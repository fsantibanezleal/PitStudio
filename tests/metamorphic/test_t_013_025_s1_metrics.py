# ruff: noqa: E501, PT018, PT011, PERF401
"""T-013-025: S1 metrics (P_d, points on target, dust returns, TTC margin), lidar-versus-radar comparison, hostile inputs.

Requirements: FR-013-36, FR-013-37, FR-013-42, P-013-13, SC-013-04.

Oracle: synthetic labelled frames with known detection counts, hand-computed per bin (P_d = detecting frames / frames, the mean
points on target, dust returns per 10^4 beams), the TTC arithmetic of the plan (R_det = 50 m, 40 km/h: 50 / (40 / 3.6) - 3 s =
4.5 s - 3 s = 1.50 s), the paired mean-difference confidence interval of the decision rule FR-000-05 worked by hand (t-based 95 %
interval; the fixtures sit far from the decision boundary, so any standard interval gives the same verdict), the relations
P-013-13 (P_d non-increasing in k_min; duplicating frames changes nothing; doubling v halves R_det / v), and a checklist of the
result rows SC-013-04 requires.

Expected API (package `pitstudio.sensors.metrics`, root environment):
- `metrics.RADAR_LABEL == "radar dust immunity assumed (UNVERIFIED)"` (FR-013-24).
- `metrics.s1_metrics(observations, *, target_ids, levels, k_min=3, range_bin_m=5.0, speeds_km_h=(30, 40, 50),
  margin_s=3.0) -> dict`. `observations`: a list of frames, each `{"level", "target", "target_range_m", "beams_emitted",
  "object_id", "material_class"}` (`level`: a transmittance level T1 from `levels` or a dust-field run id; `object_id` (n,)
  uint32 and `material_class` (n,) strings ("retro", "diffuse" or "dust") describe the frame's returns after the dust model).
  `target_ids` maps a target name to its object id in the scene labels. A frame is binned by `floor(target_range_m /
  range_bin_m)`; it detects the target when at least `k_min` returns of the target's object id (class not "dust") exist.
  Returns `{"bins": [...], "detection": [...]}` sorted by (target, level, bin): a bin row is `{"target", "level", "bin_lo_m",
  "bin_hi_m", "frames", "p_d", "points_on_target_mean", "false_dust_per_1e4_beams"}` (dust returns over all frames of the bin /
  beams over all frames x 10^4); a detection row is `{"target", "level", "r_det_m", "ttc_margin_s": {speed km/h: margin or
  None}}` with `r_det_m` the lower edge of the farthest bin with P_d >= 0.9 (None if none) and the margin
  `r_det_m / (v / 3.6) - margin_s`.
- `metrics.compare_sensors(a, b, *, a_name="lidar", b_name="radar") -> dict` on paired per-frame scores: `{"verdict":
  "<a_name> better" | "<b_name> better" | "no significant difference", "mean_diff", "ci_low", "ci_high", "n", "label"}`; the verdict
  names a sensor only when the paired 95 % interval of the mean difference a - b excludes 0; `label` is `RADAR_LABEL` whenever
  either name is "radar", else None.
- Hostile input (`k_min` < 1, an empty `levels`, a speed <= 0, `range_bin_m` <= 0, a target absent from `target_ids`, a level not in
  `levels`, a negative or non-finite `target_range_m`, `beams_emitted` <= 0, arrays of different length, fewer than 2 paired
  scores or unequal or non-finite scores) raises `ValueError` naming the input.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
from pitstudio.sensors import metrics  # noqa: E402

TARGETS = {"light-vehicle": 7, "person-vest": 8, "boulder": 9, "oncoming-truck": 10}
LEVELS = [1.0, 0.9, 0.74, 0.5, 0.3, 0.1, 0.06, 0.02]  # the pre-registered transmittance grid (FR-013-36)
VISIBLE = {"material_class": "diffuse"}


def _frame(
    level: float, target: str, rng_m: float, on_target: int, dust_returns: int = 0, beams: int = 10_000, other: int = 20
) -> dict:
    ids = [TARGETS[target]] * on_target + [0] * other + [0] * dust_returns
    cls = ["diffuse"] * (on_target + other) + ["dust"] * dust_returns
    return {
        "level": level,
        "target": target,
        "target_range_m": rng_m,
        "beams_emitted": beams,
        "object_id": np.array(ids, dtype=np.uint32),
        "material_class": np.array(cls),
    }


def _fixture() -> list[dict]:
    """light-vehicle at T1 = 1.0: bin [50, 55) 9 of 10 frames with 3 points (P_d 0.9), bin [55, 60) 8 of 10 (0.8)."""
    frames = []
    for i in range(10):
        frames.append(_frame(1.0, "light-vehicle", 52.0 + 0.1 * i, 3 if i < 9 else 2, dust_returns=5 if i < 5 else 0))
    for i in range(10):
        frames.append(_frame(1.0, "light-vehicle", 57.0 + 0.1 * i, 4 if i < 8 else 0))
    for i in range(10):
        frames.append(_frame(1.0, "light-vehicle", 41.0 + 0.1 * i, 10))  # a near bin, always detected
    return frames


def _row(result: dict, target: str, level: float, lo: float) -> dict:
    return next(b for b in result["bins"] if (b["target"], b["level"], b["bin_lo_m"]) == (target, level, lo))


@pytest.mark.req("FR-013-36")
def test_pd_points_and_false_dust_per_bin_match_the_hand_calculation() -> None:
    res = metrics.s1_metrics(_fixture(), target_ids=TARGETS, levels=LEVELS)
    near, mid, far = (_row(res, "light-vehicle", 1.0, lo) for lo in (40.0, 50.0, 55.0))
    assert (near["bin_hi_m"], mid["bin_hi_m"], far["bin_hi_m"]) == (45.0, 55.0, 60.0)
    assert (near["frames"], mid["frames"], far["frames"]) == (10, 10, 10)
    assert (near["p_d"], mid["p_d"], far["p_d"]) == (1.0, 0.9, 0.8)  # 9 of 10 frames reach k_min = 3
    assert mid["points_on_target_mean"] == pytest.approx((9 * 3 + 2) / 10)  # 2.9
    assert far["points_on_target_mean"] == pytest.approx((8 * 4) / 10)  # 3.2
    assert mid["false_dust_per_1e4_beams"] == pytest.approx(25 / 100_000 * 1e4)  # 5 dust returns in 5 frames: 2.5
    assert near["false_dust_per_1e4_beams"] == 0.0
    assert len(res["bins"]) == 3  # only the bins that hold frames


@pytest.mark.req("FR-013-36")
def test_dust_returns_are_never_counted_as_points_on_target() -> None:
    f = _frame(1.0, "light-vehicle", 52.0, on_target=2, dust_returns=50)
    f["object_id"][-50:] = TARGETS["light-vehicle"]  # dust returns that carry the target's object id by accident
    res = metrics.s1_metrics([f], target_ids=TARGETS, levels=LEVELS)
    row = _row(res, "light-vehicle", 1.0, 50.0)
    assert row["p_d"] == 0.0 and row["points_on_target_mean"] == 2.0  # 2 target points < k_min = 3


@pytest.mark.req("FR-013-36")
def test_ttc_margin_at_the_detection_range_by_hand() -> None:
    """R_det = 50 m (the farthest bin with P_d >= 0.9): v = 30, 40, 50 km/h gives 6.0 - 3, 4.5 - 3, 3.6 - 3 seconds."""
    res = metrics.s1_metrics(_fixture(), target_ids=TARGETS, levels=LEVELS)
    (det,) = [d for d in res["detection"] if (d["target"], d["level"]) == ("light-vehicle", 1.0)]
    assert det["r_det_m"] == 50.0
    margins = {float(v): m for v, m in det["ttc_margin_s"].items()}
    assert margins[30.0] == pytest.approx(3.0, abs=1e-12)
    assert margins[40.0] == pytest.approx(1.5, abs=1e-12)  # 50 / (40 / 3.6) = 4.5 s, minus 3 s
    assert margins[50.0] == pytest.approx(0.6, abs=1e-12)


@pytest.mark.req("FR-013-36")
def test_levels_targets_and_runs_are_reported_separately_and_no_detection_gives_no_margin() -> None:
    frames = [_frame(0.5, "person-vest", 22.0, 1) for _ in range(5)] + [
        _frame("run-01", "boulder", 12.0, 5) for _ in range(4)
    ]
    res = metrics.s1_metrics(frames, target_ids=TARGETS, levels=[*LEVELS, "run-01"])
    keys = {(b["target"], b["level"]) for b in res["bins"]}
    assert keys == {("person-vest", 0.5), ("boulder", "run-01")}
    person = next(d for d in res["detection"] if d["target"] == "person-vest")
    assert person["r_det_m"] is None and all(m is None for m in person["ttc_margin_s"].values())
    boulder = next(d for d in res["detection"] if d["target"] == "boulder")
    assert boulder["r_det_m"] == 10.0  # the bin [10, 15)


@pytest.mark.req("FR-013-36")
def test_the_range_bin_width_and_k_min_are_parameters() -> None:
    frames = [_frame(1.0, "light-vehicle", 52.0, 3), _frame(1.0, "light-vehicle", 57.0, 3)]
    one_bin = metrics.s1_metrics(frames, target_ids=TARGETS, levels=LEVELS, range_bin_m=10.0)
    assert [(b["bin_lo_m"], b["bin_hi_m"], b["frames"]) for b in one_bin["bins"]] == [(50.0, 60.0, 2)]
    strict = metrics.s1_metrics(frames, target_ids=TARGETS, levels=LEVELS, k_min=4)
    assert all(b["p_d"] == 0.0 for b in strict["bins"])


def _random_frames(seed: int, n: int = 60) -> list[dict]:
    rng = np.random.default_rng(seed)
    return [
        _frame(
            float(rng.choice([1.0, 0.5])),
            "light-vehicle",
            float(rng.uniform(10, 80)),
            int(rng.integers(0, 9)),
            int(rng.integers(0, 30)),
        )
        for _ in range(n)
    ]


@pytest.mark.req("P-013-13")
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1))
def test_pd_is_non_increasing_in_k_min(seed: int) -> None:
    frames = _random_frames(seed)
    previous = None
    for k in range(1, 8):
        res = metrics.s1_metrics(frames, target_ids=TARGETS, levels=LEVELS, k_min=k)
        pd = {(b["level"], b["bin_lo_m"]): b["p_d"] for b in res["bins"]}
        if previous is not None:
            assert all(pd[key] <= previous[key] + 1e-15 for key in pd)
        previous = pd


@pytest.mark.req("P-013-13")
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1))
def test_duplicating_every_frame_changes_no_rate(seed: int) -> None:
    frames = _random_frames(seed)
    once = metrics.s1_metrics(frames, target_ids=TARGETS, levels=LEVELS)
    twice = metrics.s1_metrics(frames + frames, target_ids=TARGETS, levels=LEVELS)
    assert len(once["bins"]) == len(twice["bins"])
    for a, b in zip(once["bins"], twice["bins"], strict=True):
        assert b["frames"] == 2 * a["frames"]
        for key in ("p_d", "points_on_target_mean", "false_dust_per_1e4_beams"):
            assert b[key] == pytest.approx(a[key], rel=1e-12, abs=1e-12)
    assert [d["r_det_m"] for d in once["detection"]] == [d["r_det_m"] for d in twice["detection"]]


@pytest.mark.req("P-013-13")
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1), v=st.floats(5.0, 60.0))
def test_doubling_the_speed_halves_r_det_over_v(seed: int, v: float) -> None:
    frames = [
        _frame(1.0, "light-vehicle", 5.0 * b + 1.0, 5) for b in range(int(np.random.default_rng(seed).integers(2, 15)))
    ]
    res = metrics.s1_metrics(frames, target_ids=TARGETS, levels=LEVELS, speeds_km_h=(v, 2 * v))
    (det,) = res["detection"]
    m1, m2 = [m for _, m in sorted((float(k), m) for k, m in det["ttc_margin_s"].items())]  # margins at v and 2 v
    assert (m1 + 3.0) == pytest.approx(2.0 * (m2 + 3.0), rel=1e-12)  # R_det / v at v is twice R_det / v at 2 v
    assert math.isfinite(m1)


@pytest.mark.req("FR-013-37")
@pytest.mark.parametrize(
    ("pairs", "verdict"),
    [
        ([(1, 0)] * 28 + [(0, 1)] * 2, "lidar better"),  # mean 0.867, s 0.507, 95 % CI about [0.68, 1.06]
        ([(0, 1)] * 28 + [(1, 0)] * 2, "radar better"),
        ([(1, 0)] * 17 + [(0, 1)] * 13, "no significant difference"),  # mean 0.133, s 1.0, CI about [-0.24, 0.51]
        ([(1, 1)] * 30, "no significant difference"),  # no difference at all: the interval is [0, 0]
        ([(1, 0), (0, 1)] * 15, "no significant difference"),
    ],
)
def test_a_sensor_is_better_only_when_the_paired_interval_excludes_zero(
    pairs: list[tuple[int, int]], verdict: str
) -> None:
    a = np.array([p[0] for p in pairs], dtype=float)
    b = np.array([p[1] for p in pairs], dtype=float)
    res = metrics.compare_sensors(a, b)
    assert res["verdict"] == verdict and res["n"] == 30
    d = a - b
    assert res["mean_diff"] == pytest.approx(float(d.mean()), abs=1e-12)
    assert res["ci_low"] <= res["mean_diff"] <= res["ci_high"]
    if verdict == "lidar better":
        assert res["ci_low"] > 0
    elif verdict == "radar better":
        assert res["ci_high"] < 0
    else:
        assert res["ci_low"] <= 0 <= res["ci_high"]


@pytest.mark.req("FR-013-37")
def test_the_radar_dust_immunity_label_travels_with_every_lidar_radar_comparison() -> None:
    assert metrics.RADAR_LABEL == "radar dust immunity assumed (UNVERIFIED)"
    a, b = np.array([1.0, 0.0, 1.0, 1.0]), np.array([0.0, 0.0, 1.0, 0.0])
    assert metrics.compare_sensors(a, b)["label"] == metrics.RADAR_LABEL
    assert metrics.compare_sensors(a, b, a_name="radar", b_name="lidar")["label"] == metrics.RADAR_LABEL
    assert metrics.compare_sensors(a, b, a_name="lidar-rotary", b_name="lidar-solid")["label"] is None
    renamed = metrics.compare_sensors(np.ones(30), np.zeros(30), a_name="rotary", b_name="solid-state")
    assert renamed["verdict"] == "rotary better"


def _expect_value_error(call, *needles: str) -> None:
    with pytest.raises(ValueError) as exc:
        call()
    for n in needles:
        assert n in str(exc.value), (n, str(exc.value))


@pytest.mark.req("FR-013-42")
def test_hostile_metric_inputs_raise_value_error_naming_the_input() -> None:
    ok = _fixture()
    base = {"target_ids": TARGETS, "levels": LEVELS}
    _expect_value_error(lambda: metrics.s1_metrics(ok, k_min=0, **base), "k_min")
    _expect_value_error(lambda: metrics.s1_metrics(ok, k_min=-3, **base), "k_min")
    _expect_value_error(lambda: metrics.s1_metrics(ok, target_ids=TARGETS, levels=[]), "levels")
    _expect_value_error(lambda: metrics.s1_metrics(ok, speeds_km_h=(30, 0, 50), **base), "speeds")
    _expect_value_error(lambda: metrics.s1_metrics(ok, speeds_km_h=(-40,), **base), "speeds")
    _expect_value_error(lambda: metrics.s1_metrics(ok, range_bin_m=0.0, **base), "range_bin_m")
    _expect_value_error(lambda: metrics.s1_metrics(ok, range_bin_m=-5.0, **base), "range_bin_m")
    _expect_value_error(lambda: metrics.s1_metrics(ok, range_bin_m=float("nan"), **base), "range_bin_m")
    _expect_value_error(
        lambda: metrics.s1_metrics(
            [_frame(1.0, "light-vehicle", 5.0, 1)], target_ids={"person-vest": 8}, levels=LEVELS
        ),
        "light-vehicle",
    )
    _expect_value_error(lambda: metrics.s1_metrics([_frame(0.42, "light-vehicle", 5.0, 1)], **base), "level")
    for bad_range in (-1.0, float("nan"), float("inf")):
        _expect_value_error(
            lambda r=bad_range: metrics.s1_metrics([_frame(1.0, "light-vehicle", r, 1)], **base), "target_range_m"
        )
    _expect_value_error(
        lambda: metrics.s1_metrics([_frame(1.0, "light-vehicle", 5.0, 1, beams=0)], **base), "beams_emitted"
    )
    broken = _frame(1.0, "light-vehicle", 5.0, 1)
    broken["material_class"] = broken["material_class"][:-1]
    _expect_value_error(lambda: metrics.s1_metrics([broken], **base), "material_class")


@pytest.mark.req("FR-013-42")
def test_hostile_comparison_inputs_raise_value_error() -> None:
    _expect_value_error(lambda: metrics.compare_sensors(np.array([1.0]), np.array([0.0])))  # fewer than 2 pairs
    _expect_value_error(lambda: metrics.compare_sensors(np.ones(5), np.ones(4)))
    _expect_value_error(lambda: metrics.compare_sensors(np.array([1.0, np.nan, 0.0]), np.ones(3)))
    _expect_value_error(lambda: metrics.compare_sensors(np.array([1.0, np.inf, 0.0]), np.ones(3)))


# ---------------------------------------------------------------------------------------------------- SC-013-04
@pytest.mark.req("SC-013-04")
def test_the_result_rows_required_by_the_success_criterion_are_all_reported() -> None:
    """SC-013-04: P_d against range and transmittance, points on target, false dust returns, TTC margins at 30/40/50
    km/h and the lidar-versus-radar ranges are the reported results; no rendering-throughput figure appears anywhere."""
    frames = [
        _frame(level, "light-vehicle", 5.0 * b + 2.0, 4, dust_returns=3) for level in (1.0, 0.5) for b in range(4)
    ]
    res = metrics.s1_metrics(frames, target_ids=TARGETS, levels=LEVELS)
    assert {"p_d", "points_on_target_mean", "false_dust_per_1e4_beams", "bin_lo_m", "bin_hi_m", "level"} <= set(
        res["bins"][0]
    )
    assert {"r_det_m", "ttc_margin_s"} <= set(res["detection"][0])
    assert sorted(float(v) for v in res["detection"][0]["ttc_margin_s"]) == [30.0, 40.0, 50.0]  # the default speeds
    forbidden = ("fps", "throughput", "frame_time", "latency", "wall", "rays_per", "ms_per")
    seen = {k for row in res["bins"] + res["detection"] for k in row}
    assert not [k for k in seen if any(f in k for f in forbidden)]
