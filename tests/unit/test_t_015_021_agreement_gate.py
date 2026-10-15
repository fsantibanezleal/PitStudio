# ruff: noqa: E501
"""T-015-021: the Q8_0 versus BF16 agreement gate (500 binary queries, point estimate, Wilson interval) and the rejection path.

Requirements: FR-015-14, FR-015-15, P-015-05, SC-015-01.

Spec: specs/015-vlm/spec.md
- FR-015-14: the gate compares Q8_0 and BF16 on a fixed subset of 500 binary task-A queries (100 per binary type, 50 yes and 50
  no) with greedy decoding, reasoning off and identical prompts and preprocessing; agreement a is the fraction of queries with
  identical normalised answers; the gate passes if and only if a >= 0.95 (point estimate), and its Wilson 95 % interval is reported.
- FR-015-15: if a < 0.95, every Cosmos result shall come from the BF16 path and the Q8_0 path is published only as "rejected:
  agreement a = ... < 0.95" with no task metric.
- P-015-05: (MR1) a(Q8_0, BF16) = a(BF16, Q8_0); (MR2) a = 1 for identical lists; (MR3) invariant under query permutation; the gate
  passes at 475/500 and fails at 474/500.
- SC-015-01: Q8_0 versus BF16 agreement >= 95 % on binary questions (otherwise BF16 replaces Q8_0).

Oracle: hand calculation (475 / 500 = 0.95 exactly, 474 / 500 = 0.948; Wilson interval of 485/500 = [0.9511, 0.9817], published
in spec P-015-03; the closed-form Wilson formula of `_p015_kit.wilson`); the JSON Schema of the gate and row contracts
(`contracts/vlm-metrics.schema.json`, reference implementation `jsonschema`).

Expected API of the implementation (package `pitstudio`, root environment), `pitstudio.reason.gate`:
- `agreement(a, b) -> fractions.Fraction`: fraction of positions with equal answers; ValueError for unequal lengths or n = 0.
- `evaluate_gate(q8, bf16) -> dict`: `q8` and `bf16` are aligned lists of 500 normalised answers (labels); returns the metrics
  contract's `gate` object: `status` "pass" or "fail", `n` 500, `agree` (int), `agreement` (float), `wilson95` `{"lo", "hi"}`,
  `threshold` 0.95, `q8_0_path` "accepted" or "rejected". ValueError unless both lists have exactly 500 entries.
- `apply_gate(rows, gate) -> list[dict]`: `rows` are task-A `row_a` dicts; when the gate failed, every row of arm "cosmos-q8_0" is
  replaced by a rejected row (status "rejected", `reason` "rejected: agreement a = <a> < 0.95" where <a> is the agreement to
  1 to 6 decimals, every metric None, `by_condition` empty); other rows are returned unchanged; when the gate passed all rows
  are unchanged.
- `validate_gate_subset(queries) -> None`: `queries` are the gate-flagged DC-015-02 queries; ValueError unless there are 500, 100
  per binary type (1, 2, 4, 5, 6), 50 yes and 50 no per type, none of type 3.
"""

from __future__ import annotations

import random
import re
import sys
from fractions import Fraction
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from pitstudio.reason.gate import agreement, apply_gate, evaluate_gate, validate_gate_subset

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _p015_contracts as contracts
import _p015_kit as kit

N = 500


def _lists(disagreements: int) -> tuple[list[str], list[str]]:
    bf16 = ["yes" if i % 2 == 0 else "no" for i in range(N)]
    q8 = list(bf16)
    for i in range(disagreements):
        q8[i] = "no" if bf16[i] == "yes" else "yes"
    return q8, bf16


def _validate(obj: dict, ref: str) -> list[str]:
    base = contracts.validator("vlm-metrics.schema.json").schema["$id"]
    v = Draft202012Validator({"$ref": base + ref}, registry=contracts._registry())
    return [e.message for e in v.iter_errors(obj)]


@pytest.mark.req("P-015-05")
@pytest.mark.req("SC-015-01")
def test_the_gate_passes_at_475_of_500_and_fails_at_474() -> None:
    g475 = evaluate_gate(*_lists(25))
    assert (g475["agree"], g475["agreement"], g475["status"], g475["q8_0_path"]) == (475, 0.95, "pass", "accepted")
    g474 = evaluate_gate(*_lists(26))
    assert (g474["agree"], g474["agreement"], g474["status"], g474["q8_0_path"]) == (474, 0.948, "fail", "rejected")


@pytest.mark.req("FR-015-14")
def test_the_decision_uses_the_point_estimate_not_the_wilson_bound() -> None:
    g = evaluate_gate(*_lists(25))  # 475 / 500: the Wilson lower bound is below 0.95, the point estimate is not
    assert g["status"] == "pass"
    lo, hi = kit.wilson(475, 500)
    assert lo < 0.95 < hi
    assert (g["wilson95"]["lo"], g["wilson95"]["hi"]) == pytest.approx((lo, hi), rel=1e-9)


@pytest.mark.req("FR-015-14")
def test_the_wilson_interval_of_485_of_500_is_reported() -> None:
    g = evaluate_gate(*_lists(15))
    assert g["n"] == 500
    assert g["threshold"] == 0.95
    assert g["wilson95"]["lo"] == pytest.approx(0.9511, abs=5e-5)  # spec P-015-03 published values
    assert g["wilson95"]["hi"] == pytest.approx(0.9817, abs=5e-5)
    assert g["status"] == "pass"


@pytest.mark.req("FR-015-14")
@pytest.mark.parametrize("disagreements", [0, 1, 15, 25, 26, 100, 500])
def test_the_gate_object_follows_the_metrics_contract(disagreements: int) -> None:
    g = evaluate_gate(*_lists(disagreements))
    assert _validate(g, "#/$defs/gate") == []
    assert g["agree"] == 500 - disagreements
    assert g["status"] == ("pass" if 500 - disagreements >= 475 else "fail")


