"""T-010-020: seeded Voight events, strata, splits, configuration guards.

Requirements: FR-010-11, FR-010-16.
Spec: specs/010-slope/spec.md section 3.2 (FR-010-11, FR-010-16) and the parameter table of section 7 (Voight priors,
sampling and noise, splits); plan.md rows FR-010-11 and FR-010-16.

Expected API (module `pitstudio.slope.events`, numpy only, root environment):
- default_config(snr_obs) -> dict: the section 7 priors and split sizes with the keys below (snr_obs: a number or None).
- `synthesize_event(seed, *, stratum="snr_obs", snr_obs=63.5, n_samples=2000, split="train", noise=True, params=None)
  -> dict`
  a DC-010-02 synthetic-event document (valid against `contracts/displacement-series.schema.json`). `params` may fix
  any of
  alpha, terminal_duration_h, onset_velocity_mm_per_day, steady_phase_fraction, regressive (bool),
  regressive_velocity_reduction, regressive_duration_fraction, psi_deg; the others are drawn from the priors with
  `np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))`. The record is t_i = t_0 + i (t_f - t_0) / n,
  i = 0 .. n - 1, with t_0 = 0; a steady phase at the onset velocity of length steady_phase_fraction x terminal
  duration, then
  the Voight terminal stage with A set to match the onset velocity; the LOS displacement is cos(psi) x Omega plus white
  noise of sd sigma_d = cos(psi) dOmega / SNR_target (dOmega: noise-free displacement from the first to the last
  sample);
  `noise=False` returns the noise-free series. Strata: snr_obs (SNR_target = snr_obs), half_snr_obs (0.5 x),
  double_snr_obs
  (2 x), snr_obs_atmospheric (snr_obs plus an AR(1) term, rho 0.9, marginal sd sigma_d, recorded in `parameters.ar1`).
  The document records the exact t_f (`t_f_h`), the seed, the stratum, the parameters, `sigma_d_mm` and the realised SNR
  (FR-010-12 estimator on the generated series). event_id = "voight-<split>-<stratum with - for _>-<seed:06d>".
- `make_splits(config) -> {"train": [seeds], "validation": [seeds], "test": {stratum: [seeds]}}`.
- `validate_config(config)` and `generate_event_set(config, sink)` raise `InvalidSynthConfigError(ValueError)`
  (attribute
  `.field`) for an invalid configuration before generating any event (`sink(document)` is never called).
- Configuration keys: alpha [min, max], terminal_duration_h [min, max], onset_velocity_mm_per_day [min, max],
  steady_phase_fraction [min, max], regressive_probability, regressive_velocity_reduction [min, max],
  regressive_duration_fraction [min, max], psi_deg [min, max], n_samples, snr_obs (number or null), ar1_rho,
  splits {train {start, count}, validation {start, count}, test {start, count_per_stratum}} (test strata take
  consecutive
  blocks of count_per_stratum seeds from `start`, in the order snr_obs, half_snr_obs, double_snr_obs,
  snr_obs_atmospheric).

Oracles: the closed-form Voight integral (tests/_slope_ttf_ref.py: Omega = (1/A) ln((t_f - t_on) / (t_f - t)) for
alpha = 2
and the general-alpha power form); the declared prior distributions with a Kolmogorov-Smirnov test computed with numpy
over
2,000 fixed seeds (p > 1e-3, deterministic); the section 7 sizes (20,000 / 1,000 / 4 x 500); the hand formula
sigma_d = cos(psi) dOmega / SNR; the FR-010-12 estimator of the kit on the generated series.
"""

from __future__ import annotations

import copy
import math
import re
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as lem_ref
import _slope_ttf_ref as k
from pitstudio.slope import events

