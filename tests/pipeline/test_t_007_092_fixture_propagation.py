# ruff: noqa: E501, PT018
"""T-007-092: fixture propagation through the dispatch stages: a contract-fixture input is run, never refused, and every trace, KPI table, checkpoint and report it produces says `fixture: true`; no dispatch comparison is published from it.

Requirements: FR-007-46, FR-000-23.

Spec: specs/007-haulage-dispatch/spec.md FR-007-46 (while a scenario bundle, trace or policy that the dispatch stages read is a contract fixture, the twin, the KPI layer, `s30_train` and `s50_evaluate` run against it, write `fixture: true` on every trace, KPI table, checkpoint and report, and
publish no dispatch comparison computed from it) and spec 000 FR-000-23 (a contract fixture is `fixture: true`; the product never presents it as a result).

Oracle: the spec's own contract examples (`haul-scenario.valid.json`, `des-trace.valid.json`, `dispatch-eval.valid.json`, the policy fixture of T-007-057) with and without the marker; the JSON schema validators of the contracts; plain checks that a non-fixture run carries no marker (so a real result is never mislabelled).

Marker convention (stated here: the contract schemas of spec 007 have `additionalProperties: false` and no `fixture` property, so FR-007-46 needs them extended, a spec 001 change request listed in the report): an input is a fixture when its document has the boolean `fixture: true`:
    a bundle: top-level `fixture`; a trace: `header.fixture`; a policy manifest (`policy-io.json`): top-level `fixture`; every output that this module's stages write carries the marker iff an input did: a KPI table top-level `fixture`, a train manifest and every checkpoint `fixture`, a fidelity report `fixture`,
    an evaluation table top-level `fixture`. The marker is absent (or false) otherwise. A non-boolean `fixture` value is rejected by the schemas.

Expected API (modules as in the earlier tasks of this spec):
    contracts: `haul-scenario` (top-level `fixture`), `des-trace` (`header.fixture`), `dispatch-eval` (top-level `fixture`), `dispatch-policy-io` (top-level `fixture`) accept an optional boolean `fixture` and reject any other type.
    adapter.run_shift(bundle_path, ...) -> RunResult: `trace["header"]["fixture"] is True` when the bundle has `fixture: true`; the trace validates against the extended schema; nothing is refused.
    kpi.compute_kpis(trace, ...) -> dict: top-level `fixture` is True iff `trace["header"]["fixture"]` is True.
    dispatch.fidelity.fidelity_report(bundle, ...) -> dict: `report["fixture"]` is True iff `bundle["fixture"]` is True.
    dispatch.train.train(config, ...) -> TrainResult: `manifest["fixture"]` and every checkpoint's `fixture` follow `config.bundle["fixture"]` (see test_t_007_053).
    dispatch.export.PolicyDispatcher(onnx_path, io_path).fixture -> bool: the manifest's marker.
    dispatch.evaluate.publish_table(table: dict, *, fixture: bool = False) -> dict: a deep copy; with `fixture=True` the copy has `fixture: True` and `comparisons == []` (no verdict, no interval is published); with False the table is returned unchanged (equal) and carries no marker.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_busy as busy
import p007_env as hand
import p007_kit as kit
from pitstudio_pipeline.dispatch.evaluate import publish_table
from pitstudio_pipeline.dispatch.export import PolicyDispatcher
from pitstudio_pipeline.dispatch.fidelity import fidelity_report
from pitstudio_pipeline.dispatch.train import TrainConfig, train
from pitstudio_pipeline.haulage.adapter import run_shift
from pitstudio_pipeline.haulage.kpi import compute_kpis

FIX = kit.ROOT / "tests" / "fixtures" / "haulage" / "policy"


def with_marker(doc: dict, where: str, value=True) -> dict:
    d = copy.deepcopy(doc)
    (d["header"] if where == "header" else d)["fixture"] = value
    return d


# ---------------------------------------------------------------------------------------------------------------------
# the contracts can carry the marker
# ---------------------------------------------------------------------------------------------------------------------
CONTRACTS = [
    ("haul-scenario", "haul-scenario.valid.json", "top"),
    ("des-trace", "des-trace.valid.json", "header"),
    ("dispatch-eval", "dispatch-eval.valid.json", "top"),
    ("dispatch-policy-io", "dispatch-policy-io.valid.json", "top"),
]


@pytest.mark.req("FR-007-46")
@pytest.mark.parametrize(("stem", "example", "where"), CONTRACTS, ids=[c[0] for c in CONTRACTS])
def test_the_contract_accepts_a_boolean_fixture_marker_and_rejects_any_other_type(stem, example, where):
    v = kit.schema_validator(stem)
    base = kit.example(example)
    assert not list(v.iter_errors(base))
    for ok in (True, False):
        errs = list(v.iter_errors(with_marker(base, where, ok)))
        assert not errs, [e.message for e in errs][:3]
    for bad in ("yes", 1, 0, None, [True], {"fixture": True}, "true"):
        assert list(v.iter_errors(with_marker(base, where, bad))), bad


# ---------------------------------------------------------------------------------------------------------------------
# the twin (reference adapter) and the KPI layer
# ---------------------------------------------------------------------------------------------------------------------
def run(tmp_path, fixture: bool | None):
    b = busy.busy_bundle("sptf", "fast", n_trucks=4, horizon=1800.0)
    if fixture is not None:
        b["fixture"] = fixture
    return run_shift(kit.write_bundle(tmp_path, b), seed=3)


@pytest.mark.req("FR-007-46")
def test_a_fixture_bundle_is_run_and_its_trace_header_says_fixture_true(tmp_path):
    res = run(tmp_path, True)
    assert res.trace["header"]["fixture"] is True
    assert res.events_executed > 0 and res.trace["results"]["tonnes_t"] > 0  # it ran: nothing was refused or emptied
    assert not list(kit.schema_validator("des-trace").iter_errors(res.trace))


@pytest.mark.req("FR-007-46")
@pytest.mark.parametrize("flag", [None, False])
def test_a_real_bundle_is_never_labelled_a_fixture(tmp_path, flag):
    res = run(tmp_path, flag)
    assert res.trace["header"].get("fixture", False) is False
    assert res.kpis.get("fixture", False) is False


@pytest.mark.req("FR-007-46")
def test_the_kpi_table_of_a_fixture_trace_says_fixture_true_and_a_real_one_does_not(tmp_path):
    fixture_dir, real_dir = tmp_path / "f", tmp_path / "r"
    fixture_dir.mkdir()
    real_dir.mkdir()
    fixture_run, real_run = run(fixture_dir, True), run(real_dir, None)
    fleet = [{"id": i + 1, "truck_class": "CAT_793F"} for i in range(4)]
    loaders = [{"node": ld["node"], "n_spots": ld["n_spots"]} for ld in kit.smoke_bundle()["loaders"]]
    cycle = {"CAT_793F": 900.0}
    k_fixture = compute_kpis(fixture_run.trace, fleet=fleet, loaders=loaders, free_flow_cycle_s=cycle)
    k_real = compute_kpis(real_run.trace, fleet=fleet, loaders=loaders, free_flow_cycle_s=cycle)
    assert k_fixture["fixture"] is True
    assert k_real.get("fixture", False) is False
    assert fixture_run.kpis["fixture"] is True  # the adapter's own KPIs agree


@pytest.mark.req("FR-007-46")
def test_a_trace_marker_that_is_not_a_boolean_is_not_trusted(tmp_path):
    res = run(tmp_path, None)
    for bad in ("yes", 1, "true"):
        t = copy.deepcopy(res.trace)
        t["header"]["fixture"] = bad
        with pytest.raises(Exception) as ei:  # noqa: PT011
            compute_kpis(
                t,
                fleet=[{"id": 1, "truck_class": "CAT_793F"}],
                loaders=[{"node": 1, "n_spots": 1}],
                free_flow_cycle_s={"CAT_793F": 900.0},
            )
        assert type(ei.value).__name__ == "InvalidTrace"  # the trace fails its schema (the KPI layer validates first)


# ---------------------------------------------------------------------------------------------------------------------
# training, fidelity, policy
# ---------------------------------------------------------------------------------------------------------------------
class Backend:
    device = "cpu"

    def lock(self):
        import contextlib

        return contextlib.nullcontext()

    def check(self, iteration, batch):
        return None


def small_config(fixture: bool | None, **kw):
    bundle = hand.family_bundle(3, horizon_s=1800.0)
    if fixture is not None:
        bundle["fixture"] = fixture
    return TrainConfig(
        arch="m4",
        bundle=bundle,
        iterations=2,
        block_iters=1,
        batch=4,
        decisions_per_iter=4,
        seed=1,
        seed_pool=list(range(100, 120)),
        **kw,
    )


@pytest.mark.req("FR-007-46")
def test_training_on_a_fixture_marks_the_manifest_and_every_checkpoint_and_still_trains(tmp_path):
    r = train(small_config(True), out_dir=tmp_path, backend=Backend())
    assert r.manifest["fixture"] is True and r.blocks_done == 2 and len(r.metrics) == 2
    ckpts = sorted((tmp_path / "checkpoints").glob("*.pt"))
    assert len(ckpts) == 2
    assert all(torch.load(c, weights_only=False)["fixture"] is True for c in ckpts)
    assert json.loads((tmp_path / "train-manifest.json").read_text(encoding="utf-8"))["fixture"] is True


@pytest.mark.req("FR-007-46")
@pytest.mark.parametrize("flag", [None, False])
def test_training_on_real_inputs_carries_no_fixture_marker(tmp_path, flag):
    r = train(small_config(flag), out_dir=tmp_path, backend=Backend())
    assert r.manifest["fixture"] is False
    assert all(torch.load(c, weights_only=False)["fixture"] is False for c in (tmp_path / "checkpoints").glob("*.pt"))


@pytest.mark.req("FR-007-46")
def test_the_environment_fidelity_report_of_a_fixture_bundle_says_fixture_true():
    seeds = list(range(700, 730))
    b = busy.busy_bundle("fixed", "fast", n_trucks=4, horizon=3600.0)
    b["fixture"] = True
    rep = fidelity_report(b, seeds=seeds, des_runner=lambda *a: 1000.0)
    assert rep["fixture"] is True and set(rep["fast"]) == {"fixed", "nearest", "sptf", "sq"}  # the gate still runs
    b2 = busy.busy_bundle("fixed", "fast", n_trucks=4, horizon=3600.0)
    assert fidelity_report(b2, seeds=seeds, des_runner=lambda *a: 1000.0).get("fixture", False) is False


@pytest.mark.req("FR-007-46")
@pytest.mark.parametrize(("marker", "want"), [(True, True), (False, False), (None, False)])
def test_a_policy_fixture_is_recognised_by_the_dispatcher(tmp_path, marker, want):
    io = json.loads((FIX / "ppo" / "policy-io.json").read_text(encoding="utf-8"))
    if marker is not None:
        io["fixture"] = marker
    (tmp_path / "policy.onnx").write_bytes((FIX / "ppo" / "policy.onnx").read_bytes())
    (tmp_path / "policy-io.json").write_text(json.dumps(io), encoding="utf-8")
    assert PolicyDispatcher(tmp_path / "policy.onnx", tmp_path / "policy-io.json").fixture is want


# ---------------------------------------------------------------------------------------------------------------------
# the evaluation table: no comparison from a fixture
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-46")
def test_a_fixture_evaluation_publishes_no_comparison_and_says_fixture_true():
    table = kit.example("dispatch-eval.valid.json")
    assert table["comparisons"] and table["comparisons"][0]["verdict"] == "learned-better"
    out = publish_table(table, fixture=True)
    assert out["fixture"] is True and out["comparisons"] == []
    assert (
        "learned-better" not in json.dumps(out)
        and "baseline-better" not in json.dumps(out)
        and "no-significant-difference" not in json.dumps(out)
    )
    assert (
        out["rows"] == table["rows"] and out["test_seeds"] == table["test_seeds"]
    )  # the per-seed measurements stay: they are data, not a comparison
    assert not list(kit.schema_validator("dispatch-eval").iter_errors(out))
    assert table["comparisons"]  # the input was not modified


@pytest.mark.req("FR-007-46")
def test_a_real_evaluation_is_published_unchanged_without_a_marker():
    table = kit.example("dispatch-eval.valid.json")
    out = publish_table(table, fixture=False)
    assert out == table and "fixture" not in out
    assert out is not table
    assert publish_table(table) == table  # the default is a real result


@pytest.mark.req("FR-007-46")
@pytest.mark.parametrize("bad", ["yes", 1, None, 0, []])
def test_a_non_boolean_fixture_argument_is_rejected(bad):
    with pytest.raises((TypeError, ValueError)):
        publish_table(kit.example("dispatch-eval.valid.json"), fixture=bad)


@pytest.mark.req("FR-007-46")
def test_a_fixture_table_that_already_has_comparisons_never_leaks_them_through_nested_fields():
    table = kit.example("dispatch-eval.valid.json")
    table["comparisons"][0]["differences"].append({"seed": 1, "diff_t_per_h": 5.0})
    out = publish_table(table, fixture=True)
    assert out["comparisons"] == []
    assert "differences" not in json.dumps(out) and "ci95" not in json.dumps(out)
