"""Task-B protocol and scoring (FR-015-36, FR-015-37, P-015-06, SC-015-05).

Every pair is asked four ways: a two-alternative forced choice ("which clip is physically plausible?") in both orders,
and a single-clip yes/no question for each clip. The BF16 path receives native video at 4 fps; the Q8_0 path (and the
Qwen control) receive frames sampled at 4 fps as an ordered image list, labelled "frame-list approximation".

Scoring is over pairs, not trials, because the two orders of a pair are not independent: the pair score is the
fraction of its two orders answered correctly, the accuracy is the mean pair score with a t interval over the pairs,
and "above chance" needs the lower bound above 0.5.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any

from pitstudio.reason import plausibility
from pitstudio.reason.stats import auroc, t_quantile

SAMPLE_FPS = 4
FRAME_LIST_LABEL = "frame-list approximation"
CORRECT_FIRST = "pair-calibrated-first"
CORRECT_SECOND = "pair-corrupted-first"
LABELS = ("first", "second", "unparseable")
ARMS = {
    "cosmos-bf16": "native-video",
    "cosmos-q8_0": "frame-list-approximation",
    "qwen-base": "frame-list-approximation",
}
CHANCE = 0.5
LEVEL = 0.975


def _frame_indices(clip: Mapping[str, Any]) -> list[int]:
    """Frames sampled at 4 fps: frame k * fps / 4 (nearest, halves up) for k = 0, 1, ... below the frame count."""
    out, k = [], 0
    while (idx := math.floor(k * clip["fps"] / SAMPLE_FPS + 0.5)) < clip["frame_count"]:
        out.append(idx)
        k += 1
    return out


def request_plan(pair: Mapping[str, Any], *, arm: str) -> list[dict[str, Any]]:
    """The four requests of a pair: both pair orders, then the single-calibrated and single-corrupted questions."""
    if arm not in ARMS:
        raise ValueError(f"unknown task-B arm {arm!r}; known: {sorted(ARMS)}")
    mode = ARMS[arm]
    cal, cor = pair["calibrated"], pair["corrupted"]
    shape = [
        ("pair-calibrated-first", "first", [cal, cor], "task_b_pair"),
        ("pair-corrupted-first", "second", [cor, cal], "task_b_pair"),
        ("single-calibrated", "yes", [cal], "task_b_single"),
        ("single-corrupted", "no", [cor], "task_b_single"),
    ]
    plan = []
    for presentation, truth, clips, prompt in shape:
        frames = (
            {"video_fps": SAMPLE_FPS} if mode == "native-video" else {c["asset_id"]: _frame_indices(c) for c in clips}
        )
        plan.append(
            {
                "presentation": presentation,
                "truth": truth,
                "input_mode": mode,
                "label": None if mode == "native-video" else FRAME_LIST_LABEL,
                "clips": [c["asset_id"] for c in clips],
                "prompt": prompt,
                "frames": frames,
            }
        )
    return plan


def _pair_score(first_order: str, second_order: str) -> Fraction:
    """Fraction of the two orders answered correctly: "first" when the calibrated clip is first, "second" otherwise."""
    return Fraction(int(first_order == "first") + int(second_order == "second"), 2)


def _interval(scores: Sequence[Fraction]) -> tuple[float, float, float]:
    """Mean pair score and its t interval over the pairs: mean +- t(0.975, n - 1) sd / sqrt(n)."""
    n = len(scores)
    if n < 2:
        raise ValueError("an interval over pairs needs at least two pairs")
    mean = sum(scores, Fraction(0)) / n
    variance = sum(((s - mean) ** 2 for s in scores), Fraction(0)) / (n - 1)
    half = t_quantile(LEVEL, n - 1) * math.sqrt(float(variance)) / math.sqrt(n)
    return float(mean), float(mean) - half, float(mean) + half


def _estimate(scores: Sequence[Fraction]) -> dict[str, float]:
    value, lo, hi = _interval(scores)
    return {"value": value, "lo": lo, "hi": hi}


def _verdict(lo: float) -> str:
    return "above chance" if lo > CHANCE else "not above chance"


def _detection_rate(corruptions: Sequence[str], scores: Sequence[Fraction]) -> dict[str, float] | None:
    rates = {}
    for name in plausibility.CORRUPTIONS:
        mine = [s for c, s in zip(corruptions, scores, strict=True) if c == name]
        if not mine:
            return None  # a corruption without pairs has no rate; the contract wants all six or none
        rates[name] = sum(1 for s in mine if s == 1) / len(mine)
    return rates


def _check_corruption(name: Any) -> str:
    if name not in plausibility.CORRUPTIONS:
        raise ValueError(f"unknown corruption {name!r}")
    return str(name)


def score_task_b(records: Sequence[Mapping[str, Any]], *, arm: str, input_mode: str) -> dict[str, Any]:
    """One measured `row_b` of the metrics contract from the answers of one arm over the pairs.

    A record: `{"pair_id", "corruption", "answers": {"pair-calibrated-first", "pair-corrupted-first"},
    "single_scores": {"calibrated", "corrupted"} (optional)}`; answers are "first", "second" or "unparseable"
    (unparseable is always wrong).
    """
    if arm not in ARMS:
        raise ValueError(f"unknown task-B arm {arm!r}")
    if len(records) == 0:
        raise ValueError("n = 0: no pairs to score")
    scores, corruptions, firsts = [], [], 0
    cal_scores: list[float] = []
    cor_scores: list[float] = []
    have_single = True
    for r in records:
        answers = r.get("answers")
        if not isinstance(answers, Mapping) or CORRECT_FIRST not in answers or CORRECT_SECOND not in answers:
            raise ValueError(f"pair {r.get('pair_id')!r}: both presentation orders need an answer")
        a, b = answers[CORRECT_FIRST], answers[CORRECT_SECOND]
        if a not in LABELS or b not in LABELS:
            raise ValueError(f"pair {r.get('pair_id')!r}: answers must be one of {LABELS}")
        corruptions.append(_check_corruption(r.get("corruption")))
        scores.append(_pair_score(a, b))
        firsts += int(a == "first") + int(b == "first")
        single = r.get("single_scores")
        if single is None:
            have_single = False
            continue
        cal, cor = single["calibrated"], single["corrupted"]
        if not all(isinstance(v, int | float) and math.isfinite(v) for v in (cal, cor)):
            raise ValueError(f"pair {r.get('pair_id')!r}: single-clip scores must be finite")
        cal_scores.append(float(cal))
        cor_scores.append(float(cor))
    est = _estimate(scores)
    return {
        "arm": arm,
        "status": "measured",
        "input_mode": input_mode,
        "n_pairs": len(records),
        "accuracy": est,
        "verdict": _verdict(est["lo"]),
        "position_bias": firsts / (2 * len(records)),
        "single_clip_auroc": (
            auroc(cal_scores + cor_scores, [True] * len(cal_scores) + [False] * len(cor_scores))
            if have_single
            else None
        ),
        "detection_rate": _detection_rate(corruptions, scores),
    }


def physics_check_pair(calibrated_sim: Mapping[str, Any], corrupted_sim: Mapping[str, Any]) -> float:
    """The pair score of the physics baseline: repose angle (< 5 degrees) and mass balance (>= 5 % increase, no inflow
    boundary) read from the simulation states. If exactly one clip is flagged it is taken as the implausible clip (1.0
    when that is the corrupted one, 0.0 when it is the calibrated one); if both or neither are flagged the check cannot
    choose and scores the chance value 0.5."""

    def flagged(sim: Mapping[str, Any]) -> bool:
        found = plausibility.detect(sim)
        return bool(found["zero-friction"]["triggered"] or found["mass-injection"]["triggered"])

    cal, cor = flagged(calibrated_sim), flagged(corrupted_sim)
    if cal == cor:
        return CHANCE
    return 1.0 if cor else 0.0


def score_physics_baseline(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The physics-check `row_b` from `{"pair_id", "corruption", "s"}` records (`s` from `physics_check_pair`)."""
    if len(records) == 0:
        raise ValueError("n = 0: no pairs to score")
    scores = []
    for r in records:
        s = Fraction(r["s"]).limit_denominator(2)
        if s not in (0, Fraction(1, 2), 1):
            raise ValueError(f"pair {r.get('pair_id')!r}: s must be 0, 0.5 or 1")
        scores.append(s)
    corruptions = [_check_corruption(r.get("corruption")) for r in records]
    est = _estimate(scores)
    return {
        "arm": "physics-check",
        "status": "measured",
        "input_mode": "simulation-state",
        "n_pairs": len(records),
        "accuracy": est,
        "verdict": _verdict(est["lo"]),
        "position_bias": None,
        "single_clip_auroc": None,
        "detection_rate": _detection_rate(corruptions, scores),
    }
