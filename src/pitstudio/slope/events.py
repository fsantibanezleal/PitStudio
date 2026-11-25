"""Seeded synthetic Voight events, strata and splits (FR-010-11, FR-010-16, FR-010-17), numpy only.

An event is a DC-010-02 ``synthetic-event`` document: a steady phase at the onset velocity (optionally with one
regressive
episode, centred in the steady phase), then the Voight terminal stage d2(Omega)/dt2 = A (dOmega/dt)^alpha integrated in
closed form with A set so that the terminal-stage velocity at its onset equals the onset velocity,
    v(t) = [(alpha - 1) A (t_f - t)]^(-1/(alpha - 1)),
    Omega(t) - Omega(t_on) = C [(t_f - t_on)^p - (t_f - t)^p] / p,  C = [(alpha - 1) A]^(-1/(alpha - 1)), p = (alpha -
    2) / (alpha - 1)
(for alpha = 2: (1/A) ln((t_f - t_on) / (t_f - t))). The record is t_i = t_0 + i (t_f - t_0) / n, i = 0 .. n - 1 with
t_0 = 0
(the failure time itself is not sampled). The line-of-sight displacement is cos(psi) Omega plus white Gaussian noise
of sd
sigma_d = cos(psi) dOmega / SNR_target (dOmega the noise-free displacement from the first to the last sample) and, in
the
atmospheric stratum, an AR(1) term of lag-1 correlation rho and marginal sd sigma_d. Parameters come from
``Generator(PCG64(SeedSequence(seed)))`` in a fixed order (all priors are always drawn, so fixing one parameter never
moves
the others); the noise comes from the spawn-key child ``SeedSequence(seed, spawn_key=(1,))``.
The seeds of the splits are disjoint integer blocks: train, validation, then one block per test stratum.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from itertools import pairwise
from typing import Any

import numpy as np

from pitstudio.slope import snr as _snr

MAX_SEED = 2**63 - 1
MIN_SAMPLES, MAX_SAMPLES = 64, 1_000_000
OBSERVED_STRATA = ("snr_obs", "half_snr_obs", "double_snr_obs", "snr_obs_atmospheric")
OBSERVED_FACTOR = {"snr_obs": 1.0, "half_snr_obs": 0.5, "double_snr_obs": 2.0, "snr_obs_atmospheric": 1.0}
NOMINAL_STRATA = ("nominal_10", "nominal_30", "nominal_100")
NOMINAL_SNR = {"nominal_10": 10.0, "nominal_30": 30.0, "nominal_100": 100.0}
NOMINAL_LABEL = "observed SNR not available — nominal SNR"
STRATUM_KEYS = ("alpha", "terminal_duration_h", "onset_velocity_mm_per_day", "steady_phase_fraction", "psi_deg")
CONFIG_KEYS = (
    "alpha",
    "terminal_duration_h",
    "onset_velocity_mm_per_day",
    "steady_phase_fraction",
    "regressive_probability",
    "regressive_velocity_reduction",
    "regressive_duration_fraction",
    "psi_deg",
    "n_samples",
    "snr_obs",
    "ar1_rho",
    "splits",
)


class InvalidSynthConfigError(ValueError):
    """A synthesizer configuration was rejected before any event was generated (FR-010-16)."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field or '/'}: {message}")
        self.field = field


# ----------------------------------------------------------------------------------------------------------------------
# configuration


def default_config(snr_obs: float | None) -> dict[str, Any]:
    """The section 7 priors and split sizes; ``snr_obs`` is the observed SNR or None when it is not available."""
    return {
        "alpha": [1.7, 2.3],
        "terminal_duration_h": [24.0, 720.0],
        "onset_velocity_mm_per_day": [0.1, 10.0],
        "steady_phase_fraction": [0.1, 0.5],
        "regressive_probability": 0.2,
        "regressive_velocity_reduction": [0.3, 0.7],
        "regressive_duration_fraction": [0.05, 0.15],
        "psi_deg": [0.0, 60.0],
        "n_samples": 2000,
        "snr_obs": snr_obs,
        "ar1_rho": 0.9,
        "splits": {
            "train": {"start": 0, "count": 20_000},
            "validation": {"start": 20_000, "count": 1_000},
            "test": {"start": 21_000, "count_per_stratum": 500},
        },
    }


def _number(config: dict[str, Any], key: str) -> float:
    v = config[key]
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise InvalidSynthConfigError(key, f"must be a finite number, got {v!r}")
    return float(v)


