# ruff: noqa: E501, PT018
"""T-007-014 (Python half): hostile scenario bundles (one violation per case, every class of FR-007-03) and disconnected networks, rejected with every
violation listed.

Requirements: FR-007-03, FR-007-04.

Spec: specs/007-haulage-dispatch/spec.md FR-007-03 (hostile bundles are rejected before simulating with `InvalidScenario` listing every violation (JSON path, value,
rule), never clipping, defaulting or coercing a value: a schema violation; a NaN or infinite number; a count <= 0 where a positive count is required (trucks,
loaders, dumps, loader spots); more than 40 trucks in a bundle marked `live`, or more than 400 otherwise; a segment length <= 0 m; a |grade| >= 100 %; a rolling
resistance < 0 %; a speed limit <= 0 km/h; an unknown dispatcher, variate profile, truck class or loader class; a duplicate node, segment or truck id), FR-007-04 (on the
frozen network without closures, if some loader cannot be reached from some dump, or some dump from some loader, for a truck class in the fleet (disconnected graph, width
class or one-way constraints), `DisconnectedNetwork` names every unreachable (origin, destination, truck class) triple, within 1 s for networks of <= 10^4 segments),
section 7 (closures and breakdowns are normal engine behaviour and not `DisconnectedNetwork`), section 8 (a) (a violation at `/horizon_s` is reported as `InvalidHorizon`),
(b) (the class parameters the bundle carries must equal the engine pin), (k) (bounds the spec leaves open) and the contract examples index.

Oracle: the spec's own hostile examples with the JSON pointers its index states (`contracts/examples/index.json`); hand-modified copies of the valid example bundles (one
violation each, the offending path written in the test); the engine's rule for reachability (a vehicle with a larger width class than the segment cannot use it at all; a
one-way segment is traversable only from `a` to `b`: `minehaulsim/network/graph.py`), worked out by hand for the five-node smoke network.

Expected API (module `pitstudio_pipeline.haulage.scenario`; errors in `pitstudio_pipeline.haulage.errors`):
    errors.InvalidScenario(HaulError)        `violations: list[tuple[str, object, str]]` of (JSON pointer, offending value, rule text), every violation, none twice
    errors.InvalidHorizon(HaulError)         a bundle whose only violations are at `/horizon_s` raises this (violations as above)
    errors.DisconnectedNetwork(HaulError)    `triples: list[tuple[int, int, str]]` of (origin node, destination node, truck class), every unreachable one
    validate_bundle(bundle: dict) -> None    schema (contracts/haul-scenario.schema.json) plus: finite numbers; unique node, segment and truck ids; segment end points, loader
        nodes, dump nodes and truck start loaders exist; class parameters equal the engine catalog. Pointers: a duplicate id is reported at the LATER occurrence
        (`/network/nodes/1/id`); a schema violation at the pointer the schema validator gives; a non-finite number at the number. The input is never modified.
    load_bundle(path: Path) -> dict          reads the file, tolerates NaN/Infinity tokens, validates; a malformed or empty file raises InvalidScenario with one violation at "";
                                             returns exactly the parsed JSON (nothing defaulted)
    check_connectivity(bundle: dict) -> None  raises DisconnectedNetwork unless every dump is reachable from every loader and every loader from every dump for every truck class that
        appears in the fleet, on the frozen network (no closures, no failures)
"""

from __future__ import annotations

import copy
import json
import math
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit as kit
from pitstudio_pipeline.haulage.errors import DisconnectedNetwork, InvalidHorizon, InvalidScenario
from pitstudio_pipeline.haulage.scenario import check_connectivity, load_bundle, validate_bundle

INDEX = json.loads((kit.EXAMPLES / "index.json").read_text(encoding="utf-8"))["examples"]
HOSTILE = [e for e in INDEX if e["file"].startswith("haul-scenario.") and not e["valid"]]
VALID = [e["file"] for e in INDEX if e["file"].startswith("haul-scenario.") and e["valid"]]


def paths(e: InvalidScenario) -> list[str]:
    return [v[0] for v in e.violations]


def dump(doc) -> str:
    return json.dumps(
        doc, sort_keys=True
    )  # NaN is written as NaN, so a comparison of dumps works where NaN != NaN breaks `==`


def same_value(a, b) -> bool:
    if isinstance(b, float) and math.isnan(b):
        return isinstance(a, float) and math.isnan(a)
    return a == b and type(a) is type(b)


