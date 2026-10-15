# SPDX-License-Identifier: Apache-2.0
"""Classical baselines of the IL tasks: pure pursuit + PID (IL-1) and the scripted dig (IL-2).

FR-014-29 to FR-014-31, P-014-07. Pure pursuit follows Coulter (1992), CMU-RI-TR-92-01, eqs. 2.1-2.2: the curvature
toward a goal point is 2 x / l^2, with x the lateral offset of the goal in the vehicle frame and l the look-ahead.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import numpy as np

from pitstudio.robots._check import finite, positive

__all__ = [
    "PHASES",
    "FrozenParams",
    "PidSpeed",
    "PurePursuitPid",
    "ScriptedDig",
    "TuneResult",
    "check_seed_blocks",
    "curvature",
    "freeze_params",
    "lookahead_distance",
    "pure_pursuit_goal",
    "steering_angle",
    "tune_scripted_dig",
    "verify_frozen",
]


def lookahead_distance(speed: float, *, l0: float, kv: float, l_min: float, l_max: float) -> float:
    """l = clamp(l0 + kv * speed, l_min, l_max)."""
    return min(max(l0 + kv * speed, l_min), l_max)


def _path(path: np.ndarray | None) -> np.ndarray:
    try:
        arr = np.array(path, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"path must be a numeric (N >= 2, 2) array, got {type(path).__name__}") from exc
    if arr.ndim != 2 or arr.shape[1] != 2 or arr.shape[0] < 2:
        raise ValueError(f"path must have shape (N >= 2, 2), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("path holds a non-finite coordinate")
    return arr


def pure_pursuit_goal(path: np.ndarray, lookahead: float) -> np.ndarray:
    """First point of the polyline (vehicle frame) at distance ``lookahead`` from the origin, else the path end."""
    pts = _path(path)
    end = pts[-1].copy()
    if not math.isfinite(lookahead) or lookahead <= 0.0:
        return end
    if float(np.hypot(*pts[0])) >= lookahead:
        return pts[0].copy()
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if float(np.hypot(*b)) < lookahead:
            continue
        d = b - a
        # |a + t d|^2 = lookahead^2 with |a| < lookahead <= |b|: the root t in (0, 1]
        qa = float(np.dot(d, d))
        qb = 2.0 * float(np.dot(a, d))
        qc = float(np.dot(a, a)) - lookahead * lookahead
        disc = max(qb * qb - 4.0 * qa * qc, 0.0)
        t = (-qb + math.sqrt(disc)) / (2.0 * qa)
        return a + min(max(t, 0.0), 1.0) * d
    return end


def curvature(lateral_offset: float, lookahead: float) -> float:
    """kappa = 2 x / l^2."""
    la = positive("lookahead", lookahead)
    return 2.0 * lateral_offset / (la * la)


def steering_angle(kappa: float, wheelbase: float) -> float:
    """delta = arctan(L kappa)."""
    return math.atan(positive("wheelbase", wheelbase) * kappa)


class PidSpeed:
    """Discrete PID (kd = 0) with output clamping and conditional-integration anti-windup."""

    def __init__(self, kp: float, ki: float, dt: float, out_min: float = -1.0, out_max: float = 1.0) -> None:
        self.kp = finite("kp", kp)
        self.ki = finite("ki", ki)
        self.dt = positive("dt", dt)
        self.out_min = finite("out_min", out_min)
        self.out_max = finite("out_max", out_max)
        if self.out_min >= self.out_max:
            raise ValueError(f"out_min must be < out_max, got {out_min!r} and {out_max!r}")
        self.integral = 0.0

    def reset(self) -> None:
        self.integral = 0.0

    def step(self, error: float) -> float:
        e = finite("error", error)
        previous = self.integral
        self.integral += e * self.dt
        raw = self.kp * e + self.ki * self.integral
        if (raw > self.out_max and e > 0.0) or (raw < self.out_min and e < 0.0):
            self.integral = previous  # saturated in the direction of the error: do not wind up
        return min(max(raw, self.out_min), self.out_max)


class PurePursuitPid:
    """IL-1 baseline: pure-pursuit steering and PID speed control, through the policy's action limits."""

    def __init__(
        self,
        *,
        wheelbase: float,
        l0: float,
        kv: float,
        l_min: float,
        l_max: float,
        kp: float,
        ki: float,
        dt: float,
        max_steer_rate: float,
    ) -> None:
        self.wheelbase = positive("wheelbase", wheelbase)
        self.l0, self.kv = finite("l0", l0), finite("kv", kv)
        self.l_min, self.l_max = finite("l_min", l_min), finite("l_max", l_max)
        self.dt = positive("dt", dt)
        self.max_steer_rate = positive("max_steer_rate", max_steer_rate)
        self.pid = PidSpeed(kp, ki, dt)

    def reset(self) -> None:
        self.pid.reset()

    def act(self, path: np.ndarray, speed: float, v_target: float, steer_angle: float) -> np.ndarray:
        v = finite("speed", speed)
        v_ref = finite("v_target", v_target)
        steer = finite("steer_angle", steer_angle)
        pts = _path(path)
        la = lookahead_distance(v, l0=self.l0, kv=self.kv, l_min=self.l_min, l_max=self.l_max)
        goal = pure_pursuit_goal(pts, la)
        delta_cmd = steering_angle(curvature(float(goal[1]), la), self.wheelbase)
        steer_action = (delta_cmd - steer) / (self.dt * self.max_steer_rate)
        drive_action = self.pid.step(v_ref - v)
        return np.clip(np.array([steer_action, drive_action]), -1.0, 1.0)