def _range(
    config: dict[str, Any], key: str, lo_ok: Callable[[float], bool], hi_ok: Callable[[float], bool], rule: str
) -> tuple[float, float]:
    v = config[key]
    if not isinstance(v, list | tuple) or len(v) != 2:
        raise InvalidSynthConfigError(key, "must be a [min, max] pair")
    lo, hi = v
    for x in (lo, hi):
        if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x):
            raise InvalidSynthConfigError(key, f"must hold finite numbers, got {x!r}")
    if not (lo_ok(lo) and hi_ok(hi)):
        raise InvalidSynthConfigError(key, rule)
    if not lo <= hi:
        raise InvalidSynthConfigError(key, f"min {lo} must not exceed max {hi}")
    return float(lo), float(hi)


def _block(config: dict[str, Any], name: str, count_key: str) -> tuple[int, int]:
    node = config["splits"].get(name)
    if not isinstance(node, dict) or set(node) != {"start", count_key}:
        raise InvalidSynthConfigError(f"splits/{name}", f"must be an object with start and {count_key}")
    start, count = node["start"], node[count_key]
    for what, v in (("start", start), (count_key, count)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise InvalidSynthConfigError(f"splits/{name}/{what}", f"must be an integer >= 0, got {v!r}")
    if count < 1 or start + count > MAX_SEED:
        raise InvalidSynthConfigError(f"splits/{name}/{count_key}", "must be >= 1 and keep every seed below 2**63")
    return start, count


def strata_of(config: dict[str, Any]) -> tuple[str, ...]:
    return OBSERVED_STRATA if config.get("snr_obs") is not None else NOMINAL_STRATA


def validate_config(config: Any) -> None:
    """Reject an invalid configuration (FR-010-16) with ``InvalidSynthConfigError`` naming the field."""
    if not isinstance(config, dict):
        raise InvalidSynthConfigError("", "the configuration must be a mapping")
    for key in config:
        if key not in CONFIG_KEYS:
            raise InvalidSynthConfigError(key, "unknown key")
    for key in CONFIG_KEYS:
        if key not in config:
            raise InvalidSynthConfigError(key, "missing key")
    _range(config, "alpha", lambda x: x > 1.0, lambda x: x > 1.0, "alpha must be > 1")
    _range(config, "terminal_duration_h", lambda x: x > 0.0, lambda x: x > 0.0, "the terminal duration must be > 0 h")
    _range(config, "onset_velocity_mm_per_day", lambda x: x > 0.0, lambda x: x > 0.0, "the onset velocity must be > 0")
    _range(config, "steady_phase_fraction", lambda x: x >= 0.0, lambda x: x < 1.0, "must lie in [0, 1)")
    _range(config, "regressive_velocity_reduction", lambda x: x > 0.0, lambda x: x < 1.0, "must lie in (0, 1)")
    _range(config, "regressive_duration_fraction", lambda x: x > 0.0, lambda x: x < 1.0, "must lie in (0, 1)")
    _range(config, "psi_deg", lambda x: x >= 0.0, lambda x: x <= 89.0, "psi must lie in [0, 89] degrees")
    p = _number(config, "regressive_probability")
    if not 0.0 <= p <= 1.0:
        raise InvalidSynthConfigError("regressive_probability", "must lie in [0, 1]")
    n = config["n_samples"]
    if isinstance(n, bool) or not isinstance(n, int) or not MIN_SAMPLES <= n <= MAX_SAMPLES:
        raise InvalidSynthConfigError("n_samples", f"must be an integer in [{MIN_SAMPLES}, {MAX_SAMPLES}], got {n!r}")
    snr = config["snr_obs"]
    if snr is not None and (
        isinstance(snr, bool) or not isinstance(snr, int | float) or not math.isfinite(snr) or snr <= 0.0
    ):
        raise InvalidSynthConfigError("snr_obs", f"must be a finite number > 0 or null, got {snr!r}")
    rho = _number(config, "ar1_rho")
    if not abs(rho) < 1.0:
        raise InvalidSynthConfigError("ar1_rho", "the AR(1) coefficient must satisfy |rho| < 1")
    if not isinstance(config["splits"], dict) or set(config["splits"]) != {"train", "validation", "test"}:
        raise InvalidSynthConfigError("splits", "must have train, validation and test")
    t_start, t_count = _block(config, "train", "count")
    v_start, v_count = _block(config, "validation", "count")
    s_start, s_count = _block(config, "test", "count_per_stratum")
    blocks = [("train", t_start, t_count), ("validation", v_start, v_count)]
    blocks.append(("test", s_start, s_count * len(strata_of(config))))
    spans = sorted(blocks, key=lambda b: b[1])
    for (name_a, start_a, count_a), (name_b, start_b, _) in pairwise(spans):
        if start_a + count_a > start_b:
            raise InvalidSynthConfigError("splits", f"the seed ranges of {name_a} and {name_b} overlap")


def make_splits(config: dict[str, Any]) -> dict[str, Any]:
    """Seeds of the train and validation sets and, per stratum, of the test events (consecutive blocks)."""
    validate_config(config)
    t_start, t_count = _block(config, "train", "count")
    v_start, v_count = _block(config, "validation", "count")
    s_start, s_count = _block(config, "test", "count_per_stratum")
    test = {
        stratum: list(range(s_start + i * s_count, s_start + (i + 1) * s_count))
        for i, stratum in enumerate(strata_of(config))
    }
    return {
        "train": list(range(t_start, t_start + t_count)),
        "validation": list(range(v_start, v_start + v_count)),
        "test": test,
    }


# ----------------------------------------------------------------------------------------------------------------------
# one event


def voight_a_from_onset(v_onset_mm_per_h: float, alpha: float, terminal_h: float) -> float:
    """A with the terminal-stage velocity at its onset equal to ``v_onset``: [(alpha - 1) A T]^(-1/(alpha - 1)) = v."""
    return v_onset_mm_per_h ** (-(alpha - 1.0)) / ((alpha - 1.0) * terminal_h)


def voight_displacement(t: np.ndarray, *, alpha: float, a: float, t_f: float, t_on: float) -> np.ndarray:
    """Terminal-stage displacement (mm), zero at ``t_on``."""
    if abs(alpha - 2.0) < 1e-12:
        return np.log((t_f - t_on) / (t_f - t)) / a
    p = (alpha - 2.0) / (alpha - 1.0)
    c = ((alpha - 1.0) * a) ** (-1.0 / (alpha - 1.0))
    return c * ((t_f - t_on) ** p - (t_f - t) ** p) / p


def _draw_parameters(seed: int, config: dict[str, Any]) -> dict[str, Any]:
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))
    uni = lambda lohi: float(rng.uniform(lohi[0], lohi[1]))  # noqa: E731
    logu = lambda lohi: float(math.exp(rng.uniform(math.log(lohi[0]), math.log(lohi[1]))))  # noqa: E731
    out: dict[str, Any] = {
        "alpha": uni(config["alpha"]),
        "terminal_duration_h": logu(config["terminal_duration_h"]),
        "onset_velocity_mm_per_day": logu(config["onset_velocity_mm_per_day"]),
        "steady_phase_fraction": uni(config["steady_phase_fraction"]),
    }
    flag = float(rng.random()) < float(config["regressive_probability"])
    reduction = uni(config["regressive_velocity_reduction"])
    fraction = uni(config["regressive_duration_fraction"])
    out["psi_deg"] = uni(config["psi_deg"])
    out["regressive"] = flag
    out["regressive_velocity_reduction"] = reduction
    out["regressive_duration_fraction"] = fraction
    return out