STRATA = ["snr_obs", "half_snr_obs", "double_snr_obs", "snr_obs_atmospheric"]
SEEDS = range(10_000, 12_000)
FIXED = {
    "alpha": 2.0,
    "terminal_duration_h": 240.0,
    "onset_velocity_mm_per_day": 1.2,
    "steady_phase_fraction": 0.25,
    "regressive": False,
    "psi_deg": 0.0,
}


def _schema_errors(doc: dict) -> list[str]:
    return lem_ref.schema_errors(doc, "displacement-series")


# ---------------------------------------------------------------------------------------------------------------------
# closed form (noise-free)


@pytest.mark.req("FR-010-11")
@pytest.mark.parametrize("alpha", [1.7, 2.0, 2.3])
def test_noise_free_event_matches_the_closed_form_voight_integral(alpha) -> None:
    n = 400
    ev = events.synthesize_event(5, n_samples=n, noise=False, params={**FIXED, "alpha": alpha, "psi_deg": 30.0})
    v_on = 1.2 / 24.0
    steady, term = 0.25 * 240.0, 240.0
    a = k.voight_a_from_onset(v_on, alpha, term)
    t_f = steady + term
    t = np.arange(n) * t_f / n
    omega = np.where(
        t < steady,
        v_on * t,
        v_on * steady + k.voight_displacement(np.minimum(t, t_f - 1e-9), alpha=alpha, a=a, t_f=t_f, t_on=steady),
    )
    assert ev["t_f_h"] == pytest.approx(t_f, rel=1e-12)
    assert ev["t_0_h"] == 0.0
    assert ev["t_h"] == pytest.approx(t.tolist(), rel=1e-12, abs=1e-12)
    assert ev["los_displacement_mm"] == pytest.approx(
        (math.cos(math.radians(30.0)) * omega).tolist(), rel=1e-9, abs=1e-9
    )
    assert ev["parameters"]["a_coefficient"] == pytest.approx(a, rel=1e-9)
    assert ev["t_f_source"] == "synthetic (exact)"
    assert ev["sampling"] == {"n_samples": n, "interval_h": pytest.approx(t_f / n), "regular": True}


@pytest.mark.req("FR-010-11")
def test_terminal_velocity_at_the_onset_equals_the_onset_velocity() -> None:
    n = 4000
    ev = events.synthesize_event(6, n_samples=n, noise=False, params={**FIXED, "alpha": 2.2})
    t, om = np.array(ev["t_h"]), np.array(ev["los_displacement_mm"])
    i = round(60.0 / (300.0 / n))  # t_on = 0.25 x 240 = 60 h
    v = (om[i + 1] - om[i - 1]) / (t[i + 1] - t[i - 1])
    assert v == pytest.approx(1.2 / 24.0, rel=2e-3)  # centred difference at the onset, both stages share the velocity
    assert np.all(np.diff(om) > 0)


@pytest.mark.req("FR-010-11")
def test_a_regressive_episode_reduces_the_velocity_before_the_onset_only() -> None:
    n = 3000
    p = {**FIXED, "regressive": True, "regressive_velocity_reduction": 0.5, "regressive_duration_fraction": 0.1}
    ev = events.synthesize_event(7, n_samples=n, noise=False, params=p)
    t, om = np.array(ev["t_h"]), np.array(ev["los_displacement_mm"])
    v = np.diff(om) / np.diff(t)
    pre = t[:-1] < 60.0 - 2 * (t[1] - t[0])
    values = {round(x, 9) for x in v[pre]}
    v_on = 1.2 / 24.0
    mixed = [x for x in v[pre] if abs(x - v_on) > 1e-6 and abs(x - 0.5 * v_on) > 1e-6]
    assert len(mixed) <= 2  # at most the two samples that straddle the episode boundaries
    assert len(values) <= 2 + 2
    reduced = float(np.mean(np.isclose(v[pre], 0.5 * v_on, atol=1e-6)))
    assert reduced > 0
    t_f = ev["t_f_h"]
    assert reduced * 60.0 == pytest.approx(0.1 * t_f, abs=6 * t_f / n)  # 10 % of the record at the reduced velocity
    assert ev["parameters"]["regressive"] is True
    assert ev["parameters"]["regressive_velocity_reduction"] == 0.5


