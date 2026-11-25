# ruff: noqa: E501, PT018
"""T-002-012: CI planning of every recipe on a CPU-only Linux runner (US-002-1).

Requirements: FR-002-05, FR-002-07, SC-002-01, DC-002-05.

Expected product facts:
  * `tools/plan_all_recipes.py --profile <id>` (run as `python tools/plan_all_recipes.py ...`; the repository is
    PITSTUDIO_REPO or the checkout) runs `studio plan --json` (in process or as a subprocess) for every
    `studio/recipes/cases/*.yaml` and `studio/recipes/_bench/*.yaml`, with the fake device
    `tests/fixtures/fake_gpu/linux-1x48gib.yaml` selected as the GPU backend (it sets PITSTUDIO_GPU_BACKEND itself);
    it exits 0 when every plan exits 0 and no plan leaks (FR-002-04 patterns plus this process's host, user and home),
    and exits 1 otherwise, printing the recipe file name of every failure; it prints the name of every recipe it planned;
    stages the profile does not enable are `env-disabled`, never errors;
  * `.github/workflows/ci.yml` has the jobs `runner-plan` (ubuntu, runs the tool with `--profile linux-gpu`),
    `runner-container` (ubuntu, builds `studio/containers/Dockerfile.open`, runs `not gpu` runner and contract tests in it)
    and `runner-windows` (windows runner, runs the runner tests);
  * `studio/containers/Dockerfile.open`: base image pinned by SHA-256 (`@sha256:<64 hex>`), uv from its pinned image,
    `uv sync --locked`.
Oracles: hand-built fixture repositories with known verdicts; the process's identity strings as leak references.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
import schemas
from runner_world import recipe, stage, up

ROOT = rw.ROOT
TOOL = ROOT / "tools" / "plan_all_recipes.py"
DEVICE = ROOT / "tests" / "fixtures" / "fake_gpu" / "linux-1x48gib.yaml"


def linux_profile(**over: Any) -> dict[str, Any]:
    return rw.profile_doc(
        id="linux-gpu",
        os="linux",
        process_control="process-group",
        store_default="/srv/ps",
        keep_awake=False,
        envs_enabled=["studio", "pipeline", "accel", "external"],
        **over,
    )


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path, profile=linux_profile())
    monkeypatch.delenv("PITSTUDIO_GPU_BACKEND", raising=False)  # the tool must select the fake device itself
    w.write_recipe(
        recipe(
            "case-a",
            [
                stage("s10_preprocess"),
                stage("st50_physics", gpu="exclusive", vram=40.0, inputs=[up("s10_preprocess", "out.bin")]),
            ],
        ),
        "cases",
    )
    w.write_recipe(recipe("case-b", [stage("st10_terrain")]), "cases")
    w.write_recipe(recipe("bench-c", [stage("s64_bench", env="accel")]), "_bench")
    yield w
    rw.cleanup_world(w)


def run_tool(w: rw.World, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    assert TOOL.is_file(), "tools/plan_all_recipes.py is missing"
    e = w.env()
    e.pop("PITSTUDIO_GPU_BACKEND", None)
    e.update(env or {})
    return subprocess.run(
        [sys.executable, str(TOOL), *args], capture_output=True, text=True, env=e, cwd=str(w.base), timeout=300
    )


@pytest.mark.req("FR-002-05")
@pytest.mark.req("SC-002-01")
def test_fr_002_05_tool_plans_every_recipe_of_cases_and_bench_and_exits_0(world) -> None:
    (world.repo / "studio" / "recipes" / "cases" / "README.md").write_text("not a recipe\n", encoding="utf-8")
    r = run_tool(world, "--profile", "linux-gpu")
    assert r.returncode == 0, r.stdout + r.stderr
    for name in ("case-a", "case-b", "bench-c"):
        assert name in r.stdout, f"{name} not planned: {r.stdout}"
    assert "README" not in r.stdout and "linux-gpu.yaml" not in r.stdout


@pytest.mark.req("FR-002-05")
def test_fr_002_05_a_recipe_that_does_not_plan_fails_the_job_and_is_named(world) -> None:
    world.write_recipe(
        recipe(
            "broken-cycle",
            [
                stage("s05_synthesize", inputs=[up("s10_preprocess", "out.bin")]),
                stage("s10_preprocess", inputs=[up("s05_synthesize", "out.bin")]),
            ],
        ),
        "cases",
    )
    r = run_tool(world, "--profile", "linux-gpu")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "broken-cycle" in r.stdout + r.stderr
    for name in ("case-a", "case-b", "bench-c"):
        assert name in r.stdout, "the other recipes are still planned and reported"


@pytest.mark.req("FR-002-05")
def test_fr_002_05_stages_of_disabled_environments_are_not_errors(world) -> None:
    world.write_recipe(
        recipe("needs-isaac", [stage("s10_preprocess"), stage("st52_rtx_render", gpu="exclusive", vram=2.0)]), "cases"
    )
    r = run_tool(world, "--profile", "linux-gpu")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "needs-isaac" in r.stdout


@pytest.mark.req("FR-002-05")
@pytest.mark.req("FR-002-04")
def test_fr_002_05_a_leaking_plan_fails_the_job(world) -> None:
    # `getpass.getuser()` reads these variables first: a recipe whose id equals the user name leaks that name
    world.write_recipe(recipe("pitleakuser", [stage("s10_preprocess")]), "cases")
    r = run_tool(
        world,
        "--profile",
        "linux-gpu",
        env={"LOGNAME": "pitleakuser", "USER": "pitleakuser", "USERNAME": "pitleakuser", "LNAME": "pitleakuser"},
    )
    assert r.returncode == 1, r.stdout + r.stderr
    assert "pitleakuser" in r.stdout + r.stderr


@pytest.mark.req("FR-002-05")
def test_fr_002_05_the_tool_selects_the_committed_fake_device_itself(world) -> None:
    # observable only through the tool's wiring: it must name the fixture and use the runner's `--gpu-backend fake:<file>`
    # or PITSTUDIO_GPU_BACKEND; the run with the variable unset (see run_tool) must still succeed
    assert TOOL.is_file(), "tools/plan_all_recipes.py is missing"
    doc = yaml.safe_load(DEVICE.read_text(encoding="utf-8"))  # the committed fake device is itself valid and 48 GiB
    assert schemas.errors("profile", doc, "#/$defs/fake_device") == []
    assert doc["vram_total_bytes"] == 48 * 2**30 and doc["init_error"] is False
    src = TOOL.read_text(encoding="utf-8")
    assert "linux-1x48gib.yaml" in src
    assert "fake:" in src
    r = run_tool(world, "--profile", "linux-gpu")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.req("FR-002-05")
def test_fr_002_05_unknown_profile_is_a_usage_error(world) -> None:
    r = run_tool(world, "--profile", "no-such-profile")
    assert r.returncode in (1, 2)
    assert r.returncode != 0


@pytest.mark.req("SC-002-01")
def test_sc_002_01_every_committed_recipe_plans_with_linux_gpu_on_the_real_repository() -> None:
    env = {**__import__("os").environ, "PYTHONPATH": str(rw.SRC), "PITSTUDIO_GPU_BACKEND": ""}
    env.pop("PITSTUDIO_REPO", None)
    assert TOOL.is_file(), "tools/plan_all_recipes.py is missing"
    r = subprocess.run(
        [sys.executable, str(TOOL), "--profile", "linux-gpu"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        timeout=600,
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---- CI workflow and container (FR-002-05, FR-002-07) --------------------------------------------------------------
def _ci() -> dict[str, Any]:
    return yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))


@pytest.mark.req("FR-002-05")
def test_fr_002_05_ci_has_the_runner_plan_job() -> None:
    job = _ci()["jobs"]["runner-plan"]
    assert str(job["runs-on"]).startswith("ubuntu")
    text = json.dumps(job)
    assert "plan_all_recipes.py" in text and "--profile linux-gpu" in text


@pytest.mark.req("FR-002-07")
def test_fr_002_07_ci_has_the_runner_container_job_and_the_dockerfile_is_pinned() -> None:
    job = _ci()["jobs"]["runner-container"]
    assert str(job["runs-on"]).startswith("ubuntu")
    text = json.dumps(job)
    assert "docker build" in text and "studio/containers/Dockerfile.open" in text
    assert "not gpu" in text
    df = (ROOT / "studio" / "containers" / "Dockerfile.open").read_text(encoding="utf-8")
    froms = [ln for ln in df.splitlines() if re.match(r"\s*FROM\s", ln, re.I)]
    assert froms and all(re.search(r"@sha256:[0-9a-f]{64}", ln) for ln in froms), froms
    assert "uv sync --locked" in df
    assert re.search(r"COPY\s+--from=\S*uv\S*", df), "uv comes from its own pinned image (uv's container pattern)"
