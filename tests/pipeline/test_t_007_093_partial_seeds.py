# ruff: noqa: E501, PT018
"""T-007-093: a comparison over fewer than 30 paired seeds is `partial`: it carries the number of seeds present and missing and no interval verdict.

Requirements: FR-007-47, FR-007-30, FR-000-05, SC-000-02.

Spec: specs/007-haulage-dispatch/spec.md FR-007-47 (while fewer than 30 paired seeds exist for a dispatcher comparison, `s50_evaluate` writes the comparison with status `partial`, the number of seeds present and the number missing, and reports no interval verdict ("better than" or "no significant difference")
for it; SC-000-02, FR-000-05), FR-007-30 (fewer than 30 paired seeds: the verdict is `insufficient-evidence` and no output says "better"), FR-007-29 (the comparison object of the evaluation table) and the contract `dispatch-eval.schema.json` (`$defs/comparison`).

Oracle: the number 30 of FR-007-30 and FR-007-47 and plain counting: seeds present = the seeds that both arms report with a finite value; seeds missing = 30 - present (never negative); the comparison for 30 or more pairs is `complete`; hand-built arms of known sizes; the JSON schema validator of the contract (which must accept the added fields); `json.dumps` scans for the forbidden verdict words.

Added fields of a comparison object (stated here: the contract's `$defs/comparison` has `additionalProperties: false` and no such field, so FR-007-47 needs it extended: a spec 001 change request listed in the report): `status` ("partial" | "complete"), `seeds_present` (int >= 0), `seeds_missing` (int >= 0).

Expected API (as in test_t_007_055_dispatch_eval.py, `pitstudio_pipeline.dispatch.evaluate`):
    paired_comparison(learned_th, baseline_th, *, learned, baseline, fleet_size) -> dict: `status` is "partial" with `seeds_present` = the number of seeds both arms report with a finite value and `seeds_missing` = 30 - seeds_present when seeds_present < 30; otherwise "complete" with `seeds_missing` 0;
        a partial comparison has verdict `insufficient-evidence` (with `reason`), no interval verdict and no "better" text; `n_pairs` equals `seeds_present`; the result validates against the extended `$defs/comparison`.
    assemble_table(rows, ...) -> dict: every comparison of the table carries the fields; a table with a partial comparison is still valid against the extended `dispatch-eval` schema.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit as kit
from pitstudio_pipeline.dispatch.evaluate import assemble_table, paired_comparison
from pitstudio_pipeline.dispatch.seeds import test_seeds as preregistered_seeds

SETTINGS = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
COMPARISON = kit.schema_validator("dispatch-eval", "comparison")
TABLE = kit.schema_validator("dispatch-eval")
SEEDS = [int(s) for s in preregistered_seeds(60)]
INTERVAL_WORDS = ("better", "no-significant-difference", "no significant difference")


def arms(n: int, effect: float = 300.0, seeds=None):
    seeds = SEEDS[:n] if seeds is None else seeds
    rng = np.random.default_rng(93)
    base = {s: 3000.0 + float(rng.normal(0, 40)) for s in seeds}
    return {s: v + effect for s, v in base.items()}, base


def compare(a, b):
    return paired_comparison(a, b, learned="ppo", baseline="sptf", fleet_size=24)


# ---------------------------------------------------------------------------------------------------------------------
# the boundary
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-47")
@pytest.mark.parametrize("n", [1, 2, 10, 28, 29])
def test_fewer_than_30_paired_seeds_is_partial_with_the_counts_and_no_interval_verdict(n):
    c = compare(*arms(n))
    assert c["status"] == "partial"
    assert (c["seeds_present"], c["seeds_missing"]) == (n, 30 - n)
    assert c["n_pairs"] == n
    assert c["verdict"] == "insufficient-evidence"
    text = json.dumps(c).lower()
    assert not any(w in text for w in INTERVAL_WORDS)
    assert not list(COMPARISON.iter_errors(c)), [e.message for e in COMPARISON.iter_errors(c)][:3]


@pytest.mark.req("FR-007-47")
@pytest.mark.parametrize("n", [30, 31, 45, 60])
def test_30_or_more_paired_seeds_is_complete_with_nothing_missing(n):
    c = compare(*arms(n))
    assert c["status"] == "complete"
    assert (c["seeds_present"], c["seeds_missing"]) == (n, 0)
    assert c["n_pairs"] == n and c["verdict"] == "learned-better"  # a 300 t/h effect on a 40 t/h noise: decided
    assert not list(COMPARISON.iter_errors(c))


@pytest.mark.req("FR-007-47")
def test_exactly_one_seed_short_is_partial_and_one_more_makes_it_complete():
    a29, b29 = arms(29)
    c29 = compare(a29, b29)
    assert (c29["status"], c29["seeds_present"], c29["seeds_missing"]) == ("partial", 29, 1)
    a30, b30 = arms(30)
    c30 = compare(a30, b30)
    assert (c30["status"], c30["seeds_present"], c30["seeds_missing"]) == ("complete", 30, 0)
    assert c30["verdict"] != "insufficient-evidence"


@pytest.mark.req("FR-007-47")
@SETTINGS
@given(n=st.integers(1, 60), effect=st.floats(-500, 500))
def test_present_plus_missing_is_thirty_until_thirty_are_present_and_the_verdict_follows_the_status(n, effect):
    c = compare(*arms(n, effect))
    if n < 30:
        assert (
            c["status"] == "partial"
            and c["seeds_present"] + c["seeds_missing"] == 30
            and c["verdict"] == "insufficient-evidence"
        )
    else:
        assert c["status"] == "complete" and c["seeds_missing"] == 0 and c["verdict"] != "insufficient-evidence"
    assert c["seeds_present"] == n and c["seeds_missing"] >= 0


# ---------------------------------------------------------------------------------------------------------------------
# what counts as a paired seed
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-47")
def test_only_seeds_present_in_both_arms_count_as_paired():
    a, b = arms(40)
    for s in SEEDS[:5]:
        del a[s]  # the learned arm lacks 5 seeds: 35 remain in both
    c = compare(a, b)
    assert (c["status"], c["seeds_present"], c["seeds_missing"]) == ("complete", 35, 0)
    for s in SEEDS[5:12]:
        del a[s]  # 7 more: 28 paired
    c = compare(a, b)
    assert (c["status"], c["seeds_present"], c["seeds_missing"]) == ("partial", 28, 2)
    assert c["verdict"] == "insufficient-evidence"


@pytest.mark.req("FR-007-47")
def test_a_seed_with_a_non_finite_value_is_not_a_usable_pair():
    a, b = arms(30)
    a[SEEDS[3]] = float("nan")
    c = compare(a, b)
    assert (c["status"], c["seeds_present"], c["seeds_missing"]) == ("partial", 29, 1)
    assert c["verdict"] == "insufficient-evidence"
    assert not any(w in json.dumps(c).lower() for w in INTERVAL_WORDS)


@pytest.mark.req("FR-007-47")
def test_arms_with_no_common_seed_have_zero_present_and_thirty_missing():
    a, _ = arms(30, seeds=SEEDS[:30])
    _, b = arms(30, seeds=SEEDS[30:60])
    c = compare(a, b)
    assert (c["status"], c["seeds_present"], c["seeds_missing"], c["n_pairs"]) == ("partial", 0, 30, 0)
    assert c["verdict"] == "insufficient-evidence" and not list(COMPARISON.iter_errors(c))


# ---------------------------------------------------------------------------------------------------------------------
# the table
# ---------------------------------------------------------------------------------------------------------------------
def row(seed, dispatcher, fleet, th):
    return {
        "seed": seed, "dispatcher": dispatcher, "fleet_size": fleet, "production_t_per_h": th, "queue_time_mean_min": 2.0, "loader_utilisation_frac": 0.85,
        "match_factor": 0.9, "truck_hours_per_kt": 8.0, "loader_hours_per_kt": 0.7,
    }  # fmt: skip


def rows_for(fleets, dispatchers, n):
    rng = np.random.default_rng(7)
    effects = {"sptf": 0.0, "lp": 20.0, "ppo": 90.0, "attention": 140.0}
    rows = []
    for f in fleets:
        for s in SEEDS[:n]:
            common = float(rng.normal(0, 60))
            noise = [float(rng.normal(0, 20)) for _ in dispatchers]
            rows.extend(
                row(s, d, f, 2000.0 + 30.0 * f + effects[d] + common + noise[k]) for k, d in enumerate(dispatchers)
            )
    return rows


def table_args(n):
    ex = kit.example("dispatch-eval.valid.json")
    return {
        "id": "a1-dispatch-eval",
        "recipe": "a1-dispatch-evaluate",
        "engine": ex["engine"],
        "scenarios": [{"fleet_size": 12, "bundle_sha256": "ab" * 32}],
        "test_seeds": SEEDS[:n],
        "honesty": ex["honesty"],
    }


@pytest.mark.req("FR-007-47")
@pytest.mark.parametrize("n", [12, 29])
def test_every_comparison_of_a_table_with_fewer_than_30_seeds_is_partial_and_the_table_is_valid(n):
    t = assemble_table(rows_for((12,), ("sptf", "lp", "ppo", "attention"), n), **table_args(n))
    assert t["comparisons"]
    for c in t["comparisons"]:
        assert (c["status"], c["seeds_present"], c["seeds_missing"]) == ("partial", n, 30 - n)
        assert c["verdict"] == "insufficient-evidence"
    assert not any(w in json.dumps(t["comparisons"]).lower() for w in INTERVAL_WORDS)
    assert not list(TABLE.iter_errors(t)), [e.message for e in TABLE.iter_errors(t)][:3]


@pytest.mark.req("FR-007-47")
def test_a_table_with_30_seeds_is_complete_and_has_interval_verdicts():
    t = assemble_table(rows_for((12,), ("sptf", "lp", "ppo", "attention"), 30), **table_args(30))
    assert all(c["status"] == "complete" and c["seeds_missing"] == 0 for c in t["comparisons"])
    assert {c["verdict"] for c in t["comparisons"]} <= {
        "learned-better",
        "baseline-better",
        "no-significant-difference",
    }
    assert not list(TABLE.iter_errors(t))


@pytest.mark.req("FR-007-47")
def test_partial_and_complete_comparisons_can_sit_in_one_table():
    rows = rows_for((12,), ("sptf", "lp", "ppo"), 30)
    rows = [r for r in rows if not (r["dispatcher"] == "lp" and r["seed"] in SEEDS[:4])]  # the lp arm is 4 seeds short
    t = assemble_table(rows, **table_args(30))
    by = {c["baseline"]: c for c in t["comparisons"]}
    assert (by["lp"]["status"], by["lp"]["seeds_present"], by["lp"]["seeds_missing"]) == ("partial", 26, 4)
    assert (by["sptf"]["status"], by["sptf"]["seeds_present"]) == ("complete", 30)
    assert by["lp"]["verdict"] == "insufficient-evidence" and by["sptf"]["verdict"] != "insufficient-evidence"
    assert not list(TABLE.iter_errors(t))


@pytest.mark.req("FR-007-47")
@pytest.mark.parametrize("bad", [True, "30", None, 2.5])
def test_hostile_seed_keys_never_produce_a_count(bad):
    a, b = arms(30)
    a[bad] = 1.0  # type: ignore[index]
    with pytest.raises((TypeError, ValueError)):
        compare(a, b)