# ---------------------------------------------------------------------------------------------------------------------
# noise, strata, SNR


@pytest.mark.req("FR-010-11")
def test_white_noise_has_the_declared_standard_deviation_and_the_realised_snr_follows() -> None:
    n = 2000
    p = {**FIXED, "psi_deg": 40.0}
    clean = np.array(events.synthesize_event(8, n_samples=n, noise=False, params=p)["los_displacement_mm"])
    ev = events.synthesize_event(8, n_samples=n, params=p, snr_obs=50.0)
    prm = ev["parameters"]
    sigma = (clean[-1] - clean[0]) / 50.0
    # sigma_d = cos(psi) dOmega / SNR with dOmega the noise-free displacement range, here clean = cos(psi) Omega
    assert prm["sigma_d_mm"] == pytest.approx(sigma, rel=1e-9)
    assert prm["snr_target"] == pytest.approx(50.0)
    resid = np.array(ev["los_displacement_mm"]) - clean
    assert resid.std(ddof=1) == pytest.approx(
        prm["sigma_d_mm"], rel=0.06
    )  # the sd estimate has a relative sd of 1 / sqrt(2 n) = 1.6 %
    assert abs(resid.mean()) < 5 * prm["sigma_d_mm"] / math.sqrt(n)
    assert ev["realised_snr"] == pytest.approx(k.snr_estimate(ev["los_displacement_mm"])[0], rel=1e-9)
    assert ev["realised_snr"] == pytest.approx(50.0, rel=0.2)


@pytest.mark.req("FR-010-11")
@pytest.mark.parametrize(
    ("stratum", "factor"),
    [("snr_obs", 1.0), ("half_snr_obs", 0.5), ("double_snr_obs", 2.0), ("snr_obs_atmospheric", 1.0)],
)
def test_each_stratum_sets_its_target_snr_and_the_document_is_schema_valid(stratum, factor) -> None:
    ev = events.synthesize_event(21, stratum=stratum, snr_obs=60.0, n_samples=500, split="test")
    assert ev["stratum"] == stratum
    assert ev["parameters"]["snr_target"] == pytest.approx(60.0 * factor)
    assert ev["split"] == "test"
    assert ("ar1" in ev["parameters"]) == (stratum == "snr_obs_atmospheric")
    assert re.fullmatch(r"voight-test-" + stratum.replace("_", "-") + r"-000021", ev["event_id"])
    assert _schema_errors(ev) == []


@pytest.mark.req("FR-010-11")
def test_the_atmospheric_stratum_adds_ar1_noise_with_lag_one_correlation_0_9() -> None:
    n = 6000
    p = {**FIXED, "psi_deg": 0.0}
    clean = np.array(events.synthesize_event(9, n_samples=n, noise=False, params=p)["los_displacement_mm"])
    ev = events.synthesize_event(9, stratum="snr_obs_atmospheric", n_samples=n, params=p, snr_obs=60.0)
    sd = ev["parameters"]["sigma_d_mm"]
    assert ev["parameters"]["ar1"] == {"rho": 0.9, "marginal_sd_mm": pytest.approx(sd)}
    resid = np.array(ev["los_displacement_mm"]) - clean
    r = resid - resid.mean()
    lag1 = float((r[1:] * r[:-1]).sum() / (r * r).sum())
    # white noise (variance sd^2) plus AR(1) (variance sd^2): the lag-1 correlation of the sum is 0.9 / 2 = 0.45
    assert lag1 == pytest.approx(0.45, abs=0.06)
    assert resid.std(ddof=1) == pytest.approx(math.sqrt(2.0) * sd, rel=0.25)


