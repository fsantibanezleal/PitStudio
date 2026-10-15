"""Task-B plausibility pairs: the six corruption detectors, pair confirmation and pair-set builder (FR-015-33 to 35).

A simulation state is a dict: `pos` (frames, particles, 3) metres, Z up; `fps`; `radius` (particles,); `mass` (frames,
particles) kg, 0 meaning absent; `frame_order` (frames,) the source frame shown at each output frame (identity unless
time was reversed); `observables["repose_angle_deg"]` (the spec 005 measurement) and `inflow_boundary`.

Each detector reads only the simulation state and is invariant under a permutation of the particle ids:

| corruption | statistic | triggered when |
|---|---|---|
| gravity-x0.3 | `fitted_g_ratio` | the free-fall acceleration is within +-5 % of 0.3 g |
| zero-friction | `repose_angle_deg` | the repose angle is below 5 degrees |
| mass-injection | `mass_increase_pct` | total mass grew by 5 % or more and there is no inflow boundary |
| time-reversal | `reversed_frame_fraction` | the frame order is exactly reversed |
| interpenetration | `deep_overlap_contact_fraction` | 10 % of contacts overlap by over half the radius sum for 1 s |
| frozen-particles | `frozen_particle_fraction` | 5 % of the particles stay put for 1 s while a neighbour moves |

The free-fall acceleration is the median downward acceleration of short quadratic fits (about 0.2 s windows) that are
clean (small residual) and clearly accelerating (at least 0.1 g): particles at rest, sliding steadily or colliding do
not enter. Durations are the time spanned by the frames of a run, (frames - 1) / fps.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from pitstudio.reason import _schemas

G0 = 9.80665  # standard acceleration of gravity, m/s^2
CORRUPTIONS = (
    "gravity-x0.3",
    "zero-friction",
    "mass-injection",
    "time-reversal",
    "interpenetration",
    "frozen-particles",
)
STATISTICS = {
    "gravity-x0.3": "fitted_g_ratio",
    "zero-friction": "repose_angle_deg",
    "mass-injection": "mass_increase_pct",
    "time-reversal": "reversed_frame_fraction",
    "interpenetration": "deep_overlap_contact_fraction",
    "frozen-particles": "frozen_particle_fraction",
}
GRAVITY_RATIO = 0.3
GRAVITY_TOLERANCE = 0.05  # relative, of 0.3 g
REPOSE_MAX_DEG = 5.0
MASS_INCREASE_PCT = 5.0
DEEP_OVERLAP = 0.5  # of the radius sum
DEEP_CONTACT_FRACTION = 0.10
FROZEN_FRACTION = 0.05
SUSTAIN_S = 1.0
WINDOW_S = 0.2
MIN_FIT_ACCEL = 0.1  # of g: slower windows are rest or steady sliding, not free fall
FIT_RESIDUAL = 0.25  # of the particle radius
STILL_EPS = 1e-4  # of the radius, per frame: "zero displacement"
MOVE_EPS = 1e-2  # of the radius, over the run: a neighbour "moves"
PAIRS = 100
PER_CORRUPTION = (16, 17)
MAX_ATTEMPTS = 50
SCHEMA = "plausibility-pairs.schema.json"
SCHEMA_VERSION = "1.0"
_EPS = 1e-9


# ----------------------------------------------------------------------------------------------------- the state
def _check_sim(sim: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Validated (pos, radius, present mask, fps) of a simulation state."""
    try:
        pos = np.asarray(sim["pos"], dtype=float)
        radius = np.asarray(sim["radius"], dtype=float)
        mass = np.asarray(sim["mass"], dtype=float)
        fps = float(sim["fps"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"simulation state is incomplete: {exc!r}") from exc
    if pos.ndim != 3 or pos.shape[2] != 3 or pos.shape[0] < 1 or pos.shape[1] < 1:
        raise ValueError("pos must have shape (frames, particles, 3)")
    if radius.shape != (pos.shape[1],) or mass.shape != pos.shape[:2]:
        raise ValueError("radius must be (particles,) and mass (frames, particles)")
    if not (np.isfinite(pos).all() and np.isfinite(mass).all() and (mass >= 0).all()):
        raise ValueError("pos and mass must be finite and mass non-negative")
    if not (np.isfinite(radius).all() and (radius > 0).all() and math.isfinite(fps) and fps > 0):
        raise ValueError("radius and fps must be finite and positive")
    return pos, radius, mass > 0, fps


# ------------------------------------------------------------------------------------------- neighbour search
def neighbour_pairs(points: np.ndarray, cutoff: float) -> tuple[np.ndarray, np.ndarray]:
    """Index pairs (i < j) of points at distance <= cutoff, by a uniform grid of cell size `cutoff` (NumPy only)."""
    n = len(points)
    if n < 2:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    cell = np.floor(points / cutoff).astype(np.int64)
    cell -= cell.min(axis=0)
    dims = cell.max(axis=0) + 3
    if float(dims[0]) * float(dims[1]) * float(dims[2]) > 2.0**62:
        raise ValueError("the particle domain is too large for the neighbour grid")
    key = ((cell[:, 0] + 1) * dims[1] + (cell[:, 1] + 1)) * dims[2] + (cell[:, 2] + 1)
    order = np.argsort(key, kind="stable")
    sorted_key = key[order]
    out_i, out_j = [], []
    for dx, dy, dz in itertools.product((-1, 0, 1), repeat=3):
        shifted = key + (dx * dims[1] + dy) * dims[2] + dz
        lo = np.searchsorted(sorted_key, shifted, side="left")
        hi = np.searchsorted(sorted_key, shifted, side="right")
        count = hi - lo
        total = int(count.sum())
        if total == 0:
            continue
        i = np.repeat(np.arange(n), count)
        offset = np.arange(total) - np.repeat(np.cumsum(count) - count, count)
        j = order[np.repeat(lo, count) + offset]
        keep = i < j
        i, j = i[keep], j[keep]
        close = np.linalg.norm(points[i] - points[j], axis=1) <= cutoff
        out_i.append(i[close])
        out_j.append(j[close])
    if not out_i:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    return np.concatenate(out_i), np.concatenate(out_j)


# ------------------------------------------------------------------------------------------------- statistics
def _fitted_g_ratio(pos: np.ndarray, radius: np.ndarray, present: np.ndarray, fps: float) -> float:
    frames = pos.shape[0]
    w = max(5, round(WINDOW_S * fps))
    if frames < w:
        return 0.0
    t = (np.arange(w) - (w - 1) / 2) / fps
    design = np.vander(t, 3)  # columns t^2, t, 1
    pinv = np.linalg.pinv(design)
    accel_all = []
    for start in range(0, frames - w + 1, max(1, w // 2)):
        z = pos[start : start + w, :, 2]  # (w, particles)
        coef = pinv @ z
        rms = np.sqrt(((z - design @ coef) ** 2).mean(axis=0))
        accel = -2.0 * coef[0]
        ok = present[start : start + w].all(axis=0) & (rms <= FIT_RESIDUAL * radius) & (accel >= MIN_FIT_ACCEL * G0)
        accel_all.append(accel[ok])
    accel_ok = np.concatenate(accel_all)
    return float(np.median(accel_ok) / G0) if accel_ok.size else 0.0


def _mass_increase_pct(mass: np.ndarray) -> float:
    total = mass.sum(axis=1)
    if total[0] <= 0:
        return 0.0
    return float(100.0 * (total.max() - total[0]) / total[0])


def _reversed_fraction(frame_order: np.ndarray) -> tuple[float, bool]:
    order = np.asarray(frame_order)
    if order.ndim != 1 or order.size < 2:
        return 0.0, False
    exact = bool(np.array_equal(order, np.arange(order.size)[::-1]))
    return float((np.diff(order) == -1).mean()), exact


def _longest_runs(flags: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Longest run of True per column of a (steps, columns) boolean matrix, and the step at which it ends."""
    cur = np.zeros(flags.shape[1], dtype=np.int64)
    best = np.zeros_like(cur)
    end = np.zeros_like(cur)
    for step in range(flags.shape[0]):
        cur = (cur + 1) * flags[step]
        better = cur > best
        best = np.where(better, cur, best)
        end = np.where(better, step, end)
    return best, end


def _deep_overlap(pos: np.ndarray, radius: np.ndarray, present: np.ndarray, fps: float) -> tuple[float, float]:
    """(fraction of contacts deeper than half the radius sum for >= 1 s, longest deep run in seconds)."""
    frames, n, _ = pos.shape
    rmax2 = 2.0 * float(radius.max())
    keys, deep_by_frame = [], []
    for f in range(frames):
        ids = np.flatnonzero(present[f])
        i, j = neighbour_pairs(pos[f, ids], rmax2)
        i, j = ids[i], ids[j]
        rsum = radius[i] + radius[j]
        dist = np.linalg.norm(pos[f, i] - pos[f, j], axis=1)
        touching = dist <= rsum * (1.0 + _EPS)
        i, j, rsum, dist = i[touching], j[touching], rsum[touching], dist[touching]
        keys.append(i.astype(np.int64) * n + j)
        deep_by_frame.append((rsum - dist) / rsum > DEEP_OVERLAP)
    all_keys = np.unique(np.concatenate(keys))
    if all_keys.size == 0:
        return 0.0, 0.0
    deep = np.zeros((frames, all_keys.size), dtype=bool)
    for f in range(frames):
        deep[f, np.searchsorted(all_keys, keys[f][deep_by_frame[f]])] = True
    best, _ = _longest_runs(deep)
    duration = np.maximum(best - 1, 0) / fps
    sustained = duration >= SUSTAIN_S - _EPS
    return float(sustained.sum() / all_keys.size), float(duration.max())


def _frozen(pos: np.ndarray, radius: np.ndarray, present: np.ndarray, fps: float) -> tuple[float, float]:
    """(fraction of particles still for >= 1 s while a neighbour within two radii moves, longest run in s)."""
    frames, n, _ = pos.shape
    if frames < 2:
        return 0.0, 0.0
    step = np.linalg.norm(pos[1:] - pos[:-1], axis=2)
    still = (step <= STILL_EPS * radius[None, :]) & present[1:] & present[:-1]
    best, end = _longest_runs(still)
    candidates = np.flatnonzero(best / fps >= SUSTAIN_S - _EPS)
    frozen: list[float] = []
    by_start: dict[int, list[int]] = {}
    for i in candidates:
        by_start.setdefault(int(end[i] - best[i] + 1), []).append(int(i))
    for start, members in by_start.items():
        ids = np.flatnonzero(present[start])
        a, b = neighbour_pairs(pos[start, ids], 2.0 * float(radius.max()))
        a, b = ids[a], ids[b]
        close = np.linalg.norm(pos[start, a] - pos[start, b], axis=1) <= 2.0 * np.maximum(radius[a], radius[b])
        a, b = a[close], b[close]
        neighbours: dict[int, list[int]] = {m: [] for m in members}
        for x, y in zip(a.tolist(), b.tolist(), strict=True):
            if x in neighbours:
                neighbours[x].append(y)
            if y in neighbours:
                neighbours[y].append(x)
        for m in members:
            stop = int(end[m] + 1)
            window = slice(start, stop + 1)
            for j in neighbours[m]:
                moved = np.linalg.norm(pos[window, j] - pos[start, j], axis=1).max()
                if moved > MOVE_EPS * radius[j]:
                    frozen.append(float(best[m] / fps))
                    break
    return len(frozen) / n, max(frozen, default=0.0)


def detect(sim: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Run the six detectors: `{corruption: {"triggered", "statistic", "value", "sustained_s"}}`."""
    pos, radius, present, fps = _check_sim(sim)
    mass = np.asarray(sim["mass"], dtype=float)
    ratio = _fitted_g_ratio(pos, radius, present, fps)
    try:
        repose = float(sim["observables"]["repose_angle_deg"])
    except KeyError, TypeError, ValueError:
        repose = math.nan
    mass_pct = _mass_increase_pct(mass)
    rev_fraction, rev_exact = _reversed_fraction(np.asarray(sim["frame_order"]))
    deep_fraction, deep_s = _deep_overlap(pos, radius, present, fps)
    frozen_fraction, frozen_s = _frozen(pos, radius, present, fps)

    def entry(name: str, value: float, triggered: bool, sustained: float | None = None) -> dict[str, Any]:
        return {
            "triggered": bool(triggered),
            "statistic": STATISTICS[name],
            "value": float(value),
            "sustained_s": sustained,
        }

    return {
        "gravity-x0.3": entry(
            "gravity-x0.3", ratio, abs(ratio - GRAVITY_RATIO) <= GRAVITY_TOLERANCE * GRAVITY_RATIO + _EPS
        ),
        "zero-friction": entry("zero-friction", repose, math.isfinite(repose) and repose < REPOSE_MAX_DEG),
        "mass-injection": entry(
            "mass-injection", mass_pct, mass_pct >= MASS_INCREASE_PCT and not bool(sim.get("inflow_boundary", False))
        ),
        "time-reversal": entry("time-reversal", rev_fraction, rev_exact),
        "interpenetration": entry(
            "interpenetration", deep_fraction, deep_fraction >= DEEP_CONTACT_FRACTION - _EPS, deep_s
        ),
        "frozen-particles": entry(
            "frozen-particles", frozen_fraction, frozen_fraction >= FROZEN_FRACTION - _EPS, frozen_s
        ),
    }


# ---------------------------------------------------------------------------------------------------- corruptions
def reverse_time(sim: Mapping[str, Any]) -> dict[str, Any]:
    """The same run played backwards: frames, masses and `frame_order` reversed (an involution)."""
    out = dict(sim)
    out["pos"] = np.asarray(sim["pos"])[::-1].copy()
    out["mass"] = np.asarray(sim["mass"])[::-1].copy()
    out["frame_order"] = np.asarray(sim["frame_order"])[::-1].copy()
    return out


def make_corrupted(
    simulate: Callable[..., dict[str, Any]], initial: Any, corruption: str, *, scale: float | None = None
) -> dict[str, Any]:
    """The corrupted run for the corruptions that need no physics-runner option beyond gravity.

    "gravity-x0.3": `simulate(initial, gravity_scale=scale)` (default 0.3; scale 1.0 is the identity and reproduces the
    calibrated run bit-exactly in deterministic mode); "time-reversal": the calibrated run reversed.
    """
    if corruption == "gravity-x0.3":
        return simulate(initial, gravity_scale=GRAVITY_RATIO if scale is None else scale)
    if corruption == "time-reversal":
        return reverse_time(simulate(initial, gravity_scale=1.0))
    raise ValueError(f"cannot build corruption {corruption!r} from a gravity scale; known: gravity-x0.3, time-reversal")


def confirm_pair(calibrated: Mapping[str, Any], corrupted: Mapping[str, Any], corruption: str) -> dict[str, Any]:
    """The pair `confirmation` object: the statistic of the corruption's own detector on the corrupted state, whether it
    fired, and whether none of the six detectors fires on the calibrated state."""
    if corruption not in CORRUPTIONS:
        raise ValueError(f"unknown corruption {corruption!r}")
    own = detect(corrupted)[corruption]
    clear = not any(d["triggered"] for d in detect(calibrated).values())
    return {
        "statistic": own["statistic"],
        "value": own["value"],
        "sustained_s": own["sustained_s"],
        "own_detector_triggered": own["triggered"],
        "calibrated_detectors_clear": clear,
    }


# --------------------------------------------------------------------------------------------------- the pair set
def check_pair(pair: Any) -> list[str]:
    """Reasons a pair document is not acceptable (empty: acceptable): schema violations, anything but exactly one
    corruption, a failed confirmation, clips that differ in scene, camera, duration or frame count."""
    if not isinstance(pair, Mapping):
        return ["pair is not an object"]
    reasons = [f"{_schemas.pointer(e)}: {e.message[:160]}" for e in _schemas.errors(pair, SCHEMA, "#/$defs/pair")[:8]]
    corruptions = pair.get("corruptions")
    if isinstance(corruptions, list) and len(corruptions) != 1:
        reasons.append(f"a pair declares exactly one corruption, found {len(corruptions)}")
    conf = pair.get("confirmation")
    if isinstance(conf, Mapping):
        if conf.get("own_detector_triggered") is not True:
            reasons.append("the detector of the corruption was not triggered on the corrupted clip")
        if conf.get("calibrated_detectors_clear") is not True:
            reasons.append("a detector fired on the calibrated clip")
    cal, cor = pair.get("calibrated"), pair.get("corrupted")
    if isinstance(cal, Mapping) and isinstance(cor, Mapping):
        reasons.extend(
            f"the clips differ in {key}: {cal.get(key)!r} and {cor.get(key)!r}"
            for key in ("scene_id", "camera_id", "duration_s", "frame_count", "fps")
            if cal.get(key) != cor.get(key)
        )
    return list(dict.fromkeys(reasons))


@dataclass
class PairSet:
    pairs: list[dict[str, Any]]
    excluded: list[tuple[str, list[str]]] = field(default_factory=list)
    seed: int = 0

    def to_document(self) -> dict[str, Any]:
        """The `plausibility-pairs` document (DC-015-06)."""
        return {"schema_version": SCHEMA_VERSION, "seed": self.seed, "pairs": list(self.pairs)}


def _slot_corruption(pair: Mapping[str, Any]) -> str:
    declared = pair.get("corruptions")
    if isinstance(declared, list):
        for name in declared:
            if name in CORRUPTIONS:
                return str(name)
    raise ValueError(f"pair {pair.get('pair_id')!r} declares no known corruption: its slot cannot be regenerated")


def build_pair_set(
    candidates: Sequence[Mapping[str, Any]],
    *,
    regenerate: Callable[[str, int], Mapping[str, Any]],
    seed: int = 0,
) -> PairSet:
    """Accept the acceptable candidates and replace every other one, in place, by a regenerated pair of the same
    corruption (`regenerate(corruption, attempt)`, attempt counting from 1 for each excluded slot).

    The result holds exactly 100 pairs, 16 or 17 per corruption and unique pair ids; anything else is a ValueError.
    """
    if len(candidates) != PAIRS:
        raise ValueError(f"the pair set holds {PAIRS} pairs, got {len(candidates)} candidates")
    pairs: list[dict[str, Any]] = []
    excluded: list[tuple[str, list[str]]] = []
    for cand in candidates:
        reasons = check_pair(cand)
        if not reasons:
            pairs.append(dict(cand))
            continue
        excluded.append((str(cand.get("pair_id")), reasons))
        slot = _slot_corruption(cand)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            new = dict(regenerate(slot, attempt))
            problems = check_pair(new)
            if not problems and new.get("corruptions") != [slot]:
                problems = [f"the regenerated pair is not of corruption {slot!r}"]
            if not problems:
                pairs.append(new)
                break
            excluded.append((str(new.get("pair_id")), problems))
        else:
            raise ValueError(f"no acceptable pair of corruption {slot!r} after {MAX_ATTEMPTS} attempts")
    ids = [p["pair_id"] for p in pairs]
    if len(set(ids)) != len(ids):
        raise ValueError("pair ids are not unique")
    counts = {c: sum(1 for p in pairs if p["corruptions"] == [c]) for c in CORRUPTIONS}
    if any(v not in PER_CORRUPTION for v in counts.values()):
        raise ValueError(f"each corruption needs 16 or 17 pairs, found {counts}")
    return PairSet(pairs, excluded, seed)
