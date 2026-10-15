# ruff: noqa: E501, PT018
"""T-007-011: quantile tables (2^12 bins, end bins at the conditional tail means) and the `engine` / `exponential` / `deterministic` profiles; table
moments and KS checked against the closed-form distributions.

Requirements: FR-007-06, FR-007-07, P-007-03.

Spec: specs/007-haulage-dispatch/spec.md FR-007-06 (variates only from integer operations, the IEEE basic operations and linear interpolation in quantile
tables carried in the bundle; uniform, normal, unit-mean lognormal(-sigma^2/2, sigma), exponential and bounded integers), FR-007-07 (profile `exponential`:
`loadtime` and `dumptime` unit-mean lognormal requests are answered with unit-mean exponential variates, `payload` requests with their mean, the other streams
as in `engine`; profile `deterministic`: every request is answered with the distribution mean: uniform to the midpoint, normal to loc, unit-mean lognormal to 1,
exponential to scale, bounded integers to their lower bound; the profile is recorded in the trace header), section 7 ("Quantile tables": 2^12 bins with linear
interpolation; the top 12 bits of a 64-bit word choose the bin and the next 52 bits the position inside it; the end bins are set so that their means equal the
conditional tail means; a family/parameter pair with no table is rejected with `InvalidScenario`), section 8 (c) (tables are carried per (family, sigma) in
standard form uniform(0, 1), normal(0, 1), exponential(1), unit-mean lognormal(sigma) as 4,097 float64 knots, little-endian, base64, with the SHA-256 of the
decoded bytes; sigma in [0.05, 1]) and P-007-03 (for every table: mean equal to the target, variance within rtol 1e-2, KS distance to the target CDF <= 2^-11;
for 10^5 draws on fixed seeds the empirical KS statistic <= 0.007).

Oracle: closed forms written in the test: the exact moments of a piecewise-linear quantile function (trapezoid sums for the mean, (a^2 + ab + b^2) / 3 per bin for
the second moment, summed with `math.fsum`), the target moments (uniform 1/2 and 1/12; normal 0 and 1; exponential 1 and 1; unit-mean lognormal 1 and
exp(sigma^2) - 1), the exact CDFs (`math.erf`, `1 - exp(-x)`), `scipy.stats.kstest`, the spec's own table `haul-scenario.valid-exponential.json`, `numpy.random.Philox`
for the words of each stream (as in test_t_007_010) and lerp(a, b, t) = a + t * (b - a).
Known tension (see the report): P-007-03 asks the mean of every table to equal its target to rtol 1e-12, but the spec's own exponential table has mean 1.0000198 (the
trapezoid error of a 4096-bin quantile function); the tests demand rtol 1e-12 for the symmetric families (uniform, normal) and 2e-4 for exponential and lognormal.

Expected API (module `pitstudio_pipeline.haulage.variates`, errors in `pitstudio_pipeline.haulage.errors`):
    errors.InvalidScenario(HaulError)       attribute `violations: list[tuple[str, object, str]]` of (JSON path, value, rule); message lists them all
    TABLE_BINS = 4096
    build_table(family: str, sigma: float | None = None) -> numpy.ndarray     4097 float64 knots of the standard-form quantile function: interior knots
        k_i = F^-1(i / 4096) for i = 1..4095; the end bins (0 and 4095) have mean equal to the conditional tail mean, clamped at the lower support bound where the
        family has one (so the first knot of exponential and lognormal is >= 0); families "uniform", "normal", "exponential", "lognormal-unit-mean" (needs 0.05 <= sigma <= 1);
        ValueError for an unknown family, a missing or out-of-range sigma, a sigma for another family, a non-finite sigma
    encode_table(knots, family, sigma=None) -> dict      {"family", ["sigma"], "bins": 4096, "encoding": "float64-le-base64", "knots_f64le_b64": base64 of the little-endian
        float64 bytes (43,704 characters), "knots_sha256": SHA-256 hex of the decoded bytes}
    decode_table(entry: dict) -> numpy.ndarray          verifies bins, encoding, length (4097 knots), the SHA-256, finiteness and monotonicity; InvalidScenario otherwise
    lerp_table(knots, word: int) -> float               knots[i] + t * (knots[i + 1] - knots[i]) with i = word >> 52 and t = (word & (2^52 - 1)) * 2^-52
    VariateSource(seed, *, profile="engine", tables=None)       `tables` maps (family, sigma-or-None) to knots; None builds the standard tables on demand; an empty mapping
        means "the bundle carries none" and a request that needs a table raises InvalidScenario
        .profile -> str ("engine", "exponential" or "deterministic"; anything else raises InvalidScenario at construction)
        .uniform(purpose, lo, hi)                   lo + (hi - lo) * u01(word); ValueError unless lo <= hi and both finite
        .normal(purpose, loc, scale)                loc + scale * lerp_table(normal table, word); ValueError unless scale > 0 and finite
        .lognormal_unit_mean(purpose, sigma)        lerp_table(lognormal table for sigma, word)
        .exponential(purpose, scale)                scale * lerp_table(exponential table, word); ValueError unless scale > 0 and finite
        .integers(purpose, lo, hi)                  lo + ((word * (hi - lo)) >> 64), in [lo, hi); ValueError unless lo < hi
    profile rules of FR-007-07 apply inside these methods; `loadtime`, `dumptime` and `payload` are the purposes the rule names.
"""

