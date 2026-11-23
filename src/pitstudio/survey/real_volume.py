"""The real 2018 to 2023 volume over an area of interest, as a DC-017-04 volume object (FR-017-34, FR-017-33)."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import numpy as np

from pitstudio.survey.difference import Surface, difference
from pitstudio.survey.uncertainty import volume_uncertainty

LABEL = "measurement, not validation"
SOURCE = "mining-footprint polygon intersected with the 3DEP query box"
PROVISIONAL = (
    "provisional: no mining-footprint polygon intersects the 3DEP query box, so the area of interest is the whole "
    "query box and the site label stays provisional"
)


def polygon_area(vertices: np.ndarray) -> float:
    """Shoelace area, absolute value; 0.0 for fewer than 3 vertices."""
    v = np.asarray(vertices, dtype=np.float64).reshape(-1, 2)
    if len(v) < 3:
        return 0.0
    x, y = v[:, 0], v[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def clip_polygon(subject: np.ndarray, box: np.ndarray) -> np.ndarray:
    """Sutherland-Hodgman clip of `subject` by the axis-aligned rectangle spanned by the vertices of `box`."""
    b = np.asarray(box, dtype=np.float64).reshape(-1, 2)
    x_lo, x_hi, y_lo, y_hi = b[:, 0].min(), b[:, 0].max(), b[:, 1].min(), b[:, 1].max()
    pts = [tuple(p) for p in np.asarray(subject, dtype=np.float64).reshape(-1, 2)]

    def clip(points: list, inside, cross) -> list:
        out: list = []
        for i, cur in enumerate(points):
            prev = points[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
        return out

    def at_x(x: float):
        return lambda p, q: (x, p[1] + (q[1] - p[1]) * (x - p[0]) / (q[0] - p[0]))

    def at_y(y: float):
        return lambda p, q: (p[0] + (q[0] - p[0]) * (y - p[1]) / (q[1] - p[1]), y)

    for inside, cross in (
        (lambda p: p[0] >= x_lo, at_x(x_lo)),
        (lambda p: p[0] <= x_hi, at_x(x_hi)),
        (lambda p: p[1] >= y_lo, at_y(y_lo)),
        (lambda p: p[1] <= y_hi, at_y(y_hi)),
    ):
        if not pts:
            break
        pts = clip(pts, inside, cross)
    dedup = [p for i, p in enumerate(pts) if p != pts[i - 1]]
    arr = np.array(dedup, dtype=np.float64).reshape(-1, 2)
    return arr if len(arr) >= 3 and polygon_area(arr) > 0 else np.empty((0, 2))


def real_volume(
    before: Surface,
    after: Surface,
    *,
    footprint: np.ndarray,
    query_box: np.ndarray,
    meta: Mapping[str, Any],
    footprint_label: str | None = None,
) -> dict:
    """V_cut, V_fill and V_net of `after - before` over footprint x query box, with both uncertainty bounds.

    `footprint_label` names a footprint that is not the Tang and Werner mining footprint; the area of interest then
    says so in its source text. Without an intersecting footprint the area of interest is the whole query box.
    """
    clipped = clip_polygon(footprint, query_box)
    footprint_area = polygon_area(footprint)
    if len(clipped) and footprint_area > 0:
        aoi, overlap = clipped, polygon_area(clipped) / footprint_area
        source = SOURCE if footprint_label is None else f"{footprint_label} intersected with the 3DEP query box"
    else:
        aoi, overlap, source = np.asarray(query_box, dtype=np.float64).reshape(-1, 2), 0.0, PROVISIONAL
    res = difference(before, after, polygon=aoi)
    surfaces = copy.deepcopy(dict(meta["surfaces"]))
    sig0, sig1 = surfaces["before"].get("rmse_z_m"), surfaces["after"].get("rmse_z_m")
    if sig0 is None or sig1 is None:
        raise ValueError("meta surfaces need rmse_z_m for both epochs (FR-017-33)")
    bounds = volume_uncertainty(res.n_valid, before.cell_size_m, sig0, sig1)
    ny, nx = before.z.shape
    return {
        "id": meta["id"],
        "scope": "real",
        "method": "dem-differencing",
        "status": "ok",
        "label": LABEL,
        "licence": copy.deepcopy(meta["licence"]),
        "surfaces": surfaces,
        "grid": {
            "cell_m": float(before.cell_size_m),
            "shape": [int(ny), int(nx)],
            "origin_m": [float(before.origin_xy[0]), float(before.origin_xy[1])],
            "crs": surfaces["after"]["crs"],
        },
        "resampling": copy.deepcopy(meta["resampling"]),
        "vertical_transform": copy.deepcopy(meta["vertical_transform"]),
        "polygon": {"vertices": aoi.tolist(), "source": source, "overlap_ratio": overlap},
        "v_cut_m3": res.v_cut,
        "v_fill_m3": res.v_fill,
        "v_net_m3": res.v_net,
        "cells": {"valid": res.n_valid, "nodata": res.n_nodata_excluded, "nodata_fraction": res.nodata_fraction},
        "uncertainty_m3": {"uncorrelated": bounds.uncorrelated_m3, "correlated": bounds.correlated_m3},
    }
