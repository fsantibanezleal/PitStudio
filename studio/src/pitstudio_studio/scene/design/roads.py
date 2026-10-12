"""The haul-road network as a GeoJSON graph in the site frame (FR-004-21, DC-004-06)."""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


def _grades(coords: np.ndarray) -> tuple[float, float]:
    """(mean grade %, steepest sample grade %) of a polyline; the mean is rise over the chord run between its ends."""
    run_all = np.hypot(np.diff(coords[:, 0]), np.diff(coords[:, 1]))
    rise_all = np.abs(np.diff(coords[:, 2]))
    with np.errstate(divide="ignore", invalid="ignore"):
        steps = np.where(run_all > 0, 100.0 * rise_all / run_all, np.where(rise_all > 0, 1e6, 0.0))
    chord = float(np.hypot(*(coords[-1, :2] - coords[0, :2])))
    mean = 100.0 * float(coords[-1, 2] - coords[0, 2]) / chord if chord > 0 else 0.0
    return mean, float(steps.max()) if len(steps) else 0.0


def _length(coords: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(coords, axis=0), axis=1)))


def build_road_network(
    ramp_centreline: np.ndarray, bench_roads: Sequence[np.ndarray], *, origin: Mapping[str, Any]
) -> dict[str, Any]:
    """The DC-004-06 FeatureCollection of the ramp and the bench roads.

    `ramp_centreline` runs from the pit exit down. Each bench road starts at a vertex of the ramp (or of an earlier
    bench road); that vertex becomes a junction node and splits the edge there. The first ramp vertex is the only
    `exit` node, the other degree-1 nodes are `end` nodes, the rest `junction` nodes.
    """
    polylines = [np.asarray(ramp_centreline, dtype=np.float64)] + [np.asarray(r, dtype=np.float64) for r in bench_roads]
    classes = ["ramp"] + ["bench-road"] * len(bench_roads)
    split_at: list[set[int]] = [{0, len(polylines[0]) - 1}] + [{0, len(r) - 1} for r in polylines[1:]]
    for i, road in enumerate(polylines[1:], start=1):
        key = tuple(road[0])
        for j in range(i):
            hit = np.flatnonzero((polylines[j] == road[0]).all(axis=1))
            if len(hit):
                split_at[j].add(int(hit[0]))
                break
        else:
            raise ValueError(f"bench road {i - 1} does not start on the ramp or an earlier road: {key}")
    node_of: dict[tuple[float, float, float], str] = {}
    node_order: list[tuple[float, float, float]] = []

    def node(coord: np.ndarray) -> str:
        key = (float(coord[0]), float(coord[1]), float(coord[2]))
        if key not in node_of:
            node_of[key] = f"n{len(node_of)}"
            node_order.append(key)
        return node_of[key]

    edges: list[dict[str, Any]] = []
    degree: dict[str, int] = {}
    for p, poly in enumerate(polylines):
        cuts = sorted(split_at[p])
        for a, b in itertools.pairwise(cuts):
            coords = poly[a : b + 1]
            u, v = node(poly[a]), node(poly[b])
            mean, steepest = _grades(coords)
            degree[u] = degree.get(u, 0) + 1
            degree[v] = degree.get(v, 0) + 1
            edges.append(
                {
                    "type": "Feature",
                    "id": f"e{len(edges)}",
                    "geometry": {"type": "LineString", "coordinates": coords.tolist()},
                    "properties": {
                        "kind": "edge",
                        "from": u,
                        "to": v,
                        "class": classes[p],
                        "length_m": _length(coords),
                        "grade_mean_pct": mean,
                        "grade_max_pct": steepest,
                    },
                }
            )
    exit_id = node_of[(float(polylines[0][0, 0]), float(polylines[0][0, 1]), float(polylines[0][0, 2]))]
    nodes = []
    for key in node_order:
        nid = node_of[key]
        role = "exit" if nid == exit_id else ("end" if degree.get(nid, 0) == 1 else "junction")
        nodes.append(
            {
                "type": "Feature",
                "id": nid,
                "geometry": {"type": "Point", "coordinates": [key[0], key[1], key[2]]},
                "properties": {"kind": "node", "role": role},
            }
        )
    if not all(math.isfinite(c) for n in nodes for c in n["geometry"]["coordinates"]):
        raise ValueError("non-finite road coordinate")
    return {
        "type": "FeatureCollection",
        "schema_version": "1.0",
        "frame": "site-enu",
        "site_origin": dict(origin),
        "provenance": "design-code",
        "exit_node": exit_id,
        "features": [*nodes, *edges],
    }
