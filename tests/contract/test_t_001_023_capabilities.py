"""T-001-023 · the capability report stays honest: FR-001-35, FR-001-36, FR-001-37 (and FR-001-07 for run_bench).

Oracles: the bounds of data-model 6 (probe-name pattern ``^[a-z][a-z0-9_]{0,31}$``, 64 probes, versions 32 x 64,
metrics 64 x 200, telemetry 32, notes 20 x 300, ``error`` 300, GPU name 128, driver pattern), the five sample results of
the existing ``test_capabilities_contract.py`` (they must stay valid), corpus fixtures with fixed pointers, python
``jsonschema`` as reference validator and a strict standard-library JSON parser (``parse_constant`` raising) as the
reference for "valid JSON".

Expected API: ``contracts/capabilities.schema.json`` (tightened); ``run_bench.public_view`` records a probe whose
metric or telemetry value is NaN or infinite as ``status: fail`` with ``error: "non-finite metric <name>"`` (name cut
at 64 characters), without any non-finite value left in the entry, and ``run_bench.main`` still writes
``studio/capabilities.json`` and the local report as strict JSON with the writer format of FR-001-07 (UTF-8, no BOM,
LF, 2-space indent, trailing newline).
"""

from __future__ import annotations

import copy
import json
import math
import sys
import types
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_support as cs

sys.path.insert(0, str(cs.ROOT / "studio" / "bench"))
import run_bench

VALID = json.loads((cs.FIXTURES / "capabilities/valid/capabilities.valid.json").read_text(encoding="utf-8"))
TELE = {"samples": 12, "max_temp_c": 71, "max_power_w": 80.5, "pcie_replays_delta": 0}
NAN, INF = float("nan"), float("inf")


def pairs(doc: Any) -> set[tuple[str, str]]:
    return cs.error_pairs("capabilities", "#", doc)


def ok(doc: Any) -> bool:
    return cs.accepts("capabilities", "#", doc)


def setp(doc: Any, path: list[Any], value: Any) -> Any:
    d = copy.deepcopy(doc)
    node = d
    for p in path[:-1]:
        node = node[p]
    node[path[-1]] = value
    return d


def ptr(path: list[Any]) -> str:
    return "/" + "/".join(str(p) for p in path)


def strict_loads(text: str) -> Any:
    def refuse(token: str) -> Any:
        raise ValueError(f"non-finite constant {token}")

    return json.loads(text, parse_constant=refuse)


def sample_results() -> list[dict]:
    """The samples of tests/contract/test_capabilities_contract.py (home and repo paths are scrubbed by public_view)."""
    home = str(Path.home())
    return [
        {
            "probe": "warp_newton",
            "status": "pass",
            "publish": "public",
            "env": {"python": "3.14.4"},
            "versions": {"warp": "1.17.0"},
            "metrics": {"saxpy_16M_x20_s": 0.0123},
            "telemetry": TELE,
        },
        {
            "probe": "ovrtx",
            "status": "pass",
            "publish": "local-only",
            "env": {"python": "3.12.15"},
            "versions": {"ovrtx": "0.5.0"},
            "metrics": {"frames_per_s": 12.5},
            "telemetry": TELE,
        },
        {
            "probe": "tensorrt",
            "status": "fail",
            "publish": "public",
            "versions": {},
            "error": f"FileNotFoundError: {home}\\Data\\x.onnx " + "y" * 400,
            "notes": [f"see {run_bench.ROOT}\\studio\\bench"],
        },
        {"probe": "isaacsim", "status": "skip", "notes": ["probe script not written yet"]},
    ]


# ----------------------------------------------------------------------------------------------------------------
# FR-001-35 · the tightened schema keeps its shape
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-35")
def test_fr_001_35_existing_samples_still_produce_valid_reports() -> None:
    doc = run_bench.public_view(sample_results(), "582.78", "NVIDIA RTX 5000 Ada Generation Laptop GPU")
    assert pairs(doc) == set()
    assert pairs(run_bench.public_view([], "1.0", "none")) == set()
    assert ok(VALID)


@pytest.mark.req("FR-001-35")
def test_fr_001_35_the_committed_report_validates_with_the_strict_loader() -> None:
    from pitstudio.contracts import load_json

    doc = load_json(cs.ROOT / "studio" / "capabilities.json")
    assert pairs(doc) == set()


