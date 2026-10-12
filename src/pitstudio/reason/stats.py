"""Scoring statistics of the reason lane (FR-015-30 to FR-015-32): written from their definitions, NumPy only.

- balanced accuracy (mean per-class recall, exact `Fraction`), F1 ("yes" for binary types, macro for type 3);
- stratified percentile bootstrap of both (10,000 resamples within each true class, fixed seed);
- the first-token answer score s = log p(yes) - log p(no) and its AUROC (pair counting with ties at 1/2);
- the Wilson score interval of a proportion;
- `score_row`, one `row_a` of `contracts/vlm-metrics.schema.json`.

Every function raises `ValueError` for unequal lengths, n = 0, a label outside the type's classes, a count k > n or
k < 0, or a non-finite score (FR-015-32). A prediction may also be "unparseable": it is always wrong.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from fractions import Fraction
from itertools import pairwise
from typing import Any

import numpy as np

UNPARSEABLE = "unparseable"
Z975 = 1.959963984540054  # the 0.975 quantile of the standard normal distribution
BINARY = ("yes", "no")
TYPE3 = ("0", "1", "2", "3+")
CONDITIONS = ("day", "night", "dust", "rain")
AUROC_ARMS = ("cosmos-q8_0", "qwen-base")
ARMS = ("cosmos-q8_0", "cosmos-bf16", "qwen-base", "detector-rule", "constant")
DEFAULT_RESAMPLES = 10_000


def labels_of(qtype: int) -> tuple[str, ...]:
    """The answer classes of a question type (1 to 6)."""
    if isinstance(qtype, bool) or qtype not in (1, 2, 3, 4, 5, 6):
        raise ValueError(f"unknown question type {qtype!r}")
    return TYPE3 if qtype == 3 else BINARY


def _check_pairs(truth: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> None:
    if len(truth) != len(pred):
        raise ValueError(f"truth has {len(truth)} entries, pred has {len(pred)}")
    if len(truth) == 0:
        raise ValueError("n = 0: nothing to score")
    allowed = set(labels)
    for t in truth:
        if t not in allowed:
            raise ValueError(f"truth label {t!r} is not one of {tuple(labels)}")
    for p in pred:
        if p not in allowed and p != UNPARSEABLE:
            raise ValueError(f"predicted label {p!r} is not one of {tuple(labels)} or {UNPARSEABLE!r}")


def balanced_accuracy(truth: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> Fraction:
    """Mean over the classes present in `truth` of the recall, as an exact fraction."""
    _check_pairs(truth, pred, labels)
    hits: dict[str, int] = {}
    total: dict[str, int] = {}
    for t, p in zip(truth, pred, strict=True):
        total[t] = total.get(t, 0) + 1
        hits[t] = hits.get(t, 0) + (1 if p == t else 0)
    return sum((Fraction(hits[c], total[c]) for c in total), Fraction(0)) / len(total)


def _f1_from_counts(tp: float, fp: float, fn: float) -> float:
    denom = 2 * tp + fp + fn
    return 0.0 if denom == 0 else 2 * tp / denom


def f1_score(truth: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> float:
    """F1 of the class "yes" when `labels == ("yes", "no")`, macro-F1 over `labels` otherwise."""
    _check_pairs(truth, pred, labels)
    classes = ["yes"] if tuple(labels) == BINARY else list(labels)
    scores = []
    for c in classes:
        tp = sum(1 for t, p in zip(truth, pred, strict=True) if t == c and p == c)
        fp = sum(1 for t, p in zip(truth, pred, strict=True) if t != c and p == c)
        fn = sum(1 for t, p in zip(truth, pred, strict=True) if t == c and p != c)
        scores.append(_f1_from_counts(tp, fp, fn))
    return sum(scores) / len(scores)


def bootstrap_ci(
    truth: Sequence[str],
    pred: Sequence[str],
    labels: Sequence[str],
    *,
    metric: str,
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
    level: float = 0.95,
) -> tuple[float, float]:
    """Stratified percentile bootstrap interval of "balanced_accuracy" or "f1".

    Each resample draws, within every true class, as many queries as the class holds. A metric of confusion counts
    only depends on how many of the drawn queries carry each predicted label, and that count vector is multinomial
    with the class's observed proportions, so the draw is made directly in that form.
    """
    _check_pairs(truth, pred, labels)
    if metric not in ("balanced_accuracy", "f1"):
        raise ValueError(f"unknown metric {metric!r}")
    if n_resamples < 1 or not 0.0 < level < 1.0:
        raise ValueError("n_resamples must be at least 1 and level inside (0, 1)")
    rng = np.random.default_rng(seed)
    cols = [*labels, UNPARSEABLE]
    present = [c for c in labels if c in set(truth)]
    conf = np.zeros((n_resamples, len(labels), len(cols)))
    for ci, c in enumerate(labels):
        if c not in present:
            continue
        counts = np.array([sum(1 for t, p in zip(truth, pred, strict=True) if t == c and p == k) for k in cols])
        conf[:, ci, :] = rng.multinomial(int(counts.sum()), counts / counts.sum(), size=n_resamples)
    n_true = conf.sum(axis=2)
    if metric == "balanced_accuracy":
        recalls = [conf[:, i, i] / n_true[:, i] for i, c in enumerate(labels) if c in present]
        values = np.mean(recalls, axis=0)
    else:
        classes = [list(labels).index("yes")] if tuple(labels) == BINARY else list(range(len(labels)))
        per_class = []
        for i in classes:
            tp = conf[:, i, i]
            fp = conf[:, :, i].sum(axis=1) - tp
            fn = n_true[:, i] - tp
            denom = 2 * tp + fp + fn
            per_class.append(np.divide(2 * tp, denom, out=np.zeros_like(tp), where=denom > 0))
        values = np.mean(per_class, axis=0)
    lo, hi = np.percentile(values, [50 * (1 - level), 50 * (1 + level)])
    return float(lo), float(hi)


def answer_score(top_logprobs: Mapping[str, float]) -> float:
    """s = log p("yes") - log p("no") at the first answer token, from the top-20 log-probability table.

    A token that is absent from the table takes the smallest log-probability of the table (the 20th). Spelling
    variants of a word ("Yes", " yes") are summed as probabilities.
    """
    if not top_logprobs:
        raise ValueError("the top log-probability table is empty")
    values = list(top_logprobs.values())
    if not all(isinstance(v, int | float) and math.isfinite(v) for v in values):
        raise ValueError("the top log-probability table holds a non-finite value")
    floor = min(values)

    def logp(word: str) -> float:
        found = [v for k, v in top_logprobs.items() if k.strip().casefold() == word]
        if not found:
            return floor
        top = max(found)
        return top + math.log(sum(math.exp(v - top) for v in found))

    return logp("yes") - logp("no")


def auroc(scores: Sequence[float], positive: Sequence[bool]) -> float:
    """P(s_pos > s_neg) + 0.5 P(s_pos = s_neg) over all positive and negative pairs (Mann-Whitney U / (n_pos n_neg))."""
    if len(scores) != len(positive):
        raise ValueError(f"{len(scores)} scores for {len(positive)} labels")
    if len(scores) == 0:
        raise ValueError("n = 0: nothing to score")
    s = np.asarray(scores, dtype=float)
    if not np.isfinite(s).all():
        raise ValueError("a score is not finite")
    y = np.asarray(positive, dtype=bool)
    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("AUROC needs at least one positive and one negative query")
    order = np.argsort(s, kind="stable")
    ss = s[order]
    # doubled average ranks (integers): a block of ties from position i to j shares the rank (i + j + 2) / 2
    boundaries = np.flatnonzero(np.r_[True, ss[1:] != ss[:-1], True])
    ranks2 = np.empty(len(ss), dtype=np.int64)
    for a, b in pairwise(boundaries):
        ranks2[a:b] = a + b + 1  # 2 * mean(rank) = (a + 1) + b
    rank_sum2 = int(ranks2[np.argsort(order, kind="stable")][y].sum())
    return (rank_sum2 - n_pos * (n_pos + 1)) / (2 * n_pos * n_neg)


def wilson_interval(k: int, n: int, z: float = Z975) -> tuple[float, float]:
    """Wilson score interval of k successes in n trials (Wilson 1927), clipped to [0, 1]."""
    if not _is_count(n) or n <= 0:
        raise ValueError(f"n must be a positive integer, got {n!r}")
    if not _is_count(k) or k < 0 or k > n:
        raise ValueError(f"k must be an integer with 0 <= k <= n, got {k!r} for n = {n}")
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def _is_count(x: Any) -> bool:
    return isinstance(x, int | np.integer) and not isinstance(x, bool)


def _estimate(value: float, lo: float, hi: float) -> dict[str, float]:
    return {"value": value, "lo": min(lo, value), "hi": max(hi, value)}


def score_row(
    records: Sequence[Mapping[str, Any]],
    *,
    arm: str,
    qtype: int,
    reasoning: bool = False,
    seed: int = 0,
    n_resamples: int = DEFAULT_RESAMPLES,
) -> dict[str, Any]:
    """One measured `row_a` of the metrics contract from the records of one arm and one question type.

    A record holds `truth`, `parsed`, `condition`, optionally `score` and `status` ("ok" or "error"; an errored query
    is excluded from every score and counted in `error_rate`).
    """
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    labels = labels_of(qtype)
    if len(records) == 0:
        raise ValueError("n = 0: no records to score")
    ok = [r for r in records if r.get("status", "ok") == "ok"]
    if len(ok) == 0:
        raise ValueError("every record is an errored query: nothing to score")
    truth = [r["truth"] for r in ok]
    pred = [r["parsed"] for r in ok]
    _check_pairs(truth, pred, labels)
    for r in ok:
        if r["condition"] not in CONDITIONS:
            raise ValueError(f"unknown condition {r['condition']!r}")
        if "score" in r and not (isinstance(r["score"], int | float) and math.isfinite(r["score"])):
            raise ValueError("a score is not finite")
    ba = float(balanced_accuracy(truth, pred, labels))
    f1 = f1_score(truth, pred, labels)
    ba_lo, ba_hi = bootstrap_ci(truth, pred, labels, metric="balanced_accuracy", n_resamples=n_resamples, seed=seed)
    f1_lo, f1_hi = bootstrap_ci(truth, pred, labels, metric="f1", n_resamples=n_resamples, seed=seed)
    auc = None
    positives = [t == "yes" for t in truth]
    if arm in AUROC_ARMS and qtype != 3 and all("score" in r for r in ok) and 0 < sum(positives) < len(positives):
        auc = auroc([r["score"] for r in ok], positives)
    by_condition = []
    for cond in CONDITIONS:
        sub = [r for r in ok if r["condition"] == cond]
        if sub:
            sub_ba = float(balanced_accuracy([r["truth"] for r in sub], [r["parsed"] for r in sub], labels))
            by_condition.append({"condition": cond, "n": len(sub), "balanced_accuracy": sub_ba})
    return {
        "arm": arm,
        "reasoning": bool(reasoning),
        "type": qtype,
        "status": "measured",
        "n": len(ok),
        "balanced_accuracy": _estimate(ba, ba_lo, ba_hi),
        "f1": _estimate(f1, f1_lo, f1_hi),
        "unparseable_rate": sum(1 for p in pred if p == UNPARSEABLE) / len(ok),
        "error_rate": (len(records) - len(ok)) / len(records),
        "auroc": auc,
        "by_condition": by_condition,
    }