from __future__ import annotations

import base64
import hashlib
import math
import struct
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit as kit
from pitstudio_pipeline.haulage.errors import InvalidScenario
from pitstudio_pipeline.haulage.variates import (
    TABLE_BINS,
    VariateSource,
    build_table,
    decode_table,
    encode_table,
    lerp_table,
    stream_key,
)

N = 4096
M64 = (1 << 64) - 1
SIGMAS = [0.05, 0.18, 0.5, 1.0]
FAMILIES = [("uniform", None), ("normal", None), ("exponential", None)] + [("lognormal-unit-mean", s) for s in SIGMAS]
ND = NormalDist()


def numpy_block(key, counter):
    v = (sum(w << (64 * i) for i, w in enumerate(counter)) - 1) % (1 << 256)
    start = np.array([(v >> (64 * i)) & M64 for i in range(4)], dtype=np.uint64)
    return tuple(int(x) for x in np.random.Philox(key=np.array(key, dtype=np.uint64), counter=start).random_raw(4))


def first_word(seed: int, purpose: str) -> int:
    return numpy_block(stream_key(seed, purpose), (0, 0, 0, 0))[0]


def piecewise_moments(k):
    mean = math.fsum((k[i] + k[i + 1]) / 2 for i in range(N)) / N
    second = math.fsum((k[i] ** 2 + k[i] * k[i + 1] + k[i + 1] ** 2) / 3 for i in range(N)) / N
    return mean, second - mean * mean


def target(family, sigma):
    return {
        "uniform": (0.5, 1 / 12),
        "normal": (0.0, 1.0),
        "exponential": (1.0, 1.0),
        "lognormal-unit-mean": (1.0, math.exp((sigma or 0) ** 2) - 1.0),
    }[family]


def cdf(family, sigma):
    if family == "uniform":
        return lambda x: min(1.0, max(0.0, x))
    if family == "normal":
        return lambda x: 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
    if family == "exponential":
        return lambda x: 0.0 if x <= 0 else 1.0 - math.exp(-x)
    mu = -sigma * sigma / 2
    return lambda x: 0.0 if x <= 0 else ND.cdf((math.log(x) - mu) / sigma)


IDS = [f"{f}{'' if s is None else '-' + str(s)}" for f, s in FAMILIES]


