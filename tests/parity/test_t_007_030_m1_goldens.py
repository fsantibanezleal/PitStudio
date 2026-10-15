# ruff: noqa: E501, PT018
"""T-007-030 (Python half): golden vectors of the M1 analytical models (match factor, M/M/1//N, M/M/c, MVA), including the spec section 7 worked examples, and the typed results for hostile
inputs; the TypeScript port is checked against the same file in web/src/engines/haulage/queueing.test.ts.

Requirements: FR-007-15, FR-007-16.

Spec: specs/007-haulage-dispatch/spec.md FR-007-15 (the fleet-sizing engine computes the match factor, M/M/1//N (pi_0, U, X), open M/M/c (C, W_q, L_q) and exact MVA by calling `minephys.haulage`
in Python and its TypeScript port in the browser; the port equals `minephys.haulage` on the committed golden vectors within rtol 1e-12, atol 1e-15), FR-007-16 (a non-finite input, N_T or N_L not a
positive integer, a rate or time <= 0, or N_T > 400 gives `InvalidInput` naming the field; rho >= 1 for open M/M/c gives `Unstable`; never NaN or Infinity), section 7 (worked examples: N = 8,
lambda/mu = 1/7, mu = 20 per hour: pi_0 = 0.17882, X = 16.424 loads/h; N = 5, lambda/mu = 0.2, mu = 15 per hour: pi_0 = 0.28487, X = 10.727 per hour; MVA with one queue (mu = 15/h) and a 20 min
delay: X = 2.50, 7.06, 12.12, 13.95 per hour for N = 1, 3, 6, 8) and the formulas of `minephys` spec 001 (FR-001-18 to FR-001-21).

Oracle: the closed forms written out in this file, independent of any library: pi_0 = [sum_{n=0}^{N} N!/(N-n)! (lambda/mu)^n]^-1, U = 1 - pi_0, X = mu U, L = N - X/lambda, time at loader = L / X;
Erlang C through the Erlang B recursion B_k = a B_{k-1} / (k + a B_{k-1}), C = B / (1 - rho (1 - B)), W_q = C / (c mu - lambda), L_q = lambda W_q, W = W_q + 1/mu, L = lambda W; exact MVA
(R_k = S_k (1 + L_k(n-1)) for a queue, S_k for a delay; X(n) = n / sum v_k R_k; L_k = v_k X R_k; U_k = v_k X S_k); the match factor n_trucks x load_time / (n_loaders x cycle_time); the published worked examples above.

Expected committed file `tests/fixtures/haulage/m1_goldens.json` (written by `tools/make_m1_goldens.py` from `minephys.haulage`; the numbers are the library's, which the tests check against the formulas):
    {"match_factor": [{"input": {"n_trucks", "n_loaders", "load_time", "cycle_time"}, "expected": <float>, "source"?: str}, ...],
     "finite_source": [{"input": {"n_trucks", "travel_rate", "service_rate"}, "expected": {"idle_probability", "utilisation", "throughput", "mean_at_loader", "mean_time_at_loader"}}, ...],
     "mmc": [{"input": {"arrival_rate", "service_rate", "servers"}, "expected": {"utilisation", "erlang_c", "mean_wait", "mean_queue_length", "mean_time_in_system", "mean_in_system"}}, ...],
     "mva": [{"input": {"population", "service_time": [...], "visit_ratio": [...], "station_type": [...]}, "expected": {"throughput": [X(1) ... X(N)], "residence_time": [...], "queue_length": [...], "utilisation": [...]}}, ...],
     "hostile": [{"fn": "match_factor" | "finite_source" | "mmc" | "mva", "input": {...}, "expected": {"kind": "InvalidInput", "field": <argument name>} | {"kind": "Unstable"}}, ...]}
    Non-finite numbers in `hostile` inputs are the strings "NaN", "Infinity" and "-Infinity" (JSON has no such numbers). Times are in seconds, rates in 1 / s, as in minephys.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "haulage"
FILE = FIXTURES / "m1_goldens.json"
RTOL, ATOL = 1e-12, 1e-15
SPEC_EXAMPLES = "spec-007-worked-example"


def goldens() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8"))


def close(a: float, b: float) -> bool:
    return abs(a - b) <= ATOL + RTOL * abs(b)


# ---------------------------------------------------------------------------------------------------------------------
# independent formulas
# ---------------------------------------------------------------------------------------------------------------------
def finite_source(n: int, lam: float, mu: float) -> dict:
    a = lam / mu
    term, total = 1.0, 1.0  # n = 0 term; term_n = N!/(N-n)! a^n built incrementally
    terms = [1.0]
    for k in range(1, n + 1):
        term *= (n - k + 1) * a
        terms.append(term)
    total = math.fsum(terms)
    pi0 = 1.0 / total
    util = 1.0 - pi0
    x = mu * util
    at_loader = n - x / lam
    return {
        "idle_probability": pi0,
        "utilisation": util,
        "throughput": x,
        "mean_at_loader": at_loader,
        "mean_time_at_loader": at_loader / x,
    }


def mmc(lam: float, mu: float, c: int) -> dict:
    a = lam / mu
    b = 1.0
    for k in range(1, c + 1):
        b = a * b / (k + a * b)
    rho = a / c
    erl_c = b / (1.0 - rho * (1.0 - b))
    wq = erl_c / (c * mu - lam)
    w = wq + 1.0 / mu
    return {
        "utilisation": rho,
        "erlang_c": erl_c,
        "mean_wait": wq,
        "mean_queue_length": lam * wq,
        "mean_time_in_system": w,
        "mean_in_system": lam * w,
    }


def mva(n: int, s: list[float], v: list[float], kinds: list[str]) -> dict:
    q = [0.0] * len(s)
    xs: list[float] = []
    r: list[float] = []
    for k in range(1, n + 1):
        r = [s[i] * (1.0 + q[i]) if kinds[i] == "queue" else s[i] for i in range(len(s))]
        x = k / math.fsum(v[i] * r[i] for i in range(len(s)))
        xs.append(x)
        q = [v[i] * x * r[i] for i in range(len(s))]
    x = xs[-1]
    return {
        "throughput": xs,
        "residence_time": r,
        "queue_length": q,
        "utilisation": [v[i] * x * s[i] for i in range(len(s))],
    }


def num(x):
    return {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}.get(x, x) if isinstance(x, str) else x


def positive(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x > 0


def count_ok(x, cap=None) -> bool:
    return (
        isinstance(x, (int, float))
        and not isinstance(x, bool)
        and math.isfinite(x)
        and float(x) == int(x)
        and x >= 1
        and (cap is None or x <= cap)
    )


def classify(fn: str, i: dict):
    """The rule of FR-007-16 written out: the first failing argument in the function's argument order, then Unstable for rho >= 1."""
    i = {k: ([num(y) for y in v] if isinstance(v, list) else num(v)) for k, v in i.items()}
    if fn == "match_factor":
        order = [
            ("n_trucks", lambda x: count_ok(x, 400)),
            ("n_loaders", count_ok),
            ("load_time", positive),
            ("cycle_time", positive),
        ]
    elif fn == "finite_source":
        order = [("n_trucks", lambda x: count_ok(x, 400)), ("travel_rate", positive), ("service_rate", positive)]
    elif fn == "mmc":
        order = [("arrival_rate", positive), ("service_rate", positive), ("servers", count_ok)]
    else:
        order = [
            ("population", lambda x: count_ok(x, 400)),
            ("service_time", lambda xs: bool(xs) and all(positive(y) for y in xs)),
            ("visit_ratio", lambda xs: bool(xs) and all(positive(y) for y in xs)),
        ]
    for name, ok in order:
        if not ok(i[name]):
            return {"kind": "InvalidInput", "field": name}
    if fn == "mmc" and i["arrival_rate"] >= i["servers"] * i["service_rate"]:
        return {"kind": "Unstable"}
    return None


