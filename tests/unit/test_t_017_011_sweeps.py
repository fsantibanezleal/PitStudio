"""T-017-011: Sobol sweeps, configuration split, knowledge-table links, hostile configurations (unit, property).

Requirements: FR-017-02, FR-017-10, P-017-19.

Spec: specs/017-planning-survey/spec.md
- FR-017-02: the sweep generator (`s05_synthesize`) draws 200 ore x circuit configurations by scrambled Sobol (seeded)
  over the box of section 7 and 64 blast designs per configuration by scrambled Sobol, evaluates the chain at every
  point, splits by configuration into 140 training, 20 validation and 40 held-out sweeps, and links every box bound to
  its `minephys` knowledge-table row, propagating UNVERIFIED flags into the sweep manifest (DC-017-01);
- FR-017-10: a sweep configuration with an inverted or non-finite bound, an unknown input name, P80 >= the smallest feed
  F80 of the box, fewer than 8 or more than 4,096 points per configuration, fewer than 10 or more than 10^4
  configurations, or overlapping split seeds is rejected before the chain is evaluated;
- P-017-19: the sweep design is a deterministic function of its seed, and its training, validation and held-out
  configurations are disjoint (seeds 0 to 999).
plan.md test strategy rows FR-017-02 / FR-017-10 (seeded Sobol determinism; disjoint splits; invalid configurations
written in the test) and P-017-19.

Oracles:
- the (0, m, s)-net property of a scrambled Sobol sequence (Owen / Matousek scrambling preserves it): the first 2^m
  points have exactly one point in each of the 2^m equal intervals of every one-dimensional projection, so for 256
  configurations and for 64 blast designs the integer parts of `unit_value * n` are a permutation of 0 ... n - 1 (a
  property of the sequence itself, independent of any implementation detail such as the scrambling seed);
- hand-written invalid configurations (the boundaries 8 / 4,096 points, 10 / 10^4 configurations);
- the DC-017-01 draft schema (`jsonschema`) and the spec's valid example for the document shape; the split counts
  140 / 20 / 40 by hand; the UNVERIFIED rows by set arithmetic written in the test;
- a deterministic stub chain written in the test (the sweep generator is tested against ITS outputs, evaluated here
  independently); the chain itself is tested in T-017-010.

Expected public API (module `pitstudio_pipeline.mine_to_mill.sweeps`, `pipeline/` environment, scipy Sobol):
    class SweepConfigError(ValueError)          # `.reason`; the message names the offending key
    CONFIG_INPUTS, POINT_INPUTS                 # tuples of the per-configuration and per-point input names
        (POINT_INPUTS = burden_m, spacing_ratio, powder_factor_kg_per_m3)
    link_bounds(bounds: Mapping[str, tuple[float, float]], rows: Mapping[str, str], statuses: Mapping[str, str])
        -> tuple[dict, list[str]]
        returns the DC-017-01 box ({input: {"min", "max", "row", "verification"}}) and the sorted unique knowledge
        rows whose status is "UNVERIFIED"; SweepConfigError for an input without a row or a row without a status.
    validate_design(design: Mapping, *, smallest_feed_f80_um: float | None = None) -> None
        design: {"seed", "energy_model", "n_configurations", "points_per_configuration", "split": {"train",
        "validation", "held_out"}, "box": {...}}; raises SweepConfigError for the FR-017-10 conditions and for a split
        that does not add up to n_configurations; the P80 check compares the box's target_p80_um maximum with
        `smallest_feed_f80_um` when given.
    generate_sweeps(design: Mapping, *, chain, smallest_feed_f80_um: float | None = None) -> dict
        validates first (nothing is evaluated for a bad design), then returns the DC-017-01 document: schema_version
        "1.0", synthetic true, the honesty label, `design`, `unverified_rows`, `configurations` (id, split, seed,
        inputs, points[{burden_m, spacing_ratio, powder_factor_kg_per_m3, specific_energy_kwh_per_t,
        throughput_t_per_h, cost_usd_per_t}]). `chain(inputs: dict) -> object with kwh_per_t, t_per_h, cost_per_t`
        is called once per point with the 15 section-7 inputs.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio_pipeline.mine_to_mill.sweeps import (
    CONFIG_INPUTS,
    POINT_INPUTS,
    SweepConfigError,
    generate_sweeps,
    link_bounds,
    validate_design,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "specs/017-planning-survey/contracts/comminution-sweep.schema.json").read_text("utf-8"))
LABEL = "calibrated synthetic â€” not validated against real data"

BOUNDS = {
    "burden_m": (3.0, 6.0),
    "spacing_ratio": (1.0, 1.5),
    "powder_factor_kg_per_m3": (0.3, 1.0),
    "hole_diameter_mm": (89.0, 311.0),
    "bench_height_m": (8.0, 16.0),
    "rock_factor": (6.0, 12.0),
    "bond_work_index_kwh_per_t": (8.0, 20.0),
    "crusher_css_mm": (60.0, 200.0),
    "target_p80_um": (75.0, 300.0),
    "mill_power_kw": (2_000.0, 20_000.0),
    "efficiency": (0.5, 1.0),
    "energy_cap_kwh_per_t": (8.0, 30.0),
    "explosive_cost_usd_per_kg": (0.8, 2.0),
    "energy_cost_usd_per_kwh": (0.04, 0.2),
    "consumables_usd_per_t": (0.1, 1.0),
}
ROWS = {name: f"d2_{name}" for name in BOUNDS}


def _statuses(unverified: set[str] | None = None) -> dict[str, str]:
    unverified = unverified if unverified is not None else {"d2_burden_m", "d2_rock_factor"}
    return {row: ("UNVERIFIED" if row in unverified else "VERIFIED") for row in ROWS.values()}


def _design(n_conf: int = 200, n_points: int = 64, split=(140, 20, 40), seed: int = 17, bounds=None) -> dict:
    box, _ = link_bounds(bounds or BOUNDS, ROWS, _statuses())
    return {
        "seed": seed,
        "energy_model": "bond",
        "n_configurations": n_conf,
        "points_per_configuration": n_points,
        "split": {"train": split[0], "validation": split[1], "held_out": split[2]},
        "box": box,
    }


def _fake_chain(x: dict) -> SimpleNamespace:
    """Deterministic stand-in with the identity t/h x kWh/t = eta P_mill."""
    kwh = 4.0 + 0.1 * x["bond_work_index_kwh_per_t"] + 100.0 / x["target_p80_um"] + 0.05 * x["burden_m"]
    return SimpleNamespace(
        kwh_per_t=kwh,
        t_per_h=x["efficiency"] * x["mill_power_kw"] / kwh,
        cost_per_t=x["energy_cost_usd_per_kwh"] * kwh
        + x["consumables_usd_per_t"]
        + 0.01 * x["powder_factor_kg_per_m3"],
    )


def _never_called(_x: dict) -> SimpleNamespace:
    raise AssertionError("the chain must not be evaluated for a rejected design")


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-02: knowledge links
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-02")
def test_every_bound_is_linked_to_its_knowledge_row_and_unverified_flags_propagate() -> None:
    box, unverified = link_bounds(BOUNDS, ROWS, _statuses({"d2_burden_m", "d2_rock_factor"}))
    assert set(box) == set(BOUNDS)
    for name, (lo, hi) in BOUNDS.items():
        assert box[name]["min"] == lo
        assert box[name]["max"] == hi
        assert box[name]["row"] == f"d2_{name}"
    assert box["burden_m"]["verification"] == "UNVERIFIED"
    assert box["efficiency"]["verification"] == "VERIFIED"
    assert unverified == ["d2_burden_m", "d2_rock_factor"]


@pytest.mark.req("FR-017-02")
def test_an_input_without_a_row_or_a_row_without_a_status_is_refused() -> None:
    rows = dict(ROWS)
    del rows["efficiency"]
    with pytest.raises(SweepConfigError, match="efficiency"):
        link_bounds(BOUNDS, rows, _statuses())
    statuses = _statuses()
    del statuses["d2_rock_factor"]
    with pytest.raises(SweepConfigError, match="d2_rock_factor"):
        link_bounds(BOUNDS, ROWS, statuses)


@pytest.mark.req("FR-017-02")
def test_unverified_rows_are_listed_once_and_sorted_in_the_sweep_document() -> None:
    doc = generate_sweeps(_design(n_conf=10, n_points=8, split=(7, 1, 2)), chain=_fake_chain)
    assert doc["unverified_rows"] == ["d2_burden_m", "d2_rock_factor"]
    assert doc["design"]["box"]["burden_m"]["verification"] == "UNVERIFIED"


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-02: the generated sweeps
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-02")
def test_the_default_design_gives_200_configurations_of_64_points_split_140_20_40() -> None:
    doc = generate_sweeps(_design(), chain=_fake_chain)
    configs = doc["configurations"]
    assert len(configs) == 200
    assert all(len(c["points"]) == 64 for c in configs)
    counts = {s: sum(1 for c in configs if c["split"] == s) for s in ("train", "validation", "held_out")}
    assert counts == {"train": 140, "validation": 20, "held_out": 40}
    assert len({c["id"] for c in configs}) == 200
    assert doc["synthetic"] is True
    assert doc["label"] == LABEL
    assert doc["schema_version"] == "1.0"


@pytest.mark.req("FR-017-02")
def test_the_document_validates_against_the_dc_017_01_schema() -> None:
    from jsonschema import Draft202012Validator

    doc = generate_sweeps(_design(n_conf=10, n_points=8, split=(7, 1, 2)), chain=_fake_chain)
    assert list(Draft202012Validator(SCHEMA).iter_errors(doc)) == []


@pytest.mark.req("FR-017-02")
def test_every_point_holds_the_chain_outputs_at_its_own_inputs_and_the_chain_is_called_once_per_point() -> None:
    calls: list[dict] = []

    def spy(x: dict) -> SimpleNamespace:
        calls.append(dict(x))
        return _fake_chain(x)

    doc = generate_sweeps(_design(n_conf=10, n_points=8, split=(7, 1, 2)), chain=spy)
    assert len(calls) == 10 * 8
    for conf in doc["configurations"]:
        for point in conf["points"]:
            x = {**conf["inputs"], **{k: point[k] for k in POINT_INPUTS}}
            expected = _fake_chain(x)  # evaluated independently here
            assert point["specific_energy_kwh_per_t"] == pytest.approx(expected.kwh_per_t, rel=1e-12)
            assert point["throughput_t_per_h"] == pytest.approx(expected.t_per_h, rel=1e-12)
            assert point["cost_usd_per_t"] == pytest.approx(expected.cost_per_t, rel=1e-12)
    assert all(set(c) == set(BOUNDS) for c in calls)  # the chain receives the 15 section-7 inputs


@pytest.mark.req("FR-017-02")
def test_all_draws_lie_inside_the_box() -> None:
    doc = generate_sweeps(_design(n_conf=20, n_points=16, split=(14, 2, 4)), chain=_fake_chain)
    for conf in doc["configurations"]:
        for name in CONFIG_INPUTS:
            if name in conf["inputs"]:
                lo, hi = BOUNDS[name]
                assert lo <= conf["inputs"][name] <= hi, name
        for point in conf["points"]:
            for name in POINT_INPUTS:
                lo, hi = BOUNDS[name]
                assert lo <= point[name] <= hi, name


@pytest.mark.req("FR-017-02")
def test_the_256_configurations_stratify_every_one_dimensional_projection_like_a_scrambled_sobol_net() -> None:
    doc = generate_sweeps(_design(n_conf=256, n_points=8, split=(180, 26, 50)), chain=_fake_chain)
    for name in CONFIG_INPUTS:
        if name not in BOUNDS or name not in doc["configurations"][0]["inputs"]:
            continue
        lo, hi = BOUNDS[name]
        cells = sorted(int(256 * (c["inputs"][name] - lo) / (hi - lo)) for c in doc["configurations"])
        assert cells == list(range(256)), name  # exactly one configuration in each of the 256 strata


@pytest.mark.req("FR-017-02")
def test_the_64_blast_designs_of_a_configuration_stratify_every_point_input_like_a_scrambled_sobol_net() -> None:
    doc = generate_sweeps(_design(n_conf=10, n_points=64, split=(7, 1, 2)), chain=_fake_chain)
    for conf in doc["configurations"]:
        for name in POINT_INPUTS:
            lo, hi = BOUNDS[name]
            cells = sorted(min(63, int(64 * (p[name] - lo) / (hi - lo))) for p in conf["points"])
            assert cells == list(range(64)), (conf["id"], name)


@pytest.mark.req("FR-017-02")
def test_configurations_differ_from_each_other_and_blast_designs_differ_between_configurations() -> None:
    doc = generate_sweeps(_design(n_conf=10, n_points=8, split=(7, 1, 2)), chain=_fake_chain)
    first_points = [tuple(round(p["burden_m"], 9) for p in c["points"]) for c in doc["configurations"]]
    assert len(set(first_points)) == 10  # each configuration has its own scrambled blast-design set
    assert len({c["seed"] for c in doc["configurations"]}) == 10


# ----------------------------------------------------------------------------------------------------------------------
# P-017-19
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("P-017-19")
@settings(max_examples=200, deadline=None)
@given(seed=st.integers(0, 999))
def test_the_design_is_a_deterministic_function_of_its_seed_and_the_splits_are_disjoint(seed):
    design = _design(n_conf=20, n_points=8, split=(14, 2, 4), seed=seed)
    a = generate_sweeps(copy.deepcopy(design), chain=_fake_chain)
    b = generate_sweeps(copy.deepcopy(design), chain=_fake_chain)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    ids = {s: {c["id"] for c in a["configurations"] if c["split"] == s} for s in ("train", "validation", "held_out")}
    assert not ids["train"] & ids["validation"]
    assert not ids["train"] & ids["held_out"]
    assert not ids["validation"] & ids["held_out"]
    assert len(ids["train"]) + len(ids["validation"]) + len(ids["held_out"]) == 20
    assert (len(ids["train"]), len(ids["validation"]), len(ids["held_out"])) == (14, 2, 4)


@pytest.mark.req("P-017-19")
def test_different_seeds_give_different_designs_and_the_split_assignment_depends_on_the_seed() -> None:
    a = generate_sweeps(_design(n_conf=20, n_points=8, split=(14, 2, 4), seed=1), chain=_fake_chain)
    b = generate_sweeps(_design(n_conf=20, n_points=8, split=(14, 2, 4), seed=2), chain=_fake_chain)
    assert a["configurations"][0]["inputs"] != b["configurations"][0]["inputs"]
    assert [c["split"] for c in a["configurations"]] != [c["split"] for c in b["configurations"]]


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-10: hostile configurations
# ----------------------------------------------------------------------------------------------------------------------


def _with_bound(name: str, lo: float, hi: float) -> dict:
    d = _design(n_conf=10, n_points=8, split=(7, 1, 2))
    d["box"][name] = {**d["box"][name], "min": lo, "max": hi}
    return d


HOSTILE = {
    "inverted-bound": ("burden_m", 6.0, 3.0),
    "nan-bound": ("efficiency", float("nan"), 1.0),
    "inf-bound": ("mill_power_kw", 2_000.0, float("inf")),
    "neg-inf-bound": ("rock_factor", float("-inf"), 12.0),
}


@pytest.mark.req("FR-017-10")
@pytest.mark.parametrize("label", sorted(HOSTILE))
def test_inverted_and_non_finite_bounds_are_rejected_before_any_chain_evaluation(label: str) -> None:
    design = _with_bound(*HOSTILE[label])
    with pytest.raises(SweepConfigError):
        generate_sweeps(copy.deepcopy(design), chain=_never_called)
    with pytest.raises(SweepConfigError):
        validate_design(design)


@pytest.mark.req("FR-017-10")
def test_an_unknown_input_name_is_rejected_naming_it() -> None:
    d = _design(n_conf=10, n_points=8, split=(7, 1, 2))
    d["box"]["bogus_input_m"] = {"min": 1.0, "max": 2.0, "row": "d2_burden_m", "verification": "VERIFIED"}
    with pytest.raises(SweepConfigError, match="bogus_input_m"):
        generate_sweeps(d, chain=_never_called)


@pytest.mark.req("FR-017-10")
def test_a_target_p80_at_or_above_the_smallest_feed_f80_of_the_box_is_rejected() -> None:
    d = _design(n_conf=10, n_points=8, split=(7, 1, 2))  # target_p80_um up to 300 um
    with pytest.raises(SweepConfigError, match="target_p80_um"):
        generate_sweeps(d, chain=_never_called, smallest_feed_f80_um=300.0)  # P80 max == F80 min: rejected
    with pytest.raises(SweepConfigError, match="target_p80_um"):
        validate_design(d, smallest_feed_f80_um=150.0)
    assert validate_design(d, smallest_feed_f80_um=300.0001) is None
    assert validate_design(d) is None


@pytest.mark.req("FR-017-10")
@pytest.mark.parametrize(
    ("n_points", "ok"), [(7, False), (8, True), (4096, True), (4097, False), (0, False), (-8, False)]
)
def test_points_per_configuration_must_be_between_8_and_4096(n_points: int, ok: bool) -> None:
    d = _design(n_conf=10, n_points=n_points, split=(7, 1, 2))
    if ok:
        assert validate_design(d) is None
    else:
        with pytest.raises(SweepConfigError, match="points_per_configuration"):
            generate_sweeps(d, chain=_never_called)


@pytest.mark.req("FR-017-10")
@pytest.mark.parametrize(
    ("n_conf", "split", "ok"),
    [
        (9, (6, 1, 2), False),
        (10, (7, 1, 2), True),
        (10_000, (7000, 1000, 2000), True),
        (10_001, (7000, 1001, 2000), False),
        (0, (0, 0, 0), False),
    ],
)
def test_configurations_must_be_between_10_and_10000(n_conf: int, split: tuple, ok: bool) -> None:
    d = _design(n_conf=n_conf, n_points=8, split=split)
    if ok:
        assert validate_design(d) is None
    else:
        with pytest.raises(SweepConfigError, match="n_configurations"):
            generate_sweeps(d, chain=_never_called)


@pytest.mark.req("FR-017-10")
def test_a_split_that_does_not_add_up_to_the_configuration_count_is_rejected() -> None:
    d = _design(n_conf=200, n_points=8, split=(140, 20, 39))
    with pytest.raises(SweepConfigError, match="split"):
        generate_sweeps(d, chain=_never_called)
    d2 = _design(n_conf=200, n_points=8, split=(141, 20, 40))
    with pytest.raises(SweepConfigError, match="split"):
        validate_design(d2)