@pytest.mark.req("FR-001-35")
def test_fr_001_35_shape_is_unchanged_status_metrics_and_error() -> None:
    for st in ("pass", "fail", "skip"):
        assert ok(setp(VALID, ["probes", "warp_newton", "status"], st))
    for bad in ("PASS", "ok", "", None, 1, True):
        assert any(
            p == "/probes/warp_newton/status" for p, _ in pairs(setp(VALID, ["probes", "warp_newton", "status"], bad))
        )
    local = ["probes", "ovrtx", "metrics"]
    assert ok(setp(VALID, local, cs.LOCAL_ONLY))
    for bad in (cs.LOCAL_ONLY + " ", "measured locally", "", 5, None, [], True):
        assert any(p == ptr(local) for p, _ in pairs(setp(VALID, local, bad))), bad
    assert ok(setp(VALID, ["probes", "warp_newton", "metrics"], {"a": 1, "b": "text", "c": 2.5}))
    for top in ("generated", "gpu", "driver", "probes"):
        d = copy.deepcopy(VALID)
        del d[top]
        assert ("", "required") in pairs(d), top
    for f in ("status", "versions"):
        d = copy.deepcopy(VALID)
        del d["probes"]["warp_newton"][f]
        assert ("/probes/warp_newton", "required") in pairs(d), f
    assert ok(cs_without(VALID, ["probes", "warp_newton", "metrics"]))
    assert ok(cs_without(VALID, ["probes", "warp_newton", "telemetry"]))


def cs_without(doc: Any, path: list[Any]) -> Any:
    d = copy.deepcopy(doc)
    node = d
    for p in path[:-1]:
        node = node[p]
    del node[path[-1]]
    return d


@pytest.mark.req("FR-001-35")
def test_fr_001_35_corpus_fixtures_of_the_class() -> None:
    items = [e for e in cs.schema_level(schema="capabilities") if e["rule"] == "FR-001-35" and not e["valid"]]
    assert len(items) >= 3
    for e in items:
        assert (e["pointer"], e["keyword"]) in pairs(cs.fixture_json(e)), (e["file"], e["pointer"], e["keyword"])


# ----------------------------------------------------------------------------------------------------------------
# FR-001-36 · bounds (data-model 6), boundary and one-beyond for every one
# ----------------------------------------------------------------------------------------------------------------
BOUNDS: list[tuple[list[Any], list[Any], list[Any]]] = [
    (["gpu"], ["g", "G" * 128], ["G" * 129, "G" * 1000, 5, None]),
    (
        ["driver"],
        ["582.78", "1.2.3", "0.0", "9" * 15 + "." + "9" * 16],
        ["582", "v582.78", "582.", ".78", "582..78", "582.78 ", "", "5" * 33, "582.7a", None, 582.78],
    ),
    (
        ["generated"],
        ["2026-10-07", "1999-12-31", "2026-01-01"],
        [
            "2026-13-01",
            "2026-00-10",
            "2026-10-00",
            "2026-10-32",
            "20261007",
            "2026-1-1",
            "2026-10-07T00:00:00Z",
            "",
            None,
        ],
    ),
    (
        ["probes", "warp_newton", "versions"],
        [{}, {f"p{i}": "1" for i in range(32)}, {"warp": "v" * 64}, {"A-b.c_1": "1.0"}, {"a" * 64: "1"}],
        [
            {f"p{i}": "1" for i in range(33)},
            {"warp": "v" * 65},
            {"a" * 65: "1"},
            {".warp": "1"},
            {"-w": "1"},
            {"w w": "1"},
            {"warp": 1},
            {"warp": None},
            [],
            "x",
        ],
    ),
    (
        ["probes", "warp_newton", "metrics"],
        [{}, {f"m{i}": 1 for i in range(64)}, {"a" * 64: 1}, {"A_b1": 2.5}, {"s": "x" * 200}, {"n": -1.5e-3}],
        [
            {f"m{i}": 1 for i in range(65)},
            {"a" * 65: 1},
            {"1a": 1},
            {"a-b": 1},
            {"a b": 1},
            {"_a": 1},
            {"s": "x" * 201},
            {"b": True},
            {"n": None},
            {"l": [1]},
            {"o": {"x": 1}},
            [],
            5,
        ],
    ),
    (
        ["probes", "warp_newton", "telemetry"],
        [{}, {f"t{i}": 1 for i in range(32)}, {"a" * 64: 1}, {"max_temp_c": 71}],
        [
            {f"t{i}": 1 for i in range(33)},
            {"a" * 65: 1},
            {"A": 1},
            {"1a": 1},
            {"a-b": 1},
            {"t": "71"},
            {"t": None},
            {"t": True},
            {"t": [1]},
            [],
            5,
        ],
    ),
    (
        ["probes", "isaacsim", "notes"],
        [[], ["n" * 300], ["n"] * 20, ["a", "b"]],
        [["n" * 301], ["n"] * 21, "a note", [1], [None], [["x"]]],
    ),
    (["probes", "tensorrt", "error"], ["e", "e" * 300], ["e" * 301, "e" * 10_000, 5, None]),
]


