# ruff: noqa: E501
"""T-009-018 - FR-009-40, FR-009-41: honest "not run" for SDG and sensors, and `performance: local-only`.

Oracles (independent of the code under test):
- FR-009-40, hand calculation (plan 009 test strategy row): capability fixtures in the shape of
  `contracts/capabilities.schema.json` (probe ids `isaacsim` and `ovrtx`, probe status `pass` | `fail` | `skip`) and the
  expected stage statuses typed out from the spec text: Isaac Sim / Replicator not passing -> `st55_sdg` and every
  perception stage downstream of it (s10_preprocess, s30_train, s40_infer, s50_evaluate, s60_export) end "not run", no
  substitute data is created and B2 shows "not yet run"; ovrtx not passing -> the crusher family is "not run", the
  detectors are trained on the pit family only and the model cards say "crusher family not run".
- FR-009-41, hand calculation: the stage ids that carry `performance: local-only` (`st55_sdg` for SDG, `st53_sensors` for the
  sensor lane of spec 013); a throughput, timing or telemetry key in a dataset card, in B2 baked data or in the manifest of
  a local-only stage is refused; image counts, outputs and validation verdicts are allowed; the replacement text is the
  exact label of FR-000-08 and of the capability schema (`measured locally, not published (licence)`).

Expected public API (module `pitstudio_pipeline.perception.availability`, package under `pipeline/src/`):

    STAGES: tuple[str, ...]  == ("st55_sdg", "s10_preprocess", "s30_train", "s40_infer", "s50_evaluate", "s60_export")
    StageStatus              frozen dataclass: stage: str, status: "run" | "not run", reason: str ("" when run; for a
                             "not run" stage it names the probe, e.g. contains "isaacsim" or "ovrtx")
    PerceptionPlan           frozen dataclass: stages: tuple[StageStatus, ...] (in STAGES order); families: dict[str, str]
                             ({"pit": "run" | "not run", "crusher": "run" | "not run"}); train_families: tuple[str, ...];
                             substitute_data: bool (always False); b2_status: "run" | "not yet run";
                             model_card_notes: tuple[str, ...]
    plan_perception(capabilities: Mapping) -> PerceptionPlan
        `capabilities` is a capability report (probes under "probes"). A probe passes iff its entry exists and
        its "status" == "pass"; a missing probe, "fail" and "skip" do not pass.
        - isaacsim passes, ovrtx passes: every stage "run", families both "run", train_families ("pit", "crusher"),
          b2_status "run", model_card_notes ().
        - isaacsim passes, ovrtx does not: every stage "run", families {"pit": "run", "crusher": "not run"},
          train_families ("pit",), model_card_notes == ("crusher family not run",).
        - isaacsim does not pass (whatever ovrtx): every stage "not run", both families "not run", train_families (),
          b2_status "not yet run", substitute_data False, reasons name "isaacsim".
        ValueError (message contains "capabilities") if `capabilities` is not a mapping or has no "probes" mapping.
    local_only_notice() -> str                  exactly "measured locally, not published (licence)"
    LOCAL_ONLY_STAGES: frozenset[str]           contains "st55_sdg" and "st53_sensors"
    LocalOnlyViolation(ValueError)              attribute `pointer: str` (RFC 6901 pointer of the first offending key)
    assert_no_local_only_figures(document: object) -> None
        Walks dicts and lists; raises LocalOnlyViolation for the first key (case-insensitive) that names a throughput,
        rate, latency, duration, elapsed/wall time, fps, GPU-hours or telemetry figure of Isaac Sim, Replicator or ovrtx
        (the test lists the keys it checks; image counts, outputs and validation verdicts are always allowed).
    validate_stage_record(record: Mapping) -> None
        `record` is a manifest stage entry with at least "stage" and "performance". A stage in LOCAL_ONLY_STAGES whose
        `performance` is not "local-only" raises ValueError (message contains "performance"); a record with
        performance "local-only" holding such a figure raises LocalOnlyViolation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.perception import availability as av  # noqa: E402

STAGES = ("st55_sdg", "s10_preprocess", "s30_train", "s40_infer", "s50_evaluate", "s60_export")


def caps(isaac: str | None, ovrtx: str | None) -> dict:
    probes = {}
    for name, status in (("isaacsim", isaac), ("ovrtx", ovrtx)):
        if status is not None:
            probes[name] = {"status": status, "versions": {"python": "3.12.0"}}
    probes["warp_newton"] = {"status": "pass", "versions": {"python": "3.14.4"}}
    return {"generated": "2026-10-11", "gpu": "fixture gpu", "driver": "582.78", "probes": probes}


# ---------------------------------------------------------------- FR-009-40


@pytest.mark.req("FR-009-40")
def test_the_stage_list_is_the_perception_chain_in_order() -> None:
    assert tuple(av.STAGES) == STAGES


@pytest.mark.req("FR-009-40")
def test_with_both_probes_passing_every_stage_runs_and_both_families_train() -> None:
    plan = av.plan_perception(caps("pass", "pass"))
    assert [s.stage for s in plan.stages] == list(STAGES)
    assert {s.status for s in plan.stages} == {"run"}
    assert plan.families == {"pit": "run", "crusher": "run"}
    assert plan.train_families == ("pit", "crusher")
    assert plan.b2_status == "run"
    assert plan.model_card_notes == ()
    assert plan.substitute_data is False


@pytest.mark.req("FR-009-40")
@pytest.mark.parametrize("ovrtx", ["fail", "skip", None])
def test_without_ovrtx_the_crusher_family_is_not_run_and_the_detectors_train_on_the_pit_family(
    ovrtx: str | None,
) -> None:
    plan = av.plan_perception(caps("pass", ovrtx))
    assert {s.status for s in plan.stages} == {"run"}
    assert plan.families == {"pit": "run", "crusher": "not run"}
    assert plan.train_families == ("pit",)
    assert plan.model_card_notes == ("crusher family not run",)
    assert plan.b2_status == "run"
    assert plan.substitute_data is False


@pytest.mark.req("FR-009-40")
@pytest.mark.parametrize("isaac", ["fail", "skip", None])
@pytest.mark.parametrize("ovrtx", ["pass", "fail", None])
def test_without_isaac_sim_every_stage_from_st55_sdg_on_ends_not_run_with_no_substitute_data(
    isaac: str | None, ovrtx: str | None
) -> None:
    plan = av.plan_perception(caps(isaac, ovrtx))
    assert [s.stage for s in plan.stages] == list(STAGES)
    assert {s.status for s in plan.stages} == {"not run"}
    assert all("isaacsim" in s.reason for s in plan.stages)
    assert plan.families == {"pit": "not run", "crusher": "not run"}
    assert plan.train_families == ()
    assert plan.b2_status == "not yet run"
    assert plan.substitute_data is False


@pytest.mark.req("FR-009-40")
@pytest.mark.parametrize("bad", [None, [], "caps", 3, {}, {"probes": []}, {"probes": None}])
def test_a_report_that_is_not_a_capability_report_is_rejected(bad: object) -> None:
    with pytest.raises(ValueError, match="capabilities"):
        av.plan_perception(bad)  # type: ignore[arg-type]


@pytest.mark.req("FR-009-40")
def test_a_probe_without_a_status_does_not_pass() -> None:
    c = caps("pass", "pass")
    del c["probes"]["isaacsim"]["status"]
    plan = av.plan_perception(c)
    assert {s.status for s in plan.stages} == {"not run"}


# ---------------------------------------------------------------- FR-009-41


@pytest.mark.req("FR-009-41")
def test_the_notice_is_the_exact_licence_label() -> None:
    assert av.local_only_notice() == "measured locally, not published (licence)"


@pytest.mark.req("FR-009-41")
def test_the_sdg_and_sensor_stages_are_local_only_stages() -> None:
    assert {"st55_sdg", "st53_sensors"} <= set(av.LOCAL_ONLY_STAGES)
    assert "s30_train" not in av.LOCAL_ONLY_STAGES


@pytest.mark.req("FR-009-41")
def test_a_card_with_counts_outputs_and_verdicts_is_accepted() -> None:
    card = {
        "image_counts": {"pit": {"structured": 10000, "unstructured": 10000}, "crusher": {"structured": 10000}},
        "split_counts": {"train": 8000, "validation": 1000, "test": 1000},
        "outputs": ["rgb", "semantic", "depth", "coco_instances", "frame_state"],
        "validation": {"verdict": "pass", "valid_images": 9876},
        "sim_to_real": "not measured",
    }
    assert av.assert_no_local_only_figures(card) is None
    assert av.assert_no_local_only_figures([card, {"note": av.local_only_notice()}]) is None


@pytest.mark.req("FR-009-41")
@pytest.mark.parametrize(
    "key",
    [
        "throughput_images_per_s",
        "images_per_second",
        "render_time_s",
        "replicator_fps",
        "FPS",
        "ovrtx_latency_ms",
        "elapsed_s",
        "wall_time_s",
        "duration_s",
        "gpu_hours",
        "telemetry",
    ],
)
def test_a_throughput_timing_or_telemetry_key_is_refused_at_any_depth(key: str) -> None:
    card = {"image_counts": {"pit": 10}, "sdg": {"stats": [{"ok": 1}, {key: 12.5}]}}
    with pytest.raises(av.LocalOnlyViolation) as exc:
        av.assert_no_local_only_figures(card)
    assert exc.value.pointer == f"/sdg/stats/1/{key}"
    assert isinstance(exc.value, ValueError)


@pytest.mark.req("FR-009-41")
def test_a_local_only_stage_must_carry_the_marker() -> None:
    for stage in ("st55_sdg", "st53_sensors"):
        assert av.validate_stage_record({"stage": stage, "performance": "local-only", "outputs": ["rgb"]}) is None
        for bad in ("published", None, "", "Local-Only"):
            with pytest.raises(ValueError, match="performance"):
                av.validate_stage_record({"stage": stage, "performance": bad})
        with pytest.raises(ValueError, match="performance"):
            av.validate_stage_record({"stage": stage})


@pytest.mark.req("FR-009-41")
def test_a_timing_field_on_a_local_only_stage_is_refused() -> None:
    rec = {"stage": "st55_sdg", "performance": "local-only", "outputs": ["rgb"], "timing": {"render_time_s": 41.0}}
    with pytest.raises(av.LocalOnlyViolation) as exc:
        av.validate_stage_record(rec)
    assert exc.value.pointer.startswith("/timing")
    rec2 = {"stage": "st53_sensors", "performance": "local-only", "throughput_frames_per_s": 30.0}
    with pytest.raises(av.LocalOnlyViolation):
        av.validate_stage_record(rec2)


@pytest.mark.req("FR-009-41")
def test_a_stage_that_is_not_local_only_is_not_subject_to_the_marker_rule() -> None:
    assert av.validate_stage_record({"stage": "s30_train", "performance": "published", "gpu_hours": 3.2}) is None