def reject(bundle: dict) -> InvalidScenario:
    before = dump(bundle)
    with pytest.raises(InvalidScenario) as ei:
        validate_bundle(bundle)
    assert dump(bundle) == before  # never modified: nothing clipped, defaulted or coerced
    assert ei.value.violations and all(len(v) == 3 and isinstance(v[0], str) and v[2] for v in ei.value.violations)
    assert len({(v[0], v[2]) for v in ei.value.violations}) == len(ei.value.violations)  # no violation twice
    return ei.value


# ---------------------------------------------------------------------------------------------------------------------
# valid bundles and the contract's hostile examples
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-03")
@pytest.mark.parametrize("name", VALID)
def test_the_valid_example_bundles_are_accepted_unchanged(name):
    b = kit.example(name)
    before = copy.deepcopy(b)
    validate_bundle(b)
    assert b == before  # no clipping, defaulting or coercing


@pytest.mark.req("FR-007-03")
@pytest.mark.parametrize("name", VALID)
def test_load_bundle_returns_exactly_the_parsed_json(name):
    assert load_bundle(kit.example_path(name)) == kit.example(name)


@pytest.mark.req("FR-007-03")
@pytest.mark.parametrize(
    "entry",
    [e for e in HOSTILE if e["rule"] != "FR-007-13"],
    ids=[e["file"] for e in HOSTILE if e["rule"] != "FR-007-13"],
)
def test_every_hostile_example_is_rejected_at_the_pointer_its_index_states(entry):
    e = reject(kit.example(entry["file"]))
    assert entry["pointer"] in paths(e), (entry["pointer"], paths(e))


@pytest.mark.req("FR-007-03")
def test_a_horizon_over_seven_days_is_invalid_horizon():
    entry = next(e for e in HOSTILE if e["rule"] == "FR-007-13")
    with pytest.raises(InvalidHorizon) as ei:
        validate_bundle(kit.example(entry["file"]))
    assert "/horizon_s" in [v[0] for v in ei.value.violations]


# ---------------------------------------------------------------------------------------------------------------------
# one violation per case
# ---------------------------------------------------------------------------------------------------------------------
def set_path(b: dict, pointer: str, value) -> dict:
    node = b
    parts = pointer.strip("/").split("/")
    for p in parts[:-1]:
        node = node[int(p)] if isinstance(node, list) else node[p]
    if isinstance(node, list):
        node[int(parts[-1])] = value
    else:
        node[parts[-1]] = value
    return b


NUMERIC = [
    ("/network/segments/0/grade_pct", float("nan")),
    ("/network/segments/0/grade_pct", float("inf")),
    ("/network/segments/0/grade_pct", 100.0),
    ("/network/segments/0/grade_pct", -100.0),
    ("/network/segments/0/grade_pct", 100.001),
    ("/network/segments/0/grade_pct", -1e6),
    ("/network/segments/0/length_m", 0.0),
    ("/network/segments/0/length_m", -5.0),
    ("/network/segments/0/length_m", -0.0),
    ("/network/segments/0/length_m", float("inf")),
    ("/network/segments/0/length_m", float("nan")),
    ("/network/segments/0/rolling_resistance_pct", -0.001),
    ("/network/segments/0/rolling_resistance_pct", float("nan")),
    ("/network/segments/0/speed_limit_kmh", 0.0),
    ("/network/segments/0/speed_limit_kmh", -10.0),
    ("/network/segments/0/speed_limit_kmh", float("nan")),
    ("/loaders/0/n_spots", 0),
    ("/loaders/0/n_spots", -1),
    ("/loaders/0/n_spots", "2"),
    ("/loaders/0/n_spots", 1.5),
    ("/loaders/0/n_spots", None),
]


@pytest.mark.req("FR-007-03")
@pytest.mark.parametrize(("pointer", "value"), NUMERIC, ids=[f"{p.split('/')[-1]}={v!r}" for p, v in NUMERIC])
def test_numeric_hostile_values_are_rejected_at_their_own_pointer(pointer, value):
    b = set_path(kit.smoke_bundle(), pointer, value)
    e = reject(b)
    assert pointer in paths(e)
    offending = next(v[1] for v in e.violations if v[0] == pointer)
    assert same_value(offending, value)


