# ruff: noqa: E501
"""T-015-041: the task-B protocol (two-alternative forced choice, single-clip questions) and its scoring over pairs.

Requirements: FR-015-36, FR-015-37, P-015-06, SC-015-05.

Spec: specs/015-vlm/spec.md
- FR-015-36: each pair is asked as a 2AFC question ("which clip is physically plausible?") in both orders and as a single-clip yes/no
  question for each clip; the BF16 path receives native video at 4 fps; the Q8_0 path receives frames sampled at 4 fps as an ordered
  image list, labelled "frame-list approximation".
- FR-015-37: each pair scores s_i = the fraction of its two orders answered correctly; accuracy s_bar with the interval
  s_bar +- t(0.975, 99) sd(s) / sqrt(100); the verdict "above chance" only if the lower bound exceeds 0.5; the detection rate per
  corruption, the single-clip AUROC, the position-bias index (fraction of "first clip" answers) and the physics-check baseline.
- P-015-06: (MR1) a responder that always picks the first clip scores s_bar = 0.5 exactly; (MR2) so does one that always picks the
  second; (MR3) swapping the presentation order of every pair leaves s_bar unchanged; a perfect responder scores 1 (100-pair tables, exact).
- SC-015-05: pair accuracy with its 95 % interval against chance = 0.5; "above chance" only by FR-015-37 (the interval is over pairs,
  spec section 8, because the two orders of a pair are not independent).

Oracle: hand calculation on 100-pair tables. For 60 pairs with s = 1, 20 with s = 0.5 and 20 with s = 0: s_bar = 0.70, sum of
squares 60 (0.3)^2 + 20 (0.2)^2 + 20 (0.7)^2 = 16, sample variance 16 / 99, sd = 0.40202, half-width = 1.984217 * 0.40202 / 10 = 0.07977
(t(0.975, 99) = 1.984217, scipy.stats.t.ppf; checked in tests/pipeline/test_t_015_041_reference_parity.py), so the interval is
[0.6202, 0.7798]; for 30 / 50 / 20 pairs: s_bar = 0.55, variance 12.25 / 99, half-width 0.0698, lower bound 0.480 (not above chance).
Pair counting for the AUROC (`_p015_kit.auroc_pairs`), `statistics.stdev` for the sample sd, the contract schema
(`contracts/vlm-metrics.schema.json#/$defs/row_b`, `jsonschema`).

Expected API of the implementation (package `pitstudio`, root environment), `pitstudio.reason.taskb`:
- `request_plan(pair, *, arm) -> list[dict]`: the four requests of a pair document (`plausibility-pairs` pair), in this order:
  presentation "pair-calibrated-first", "pair-corrupted-first", "single-calibrated", "single-corrupted"; each is
  `{"presentation", "truth", "input_mode", "label", "clips", "prompt", "frames"}` where `truth` is "first", "second", "yes", "no"
  respectively; `clips` the clip asset ids in presentation order; `prompt` "task_b_pair" or "task_b_single" (the pin names of the
  committed templates); arm "cosmos-bf16": `input_mode` "native-video", `label` None, `frames` `{"video_fps": 4}`; arm "cosmos-q8_0":
  `input_mode` "frame-list-approximation", `label` "frame-list approximation", `frames` maps each clip id to the ordered frame indices
  sampled at 4 fps (frame k * fps / 4 for k = 0, 1, ... below the frame count). ValueError for another arm.
- `score_task_b(records, *, arm, input_mode) -> dict`: `records` are dicts `{"pair_id", "corruption", "answers": {"pair-calibrated-first":
  label, "pair-corrupted-first": label}, "single_scores": {"calibrated": float, "corrupted": float} (optional)}` with labels "first",
  "second" or "unparseable"; returns a `row_b` of the metrics contract (`status` "measured", `n_pairs`, `accuracy` `{value, lo, hi}`,
  `verdict`, `position_bias`, `single_clip_auroc` (None without single scores), `detection_rate` per corruption).
- `physics_check_pair(calibrated_sim, corrupted_sim) -> float`: the pair score s_i of the physics baseline (states as in
  tests/unit/test_t_015_040_plausibility_pairs.py): 1.0 when the repose angle (< 5 deg) or the mass balance (>= 5 % increase, no inflow
  boundary) of exactly one clip flags it, which is then taken as the implausible clip.
"""

