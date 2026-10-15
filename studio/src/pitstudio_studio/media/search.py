"""VMAF-targeted constant-quality search (FR-006-02 to FR-006-04) and the libvmaf log reader.

The search variable is the NVENC constant-quality value (`-cq`): a larger value is a lower quality and a smaller
file. The search is a bisection for the largest value whose measured VMAF mean and 5th percentile meet the
targets, followed by one re-measure of the chosen value; a setting is never reported on the strength of an
inference.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .errors import OverBudget, VmafUnreachable
from .vmaf import aggregate_vmaf as aggregate_vmaf  # re-exported: the search and its aggregation are one API
from .vmaf import parse_vmaf_log as parse_vmaf_log

VMAF_MEAN_MIN = 93.0
VMAF_P5_MIN = 85.0
RELAXED_MEAN_FLOOR = 80.0
PAIR_BYTES_MAX = 25_000_000
POSTER_BYTES_MAX = 150_000
POSTER_QUALITY_RANGE = (50, 90)
H264_CQ_MAX = 51
CQ_MAX = 63
RELAXATION_KINDS = ("lower-target", "shorter-duration", "crop")


@dataclass(frozen=True)
class Measurement:
    vmaf_mean: float
    vmaf_p5: float
    bytes: int


@dataclass(frozen=True)
class Trial:
    cq: int
    vmaf_mean: float
    vmaf_p5: float
    bytes: int


@dataclass(frozen=True)
class VariantResult:
    chosen_cq: int
    trials: tuple[Trial, ...]
    final: Measurement


@dataclass(frozen=True)
class ClipSearch:
    av1: VariantResult
    h264: VariantResult
    pair_bytes: int
    relaxation: dict | None


# ---------------------------------------------------------------------------------------------------------------------
# the search
# ---------------------------------------------------------------------------------------------------------------------
def _check_range(cq_range: tuple[int, int], top: int = CQ_MAX) -> tuple[int, int]:
    try:
        lo, hi = cq_range
    except TypeError, ValueError:
        raise ValueError("the constant-quality range must be a pair (lo, hi)") from None
    for v in (lo, hi):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("the constant-quality range holds integers")
    if not 1 <= lo <= hi <= top:
        raise ValueError(f"the constant-quality range must satisfy 1 <= lo <= hi <= {top}, got ({lo}, {hi})")
    return lo, hi


def search_variant(
    measure: Callable[[int], Measurement],
    cq_range: tuple[int, int],
    *,
    vmaf_mean_min: float = VMAF_MEAN_MIN,
    vmaf_p5_min: float = VMAF_P5_MIN,
    max_trials: int = 8,
) -> VariantResult:
    """Bisection for the largest `cq` in `cq_range` that meets both targets, then a re-measure of that value."""
    lo, hi = _check_range(cq_range)

    def meets(m: Measurement) -> bool:
        return m.vmaf_mean >= vmaf_mean_min and m.vmaf_p5 >= vmaf_p5_min

    trials: list[Trial] = []
    chosen: int | None = None
    a, b = lo, hi
    while a <= b and len(trials) < max_trials:
        mid = (a + b) // 2
        m = measure(mid)
        trials.append(Trial(mid, m.vmaf_mean, m.vmaf_p5, m.bytes))
        if meets(m):
            chosen, a = mid, mid + 1
        else:
            b = mid - 1
    best = min(trials, key=lambda t: (-t.vmaf_mean, t.cq)) if trials else None
    if chosen is None:
        assert best is not None
        raise VmafUnreachable(
            f"no setting in {lo}..{hi} reaches VMAF mean {vmaf_mean_min} and p5 {vmaf_p5_min}; best cq {best.cq} "
            f"(mean {best.vmaf_mean:.2f}, p5 {best.vmaf_p5:.2f}, {best.bytes} bytes)",
            best=best,
        )
    final = measure(chosen)
    if not meets(final):
        raise VmafUnreachable(
            f"the re-measure of cq {chosen} misses the targets (mean {final.vmaf_mean:.2f}, p5 {final.vmaf_p5:.2f})",
            best=best,
        )
    return VariantResult(chosen, tuple(trials), final)


def check_pair_budget(av1_bytes: int, h264_bytes: int, *, max_bytes: int = PAIR_BYTES_MAX) -> int:
    total = av1_bytes + h264_bytes
    if total > max_bytes:
        raise OverBudget(f"the clip pair is {total} bytes, the budget is {max_bytes}", best=(av1_bytes, h264_bytes))
    return total


def choose_poster_quality(
    size_at: Callable[[int], int],
    *,
    max_bytes: int = POSTER_BYTES_MAX,
    quality_range: tuple[int, int] = POSTER_QUALITY_RANGE,
) -> int:
    """The largest WebP quality in `quality_range` whose size fits `max_bytes` (bisection, sizes grow with quality)."""
    lo, hi = quality_range
    chosen: int | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if size_at(mid) <= max_bytes:
            chosen, lo = mid, mid + 1
        else:
            hi = mid - 1
    if chosen is None:
        raise OverBudget(f"the poster does not fit {max_bytes} bytes even at quality {quality_range[0]}")
    return chosen


# ---------------------------------------------------------------------------------------------------------------------
# the clip: two variants, the pair budget and the declared relaxation
# ---------------------------------------------------------------------------------------------------------------------
def _number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_relaxation(relaxation: dict | None) -> tuple[float, float]:
    """Check a recipe relaxation and return the (mean, p5) targets that apply."""
    if relaxation is None:
        return VMAF_MEAN_MIN, VMAF_P5_MIN
    if not isinstance(relaxation, dict):
        raise ValueError("a relaxation is a mapping")
    kind, reason = relaxation.get("kind"), relaxation.get("reason")
    if kind not in RELAXATION_KINDS:
        raise ValueError(f"unknown relaxation kind {kind!r}")
    if not isinstance(reason, str) or not 10 <= len(reason) <= 300:
        raise ValueError("a relaxation needs a written reason of 10 to 300 characters")
    if kind != "lower-target":
        if "vmaf_mean_min" in relaxation or "vmaf_p5_min" in relaxation:
            raise ValueError(f"a {kind} relaxation keeps the 93/85 targets and carries no target values")
        return VMAF_MEAN_MIN, VMAF_P5_MIN
    mean_min, p5_min = relaxation.get("vmaf_mean_min"), relaxation.get("vmaf_p5_min")
    if not (_number(mean_min) and RELAXED_MEAN_FLOOR <= mean_min < VMAF_MEAN_MIN):
        raise ValueError(f"a lower-target relaxation needs vmaf_mean_min in [{RELAXED_MEAN_FLOOR}, {VMAF_MEAN_MIN})")
    if not (_number(p5_min) and 0 <= p5_min <= VMAF_P5_MIN):
        raise ValueError(f"a lower-target relaxation needs vmaf_p5_min in [0, {VMAF_P5_MIN}]")
    return float(mean_min), float(p5_min)


def plan_clip(
    measure_av1: Callable[[int], Measurement],
    measure_h264: Callable[[int], Measurement],
    *,
    av1_range: tuple[int, int] = (20, 50),
    h264_range: tuple[int, int] = (15, 40),
    relaxation: dict | None = None,
) -> ClipSearch:
    mean_min, p5_min = validate_relaxation(relaxation)
    _check_range(av1_range)
    _check_range(h264_range, H264_CQ_MAX)
    av1 = search_variant(measure_av1, av1_range, vmaf_mean_min=mean_min, vmaf_p5_min=p5_min)
    h264 = search_variant(measure_h264, h264_range, vmaf_mean_min=mean_min, vmaf_p5_min=p5_min)
    try:
        total = check_pair_budget(av1.final.bytes, h264.final.bytes)
    except OverBudget as e:
        best = (
            Trial(av1.chosen_cq, av1.final.vmaf_mean, av1.final.vmaf_p5, av1.final.bytes),
            Trial(h264.chosen_cq, h264.final.vmaf_mean, h264.final.vmaf_p5, h264.final.bytes),
        )
        raise OverBudget(e.detail, best=best) from None
    return ClipSearch(av1, h264, total, relaxation)
