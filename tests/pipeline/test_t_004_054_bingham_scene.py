# ruff: noqa: E501, PT018
"""T-004-054: Bingham scene acceptance on the published run (data-and-models phase).

Requirements: NFR-004-01, NFR-004-02, SC-004-01.

Oracle: the thresholds of spec section 5 (st10_terrain wall time <= 40 min = 2,400 s; the default Bingham scene passes every
invariant of FR-004-35, has validation status `complete` and two identical builds), read from the published run's committed
artefacts (`web/public/assets/runs/<run_id>/manifest.json`, schema DC-001-01, and the validation report DC-004-07 that the
run publishes), never from running the stages here.

Expected artefacts (the data-and-models phase): at least one published run
`web/public/assets/runs/<run_id>/manifest.json` with the five scene stages `st10_terrain` ... `st45_validate`, each
`status: succeeded`, `determinism` bitwise; `st10_terrain` with `wall_s` <= 2400; and the run's `st45_validate` report
published as `scene-validation-report.json` somewhere under `web/public/assets/runs/<run_id>/` (spec 004 does not say where:
see the review notes), with `status: complete`, `passed: true`, every invariant `passed`, `determinism.identical: true` and the
validated variant selections covering all three `lod` variants. The spec names no field for the peak resident memory of a
stage (NFR-004-02: <= 8 GB, "runner process telemetry"): the manifest and the published telemetry schemas carry GPU memory
only, so that threshold has no committed artefact to read and is not asserted here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "web" / "public" / "assets" / "runs"
STAGES = ["st10_terrain", "st20_pit_design", "st30_assets", "st40_compose", "st45_validate"]


def _scene_runs() -> list[tuple[Path, dict]]:
    found = []
    for manifest_path in sorted(RUNS.glob("*/manifest.json")) if RUNS.is_dir() else []:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ids = {s.get("key", {}).get("id") for s in manifest.get("stages", []) if isinstance(s, dict)}
        if "st45_validate" in ids:
            found.append((manifest_path.parent, manifest))
    return found


def _stage(manifest: dict, stage_id: str) -> dict:
    return next(s for s in manifest["stages"] if s["key"]["id"] == stage_id)


@pytest.mark.slow
@pytest.mark.req("SC-004-01")
def test_a_published_run_built_and_validated_the_default_bingham_scene() -> None:
    runs = _scene_runs()
    assert runs, "no published run contains the scene stages (web/public/assets/runs/*/manifest.json)"
    run_dir, manifest = runs[-1]
    for stage_id in STAGES:
        stage = _stage(manifest, stage_id)
        assert stage["status"] == "succeeded", stage_id
        assert stage["determinism"]["class"] == "bitwise", stage_id
    reports = sorted(run_dir.rglob("scene-validation-report.json"))
    assert reports, "the run publishes no scene-validation-report.json"
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert report["status"] == "complete" and report["passed"] is True
    assert all(inv["passed"] is True for inv in report["invariants"].values())
    assert report["determinism"]["identical"] is True and all(
        layer["equal"] for layer in report["determinism"]["layers"]
    )
    assert {s["lod"] for s in report["selections"]} == {"lod0", "lod1", "lod2"}
    assert all(v["status"] == "ran" for v in report["validators"])


@pytest.mark.slow
@pytest.mark.req("NFR-004-01")
def test_the_bingham_terrain_stage_ran_within_forty_minutes() -> None:
    runs = _scene_runs()
    assert runs, "no published run contains the scene stages (web/public/assets/runs/*/manifest.json)"
    stage = _stage(runs[-1][1], "st10_terrain")
    assert 0 < stage["wall_s"] <= 2400, stage["wall_s"]
