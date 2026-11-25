"""Wall sections of case C1: the analysed face, FoS inputs and the PoF distribution (FR-010-01 to FR-010-03, FR-010-06).

``extract_sections`` (``pitstudio_pipeline.slope.sections``) cuts the ground profiles from the DEM; its crest and
toe are
the ends of the steepest single run, which on a 1 m DEM is a bench scarp of a few metres. ``choose_face`` takes instead
the steepest stretch of one inter-ramp height, ``wall_section`` writes the analysis settings and ``pof_distribution``
returns the PoF of ``pitstudio.slope.pof`` together with the per-sample minimum factor, so the distribution that
the PoF counts below 1 can be drawn.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from pitstudio.slope import pof
from pitstudio.slope import section as _section

SLICES = {"live": 50, "baked": 200}
SEARCH = {"entry_points": 40, "exit_points": 40, "radius_ratios": 8, "rho_min": 1.02, "rho_max": 4.0}


def choose_face(ground: Sequence[Sequence[float]], *, drop_m: float) -> tuple[float, float]:
    """Crest and toe x of the steepest stretch that drops by at least ``drop_m`` (see the module docstring)."""
    g = np.asarray(ground, dtype=float)
    if g.ndim != 2 or g.shape[1] != 2 or len(g) < 2:
        raise ValueError("the ground needs at least 2 vertices of 2 coordinates")
    if not (isinstance(drop_m, int | float) and math.isfinite(drop_m) and drop_m > 0.0):
        raise ValueError("drop_m must be finite and > 0")
    best: tuple[float, int, int] | None = None
    for i in range(len(g) - 1):
        below = np.flatnonzero(g[i + 1 :, 1] <= g[i, 1] - drop_m)
        if below.size == 0:
            continue
        j = i + 1 + int(below[0])
        angle = math.atan2(g[i, 1] - g[j, 1], g[j, 0] - g[i, 0])
        if best is None or angle > best[0] + 1e-12:
            best = (angle, i, j)
    if best is None:
        raise ValueError(f"no stretch of the ground drops by {drop_m} m")
    return float(g[best[1], 0]), float(g[best[2], 0])


def wall_section(
    section: Mapping[str, Any],
    *,
    drop_m: float,
    mode: str,
    pof_settings: Mapping[str, Any],
    material: Mapping[str, Any],
    distributions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """A DC-010-01 document of the analysed face with its material, search and PoF settings (input not modified)."""
    if mode not in SLICES:
        raise ValueError(f"mode must be one of {list(SLICES)}, got {mode!r}")
    doc = copy.deepcopy(dict(section))
    doc["crest_x_m"], doc["toe_x_m"] = choose_face(doc["ground"], drop_m=drop_m)
    doc["materials"] = [copy.deepcopy(dict(material))]
    doc["analysis"] = {
        "mode": mode,
        "methods": ["bishop", "spencer"],
        "slices": SLICES[mode],
        "search": dict(SEARCH),
        "pof": {**dict(pof_settings), "distributions": [dict(d) for d in distributions]},
    }
    _section.parse_section(doc)
    return doc


def pof_distribution(section: Any, *, n: int, k: int, seed: int) -> dict[str, Any]:
    """The PoF result of ``pof.probability_of_failure`` and the per-sample minimum Bishop factor (``min_factors``)."""
    prep = _section.parse_section(section) if not isinstance(section, _section.Section) else section
    settings = prep.pof or {}
    distributions = list(settings.get("distributions", []))
    for d in distributions:
        pof._check_distribution(d)
    n = pof._check_n(n)
    seed = pof._check_seed(seed)
    chosen, _ = pof.candidate_circles(prep, int(k))
    samples = pof.draw_samples(distributions, n, seed)
    minimum = pof._minimum_over(prep, chosen, samples, n, None)
    failures = int(np.sum((minimum < 1.0) | np.isinf(minimum)))
    lower, upper = pof.wilson_interval(failures, n)
    return {
        "method": "bishop",
        "candidate_set": pof.CANDIDATE_SET,
        "samples": n,
        "candidates": int(k),
        "failures": failures,
        "pof": failures / n,
        "wilson_95": {"lower": lower, "upper": upper, "z": pof.Z95},
        "seed": seed,
        "min_factors": [float(v) if math.isfinite(v) else float("nan") for v in minimum],
    }


def histogram(values: Sequence[float], *, bins: int) -> dict[str, Any]:
    """Equal-width histogram over [min, max]: ``edges`` (bins + 1), ``counts`` and ``centres``."""
    v = np.asarray(values, dtype=float)
    if v.size == 0 or not np.all(np.isfinite(v)):
        raise ValueError("the histogram needs finite values")
    counts, edges = np.histogram(v, bins=int(bins))
    centres = (edges[:-1] + edges[1:]) / 2.0
    return {
        "edges": [float(e) for e in edges],
        "counts": [int(c) for c in counts],
        "centres": [float(c) for c in centres],
    }