@pytest.mark.req("FR-007-03")
@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        ("/network/segments/0/grade_pct", 99.999),
        ("/network/segments/0/grade_pct", -99.999),
        ("/network/segments/0/rolling_resistance_pct", 0.0),
        ("/network/segments/0/speed_limit_kmh", 0.001),
        ("/network/segments/0/length_m", 0.001),
    ],
)
def test_values_just_inside_the_bounds_are_accepted(pointer, value):
    validate_bundle(set_path(kit.smoke_bundle(), pointer, value))


@pytest.mark.req("FR-007-03")
@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        ("/dispatcher/id", "teleport"),
        ("/dispatcher/id", ""),
        ("/variate_profile", "lognormal"),
        ("/fleet/0/truck_class", "CAT_999Z"),
        ("/loaders/0/loader_class", "SHOVEL_99"),
        ("/equipment/truck_classes/0/name", "CAT_999Z"),
        ("/equipment/loader_classes/0/name", "SHOVEL_99"),
    ],
)
def test_unknown_dispatchers_profiles_and_classes_are_rejected(pointer, value):
    e = reject(set_path(kit.smoke_bundle(), pointer, value))
    assert pointer in paths(e)


@pytest.mark.req("FR-007-03")
def test_a_count_of_zero_trucks_loaders_or_dumps_is_rejected():
    for key in ("fleet", "loaders", "dumps"):
        b = kit.smoke_bundle()
        b[key] = []
        assert f"/{key}" in paths(reject(b))


@pytest.mark.req("FR-007-03")
@pytest.mark.parametrize(
    ("live", "n", "ok"),
    [
        (True, 40, True),
        (True, 41, False),
        (False, 41, True),
        (False, 400, True),
        (False, 401, False),
        (True, 400, False),
    ],
)
def test_fleet_size_limits_depend_on_the_live_flag(live, n, ok):
    b = kit.smoke_bundle()
    b["live"] = live
    b["fleet"] = [{"id": i + 1, "truck_class": "CAT_793F", "start_loader": 1 if i % 2 == 0 else 2} for i in range(n)]
    if ok:
        validate_bundle(b)
    else:
        assert "/fleet" in paths(reject(b))


@pytest.mark.req("FR-007-03")
@pytest.mark.parametrize(
    ("pointer", "value", "reported"),
    [
        ("/network/nodes/1/id", 1, "/network/nodes/1/id"),  # node 2 given node 1's id
        ("/network/segments/1/id", 1, "/network/segments/1/id"),
        ("/fleet/1/id", 1, "/fleet/1/id"),
    ],
)
def test_duplicate_node_segment_and_truck_ids_are_reported_at_the_later_occurrence(pointer, value, reported):
    e = reject(set_path(kit.smoke_bundle(), pointer, value))
    assert reported in paths(e)


@pytest.mark.req("FR-007-03")
def test_a_duplicate_dump_is_rejected():
    b = kit.smoke_bundle()
    b["dumps"] = [4, 4]
    assert "/dumps" in paths(reject(b))


@pytest.mark.req("FR-007-03")
@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        ("/network/segments/0/a", 99),  # a segment end point that is not a node
        ("/network/segments/3/b", 99),
        ("/loaders/0/node", 99),
        ("/dumps/0", 99),
        ("/fleet/0/start_loader", 3),  # node 3 is a junction, not a loader
    ],
)
def test_dangling_references_are_rejected_before_simulating(pointer, value):
    assert pointer in paths(reject(set_path(kit.smoke_bundle(), pointer, value)))


@pytest.mark.req("FR-007-03")
@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        ("/equipment/truck_classes/0/payload_mean_t", 228.0),
        ("/equipment/truck_classes/0/empty_t", 1.0),
        ("/equipment/truck_classes/0/rimpull_kn/0/force_kn", 1.0),
        ("/equipment/loader_classes/0/pass_t", 46.0),
        ("/equipment/loader_classes/0/time_cv", 0.5),
    ],
)
def test_class_parameters_that_differ_from_the_engine_catalog_are_rejected(pointer, value):
    assert pointer in paths(reject(set_path(kit.smoke_bundle(), pointer, value)))


@pytest.mark.req("FR-007-03")
@pytest.mark.parametrize("bad", [[], None, 3, "bundle", [{"id": 1}]])
def test_a_document_that_is_not_an_object_is_rejected_at_the_root(bad):
    with pytest.raises(InvalidScenario) as ei:
        validate_bundle(bad)
    assert "" in paths(ei.value)


