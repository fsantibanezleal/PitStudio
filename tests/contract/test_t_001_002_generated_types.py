"""T-001-002 · generated Pydantic modules, drift detection, unsupported constructs: FR-001-40, FR-001-42, FR-001-43,
FR-001-46, NFR-001-04 (the TypeScript half lives in ``web/src/contracts/generated.test.ts``: FR-001-41, FR-001-44,
NFR-001-02).

Oracles: byte-for-byte comparison of two fresh generations and of a fresh generation with the committed files (the
reference is the generator's own determinism claim, NFR-001-04: two runs, two output folders, two hash seeds, two
working directories); a seeded one-character edit, an orphan file and a missing file must each be named by
``--check``; unsupported constructs (``prefixItems``, ``$dynamicRef``, a remote ``$ref``, invalid JSON, a schema that
fails the 2020-12 meta-schema) and an unknown option must leave a pre-populated output folder byte-identical;
``ruff format --check`` and ``mypy`` as the reference tools for formatting and typing; the locked pydantic version is
read from ``uv.lock``.

Expected API: ``python tools/gen_types.py [--check] [--contracts DIR] [--out DIR]`` (defaults: ``contracts`` and
``src/pitstudio/contracts/_generated`` of the repository). One module ``<stem>.py`` per ``<stem>.schema.json`` (``-`` ->
``_``) plus ``__init__.py``; first line ``# Generated from contracts/<file> by tools/gen_types.py. Do not edit.``;
``--check`` exits 0 when the output folder equals a fresh generation and 1 otherwise, listing every differing, orphan
and missing file by name, writing nothing; a generation error exits non-zero (and not 1 for usage), names the schema
file and writes nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_support as cs

GENERATED = cs.ROOT / "src" / "pitstudio" / "contracts" / "_generated"
STEMS = list(cs.SCHEMA_STEMS)
HEADER = "# Generated from contracts/{file} by tools/gen_types.py. Do not edit."


def gen(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    assert cs.GEN_TYPES.is_file(), "tools/gen_types.py does not exist (task T-001-002)"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(cs.ROOT / "src"), environment.get("PYTHONPATH", "")]))
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, str(cs.GEN_TYPES), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd or cs.ROOT,
        env=environment,
        timeout=600,
    )


def snapshot(folder: Path) -> dict[str, str]:
    return {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def fresh(tmp: Path, name: str = "out", **env: str) -> Path:
    out = tmp / name
    proc = gen("--out", str(out), env=env or None)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return out


def contracts_copy(tmp: Path) -> Path:
    d = tmp / "contracts"
    d.mkdir(parents=True)
    for stem in STEMS:
        shutil.copy(cs.schema_path(stem), d / f"{stem}.schema.json")
    return d


# ----------------------------------------------------------------------------------------------------------------
# FR-001-40 · one module per contract, pinned header, closed models
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-40")
@pytest.mark.req("DC-001-06")
def test_fr_001_40_one_module_per_contract_plus_an_init_with_the_pinned_header_and_no_noise(tmp_path: Path) -> None:
    out = fresh(tmp_path)
    assert sorted(p.name for p in out.iterdir()) == sorted([*(f"{s}.py" for s in STEMS), "__init__.py"])
    for stem in STEMS:
        text = (out / f"{stem}.py").read_bytes().decode("utf-8")
        assert text.split("\n", 1)[0] == HEADER.format(file=f"{stem}.schema.json")
        assert "\r" not in text
        assert text.endswith("\n")
        assert not text.endswith("\n\n")
        assert "timestamp" not in text.lower().split("import", 1)[0]  # --disable-timestamp
        assert str(cs.ROOT) not in text
        assert str(tmp_path) not in text
        assert str(Path.home()) not in text
        assert "from pydantic import" in text
        assert "BaseModel" in text
        assert 'extra="forbid"' in text  # ruff-formatted double quotes; --extra-fields forbid
    init = (out / "__init__.py").read_text(encoding="utf-8")
    assert all(stem in init for stem in STEMS)
    assert "\r" not in init


@pytest.mark.req("FR-001-40")
def test_fr_001_40_a_dash_in_the_schema_stem_becomes_an_underscore_in_the_module_name(tmp_path: Path) -> None:
    contracts = contracts_copy(tmp_path)
    (contracts / "run-events.schema.json").write_text(
        json.dumps(
            {
                "$schema": cs.META_2020_12,
                "$id": "https://fsantibanezleal.github.io/PitStudio/contracts/run-events.schema.json",
                "title": "Run events",
                "type": "object",
                "additionalProperties": False,
                "required": ["n"],
                "properties": {"n": {"type": "integer"}},
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    proc = gen("--contracts", str(contracts), "--out", str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (out / "run_events.py").is_file()
    assert (out / "run_events.py").read_text(encoding="utf-8").startswith(HEADER.format(file="run-events.schema.json"))
    assert "run_events" in (out / "__init__.py").read_text(encoding="utf-8")


@pytest.mark.req("FR-001-40")
def test_fr_001_40_generated_files_pass_ruff_format_check(tmp_path: Path) -> None:
    out = fresh(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "--config",
            str(cs.ROOT / "pyproject.toml"),
            *map(str, sorted(out.glob("*.py"))),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.req("FR-001-40")
def test_fr_001_40_generated_models_are_closed_and_enforce_the_constraints_the_schema_states(tmp_path: Path) -> None:
    import importlib.util

    out = fresh(tmp_path)
    spec = importlib.util.spec_from_file_location("gen_job_probe", out / "recipe.py")
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    from pydantic import ValidationError

    good = {"recipe": "a2-haulage", "profile": "laptop-rtx5000ada"}
    module.JobRequest.model_validate(good, strict=True)
    for bad in (
        {**good, "entry": "x"},
        {**good, "recipe": "../x"},
        {**good, "recipe": "A"},
        {"recipe": "a"},
        {**good, "stages": []},
        {**good, "stages": [{"id": "st99_magic"}]},
    ):
        with pytest.raises(ValidationError):
            module.JobRequest.model_validate(bad, strict=True)


@pytest.mark.req("FR-001-40")
def test_fr_001_40_dependency_versions_are_the_pinned_ones() -> None:
    lock = tomllib.loads((cs.ROOT / "uv.lock").read_text(encoding="utf-8"))
    versions = {p["name"]: p["version"] for p in lock["package"]}
    assert versions["datamodel-code-generator"] == "0.83.0"
    assert GENERATED.is_dir()
    assert {p.stem for p in GENERATED.glob("*.py")} >= {*STEMS, "__init__"}


# ----------------------------------------------------------------------------------------------------------------
# NFR-001-04 · determinism
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("NFR-001-04")
def test_nfr_001_04_two_generations_are_byte_identical(tmp_path: Path) -> None:
    a, b = fresh(tmp_path, "a"), fresh(tmp_path, "b")
    assert snapshot(a) == snapshot(b)


@pytest.mark.req("NFR-001-04")
def test_nfr_001_04_output_does_not_depend_on_the_hash_seed_or_the_working_directory(tmp_path: Path) -> None:
    a = tmp_path / "a"
    assert gen("--out", str(a), env={"PYTHONHASHSEED": "1"}).returncode == 0
    b = tmp_path / "b"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert gen("--out", str(b), cwd=elsewhere, env={"PYTHONHASHSEED": "12345"}).returncode == 0
    assert snapshot(a) == snapshot(b)


@pytest.mark.req("NFR-001-04")
@pytest.mark.req("FR-001-42")
def test_nfr_001_04_the_committed_generated_files_equal_a_fresh_generation(tmp_path: Path) -> None:
    assert snapshot(fresh(tmp_path)) == snapshot(GENERATED)
    proc = gen("--check")
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ----------------------------------------------------------------------------------------------------------------
# FR-001-42 · drift
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-42")
def test_fr_001_42_check_passes_on_a_fresh_generation_and_writes_nothing(tmp_path: Path) -> None:
    out = fresh(tmp_path)
    before = snapshot(out)
    proc = gen("--check", "--out", str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert snapshot(out) == before


@pytest.mark.req("FR-001-42")
@pytest.mark.parametrize(
    "target", ["manifest.py", "recipe.py", "tools.py", "sources.py", "capabilities.py", "__init__.py"]
)
def test_fr_001_42_a_one_character_edit_is_reported_by_file_name(tmp_path: Path, target: str) -> None:
    out = fresh(tmp_path)
    p = out / target
    data = p.read_text(encoding="utf-8")
    index = max(data.rfind("a"), data.rfind("e"))
    p.write_text(
        data[:index] + ("b" if data[index] != "b" else "c") + data[index + 1 :], encoding="utf-8", newline="\n"
    )
    before = snapshot(out)
    proc = gen("--check", "--out", str(out))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert target in proc.stdout + proc.stderr
    assert snapshot(out) == before  # --check never repairs


@pytest.mark.req("FR-001-42")
def test_fr_001_42_an_orphan_file_a_missing_file_and_a_schema_without_a_file_are_all_listed(tmp_path: Path) -> None:
    out = fresh(tmp_path)
    (out / "ghost.py").write_text("# orphan\n", encoding="utf-8")  # a generated file with no schema
    (out / "recipe.py").unlink()  # a schema with no generated file
    manifest = out / "manifest.py"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8", newline="\n")
    proc = gen("--check", "--out", str(out))
    text = proc.stdout + proc.stderr
    assert proc.returncode == 1
    for name in ("ghost.py", "recipe.py", "manifest.py"):
        assert name in text, name  # every differing file is listed, not just the first


@pytest.mark.req("FR-001-42")
def test_fr_001_42_a_schema_change_makes_the_matching_module_drift(tmp_path: Path) -> None:
    out = fresh(tmp_path)
    contracts = contracts_copy(tmp_path)
    schema = json.loads((contracts / "capabilities.schema.json").read_text(encoding="utf-8"))
    schema["properties"]["gpu"]["maxLength"] = 127
    (contracts / "capabilities.schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
    proc = gen("--check", "--contracts", str(contracts), "--out", str(out))
    assert proc.returncode == 1
    assert "capabilities.py" in proc.stdout + proc.stderr


@pytest.mark.req("FR-001-42")
def test_fr_001_42_an_empty_or_missing_output_folder_is_drift_not_a_crash(tmp_path: Path) -> None:
    proc = gen("--check", "--out", str(tmp_path / "does-not-exist"))
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = gen("--check", "--out", str(empty))
    assert proc.returncode == 1
    assert all(f"{s}.py" in proc.stdout + proc.stderr for s in STEMS)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-46 · unsupported constructs and unknown options leave the output untouched
# ----------------------------------------------------------------------------------------------------------------
BAD_SCHEMAS: dict[str, Any] = {
    "prefix": {"$schema": cs.META_2020_12, "type": "array", "prefixItems": [{"type": "string"}]},
    "dynamic": {
        "$schema": cs.META_2020_12,
        "$dynamicAnchor": "node",
        "type": "object",
        "properties": {"child": {"$dynamicRef": "#node"}},
    },
    "remote": {
        "$schema": cs.META_2020_12,
        "type": "object",
        "properties": {"x": {"$ref": "https://example.com/other.schema.json#/$defs/x"}},
    },
    "metainvalid": {"$schema": cs.META_2020_12, "type": "object", "properties": {"a": {"type": "nonsense"}}},
    "minimum-text": {"$schema": cs.META_2020_12, "type": "number", "minimum": "zero"},
}


@pytest.mark.req("FR-001-46")
@pytest.mark.parametrize("label", sorted(BAD_SCHEMAS))
def test_fr_001_46_an_unsupported_or_invalid_schema_fails_naming_it_and_changes_no_file(
    tmp_path: Path, label: str
) -> None:
    out = fresh(tmp_path, "committed")
    before = snapshot(out)
    contracts = contracts_copy(tmp_path)
    (contracts / "bad.schema.json").write_text(json.dumps(BAD_SCHEMAS[label]), encoding="utf-8")
    proc = gen("--contracts", str(contracts), "--out", str(out))
    assert proc.returncode != 0
    assert "bad.schema.json" in proc.stdout + proc.stderr
    assert "Traceback" not in proc.stderr
    assert snapshot(out) == before, "a failed run must not write, delete or rewrite any generated file"
    check = gen("--check", "--contracts", str(contracts), "--out", str(out))
    assert check.returncode != 0
    assert "bad.schema.json" in check.stdout + check.stderr


@pytest.mark.req("FR-001-46")
def test_fr_001_46_malformed_json_and_a_bom_are_rejected_naming_the_file(tmp_path: Path) -> None:
    out = fresh(tmp_path, "committed")
    before = snapshot(out)
    for payload in (b'{"type": "object"', b"\xef\xbb\xbf{}", b"", b'{"a": NaN}', b"\xff\xfe"):
        contracts = contracts_copy(tmp_path / f"case{len(payload)}x")
        (contracts / "broken.schema.json").write_bytes(payload)
        proc = gen("--contracts", str(contracts), "--out", str(out))
        assert proc.returncode != 0
        assert "broken.schema.json" in proc.stdout + proc.stderr
        assert snapshot(out) == before


@pytest.mark.req("FR-001-46")
@pytest.mark.parametrize(
    "args",
    [["--frobnicate"], ["--out"], ["--contracts", "x", "--nope"], ["stray-positional"], ["--schema-version", "draft7"]],
)
def test_fr_001_46_an_unknown_option_is_a_usage_error_and_writes_nothing(tmp_path: Path, args: list[str]) -> None:
    out = fresh(tmp_path, "committed")
    before = snapshot(out)
    proc = gen(*args, "--out", str(out)) if args[-1] != "--out" else gen(*args)
    assert proc.returncode not in (0, 1), (args, proc.stdout, proc.stderr)  # 2 = usage, never a drift answer
    assert "Traceback" not in proc.stderr
    assert snapshot(out) == before


@pytest.mark.req("FR-001-46")
def test_fr_001_46_the_committed_generated_folder_is_untouched_by_a_failed_default_run(tmp_path: Path) -> None:
    before = snapshot(GENERATED)
    contracts = contracts_copy(tmp_path)
    (contracts / "bad.schema.json").write_text(json.dumps(BAD_SCHEMAS["prefix"]), encoding="utf-8")
    proc = gen("--contracts", str(contracts))  # default --out: the committed folder
    assert proc.returncode != 0
    assert "bad.schema.json" in proc.stdout + proc.stderr
    assert snapshot(GENERATED) == before


# ----------------------------------------------------------------------------------------------------------------
# FR-001-43 · import on Python 3.12 and 3.14, parse the valid corpus, mypy and ruff
# ----------------------------------------------------------------------------------------------------------------
IMPORT_SCRIPT = """
import importlib.util, json, sys
from pathlib import Path
gen, fixtures = Path(sys.argv[1]), json.loads(sys.argv[2])
names = ["manifest", "recipe", "tools", "sources", "capabilities"]
mods = {}
for stem in names:
    spec = importlib.util.spec_from_file_location("gen_" + stem, gen / (stem + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    mods[stem] = mod
ok = 0
for stem, target, doc in fixtures:
    mod = mods[stem]
    if target == "#":
        title = json.loads((Path(sys.argv[3]) / (stem + ".schema.json")).read_text(encoding="utf-8"))["title"]
        model = next(getattr(mod, n) for n in ("Model", title.title().replace(" ", "")) if hasattr(mod, n))
    else:
        model = getattr(mod, "".join(w.capitalize() for w in target.rsplit("/", 1)[1].split("_")))
    model.model_validate(doc, strict=True)
    ok += 1
print(sys.version_info[:2], ok)
"""


def valid_examples() -> list[list[Any]]:
    return [
        [e["schema"], e["target"], cs.fixture_json(e)] for e in cs.entries(valid=True) if e["file"].endswith(".json")
    ]


def locked_pydantic() -> str:
    lock = tomllib.loads((cs.ROOT / "uv.lock").read_text(encoding="utf-8"))
    return next(p["version"] for p in lock["package"] if p["name"] == "pydantic")


@pytest.mark.req("FR-001-43")
def test_fr_001_43_generated_modules_import_on_the_root_python_and_parse_every_valid_example() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", IMPORT_SCRIPT, str(GENERATED), json.dumps(valid_examples()), str(cs.CONTRACTS)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip().endswith(str(len(valid_examples())))


@pytest.mark.req("FR-001-43")
def test_fr_001_43_generated_modules_import_on_python_3_12_with_the_locked_pydantic() -> None:
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--no-project",
            "--python",
            "3.12",
            "--with",
            f"pydantic=={locked_pydantic()}",
            "python",
            "-c",
            IMPORT_SCRIPT,
            str(GENERATED),
            json.dumps(valid_examples()),
            str(cs.CONTRACTS),
        ],
        capture_output=True,
        text=True,
        timeout=900,
        cwd=cs.ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "(3, 12)" in proc.stdout


@pytest.mark.req("FR-001-43")
def test_fr_001_43_committed_generated_files_are_ruff_formatted_and_mypy_clean() -> None:
    assert {p.stem for p in GENERATED.glob("*.py")} >= {*STEMS, "__init__"}
    fmt = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", str(GENERATED)], capture_output=True, text=True, cwd=cs.ROOT
    )
    assert fmt.returncode == 0, fmt.stdout + fmt.stderr
    typing = subprocess.run(
        [sys.executable, "-m", "mypy", "src"], capture_output=True, text=True, cwd=cs.ROOT, timeout=900
    )
    assert typing.returncode == 0, typing.stdout + typing.stderr


# ----------------------------------------------------------------------------------------------------------------
# CI and package wiring (FR-001-42 for both runtimes, FR-001-41)
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-42")
def test_fr_001_42_ci_runs_both_drift_checks() -> None:
    wf = yaml.safe_load((cs.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    python_runs = " ".join(str(s.get("run", "")) for s in wf["jobs"]["python"]["steps"])
    web_runs = " ".join(str(s.get("run", "")) for s in wf["jobs"]["web"]["steps"])
    assert "tools/gen_types.py --check" in python_runs
    assert "gen:types --check" in web_runs or "gen:types -- --check" in web_runs


@pytest.mark.req("FR-001-41")
def test_fr_001_41_web_package_declares_the_generator_script_and_the_pinned_dependency() -> None:
    package = json.loads((cs.ROOT / "web/package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["gen:types"].strip().startswith("node scripts/gen-types.mjs")
    assert "json-schema-to-typescript" in package["devDependencies"]
    assert (cs.ROOT / "web/scripts/gen-types.mjs").is_file()
    lock = (cs.ROOT / "web/pnpm-lock.yaml").read_text(encoding="utf-8")
    assert "json-schema-to-typescript@16.0.0" in lock or "json-schema-to-typescript: 16.0.0" in lock