@pytest.mark.req("FR-015-14")
def test_agreement_counts_identical_normalised_answers() -> None:
    assert agreement(["yes", "no", "yes", "no"], ["yes", "no", "no", "no"]) == Fraction(3, 4)
    assert agreement(["yes", "no", "unparseable"], ["no", "yes", "yes"]) == 0
    assert isinstance(agreement(["yes"], ["yes"]), Fraction)


@pytest.mark.req("P-015-05")
@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.tuples(st.sampled_from(["yes", "no", "unparseable"]), st.sampled_from(["yes", "no", "unparseable"])),
        min_size=1,
        max_size=10_000,
    )
)
def test_property_agreement_is_symmetric_one_for_identical_lists_and_permutation_invariant(pairs: list) -> None:
    a, b = [x for x, _ in pairs], [y for _, y in pairs]
    ag = agreement(a, b)
    assert ag == Fraction(sum(1 for x, y in pairs if x == y), len(pairs))  # exact
    assert agreement(b, a) == ag  # MR1
    assert agreement(a, list(a)) == 1  # MR2
    idx = list(range(len(a)))
    random.Random(3).shuffle(idx)
    assert agreement([a[i] for i in idx], [b[i] for i in idx]) == ag  # MR3


@pytest.mark.req("FR-015-15")
def test_a_failed_gate_rejects_every_q8_row_with_the_prescribed_text_and_no_metric() -> None:
    gate = evaluate_gate(*_lists(26))
    rows = [_measured("cosmos-q8_0", t) for t in (1, 2, 3)] + [
        _measured("cosmos-q8_0", 1, reasoning=True),
        _measured("cosmos-bf16", 1),
        _measured("qwen-base", 1),
        _measured("constant", 1),
    ]
    out = apply_gate(rows, gate)
    assert len(out) == len(rows)
    for before, after in zip(rows, out, strict=True):
        if before["arm"] != "cosmos-q8_0":
            assert after == before
            continue
        assert (after["arm"], after["type"], after["reasoning"]) == (before["arm"], before["type"], before["reasoning"])
        assert after["status"] == "rejected"
        m = re.fullmatch(r"rejected: agreement a = (0\.[0-9]{1,6}) < 0\.95", after["reason"])
        assert m, after["reason"]
        assert float(m.group(1)) == pytest.approx(0.948, abs=5e-7)
        assert all(after[k] is None for k in ("balanced_accuracy", "f1", "auroc"))
        assert after["by_condition"] == []
        assert _validate(after, "#/$defs/row_a") == []


@pytest.mark.req("FR-015-15")
def test_a_passed_gate_leaves_every_row_unchanged() -> None:
    rows = [_measured("cosmos-q8_0", 1), _measured("cosmos-bf16", 1)]
    assert apply_gate(rows, evaluate_gate(*_lists(25))) == rows


def _measured(arm: str, qtype: int, *, reasoning: bool = False) -> dict:
    est = {"value": 0.8, "lo": 0.75, "hi": 0.85}
    return {
        "arm": arm,
        "reasoning": reasoning,
        "type": qtype,
        "status": "measured",
        "n": 1000,
        "balanced_accuracy": est,
        "f1": est,
        "unparseable_rate": 0.01,
        "error_rate": 0.0,
        "auroc": None,
        "by_condition": [{"condition": "day", "n": 250, "balanced_accuracy": 0.8}],
    }


def _gate_queries() -> list[dict]:
    return [
        {"query_id": f"q{t}-{i:03d}", "type": t, "truth": "yes" if i < 50 else "no", "gate_subset": True}
        for t in (1, 2, 4, 5, 6)
        for i in range(100)
    ]


@pytest.mark.req("FR-015-14")
def test_the_gate_subset_validator_accepts_the_prescribed_composition() -> None:
    validate_gate_subset(_gate_queries())


@pytest.mark.req("FR-015-14")
@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda qs: qs[:-1], id="499-queries"),
        pytest.param(
            lambda qs: [*qs, {"query_id": "x", "type": 1, "truth": "yes", "gate_subset": True}], id="501-queries"
        ),
        pytest.param(
            lambda qs: [*qs[:-1], {"query_id": "x", "type": 3, "truth": "1", "gate_subset": True}], id="a-type-3-query"
        ),
        pytest.param(
            lambda qs: [
                {**q, "truth": "yes"} if q["type"] == 1 and q["truth"] == "no" and q["query_id"].endswith("99") else q
                for q in qs
            ],
            id="51-yes-49-no",
        ),
        pytest.param(
            lambda qs: [{**q, "type": 2} if q["type"] == 1 and q["query_id"].endswith("0") else q for q in qs],
            id="type-counts-off",
        ),
        pytest.param(lambda qs: [], id="empty"),
    ],
)
def test_the_gate_subset_validator_rejects_any_other_composition(mutate) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        validate_gate_subset(mutate(_gate_queries()))


@pytest.mark.req("FR-015-14")
@pytest.mark.parametrize("n", [0, 1, 499, 501, 1000])
def test_the_gate_needs_exactly_500_aligned_answers(n: int) -> None:
    a = ["yes"] * n
    with pytest.raises(ValueError):  # noqa: PT011
        evaluate_gate(a, list(a))


@pytest.mark.req("FR-015-14")
def test_unequal_lists_are_refused() -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        agreement(["yes"], ["yes", "no"])
    with pytest.raises(ValueError):  # noqa: PT011
        agreement([], [])
    with pytest.raises(ValueError):  # noqa: PT011
        evaluate_gate(["yes"] * 500, ["yes"] * 499)