# ---------------------------------------------------------------------------------------------------------------------
# the file
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-15")
def test_the_golden_file_exists_with_enough_vectors_of_every_model():
    g = goldens()
    assert set(g) >= {"match_factor", "finite_source", "mmc", "mva", "hostile"}
    assert (
        len(g["match_factor"]) >= 15
        and len(g["finite_source"]) >= 25
        and len(g["mmc"]) >= 25
        and len(g["mva"]) >= 10
        and len(g["hostile"]) >= 40
    )


@pytest.mark.req("FR-007-15")
@pytest.mark.parametrize("key", ["match_factor", "finite_source", "mmc", "mva"])
def test_every_vector_is_finite_and_has_the_documented_fields(key):
    fields = {
        "finite_source": {"idle_probability", "utilisation", "throughput", "mean_at_loader", "mean_time_at_loader"},
        "mmc": {"utilisation", "erlang_c", "mean_wait", "mean_queue_length", "mean_time_in_system", "mean_in_system"},
        "mva": {"throughput", "residence_time", "queue_length", "utilisation"},
    }
    for v in goldens()[key]:
        exp = v["expected"]
        if key == "match_factor":
            assert isinstance(exp, float) and math.isfinite(exp)
        else:
            assert set(exp) == fields[key]
            flat = [y for x in exp.values() for y in (x if isinstance(x, list) else [x])]
            assert all(isinstance(y, (int, float)) and math.isfinite(y) for y in flat)