from __future__ import annotations

import random
import statistics
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from pitstudio.reason import taskb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))  # the shared kit lives in tests/unit
import _p015_contracts as contracts
import _p015_kit as kit

T975_99 = 1.984216951586417  # scipy.stats.t.ppf(0.975, 99); Student t table, 99 degrees of freedom: 1.9842
CORR = ("gravity-x0.3", "zero-friction", "mass-injection", "time-reversal", "interpenetration", "frozen-particles")
CF, KF = "pair-calibrated-first", "pair-corrupted-first"


def _rec(
    i: int, a_cf: str, a_kf: str, *, corruption: str | None = None, single: tuple[float, float] | None = None
) -> dict:
    r = {"pair_id": f"pair-{i:03d}", "corruption": corruption or CORR[i % 6], "answers": {CF: a_cf, KF: a_kf}}
    if single is not None:
        r["single_scores"] = {"calibrated": single[0], "corrupted": single[1]}
    return r


def _table(n_full: int, n_half: int, n_zero: int) -> list[dict]:
    """Records with s_i = 1 (both orders right), 0.5 (one right) and 0 (both wrong); calibrated-first truth "first", corrupted-first "second"."""
    recs = []
    for _ in range(n_full):
        recs.append(_rec(len(recs) + 1, "first", "second"))
    for _ in range(n_half):
        recs.append(_rec(len(recs) + 1, "first", "first"))  # right when calibrated is first, wrong when it is second
    for _ in range(n_zero):
        recs.append(_rec(len(recs) + 1, "second", "first"))
    assert len(recs) == 100
    return recs


def _score(recs: list[dict], **kw) -> dict:
    return taskb.score_task_b(recs, arm=kw.pop("arm", "cosmos-bf16"), input_mode=kw.pop("input_mode", "native-video"))


def _row_errors(row: dict) -> list[str]:
    base = contracts.validator("vlm-metrics.schema.json").schema["$id"]
    v = Draft202012Validator({"$ref": base + "#/$defs/row_b"}, registry=contracts._registry())
    return [e.message for e in v.iter_errors(row)]


# ------------------------------------------------------------------------------------------------ scoring over pairs
@pytest.mark.req("FR-015-37")
def test_the_accuracy_interval_is_over_pairs_with_the_t_quantile_for_99_degrees_of_freedom() -> None:
    row = _score(_table(60, 20, 20))
    s = [1.0] * 60 + [0.5] * 20 + [0.0] * 20
    mean, sd = statistics.fmean(s), statistics.stdev(s)
    assert mean == pytest.approx(0.70, abs=1e-12)
    half = T975_99 * sd / 10.0
    assert half == pytest.approx(0.07977, abs=5e-5)  # the hand calculation of the header
    assert row["n_pairs"] == 100
    assert row["accuracy"]["value"] == pytest.approx(mean, abs=1e-12)
    assert row["accuracy"]["lo"] == pytest.approx(mean - half, abs=1e-9)
    assert row["accuracy"]["hi"] == pytest.approx(mean + half, abs=1e-9)
    assert row["verdict"] == "above chance"  # 0.6202 > 0.5


@pytest.mark.req("SC-015-05")
def test_the_verdict_is_above_chance_only_if_the_lower_bound_exceeds_one_half() -> None:
    row = _score(_table(30, 50, 20))  # s_bar = 0.55, half-width 0.0698, lower bound 0.480
    assert row["accuracy"]["value"] == pytest.approx(0.55, abs=1e-12)
    assert row["accuracy"]["lo"] == pytest.approx(
        0.55 - T975_99 * statistics.stdev([1.0] * 30 + [0.5] * 50 + [0.0] * 20) / 10, abs=1e-9
    )
    assert row["accuracy"]["lo"] < 0.5
    assert row["verdict"] == "not above chance"
    assert (
        _score(_table(0, 100, 0))["verdict"] == "not above chance"
    )  # s_bar = 0.5 with zero variance: lo = hi = 0.5, not above