def _omega(t: np.ndarray, p: dict[str, Any]) -> tuple[np.ndarray, float, float, float]:
    """Noise-free displacement along the record: (Omega, A, t_on, t_f)."""
    alpha, term = p["alpha"], p["terminal_duration_h"]
    v_on = p["onset_velocity_mm_per_day"] / 24.0
    a = voight_a_from_onset(v_on, alpha, term)
    t_on = p["steady_phase_fraction"] * term
    t_f = t_on + term
    pre = v_on * np.minimum(t, t_on)
    lost = 0.0
    if p["regressive"]:
        d = min(p["regressive_duration_fraction"] * t_f, t_on)
        s = 0.5 * (t_on - d)  # the episode is centred in the steady phase and always fits inside it
        overlap = np.clip(np.minimum(t, s + d) - s, 0.0, d)
        pre = pre - p["regressive_velocity_reduction"] * v_on * overlap
        lost = p["regressive_velocity_reduction"] * v_on * d
    terminal = (
        v_on * t_on
        - lost
        + voight_displacement(np.minimum(np.maximum(t, t_on), t_f - 1e-9), alpha=alpha, a=a, t_f=t_f, t_on=t_on)
    )
    return np.where(t < t_on, pre, terminal), a, t_on, t_f


def _ar1(rng: np.random.Generator, n: int, rho: float, sd: float) -> np.ndarray:
    z = rng.standard_normal(n)
    out = np.empty(n)
    out[0] = sd * z[0]
    scale = sd * math.sqrt(1.0 - rho * rho)
    prev = out[0]
    for i in range(1, n):
        prev = rho * prev + scale * z[i]
        out[i] = prev
    return out