@pytest.mark.req("FR-007-15")
def test_match_factor_vectors_equal_the_formula():
    for v in goldens()["match_factor"]:
        i = v["input"]
        assert close(v["expected"], i["n_trucks"] * i["load_time"] / (i["n_loaders"] * i["cycle_time"])), i


@pytest.mark.req("FR-007-15")
def test_finite_source_vectors_equal_the_closed_form():
    for v in goldens()["finite_source"]:
        i, want = (
            v["input"],
            finite_source(v["input"]["n_trucks"], v["input"]["travel_rate"], v["input"]["service_rate"]),
        )
        for k, x in v["expected"].items():
            assert close(x, want[k]), (i, k, x, want[k])


@pytest.mark.req("FR-007-15")
def test_mmc_vectors_equal_the_erlang_recursion_form():
    for v in goldens()["mmc"]:
        i = v["input"]
        want = mmc(i["arrival_rate"], i["service_rate"], i["servers"])
        for k, x in v["expected"].items():
            assert close(x, want[k]), (i, k, x, want[k])
        assert 0 < v["expected"]["erlang_c"] < 1 and v["expected"]["utilisation"] < 1


@pytest.mark.req("FR-007-15")
def test_mva_vectors_equal_the_recursion():
    for v in goldens()["mva"]:
        i = v["input"]
        want = mva(i["population"], i["service_time"], i["visit_ratio"], i["station_type"])
        assert len(v["expected"]["throughput"]) == i["population"]
        for k, x in v["expected"].items():
            assert len(x) == len(want[k]) and all(close(a, b) for a, b in zip(x, want[k], strict=True)), (i, k)
        assert math.isclose(
            sum(v["expected"]["queue_length"]), i["population"], rel_tol=1e-9
        )  # the population is conserved: sum of L_k(N) = N


@pytest.mark.req("FR-007-15")
def test_the_vectors_span_the_documented_ranges():
    g = goldens()
    assert (
        max(v["input"]["n_trucks"] for v in g["finite_source"]) >= 100
        and min(v["input"]["n_trucks"] for v in g["finite_source"]) == 1
    )
    assert max(v["input"]["servers"] for v in g["mmc"]) >= 50 and min(v["input"]["servers"] for v in g["mmc"]) == 1
    assert max(v["input"]["population"] for v in g["mva"]) >= 200
    assert max(len(v["input"]["service_time"]) for v in g["mva"]) >= 5
    assert any("delay" in v["input"]["station_type"] for v in g["mva"]) and any(
        set(v["input"]["station_type"]) == {"queue"} for v in g["mva"]
    )
    rhos = [v["expected"]["utilisation"] for v in g["mmc"]]
    assert min(rhos) < 0.1 and max(rhos) > 0.95  # light and heavy traffic


@pytest.mark.req("FR-007-15")
def test_the_spec_worked_examples_are_in_the_file_with_their_published_numbers():
    g = goldens()
    fs = {v["input"]["n_trucks"]: v for v in g["finite_source"] if v.get("source") == SPEC_EXAMPLES}
    e8 = fs[8]  # N = 8, lambda / mu = 1/7, mu = 20 per hour
    assert e8["input"]["service_rate"] * 3600 == pytest.approx(20.0, rel=1e-12) and e8["input"]["travel_rate"] / e8[
        "input"
    ]["service_rate"] == pytest.approx(1 / 7, rel=1e-12)
    assert e8["expected"]["idle_probability"] == pytest.approx(0.17882, abs=5e-6) and e8["expected"][
        "throughput"
    ] * 3600 == pytest.approx(16.424, abs=5e-4)
    e5 = fs[5]  # N = 5, lambda / mu = 0.2, mu = 15 per hour
    assert e5["input"]["service_rate"] * 3600 == pytest.approx(15.0, rel=1e-12) and e5["input"]["travel_rate"] / e5[
        "input"
    ]["service_rate"] == pytest.approx(0.2, rel=1e-12)
    assert e5["expected"]["idle_probability"] == pytest.approx(0.28487, abs=5e-6) and e5["expected"][
        "throughput"
    ] * 3600 == pytest.approx(10.727, abs=5e-4)
    mv = {v["input"]["population"]: v for v in g["mva"] if v.get("source") == SPEC_EXAMPLES}
    for n, per_hour in ((1, 2.50), (3, 7.06), (5, 10.727), (6, 12.12), (8, 13.95)):
        assert mv[n]["input"]["service_time"] == [240.0, 1200.0] and mv[n]["input"]["visit_ratio"] == [1.0, 1.0]
        assert mv[n]["input"]["station_type"] == ["queue", "delay"] and mv[n]["expected"]["throughput"][
            -1
        ] * 3600 == pytest.approx(per_hour, abs=0.005)