@pytest.mark.req("FR-015-37")
def test_the_pair_score_is_the_fraction_of_the_two_orders_answered_correctly_and_unparseable_is_wrong() -> None:
    row = _score(
        [_rec(i + 1, "first", "second") for i in range(50)] + [_rec(i + 51, "first", "unparseable") for i in range(50)]
    )
    assert row["accuracy"]["value"] == pytest.approx(0.75, abs=1e-12)  # 50 pairs with s = 1, 50 with s = 0.5


@pytest.mark.req("P-015-06")
def test_mr1_and_mr2_a_responder_that_always_picks_one_position_scores_exactly_one_half() -> None:
    for pick in ("first", "second"):
        row = _score([_rec(i + 1, pick, pick) for i in range(100)])
        assert row["accuracy"]["value"] == 0.5  # exact
        assert row["verdict"] == "not above chance"


@pytest.mark.req("P-015-06")
def test_a_perfect_responder_scores_one_and_an_adversarial_one_scores_zero() -> None:
    assert _score(_table(100, 0, 0))["accuracy"]["value"] == 1.0
    assert _score(_table(0, 0, 100))["accuracy"]["value"] == 0.0


_LABELS = st.sampled_from(["first", "second", "unparseable"])


@pytest.mark.req("P-015-06")
@settings(max_examples=200, deadline=None)
@given(st.lists(st.tuples(_LABELS, _LABELS), min_size=100, max_size=100), st.randoms(use_true_random=False))
def test_property_the_accuracy_equals_the_exact_oracle_and_mr3_swapping_orders_or_pairs_changes_nothing(
    table: list, rnd
) -> None:
    recs = [_rec(i + 1, a, b) for i, (a, b) in enumerate(table)]
    exact = sum((Fraction(int(a == "first") + int(b == "second"), 2) for a, b in table), Fraction(0)) / 100
    row = _score(recs)
    assert row["accuracy"]["value"] == pytest.approx(float(exact), abs=1e-15)
    # MR3: swapping the presentation order of every pair (the clip that was first is now second, so every label and every truth flips)
    flip = {"first": "second", "second": "first", "unparseable": "unparseable"}
    mirrored = [_rec(i + 1, flip[b], flip[a]) for i, (a, b) in enumerate(table)]
    assert _score(mirrored)["accuracy"]["value"] == pytest.approx(row["accuracy"]["value"], abs=1e-15)
    order = list(recs)
    rnd.shuffle(order)
    assert _score(order)["accuracy"]["value"] == pytest.approx(row["accuracy"]["value"], abs=1e-15)


# ------------------------------------------------------------------------------------------------ the other task-B statistics
@pytest.mark.req("FR-015-37")
def test_the_position_bias_index_is_the_fraction_of_first_clip_answers() -> None:
    assert _score([_rec(i + 1, "first", "first") for i in range(100)])["position_bias"] == 1.0
    assert _score([_rec(i + 1, "second", "second") for i in range(100)])["position_bias"] == 0.0
    # 200 trials: 150 "first" (75 pairs answer first twice, 25 pairs answer first once)
    recs = [_rec(i + 1, "first", "first") for i in range(50)] + [_rec(i + 51, "first", "second") for i in range(50)]
    assert _score(recs)["position_bias"] == pytest.approx(150 / 200, abs=1e-12)


@pytest.mark.req("FR-015-37")
def test_the_single_clip_auroc_ranks_calibrated_clips_above_corrupted_ones() -> None:
    perfect = [_rec(i + 1, "first", "second", single=(2.0 + 0.01 * i, -1.0 - 0.01 * i)) for i in range(100)]
    assert _score(perfect)["single_clip_auroc"] == 1.0
    rng = np.random.default_rng(6)
    cal = [round(float(x), 2) for x in rng.normal(0.4, 1.0, 100)]
    cor = [round(float(x), 2) for x in rng.normal(0.0, 1.0, 100)]
    recs = [_rec(i + 1, "first", "second", single=(cal[i], cor[i])) for i in range(100)]
    expected = kit.auroc_pairs(cal + cor, [True] * 100 + [False] * 100)  # ties (2-decimal rounding) count one half
    assert _score(recs)["single_clip_auroc"] == pytest.approx(expected, rel=1e-12)
    assert _score(_table(60, 20, 20))["single_clip_auroc"] is None  # no single-clip scores recorded


