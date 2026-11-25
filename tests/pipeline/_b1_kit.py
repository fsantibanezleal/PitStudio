# ruff: noqa: E501
"""Shared fixtures of the B1 traffic tests: a small pit-like road network as a design geojson (nodes and edges with 3D
coordinates, the shape of `road-network.geojson` of the pit design), the A1 scenario block for it, and a bundle written to disk.
Not a test file: nothing here is collected."""

from __future__ import annotations

import json
from pathlib import Path

from pitstudio_pipeline.haulage.a1_run import design_bundle

NODES = {
    0: (0.0, 0.0, 0.0), 1: (250.0, 0.0, -10.0), 2: (500.0, 0.0, -20.0), 3: (250.0, 200.0, -10.0), 4: (250.0, 400.0, -20.0), 5: (-150.0, 0.0, 0.0),
}  # fmt: skip
EDGES = [(0, 1, "ramp"), (1, 2, "bench-road"), (1, 3, "ramp"), (3, 4, "bench-road"), (0, 5, "bench-road")]


def geojson() -> dict:
    feats = [
        {
            "type": "Feature",
            "properties": {"kind": "node", "id": f"n{i}"},
            "geometry": {"type": "Point", "coordinates": list(p)},
        }
        for i, p in NODES.items()
    ]
    for a, b, cls in EDGES:
        pa, pb = NODES[a], NODES[b]
        mid = [
            (pa[k] + pb[k]) / 2 + (8.0 if k == 1 else 0.0) for k in range(3)
        ]  # a slight bend so that the polyline has an interior vertex
        feats.append(
            {
                "type": "Feature",
                "properties": {"kind": "edge", "from": f"n{a}", "to": f"n{b}", "class": cls},
                "geometry": {"type": "LineString", "coordinates": [list(pa), mid, list(pb)]},
            }
        )
    return {"type": "FeatureCollection", "features": feats}


def scenario(horizon_s: float = 3600.0, warmup_s: float = 600.0) -> dict:
    return {
        "horizon_s": horizon_s, "warmup_s": warmup_s, "truck_class": "CAT_793F", "loader_class": "SHOVEL_45", "rolling_resistance_pct": 2.5,
        "speed_limit_kmh": {"ramp": 30.0, "bench-road": 40.0}, "simplify_epsilon_m": 2.0, "loaders": {"n2": 0, "n4": 1}, "dumps": ["n0", "n5"],
    }  # fmt: skip


def write_bundle(
    folder: Path, n_trucks: int = 4, horizon_s: float = 3600.0, dispatcher: str = "sptf"
) -> tuple[Path, dict]:
    b = design_bundle(geojson(), scenario(horizon_s), n_trucks, dispatcher)
    path = folder / f"b1-{n_trucks}-{int(horizon_s)}.json"
    path.write_text(json.dumps(b), encoding="utf-8")
    return path, b