@pytest.mark.req("FR-007-15")
def test_one_queue_with_a_delay_equals_the_finite_source_model():
    """The identity behind the worked example: MVA with one queue (mu = 15/h) and a delay of 1 / lambda equals M/M/1//N (spec 007 section 7, minephys P-001-11)."""
    for n in (1, 3, 5, 8):
        mu, lam = 15 / 3600, (15 / 3600) * 0.2
        want = finite_source(n, lam, mu)["throughput"]
        got = mva(n, [1 / mu, 1 / lam], [1.0, 1.0], ["queue", "delay"])["throughput"][-1]
        assert got == pytest.approx(want, rel=1e-12)


# ---------------------------------------------------------------------------------------------------------------------
# hostile vectors (FR-007-16)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-16")
def test_every_hostile_vector_is_classified_as_the_rule_says():
    for h in goldens()["hostile"]:
        assert classify(h["fn"], h["input"]) == h["expected"], h


@pytest.mark.req("FR-007-16")
def test_the_hostile_vectors_cover_every_argument_and_every_failure_class():
    hs = goldens()["hostile"]
    seen = {(h["fn"], h["expected"].get("field", "-"), h["expected"]["kind"]) for h in hs}
    for fn, args in (
        ("match_factor", ["n_trucks", "n_loaders", "load_time", "cycle_time"]),
        ("finite_source", ["n_trucks", "travel_rate", "service_rate"]),
        ("mmc", ["arrival_rate", "service_rate", "servers"]),
        ("mva", ["population", "service_time", "visit_ratio"]),
    ):
        for a in args:
            assert (fn, a, "InvalidInput") in seen, (fn, a)
    assert ("mmc", "-", "Unstable") in seen
    # the value classes of the spec: non-finite, not a positive integer, <= 0, N_T > 400
    values = [
        num(x)
        for h in hs
        for x in ([h["input"].get("n_trucks"), h["input"].get("population"), h["input"].get("servers")])
    ]
    assert any(isinstance(x, float) and math.isnan(x) for x in values) and any(
        isinstance(x, float) and math.isinf(x) for x in values
    )
    assert any(isinstance(x, float) and math.isfinite(x) and x > 0 and x % 1 != 0 for x in values)  # a fractional count
    assert any(isinstance(x, (int, float)) and x <= 0 for x in values) and any(
        isinstance(x, (int, float)) and x in (401, 1000, 10**6) for x in values
    )
    unstable = [h for h in hs if h["expected"]["kind"] == "Unstable"]
    assert any(
        h["input"]["arrival_rate"] == h["input"]["servers"] * h["input"]["service_rate"] for h in unstable
    )  # rho = 1 exactly
    assert any(
        h["input"]["arrival_rate"] > h["input"]["servers"] * h["input"]["service_rate"] for h in unstable
    )  # rho > 1
    boundary = [h for h in hs if h["input"].get("n_trucks") == 400 or h["input"].get("population") == 400]
    assert not boundary or all(
        h["expected"]["kind"] != "InvalidInput" or h["expected"].get("field") != "n_trucks" for h in boundary
    )  # 400 itself is valid


@pytest.mark.req("FR-007-16")
def test_the_valid_vectors_are_not_classified_as_hostile():
    g = goldens()
    for v in g["finite_source"]:
        assert classify("finite_source", v["input"]) is None
    for v in g["mmc"]:
        assert classify("mmc", v["input"]) is None
    for v in g["match_factor"]:
        assert classify("match_factor", v["input"]) is None
    for v in g["mva"]:
        assert classify("mva", v["input"]) is None
