# ruff: noqa: E501, PT018
"""T-003-001: the console's contract, packaging and generated OpenAPI document (US-003-1).

Requirements: DC-003-01, DC-003-02, DC-003-03, DC-003-04, FR-003-17.

Expected product facts (stated for the implementer):
  * contracts/console.schema.json promoted from specs/003-console/contracts/ (valid 2020-12, `$id`
    https://fsantibanezleal.github.io/PitStudio/contracts/console.schema.json); every example of its corpus keeps its verdict;
    generated models src/pitstudio/contracts/_generated/console.py and web/src/contracts/generated/console.ts;
  * packaging: `schemathesis` and `httpx` in the `dev` group, `fastapi`/`uvicorn` in the `api` extra, and the setuptools
    configuration of pyproject.toml finds the package folder `api/` (package `pitstudio_api`);
  * `api/openapi.json`: the committed OpenAPI 3.1 document, equal to `create_app(port=...).openapi()` and to the body of
    `GET /openapi.json`; it describes every endpoint of plan.md D1 with the status codes of D2 and response schemas named
    after the contract bodies (health, recipe list, job, job list, job created, run list, problem);
  * `tools/gen_openapi.py [--check]`: without the flag it (re)writes `api/openapi.json`; with `--check` it exits 0 when the
    file equals the generated document and 1 (naming the file) when it differs or is missing.
Oracles: the spec's own corpus (specs/003-console/contracts/examples/index.json) validated with Python `jsonschema`; the
endpoint and status tables of plan.md D1/D2 written out by hand; a seeded one-character drift in a copy of the tree.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
import schemas

ROOT = rw.ROOT
EX_DIR = ROOT / "specs" / "003-console" / "contracts" / "examples"
INDEX = json.loads((EX_DIR / "index.json").read_text(encoding="utf-8"))["examples"]
OPENAPI = ROOT / "api" / "openapi.json"

# plan.md D1 and D2, written out by hand: path -> {method: documented status codes (at least)}
ENDPOINTS: dict[str, dict[str, set[str]]] = {
    "/health": {"get": {"200"}},
    "/recipes": {"get": {"200"}},
    "/recipes/{recipe_id}": {"get": {"200", "404", "422"}},
    "/queue": {"get": {"200"}},
    "/jobs": {"post": {"202", "400", "403", "413", "415", "422"}},
    "/jobs/{job_id}": {"get": {"200", "404", "422"}},
    "/jobs/{job_id}/cancel": {"post": {"202", "403", "404", "409", "422"}},
    "/runs": {"get": {"200"}},
    "/runs/{run_id}": {"get": {"200", "404", "409", "422"}},
    "/runs/{run_id}/artefacts/{artefact_id}": {"get": {"200", "206", "404", "416", "422"}},
    "/runs/{run_id}/events": {"get": {"200", "404", "422", "429"}},
}


@pytest.mark.req("DC-003-01")
def test_dc_003_01_the_console_schema_is_promoted_and_valid() -> None:
    p = ROOT / "contracts" / "console.schema.json"
    assert p.is_file(), "contracts/console.schema.json is not promoted from specs/003-console/contracts/"
    doc = json.loads(p.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(doc)
    assert doc["$id"] == "https://fsantibanezleal.github.io/PitStudio/contracts/console.schema.json"


@pytest.mark.req("DC-003-01")
@pytest.mark.req("DC-003-03")
@pytest.mark.parametrize("entry", INDEX, ids=[e["file"] for e in INDEX])
def test_dc_003_01_corpus_verdicts_hold_on_the_promoted_schema(entry: dict[str, Any]) -> None:
    assert (ROOT / "contracts" / entry["schema"]).is_file(), "schema not promoted to contracts/"
    inst = json.loads((EX_DIR / entry["file"]).read_text(encoding="utf-8"))
    errs = list(schemas.validator(entry["schema"].removesuffix(".schema.json"), entry["target"]).iter_errors(inst))
    assert (errs == []) == entry["valid"], f"{entry['file']}: {[e.message for e in errs][:2]}"


@pytest.mark.req("DC-003-01")
@pytest.mark.req("DC-003-04")
def test_dc_003_04_generated_models_exist_for_the_console_contract() -> None:
    py = ROOT / "src" / "pitstudio" / "contracts" / "_generated" / "console.py"
    ts = ROOT / "web" / "src" / "contracts" / "generated" / "console.ts"
    assert py.is_file() and ts.is_file(), "generated Python and TypeScript models are missing"
    assert (
        py.read_text(encoding="utf-8")
        .splitlines()[0]
        .startswith("# Generated from contracts/console.schema.json by tools/gen_types.py")
    )
    assert "Generated from contracts/console.schema.json" in ts.read_text(encoding="utf-8").splitlines()[0]


@pytest.mark.req("DC-003-02")
def test_dc_003_02_dependencies_and_packaging() -> None:
    pp = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev = " ".join(pp["dependency-groups"]["dev"])
    assert re.search(r"\bschemathesis\b", dev) and re.search(r"\bhttpx\b", dev), (
        "schemathesis and httpx must be in the dev group"
    )
    api = " ".join(pp["project"]["optional-dependencies"]["api"])
    assert "fastapi" in api and "uvicorn" in api
    setuptools_cfg = json.dumps(pp.get("tool", {}).get("setuptools", {}))
    assert '"api"' in setuptools_cfg or "api/" in setuptools_cfg or "pitstudio_api" in setuptools_cfg, (
        f"setuptools does not search api/: {setuptools_cfg}"
    )
    assert (
        (ROOT / "api" / "pitstudio_api" / "__init__.py").is_file()
        and (ROOT / "api" / "pitstudio_api" / "app.py").is_file()
        and (ROOT / "api" / "pitstudio_api" / "__main__.py").is_file()
    )


# ---- FR-003-17: the OpenAPI document --------------------------------------------------------------------------------------------------------
def committed() -> dict[str, Any]:
    assert OPENAPI.is_file(), "api/openapi.json is not committed"
    return json.loads(OPENAPI.read_text(encoding="utf-8"))


@pytest.mark.req("FR-003-17")
def test_fr_003_17_the_committed_document_describes_every_endpoint_with_its_status_codes() -> None:
    doc = committed()
    assert doc["openapi"].startswith("3.1")
    paths = doc["paths"]
    for path, methods in ENDPOINTS.items():
        assert path in paths, f"{path} missing from api/openapi.json"
        assert set(paths[path]) >= set(methods), (path, sorted(paths[path]))
        for method, codes in methods.items():
            have = set(paths[path][method]["responses"])
            assert codes <= have, f"{method.upper()} {path} must document {sorted(codes)}, has {sorted(have)}"
    assert set(paths["/jobs"]) == {"post"} or "get" not in paths["/jobs"], "no GET /jobs (the list is /queue)"
    comps = {k.lower().replace("_", "") for k in doc.get("components", {}).get("schemas", {})}
    for needed in ("health", "recipelist", "joblist", "jobcreated", "runlist", "problem"):
        assert any(needed in c for c in comps), (
            f"response schema for {needed} is not generated from the contract: {sorted(comps)}"
        )


@pytest.mark.req("FR-003-17")
def test_fr_003_17_the_committed_document_equals_the_generated_one_and_the_served_one() -> None:
    sys.path.insert(0, str(ROOT / "api"))
    sys.path.insert(0, str(ROOT / "src"))
    from asgi_client import Client
    from pitstudio_api.app import create_app

    app = create_app(port=8765)
    generated = json.loads(json.dumps(app.openapi()))
    assert generated == committed(), "api/openapi.json drifted from the application: run tools/gen_openapi.py"
    r = Client(app, 8765).get("/openapi.json")
    assert r.status == 200 and (r.header("content-type") or "").startswith("application/json") and r.json() == generated


def copy_tree(dst: Path) -> Path:
    for name in ("api", "contracts", "tools", "src"):
        shutil.copytree(
            ROOT / name,
            dst / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "node_modules"),
        )
    shutil.copy2(ROOT / "pyproject.toml", dst / "pyproject.toml")
    return dst


def gen(tree: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    tool = tree / "tools" / "gen_openapi.py"
    assert tool.is_file(), "tools/gen_openapi.py is missing"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(tree / "src"), str(tree / "api"), str(rw.SUPPORT)])}
    return subprocess.run(
        [sys.executable, str(tool), *flags], capture_output=True, text=True, cwd=str(tree), env=env, timeout=180
    )


@pytest.mark.req("FR-003-17")
def test_fr_003_17_gen_openapi_check_passes_when_clean_and_detects_a_seeded_drift(tmp_path: Path) -> None:
    tree = copy_tree(tmp_path / "tree")
    clean = gen(tree, "--check")
    assert clean.returncode == 0, clean.stdout + clean.stderr
    target = tree / "api" / "openapi.json"
    text = target.read_text(encoding="utf-8")
    target.write_text(text.replace('"title"', '"titel"', 1), encoding="utf-8")  # one-character drift
    drift = gen(tree, "--check")
    assert drift.returncode == 1, drift.stdout + drift.stderr
    assert "openapi.json" in drift.stdout + drift.stderr
    assert target.read_text(encoding="utf-8") != text, "--check never rewrites the file"
    regenerated = gen(tree)
    assert regenerated.returncode == 0, regenerated.stderr
    assert gen(tree, "--check").returncode == 0, "generating fixes the drift"
    target.unlink()
    assert gen(tree, "--check").returncode == 1, "a missing document counts as drift"