def synthesize_event(
    seed: int,
    *,
    stratum: str = "snr_obs",
    snr_obs: float | None = 63.5,
    n_samples: int = 2000,
    split: str = "train",
    noise: bool = True,
    params: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One DC-010-02 synthetic-event document (see the module docstring)."""
    config = config if config is not None else default_config(snr_obs)
    if stratum in OBSERVED_STRATA:
        if snr_obs is None:
            raise ValueError(f"stratum {stratum!r} needs the observed SNR, which is not available")
        snr_target = float(snr_obs) * OBSERVED_FACTOR[stratum]
    elif stratum in NOMINAL_STRATA:
        if snr_obs is not None:
            raise ValueError(f"stratum {stratum!r} is for runs without the observed SNR")
        snr_target = NOMINAL_SNR[stratum]
    else:
        raise ValueError(f"unknown stratum {stratum!r}")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= MAX_SEED:
        raise ValueError(f"seed must be an integer in [0, 2**63), got {seed!r}")
    p = _draw_parameters(seed, config)
    p.update(params or {})
    n = int(n_samples)
    term = p["terminal_duration_h"]
    t_on = p["steady_phase_fraction"] * term
    t_f = t_on + term
    t = np.arange(n) * t_f / n
    omega, a, t_on, t_f = _omega(t, p)
    cos_psi = math.cos(math.radians(p["psi_deg"]))
    clean = cos_psi * omega
    sigma_d = cos_psi * float(omega[-1] - omega[0]) / snr_target
    series = clean.copy()
    parameters: dict[str, Any] = {
        "alpha": float(p["alpha"]),
        "a_coefficient": float(a),
        "terminal_duration_h": float(term),
        "onset_velocity_mm_per_day": float(p["onset_velocity_mm_per_day"]),
        "steady_phase_fraction": float(p["steady_phase_fraction"]),
        "regressive": bool(p["regressive"]),
        "psi_deg": float(p["psi_deg"]),
        "snr_target": snr_target,
        "sigma_d_mm": sigma_d if noise else 0.0,
    }
    if p["regressive"]:
        parameters["regressive_velocity_reduction"] = float(p["regressive_velocity_reduction"])
        parameters["regressive_duration_fraction"] = float(p["regressive_duration_fraction"])
    if stratum == "snr_obs_atmospheric":
        parameters["ar1"] = {"rho": float(config["ar1_rho"]), "marginal_sd_mm": sigma_d}
    if noise:
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed, spawn_key=(1,))))
        series = series + sigma_d * rng.standard_normal(n)
        if stratum == "snr_obs_atmospheric":
            series = series + _ar1(rng, n, float(config["ar1_rho"]), sigma_d)
    try:
        realised = _snr.estimate(series)[0]
    except ValueError:
        realised = 1e9
    doc: dict[str, Any] = {
        "kind": "synthetic-event",
        "synthetic": True,
        "event_id": f"voight-{split}-{stratum.replace('_', '-')}-{seed:06d}",
        "seed": seed,
        "split": split,
        "stratum": stratum,
        "parameters": parameters,
        "t_0_h": 0.0,
        "t_f_h": float(t_f),
        "t_f_source": "synthetic (exact)",
        "realised_snr": float(min(max(realised, 1e-9), 1e9)),
        "sampling": {"n_samples": n, "interval_h": float(t_f / n), "regular": True},
        "t_h": [float(x) for x in t],
        "los_displacement_mm": [float(x) for x in series],
    }
    if stratum in NOMINAL_STRATA:
        doc["snr_note"] = NOMINAL_LABEL
    return doc


def generate_event_set(config: dict[str, Any], sink: Callable[[dict[str, Any]], None]) -> None:
    """Validate the configuration, then emit every train, validation and test event once through ``sink``."""
    validate_config(config)
    splits = make_splits(config)
    snr_obs = config["snr_obs"]
    base = "snr_obs" if snr_obs is not None else "nominal_30"
    n = int(config["n_samples"])
    for split in ("train", "validation"):
        for seed in splits[split]:
            sink(synthesize_event(seed, stratum=base, snr_obs=snr_obs, n_samples=n, split=split, config=config))
    for stratum, seeds in splits["test"].items():
        for seed in seeds:
            sink(synthesize_event(seed, stratum=stratum, snr_obs=snr_obs, n_samples=n, split="test", config=config))
