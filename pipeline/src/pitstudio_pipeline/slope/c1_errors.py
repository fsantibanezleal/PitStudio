"""C1 error results from the scored event rows (FR-010-23, FR-010-25, FR-010-28; C1-U1).

The rows are the ``events`` of a TTF results document (``evaluate.score_events``): one per event, method and cut-off.
``paired_intervals`` forms, for every stratum, learned method and cut-off, the paired percentile bootstrap of
d_i = e_inverse_velocity(i) - e_method(i) by event id through ``evaluate.paired_comparison`` (an arm whose event ids
differ from the baseline's raises ``UnpairedError``: an interval is never formed from unpaired errors).
``error_distributions`` reduces the per-event errors to quantiles, the share scored at the horizon cap and an empirical
CDF on a fixed grid, so a few kilobytes stand for 18,000 rows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from pitstudio.slope import evaluate as ev

QUANTILES = (5, 25, 50, 75, 90, 95)
ECDF_GRID = tuple(round(0.05 * i, 2) for i in range(41))  # 0 to 2 relative error


def _scored(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [r for r in rows if r["outcome"] != "no forecast"]


def _errors(rows: Sequence[Mapping[str, Any]], method: str, cutoff: float, stratum: str) -> dict[str, float]:
    return {
        r["event_id"]: float(r["rel_error"])
        for r in rows
        if r["method"] == method and r["cutoff"] == cutoff and r["stratum"] == stratum
    }


def paired_intervals(
    events: Sequence[Mapping[str, Any]], *, seed: int, resamples: int = ev.RESAMPLES
) -> list[dict[str, Any]]:
    """One paired comparison against inverse velocity per (stratum, learned method, cut-off) present in ``events``."""
    rows = _scored(events)
    strata = list(dict.fromkeys(r["stratum"] for r in rows))
    out: list[dict[str, Any]] = []
    for stratum in strata:
        for method in ev.LEARNED:
            for cutoff in ev.CUTOFFS:
                model = _errors(rows, method, cutoff, stratum)
                if not model:
                    continue
                base = _errors(rows, "inverse_velocity", cutoff, stratum)
                comparison = ev.paired_comparison(
                    base, model, method=method, cutoff=cutoff, resamples=resamples, seed=seed
                )
                out.append({**comparison, "stratum": stratum})
    return out


def comparison_statement(comparisons: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """How many comparisons were made (total and per stratum) and that no family-wise claim is made (FR-010-25)."""
    per: dict[str, int] = {}
    for c in comparisons:
        per[c["stratum"]] = per.get(c["stratum"], 0) + 1
    return {"comparisons": len(comparisons), "per_stratum": per, "family_wise_claim": False}


def error_distributions(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Per (method, stratum, cut-off): n, quantiles, share at the cap and the empirical CDF of the relative error."""
    groups: dict[tuple[str, str, float], list[Mapping[str, Any]]] = {}
    for r in _scored(events):
        groups.setdefault((r["method"], r["stratum"], r["cutoff"]), []).append(r)
    grid = np.array(ECDF_GRID)
    out = []
    for (method, stratum, cutoff), g in groups.items():
        e = np.sort(np.array([x["rel_error"] for x in g], dtype=float))
        q = np.percentile(e, QUANTILES)
        out.append(
            {
                "method": method,
                "stratum": stratum,
                "cutoff": cutoff,
                "n_events": int(e.size),
                "quantiles": {f"p{p:02d}": float(v) for p, v in zip(QUANTILES, q, strict=True)},
                "share_at_cap": float(np.mean([bool(x["scored_at_cap"]) for x in g])),
                "ecdf": {
                    "x": [float(x) for x in grid],
                    "p": [float(np.searchsorted(e, x, side="right") / e.size) for x in grid],
                },
            }
        )
    return out