# ---------------------------------------------------------------------------------------------- scripted dig
PHASES = ("penetrate", "drag", "curl", "lift")
TUNE_COUNT = 20
EVAL_COUNT = 100
_SEED_KEYS = ("train", "tune", "eval")


def _seed_range(seeds: Mapping[str, Any], key: str, required: bool) -> tuple[int, int] | None:
    block = seeds.get(key) if isinstance(seeds, Mapping) else None
    if block is None:
        if required:
            raise ValueError(f"seeds lack the {key!r} block")
        return None
    try:
        start, count = int(block["start"]), int(block["count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"seeds {key!r} needs integer start and count") from exc
    if start < 0 or count < 1:
        raise ValueError(f"seeds {key!r}: start must be >= 0 and count >= 1")
    return start, start + count


def check_seed_blocks(seeds: Mapping[str, Any]) -> None:
    """The tune block holds 20 seeds, the eval block 100, and no two blocks share a seed (end exclusive)."""
    ranges = {key: _seed_range(seeds, key, required=key != "train") for key in _SEED_KEYS}
    for key, want in (("tune", TUNE_COUNT), ("eval", EVAL_COUNT)):
        lo, hi = ranges[key]  # type: ignore[misc]
        if hi - lo != want:
            raise ValueError(f"seeds {key!r} must hold exactly {want} seeds, got {hi - lo}")
    present = [(key, rng) for key, rng in ranges.items() if rng is not None]
    for i, (ka, (alo, ahi)) in enumerate(present):
        for kb, (blo, bhi) in present[i + 1 :]:
            if alo < bhi and blo < ahi:
                raise ValueError(f"seed ranges {ka!r} and {kb!r} overlap")


def _canonical(params: Mapping[str, Any]) -> str:
    return json.dumps(dict(params), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(params: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(params).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FrozenParams:
    params: Mapping[str, Any]
    sha256: str


def freeze_params(params: Mapping[str, Any]) -> FrozenParams:
    """A read-only deep copy of the parameters with the SHA-256 of their canonical JSON."""
    for key, value in params.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"parameter {key!r} is not finite")
    copy = json.loads(_canonical(params))
    return FrozenParams(params=MappingProxyType(copy), sha256=_digest(copy))


def verify_frozen(frozen: FrozenParams, params: Mapping[str, Any]) -> None:
    if _digest(params) != frozen.sha256:
        raise ValueError("parameters differ from the frozen set: sha256 mismatch")


@dataclass(frozen=True)
class TuneResult:
    frozen: FrozenParams
    mean_score: float
    scores: list[float]
    seeds_used: list[int]


def tune_scripted_dig(
    candidates: Sequence[Mapping[str, Any]],
    run_episode: Callable[[Mapping[str, Any], int], float],
    seeds: Mapping[str, Any],
) -> TuneResult:
    """Tune once on the 20 tune seeds (one run per candidate and seed) and freeze the best mean score."""
    check_seed_blocks(seeds)
    if not candidates:
        raise ValueError("candidates must be a non-empty list")
    start, end = _seed_range(seeds, "tune", True)  # type: ignore[misc]
    tune_seeds = list(range(start, end))
    scores: list[float] = []
    for cand in candidates:
        total = 0.0
        for seed in tune_seeds:
            score = float(run_episode(cand, seed))
            if not math.isfinite(score):
                raise ValueError(f"episode score is not finite for seed {seed}")
            total += score
        scores.append(total / len(tune_seeds))
    best = 0
    for i, mean in enumerate(scores):
        if mean > scores[best]:
            best = i
    return TuneResult(freeze_params(candidates[best]), scores[best], scores, tune_seeds)


class ScriptedDig:
    """Joint-space dig on the IL-2 observation: penetrate, drag, curl, lift (FR-014-30).

    Parameters (a frozen set): penetration_m is the depth held while dragging, drag_speed_m_s the stick command (full
    command at 0.5 m/s), curl_rate_rad_s the bucket command (full command at 1.0 rad/s), lift_height_m the clearance
    above the surface that ends the lift, approach_angle_deg the bucket-pitch change that ends the curl. The surface
    under the tip is read from the terrain heights of the observation, so the controller follows the initial terrain
    profile. Joint order: swing, boom, stick, bucket; the swing is never commanded.
    """

    DRAG_REFERENCE_SPEED = 0.5  # m/s of drag that maps to a full stick command
    CURL_REFERENCE_RATE = 1.0  # rad/s of curl that maps to a full bucket command
    FILL_DONE = 0.95  # fill estimate that ends the drag
    DEPTH_GAIN = 2.0  # boom command per metre of depth error
    MAX_DRAG_DISTANCE = 4.0  # m of tip travel that ends the drag

    def __init__(self, frozen: FrozenParams) -> None:
        if not isinstance(frozen, FrozenParams):
            raise TypeError("frozen must be a FrozenParams (tuned once, then frozen)")
        if _digest(frozen.params) != frozen.sha256:
            raise ValueError("frozen parameters no longer match their sha256")
        self.params = frozen.params
        self.reset()

    def reset(self) -> None:
        self.phase = PHASES[0]
        self._drag_start_x: float | None = None
        self._curl_start_pitch: float | None = None

    def act(self, obs: np.ndarray) -> np.ndarray:
        """The four joint-velocity commands in [-1, 1] for the 46-element observation."""
        o = np.asarray(obs, dtype=np.float64)
        if o.shape != (46,) or not np.all(np.isfinite(o)):
            raise ValueError("obs must be a finite vector of 46 values")
        tip_x, tip_z, pitch = float(o[12]), float(o[13]), float(o[14])
        surface = float(o[15])
        fill = float(o[45])
        depth = surface - tip_z
        p = self.params
        cmd = np.zeros(4)
        if self.phase == "penetrate":
            cmd[1] = -1.0
            if depth >= float(p["penetration_m"]):
                self.phase = "drag"
                self._drag_start_x = tip_x
        if self.phase == "drag":
            cmd[1] = float(np.clip(self.DEPTH_GAIN * (float(p["penetration_m"]) - depth), -1.0, 1.0))
            cmd[2] = float(np.clip(float(p["drag_speed_m_s"]) / self.DRAG_REFERENCE_SPEED, 0.0, 1.0))
            start_x = self._drag_start_x if self._drag_start_x is not None else tip_x
            if fill >= self.FILL_DONE or abs(tip_x - start_x) >= self.MAX_DRAG_DISTANCE:
                self.phase = "curl"
                self._curl_start_pitch = pitch
                cmd[:] = 0.0
        if self.phase == "curl":
            cmd[3] = float(np.clip(float(p["curl_rate_rad_s"]) / self.CURL_REFERENCE_RATE, -1.0, 1.0))
            start = self._curl_start_pitch if self._curl_start_pitch is not None else pitch
            if abs(pitch - start) >= math.radians(float(p["approach_angle_deg"])):
                self.phase = "lift"
                cmd[:] = 0.0
        if self.phase == "lift":
            if tip_z - surface >= float(p["lift_height_m"]):
                return np.zeros(4)
            cmd[1] = 1.0
        return cmd