@pytest.mark.req("FR-010-11")
def test_events_are_deterministic_in_the_seed() -> None:
    a = events.synthesize_event(77, n_samples=200)
    b = events.synthesize_event(77, n_samples=200)
    c = events.synthesize_event(78, n_samples=200)
    assert a == b
    assert a["los_displacement_mm"] != c["los_displacement_mm"]
    assert a["parameters"] != c["parameters"]
    assert a["seed"] == 77


# ---------------------------------------------------------------------------------------------------------------------
# priors (Kolmogorov-Smirnov against the declared distributions)


@pytest.fixture(scope="module")
def drawn() -> list[dict]:
    return [events.synthesize_event(s, n_samples=64)["parameters"] for s in SEEDS]


def _ks_ok(sample, cdf) -> None:
    d = k.ks_statistic(sample, cdf)
    assert k.ks_pvalue(d, len(sample)) > 1e-3, d


@pytest.mark.req("FR-010-11")
def test_priors_follow_their_declared_distributions(drawn) -> None:
    uni = lambda lo, hi: lambda x: min(1.0, max(0.0, (x - lo) / (hi - lo)))  # noqa: E731
    logu = lambda lo, hi: lambda x: min(1.0, max(0.0, math.log(x / lo) / math.log(hi / lo)))  # noqa: E731
    _ks_ok([p["alpha"] for p in drawn], uni(1.7, 2.3))
    _ks_ok([p["terminal_duration_h"] for p in drawn], logu(24.0, 720.0))
    _ks_ok([p["onset_velocity_mm_per_day"] for p in drawn], logu(0.1, 10.0))
    _ks_ok([p["steady_phase_fraction"] for p in drawn], uni(0.1, 0.5))
    _ks_ok([p["psi_deg"] for p in drawn], uni(0.0, 60.0))
    reg = [p for p in drawn if p["regressive"]]
    assert abs(len(reg) / len(drawn) - 0.2) < 4 * math.sqrt(0.2 * 0.8 / len(drawn))
    _ks_ok([p["regressive_velocity_reduction"] for p in reg], uni(0.3, 0.7))
    _ks_ok([p["regressive_duration_fraction"] for p in reg], uni(0.05, 0.15))
    assert all(("regressive_velocity_reduction" in p) == p["regressive"] for p in drawn)


@pytest.mark.req("FR-010-11")
def test_every_drawn_event_keeps_the_terminal_stage_before_one_third_of_the_record(drawn) -> None:
    # section 7: steady phase U[0.1, 0.5] x terminal duration, so t_on / t_f = s / (1 + s) < 1/3 (every cut-off sees it)
    assert all(p["steady_phase_fraction"] / (1 + p["steady_phase_fraction"]) < 1 / 3 for p in drawn)


# ---------------------------------------------------------------------------------------------------------------------
# splits


@pytest.mark.req("FR-010-11")
def test_default_splits_have_the_section_7_sizes_and_are_disjoint_by_seed() -> None:
    cfg = events.default_config(63.5)
    s = events.make_splits(cfg)
    assert len(s["train"]) == 20_000
    assert len(s["validation"]) == 1_000
    assert list(s["test"]) == STRATA
    assert all(len(v) == 500 for v in s["test"].values())
    everything = [*s["train"], *s["validation"], *[x for v in s["test"].values() for x in v]]
    assert len(everything) == len(set(everything)) == 20_000 + 1_000 + 4 * 500


@pytest.mark.req("FR-010-11")
def test_generate_event_set_emits_each_event_once_in_its_split_and_stratum() -> None:
    cfg = events.default_config(63.5)
    cfg["n_samples"] = 64
    cfg["splits"] = {
        "train": {"start": 0, "count": 5},
        "validation": {"start": 100, "count": 3},
        "test": {"start": 200, "count_per_stratum": 2},
    }
    docs: list[dict] = []
    events.generate_event_set(cfg, docs.append)
    assert len(docs) == 5 + 3 + 4 * 2
    seeds = events.make_splits(cfg)
    by_split = {"train": seeds["train"], "validation": seeds["validation"]}
    for d in docs:
        assert _schema_errors(d) == []
        if d["split"] != "test":
            assert d["seed"] in by_split[d["split"]]
            assert d["stratum"] == "snr_obs"
        else:
            assert d["seed"] in seeds["test"][d["stratum"]]
    assert len({d["event_id"] for d in docs}) == len(docs)


