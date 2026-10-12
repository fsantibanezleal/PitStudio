"""T-018-005: `tools/make_parity_fixtures.py` writes parity fixtures with SHA-256 pins and rejects bad sets.

Invalid, tampered and empty fixture sets fail.

Requirements: DC-018-04 (fixture file contract), FR-018-67 (a fixture that fails its schema or its pinned SHA-256, an
empty fixture set, or an invalid report or measurement file fails the suite or the build, naming the file; no engine
passes on an empty or invalid set).

Spec: specs/018-web-cases/ (spec.md DC-018-04 and FR-018-67, plan.md, tasks.md T-018-005; draft schema
`contracts/parity-fixture.schema.json`, engine schemas `contracts/engines/<engine>.schema.json`, the checker classes
listed in `contracts/examples/index.json` for the parity-fixture schema).

Expected API of the implementation (`tools/make_parity_fixtures.py`, loaded here by path; the heavy reference runs of
section 7.1 live in its `generate` command and need the pipeline environment, so they are not exercised by this
root-environment test):

- `build_fixture(engine, function, fixture, reference, tolerance, cases) -> dict`: adds `schema_version` "1.0"; keys
  engine, fixture, function, reference, tolerance, cases (DC-018-04).
- `write_fixture(root, doc, *, gzip=False) -> Path`: writes `<root>/<engine>/<fixture>.json` (or `.json.gz`), UTF-8,
  LF, deterministic bytes (gzip with mtime 0), and appends or updates the line "<sha256>  <engine>/<file>" in
  `<root>/SHA256SUMS` (sha256sum format, the pin of the STORED bytes); returns the path.
- `check_fixtures(root, engines=None) -> list[Problem]`: a Problem has `.path` (relative to root, or the engine
  folder), `.rule` and `.message`; an empty list means ok. One problem per defect, always naming the file:
  "loader" (not UTF-8, BOM, malformed JSON or gzip, duplicate key, NaN or Infinity: the FR-001-05 loader rules),
  "schema" (fails parity-fixture.schema.json: unknown key, missing field, fewer than 200 vectors for an analytical
  class, a looser tolerance, empty cases), "engine-schema" (a vector input or output not valid against the DC-018-02
  schema of its function; the message names the vector index), "name-mismatch" (`fixture` different from the file
  stem, or `engine` different from its folder), "unknown-engine" (a folder that is not an engine id of spec 018
  section 7.1), "sha256-mismatch" (the bytes differ from the pin in SHA256SUMS), "unpinned" (a fixture file with no
  line in SHA256SUMS), "missing-file" (a pinned file that does not exist), "empty-fixture-set" (an engine of
  `engines`, default every engine present, with no fixture file).
- CLI: `python tools/make_parity_fixtures.py check --root DIR [--engines a,b]` exits 0 when the list is empty, 1
  otherwise with one stderr line per problem (`<path>: <rule>: <message>`), 2 for a usage error.

Oracle: hand calculation. The vectors are the closed form powder factor = Q / (B S H) (spec 002 of minephys,
FR-002-01) evaluated here with plain floats on a fixed pseudo-random list; the pins are recomputed here with
`hashlib.sha256`; every hostile case is one hand mutation of a valid file.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "make_parity_fixtures.py"


def _tool() -> ModuleType:
    assert TOOL.is_file(), "tools/make_parity_fixtures.py exists (T-018-005)"
    spec = importlib.util.spec_from_file_location("make_parity_fixtures", TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cases(n: int = 200, seed: int = 20261011) -> list[dict]:
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        q = round(rnd.uniform(1.0, 1.0e5), 6)
        b, s = round(rnd.uniform(0.5, 50.0), 6), round(rnd.uniform(0.5, 50.0), 6)
        h = round(rnd.uniform(1.0, 100.0), 6)
        out.append(
            {
                "name": f"v{i}",
                "input": {"charge_kg": q, "burden_m": b, "spacing_m": s, "bench_height_m": h},
                "output": {"powder_factor_kg_per_m3": q / (b * s * h)},
            }
        )
    return out


REFERENCE = {"name": "minephys", "version": "0.1.0", "callable": "minephys.blasting.powder_factor"}
TOLERANCE = {"class": "analytical-closed-form", "rtol": 1e-9, "atol_scale": 1e-12}


def _doc(tool: ModuleType, **over) -> dict:
    doc = tool.build_fixture(
        "blasting",
        "powder_factor",
        over.pop("fixture", "powder-factor"),
        REFERENCE,
        TOLERANCE,
        over.pop("cases", _cases()),
    )
    doc.update(over)
    return doc


def _rules(problems) -> list[str]:
    return sorted(p.rule for p in problems)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "parity"


@pytest.mark.req("DC-018-04")
def test_build_fixture_returns_the_dc_018_04_document() -> None:
    tool = _tool()
    doc = _doc(tool)
    assert doc["schema_version"] == "1.0"
    assert doc["engine"] == "blasting"
    assert doc["function"] == "powder_factor"
    assert doc["fixture"] == "powder-factor"
    assert doc["reference"] == REFERENCE
    assert doc["tolerance"] == TOLERANCE
    assert len(doc["cases"]) == 200


@pytest.mark.req("DC-018-04")
def test_a_written_fixture_lands_in_its_engine_folder_with_a_sha256sum_pin(root: Path) -> None:
    tool = _tool()
    path = tool.write_fixture(root, _doc(tool))
    assert path == root / "blasting" / "powder-factor.json"
    assert json.loads(path.read_text(encoding="utf-8"))["cases"][0]["name"] == "v0"
    pins = (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert pins == [f"{_sha(path)}  blasting/powder-factor.json"]
    assert tool.check_fixtures(root) == []


@pytest.mark.req("DC-018-04")
def test_writing_is_deterministic_and_repeated_writes_keep_one_pin(root: Path) -> None:
    tool = _tool()
    first = tool.write_fixture(root, _doc(tool)).read_bytes()
    pins = (root / "SHA256SUMS").read_text(encoding="utf-8")
    second = tool.write_fixture(root, _doc(tool)).read_bytes()
    assert first == second
    assert (root / "SHA256SUMS").read_text(encoding="utf-8") == pins
    assert b"\r" not in first
    assert first.endswith(b"\n")


@pytest.mark.req("DC-018-04")
def test_a_gzip_fixture_is_deterministic_and_pins_the_stored_bytes(root: Path) -> None:
    tool = _tool()
    path = tool.write_fixture(root, _doc(tool), gzip=True)
    assert path.name == "powder-factor.json.gz"
    raw = path.read_bytes()
    assert raw[4:8] == b"\x00\x00\x00\x00", "gzip mtime is fixed at 0 so the bytes do not depend on the clock"
    assert json.loads(gzip.decompress(raw).decode("utf-8"))["fixture"] == "powder-factor"
    assert (
        f"{hashlib.sha256(raw).hexdigest()}  blasting/powder-factor.json.gz"
        in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    )
    assert tool.check_fixtures(root) == []
    assert tool.write_fixture(root.parent / "again", _doc(tool), gzip=True).read_bytes() == raw


@pytest.mark.req("FR-018-67")
def test_one_changed_byte_fails_the_pinned_sha256_and_names_the_file(root: Path) -> None:
    tool = _tool()
    path = tool.write_fixture(root, _doc(tool))
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0x01
    path.write_bytes(bytes(data))
    problems = tool.check_fixtures(root)
    assert any(p.rule == "sha256-mismatch" and "blasting/powder-factor.json" in str(p.path) for p in problems), problems


@pytest.mark.req("FR-018-67")
def test_a_fixture_without_a_pin_and_a_pin_without_a_file_are_problems(root: Path) -> None:
    tool = _tool()
    path = tool.write_fixture(root, _doc(tool))
    (root / "SHA256SUMS").write_text("", encoding="utf-8")
    assert "unpinned" in _rules(tool.check_fixtures(root))
    (root / "SHA256SUMS").write_text(
        f"{_sha(path)}  blasting/powder-factor.json\n{'0' * 64}  blasting/ghost.json\n", encoding="utf-8"
    )
    problems = tool.check_fixtures(root)
    assert any(p.rule == "missing-file" and "ghost.json" in str(p.path) for p in problems), problems


@pytest.mark.req("FR-018-67")
def test_an_empty_fixture_set_fails_for_the_engine_that_has_none(root: Path) -> None:
    tool = _tool()
    tool.write_fixture(root, _doc(tool))
    problems = tool.check_fixtures(root, engines=["blasting", "plume"])
    assert any(p.rule == "empty-fixture-set" and "plume" in str(p.path) + p.message for p in problems), problems
    assert not any("blasting" in str(p.path) for p in problems)
    (root / "plume").mkdir()
    assert any(p.rule == "empty-fixture-set" for p in tool.check_fixtures(root, engines=["plume"]))
    assert any(
        p.rule == "empty-fixture-set" for p in tool.check_fixtures(root.parent / "nowhere", engines=["blasting"])
    )


def _write_raw(root: Path, name: str, data: bytes, engine: str = "blasting") -> Path:
    path = root / engine / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    pins = root / "SHA256SUMS"
    with pins.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{hashlib.sha256(data).hexdigest()}  {engine}/{name}\n")
    return path


def _schema_problems(tool: ModuleType, root: Path, doc: dict, name: str = "powder-factor.json") -> list:
    _write_raw(root, name, (json.dumps(doc, indent=2) + "\n").encode("utf-8"))
    return tool.check_fixtures(root)


@pytest.mark.req("FR-018-67")
@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("unknown top-level key", lambda d: d.update(extra="x")),
        ("missing reference version", lambda d: d["reference"].pop("version")),
        ("no vectors", lambda d: d.update(cases=[])),
        ("199 vectors for an analytical class", lambda d: d.update(cases=d["cases"][:199])),
        ("a closed-form tolerance looser than 1e-9", lambda d: d["tolerance"].update(rtol=1e-6)),
        ("an unknown tolerance class", lambda d: d["tolerance"].update({"class": "approximately-fine"})),
        ("a function key outside the parameter pattern", lambda d: d.update(function="Powder Factor")),
    ],
)
def test_a_fixture_that_fails_its_schema_is_a_problem_naming_the_file(root: Path, label: str, mutate) -> None:
    tool = _tool()
    doc = copy.deepcopy(_doc(tool))
    mutate(doc)
    problems = _schema_problems(tool, root, doc)
    assert any(p.rule == "schema" and "powder-factor.json" in str(p.path) for p in problems), (label, problems)


@pytest.mark.req("FR-018-67")
def test_a_vector_that_is_not_valid_against_the_engine_schema_is_a_problem_naming_the_vector(root: Path) -> None:
    tool = _tool()
    doc = copy.deepcopy(_doc(tool))
    doc["cases"][7]["input"]["burden_m"] = -3.0  # exclusiveMinimum 0 in blasting.schema.json
    problems = _schema_problems(tool, root, doc)
    assert any(p.rule == "engine-schema" and "7" in p.message for p in problems), problems
    doc2 = copy.deepcopy(_doc(tool))
    doc2["cases"][3]["output"]["powder_factor_kg_per_m3"] = -1.0  # minimum 0
    problems2 = _schema_problems(tool, root.parent / "second", doc2)
    assert any(p.rule == "engine-schema" for p in problems2), problems2


@pytest.mark.req("FR-018-67")
def test_a_fixture_id_that_differs_from_the_file_stem_or_the_wrong_engine_folder_is_a_problem(root: Path) -> None:
    tool = _tool()
    doc = _doc(tool, fixture="something-else")
    problems = _schema_problems(tool, root, doc, name="powder-factor.json")
    assert any(p.rule == "name-mismatch" for p in problems), problems
    other = _doc(tool)
    other_root = root.parent / "wrong-folder"
    _write_raw(other_root, "powder-factor.json", (json.dumps(other) + "\n").encode("utf-8"), engine="plume")
    assert any(p.rule == "name-mismatch" for p in tool.check_fixtures(other_root))


@pytest.mark.req("FR-018-67")
def test_a_folder_that_is_not_an_engine_is_unknown(root: Path) -> None:
    tool = _tool()
    _write_raw(root, "x.json", b"{}\n", engine="not-an-engine")
    assert "unknown-engine" in _rules(tool.check_fixtures(root))


@pytest.mark.req("FR-018-67")
@pytest.mark.parametrize(
    ("label", "data"),
    [
        ("NaN", b'{"schema_version": "1.0", "cases": [{"input": {}, "output": {"x": NaN}}]}\n'),
        ("Infinity", b'{"schema_version": "1.0", "cases": [{"input": {}, "output": {"x": Infinity}}]}\n'),
        ("a duplicate key", b'{"schema_version": "1.0", "schema_version": "1.0"}\n'),
        ("a byte order mark", b"\xef\xbb\xbf{}\n"),
        ("malformed JSON", b'{"schema_version": '),
        ("invalid UTF-8", b'{"a": "\xff\xfe"}\n'),
        ("an empty file", b""),
    ],
)
def test_loader_level_defects_are_problems_naming_the_file(root: Path, label: str, data: bytes) -> None:
    tool = _tool()
    _write_raw(root, "powder-factor.json", data)
    problems = tool.check_fixtures(root)
    assert any(p.rule == "loader" and "powder-factor.json" in str(p.path) for p in problems), (label, problems)


@pytest.mark.req("FR-018-67")
def test_a_malformed_gzip_file_is_a_loader_problem(root: Path) -> None:
    tool = _tool()
    _write_raw(root, "powder-factor.json.gz", b"this is not gzip")
    assert any(p.rule == "loader" for p in tool.check_fixtures(root))


def _cli(*args: str) -> subprocess.CompletedProcess:
    assert TOOL.is_file(), "tools/make_parity_fixtures.py exists (T-018-005)"
    return subprocess.run(
        [sys.executable, str(TOOL), *args], capture_output=True, text=True, cwd=ROOT, timeout=120, check=False
    )


@pytest.mark.req("FR-018-67")
def test_the_check_command_exits_0_on_a_clean_set_1_naming_the_file_otherwise_and_2_on_misuse(root: Path) -> None:
    tool = _tool()
    path = tool.write_fixture(root, _doc(tool))
    ok = _cli("check", "--root", str(root))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    data = bytearray(path.read_bytes())
    data[100] ^= 0x01
    path.write_bytes(bytes(data))
    bad = _cli("check", "--root", str(root))
    assert bad.returncode == 1
    assert "blasting/powder-factor.json" in bad.stderr.replace("\\", "/")
    assert "sha256-mismatch" in bad.stderr
    assert "Traceback" not in bad.stderr
    empty = _cli("check", "--root", str(root.parent / "empty"), "--engines", "blasting")
    assert empty.returncode == 1
    assert "blasting" in empty.stderr
    assert _cli().returncode == 2
    assert _cli("bogus-command").returncode == 2
