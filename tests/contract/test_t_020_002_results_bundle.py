"""T-020-002: results bundle schema, generated types and tools/check_results.py.

Requirements: DC-020-02, FR-020-23, FR-020-29.

Spec: specs/020-web-knowledge/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/results.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/results.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import json

import _contract_kit as kit
import pytest

SPEC = "020-web-knowledge"


@pytest.mark.req("DC-020-02")
def test_results_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("results.schema.json")


@pytest.mark.req("DC-020-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["results.schema.json"], valid=True))
def test_results_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-020-02")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["results.schema.json"], valid=False))
def test_results_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-020-02")
def test_results_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["results.schema.json"])


@pytest.mark.req("DC-020-02")
def test_results_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["results.schema.json"])


VERDICTS = ("challenger-better", "baseline-better", "no-significant-difference")


def _base() -> dict:
    ex = next(e for e in kit.load_examples(SPEC, ["results.schema.json"]) if e["file"] == "results.valid.json")
    return kit.read_json(ex["path"])


def _write(tmp_path, doc: dict | str, name: str | None = None):
    d = tmp_path / "results"
    d.mkdir(parents=True, exist_ok=True)
    stem = name or (doc["id"] if isinstance(doc, dict) else "bad")
    p = d / f"{stem}.json"
    p.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")
    return p


def expected_verdict(lo: float, hi: float, orientation: str) -> str:
    """FR-020-22 written out: the interval is oriented so that positive means the challenger is better."""
    olo, ohi = (lo, hi) if orientation == "higher-is-better" else (-hi, -lo)
    if olo > 0:
        return "challenger-better"
    if ohi < 0:
        return "baseline-better"
    return "no-significant-difference"


# Hand truth table (interval of challenger - baseline, orientation, verdict); touching 0 counts as no difference.
TRUTH = [
    (1.0, 3.0, "higher-is-better", "challenger-better"),
    (-3.0, -1.0, "higher-is-better", "baseline-better"),
    (-1.0, 2.0, "higher-is-better", "no-significant-difference"),
    (0.0, 2.0, "higher-is-better", "no-significant-difference"),
    (-2.0, 0.0, "higher-is-better", "no-significant-difference"),
    (1.0, 3.0, "lower-is-better", "baseline-better"),
    (-3.0, -1.0, "lower-is-better", "challenger-better"),
    (-1.0, 2.0, "lower-is-better", "no-significant-difference"),
    (0.0, 2.0, "lower-is-better", "no-significant-difference"),
    (-2.0, 0.0, "lower-is-better", "no-significant-difference"),
]


def _paired(doc: dict, lo: float, hi: float, orientation: str, verdict: str) -> dict:
    row = doc["rows"][0]
    row["metric"]["orientation"] = orientation
    row["interval"] = {"lo": lo, "hi": hi, "level": 0.95, "method": "paired-t"}
    row["verdict"] = verdict
    doc["rows"] = [row]
    doc["criteria"] = []  # criterion status (FR-020-24) is another rule; keep it out of the verdict cases
    return doc


@pytest.mark.req("DC-020-02")
@pytest.mark.parametrize(
    "name",
    [
        "results.valid.json",
        "results.valid-cosmos.json",
        "results.valid-single-event.json",
        "results.valid-acceleration.json",
    ],
)
def test_check_results_accepts_the_valid_examples(tmp_path, name: str) -> None:
    # Expected CLI: `python tools/check_results.py FILE...`; exit 0 clean, 1 on findings (each names the file and the
    # comparison id), 2 on usage error; never a traceback.
    ex = next(e for e in kit.load_examples(SPEC, ["results.schema.json"]) if e["file"] == name)
    doc = kit.read_json(ex["path"])
    code, out = kit.run_tool("check_results.py", str(_write(tmp_path, doc)))
    assert code == 0, out


@pytest.mark.req("FR-020-23")
@pytest.mark.parametrize(("lo", "hi", "orientation", "want"), TRUTH)
def test_check_results_accepts_the_derived_verdict_and_rejects_every_other(tmp_path, lo, hi, orientation, want) -> None:
    assert expected_verdict(lo, hi, orientation) == want  # the hand table agrees with the rule of FR-020-22
    good = _paired(_base(), lo, hi, orientation, want)
    code, out = kit.run_tool("check_results.py", str(_write(tmp_path, good)))
    assert code == 0, out
    for other in VERDICTS:
        if other == want:
            continue
        bad = _paired(_base(), lo, hi, orientation, other)
        code, out = kit.run_tool("check_results.py", str(_write(tmp_path / other, bad)))
        assert code == 1, f"stored verdict {other} for [{lo}, {hi}] {orientation} must be rejected: {out}"
        assert bad["id"] in out, f"the finding must name the entry {bad['id']!r}: {out[:300]}"


def _lo_above_hi(doc: dict) -> None:
    doc["rows"][0]["interval"].update(lo=5.0, hi=1.0)


def _paired_n_one(doc: dict) -> None:
    doc["rows"][0]["n"] = 1


def _no_orientation(doc: dict) -> None:
    del doc["rows"][0]["metric"]["orientation"]


@pytest.mark.req("FR-020-23")
@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_lo_above_hi, id="lo-above-hi"),
        pytest.param(_paired_n_one, id="paired-claim-with-n-1"),
        pytest.param(_no_orientation, id="no-orientation"),
    ],
)
def test_check_results_rejects_structural_failures_naming_the_entry(tmp_path, mutate) -> None:
    doc = _base()
    mutate(doc)
    code, out = kit.run_tool("check_results.py", str(_write(tmp_path, doc)))
    assert code == 1, out
    assert doc["id"] in out
    assert "Traceback" not in out


@pytest.mark.req("FR-020-23")
@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_check_results_rejects_a_non_finite_bound_without_a_traceback(tmp_path, literal: str) -> None:
    text = json.dumps(_base()).replace('"hi": 31.9', f'"hi": {literal}')
    assert literal in text
    code, out = kit.run_tool("check_results.py", str(_write(tmp_path, text, "a1-ppo-vs-sptf")))
    assert code == 1, out
    assert "Traceback" not in out


def _exact_mcnemar_p(b: int, c: int) -> float:
    """Two-sided exact McNemar p: 2 * P(X <= min(b, c)), X ~ Binomial(b + c, 1/2), capped at 1 (hand formula)."""
    from math import comb

    n = b + c
    tail = sum(comb(n, k) for k in range(0, min(b, c) + 1)) / 2**n
    return min(1.0, 2 * tail)


def _mcnemar_doc(b: int, c: int, p: float, verdict: str) -> dict:
    ex = next(e for e in kit.load_examples(SPEC, ["results.schema.json"]) if e["file"] == "results.valid-cosmos.json")
    doc = kit.read_json(ex["path"])
    row = next(r for r in doc["rows"] if r["kind"] == "mcnemar")
    row.update(b=b, c=c, n=max(row["n"], b + c), p_value=p, verdict=verdict)
    doc["rows"] = [row]
    doc["criteria"] = []
    return doc


@pytest.mark.req("FR-020-23")
def test_check_results_mcnemar_rows_follow_the_exact_test_and_the_discordant_counts(tmp_path) -> None:
    # b = challenger right / baseline wrong, c = the reverse (schema description). p from the exact binomial formula.
    b, c = 40, 15
    p = _exact_mcnemar_p(b, c)  # ~0.00056 < 0.05, so the direction comes from b > c: challenger-better
    assert p < 0.05
    code, out = kit.run_tool(
        "check_results.py", str(_write(tmp_path / "ok", _mcnemar_doc(b, c, p, "challenger-better")))
    )
    assert code == 0, out
    wrong_direction = _mcnemar_doc(b, c, p, "baseline-better")
    code, out = kit.run_tool("check_results.py", str(_write(tmp_path / "dir", wrong_direction)))
    assert code == 1, out
    assert wrong_direction["id"] in out, out
    wrong_p = _mcnemar_doc(b, c, 0.03, "challenger-better")  # p-value differs from the exact test
    code, out = kit.run_tool("check_results.py", str(_write(tmp_path / "p", wrong_p)))
    assert code == 1, out
    assert wrong_p["id"] in out, out


@pytest.mark.req("FR-020-29")
@pytest.mark.parametrize("tool", ["ovrtx", "isaac-sim", "isaacsim", "kit", "replicator", "tensorrt-rtx"])
def test_check_results_rejects_performance_data_of_licence_restricted_software(tmp_path, tool: str) -> None:
    # FR-000-08: Isaac Sim, Kit, Replicator, ovrtx and TensorRT for RTX performance is never published.
    ex = next(
        e for e in kit.load_examples(SPEC, ["results.schema.json"]) if e["file"] == "results.valid-acceleration.json"
    )
    doc = kit.read_json(ex["path"])
    doc["conditions"]["versions"][tool] = "1.0.0"
    code, out = kit.run_tool("check_results.py", str(_write(tmp_path, doc)))
    assert code == 1, out
    assert doc["id"] in out
    assert "Traceback" not in out


@pytest.mark.req("FR-020-29")
def test_check_results_rejects_a_row_whose_model_is_restricted_software(tmp_path) -> None:
    ex = next(
        e for e in kit.load_examples(SPEC, ["results.schema.json"]) if e["file"] == "results.valid-acceleration.json"
    )
    doc = kit.read_json(ex["path"])
    doc["rows"][0]["model"] = "ovrtx-lidar"
    code, out = kit.run_tool("check_results.py", str(_write(tmp_path, doc)))
    assert code == 1, out
    assert doc["id"] in out