@pytest.mark.req("FR-015-37")
def test_the_detection_rate_is_reported_per_corruption() -> None:
    """Pairs of corruption c answered consistently (s = 1) or consistently wrong (s = 0): rate = fraction of its pairs with s = 1."""
    recs = []
    plan = {
        "gravity-x0.3": (16, 16),
        "zero-friction": (16, 12),
        "mass-injection": (17, 17),
        "time-reversal": (17, 0),
        "interpenetration": (17, 9),
        "frozen-particles": (17, 4),
    }
    for c, (n, ok) in plan.items():
        for j in range(n):
            recs.append(_rec(len(recs) + 1, *(("first", "second") if j < ok else ("second", "first")), corruption=c))
    assert len(recs) == 100
    rates = _score(recs)["detection_rate"]
    assert set(rates) == set(CORR)
    for c, (n, ok) in plan.items():
        assert rates[c] == pytest.approx(ok / n, abs=1e-12)


@pytest.mark.req("FR-015-37")
@pytest.mark.parametrize(
    ("arm", "mode"),
    [
        ("cosmos-q8_0", "frame-list-approximation"),
        ("cosmos-bf16", "native-video"),
        ("qwen-base", "frame-list-approximation"),
    ],
)
def test_the_row_follows_the_metrics_contract(arm: str, mode: str) -> None:
    recs = _table(60, 20, 20)
    row = _score(recs, arm=arm, input_mode=mode)
    assert (row["arm"], row["input_mode"], row["status"]) == (arm, mode, "measured")
    assert _row_errors(row) == []


# ------------------------------------------------------------------------------------------------ the protocol
def _pair(fps: float = 32.0, frames: int = 192) -> dict:
    def clip(kind: str) -> dict:
        return {
            "asset_id": f"clip-007-{kind}",
            "path": f"data/reason/task_b/007/{kind}.mp4",
            "sha256": kit.sha256_hex(kind.encode()),
            "duration_s": frames / fps,
            "frame_count": frames,
            "fps": fps,
            "camera_id": "cam-dump-02",
            "scene_id": "truck-dump-s07",
        }

    return {
        "pair_id": "pair-007",
        "scenario": "truck-dump",
        "source_run_id": "20261009T020000Z-a1",
        "corruptions": ["gravity-x0.3"],
        "calibrated": clip("calibrated"),
        "corrupted": clip("corrupted"),
        "confirmation": {
            "statistic": "fitted_g_ratio",
            "value": 0.301,
            "sustained_s": None,
            "own_detector_triggered": True,
            "calibrated_detectors_clear": True,
        },
    }


@pytest.mark.req("FR-015-36")
@pytest.mark.parametrize("arm", ["cosmos-q8_0", "cosmos-bf16"])
def test_every_pair_is_asked_in_both_orders_and_as_a_single_clip_question_for_each_clip(arm: str) -> None:
    plan = taskb.request_plan(_pair(), arm=arm)
    assert [r["presentation"] for r in plan] == [
        "pair-calibrated-first",
        "pair-corrupted-first",
        "single-calibrated",
        "single-corrupted",
    ]
    assert [r["truth"] for r in plan] == ["first", "second", "yes", "no"]
    assert [r["clips"] for r in plan] == [
        ["clip-007-calibrated", "clip-007-corrupted"],
        ["clip-007-corrupted", "clip-007-calibrated"],
        ["clip-007-calibrated"],
        ["clip-007-corrupted"],
    ]
    assert [r["prompt"] for r in plan] == ["task_b_pair", "task_b_pair", "task_b_single", "task_b_single"]


@pytest.mark.req("FR-015-36")
def test_the_bf16_path_receives_native_video_at_4_fps() -> None:
    for r in taskb.request_plan(_pair(), arm="cosmos-bf16"):
        assert (r["input_mode"], r["label"], r["frames"]) == ("native-video", None, {"video_fps": 4})


