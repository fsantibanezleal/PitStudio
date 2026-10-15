# ruff: noqa: E501, PT018
"""T-004-053: CPU-only resources, fixture build time, layer sizes.

Requirements: NFR-004-03, NFR-004-04, NFR-004-05.

Oracle: the thresholds of spec section 5 written out (no GPU: `resources.gpu: none` in the recipe and no GPU runner in the
CI job of the studio tests, on ubuntu and Windows; committed fixtures <= 1 MB in total; fixture scene build and validation
including both builds <= 120 s; each small `.usda` layer <= 10 MB = 10,000,000 bytes), read with PyYAML, `os` and
`time.perf_counter`.

Expected artefacts and API:
- `studio/recipes/**/*.yaml` declares `st10_terrain` ... `st45_validate` with `resources: {gpu: none}` (also FR-004-41).
- `.github/workflows/ci.yml` has a job that runs `pytest` for the studio environment (`uv run --project studio --frozen pytest
  ... -m "not gpu"`) with an OS matrix containing an ubuntu and a windows runner; no job of the scene tests runs on a
  runner whose label mentions a GPU (task T-004-002).
- `tests/fixtures/scene/` (task T-004-003) holds the committed fixtures, at most 1,000,000 bytes in total.
- `validate.validate_scene(...)` (test_t_004_050): the report's `layer_size_max` invariant has limit 10,000,000 and holds
  the size in bytes of the largest small `.usda` layer.
"""

from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import compose, validate  # noqa: E402

STAGES = ["st10_terrain", "st20_pit_design", "st30_assets", "st40_compose", "st45_validate"]
SMALL = ["root.usda", *(f"layers/{n}.usda" for n in ("anim", "sensors", "weather", "lights", "fleet", "design"))]


def _fixture_scene(tmp: Path, runners=None):
    spec = kit.scene_spec()
    spec["variants"]["lod"] = ["lod0", "lod1", "lod2"]
    counter = itertools.count()

    def build(out: Path):
        return compose.compose_scene(spec, kit.fixture_upstream(tmp / f"up{next(counter)}"), out)

    return validate.validate_scene(spec, build, tmp / "work", runners=runners)


@pytest.mark.req("NFR-004-03")
def test_the_recipe_declares_no_gpu_for_every_scene_stage() -> None:
    folder = ROOT / "studio" / "recipes"
    stages = {}
    for path in sorted(folder.rglob("*.yaml")) if folder.is_dir() else []:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for stage in doc.get("stages", []) if isinstance(doc, dict) else []:
            if isinstance(stage, dict) and stage.get("id") in STAGES:
                stages[stage["id"]] = stage
    assert sorted(stages) == sorted(STAGES)
    assert all(stage["resources"]["gpu"] == "none" for stage in stages.values())


@pytest.mark.req("NFR-004-03")
def test_ci_runs_the_studio_tests_on_ubuntu_and_windows_without_a_gpu() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    jobs = []
    for name, job in workflow["jobs"].items():
        runs = " ".join(str(step.get("run", "")) for step in job.get("steps", []) if isinstance(step, dict))
        if "--project studio" in runs and "pytest" in runs and "not gpu" in runs:
            jobs.append((name, job))
    assert jobs, (
        "no CI job runs the studio environment's CPU tests (uv run --project studio --frozen pytest -m 'not gpu')"
    )
    for name, job in jobs:
        matrix = job.get("strategy", {}).get("matrix", {})
        labels = [str(x).lower() for x in (matrix.get("os") or [job.get("runs-on", "")])]
        assert any("ubuntu" in x for x in labels) and any("windows" in x for x in labels), (name, labels)
        assert not any("gpu" in x or "cuda" in x for x in labels), (name, labels)
        assert "gpu" not in str(job.get("runs-on", "")).lower()


@pytest.mark.req("NFR-004-04")
def test_committed_scene_fixtures_are_at_most_one_megabyte() -> None:
    folder = ROOT / "tests" / "fixtures" / "scene"
    assert folder.is_dir(), "tests/fixtures/scene/ is missing (task T-004-003)"
    files = [p for p in folder.rglob("*") if p.is_file()]
    assert files
    assert sum(p.stat().st_size for p in files) <= 1_000_000


@pytest.mark.req("NFR-004-04")
def test_the_fixture_scene_builds_twice_and_validates_within_120_seconds(tmp_path: Path) -> None:
    t0 = time.perf_counter()
    out = _fixture_scene(tmp_path)  # real validators, both builds included
    elapsed = time.perf_counter() - t0
    assert out.report["determinism"]["identical"] is True and out.passed is True, out.report
    assert elapsed <= 120.0, f"{elapsed:.1f} s"


@pytest.mark.req("NFR-004-05")
def test_small_usda_layers_are_at_most_ten_megabytes_and_the_report_says_so(tmp_path: Path) -> None:
    out = _fixture_scene(
        tmp_path, runners={"usd-validation-nvidia": lambda r, s: [], "simready-validate": lambda r, s: []}
    )
    scene = Path(out.scene_dir)
    sizes = [(scene / rel).stat().st_size for rel in SMALL]
    assert max(sizes) <= 10_000_000
    inv = out.report["invariants"]["layer_size_max"]
    assert (inv["limit"], inv["unit"], inv["comparison"]) == (10_000_000, "bytes", "le")
    assert inv["measured"] == max(sizes) and inv["passed"] is True
