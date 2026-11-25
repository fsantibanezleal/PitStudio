"""T-011-095 - FR-011-49: fixture propagation through the surrogate stages.

Oracles (independent of the code under test; plan 011 test strategy FR-011-49: "a fixture rollout set gives a
    report `fixture: true` and the publish
step drops it"): hand calculation from the spec text. A dataset manifest with `fixture: true` (the contract-fixture
    flag of FR-000-23) must make
`s30_train`, `s40_infer` and `s50_evaluate` run to completion, write `fixture: true` on every checkpoint, rollout
    and report, and publish no repose,
run-out or relative-L2 result; a manifest without the flag leaves the artefacts unflagged and publishable. The
    fixtures are the tiny trainings and the
analytic piles of tests/_surrogate_fixtures.py.

Expected public API (package under `pipeline/src/`):

  module `pitstudio_pipeline.surrogates.fixture`
    is_fixture(dataset_manifest) -> bool          True iff manifest["fixture"] is True; absent -> False; any other
        value (a string, a number) -> ValueError
    stamp(artefact, dataset_manifest) -> dict     a shallow copy of `artefact` with "fixture": True when the
        dataset is a fixture; an unflagged dataset
                                                  leaves `fixture` absent or False
    publishable(report) -> dict | None            None for a report whose "fixture" is True (the publish step drops
        it), else the report itself
  stage entry points (extended by the optional keyword `dataset_manifest`, default None = not a fixture):
    pitstudio_pipeline.surrogates.gns.train.train_gns(splits, config, *, seed, dataset_manifest=None)
        -> TrainResult whose checkpoint["fixture"] and log["fixture"] are True for a fixture
    pitstudio_pipeline.surrogates.gns.evaluate.evaluate_held_out(geometries, surrogate, *, expected=None,
        dataset_manifest=None)
        -> report["fixture"] True for a fixture (the numbers are still computed, for development builds)
    pitstudio_pipeline.surrogates.fno.evaluate.evaluate_fno(preds, truths, field_names, *, model,
        dataset_manifest=None, ...)
        -> report["fixture"] True for a fixture
    pitstudio_pipeline.surrogates.gns.infer.stamp_rollout(rollout_record, dataset_manifest) -> dict    the
        s40_infer record with the flag
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))
sys.path.insert(0, str(ROOT / "tests"))

torch = pytest.importorskip("torch")

import _surrogate_fixtures as fx  # noqa: E402
from pitstudio_pipeline.surrogates.fixture import is_fixture, publishable, stamp  # noqa: E402
from pitstudio_pipeline.surrogates.fno import evaluate as fno_evaluate  # noqa: E402
from pitstudio_pipeline.surrogates.gns import evaluate as gns_evaluate  # noqa: E402
from pitstudio_pipeline.surrogates.gns import infer, train  # noqa: E402

FIXTURE = {"id": "rollouts-fixture", "fixture": True}
REAL = {"id": "rollouts-real", "fixture": False}
ABSENT = {"id": "rollouts-no-flag"}


# ------------------------------------------------------------------ the helpers


@pytest.mark.req("FR-011-49")
@pytest.mark.parametrize(("manifest", "expected"), [(FIXTURE, True), (REAL, False), (ABSENT, False), ({}, False)])
def test_the_fixture_flag_is_read_from_the_dataset_manifest(manifest: dict, expected: bool) -> None:
    assert is_fixture(manifest) is expected


@pytest.mark.req("FR-011-49")
@pytest.mark.parametrize("flag", ["true", "yes", 1, 0, None, [], "fixture"])
def test_a_flag_that_is_not_a_boolean_is_refused_not_coerced(flag) -> None:
    with pytest.raises(ValueError, match="fixture"):
        is_fixture({"fixture": flag})


@pytest.mark.req("FR-011-49")
def test_stamp_flags_fixture_artefacts_and_leaves_the_others_alone() -> None:
    artefact = {"kind": "checkpoint", "epoch": 3}
    flagged = stamp(artefact, FIXTURE)
    assert flagged["fixture"] is True
    assert flagged["epoch"] == 3
    assert "fixture" not in artefact  # the argument is not mutated
    assert stamp(artefact, REAL).get("fixture", False) is False
    assert stamp(artefact, ABSENT).get("fixture", False) is False


@pytest.mark.req("FR-011-49")
def test_the_publish_step_drops_fixture_reports_and_keeps_the_others() -> None:
    fixture_report = {"fixture": True, "sc_011_01": "pass", "geometries": []}
    real_report = {"fixture": False, "sc_011_01": "pass", "geometries": []}
    unflagged = {"sc_011_01": "pass"}
    assert publishable(fixture_report) is None
    assert publishable(real_report) is real_report
    assert publishable(unflagged) is unflagged


# ------------------------------------------------------------------ GNS training


@pytest.mark.req("FR-011-49")
def test_gns_training_runs_on_a_fixture_and_flags_the_checkpoint_and_the_log() -> None:
    res = train.train_gns(fx.tiny_splits(), dict(fx.TRAIN_CONFIG), seed=0, dataset_manifest=FIXTURE)
    assert res.checkpoint["fixture"] is True
    assert res.log["fixture"] is True
    assert res.checkpoint["epoch"] >= 1  # it ran
    assert len(res.log["epochs"]) == fx.TRAIN_CONFIG["epochs"]


@pytest.mark.req("FR-011-49")
@pytest.mark.parametrize("manifest", [REAL, ABSENT, None])
def test_gns_training_on_real_data_is_not_flagged(manifest) -> None:
    res = train.train_gns(fx.tiny_splits(), dict(fx.TRAIN_CONFIG), seed=0, dataset_manifest=manifest)
    assert res.checkpoint.get("fixture", False) is False
    assert res.log.get("fixture", False) is False


# ------------------------------------------------------------------ s40_infer


@pytest.mark.req("FR-011-49")
def test_rollout_records_of_a_fixture_are_flagged() -> None:
    record = {"geometry_id": "g001", "seed": 1, "steps": 3}
    assert infer.stamp_rollout(record, FIXTURE)["fixture"] is True
    assert infer.stamp_rollout(record, REAL).get("fixture", False) is False


# ------------------------------------------------------------------ s50_evaluate


@pytest.mark.req("FR-011-49")
def test_gns_evaluation_runs_on_a_fixture_set_flags_the_report_and_publishes_nothing() -> None:
    geoms = [fx.collapse_geometry("col-00")]
    report = gns_evaluate.evaluate_held_out(geoms, fx.identity_surrogate(geoms), dataset_manifest=FIXTURE)
    assert report["fixture"] is True
    assert report["n_geometries"] == 1  # it ran
    assert publishable(report) is None


@pytest.mark.req("FR-011-49")
def test_gns_evaluation_of_real_rollouts_is_not_flagged_and_stays_publishable() -> None:
    geoms = [fx.collapse_geometry("col-00")]
    report = gns_evaluate.evaluate_held_out(geoms, fx.identity_surrogate(geoms), dataset_manifest=REAL)
    assert report.get("fixture", False) is False
    assert publishable(report) is report
    plain = gns_evaluate.evaluate_held_out(geoms, fx.identity_surrogate(geoms))
    assert plain.get("fixture", False) is False


@pytest.mark.req("FR-011-49")
def test_fno_evaluation_runs_on_a_fixture_dataset_flags_the_report_and_publishes_nothing() -> None:
    pred, truth = fx.tailings_set(4)
    report = fno_evaluate.evaluate_fno(pred, truth, fx.TAILINGS_FIELDS, model="tailings", dataset_manifest=FIXTURE)
    assert report["fixture"] is True
    assert report["fields"]["depth_max"]["mean"] == pytest.approx(0.01, rel=1e-9)  # it ran
    assert publishable(report) is None


@pytest.mark.req("FR-011-49")
def test_fno_evaluation_of_real_fields_is_not_flagged() -> None:
    pred, truth = fx.tailings_set(4)
    report = fno_evaluate.evaluate_fno(pred, truth, fx.TAILINGS_FIELDS, model="tailings", dataset_manifest=REAL)
    assert report.get("fixture", False) is False
    assert publishable(report) is report


@pytest.mark.req("FR-011-49")
def test_a_non_boolean_fixture_flag_stops_the_stages_before_any_work() -> None:
    bad = {"fixture": "true"}
    with pytest.raises(ValueError, match="fixture"):
        train.train_gns(fx.tiny_splits(), dict(fx.TRAIN_CONFIG), seed=0, dataset_manifest=bad)
    geoms = [fx.collapse_geometry("col-00")]
    with pytest.raises(ValueError, match="fixture"):
        gns_evaluate.evaluate_held_out(geoms, fx.identity_surrogate(geoms), dataset_manifest=bad)
    pred, truth = fx.tailings_set(2)
    with pytest.raises(ValueError, match="fixture"):
        fno_evaluate.evaluate_fno(pred, truth, fx.TAILINGS_FIELDS, model="tailings", dataset_manifest=bad)