@pytest.mark.req("FR-007-03")
def test_every_violation_of_a_bundle_is_listed_and_nothing_else():
    b = kit.smoke_bundle()
    b["network"]["segments"][0]["grade_pct"] = float("nan")
    b["network"]["segments"][1]["length_m"] = 0.0
    b["fleet"][1]["id"] = 1
    b["dispatcher"]["id"] = "teleport"
    b["loaders"][0]["n_spots"] = 0
    e = reject(b)
    expected = {
        "/network/segments/0/grade_pct",
        "/network/segments/1/length_m",
        "/fleet/1/id",
        "/dispatcher/id",
        "/loaders/0/n_spots",
    }
    got = set(paths(e))
    assert expected <= got
    assert all(any(p == x or p.startswith(x + "/") or x.startswith(p + "/") for x in expected) for p in got), (
        got
    )  # no unrelated violation
    by = {v[0]: v for v in e.violations}
    assert (
        by["/network/segments/1/length_m"][1] == 0.0
        and by["/loaders/0/n_spots"][1] == 0
        and by["/dispatcher/id"][1] == "teleport"
    )


@pytest.mark.req("FR-007-03")
def test_load_bundle_rejects_nan_tokens_malformed_and_empty_files(tmp_path):
    b = kit.smoke_bundle()
    text = json.dumps(b).replace('"grade_pct": 7.428', '"grade_pct": NaN', 1)
    p = tmp_path / "nan.json"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(InvalidScenario) as ei:
        load_bundle(p)
    assert "/network/segments/0/grade_pct" in paths(ei.value)
    for name, content in (
        ("broken.json", "{not json"),
        ("empty.json", ""),
        ("array.json", "[1, 2]"),
        ("bom.json", "﻿" + json.dumps(b)),
    ):
        q = tmp_path / name
        q.write_text(content, encoding="utf-8")
        if name == "bom.json":
            continue  # a BOM is tolerated or rejected, the spec does not say; not tested
        with pytest.raises(InvalidScenario) as ei2:
            load_bundle(q)
        assert "" in paths(ei2.value)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-04: disconnected networks
# ---------------------------------------------------------------------------------------------------------------------
def disconnect(b: dict) -> list[tuple[int, int, str]]:
    with pytest.raises(DisconnectedNetwork) as ei:
        check_connectivity(b)
    return ei.value.triples


@pytest.mark.req("FR-007-04")
@pytest.mark.parametrize("name", VALID)
def test_the_valid_examples_are_connected(name):
    check_connectivity(
        kit.example(name)
    )  # also the traffic example with its closure windows: closures are not part of the frozen network


@pytest.mark.req("FR-007-04")
def test_an_isolated_dump_names_every_unreachable_pair_in_both_directions():
    b = kit.smoke_bundle()
    b["network"]["segments"] = [
        s for s in b["network"]["segments"] if s["id"] != 4
    ]  # node 5 (a dump) loses its only road
    assert set(disconnect(b)) == {(1, 5, "CAT_793F"), (2, 5, "CAT_793F"), (5, 1, "CAT_793F"), (5, 2, "CAT_793F")}
    assert len(disconnect(b)) == 4  # none twice


@pytest.mark.req("FR-007-04")
def test_a_one_way_road_makes_the_way_back_unreachable():
    b = kit.smoke_bundle()
    seg3 = next(s for s in b["network"]["segments"] if s["id"] == 3)  # 3 -> 4, the only road to dump 4
    seg3["one_way"] = True  # traversable 3 -> 4 only
    assert set(disconnect(b)) == {(4, 1, "CAT_793F"), (4, 2, "CAT_793F")}


@pytest.mark.req("FR-007-04")
def test_a_one_way_road_in_the_wrong_direction_blocks_the_way_in():
    b = kit.smoke_bundle()
    seg3 = next(s for s in b["network"]["segments"] if s["id"] == 3)
    seg3["a"], seg3["b"] = 4, 3  # now one-way 4 -> 3
    seg3["polyline_m"] = list(reversed(seg3["polyline_m"]))
    seg3["grade_pct"] = -seg3["grade_pct"]
    seg3["one_way"] = True
    assert set(disconnect(b)) == {(1, 4, "CAT_793F"), (2, 4, "CAT_793F")}


@pytest.mark.req("FR-007-04")
def test_a_segment_narrower_than_the_truck_class_cannot_be_used():
    b = kit.smoke_bundle()
    next(s for s in b["network"]["segments"] if s["id"] == 2)["width_class"] = (
        1  # the road of loader 2 is single-lane, CAT_793F is class 2
    )
    assert set(disconnect(b)) == {(2, 4, "CAT_793F"), (2, 5, "CAT_793F"), (4, 2, "CAT_793F"), (5, 2, "CAT_793F")}


