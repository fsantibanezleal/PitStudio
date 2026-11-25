# ruff: noqa: E501
"""T-014-027: scripted-dig baseline, seed disjointness and freeze before evaluation.

Requirements: FR-014-30.

Spec: specs/014-robot-learning/spec.md FR-014-30: "The IL-2 baseline shall be a scripted joint-space dig (penetrate, drag,
curl, lift) parameterised by the initial terrain profile, tuned once on 20 training seeds disjoint from the evaluation seeds
and frozen before any policy evaluation." Plan: "seed-disjointness and freeze check (hash of the tuned parameters before
evaluation)". Seed blocks follow `contracts/il-task.schema.json` `$defs/seeds` (ranges [start, start + count); tune count 20;
eval count 100).

Oracle: hand-built seed ranges (the valid contract example `il-task.valid-il2.json` and arithmetic on it); a tuning loop
driven by a fake episode runner with known scores (hand calculation of the winner and of the call count: candidates x 20);
the SHA-256 of the canonical JSON text of the tuned parameters computed with `hashlib` over `json.dumps(sort_keys=True,
separators=(",", ":"))` (equal to RFC 8785 for these simple numbers and ASCII keys).

Expected API of the implementation (module `pitstudio.robots.baselines`):
    PHASES = ("penetrate", "drag", "curl", "lift")
    check_seed_blocks(seeds) -> None
        seeds is the `seeds` block of an IL-2 task (keys train, tune, eval; each {"start", "count"}). Raises ValueError naming
        the pair, for example "tune and eval", when two ranges overlap; naming `tune` when its count is not 20 or the key
        is missing; naming `eval` when its count is not 100. Adjacent ranges (end exclusive) do not overlap.
    freeze_params(params) -> FrozenParams
        FrozenParams (frozen dataclass) has `params` (a read-only mapping holding a deep copy of the input; item assignment
        raises TypeError) and `sha256` (hex digest of the canonical JSON of the parameters). ValueError naming the key for
        a non-finite parameter value.
    verify_frozen(frozen, params) -> None
        raises ValueError naming `sha256` unless the canonical-JSON digest of `params` equals frozen.sha256
    tune_scripted_dig(candidates, run_episode, seeds) -> TuneResult
        candidates: non-empty list of parameter dicts; run_episode(params, seed) -> float, higher is better (per-episode
        productivity); seeds: the seeds block. Calls run_episode exactly once per (candidate, tune seed) and only with tune
        seeds, never with train or eval seeds; picks the candidate with the highest mean score (first one on a tie).
        TuneResult has `frozen` (FrozenParams of the winner), `mean_score` (float), `scores` (list of the candidates' mean
        scores in input order) and `seeds_used` (the sorted tune seeds).
    ScriptedDig(frozen) -> baseline controller; a plain dict, or a FrozenParams whose digest no longer matches its
        parameters, raises TypeError or ValueError naming `frozen`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import pytest
from pitstudio.robots.baselines import (
    PHASES,
    ScriptedDig,
    check_seed_blocks,
    freeze_params,
    tune_scripted_dig,
    verify_frozen,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads(
    (ROOT / "specs" / "014-robot-learning" / "contracts" / "examples" / "il-task.valid-il2.json").read_text("utf-8")
)
SEEDS = EXAMPLE["seeds"]  # train 0..4095, eval 1,000,000..1,000,099, tune 2,000,000..2,000,019
PARAMS = {
    "approach_angle_deg": 35.0,
    "drag_speed_m_s": 0.4,
    "curl_rate_rad_s": 0.8,
    "lift_height_m": 0.6,
    "penetration_m": 0.25,
}


def digest(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@pytest.mark.req("FR-014-30")
def test_the_phases_run_in_the_order_penetrate_drag_curl_lift() -> None:
    assert PHASES == ("penetrate", "drag", "curl", "lift")


# ------------------------------------------------------------------------------------------ seed disjointness
@pytest.mark.req("FR-014-30")
def test_the_contract_example_seed_blocks_are_accepted() -> None:
    check_seed_blocks(SEEDS)
    assert SEEDS["tune"]["count"] == 20
    assert SEEDS["eval"]["count"] == 100


@pytest.mark.req("FR-014-30")
def test_adjacent_ranges_do_not_overlap_because_the_end_is_exclusive() -> None:
    seeds = copy.deepcopy(SEEDS)
    seeds["tune"]["start"] = seeds["eval"]["start"] + seeds["eval"]["count"]  # tune begins right after eval ends
    check_seed_blocks(seeds)
    seeds["train"] = {"start": 0, "count": seeds["eval"]["start"]}  # train ends exactly where eval starts
    check_seed_blocks(seeds)


@pytest.mark.req("FR-014-30")
@pytest.mark.parametrize(
    ("mutation", "pair"),
    [
        ({"tune": {"start": 1_000_050, "count": 20}}, r"tune.*eval|eval.*tune"),  # inside the eval range
        ({"tune": {"start": 999_990, "count": 20}}, r"tune.*eval|eval.*tune"),  # straddles the eval start
        ({"tune": {"start": 1_000_099, "count": 20}}, r"tune.*eval|eval.*tune"),  # one shared seed at the end
        ({"tune": {"start": 10, "count": 20}}, r"tune.*train|train.*tune"),  # inside the train range
        ({"train": {"start": 999_000, "count": 2_000}}, r"train.*eval|eval.*train"),
        ({"eval": {"start": 2_000_010, "count": 100}}, r"tune.*eval|eval.*tune"),
    ],
)
def test_overlapping_seed_ranges_raise_value_error_naming_the_pair(mutation, pair) -> None:
    seeds = {**copy.deepcopy(SEEDS), **mutation}
    with pytest.raises(ValueError, match=pair):
        check_seed_blocks(seeds)


@pytest.mark.req("FR-014-30")
@pytest.mark.parametrize(
    ("mutation", "name"),
    [
        ({"tune": {"start": 2_000_000, "count": 19}}, "tune"),
        ({"tune": {"start": 2_000_000, "count": 21}}, "tune"),
        ({"eval": {"start": 1_000_000, "count": 99}}, "eval"),
        ({"eval": {"start": 1_000_000, "count": 101}}, "eval"),
    ],
)
def test_the_tune_count_must_be_20_and_the_eval_count_100(mutation, name) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        check_seed_blocks({**copy.deepcopy(SEEDS), **mutation})


@pytest.mark.req("FR-014-30")
def test_a_missing_tune_block_is_rejected_for_the_baseline() -> None:
    seeds = copy.deepcopy(SEEDS)
    del seeds["tune"]
    with pytest.raises(ValueError, match=r"\btune\b"):
        check_seed_blocks(seeds)


# ------------------------------------------------------------------------------------------------ freezing
@pytest.mark.req("FR-014-30")
def test_freezing_hashes_the_canonical_json_of_the_parameters() -> None:
    frozen = freeze_params(PARAMS)
    assert frozen.sha256 == digest(PARAMS)
    assert (
        freeze_params({k: PARAMS[k] for k in reversed(list(PARAMS))}).sha256 == frozen.sha256
    )  # key order is irrelevant
    assert dict(frozen.params) == PARAMS


@pytest.mark.req("FR-014-30")
def test_frozen_parameters_are_a_read_only_copy() -> None:
    src = copy.deepcopy(PARAMS)
    frozen = freeze_params(src)
    src["drag_speed_m_s"] = 9.9  # changing the source afterwards does not change the frozen copy
    assert frozen.params["drag_speed_m_s"] == 0.4
    with pytest.raises(TypeError):
        frozen.params["drag_speed_m_s"] = 1.0  # type: ignore[index]
    with pytest.raises(TypeError):
        del frozen.params["lift_height_m"]  # type: ignore[attr-defined]


@pytest.mark.req("FR-014-30")
def test_verify_frozen_accepts_the_same_parameters_and_rejects_any_change() -> None:
    frozen = freeze_params(PARAMS)
    verify_frozen(frozen, copy.deepcopy(PARAMS))
    for key in PARAMS:
        changed = {**PARAMS, key: PARAMS[key] * (1.0 + 1e-9)}
        with pytest.raises(ValueError, match="sha256"):
            verify_frozen(frozen, changed)
    with pytest.raises(ValueError, match="sha256"):
        verify_frozen(frozen, {**PARAMS, "extra": 1.0})
    with pytest.raises(ValueError, match="sha256"):
        verify_frozen(frozen, {k: v for k, v in PARAMS.items() if k != "penetration_m"})


@pytest.mark.req("FR-014-30")
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_freezing_a_non_finite_parameter_raises_value_error_naming_the_key(bad) -> None:
    with pytest.raises(ValueError, match="drag_speed_m_s"):
        freeze_params({**PARAMS, "drag_speed_m_s": bad})


@pytest.mark.req("FR-014-30")
def test_the_baseline_requires_frozen_parameters_that_still_match_their_digest() -> None:
    frozen = freeze_params(PARAMS)
    ScriptedDig(frozen)  # accepted
    with pytest.raises((TypeError, ValueError), match="frozen"):
        ScriptedDig(dict(PARAMS))
    tampered = copy.copy(frozen)
    object.__setattr__(tampered, "sha256", "0" * 64)
    with pytest.raises((TypeError, ValueError), match="frozen"):
        ScriptedDig(tampered)


# ------------------------------------------------------------------------------------------------ tuning
@pytest.mark.req("FR-014-30")
def test_tuning_uses_only_the_20_tune_seeds_once_per_candidate_and_picks_the_best_mean() -> None:
    candidates = [
        {"penetration_m": 0.1, "drag_speed_m_s": 0.3},
        {"penetration_m": 0.2, "drag_speed_m_s": 0.3},  # best: score 2.0 + 0.001 * seed offset (mean over the seeds)
        {"penetration_m": 0.3, "drag_speed_m_s": 0.3},
    ]
    base = {0.1: 1.0, 0.2: 2.0, 0.3: 1.5}
    tune_start = SEEDS["tune"]["start"]
    calls: list[tuple[float, int]] = []

    def run_episode(params: dict, seed: int) -> float:
        calls.append((params["penetration_m"], seed))
        return base[params["penetration_m"]] + 0.001 * (seed - tune_start)

    result = tune_scripted_dig(candidates, run_episode, SEEDS)
    tune_seeds = set(range(tune_start, tune_start + 20))
    assert len(calls) == 3 * 20  # tuned once: one run per (candidate, seed)
    assert {s for _p, s in calls} == tune_seeds
    assert len(set(calls)) == len(calls)
    assert result.seeds_used == sorted(tune_seeds)
    # mean offset of seeds 0..19 is 9.5, so means are base + 0.0095
    assert result.scores == pytest.approx([1.0095, 2.0095, 1.5095], rel=1e-12)
    assert result.mean_score == pytest.approx(2.0095, rel=1e-12)
    assert dict(result.frozen.params) == candidates[1]
    assert result.frozen.sha256 == digest(candidates[1])


@pytest.mark.req("FR-014-30")
def test_a_tie_picks_the_first_candidate() -> None:
    candidates = [{"penetration_m": 0.1}, {"penetration_m": 0.2}]
    result = tune_scripted_dig(candidates, lambda _p, _s: 1.0, SEEDS)
    assert dict(result.frozen.params) == candidates[0]


@pytest.mark.req("FR-014-30")
def test_tuning_refuses_overlapping_or_miscounted_seeds_before_running_any_episode() -> None:
    calls: list[int] = []

    def run_episode(_params: dict, seed: int) -> float:
        calls.append(seed)
        return 0.0

    bad = {**copy.deepcopy(SEEDS), "tune": {"start": 1_000_010, "count": 20}}  # inside the evaluation range
    with pytest.raises(ValueError, match=r"tune.*eval|eval.*tune"):
        tune_scripted_dig([{"penetration_m": 0.1}], run_episode, bad)
    with pytest.raises(ValueError, match=r"\bcandidates\b"):
        tune_scripted_dig([], run_episode, SEEDS)
    assert calls == []  # nothing ran


@pytest.mark.req("FR-014-30")
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_non_finite_episode_score_aborts_the_tuning(bad) -> None:
    with pytest.raises(ValueError, match="score"):
        tune_scripted_dig([{"penetration_m": 0.1}], lambda _p, _s: bad, SEEDS)