# ---------------------------------------------------------------------------------------------------------------------
# FR-010-16: hostile configurations are rejected before any event is generated


def _cfg(**changes) -> dict:
    cfg = copy.deepcopy(events.default_config(63.5))
    cfg["n_samples"] = 64
    cfg["splits"] = {
        "train": {"start": 0, "count": 3},
        "validation": {"start": 10, "count": 2},
        "test": {"start": 20, "count_per_stratum": 2},
    }
    for path, value in changes.items():
        node = cfg
        parts = path.split("__")
        for p in parts[:-1]:
            node = node[p]
        node[parts[-1]] = value
    return cfg


HOSTILE = [
    ("alpha-one", _cfg(alpha=[1.0, 2.3]), "alpha"),
    ("alpha-below-one", _cfg(alpha=[0.5, 2.3]), "alpha"),
    ("alpha-reversed", _cfg(alpha=[2.3, 1.7]), "alpha"),
    ("duration-zero", _cfg(terminal_duration_h=[0.0, 720.0]), "terminal_duration_h"),
    ("duration-negative", _cfg(terminal_duration_h=[-5.0, 720.0]), "terminal_duration_h"),
    ("snr-zero", _cfg(snr_obs=0.0), "snr_obs"),
    ("snr-negative", _cfg(snr_obs=-3.0), "snr_obs"),
    ("snr-nan", _cfg(snr_obs=float("nan")), "snr_obs"),
    ("snr-inf", _cfg(snr_obs=float("inf")), "snr_obs"),
    ("psi-above-89", _cfg(psi_deg=[0.0, 89.5]), "psi_deg"),
    ("psi-negative", _cfg(psi_deg=[-1.0, 60.0]), "psi_deg"),
    ("samples-63", _cfg(n_samples=63), "n_samples"),
    ("samples-too-many", _cfg(n_samples=10**6 + 1), "n_samples"),
    ("samples-zero", _cfg(n_samples=0), "n_samples"),
    ("samples-float", _cfg(n_samples=100.5), "n_samples"),
    ("seeds-overlap-train-validation", _cfg(splits__validation__start=2), "splits"),
    ("seeds-overlap-validation-test", _cfg(splits__test__start=11), "splits"),
    ("unknown-key", {**_cfg(), "surprise": 1}, "surprise"),
    ("not-a-mapping", [1, 2, 3], ""),
    ("ar1-unit-root", _cfg(ar1_rho=1.0), "ar1_rho"),
]


@pytest.mark.req("FR-010-16")
@pytest.mark.parametrize(("name", "cfg", "field"), HOSTILE, ids=[h[0] for h in HOSTILE])
def test_a_hostile_configuration_is_rejected_before_any_event_is_generated(name, cfg, field) -> None:
    sink: list = []
    with pytest.raises(events.InvalidSynthConfigError) as exc:
        events.validate_config(cfg)
    assert exc.value.field.startswith(field)
    with pytest.raises(events.InvalidSynthConfigError):
        events.generate_event_set(cfg, sink.append)
    assert sink == []


@pytest.mark.req("FR-010-16")
def test_the_valid_configuration_and_its_limits_are_accepted() -> None:
    events.validate_config(events.default_config(63.5))
    events.validate_config(_cfg(n_samples=64))
    events.validate_config(_cfg(n_samples=10**6))
    events.validate_config(_cfg(psi_deg=[0.0, 89.0]))
    events.validate_config(_cfg(alpha=[1.0001, 2.3]))