@pytest.mark.req("FR-001-36")
@pytest.mark.parametrize(("path", "good", "bad"), BOUNDS, ids=[ptr(b[0]) for b in BOUNDS])
def test_fr_001_36_bound_and_one_beyond(path: list[Any], good: list[Any], bad: list[Any]) -> None:
    for v in good:
        got = pairs(setp(VALID, path, v))
        assert got == set(), (ptr(path), str(v)[:40], sorted(got)[:3])
    for v in bad:
        got = pairs(setp(VALID, path, v))
        assert any(p.startswith(ptr(path)) for p, _ in got), (ptr(path), str(v)[:40])


@pytest.mark.req("FR-001-36")
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a", True),
        ("warp_newton", True),
        ("a" * 32, True),
        ("a_1", True),
        ("a0", True),
        ("a" * 33, False),
        ("", False),
        ("Warp", False),
        ("warp-newton", False),
        ("1warp", False),
        ("_warp", False),
        ("w w", False),
        ("w.n", False),
        ("wé", False),
        ("w/n", False),
        ("..", False),
    ],
)
def test_fr_001_36_probe_name_pattern_and_length(name: str, expected: bool) -> None:
    doc = copy.deepcopy(VALID)
    doc["probes"] = {name: doc["probes"]["isaacsim"]}
    assert ok(doc) is expected
    if not expected:
        assert any(p == "/probes" for p, _ in pairs(doc))


@pytest.mark.req("FR-001-36")
@pytest.mark.parametrize(
    ("count", "expected"), [(0, True), (1, True), (63, True), (64, True), (65, False), (200, False)]
)
def test_fr_001_36_at_most_64_probes(count: int, expected: bool) -> None:
    doc = copy.deepcopy(VALID)
    doc["probes"] = {f"p{i}": {"status": "skip", "versions": {}} for i in range(count)}
    assert ok(doc) is expected


@pytest.mark.req("FR-001-36")
def test_fr_001_36_unknown_fields_at_every_level_are_rejected() -> None:
    assert ("", "additionalProperties") in pairs(setp(VALID, ["host"], "box"))
    assert ("/probes/warp_newton", "additionalProperties") in pairs(
        setp(VALID, ["probes", "warp_newton", "wall_s"], 1.0)
    )
    assert ("/probes/warp_newton", "additionalProperties") in pairs(
        setp(VALID, ["probes", "warp_newton", "publish"], "public")
    )
    assert ("/probes/warp_newton", "additionalProperties") in pairs(
        setp(VALID, ["probes", "warp_newton", "env"], {"python": "3"})
    )


@pytest.mark.req("FR-001-36")
@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_fr_001_36_non_finite_numbers_are_rejected_by_the_strict_loader(tmp_path: Path, token: str) -> None:
    from pitstudio.contracts import ContractError, load_json

    text = json.dumps(VALID, indent=2).replace("0.0123", token)
    assert token in text
    p = tmp_path / "capabilities.json"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ContractError):
        load_json(p)
    text2 = json.dumps(VALID, indent=2).replace('"pcie_replays_delta": 0', f'"pcie_replays_delta": {token}')
    p.write_text(text2, encoding="utf-8")
    with pytest.raises(ContractError):
        load_json(p)


@pytest.mark.req("FR-001-36")
def test_fr_001_36_corpus_fixtures_of_the_class() -> None:
    items = [e for e in cs.schema_level(schema="capabilities") if e["rule"] == "FR-001-36" and not e["valid"]]
    assert len(items) >= 10
    for e in items:
        assert (e["pointer"], e["keyword"]) in pairs(cs.fixture_json(e)), (e["file"], e["pointer"], e["keyword"])
    loader = [e for e in cs.entries(schema="capabilities", tag_in=("loader",))]
    assert len(loader) >= 4