# ---------------------------------------------------------------------------------------------------------------------
# tables: shape, moments, KS
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("P-007-03")
@pytest.mark.parametrize(("family", "sigma"), FAMILIES, ids=IDS)
def test_a_table_is_4097_finite_non_decreasing_float64_knots(family, sigma):
    k = build_table(family, sigma)
    assert TABLE_BINS == 4096 and k.shape == (4097,) and k.dtype == np.float64
    assert np.all(np.isfinite(k)) and np.all(np.diff(k) >= 0.0)
    if family in ("exponential", "lognormal-unit-mean"):
        assert k[0] >= 0.0  # clamped at the support's lower bound


@pytest.mark.req("P-007-03")
@pytest.mark.parametrize(("family", "sigma"), FAMILIES, ids=IDS)
def test_the_mean_of_the_table_distribution_equals_the_target(family, sigma):
    mean, _ = piecewise_moments(build_table(family, sigma))
    tmean, _ = target(family, sigma)
    if family == "uniform":
        assert mean == pytest.approx(tmean, rel=1e-12)
    elif family == "normal":
        assert abs(mean) <= 1e-12  # antisymmetric knots: the mean is 0 to rounding
    else:
        # P-007-03 states rtol 1e-12, but the spec's own exponential table has relative mean error 1.98e-5 (trapezoid error of 4096 bins)
        assert mean == pytest.approx(tmean, rel=2e-4)


@pytest.mark.req("P-007-03")
@pytest.mark.parametrize(("family", "sigma"), FAMILIES, ids=IDS)
def test_the_variance_of_the_table_distribution_is_within_one_percent(family, sigma):
    _, var = piecewise_moments(build_table(family, sigma))
    _, tvar = target(family, sigma)
    assert var == pytest.approx(tvar, rel=1e-2)


@pytest.mark.req("P-007-03")
@pytest.mark.parametrize(("family", "sigma"), FAMILIES, ids=IDS)
def test_the_ks_distance_of_the_table_cdf_to_the_target_cdf_is_at_most_2_to_the_minus_11(family, sigma):
    k = build_table(family, sigma)
    u = np.arange(N + 1) / N
    exact = cdf(family, sigma)
    lo, hi = float(k[0]), float(k[-1])
    xs = np.unique(np.concatenate([np.linspace(lo, hi, 20001), k[::7]]))
    table_cdf = np.interp(xs, k, u)  # the CDF of the piecewise-linear quantile function is its inverse
    ref = np.array([exact(float(x)) for x in xs])
    assert float(np.max(np.abs(table_cdf - ref))) <= 2.0**-11


@pytest.mark.req("P-007-03")
@pytest.mark.parametrize("family", ["uniform", "normal"])
def test_symmetric_families_have_symmetric_knots(family):
    k = build_table(family)
    assert np.allclose(k + k[::-1], 2 * (0.5 if family == "uniform" else 0.0), rtol=0, atol=1e-12)


@pytest.mark.req("P-007-03")
def test_end_bins_have_the_conditional_tail_means():
    k = build_table("normal")
    h = 1.0 / N
    z = ND.inv_cdf(h)
    low_tail_mean = -ND.pdf(z) / h  # E[Z | Z < z_h]
    assert (k[0] + k[1]) / 2 == pytest.approx(low_tail_mean, rel=1e-9)
    assert (k[N - 1] + k[N]) / 2 == pytest.approx(-low_tail_mean, rel=1e-9)
    e = build_table("exponential")
    assert (e[N - 1] + e[N]) / 2 == pytest.approx(1.0 - math.log(h), rel=1e-9)  # E[X | U > 1 - h] for Exp(1)


@pytest.mark.req("FR-007-06")
def test_the_exponential_table_equals_the_one_in_the_spec_example():
    ex = kit.example("haul-scenario.valid-exponential.json")["quantile_tables"][0]
    raw = base64.b64decode(ex["knots_f64le_b64"])
    assert hashlib.sha256(raw).hexdigest() == ex["knots_sha256"]  # the example is self-consistent
    theirs = np.array(struct.unpack("<4097d", raw))
    assert np.allclose(build_table("exponential"), theirs, rtol=1e-9, atol=1e-12)


