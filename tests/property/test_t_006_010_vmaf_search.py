# ruff: noqa: E501, PT018
"""T-006-010: VMAF-targeted constant-quality search, re-measure, pair and poster budgets, `vmaf-unreachable` and `over-budget`,
recorded relaxation.

Requirements: FR-006-02, FR-006-03, FR-006-04, P-006-01, P-006-02, P-006-03, P-006-04.

Spec: specs/006-media-telemetry/spec.md section 3.1 (FR-006-02: the largest constant-quality value whose measured VMAF has
mean >= 93 and 5th percentile >= 85, by bisection over the integer range with at most 8 encodes per variant, and a re-measure of
the chosen setting; FR-006-03: pair <= 25,000,000 bytes, poster <= 150,000 bytes with WebP quality in [50, 90]; FR-006-04:
`vmaf-unreachable` / `over-budget` reporting the best measured (setting, VMAF mean, VMAF p5, bytes), unless a declared
relaxation with a written reason applies), section 4 (P-006-01 to P-006-04) and section 8 (the <= 8 encodes are the bisection
trials; the re-measure is the variant's encoder record; relaxation kinds `lower-target` with mean >= 80, `shorter-duration`,
`crop`, reason >= 10 characters; cq values 1..63, 1..51 for H.264).

Oracle: brute-force enumeration of the whole range on the same fake curve (plan.md test strategy, FR-006-02), hand-calculated
poster and pair-budget boundaries, and the encode-report contract example `encode-report.valid.json` (AV1 range 20..50: the
chosen cq 34 is the largest value with VMAF mean >= 93 on its five published trials).

Expected API of the implementation (module `pitstudio_studio.media.search`, errors in `pitstudio_studio.media.errors`):

    errors.EncodeError(Exception)   base class; attribute `error_class: str`; `str(e)` starts with `"<error_class>: "`
    errors.VmafUnreachable          error_class "vmaf-unreachable"; attribute `best: Trial` (the trial with the highest VMAF mean;
                                    ties go to the smaller cq)
    errors.OverBudget               error_class "over-budget"; attribute `best`: for a pair, a tuple (av1: Trial, h264: Trial) of the
                                    final measurements; for a poster, a tuple of one Trial-like (quality, bytes) is not required
    Measurement(vmaf_mean: float, vmaf_p5: float, bytes: int)   frozen dataclass
    Trial(cq: int, vmaf_mean: float, vmaf_p5: float, bytes: int)        frozen dataclass
    VariantResult(chosen_cq: int, trials: tuple[Trial, ...], final: Measurement)   frozen dataclass
    search_variant(measure, cq_range, *, vmaf_mean_min=93.0, vmaf_p5_min=85.0, max_trials=8) -> VariantResult
        `measure(cq: int) -> Measurement` encodes at `cq` and measures it. The search calls it once per bisection trial (at most
        `max_trials`, in `trials` order) and exactly once more, at `chosen_cq`, for the re-measure whose result is `final`.
        `cq_range = (lo, hi)` inclusive, 1 <= lo <= hi <= 63; larger cq means lower quality and fewer bytes. Raises ValueError
        for an invalid range; raises VmafUnreachable when no setting meets both targets or the re-measure fails them.
    check_pair_budget(av1_bytes: int, h264_bytes: int, *, max_bytes=25_000_000) -> int    returns the total; raises OverBudget above
    choose_poster_quality(size_at, *, max_bytes=150_000, quality_range=(50, 90)) -> int
        `size_at(quality: int) -> int` is the WebP size at that quality; returns the largest quality whose size fits; raises
        OverBudget when even the lowest quality does not fit.
    ClipSearch(av1: VariantResult, h264: VariantResult, pair_bytes: int, relaxation: dict | None)   frozen dataclass
    plan_clip(measure_av1, measure_h264, *, av1_range=(20, 50), h264_range=(15, 40), relaxation=None) -> ClipSearch
        runs `search_variant` for both variants, applies `check_pair_budget`, carries the recipe relaxation verbatim. A relaxation is
        a dict {"kind", "reason", ...}; kind "lower-target" must carry "vmaf_mean_min" in [80, 93) and "vmaf_p5_min" in [0, 85]
        and replaces the targets; "shorter-duration" and "crop" keep 93/85. A relaxation with an unknown kind, a reason shorter than
        10 characters or a lower-target below 80 raises ValueError. An H.264 range above 51 raises ValueError.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_studio.media.errors import EncodeError, OverBudget, VmafUnreachable
from pitstudio_studio.media.search import (
    Measurement,
    check_pair_budget,
    choose_poster_quality,
    plan_clip,
    search_variant,
)

SETTINGS = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
MEAN, P5 = kit.VMAF_MEAN_MIN, kit.VMAF_P5_MIN


class Curve:
    """A fake encoder: tables of (mean, p5, bytes) per cq, with a call log. `noise(cq, call_index)` perturbs repeated calls."""

    def __init__(self, lo, means, p5s, sizes, noise=None):
        self.lo, self.means, self.p5s, self.sizes, self.noise, self.calls = (
            lo,
            list(means),
            list(p5s),
            list(sizes),
            noise,
            [],
        )

    def __call__(self, cq):
        i = cq - self.lo
        self.calls.append(cq)
        d = self.noise(cq, len(self.calls)) if self.noise else 0.0
        return Measurement(self.means[i] + d, self.p5s[i] + d, int(self.sizes[i]))

    def feasible(self, mean_min=MEAN, p5_min=P5):
        return [
            self.lo + i
            for i, (m, p) in enumerate(zip(self.means, self.p5s, strict=True))
            if m >= mean_min and p >= p5_min
        ]


@st.composite
def monotone_curves(draw, max_len=40):
    n = draw(st.integers(1, max_len))
    lo = draw(st.integers(1, 63 - n + 1))
    means = sorted(draw(st.lists(st.floats(55, 100, allow_nan=False), min_size=n, max_size=n)), reverse=True)
    p5s = sorted(draw(st.lists(st.floats(30, 98, allow_nan=False), min_size=n, max_size=n)), reverse=True)
    sizes = sorted(draw(st.lists(st.integers(1_000, 30_000_000), min_size=n, max_size=n)), reverse=True)
    return Curve(lo, means, p5s, sizes), (lo, lo + n - 1)


@st.composite
def arbitrary_curves(draw, max_len=40):
    n = draw(st.integers(1, max_len))
    lo = draw(st.integers(1, 63 - n + 1))
    means = draw(st.lists(st.floats(0, 100, allow_nan=False), min_size=n, max_size=n))
    p5s = draw(st.lists(st.floats(0, 100, allow_nan=False), min_size=n, max_size=n))
    sizes = draw(st.lists(st.integers(1, 30_000_000), min_size=n, max_size=n))
    return Curve(lo, means, p5s, sizes), (lo, lo + n - 1)


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-02 and P-006-01
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("P-006-01")
@pytest.mark.req("FR-006-02")
@SETTINGS
@given(monotone_curves())
def test_search_equals_brute_force_enumeration(case):
    curve, rng = case
    expected = curve.feasible()
    if not expected:
        with pytest.raises(VmafUnreachable):
            search_variant(curve, rng)
        return
    res = search_variant(curve, rng)
    assert res.chosen_cq == max(expected)  # largest value meeting both targets (smallest file)
    assert len(res.trials) <= 8  # FR-006-02: at most 8 encodes per variant (the bisection trials)
    assert all(rng[0] <= t.cq <= rng[1] for t in res.trials)


@pytest.mark.req("FR-006-02")
@SETTINGS
@given(monotone_curves())
def test_chosen_setting_is_remeasured_not_inferred(case):
    curve, rng = case
    if not curve.feasible():
        return
    res = search_variant(curve, rng)
    # one call per trial, in trial order, then exactly one more call at the chosen cq (the re-measure)
    assert len(curve.calls) == len(res.trials) + 1
    assert curve.calls[:-1] == [t.cq for t in res.trials]
    assert curve.calls[-1] == res.chosen_cq
    assert res.final == curve(res.chosen_cq)
    for t in res.trials:
        m = curve(t.cq)
        assert (t.vmaf_mean, t.vmaf_p5, t.bytes) == (m.vmaf_mean, m.vmaf_p5, m.bytes)


@pytest.mark.req("FR-006-02")
def test_contract_example_av1_range_20_50_chooses_34():
    """Oracle: encode-report.valid.json (spec 006 contract example): AV1 range 20..50, five published trials, chosen_cq 34."""
    ex = json.loads((kit.SPEC / "contracts" / "examples" / "encode-report.valid.json").read_text(encoding="utf-8"))
    av1 = ex["clips"][0]["variants"]["av1"]
    pts = {t["cq"]: (t["vmaf_mean"], t["vmaf_p5"], t["bytes"]) for t in av1["trials"]}
    cqs = sorted(pts)

    def interp(cq, k):  # piecewise-linear through the published points, flat-extended outside, same monotone shape
        if cq in pts:
            return pts[cq][k]
        lo = max((c for c in cqs if c < cq), default=None)
        hi = min((c for c in cqs if c > cq), default=None)
        if lo is None:
            return pts[hi][k]
        if hi is None:
            return pts[lo][k]
        w = (cq - lo) / (hi - lo)
        return pts[lo][k] * (1 - w) + pts[hi][k] * w

    curve = Curve(
        20,
        [interp(c, 0) for c in range(20, 51)],
        [interp(c, 1) for c in range(20, 51)],
        [interp(c, 2) for c in range(20, 51)],
    )
    res = search_variant(curve, (av1["cq_range"]["min"], av1["cq_range"]["max"]))
    assert res.chosen_cq == av1["chosen_cq"] == 34
    assert res.final.vmaf_mean == pytest.approx(93.1) and res.final.vmaf_p5 == pytest.approx(86.9)
    assert len(res.trials) <= 8


@pytest.mark.req("FR-006-02")
@pytest.mark.parametrize(
    ("means", "p5s", "expected"),
    [
        ([95, 94, 93, 92], [90, 90, 90, 90], 22),  # the mean binds: 93 at cq 22 is the last passing value (>=)
        (
            [95, 95, 95, 95],
            [90, 86, 85, 84],
            22,
        ),  # the 5th percentile binds: 85 at cq 22 passes (>=), 84 at cq 23 fails
        ([99, 99, 99, 99], [99, 99, 99, 99], 23),  # everything passes: the top of the range
    ],
)
def test_both_targets_bind_with_inclusive_thresholds(means, p5s, expected):
    curve = Curve(20, means, p5s, [4000, 3000, 2000, 1000])
    assert search_variant(curve, (20, 23)).chosen_cq == expected


@pytest.mark.req("FR-006-02")
def test_single_value_range_costs_one_trial_and_one_remeasure():
    curve = Curve(30, [95.0], [90.0], [1234])
    res = search_variant(curve, (30, 30))
    assert res.chosen_cq == 30 and len(res.trials) == 1 and curve.calls == [30, 30]


@pytest.mark.req("FR-006-02")
@pytest.mark.parametrize("rng", [(0, 30), (30, 20), (1, 64), (-3, 10)])
def test_invalid_cq_range_is_rejected_before_any_encode(rng):
    curve = Curve(1, [95.0] * 63, [90.0] * 63, [100] * 63)
    with pytest.raises(ValueError):  # noqa: PT011
        search_variant(curve, rng)
    assert curve.calls == []


@pytest.mark.req("FR-006-02")
def test_measurement_errors_propagate_unchanged():
    def boom(cq):
        raise RuntimeError(f"encoder died at {cq}")

    with pytest.raises(RuntimeError, match="encoder died at"):
        search_variant(boom, (20, 50))


# ---------------------------------------------------------------------------------------------------------------------
# P-006-02, P-006-03, P-006-04
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("P-006-02")
@SETTINGS
@given(monotone_curves(), st.floats(60, 99), st.floats(0, 10), st.floats(30, 90), st.floats(0, 8))
def test_raising_a_target_never_raises_the_quality_value(case, m1, dm, p1, dp):
    curve, rng = case
    a = (m1, p1)
    b = (m1 + dm, p1 + dp)  # componentwise stricter

    def run(t):
        try:
            return search_variant(
                Curve(curve.lo, curve.means, curve.p5s, curve.sizes), rng, vmaf_mean_min=t[0], vmaf_p5_min=t[1]
            ).chosen_cq
        except VmafUnreachable:
            return None

    lax, strict = run(a), run(b)
    if strict is not None:
        assert lax is not None and strict <= lax
    # a lax target that is unreachable makes every stricter target unreachable
    if lax is None:
        assert strict is None


@pytest.mark.req("P-006-03")
@SETTINGS
@given(monotone_curves(), st.floats(0.1, 10, allow_nan=False))
def test_size_scaling_changes_only_the_budget_never_the_vmaf_choice(case, factor):
    curve, rng = case
    base = Curve(curve.lo, curve.means, curve.p5s, curve.sizes)
    scaled = Curve(curve.lo, curve.means, curve.p5s, [max(1, int(s * factor)) for s in curve.sizes])
    try:
        r0 = search_variant(base, rng)
    except VmafUnreachable:
        with pytest.raises(VmafUnreachable):
            search_variant(scaled, rng)
        return
    r1 = search_variant(scaled, rng)
    assert r0.chosen_cq == r1.chosen_cq
    assert [t.cq for t in r0.trials] == [t.cq for t in r1.trials]


@pytest.mark.req("P-006-04")
@SETTINGS
@given(arbitrary_curves())
def test_for_any_curve_the_remeasure_meets_both_targets_or_the_search_fails(case):
    curve, rng = case
    try:
        res = search_variant(curve, rng)
    except VmafUnreachable:
        return
    assert res.final.vmaf_mean >= MEAN and res.final.vmaf_p5 >= P5
    assert curve.calls[-1] == res.chosen_cq and rng[0] <= res.chosen_cq <= rng[1]
    assert len(res.trials) <= 8


@pytest.mark.req("P-006-04")
@pytest.mark.req("FR-006-04")
@SETTINGS
@given(monotone_curves(), st.floats(0.1, 3.0))
def test_a_remeasure_that_misses_a_target_is_never_reported_as_success(case, drop):
    """The first measurement of the winner passes; the re-measure drops by `drop`: a result must still meet the targets."""
    curve, rng = case

    def noisy(cq, call_index):
        return -drop if call_index > 1 and cq == curve.noisy_cq else 0.0

    curve.noisy_cq = None
    pre = curve.feasible()
    if not pre:
        return
    curve.noisy_cq = max(pre)  # the cq the search is going to pick; its repeated measurement is lower
    curve.noise = noisy
    try:
        res = search_variant(curve, rng)
    except VmafUnreachable:
        return
    assert res.final.vmaf_mean >= MEAN and res.final.vmaf_p5 >= P5


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-04: failures and relaxation
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-04")
def test_unreachable_target_fails_with_vmaf_unreachable_and_the_best_measurement():
    # the best VMAF mean anywhere in [20, 50] is 92.9 at cq 20 (< 93): hand-written curve, never reaches the target
    n = 31
    means = [92.9 - 0.1 * i for i in range(n)]
    curve = Curve(20, means, [86.0] * n, [9_000_000 - 100_000 * i for i in range(n)])
    with pytest.raises(VmafUnreachable) as ei:
        search_variant(curve, (20, 50))
    e = ei.value
    assert (
        isinstance(e, EncodeError) and e.error_class == "vmaf-unreachable" and str(e).startswith("vmaf-unreachable: ")
    )
    assert e.best.vmaf_mean == pytest.approx(
        max(means[t - 20] for t in [x for x in curve.calls])
    )  # best of what was measured
    assert e.best.cq in curve.calls and e.best.bytes == curve(e.best.cq).bytes


@pytest.mark.req("FR-006-04")
def test_p5_alone_can_make_the_target_unreachable():
    curve = Curve(20, [99.0] * 4, [84.9] * 4, [400, 300, 200, 100])
    with pytest.raises(VmafUnreachable):
        search_variant(curve, (20, 23))


@pytest.mark.req("FR-006-04")
@pytest.mark.req("FR-006-03")
def test_pair_over_25_million_bytes_fails_with_over_budget_and_boundary_is_inclusive():
    assert check_pair_budget(12_500_000, 12_500_000) == 25_000_000  # exactly the budget passes (<=)
    with pytest.raises(OverBudget) as ei:
        check_pair_budget(12_500_000, 12_500_001)
    assert ei.value.error_class == "over-budget" and str(ei.value).startswith("over-budget: ")
    assert check_pair_budget(1, 1) == 2


@pytest.mark.req("FR-006-04")
def test_plan_clip_over_budget_promotes_nothing():
    av1 = Curve(20, [99.0] * 31, [95.0] * 31, [26_000_000] * 31)  # every setting alone exceeds the pair budget
    h264 = Curve(15, [99.0] * 26, [95.0] * 26, [1_000] * 26)
    with pytest.raises(OverBudget):
        plan_clip(av1, h264)


@pytest.mark.req("FR-006-04")
@pytest.mark.req("FR-006-03")
def test_plan_clip_happy_path_pair_total_and_no_relaxation():
    n1, n2 = 31, 26
    av1 = Curve(20, [100.0 - 0.5 * i for i in range(n1)], [95.0] * n1, [900_000 - 10_000 * i for i in range(n1)])
    h264 = Curve(15, [100.0 - 0.4 * i for i in range(n2)], [95.0] * n2, [700_000 - 10_000 * i for i in range(n2)])
    plan = plan_clip(av1, h264)
    # hand calculation: av1 mean(cq) = 100 - 0.5 (cq - 20) >= 93 -> cq <= 34; h264 mean = 100 - 0.4 (cq - 15) >= 93 -> cq <= 32.5 -> 32
    assert plan.av1.chosen_cq == 34 and plan.h264.chosen_cq == 32
    assert plan.pair_bytes == (900_000 - 10_000 * 14) + (700_000 - 10_000 * 17)
    assert plan.relaxation is None


RELAX_LOWER = {
    "kind": "lower-target",
    "reason": "dust-heavy plume frames cannot reach 93",
    "vmaf_mean_min": 85.0,
    "vmaf_p5_min": 70.0,
}


@pytest.mark.req("FR-006-04")
def test_declared_lower_target_relaxation_is_applied_and_carried_verbatim():
    n1, n2 = 31, 26
    # AV1 tops out at 90 (below 93): only reachable through the relaxation
    av1 = Curve(
        20,
        [90.0 - 0.5 * i for i in range(n1)],
        [80.0 - 0.2 * i for i in range(n1)],
        [900_000 - 10_000 * i for i in range(n1)],
    )
    h264 = Curve(15, [95.0 - 0.4 * i for i in range(n2)], [90.0] * n2, [700_000 - 10_000 * i for i in range(n2)])
    with pytest.raises(VmafUnreachable):
        plan_clip(
            Curve(20, av1.means, av1.p5s, av1.sizes), Curve(15, h264.means, h264.p5s, h264.sizes)
        )  # without the relaxation
    plan = plan_clip(av1, h264, relaxation=dict(RELAX_LOWER))
    # hand calculation, relaxed targets mean >= 85 and p5 >= 70: mean 90 - 0.5 d >= 85 -> d <= 10; p5 80 - 0.2 d >= 70 -> d <= 50 -> cq 30
    assert plan.av1.chosen_cq == 30
    assert plan.av1.final.vmaf_mean >= 85.0 and plan.av1.final.vmaf_p5 >= 70.0
    assert plan.relaxation == RELAX_LOWER  # carried as declared


@pytest.mark.req("FR-006-04")
@pytest.mark.parametrize(
    "bad",
    [
        {
            "kind": "lower-target",
            "reason": "dust-heavy plume frames",
            "vmaf_mean_min": 79.9,
            "vmaf_p5_min": 70.0,
        },  # below the floor of 80
        {
            "kind": "lower-target",
            "reason": "short",
            "vmaf_mean_min": 85.0,
            "vmaf_p5_min": 70.0,
        },  # reason < 10 characters
        {"kind": "lower-target", "reason": "", "vmaf_mean_min": 85.0, "vmaf_p5_min": 70.0},
        {
            "kind": "lower-target",
            "reason": "dust-heavy plume frames",
            "vmaf_mean_min": 93.0,
            "vmaf_p5_min": 70.0,
        },  # not lower
        {"kind": "lower-target", "reason": "dust-heavy plume frames"},  # targets missing
        {"kind": "invent-new-kind", "reason": "dust-heavy plume frames"},
        {"kind": "crop"},  # no reason
    ],
)
def test_invalid_relaxations_are_rejected_before_any_encode(bad):
    av1 = Curve(20, [99.0] * 31, [95.0] * 31, [100] * 31)
    h264 = Curve(15, [99.0] * 26, [95.0] * 26, [100] * 26)
    with pytest.raises(ValueError):  # noqa: PT011
        plan_clip(av1, h264, relaxation=bad)
    assert av1.calls == [] and h264.calls == []


@pytest.mark.req("FR-006-04")
@pytest.mark.parametrize("kind", ["shorter-duration", "crop"])
def test_shorter_duration_and_crop_keep_the_93_85_targets(kind):
    n1, n2 = 31, 26
    av1 = Curve(20, [100.0 - 0.5 * i for i in range(n1)], [95.0] * n1, [900_000 - 10_000 * i for i in range(n1)])
    h264 = Curve(15, [100.0 - 0.4 * i for i in range(n2)], [95.0] * n2, [700_000 - 10_000 * i for i in range(n2)])
    relax = {"kind": kind, "reason": "clip shortened to the first ten seconds"}
    plan = plan_clip(av1, h264, relaxation=relax)
    assert plan.av1.chosen_cq == 34 and plan.relaxation == relax  # same targets as without a relaxation


@pytest.mark.req("FR-006-02")
@pytest.mark.req("FR-006-04")
def test_h264_range_above_51_is_rejected():
    av1 = Curve(20, [99.0] * 31, [95.0] * 31, [100] * 31)
    h264 = Curve(15, [99.0] * 40, [95.0] * 40, [100] * 40)
    with pytest.raises(ValueError):  # noqa: PT011
        plan_clip(av1, h264, h264_range=(15, 54))
    assert av1.calls == [] and h264.calls == []


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-03: poster
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-03")
@pytest.mark.parametrize(
    ("size_at", "expected"),
    [
        (lambda q: 2000 * q, 75),  # hand calculation: 2000 q <= 150,000 -> q <= 75
        (lambda q: 2000 * q + 1, 74),  # 2000 * 75 + 1 = 150,001 > 150,000
        (lambda q: 1000, 90),  # everything fits: the top of the range
        (lambda q: 150_000 if q <= 50 else 150_001, 50),  # only the lowest quality fits (<= is inclusive)
    ],
)
def test_poster_quality_is_the_largest_in_50_90_that_fits_150000_bytes(size_at, expected):
    assert choose_poster_quality(size_at) == expected


@pytest.mark.req("FR-006-03")
def test_poster_that_does_not_fit_at_quality_50_is_over_budget():
    with pytest.raises(OverBudget) as ei:
        choose_poster_quality(lambda q: 150_001 + q)
    assert ei.value.error_class == "over-budget"


@pytest.mark.req("FR-006-03")
@SETTINGS
@given(st.lists(st.integers(1, 400_000), min_size=41, max_size=41))
def test_poster_quality_equals_brute_force_on_monotone_size_curves(raw):
    sizes = sorted(raw)  # bytes grow with quality
    fits = [q for q in range(50, 91) if sizes[q - 50] <= 150_000]
    if not fits:
        with pytest.raises(OverBudget):
            choose_poster_quality(lambda q: sizes[q - 50])
    else:
        assert choose_poster_quality(lambda q: sizes[q - 50]) == max(fits)