# ----------------------------------------------------------------------------------------------------------------
# FR-001-37 · non-finite probe values become a failed probe, and both files are still written
# ----------------------------------------------------------------------------------------------------------------
def all_finite(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(all_finite(v) for v in value.values())
    if isinstance(value, list):
        return all(all_finite(v) for v in value)
    return True


def view(result: dict) -> dict:
    return run_bench.public_view([result], "582.78", "gpu")["probes"][result["probe"]]


@pytest.mark.req("FR-001-37")
@pytest.mark.parametrize("bad", [NAN, INF, -INF], ids=["nan", "inf", "-inf"])
@pytest.mark.parametrize("where", ["metrics", "telemetry"])
def test_fr_001_37_a_non_finite_value_makes_the_probe_a_failure_named_after_the_value(bad: float, where: str) -> None:
    result = {
        "probe": "warp_newton",
        "status": "pass",
        "publish": "public",
        "versions": {"warp": "1.17.0"},
        "metrics": {"good_metric": 1.5},
        "telemetry": dict(TELE),
    }
    result[where] = {**result[where], "bad_value": bad}
    entry = view(result)
    assert entry["status"] == "fail"
    assert entry["error"] == "non-finite metric bad_value"
    assert all_finite(entry), entry
    doc = run_bench.public_view([result], "582.78", "gpu")
    json.dumps(doc, allow_nan=False)  # the whole report is serialisable
    assert pairs(doc) == set()


@pytest.mark.req("FR-001-37")
def test_fr_001_37_local_only_probes_are_handled_the_same_way_and_publish_no_figures() -> None:
    entry = view({"probe": "ovrtx", "status": "pass", "publish": "local-only", "metrics": {"frames_per_s": NAN}})
    assert entry["status"] == "fail"
    assert entry["error"] == "non-finite metric frames_per_s"
    assert entry.get("metrics") in (None, run_bench.LOCAL_ONLY)
    assert all_finite(entry)


@pytest.mark.req("FR-001-37")
def test_fr_001_37_the_error_names_the_metric_and_the_name_is_cut_at_64_characters() -> None:
    long_name = "m" * 100
    entry = view({"probe": "warp_newton", "status": "pass", "publish": "public", "metrics": {long_name: NAN}})
    assert entry["error"] == "non-finite metric " + "m" * 64
    short = view({"probe": "warp_newton", "status": "pass", "publish": "public", "metrics": {"x" * 64: NAN}})
    assert short["error"] == "non-finite metric " + "x" * 64
    assert len(short["error"]) <= 300


@pytest.mark.req("FR-001-37")
def test_fr_001_37_with_several_offenders_the_error_names_one_of_them() -> None:
    entry = view(
        {"probe": "warp_newton", "status": "pass", "publish": "public", "metrics": {"a1": NAN, "b1": INF, "c1": 1.0}}
    )
    assert entry["status"] == "fail"
    assert entry["error"] in ("non-finite metric a1", "non-finite metric b1")
    assert all_finite(entry)


@pytest.mark.req("FR-001-37")
def test_fr_001_37_finite_probes_and_string_metrics_are_unaffected() -> None:
    entry = view(
        {
            "probe": "warp_newton",
            "status": "pass",
            "publish": "public",
            "metrics": {"a": 1.0, "label": "nan", "z": 0.0},
            "telemetry": dict(TELE),
        }
    )
    assert entry["status"] == "pass"
    assert "error" not in entry
    assert entry["metrics"] == {"a": 1.0, "label": "nan", "z": 0.0}
    results = [
        {"probe": "good", "status": "pass", "publish": "public", "metrics": {"a": 1.0}},
        {"probe": "bad", "status": "pass", "publish": "public", "metrics": {"a": NAN}},
    ]
    probes = run_bench.public_view(results, "1.0", "gpu")["probes"]
    assert probes["good"]["status"] == "pass"
    assert probes["bad"]["status"] == "fail"


@pytest.mark.req("FR-001-37")
def test_fr_001_37_public_view_does_not_modify_the_results_the_local_report_needs() -> None:
    result = {
        "probe": "warp_newton",
        "status": "pass",
        "publish": "public",
        "metrics": {"a": NAN},
        "telemetry": dict(TELE),
    }
    before = copy.deepcopy(result)
    run_bench.public_view([result], "1.0", "gpu")
    assert result["status"] == before["status"] == "pass"
    assert math.isnan(result["metrics"]["a"])
    assert "error" not in result


class FakeNvml:
    @staticmethod
    def nvmlDeviceGetName(handle: Any) -> str:
        return "Fake GPU"

    @staticmethod
    def nvmlSystemGetDriverVersion() -> str:
        return "582.78"


class FakeTelemetry:
    nv = FakeNvml
    h = object()


class FakeFileLock:
    def __init__(self, path: Any) -> None:
        self.lock_file = path

    def acquire(self, timeout: float = 0) -> None:
        return None

    def release(self) -> None:
        return None


class FakeTimeout(Exception):
    pass


def fake_run(results: list[dict]) -> Any:
    def run_one(name: str, tele: Any, timeout_s: int) -> dict:
        r = next(x for x in results if x["probe"] == name)
        return copy.deepcopy(r)

    return run_one


def run_main(
    tmp: Path, monkeypatch: pytest.MonkeyPatch, results: list[dict], probes: list[str]
) -> tuple[int, Path, Path]:
    (tmp / "studio").mkdir(parents=True, exist_ok=True)
    (tmp / "locks").mkdir(exist_ok=True)
    monkeypatch.setenv("GPU_LOCK_DIR", str(tmp / "locks"))
    monkeypatch.setenv("PITSTUDIO_TMP", str(tmp / "local"))
    monkeypatch.setattr(run_bench, "ROOT", tmp)
    monkeypatch.setattr(run_bench, "Telemetry", FakeTelemetry)
    monkeypatch.setattr(run_bench, "run_one", fake_run(results))
    fake = types.ModuleType("filelock")
    fake.FileLock, fake.Timeout = FakeFileLock, FakeTimeout  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "filelock", fake)
    code = run_bench.main(["run_bench.py", *probes])
    reports = sorted((tmp / "local" / "bench").glob("bench-*.json"))
    assert len(reports) == 1
    return code, tmp / "studio" / "capabilities.json", reports[0]