# ---------------------------------------------------------------------------------------------------------------------
# build / encode / decode hostile inputs
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-06")
@pytest.mark.parametrize(
    ("family", "sigma"),
    [
        ("nope", None),
        ("lognormal-unit-mean", None),
        ("lognormal-unit-mean", 0.049),
        ("lognormal-unit-mean", 1.001),
        ("lognormal-unit-mean", float("nan")),
        ("lognormal-unit-mean", float("inf")),
        ("normal", 0.5),
        ("exponential", 1.0),
        ("uniform", 0.1),
        ("", None),
    ],
)
def test_build_table_rejects_unknown_families_and_bad_sigma(family, sigma):
    with pytest.raises(ValueError):  # noqa: PT011
        build_table(family, sigma)


@pytest.mark.req("FR-007-06")
@pytest.mark.parametrize(("family", "sigma"), [("normal", None), ("lognormal-unit-mean", 0.18)])
def test_encode_then_decode_round_trips_exactly(family, sigma):
    k = build_table(family, sigma)
    entry = encode_table(k, family, sigma)
    assert entry["bins"] == 4096 and entry["encoding"] == "float64-le-base64" and entry["family"] == family
    assert ("sigma" in entry) == (sigma is not None)
    assert len(entry["knots_f64le_b64"]) == 43704
    raw = base64.b64decode(entry["knots_f64le_b64"])
    assert raw == k.astype("<f8").tobytes() and entry["knots_sha256"] == hashlib.sha256(raw).hexdigest()
    assert np.array_equal(decode_table(entry), k)


@pytest.mark.req("FR-007-06")
def test_decode_rejects_every_kind_of_damage():
    good = encode_table(build_table("normal"), "normal")
    k = build_table("normal")

    def mutate(**kw):
        e = dict(good)
        e.update(kw)
        return e

    bad_nan = k.copy()
    bad_nan[100] = float("nan")
    bad_order = k.copy()
    bad_order[[10, 11]] = bad_order[[11, 10]]
    raw = k.astype("<f8").tobytes()
    cases = [
        mutate(knots_sha256="0" * 64),
        mutate(bins=2048),
        mutate(encoding="float32-le-base64"),
        mutate(knots_f64le_b64=base64.b64encode(raw[:-8]).decode()),
        mutate(knots_f64le_b64="!!!not base64!!!"),
        mutate(
            knots_f64le_b64=base64.b64encode(bad_nan.astype("<f8").tobytes()).decode(),
            knots_sha256=hashlib.sha256(bad_nan.astype("<f8").tobytes()).hexdigest(),
        ),
        mutate(
            knots_f64le_b64=base64.b64encode(bad_order.astype("<f8").tobytes()).decode(),
            knots_sha256=hashlib.sha256(bad_order.astype("<f8").tobytes()).hexdigest(),
        ),
        {k2: v for k2, v in good.items() if k2 != "knots_sha256"},
    ]
    for e in cases:
        with pytest.raises(InvalidScenario):
            decode_table(e)


# ---------------------------------------------------------------------------------------------------------------------
# draws: the word -> bin and position rule, the formulas
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-06")
def test_lerp_uses_the_top_12_bits_for_the_bin_and_the_next_52_for_the_position():
    k = build_table("normal")
    for word in (0, 1, (1 << 52) - 1, 1 << 52, 0xABC << 52 | 0x123456789ABCD, M64, 0x800 << 52, 4095 << 52):
        i, frac = word >> 52, (word & ((1 << 52) - 1)) * 2.0**-52
        assert lerp_table(k, word) == k[i] + frac * (k[i + 1] - k[i])
    assert (
        lerp_table(k, 0) == k[0] and lerp_table(k, M64) <= k[4096]
    )  # t = 1 - 2^-52: the result may round to the last knot