@pytest.mark.req("FR-007-04")
def test_only_the_truck_classes_in_the_fleet_are_checked_and_each_class_is_named():
    b = kit.smoke_bundle()
    next(s for s in b["network"]["segments"] if s["id"] == 2)["width_class"] = 1
    b["equipment"]["truck_classes"].append(
        kit.truck_class_entry("UG_TRUCK_50")
    )  # width class 1: may use the narrow road
    # not in the fleet: still only CAT_793F is checked
    assert {t[2] for t in disconnect(b)} == {"CAT_793F"}
    b["fleet"].append(
        {"id": 3, "truck_class": "UG_TRUCK_50", "start_loader": 1}
    )  # now in the fleet: it passes everywhere, the wide class still fails
    triples = set(disconnect(b))
    assert triples == {(2, 4, "CAT_793F"), (2, 5, "CAT_793F"), (4, 2, "CAT_793F"), (5, 2, "CAT_793F")}


@pytest.mark.req("FR-007-04")
def test_two_islands_name_every_cross_pair():
    b = kit.smoke_bundle()
    b["network"]["segments"] = [
        s for s in b["network"]["segments"] if s["id"] not in (1, 2)
    ]  # both loaders cut off from the junction
    got = set(disconnect(b))
    assert got == {
        (1, 4, "CAT_793F"),
        (1, 5, "CAT_793F"),
        (2, 4, "CAT_793F"),
        (2, 5, "CAT_793F"),
        (4, 1, "CAT_793F"),
        (4, 2, "CAT_793F"),
        (5, 1, "CAT_793F"),
        (5, 2, "CAT_793F"),
    }


@pytest.mark.req("FR-007-04")
def test_a_network_of_ten_thousand_segments_is_checked_within_one_second():
    side = 70  # 70 x 70 nodes, 2 * 70 * 69 = 9,660 segments
    b = kit.smoke_bundle()
    nodes, segs = [], []
    nid = lambda r, c: r * side + c + 1  # noqa: E731
    pos = lambda r, c: (100.0 * c, 100.0 * r, 1000.0)  # noqa: E731
    for r in range(side):
        for c in range(side):
            kind = (
                "face"
                if (r, c) in ((0, 0), (0, side - 1))
                else "dump"
                if (r, c) in ((side - 1, 0), (side - 1, side - 1))
                else "junction"
            )
            nodes.append({"id": nid(r, c), "kind": kind, "pos_m": list(pos(r, c))})
    k = 0
    for r in range(side):
        for c in range(side):
            for dr, dc in ((0, 1), (1, 0)):
                if r + dr < side and c + dc < side:
                    k += 1
                    segs.append(
                        kit.segment_entry(
                            k, nid(r, c), nid(r + dr, c + dc), pos(r, c), pos(r + dr, c + dc), speed_limit_kmh=40.0
                        )
                    )
    b["network"] = {"nodes": nodes, "segments": segs, "zones": [], "junctions": []}
    b["loaders"] = [
        {"node": nid(0, 0), "loader_class": "SHOVEL_45", "n_spots": 1, "destination_dump": nid(side - 1, 0)},
        {
            "node": nid(0, side - 1),
            "loader_class": "SHOVEL_45",
            "n_spots": 1,
            "destination_dump": nid(side - 1, side - 1),
        },
    ]
    b["dumps"] = [nid(side - 1, 0), nid(side - 1, side - 1)]
    b["fleet"] = [{"id": 1, "truck_class": "CAT_793F", "start_loader": nid(0, 0)}]
    assert len(segs) == 9660
    t0 = time.perf_counter()
    check_connectivity(b)  # fully connected grid: must pass
    assert time.perf_counter() - t0 < 1.0
    b["network"]["segments"] = [
        s for s in segs if s["a"] != nid(side - 1, 0) and s["b"] != nid(side - 1, 0)
    ]  # isolate one dump
    t0 = time.perf_counter()
    got = set(disconnect(b))
    assert time.perf_counter() - t0 < 1.0
    assert got == {
        (nid(0, 0), nid(side - 1, 0), "CAT_793F"),
        (nid(0, side - 1), nid(side - 1, 0), "CAT_793F"),
        (nid(side - 1, 0), nid(0, 0), "CAT_793F"),
        (nid(side - 1, 0), nid(0, side - 1), "CAT_793F"),
    }
