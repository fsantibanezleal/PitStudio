# ruff: noqa: E501
"""Scenario bundle loader and hostile-input checks (FR-007-03, FR-007-04, FR-007-12, FR-007-13; DC-007-01).

A bundle is rejected before any simulation with `InvalidScenario` listing every violation as (JSON pointer, value, rule); a
bundle whose only violations sit at /horizon_s raises `InvalidHorizon`. Nothing is clipped, defaulted or coerced, and the
input is never modified.
"""

from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path
from typing import Any

from pitstudio_pipeline._contracts import _pointer, _validator

from .errors import DisconnectedNetwork, InvalidHorizon, InvalidScenario, UnsupportedFeature

SCHEMA = "haul-scenario.schema.json"
MAX_HORIZON_S = 604800.0
TWIN_UNSUPPORTED = ("lhds", "ore_passes", "shaft_bin", "planning_overlay", "zone_penalty_s")  # FR-007-12, in this order


def _short(value: Any) -> Any:
    """A leaf value as is; a container as a short description (a violation never carries a whole document)."""
    if isinstance(value, dict):
        return f"<object with {len(value)} fields>"
    if isinstance(value, list):
        return f"<array of {len(value)}>"
    return value


def _esc(part: Any) -> str:
    return str(part).replace("~", "~0").replace("/", "~1")