@pytest.mark.req("FR-007-06")
@pytest.mark.parametrize("seed", [0, 42, 2**62 + 5])
def test_engine_profile_draws_follow_the_quantile_table_formulas(seed):
    src = VariateSource(seed)
    z = lerp_table(build_table("normal"), first_word(seed, "payload"))
    assert src.normal("payload", 227.0, 11.0) == 227.0 + 11.0 * z
    src = VariateSource(seed)
    ln = lerp_table(build_table("lognormal-unit-mean", 0.18), first_word(seed, "loadtime"))
    assert src.lognormal_unit_mean("loadtime", 0.18) == ln
    src = VariateSource(seed)
    ex = lerp_table(build_table("exponential"), first_word(seed, "dumptime"))
    assert src.exponential("dumptime", 55.0) == 55.0 * ex
    src = VariateSource(seed)
    assert src.integers("init", 3, 10) == 3 + ((first_word(seed, "init") * 7) >> 64)


@pytest.mark.req("FR-007-06")
def test_successive_draws_use_successive_words_of_the_stream():
    seed = 9
    key = stream_key(seed, "loadtime")
    words = [w for b in range(2) for w in numpy_block(key, (b, 0, 0, 0))]
    tab = build_table("lognormal-unit-mean", 0.5)
    src = VariateSource(seed)
    assert [src.lognormal_unit_mean("loadtime", 0.5) for _ in range(8)] == [lerp_table(tab, w) for w in words]


@pytest.mark.req("FR-007-06")
def test_a_request_that_needs_a_table_the_bundle_does_not_carry_is_invalid_scenario():
    src = VariateSource(1, tables={})
    for call in (
        lambda: src.normal("payload", 1.0, 1.0),
        lambda: src.lognormal_unit_mean("loadtime", 0.18),
        lambda: src.exponential("dumptime", 1.0),
    ):
        with pytest.raises(InvalidScenario):
            call()
    assert 0.0 <= src.uniform("init", 0.0, 60.0) < 60.0  # uniform and integers need no table
    assert 0 <= src.integers("init", 0, 5) < 5
    carried = {("lognormal-unit-mean", 0.18): build_table("lognormal-unit-mean", 0.18)}
    ok = VariateSource(1, tables=carried)
    assert ok.lognormal_unit_mean("loadtime", 0.18) > 0.0
    with pytest.raises(InvalidScenario):
        ok.lognormal_unit_mean("loadtime", 0.5)  # another sigma: no table


@pytest.mark.req("FR-007-06")
@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.uniform("init", 2.0, 1.0),
        lambda s: s.uniform("init", float("nan"), 1.0),
        lambda s: s.uniform("init", 0.0, float("inf")),
        lambda s: s.normal("payload", 0.0, 0.0),
        lambda s: s.normal("payload", 0.0, -1.0),
        lambda s: s.normal("payload", float("nan"), 1.0),
        lambda s: s.exponential("dumptime", 0.0),
        lambda s: s.exponential("dumptime", float("inf")),
        lambda s: s.integers("init", 5, 5),
        lambda s: s.integers("init", 6, 5),
    ],
)
def test_degenerate_or_non_finite_parameters_are_rejected(call):
    with pytest.raises(ValueError):  # noqa: PT011
        call(VariateSource(3))


# ---------------------------------------------------------------------------------------------------------------------
# the profiles (FR-007-07)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-07")
def test_the_profile_is_recorded_and_unknown_profiles_are_rejected():
    for p in ("engine", "exponential", "deterministic"):
        assert VariateSource(1, profile=p).profile == p
    assert VariateSource(1).profile == "engine"
    for bad in ("Engine", "", "uniform", None, 3):
        with pytest.raises(InvalidScenario):
            VariateSource(1, profile=bad)


