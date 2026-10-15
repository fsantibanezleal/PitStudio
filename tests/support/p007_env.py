# ruff: noqa: E501
"""Third test-support module of spec 007: hand-built bundles for the learned-dispatch tests (vectorised environment, policies, training, evaluation, export).

Locked with its first user (T-007-050). Nothing here imports the code under test. Built on `p007_kit` (locked with T-007-003).

Two networks, both flat (grade 0 %, rolling resistance 2 %) with the speed limit below every rimpull-limited speed, so that a leg takes length / limit exactly (hand calculation):
    * `script_bundle()`: loaders 1 and 2, dump 3; roads 1 - 3 of 1,500 m and 2 - 3 of 3,000 m at 20 km/h (legs of 270 s and 540 s); trucks 1 (start loader 1) and 2 (start loader 2).
    * `family_bundle(n)`: one loader (node 1), one dump (node 2), one road of 1,500 m at 20 km/h, `n` trucks (the MVA oracle family of test_t_007_017).
Loading takes ceil(227 / 45) x 38 s + 30 s = 258 s, dumping 55 s, the payload is 227 t (deterministic profile).
"""

from __future__ import annotations

import p007_kit as kit

LOAD_S, DUMP_S, PAYLOAD_T = 258.0, 55.0, 227.0
LABEL = kit.LABEL


def _base() -> dict:
    b = kit.smoke_bundle()
    b["id"] = "env-hand"
    b["mode"] = "fast"
    b["dispatcher"] = {"id": "fixed"}
    b["variate_profile"] = "deterministic"
    b["quantile_tables"] = []
    b["failures"] = None
    b["kpi_window"] = {"warmup_s": 0.0}
    return b


def script_bundle(horizon_s: float = 1200.0) -> dict:
    b = _base()
    b["horizon_s"] = horizon_s
    b["network"] = {
        "nodes": [
            {"id": 1, "kind": "face", "pos_m": [0.0, 0.0, 1000.0]},
            {"id": 2, "kind": "face", "pos_m": [-1500.0, 0.0, 1000.0]},
            {"id": 3, "kind": "dump", "pos_m": [1500.0, 0.0, 1000.0]},
        ],
        "segments": [
            kit.segment_entry(
                1, 1, 3, (0.0, 0.0, 1000.0), (1500.0, 0.0, 1000.0), speed_limit_kmh=20.0
            ),  # 1,500 m: 270 s
            kit.segment_entry(
                2, 2, 3, (-1500.0, 0.0, 1000.0), (1500.0, 0.0, 1000.0), speed_limit_kmh=20.0
            ),  # 3,000 m: 540 s
        ],
        "zones": [],
        "junctions": [],
    }
    b["loaders"] = [
        {"node": 1, "loader_class": "SHOVEL_45", "n_spots": 1, "destination_dump": 3},
        {"node": 2, "loader_class": "SHOVEL_45", "n_spots": 1, "destination_dump": 3},
    ]
    b["dumps"] = [3]
    b["fleet"] = [
        {"id": 1, "truck_class": "CAT_793F", "start_loader": 1},
        {"id": 2, "truck_class": "CAT_793F", "start_loader": 2},
    ]
    return b


def family_bundle(n: int, *, horizon_s: float = 8 * 3600.0, profile: str = "deterministic") -> dict:
    b = _base()
    b["id"] = "env-family"
    b["horizon_s"] = horizon_s
    b["network"] = {
        "nodes": [
            {"id": 1, "kind": "face", "pos_m": [0.0, 0.0, 1500.0]},
            {"id": 2, "kind": "dump", "pos_m": [1500.0, 0.0, 1500.0]},
        ],
        "segments": [kit.segment_entry(1, 1, 2, (0.0, 0.0, 1500.0), (1500.0, 0.0, 1500.0), speed_limit_kmh=20.0)],
        "zones": [],
        "junctions": [],
    }
    b["loaders"] = [{"node": 1, "loader_class": "SHOVEL_45", "n_spots": 1, "destination_dump": 2}]
    b["dumps"] = [2]
    b["fleet"] = [{"id": i + 1, "truck_class": "CAT_793F", "start_loader": 1} for i in range(n)]
    if profile == "exponential":
        b["variate_profile"] = "exponential"
        b["quantile_tables"] = [kit.example("haul-scenario.valid-exponential.json")["quantile_tables"][0]]
    elif profile == "engine":
        kit.with_engine_profile(b)
    return b
