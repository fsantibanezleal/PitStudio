"""T-017-013: held-out R^2, per-sweep distribution, monotonicity pass rates, optimisation gap, acceptance (pipeline).

Requirements: FR-017-05, FR-017-06, P-017-18, SC-017-01.

Spec: specs/017-planning-survey/spec.md
- FR-017-05: `s50_evaluate` reports, per output (kWh/t, t/h, cost/t), the R^2 pooled over all held-out points, the
  distribution of per-sweep R^2 (median, minimum), the maximum absolute error, and the pass rates of the monotonicity
  checks of section 7 for both the chain and the meta-model (lower target P80 -> higher kWh/t; higher W_i -> higher
  kWh/t; t/h x kWh/t = eta P_mill);
- FR-017-06: for each held-out configuration it takes the meta-model's argmax of t/h subject to kWh/t <= the
  configuration's cap over a 1,024-point blast-design grid, re-evaluates the chain there, and reports the t/h gap (%)
  and any cap violation;
- P-017-18: R^2 equals 1 for exact predictions, matches the hand calculation, and is unchanged when y and y-hat undergo
  the same affine map a y + b with a != 0 (rtol 1e-12; n in [2, 10^4]);
- SC-017-01: R^2 >= 0.95 against the analytical chain on held-out sweeps, for kWh/t and for t/h, pooled over the 40
  held-out sweeps.
plan.md test strategy rows FR-017-05 (R^2 by hand on 5 points; pooled vs per-sweep on a 2-sweep fixture), FR-017-06 (a
fixture meta-model equal to the chain gives a gap of 0; one with a known offset gives the hand-computed gap),
SC-017-01 (report logic on fixture results that pass and fail by construction).

Oracles (hand calculations written in the test):
- R^2 = 1 - SS_res / SS_tot: y = (1, 2, 3, 4, 5), y-hat = (1.1, 1.9, 3.2, 3.8, 5.1): SS_res = 0.11, SS_tot = 10, R^2 =
  0.989; two-sweep fixture: sweep A exact (R^2 1), sweep B y = (1, 2, 3), y-hat = (2, 2, 2) (SS_res 2, SS_tot 2, R^2 0),
  pooled SS_res 2, SS_tot 4, R^2 0.5, median of the per-sweep values 0.5, minimum 0;
- the optimisation fixture: chain kWh/t = 10 + g, t/h = 100 + 10 g, cap 15 (chain-feasible g <= 5); a meta-model that
  under-predicts energy by 2 and over-predicts t/h by 10 % takes g = 7 (predicted kWh/t 15), where the chain gives kWh/t
  17 > 15 (cap violation) and t/h 170; the predicted t/h is 187, so the gap is 100 (187 - 170) / 170 = 10 %;
- thresholds.yaml `models.meta_model_r2_min` = 0.95; monotone and deliberately non-monotone toy predictors with known
  pass rates.

Expected public API (module `pitstudio_pipeline.mine_to_mill.evaluate`, `pipeline/` environment, numpy only):
    OUTPUTS = ("kwh_per_t", "t_per_h", "cost_per_t")
    r2(y, y_hat) -> float                    # 1 - SS_res / SS_tot (1.0 for a constant-free exact fit)
    output_report(y_sweeps: Sequence[np.ndarray], y_hat_sweeps: Sequence[np.ndarray]) -> dict
        each element (n_i, 3) in OUTPUTS order; returns {output: {"r2_pooled", "r2_per_sweep": {"median", "min"},
        "max_abs_error"}}.
    monotonicity_pass_rates(predict, X: np.ndarray, names: Sequence[str]) -> dict
        `predict(X) -> (n, 3)` in OUTPUTS order, X (n, 15) with the section-7 input names `names`. Returns {"p80":
        share of rows whose kWh/t does not increase when target_p80_um grows by 10 %, "work_index": share whose kWh/t
        does not decrease when bond_work_index_kwh_per_t grows by 10 %, "identity": share with |t/h x kWh/t - eta
        P_mill| <= 1e-6 eta P_mill}.
    GRID_POINTS = 1024
    blast_grid(box: Mapping[str, tuple[float, float]], n: int = GRID_POINTS) -> list[dict]
        n blast designs {burden_m, spacing_ratio, powder_factor_kg_per_m3} inside the box, deterministic.
    @dataclass OptimisationGap     # gap_pct: float | None, cap_violation: bool, index: int | None
    optimisation_gap(config_inputs: Mapping, grid: Sequence[Mapping], *, meta, chain, cap: float) -> OptimisationGap
        `meta(rows: list[dict]) -> np.ndarray (n, 3)` (OUTPUTS order); `chain(row: dict)` returns an object with
        kwh_per_t, t_per_h. Rows are config_inputs + one grid point. index = the grid point with the largest predicted
        t/h among those with predicted kWh/t <= cap (None and gap_pct None when none is feasible); gap_pct = 100
        (predicted t/h - chain t/h) / chain t/h at that point; cap_violation = chain kWh/t > cap there.
    acceptance(report: Mapping) -> Acceptance      # passes: bool, statement: str
        report = output_report(...) result; passes iff r2_pooled >= 0.95 for kwh_per_t and for t_per_h; the statement
        names both R^2 values and contains "accepted" or "not accepted".
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio_pipeline.mine_to_mill.evaluate import (
    GRID_POINTS,
    OUTPUTS,
    acceptance,
    blast_grid,
    monotonicity_pass_rates,
    optimisation_gap,
    output_report,
    r2,
)

ROOT = Path(__file__).resolve().parents[2]
R2_MIN = yaml.safe_load((ROOT / "specs/000-foundation/thresholds.yaml").read_text("utf-8"))["models"][
    "meta_model_r2_min"
]


# ----------------------------------------------------------------------------------------------------------------------
# P-017-18
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("P-017-18")
def test_r2_by_hand_on_five_points() -> None:
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    yh = np.array([1.1, 1.9, 3.2, 3.8, 5.1])
    assert r2(y, yh) == pytest.approx(1 - 0.11 / 10.0, rel=1e-12)  # 0.989
    assert r2(y, y.copy()) == 1.0


@pytest.mark.req("P-017-18")
@settings(max_examples=200, deadline=None)
@given(
    n=st.integers(2, 10_000),
    seed=st.integers(0, 2**32 - 1),
    a=st.floats(0.01, 100).flatmap(lambda m: st.sampled_from([m, -m])),
    b=st.floats(-1e3, 1e3),
)
def test_r2_is_one_for_exact_predictions_and_unchanged_by_a_common_affine_map(n, seed, a, b):
    rng = np.random.default_rng(seed)
    y = rng.normal(5.0, 2.0, n)
    yh = y + rng.normal(0.0, 0.5, n)
    base = r2(y, yh)
    assert r2(y, y.copy()) == 1.0
    assert r2(a * y + b, a * yh + b) == pytest.approx(base, rel=1e-12)


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-05
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-05")
def test_pooled_and_per_sweep_r2_on_the_two_sweep_fixture_by_hand() -> None:
    ya = np.column_stack([[1.0, 2.0, 3.0]] * 3)
    yb = np.column_stack([[1.0, 2.0, 3.0]] * 3)
    yha, yhb = ya.copy(), np.column_stack([[2.0, 2.0, 2.0]] * 3)
    report = output_report([ya, yb], [yha, yhb])
    assert set(report) == set(OUTPUTS)
    for name in OUTPUTS:
        assert report[name]["r2_pooled"] == pytest.approx(0.5, rel=1e-12)
        assert report[name]["r2_per_sweep"]["median"] == pytest.approx(0.5, rel=1e-12)
        assert report[name]["r2_per_sweep"]["min"] == pytest.approx(0.0, abs=1e-12)
        assert report[name]["max_abs_error"] == 1.0


@pytest.mark.req("FR-017-05")
def test_each_output_is_scored_on_its_own_column() -> None:
    y = np.column_stack([[1.0, 2.0, 3.0], [10.0, 20.0, 30.0], [5.0, 5.5, 6.0]])
    yh = y.copy()
    yh[:, 1] += np.array([0.0, 0.0, 3.0])  # only t/h is off, by 3 at one point
    report = output_report([y], [yh])
    assert report["kwh_per_t"]["r2_pooled"] == 1.0
    assert report["cost_per_t"]["max_abs_error"] == 0.0
    assert report["t_per_h"]["max_abs_error"] == 3.0
    assert report["t_per_h"]["r2_pooled"] == pytest.approx(1 - 9.0 / 200.0, rel=1e-12)  # SS_tot = 100 + 0 + 100


NAMES = [
    "burden_m", "spacing_ratio", "powder_factor_kg_per_m3", "hole_diameter_mm", "bench_height_m", "rock_factor",
    "bond_work_index_kwh_per_t", "crusher_css_mm", "target_p80_um", "mill_power_kw", "efficiency",
    "energy_cap_kwh_per_t", "explosive_cost_usd_per_kg", "energy_cost_usd_per_kwh", "consumables_usd_per_t",
]  # fmt: skip


def _x(n: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = np.zeros((n, 15))
    x[:, NAMES.index("burden_m")] = rng.uniform(3, 6, n)
    x[:, NAMES.index("bond_work_index_kwh_per_t")] = rng.uniform(8, 20, n)
    x[:, NAMES.index("target_p80_um")] = rng.uniform(75, 300, n)
    x[:, NAMES.index("mill_power_kw")] = rng.uniform(2000, 20000, n)
    x[:, NAMES.index("efficiency")] = rng.uniform(0.5, 1.0, n)
    return x


def _good(x: np.ndarray) -> np.ndarray:
    col = {n: x[:, i] for i, n in enumerate(NAMES)}
    kwh = 0.5 * col["bond_work_index_kwh_per_t"] + 1000.0 / col["target_p80_um"]
    return np.column_stack([kwh, col["efficiency"] * col["mill_power_kw"] / kwh, 0.1 * kwh])


@pytest.mark.req("FR-017-05")
def test_a_monotone_and_identity_respecting_predictor_passes_every_check() -> None:
    rates = monotonicity_pass_rates(_good, _x(200), NAMES)
    assert rates == {"p80": 1.0, "work_index": 1.0, "identity": 1.0}


@pytest.mark.req("FR-017-05")
def test_pass_rates_are_the_share_of_rows_by_construction() -> None:
    x = _x(100, seed=1)
    flipped = x[:, NAMES.index("burden_m")] > 4.5  # on those rows the predictor breaks both monotonicity checks

    def bad(rows: np.ndarray) -> np.ndarray:
        out = _good(rows)
        sign = np.where(rows[:, NAMES.index("burden_m")] > 4.5, -1.0, 1.0)
        w_i = rows[:, NAMES.index("bond_work_index_kwh_per_t")]
        p80 = rows[:, NAMES.index("target_p80_um")]
        kwh = 20.0 + sign * (0.5 * w_i + 1000.0 / p80)
        return np.column_stack([kwh, out[:, 1], out[:, 2]])

    rates = monotonicity_pass_rates(bad, x, NAMES)
    share_ok = float(np.mean(~flipped))
    assert rates["p80"] == pytest.approx(share_ok, abs=1e-12)
    assert rates["work_index"] == pytest.approx(share_ok, abs=1e-12)
    assert rates["identity"] == 0.0 or rates["identity"] <= share_ok  # the broken kWh/t also breaks t/h x kWh/t


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-06
# ----------------------------------------------------------------------------------------------------------------------


def _grid(n: int = 10) -> list[dict]:
    return [{"burden_m": 3.0 + g, "spacing_ratio": 1.2, "powder_factor_kg_per_m3": 0.6} for g in range(n)]


def _chain(row: dict) -> SimpleNamespace:
    g = row["burden_m"] - 3.0
    return SimpleNamespace(kwh_per_t=10.0 + g, t_per_h=100.0 + 10.0 * g)


def _meta_equal(rows: list[dict]) -> np.ndarray:
    return np.array([[_chain(r).kwh_per_t, _chain(r).t_per_h, 0.0] for r in rows])


def _meta_offset(rows: list[dict]) -> np.ndarray:
    return np.array([[_chain(r).kwh_per_t - 2.0, 1.1 * _chain(r).t_per_h, 0.0] for r in rows])


@pytest.mark.req("FR-017-06")
def test_a_meta_model_equal_to_the_chain_has_zero_gap_and_no_cap_violation() -> None:
    result = optimisation_gap({}, _grid(), meta=_meta_equal, chain=_chain, cap=15.0)
    assert result.index == 5  # largest feasible g: kWh/t 10 + g <= 15
    assert result.gap_pct == pytest.approx(0.0, abs=1e-12)
    assert result.cap_violation is False


@pytest.mark.req("FR-017-06")
def test_a_known_offset_gives_the_hand_computed_gap_and_a_cap_violation() -> None:
    result = optimisation_gap({}, _grid(), meta=_meta_offset, chain=_chain, cap=15.0)
    assert result.index == 7  # predicted kWh/t = 8 + g <= 15
    assert result.gap_pct == pytest.approx(10.0, rel=1e-12)  # (187 - 170) / 170 x 100
    assert result.cap_violation is True  # the chain gives 17 kWh/t there


@pytest.mark.req("FR-017-06")
def test_no_feasible_point_gives_no_choice() -> None:
    result = optimisation_gap({}, _grid(), meta=_meta_equal, chain=_chain, cap=5.0)
    assert (result.index, result.gap_pct) == (None, None)
    assert result.cap_violation is False


@pytest.mark.req("FR-017-06")
def test_the_blast_grid_has_1024_deterministic_points_inside_the_box() -> None:
    box = {"burden_m": (3.0, 6.0), "spacing_ratio": (1.0, 1.5), "powder_factor_kg_per_m3": (0.3, 1.0)}
    grid = blast_grid(box)
    assert GRID_POINTS == len(grid) == 1024
    assert grid == blast_grid(box)
    for point in grid:
        for name, (lo, hi) in box.items():
            assert lo <= point[name] <= hi
    assert len({tuple(p.values()) for p in grid}) == 1024


# ----------------------------------------------------------------------------------------------------------------------
# SC-017-01
# ----------------------------------------------------------------------------------------------------------------------


def _report(r2_kwh: float, r2_th: float) -> dict:
    stat = {"r2_per_sweep": {"median": 0.97, "min": 0.9}, "max_abs_error": 1.0}
    return {
        "kwh_per_t": {**stat, "r2_pooled": r2_kwh},
        "t_per_h": {**stat, "r2_pooled": r2_th},
        "cost_per_t": {**stat, "r2_pooled": 0.1},  # cost/t has no acceptance threshold
    }


@pytest.mark.req("SC-017-01")
def test_the_threshold_is_the_preregistered_095() -> None:
    assert R2_MIN == 0.95


@pytest.mark.req("SC-017-01")
@pytest.mark.parametrize(
    ("kwh", "th", "passes"),
    [(0.95, 0.95, True), (0.99, 0.96, True), (0.9499, 0.99, False), (0.99, 0.9499, False), (0.5, 0.5, False)],
)
def test_acceptance_needs_095_on_both_kwh_per_t_and_t_per_h(kwh: float, th: float, passes: bool) -> None:
    result = acceptance(_report(kwh, th))
    assert result.passes is passes
    assert ("not accepted" in result.statement) is (not passes)


@pytest.mark.req("SC-017-01")
def test_a_low_cost_r2_does_not_block_acceptance() -> None:
    assert acceptance(_report(0.99, 0.99)).passes is True