@pytest.mark.req("FR-015-36")
def test_the_q8_0_path_receives_frames_sampled_at_4_fps_as_an_ordered_image_list_labelled_as_an_approximation() -> None:
    for r in taskb.request_plan(_pair(), arm="cosmos-q8_0"):
        assert r["input_mode"] == "frame-list-approximation"
        assert r["label"] == "frame-list approximation"
        for clip_id in r["clips"]:
            idx = r["frames"][clip_id]
            assert idx == list(
                range(0, 192, 8)
            )  # 32 fps clip of 192 frames: one frame every 8 = 4 per second, 24 frames
            assert idx == sorted(idx)


@pytest.mark.req("FR-015-36")
def test_the_sampling_follows_the_clip_frame_rate() -> None:
    r = taskb.request_plan(_pair(fps=24.0, frames=144), arm="cosmos-q8_0")[2]
    assert r["frames"]["clip-007-calibrated"] == list(range(0, 144, 6))  # 24 / 4 = one frame every 6


@pytest.mark.req("FR-015-36")
def test_an_unknown_arm_is_refused() -> None:
    for arm in ("detector-rule", "constant", "", "cosmos"):
        with pytest.raises(ValueError):  # noqa: PT011
            taskb.request_plan(_pair(), arm=arm)


# ------------------------------------------------------------------------------------------------ physics baseline
def _sim(**kw) -> dict:
    t, n = 40, 30
    pos = np.zeros((t, n, 3))
    pos[:, :, 0] = np.arange(n) * 3.0
    pos[:, :, 2] = 50.0 - 0.5 * 9.80665 * (np.arange(t) / 30.0)[:, None] ** 2
    mass = kw.pop("mass", np.ones((t, n)))
    return {
        "pos": pos,
        "fps": 30.0,
        "radius": np.full(n, 0.05),
        "mass": mass,
        "frame_order": np.arange(t),
        "observables": {"repose_angle_deg": kw.pop("repose", 30.0)},
        "inflow_boundary": False,
    }


@pytest.mark.req("FR-015-37")
def test_the_physics_check_finds_the_corrupted_clip_by_repose_angle_and_by_mass_balance() -> None:
    assert taskb.physics_check_pair(_sim(), _sim(repose=2.0)) == 1.0  # repose 2 deg < 5 deg: friction removed
    heavier = np.concatenate([np.ones((40, 30)), np.ones((40, 3))], axis=1)  # 3 extra kg in every frame
    heavier[:, 30:] = 0.0
    heavier[10:, 30:] = 1.0  # appear at frame 10: +3 / 30 = 10 %
    corrupted = _sim()
    corrupted["pos"] = np.concatenate([corrupted["pos"], np.zeros((40, 3, 3)) + 100.0], axis=1)
    corrupted["radius"] = np.full(33, 0.05)
    corrupted["mass"] = heavier
    assert taskb.physics_check_pair(_sim(), corrupted) == 1.0


# ------------------------------------------------------------------------------------------------ hostile inputs
@pytest.mark.req("FR-015-37")
@pytest.mark.parametrize(
    "records",
    [
        pytest.param([], id="no-pairs"),
        pytest.param([_rec(1, "left", "second")], id="unknown-label"),
        pytest.param(
            [{"pair_id": "pair-001", "corruption": "gravity-x0.3", "answers": {CF: "first"}}], id="missing-order"
        ),
        pytest.param(
            [{"pair_id": "pair-001", "corruption": "levitation", "answers": {CF: "first", KF: "second"}}],
            id="unknown-corruption",
        ),
        pytest.param([_rec(1, "first", "second", single=(float("nan"), 0.0))], id="nan-single-score"),
        pytest.param([_rec(1, "first", "second", single=(float("inf"), 0.0))], id="inf-single-score"),
    ],
)
def test_hostile_records_raise_value_error(records: list[dict]) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        _score(records)


@pytest.mark.req("P-015-06")
def test_the_order_of_the_records_does_not_change_the_row() -> None:
    recs = _table(60, 20, 20)
    shuffled = list(recs)
    random.Random(5).shuffle(shuffled)
    a, b = _score(recs), _score(shuffled)
    for key in ("value", "lo", "hi"):
        assert a["accuracy"][key] == pytest.approx(b["accuracy"][key], abs=1e-12)
