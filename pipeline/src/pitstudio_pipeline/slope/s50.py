"""`s50_evaluate` of case C1: the DC-010-03 TTF results document (FR-010-23 to FR-010-28, FR-010-35, FR-010-46,
FR-010-47,
SC-010-01, SC-010-02).

Built on ``pitstudio.slope.evaluate``. A result that is missing a stratum (or the real event) that the comparison
names is
labelled ``partial``: every existing stratum is reported, the missing ones are ``not run (absent)``, no SC-010-01
verdict and
no comparison is computed. A result computed from a contract fixture carries ``fixture: true`` and publishes nothing.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio.slope import evaluate as ev
from pitstudio.slope import fixture as fx

SCHEMA_VERSION = "1.0"
HORIZON_CAP_STEPS = 1024
ABSENT = "not run (absent)"
PSIS = (0, 45, 70)


@dataclass
class S50Result:
    document: dict[str, Any]
    fixture: bool
    partial: bool
    missing_strata: list[str]
    pooled_claims_allowed: bool
    status: str
    label: str
    strata_status: dict[str, str] = field(default_factory=dict)


def _errors(rows: Sequence[Mapping[str, Any]], method: str, cutoff: float, stratum: str) -> dict[str, float]:
    return {
        r["event_id"]: r["rel_error"]
        for r in rows
        if r["method"] == method and r["cutoff"] == cutoff and r["stratum"] == stratum and r["outcome"] != "no forecast"
    }


def _acceptance(rows: Sequence[Mapping[str, Any]], *, observed: bool, partial: bool, seed: int) -> list[dict[str, Any]]:
    out = []
    for method in ev.LEARNED:
        for cutoff in ev.CUTOFFS:
            base = {
                "criterion": "SC-010-01",
                "method": method,
                "cutoff": cutoff,
                "stratum": "snr_obs",
                "threshold": 0.1,
            }
            errors = _errors(rows, method, cutoff, "snr_obs")
            if not observed:
                out.append({**base, "verdict": "not run", "reason": "observed SNR unavailable: nominal strata only"})
            elif partial:
                out.append(
                    {
                        **base,
                        "verdict": "not run",
                        "reason": "partial result: the strata the comparison names are not all present",
                    }
                )
            elif not errors:
                out.append({**base, "verdict": "not run", "reason": "no predictions for this arm"})
            else:
                out.append(ev.acceptance_row(method, cutoff, errors, seed=seed))
    return out


def _alarm_summary(alarms: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for a in alarms:
        groups.setdefault((a["method"], a["stratum"]), []).append(a)
    return [{"method": m, "stratum": s, "n_events": len(g), **ev.alarm_summary(g)} for (m, s), g in groups.items()]


def evaluate(
    *,
    run_id: str,
    snr_basis: str,
    snr_obs: float | None,
    predictions: Sequence[Mapping[str, Any]],
    alarms: Sequence[Mapping[str, Any]] = (),
    t_alarm_h: float = 24.0,
    seeds: Mapping[str, int],
    real_event: dict[str, Any] | None = None,
    s4b: list[dict[str, Any]] | None = None,
    expected_strata: Sequence[str] | None = None,
    real_event_expected: bool = False,
    fixture: bool = False,
) -> S50Result:
    """Score the predictions and build the results document (see the module docstring)."""
    scored = ev.score_events(predictions)
    present = list(dict.fromkeys(r["stratum"] for r in scored))
    named = list(expected_strata) if expected_strata is not None else present
    strata_status = {s: ("present" if s in present else ABSENT) for s in named}
    missing = [s for s in named if s not in present]
    if real_event_expected:
        strata_status["real_event"] = "present" if real_event is not None else ABSENT
        if real_event is None:
            missing.append("real_event")
    partial = bool(missing)
    observed = snr_basis == "observed"
    comparisons: list[dict[str, Any]] = []
    if observed and not partial:
        iv = {c: _errors(scored, "inverse_velocity", c, "snr_obs") for c in ev.CUTOFFS}
        models = {m: {c: _errors(scored, m, c, "snr_obs") for c in ev.CUTOFFS} for m in ev.LEARNED}
        models = {m: {c: e for c, e in per.items() if e} for m, per in models.items()}
        out = ev.compare_all({c: e for c, e in iv.items() if e}, models, seed=int(seeds["comparison"]))
        comparisons = [c for c in out["comparisons"] if c.get("n_pairs", 0) >= 2]
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "snr_basis": snr_basis,
        "t_alarm_h": t_alarm_h,
        "horizon_cap_steps": HORIZON_CAP_STEPS,
        "events": scored,
        "alarms": [dict(a) for a in alarms],
        "summary": ev.summarise(scored),
        "alarm_summary": _alarm_summary(alarms),
        "acceptance": _acceptance(scored, observed=observed, partial=partial, seed=int(seeds["acceptance"])),
        "comparisons": comparisons,
        "multiplicity": {"comparisons": 8, "family_wise_claim": False},
        "real_event": real_event
        if real_event is not None
        else ev.real_event_not_run(
            "dewit-2025-event", ABSENT if real_event_expected else "the real series was not ingested"
        ),
        "status": "partial" if partial else "complete",
    }
    if observed:
        document["snr_obs"] = snr_obs
    if partial:
        document["missing_strata"] = missing
    if s4b is not None:
        document["s4b"] = s4b
    if fixture:
        document["fixture"] = True
    return S50Result(
        document=document,
        fixture=fixture,
        partial=partial,
        missing_strata=missing,
        pooled_claims_allowed=not partial,
        status=document["status"],
        label=document["status"],
        strata_status=strata_status,
    )


def write_result(result: S50Result, path: str | Path) -> Path:
    """Write the document as JSON (a fixture result carries ``fixture: true`` at the top level)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def publish(result: S50Result) -> dict[str, Any] | None:
    """None for a fixture result (nothing computed from a fixture is published), else the document."""
    return fx.publishable(result.document)


def lead_time_claims(result: S50Result) -> list[dict[str, Any]]:
    """The lead-time statements that may be published: none for a fixture."""
    return fx.lead_time_claims(result.document["alarm_summary"], dataset_manifest={"fixture": result.fixture})


def s4b_rows(
    *,
    los_errors: Mapping[tuple[int, str, float], Mapping[str, float]],
    full_vector_errors: Mapping[tuple[str, float], Mapping[str, float]],
    excluded_ambiguous: Mapping[int, int],
) -> list[dict[str, Any]]:
    """S4b rows: median relative error per psi, cut-off, method and series (LOS first, then noise-free full vector)."""
    rows = []
    for psi in PSIS:
        for cutoff in ev.CUTOFFS:
            for method in ev.METHODS:
                for series, errs, excluded in (
                    ("los", los_errors.get((psi, method, cutoff)), excluded_ambiguous.get(psi, 0)),
                    ("full-vector-noise-free", full_vector_errors.get((method, cutoff)), 0),
                ):
                    if not errs:
                        continue
                    rows.append(
                        {
                            "psi_deg": psi,
                            "cutoff": cutoff,
                            "method": method,
                            "series": series,
                            "n_events": len(errs),
                            "median_rel_error": float(np.median(list(errs.values()))),
                            "excluded_ambiguous_pixels": excluded,
                        }
                    )
    return rows