@pytest.mark.req("FR-001-37")
@pytest.mark.req("FR-001-07")
def test_fr_001_37_main_still_writes_two_valid_strict_json_files_when_a_probe_returns_nan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = [
        {
            "probe": "warp_newton",
            "status": "pass",
            "publish": "public",
            "versions": {"warp": "1.17.0"},
            "metrics": {"saxpy_s": NAN, "ok_metric": 2.0},
            "telemetry": {**TELE, "max_power_w": INF},
            "wall_s": 3.5,
        },
        {
            "probe": "nvenc",
            "status": "pass",
            "publish": "public",
            "versions": {},
            "metrics": {"fps": 240.0},
            "telemetry": dict(TELE),
        },
    ]
    code, cap, local = run_main(tmp_path, monkeypatch, results, ["warp_newton", "nvenc"])
    assert code == 1  # a failed probe
    cap_text, local_text = cap.read_bytes().decode("utf-8"), local.read_bytes().decode("utf-8")
    capabilities, report = strict_loads(cap_text), strict_loads(local_text)  # strict: a NaN would raise
    assert pairs(capabilities) == set()
    probes = capabilities["probes"]
    assert probes["warp_newton"]["status"] == "fail"
    assert probes["warp_newton"]["error"] in ("non-finite metric saxpy_s", "non-finite metric max_power_w")
    assert probes["nvenc"]["status"] == "pass"
    assert all_finite(capabilities)
    assert all_finite(report)
    by_name = {r["probe"]: r for r in report["results"]}
    assert by_name["warp_newton"]["status"] == "fail"
    assert by_name["nvenc"]["status"] == "pass"
    for raw in (cap.read_bytes(), local.read_bytes()):  # the writer format of FR-001-07
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in raw
        assert raw.endswith(b"}\n")
        assert not raw.endswith(b"\n\n")
        assert raw.split(b"\n")[1].startswith(b'  "'), "2-space indentation"


@pytest.mark.req("FR-001-07")
def test_fr_001_07_run_bench_output_is_byte_identical_to_dump_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pitstudio.contracts import dump_json

    results = [
        {
            "probe": "warp_newton",
            "status": "pass",
            "publish": "public",
            "versions": {"warp": "1.17.0"},
            "metrics": {"saxpy_s": 0.0123},
            "telemetry": dict(TELE),
        }
    ]
    _, cap, _ = run_main(tmp_path, monkeypatch, results, ["warp_newton"])
    written = json.loads(cap.read_text(encoding="utf-8"))
    assert cap.read_bytes() == dump_json(written)  # equal objects, equal bytes