def _walk_numbers(node: Any, path: str, out: list[tuple[str, Any]]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            _walk_numbers(v, f"{path}/{_esc(k)}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_numbers(v, f"{path}/{i}", out)
    elif isinstance(node, float) and not math.isfinite(node):
        out.append((path, node))


def _catalog_truck(name: str) -> dict:
    from minehaulsim.equipment.catalog import TRUCKS

    t = TRUCKS[name]
    return {
        "name": t.name,
        "kind": t.kind,
        "payload_mean_t": t.payload_mean_t,
        "payload_sd_t": t.payload_sd_t,
        "empty_t": t.empty_t,
        "width_class": t.width_class,
        "power_kw": t.power_kw,
        "max_speed_kmh": t.max_speed_kmh,
        "rimpull_kn": [{"speed_kmh": v, "force_kn": f} for v, f in t.rimpull_kn],
        "retarder_kn": [{"speed_kmh": v, "force_kn": f} for v, f in t.retarder_kn],
    }


def _catalog_loader(name: str) -> dict:
    from minehaulsim.equipment.catalog import LOADERS

    c = LOADERS[name]
    return {
        "name": c.name,
        "pass_t": c.pass_t,
        "pass_time_s": c.pass_time_s,
        "time_cv": c.time_cv,
        "spot_time_s": c.spot_time_s,
    }


def _diff(path: str, got: Any, want: Any, out: list[tuple[str, object, str]]) -> None:
    if isinstance(want, dict) and isinstance(got, dict):
        for k, w in want.items():
            if k in got:
                _diff(f"{path}/{k}", got[k], w, out)
    elif isinstance(want, list) and isinstance(got, list):
        if len(got) != len(want):
            out.append((path, _short(got), f"must have the engine catalog's {len(want)} entries"))
            return
        for i, (g, w) in enumerate(zip(got, want, strict=True)):
            _diff(f"{path}/{i}", g, w, out)
    elif got != want:
        out.append(
            (
                path,
                got,
                f"must equal the engine catalog value {want!r} (the class parameters are pinned with the engine)",
            )
        )


def _structural(b: dict, out: list[tuple[str, object, str]]) -> None:
    """Rules the schema cannot state: unique ids, references, class parameters against the engine pin."""
    net = b.get("network") if isinstance(b.get("network"), dict) else {}
    nodes = net.get("nodes") if isinstance(net.get("nodes"), list) else []
    segs = net.get("segments") if isinstance(net.get("segments"), list) else []

    def ids(items: list, base: str, label: str) -> set:
        seen: set = set()
        for i, item in enumerate(items):
            if not isinstance(item, dict) or not isinstance(item.get("id"), int) or isinstance(item.get("id"), bool):
                continue
            if item["id"] in seen:
                out.append((f"{base}/{i}/id", item["id"], f"duplicate {label} id"))
            seen.add(item["id"])
        return seen

    node_ids = ids(nodes, "/network/nodes", "node")
    seg_ids = ids(segs, "/network/segments", "segment")
    fleet = b.get("fleet") if isinstance(b.get("fleet"), list) else []
    ids(fleet, "/fleet", "truck")

    for i, s in enumerate(segs):
        if not isinstance(s, dict):
            continue
        for end in ("a", "b"):
            v = s.get(end)
            if isinstance(v, int) and not isinstance(v, bool) and v not in node_ids:
                out.append((f"/network/segments/{i}/{end}", v, "segment end point is not a node"))

    loaders = b.get("loaders") if isinstance(b.get("loaders"), list) else []
    loader_nodes: set = set()
    for i, ld in enumerate(loaders):
        if not isinstance(ld, dict):
            continue
        v = ld.get("node")
        if isinstance(v, int) and not isinstance(v, bool):
            loader_nodes.add(v)
            if v not in node_ids:
                out.append((f"/loaders/{i}/node", v, "loader node is not a node of the network"))
        d = ld.get("destination_dump")
        if isinstance(d, int) and not isinstance(d, bool) and isinstance(b.get("dumps"), list) and d not in b["dumps"]:
            out.append((f"/loaders/{i}/destination_dump", d, "declared destination is not one of the dumps"))
    for i, d in enumerate(b.get("dumps") if isinstance(b.get("dumps"), list) else []):
        if isinstance(d, int) and not isinstance(d, bool) and d not in node_ids:
            out.append((f"/dumps/{i}", d, "dump node is not a node of the network"))
    for i, t in enumerate(fleet):
        if isinstance(t, dict):
            v = t.get("start_loader")
            if isinstance(v, int) and not isinstance(v, bool) and v not in loader_nodes:
                out.append((f"/fleet/{i}/start_loader", v, "start loader is not a loader node"))

    zones = net.get("zones") if isinstance(net.get("zones"), list) else []
    zone_ids = {z["id"] for z in zones if isinstance(z, dict) and isinstance(z.get("id"), int)}
    for i, s in enumerate(segs):
        if isinstance(s, dict) and s.get("zone_id") is not None and s.get("zone_id") not in zone_ids:
            out.append(
                (f"/network/segments/{i}/zone_id", s["zone_id"], "segment names a zone the network does not define")
            )
    for i, z in enumerate(zones):
        for j, sid in enumerate(z.get("segment_ids", []) if isinstance(z, dict) else []):
            if sid not in seg_ids:
                out.append((f"/network/zones/{i}/segment_ids/{j}", sid, "zone names a segment that does not exist"))
    for i, j in enumerate(net.get("junctions") if isinstance(net.get("junctions"), list) else []):
        if isinstance(j, dict) and j.get("node") not in node_ids:
            out.append((f"/network/junctions/{i}/node", j.get("node"), "junction node is not a node of the network"))

    eq = b.get("equipment") if isinstance(b.get("equipment"), dict) else {}
    from minehaulsim.equipment.catalog import LOADERS, TRUCKS

    for i, e in enumerate(eq.get("truck_classes") if isinstance(eq.get("truck_classes"), list) else []):
        if isinstance(e, dict) and e.get("name") in TRUCKS:
            _diff(f"/equipment/truck_classes/{i}", e, _catalog_truck(e["name"]), out)
    for i, e in enumerate(eq.get("loader_classes") if isinstance(eq.get("loader_classes"), list) else []):
        if isinstance(e, dict) and e.get("name") in LOADERS:
            _diff(f"/equipment/loader_classes/{i}", e, _catalog_loader(e["name"]), out)

    h, kw = b.get("horizon_s"), b.get("kpi_window")
    if (
        isinstance(h, (int, float))
        and not isinstance(h, bool)
        and math.isfinite(h)
        and 0 < h <= MAX_HORIZON_S
        and isinstance(kw, dict)
        and isinstance(kw.get("warmup_s"), (int, float))
        and math.isfinite(kw["warmup_s"])
        and kw["warmup_s"] >= h
    ):
        out.append(("/kpi_window/warmup_s", kw["warmup_s"], "warm-up must be shorter than the horizon"))


def validate_bundle(bundle: Any) -> None:
    """Raise InvalidScenario (or InvalidHorizon) listing every violation; return None for a valid bundle."""
    if not isinstance(bundle, dict):
        raise InvalidScenario([("", _short(bundle), "a scenario bundle must be a JSON object")])
    out: list[tuple[str, object, str]] = []
    non_finite: list[tuple[str, Any]] = []
    _walk_numbers(bundle, "", non_finite)
    bad_paths = {p for p, _ in non_finite}
    for p, v in non_finite:
        out.append((p, v, "a number must be finite"))
    for err in _validator(SCHEMA).iter_errors(bundle):
        p = _pointer(err)
        if p in bad_paths:
            continue
        out.append((p, _short(err.instance), err.message[:200]))
    _structural(bundle, out)
    seen: set = set()
    unique = []
    for v in sorted(out, key=lambda v: (v[0], v[2])):
        if (v[0], v[2]) not in seen:
            seen.add((v[0], v[2]))
            unique.append(v)
    if not unique:
        return
    if all(v[0] == "/horizon_s" for v in unique):
        raise InvalidHorizon(unique)
    raise InvalidScenario(unique)


def load_bundle(path: Path) -> dict:
    """Read, parse (NaN and Infinity tokens are tolerated, then rejected as violations) and validate a bundle file."""
    try:
        text = Path(path).read_text(encoding="utf-8")
        doc = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidScenario([("", "<unreadable>", f"the bundle is not a readable JSON file: {exc}")]) from None
    validate_bundle(doc)
    return doc


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-04: reachability on the frozen network
# ---------------------------------------------------------------------------------------------------------------------
def check_connectivity(bundle: dict) -> None:
    """Raise DisconnectedNetwork naming every unreachable (origin, destination, truck class) between loaders and dumps."""
    from minehaulsim.equipment.catalog import TRUCKS

    classes = sorted({t["truck_class"] for t in bundle["fleet"]})
    loaders = sorted(ld["node"] for ld in bundle["loaders"])
    dumps = sorted(bundle["dumps"])
    triples: list[tuple[int, int, str]] = []
    for cls in classes:
        width = TRUCKS[cls].width_class
        adj: dict[int, list[int]] = {n["id"]: [] for n in bundle["network"]["nodes"]}
        for s in bundle["network"]["segments"]:
            if width > s["width_class"]:
                continue  # a wider vehicle cannot use the segment at all
            adj[s["a"]].append(s["b"])
            if not s["one_way"]:
                adj[s["b"]].append(s["a"])
        reach: dict[int, set[int]] = {}
        for origin in {*loaders, *dumps}:
            seen = {origin}
            queue = deque([origin])
            while queue:
                u = queue.popleft()
                for v in adj[u]:
                    if v not in seen:
                        seen.add(v)
                        queue.append(v)
            reach[origin] = seen
        for ld in loaders:
            for d in dumps:
                if d not in reach[ld]:
                    triples.append((ld, d, cls))
                if ld not in reach[d]:
                    triples.append((d, ld, cls))
    if triples:
        raise DisconnectedNetwork(sorted(set(triples)))


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-12: the twin's declared feature set
# ---------------------------------------------------------------------------------------------------------------------
def unsupported_features(bundle: dict) -> list[str]:
    """The reference-engine features the bundle uses that the twin does not support, in the documented order."""
    ro = bundle.get("reference_only") or {}
    used = []
    for key in TWIN_UNSUPPORTED:
        v = ro.get(key)
        if key in ("lhds", "ore_passes"):
            if v:
                used.append(key)
        elif key == "zone_penalty_s":
            if v is not None and v != 0:
                used.append(key)
        elif v is not None:
            used.append(key)
    return used


def check_twin_features(bundle: dict) -> None:
    features = unsupported_features(bundle)
    if features:
        raise UnsupportedFeature(features)