@pytest.mark.req("FR-007-07")
@pytest.mark.parametrize("seed", [0, 5, 77])
def test_exponential_profile_answers_load_and_dump_times_with_unit_exponential_variates(seed):
    exp_tab = build_table("exponential")
    for purpose in ("loadtime", "dumptime"):
        src = VariateSource(seed, profile="exponential")
        assert src.lognormal_unit_mean(purpose, 0.18) == lerp_table(exp_tab, first_word(seed, purpose))
    src = VariateSource(seed, profile="exponential")
    ln = lerp_table(build_table("lognormal-unit-mean", 0.18), first_word(seed, "lhd.dig"))
    assert src.lognormal_unit_mean("lhd.dig", 0.18) == ln  # other purposes keep the engine family


@pytest.mark.req("FR-007-07")
def test_exponential_profile_answers_payload_with_the_mean_and_leaves_other_normals_alone():
    src = VariateSource(11, profile="exponential")
    for _ in range(5):
        assert src.normal("payload", 227.0, 11.0) == 227.0
    z = lerp_table(build_table("normal"), first_word(11, "lhd.bucket"))
    assert VariateSource(11, profile="exponential").normal("lhd.bucket", 14.0, 1.0) == 14.0 + 1.0 * z
    ref = VariateSource(11)
    mine = VariateSource(11, profile="exponential")
    assert mine.uniform("init", 0.0, 60.0) == ref.uniform("init", 0.0, 60.0)  # uniform is unchanged by the profile


@pytest.mark.req("FR-007-07")
def test_deterministic_profile_answers_every_request_with_the_mean():
    src = VariateSource(123, profile="deterministic", tables={})  # no table needed at all
    for _ in range(3):
        assert src.uniform("init", 0.0, 60.0) == 30.0
        assert src.uniform("init", -4.0, 10.0) == 3.0
        assert src.normal("payload", 227.0, 11.0) == 227.0
        assert src.lognormal_unit_mean("loadtime", 0.18) == 1.0
        assert src.exponential("dumptime", 55.0) == 55.0
        assert src.integers("init", 3, 10) == 3
    assert src.profile == "deterministic"


# ---------------------------------------------------------------------------------------------------------------------
# empirical KS (P-007-03)
# ---------------------------------------------------------------------------------------------------------------------
def draws(family, sigma, n, seed):
    src = VariateSource(seed)
    if family == "uniform":
        return [src.uniform("init", 0.0, 1.0) for _ in range(n)]
    if family == "normal":
        return [src.normal("payload", 0.0, 1.0) for _ in range(n)]
    if family == "exponential":
        return [src.exponential("dumptime", 1.0) for _ in range(n)]
    return [src.lognormal_unit_mean("loadtime", sigma) for _ in range(n)]


def scipy_cdf(family, sigma):
    return {
        "uniform": stats.uniform().cdf,
        "normal": stats.norm().cdf,
        "exponential": stats.expon().cdf,
        "lognormal-unit-mean": stats.lognorm(s=sigma or 1.0, scale=math.exp(-((sigma or 1.0) ** 2) / 2)).cdf,
    }[family]


@pytest.mark.req("P-007-03")
@pytest.mark.parametrize(("family", "sigma"), FAMILIES, ids=IDS)
def test_empirical_ks_of_ten_thousand_draws_is_small(family, sigma):
    ks = stats.kstest(draws(family, sigma, 10_000, 20261012), scipy_cdf(family, sigma)).statistic
    assert (
        ks <= 1.95 / math.sqrt(10_000) + 2.0**-11
    )  # the spec's bound at n = 10^4 (alpha = 0.001 plus the table error)


@pytest.mark.req("P-007-03")
@pytest.mark.parametrize(
    ("family", "sigma"),
    [("uniform", None), ("normal", None), ("exponential", None), ("lognormal-unit-mean", 0.18)],
    ids=["uniform", "normal", "exponential", "lognormal-0.18"],
)
def test_empirical_ks_of_one_hundred_thousand_draws_is_at_most_0_007(family, sigma):
    ks = stats.kstest(draws(family, sigma, 100_000, 424242), scipy_cdf(family, sigma)).statistic
    assert ks <= 0.007
