# ruff: noqa: E501
"""Mixed autonomous and manned traffic on a haul road network with the time to collision of every close pair (case B1, spec 018
FR-018-55, docs M20 "Agents" and "Time-to-collision"), CPU only.

What it simulates. Every haul truck follows the trajectory the pinned discrete-event engine produced for it (the legs recorded by
`legs.run_shift_with_legs`: segment by segment, with the engine's queue waits and kinematic traversal times). Manned light
vehicles patrol the same network: seeded random trips between design nodes along the shortest path at a fraction of each
segment's speed limit, with exponential dwell times at the nodes. Every vehicle drives in its own lane, offset from the road
centre line by `lane_offset_m` to the right (mitered at the vertices of its path), so that opposing vehicles pass at twice the
offset and only vehicles that share a lane or cross a path can touch.

The time-stepped layer (`dt_s`) moves each vehicle along its own timeline with a progress variable tau: velocity is the planned
velocity at tau times a multiplier m in [0, 1]. With m = 1 throughout, a truck is exactly where the engine put it at every time
(parity with the DES); a vehicle that brakes lags its schedule, and tau stops advancing in proportion.

Yielding (the only behavioural rule, all values are recipe inputs). A vehicle yields to another when (a) the other is ahead of it
within `look_ahead_m` and in its narrow forward cone (following) or in its forward half plane and of higher priority (crossing),
and (b) the constant-velocity TTC of the pair, with the yielding vehicle at its planned velocity and the other at its actual
velocity, is below `brake_ttc_s`. Priority is haul truck over light vehicle, ties by lower vehicle id. Whoever has the right of way still brakes for any vehicle ahead
whose TTC falls below `emergency_ttc_s` while that vehicle is still moving (a stopped vehicle is yielding), so an imminent conflict
is not left to the other party. A threat that persists for
the class reaction time `reaction_s` makes the vehicle brake at its deceleration; it keeps braking for `brake_hold_s` after the last trigger and re-accelerates when the threat is gone; a threat that flickers lowers the reaction timer by dt per step instead of restarting it. A
vehicle blocked for `release_s` (staggered by 0.25 s per vehicle index) goes ahead regardless until the threat clears: this
negotiated go breaks the cycles of yields that opposing vehicles at a junction can form, and is counted in `releases`. The
class reaction time is what differs between an autonomous and a manned truck, so the share of autonomous trucks acts only
through it. Pairs are left out when either vehicle is at rest in its plan (queued, loading, dumping, dwelling: the engine puts queued
trucks on the node, not in lane slots, and light vehicles are taken to dwell off the road; a truck at rest still is a body, an obstacle for a moving light vehicle) and when both are trucks (the engine
already separates trucks with segment slots and a no-overtake headway, and declares no junction control in this network, so
truck-truck crossing conflicts are possible and not evaluated here).

Bodies. Every vehicle is an oriented rectangle of its footprint (`footprint_m`, the asset specification's length and width), centred on
its position and aligned with its heading. Two footprints never overlap: when the pair would touch within the coming step (the
swept contact time `ttc.obb_pairs` of the step velocities is below dt) or overlap already and get deeper, that is a collision event,
counted once per episode (contacts of a pair closer than `collision_gap_s` are one event), and the body that would run into the
other is stopped for the step: the lower-ranked first, the other one too when that does not keep them apart. An overlap has no
time to collision (NaN, left out of every minimum): there is never a TTC of 0. A body at rest in its plan does not negotiate, so
the negotiated go-ahead applies only against vehicles that move.

Metrics. An encounter is a maximal time window in which two moving vehicles are within `encounter_radius_m`; its
minimum TTC is the smallest constant-velocity TTC of the pair over the window (infinite when the pair never closes). A near-miss is
an encounter whose minimum TTC is below `near_miss_ttc_s`; exposure is vehicle-hours of the evaluation window. Throughput counts
the engine's return events (tonnes) at the time the lagging truck reaches them; the delay is applied to the engine schedule after
the fact, so queueing knock-on at loaders and dumps is not re-simulated.

Honest limits: behaviour is rule-based and parameterised, not learned from driver data; constant-velocity TTC ignores braking
and steering; the footprints, lane offset, manned reaction time and decelerations are cited and the other inputs UNVERIFIED for any
site (see `b1_run.INPUT_ROWS`); a body stopped by contact stops within one step, which no real machine does; calibrated synthetic.
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from pitstudio.haulage.ttc import obb_pairs

from .legs import Leg

TRUCK, LIGHT = 0, 1
PAIR_TT, PAIR_TL, PAIR_LL = 0, 1, 2
PAIR_NAMES = {PAIR_TT: "truck-truck", PAIR_TL: "truck-light-vehicle", PAIR_LL: "light-vehicle-light-vehicle"}
BIG = 1.0e6  # key stride of the timeline search: vehicle id * BIG + time; times stay below it
DEFAULTS: dict[str, Any] = {
    # sourced inputs (`b1_run.INPUT_ROWS` gives each source with its page or table)
    "footprint_m": {
        "haul-truck": [13.36, 8.563],
        "light-vehicle": [5.275, 1.96],
    },  # length, width: the asset specification (Cat 793F, Land Cruiser 79)
    "lane_offset_m": 7.493,  # 0.875 x the truck width: lane centre of a two-lane road of 3.5 x the truck width (Tannant and Regensburg 2001, Eq. 5)
    "reaction_s": {
        "autonomous": 0.5,
        "manned": 1.5,
    },  # manned: driver reaction (Tannant and Regensburg 2001, p. 14); autonomous: UNVERIFIED
    "decel_mps2": {
        "haul-truck": 2.94,
        "light-vehicle": 3.4,
    },  # truck: Kaufman and Ault via Tannant and Regensburg 2001, p. 14; light vehicle: AASHTO 11.2 ft/s2 (TxDOT RDM 4.11.1)
    # model rules and inputs without a source, UNVERIFIED
    "dt_s": 0.5,
    "accel_mps2": {"haul-truck": 1.0, "light-vehicle": 2.0},
    "brake_ttc_s": 6.0,
    "look_ahead_m": 100.0,
    "follow_half_angle_deg": 20.0,
    "encounter_radius_m": 60.0,
    "near_miss_ttc_s": 3.0,  # FR-018-55
    "emergency_ttc_s": 3.5,
    "brake_hold_s": 1.0,
    "release_s": 30.0,
    "collision_gap_s": 5.0,  # contacts of one pair closer in time than this are one collision event
    "light_vehicle": {"speed_factor": 0.9, "dwell_mean_s": 60.0},
}


# ---------------------------------------------------------------------------------------------------------------------
# geometry


@dataclass(frozen=True)
class RoadNet:
    nodes: dict[int, tuple[float, float]]
    segments: dict[int, dict[str, Any]]  # id -> {a, b, pts (k, 2), length_m, limit_kmh}
    adjacency: dict[int, list[tuple[int, int, int, float]]]  # node -> [(neighbour, segment id, direction, length)]


def road_net(bundle: dict) -> RoadNet:
    """The network of a scenario bundle (`contracts/haul-scenario.schema.json`) as plain geometry."""
    nodes = {n["id"]: (float(n["pos_m"][0]), float(n["pos_m"][1])) for n in bundle["network"]["nodes"]}
    segments, adj = {}, defaultdict(list)
    for s in bundle["network"]["segments"]:
        pts = np.asarray([[p[0], p[1]] for p in s["polyline_m"]], dtype=float)
        segments[s["id"]] = {
            "a": s["a"],
            "b": s["b"],
            "pts": pts,
            "length_m": float(s["length_m"]),
            "limit_kmh": float(s["speed_limit_kmh"]),
        }
        adj[s["a"]].append((s["b"], s["id"], +1, float(s["length_m"])))
        adj[s["b"]].append((s["a"], s["id"], -1, float(s["length_m"])))
    return RoadNet(nodes, segments, dict(adj))


def offset_polyline(points: np.ndarray, offset_m: float, miter_cap: float = 3.0) -> np.ndarray:
    """The polyline moved `offset_m` to its right, mitered at the interior vertices (the miter length is capped at `miter_cap`
    offsets). Repeated vertices are an error of the caller; a one-vertex polyline is returned unchanged."""
    pts = np.asarray(points, dtype=float)
    if len(pts) < 2:
        return pts.copy()
    d = np.diff(pts, axis=0)
    ln = np.hypot(d[:, 0], d[:, 1])
    if np.any(ln <= 0):
        raise ValueError("a polyline with a repeated vertex has no offset")
    u = d / ln[:, None]
    n = np.stack([u[:, 1], -u[:, 0]], axis=1)  # right-hand normal of each edge
    out = np.empty_like(pts)
    out[0], out[-1] = pts[0] + n[0] * offset_m, pts[-1] + n[-1] * offset_m
    for k in range(1, len(pts) - 1):
        m = n[k - 1] + n[k]
        mm = float(m @ m)
        if mm < 1e-12:  # a U-turn: no miter exists, use the incoming normal
            out[k] = pts[k] + n[k - 1] * offset_m
            continue
        vec = m * (2.0 * offset_m / mm)
        length = math.hypot(*vec)
        if length > miter_cap * abs(offset_m):
            vec = vec * (miter_cap * abs(offset_m) / length)
        out[k] = pts[k] + vec
    return out


def shortest_path(net: RoadNet, a: int, b: int) -> list[tuple[int, int]]:
    """Dijkstra over segment lengths: the (segment id, direction) uses of the shortest road path from node a to node b."""
    dist, prev = {a: 0.0}, {}
    heap = [(0.0, a)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == b:
            break
        if d > dist.get(u, math.inf):
            continue
        for v, sid, direction, ln in net.adjacency.get(u, []):
            nd = d + ln
            if nd < dist.get(v, math.inf) - 1e-12:
                dist[v], prev[v] = nd, (u, sid, direction)
                heapq.heappush(heap, (nd, v))
    if b not in dist:
        raise ValueError(f"no road path from node {a} to node {b}")
    path = []
    while b != a:
        u, sid, direction = prev[b]
        path.append((sid, direction))
        b = u
    return path[::-1]


def chain_vertices(net: RoadNet, uses: list[tuple[int, int]]) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """The centre-line vertices of a path of segment uses and, per use, the (first, last) vertex index of that use."""
    verts: list[np.ndarray] = []
    spans = []
    for sid, direction in uses:
        pts = net.segments[sid]["pts"]
        pts = pts if direction > 0 else pts[::-1]
        first = len(verts) - 1 if verts else 0
        verts.extend(pts if not verts else pts[1:])
        spans.append((first, len(verts) - 1))
    return np.asarray(verts, dtype=float), spans


# ---------------------------------------------------------------------------------------------------------------------
# timelines


class Timeline:
    """Piecewise-constant-velocity motion: interval i starts at `t[i]` at position `p0[i]` with velocity `v[i]` and lasts until
    the next interval starts. A jump of position between consecutive intervals is allowed (a vehicle turning on the spot)."""

    def __init__(self) -> None:
        self.t: list[float] = []
        self.p: list[tuple[float, float]] = []
        self.v: list[tuple[float, float]] = []
        self.s: list[int] = []  # the road segment of a moving interval, -1 for an interval at rest

    def _add(self, t: float, p: tuple[float, float], v: tuple[float, float], seg: int = -1) -> None:
        if self.t and t < self.t[-1] - 1e-9:
            raise ValueError(f"timeline goes backwards: {t} after {self.t[-1]}")
        self.t.append(max(t, self.t[-1]) if self.t else t)
        self.p.append((float(p[0]), float(p[1])))
        self.v.append((float(v[0]), float(v[1])))
        self.s.append(int(seg))

    def stay(self, t: float, p: Any) -> None:
        self._add(t, (p[0], p[1]), (0.0, 0.0))

    def move(self, t0: float, t1: float, p0: Any, p1: Any, seg: int = -1) -> None:
        """Straight motion from p0 at t0 to p1 at t1 on road segment `seg`, then at rest at p1."""
        if t1 <= t0:
            raise ValueError("a move needs t1 > t0")
        v = ((p1[0] - p0[0]) / (t1 - t0), (p1[1] - p0[1]) / (t1 - t0))
        self._add(t0, p0, v, seg)
        self._add(t1, p1, (0.0, 0.0))

    def arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return np.asarray(self.t), np.asarray(self.p), np.asarray(self.v)

    def segments(self) -> np.ndarray:
        return np.asarray(self.s, dtype=int)


def _drive_chain(
    tl: Timeline, offs: np.ndarray, cen: np.ndarray, span: tuple[int, int], t0: float, t1: float, seg: int = -1
) -> None:
    """Motion over the vertices span[0]..span[1] of an offset chain between t0 and t1, time proportional to centre-line length."""
    i0, i1 = span
    lengths = np.hypot(*np.diff(cen[i0 : i1 + 1], axis=0).T)
    total = float(lengths.sum())
    cum = np.concatenate([[0.0], np.cumsum(lengths)])
    for k in range(i0, i1):
        a = t0 + (t1 - t0) * cum[k - i0] / total
        b = t0 + (t1 - t0) * cum[k - i0 + 1] / total
        if b > a:
            tl.move(a, b, offs[k], offs[k + 1], seg)


def truck_timeline(net: RoadNet, legs: list[Leg], start_node: int, lane_offset_m: float) -> Timeline:
    """The lane trajectory of one truck from its recorded legs. Within a segment the truck waits at the segment entry until
    `t_exit - t_kinematic` (or its request time if later) and then moves at the average kinematic speed to the segment exit."""
    tl = Timeline()
    legs = sorted((g for g in legs if g.passes), key=lambda g: g.t_call_s)
    first_pos = net.nodes[start_node]
    tl.stay(0.0, first_pos)
    for leg in legs:
        uses = [(p.segment_id, p.direction) for p in leg.passes]
        cen, spans = chain_vertices(net, uses)
        offs = offset_polyline(cen, lane_offset_m)
        tl.stay(leg.t_call_s, offs[0])
        for p, span in zip(leg.passes, spans, strict=True):
            ts = max(p.t_request_s, p.t_exit_s - p.t_kinematic_s)
            if p.t_exit_s <= ts:
                continue
            _drive_chain(tl, offs, cen, span, ts, p.t_exit_s, p.segment_id)
    return tl


def light_vehicle_timeline(
    net: RoadNet,
    node_ids: list[int],
    rng: np.random.Generator,
    horizon_s: float,
    speed_factor: float,
    dwell_mean_s: float,
    lane_offset_m: float,
) -> Timeline:
    """Seeded random trips between design nodes along the shortest road path, at `speed_factor` times each segment's limit."""
    tl = Timeline()
    node = int(rng.choice(node_ids))
    t = 0.0
    tl.stay(0.0, net.nodes[node])
    t += float(rng.exponential(dwell_mean_s))
    while t < horizon_s:
        dest = int(rng.choice([n for n in node_ids if n != node]))
        uses = shortest_path(net, node, dest)
        cen, spans = chain_vertices(net, uses)
        offs = offset_polyline(cen, lane_offset_m)
        tl.stay(t, offs[0])
        for (sid, _), span in zip(uses, spans, strict=True):
            seg = net.segments[sid]
            dt = seg["length_m"] / (speed_factor * seg["limit_kmh"] / 3.6)
            _drive_chain(tl, offs, cen, span, t, t + dt, sid)
            t += dt
        node = dest
        tl.stay(t, offs[-1])
        t += float(rng.exponential(dwell_mean_s))
    return tl


# ---------------------------------------------------------------------------------------------------------------------
# the time-stepped layer


@dataclass
class Vehicle:
    vid: int
    kind: int  # TRUCK or LIGHT
    autonomous: bool
    timeline: Timeline
    events: list[tuple[float, float]] = field(
        default_factory=list
    )  # (engine time, tonnes) of the return events of a truck


@dataclass
class TrafficResult:
    n_vehicles: int
    encounters: np.ndarray  # structured: i, j, pair, t0, min_ttc, min_gap, auton, collisions
    near_misses: int
    collisions: int  # collision events of the window: episodes in which two footprints would have overlapped (counted, never a TTC of 0)
    exposure_vehicle_h: float
    tonnes_des: float  # engine tonnes of the window
    tonnes_delivered: float  # tonnes of the window after the braking delays
    held_truck_s: float  # truck seconds spent braked or held (m < 1 while the plan moves)
    releases: int  # negotiated go-aheads that broke a block longer than release_s
    final_tau: np.ndarray
    contact_hold_s: float = 0.0  # vehicle seconds of the window stopped to keep two footprints apart
    trace_pos: np.ndarray | None = None
    trace_m: np.ndarray | None = None
    trace_cand: np.ndarray | None = None  # (steps + 1, n, n): vehicle i yields to vehicle j at that step


ENC_DTYPE = np.dtype(
    [
        ("i", "i4"), ("j", "i4"), ("pair", "i1"), ("t0", "f8"), ("min_ttc", "f8"), ("min_gap", "f8"), ("auton", "i1"),
        ("collisions", "i2"),
    ]
)  # fmt: skip


def _params(p: dict[str, Any] | None) -> dict[str, Any]:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    for k, v in (p or {}).items():
        if k not in DEFAULTS:
            raise ValueError(f"unknown traffic parameter {k!r}")
        out[k] = {**out[k], **v} if isinstance(v, dict) else v
    return out


def _headings(t: np.ndarray, p: np.ndarray, v: np.ndarray) -> np.ndarray:
    """The heading angle (rad) of every interval of a timeline: that of its velocity while it moves; at rest the last heading,
    or the next one after a jump of position (a vehicle placed at the start of its next path) and before the first move."""
    n = len(t)
    sp = np.hypot(v[:, 0], v[:, 1])
    moving = sp > 1e-9
    ang = np.where(moving, np.arctan2(v[:, 1], np.where(moving, v[:, 0], 1.0)), np.nan)
    nxt = np.full(n, np.nan)
    cur = np.nan
    for i in range(n - 1, -1, -1):
        if moving[i]:
            cur = ang[i]
        nxt[i] = cur
    out = np.empty(n)
    last = np.nan
    for i in range(n):
        if moving[i]:
            last = ang[i]
            out[i] = ang[i]
            continue
        jump = i > 0 and float(np.hypot(*(p[i] - (p[i - 1] + v[i - 1] * (t[i] - t[i - 1]))))) > 0.5
        out[i] = nxt[i] if (jump or np.isnan(last)) else last
        if np.isnan(out[i]):
            out[i] = last if not np.isnan(last) else 0.0
    return out


def simulate(
    vehicles: list[Vehicle],
    *,
    horizon_s: float,
    warmup_s: float,
    net: RoadNet | None = None,
    params: dict[str, Any] | None = None,
    interactions: bool = True,
    trace: bool = False,
) -> TrafficResult:
    """Run the time-stepped layer over `horizon_s` and return the encounters and the counts of the window [warmup_s, horizon_s]."""
    cfg = _params(params)
    n = len(vehicles)
    if n < 1:
        raise ValueError("no vehicles")
    dt = float(cfg["dt_s"])
    steps = round(horizon_s / dt)
    kind = np.array([v.kind for v in vehicles])
    auton = np.array([v.autonomous for v in vehicles], dtype=bool)
    vid = np.array([v.vid for v in vehicles], dtype=float)
    if len(set(vid.tolist())) != n:
        raise ValueError("vehicle ids must be unique")
    cls = ["haul-truck" if k == TRUCK else "light-vehicle" for k in kind]
    half = np.array([cfg["footprint_m"][c] for c in cls], dtype=float) / 2.0  # (n, 2): half length, half width
    decel = np.array([cfg["decel_mps2"][c] for c in cls])
    accel = np.array([cfg["accel_mps2"][c] for c in cls])
    react = np.where(auton, cfg["reaction_s"]["autonomous"], cfg["reaction_s"]["manned"]).astype(float)
    rank = (
        np.where(kind == TRUCK, 2.0, 1.0) * 1e6 - vid
    )  # higher wins; a truck beats a light vehicle, a lower id beats a higher one
    cos_follow = math.cos(math.radians(cfg["follow_half_angle_deg"]))
    look, enc_r = float(cfg["look_ahead_m"]), float(cfg["encounter_radius_m"])
    brake_ttc, nm_ttc = float(cfg["brake_ttc_s"]), float(cfg["near_miss_ttc_s"])
    emergency_ttc, brake_hold = float(cfg["emergency_ttc_s"]), float(cfg["brake_hold_s"])
    collision_gap = float(cfg["collision_gap_s"])
    is_truck = kind == TRUCK
    eye = np.eye(n, dtype=bool)
    upper = np.triu(np.ones((n, n), dtype=bool), 1)
    tt_pair = (
        is_truck[:, None] & is_truck[None, :]
    )  # truck against truck is the engine's business (slots, headway), not evaluated here
    pair_type = np.where(
        is_truck[:, None] & is_truck[None, :],
        PAIR_TT,
        np.where(is_truck[:, None] | is_truck[None, :], PAIR_TL, PAIR_LL),
    ).astype(np.int8)

    # the timelines as one searchable table
    keys, p0, vv, ts_all, sg_all, hd_all = [], [], [], [], [], []
    for k, v in enumerate(vehicles):
        t, p, vel = v.timeline.arrays()
        if len(t) == 0 or np.any(np.diff(t) < 0) or t[-1] >= BIG:
            raise ValueError(f"vehicle {v.vid}: an empty, unordered or too long timeline")
        keys.append(k * BIG + t)
        ts_all.append(t)
        sg_all.append(v.timeline.segments())
        p0.append(p)
        vv.append(vel)
        hd_all.append(_headings(t, p, vel))
    keys, ts_all, p0, vv, sg_all, hd_all = (
        np.concatenate(keys),
        np.concatenate(ts_all),
        np.concatenate(p0),
        np.concatenate(vv),
        np.concatenate(sg_all),
        np.concatenate(hd_all),
    )
    # two moving vehicles can only conflict on the road graph: on one segment or on two segments that share a node
    seg_ids = sorted(net.segments) if net is not None else []
    seg_index = {sid: k for k, sid in enumerate(seg_ids)}
    nodes_of = {sid: (net.segments[sid]["a"], net.segments[sid]["b"]) for sid in seg_ids} if net is not None else {}
    touch = np.zeros((len(seg_ids) + 1, len(seg_ids) + 1), dtype=bool)  # the last row and column stand for "no segment"
    for a_id in seg_ids:
        for b_id in seg_ids:
            touch[seg_index[a_id], seg_index[b_id]] = bool(set(nodes_of[a_id]) & set(nodes_of[b_id]))
    sg_map = np.array([seg_index.get(int(x), len(seg_ids)) for x in sg_all], dtype=int)

    # the events a truck delivers: tau of the engine event and its tonnes
    ev_tau = [np.array([e[0] for e in v.events]) for v in vehicles]
    ev_t = [np.array([e[1] for e in v.events]) for v in vehicles]
    ev_ptr = np.zeros(n, dtype=int)
    tonnes_des = sum(
        float(t[(tau >= warmup_s) & (tau <= horizon_s)].sum()) for tau, t in zip(ev_tau, ev_t, strict=True)
    )
    tonnes_delivered = 0.0
    nxt = np.array([e[0] if len(e) else np.inf for e in ev_tau])

    tau = np.zeros(n)
    m = np.ones(n)
    thr = np.zeros(n)
    hold = np.zeros(n)
    wait = np.zeros(n)  # seconds a vehicle has been blocked without a break
    releases = 0
    release_after = float(cfg["release_s"]) + 0.25 * np.arange(
        n
    )  # staggered by index so that a cycle is broken one vehicle at a time
    active = np.zeros((n, n), dtype=bool)
    emin = np.full((n, n), np.inf)
    egap = np.full((n, n), np.inf)
    et0 = np.zeros((n, n))
    ecol = np.zeros((n, n), dtype=np.int16)
    col_until = np.full((n, n), -np.inf)  # a contact before this time continues the collision event of the pair
    out: list[tuple] = []
    held = 0.0
    contact_hold = 0.0
    tr_pos = np.zeros((steps + 1, n, 2)) if trace else None
    tr_m = np.zeros((steps + 1, n)) if trace else None
    tr_cand = np.zeros((steps + 1, n, n), dtype=bool) if trace else None
    idx_base = np.arange(n) * BIG

    def finalize(mask: np.ndarray) -> None:
        for i, j in zip(*np.nonzero(mask), strict=True):
            if et0[i, j] >= warmup_s:
                a = int(auton[i]) + int(auton[j])
                out.append((i, j, pair_type[i, j], et0[i, j], emin[i, j], egap[i, j], a, ecol[i, j]))

    for step in range(steps + 1):
        now = step * dt
        k = np.searchsorted(keys, idx_base + np.minimum(tau, BIG - 1.0), side="right") - 1
        pos = p0[k] + vv[k] * (tau - ts_all[k])[:, None]
        pv = vv[k]
        spd = np.hypot(pv[:, 0], pv[:, 1])
        vel = pv * m[:, None]
        hv = np.stack([np.cos(hd_all[k]), np.sin(hd_all[k])], axis=1)  # unit heading of every footprint
        if trace:
            tr_pos[step], tr_m[step] = pos, m  # type: ignore[index]
        d = pos[None, :, :] - pos[:, None, :]  # d[i, j] = position of j minus position of i
        dist = np.hypot(d[..., 0], d[..., 1])
        planned = (
            spd > 1e-9
        )  # a vehicle at rest in its plan (queued, loading, dumping, dwelling) has no motion; a truck at rest is still a body
        rest_truck = ~planned & is_truck  # in the way of a moving vehicle; a light vehicle at rest dwells off the road
        both_moving = planned[:, None] & planned[None, :]
        ev = (
            ~eye
            & ~tt_pair
            & (both_moving | (planned[:, None] & rest_truck[None, :]) | (rest_truck[:, None] & planned[None, :]))
        )
        if net is not None:
            sidx = sg_map[k]
            ev &= touch[sidx[:, None], sidx[None, :]] | ~both_moving
        within = (dist <= enc_r) & ev & upper
        pi, pj = np.nonzero(within)

        def pair_geometry(ia, ja, va, vb, rel=None, pos=pos, hv=hv):
            """Time to contact and separation of the footprints of the pairs (ia, ja) with the velocities `va` of ia and `vb` of ja."""
            rel = (pos[ja] - pos[ia]) if rel is None else rel
            return obb_pairs(rel, vb - va, hv[ia], hv[ja], half[ia], half[ja])

        if len(pi) or active.any():
            if len(pi):
                tt_e, sep_e = pair_geometry(pi, pj, vel[pi], vel[pj])
                started = within & ~active
                emin[started], egap[started], et0[started], ecol[started] = np.inf, np.inf, now, 0
                emin[pi, pj] = np.fmin(emin[pi, pj], tt_e)  # an overlap has no TTC: NaN is left out of the minimum
                egap[pi, pj] = np.minimum(egap[pi, pj], sep_e)
            ended = active & ~within
            if ended.any():
                finalize(ended)
            active = within.copy()
        threat = np.zeros(n, dtype=bool)
        blocked_by_mover = np.zeros(n, dtype=bool)
        if interactions:
            near = (dist <= look) & ev
            if near.any():
                heading = pv / np.where(spd > 1e-9, spd, 1.0)[:, None]
                fwd = (d[..., 0] * heading[:, None, 0] + d[..., 1] * heading[:, None, 1]) / np.where(
                    dist > 0, dist, 1.0
                )
                ahead = near & (planned[None, :] | rest_truck[None, :])
                ii, jj = np.nonzero(ahead)
                ttc_p = np.full((n, n), np.inf)
                if len(ii):
                    t_p, _ = pair_geometry(ii, jj, pv[ii], vel[jj])  # the yielding vehicle at its planned velocity
                    ttc_p[ii, jj] = np.nan_to_num(t_p, nan=0.0)
                cand = (
                    ahead & (ttc_p < brake_ttc) & ((fwd > cos_follow) | ((fwd > 0) & (rank[None, :] > rank[:, None])))
                )
                cand &= ~(
                    cand & cand.T & (rank[:, None] > rank[None, :])
                )  # of two vehicles that would yield to each other, the higher-ranked goes on
                cand |= (
                    ahead & (fwd > 0) & (ttc_p < emergency_ttc) & (np.hypot(vel[:, 0], vel[:, 1]) > 0.5)[None, :]
                )  # an imminent conflict with a vehicle that is still moving is braked for by whoever has the right of way; a vehicle that has stopped is yielding
                threat = cand.any(axis=1) & (spd > 1e-9)
                blocked_by_mover = (cand & planned[None, :]).any(
                    axis=1
                )  # a body at rest in its plan does not negotiate
                if trace:
                    tr_cand[step] = cand  # type: ignore[index]
        wait = np.where(threat, wait + dt, 0.0)
        go = (
            threat & blocked_by_mover & (wait >= release_after)
        )  # a negotiated go after a long block: the only way out of a cycle of yields
        releases += int((go & (wait - dt < release_after)).sum())
        threat = threat & ~go
        core = threat & (thr >= react - 1e-9)
        thr = np.where(
            threat, thr + dt, np.maximum(thr - dt, 0.0)
        )  # a threat that flickers does not restart the reaction time
        hold = np.where(core, brake_hold, np.maximum(hold - dt, 0.0))
        brake = core | (
            (hold > 0) & (spd > 1e-9)
        )  # a braking vehicle keeps braking for brake_hold_s after the last trigger
        safe = np.where(spd > 1e-9, spd, 1.0)
        m_new = np.clip(m + np.where(brake, -decel, accel) * dt / safe, 0.0, 1.0)
        m_new = np.where(spd > 1e-9, m_new, 1.0)

        # bodies do not overlap: a pair whose footprints would touch within this step is a collision event; the body that would
        # run into the other is stopped for the step (the lower-ranked first, the other too when that does not keep them apart)
        stopped = np.zeros(n, dtype=bool)
        if len(pi):
            step_v = pv * (0.5 * (m + m_new))[:, None]

            def bad_pairs(ia, ja, sa, sb, step_v=step_v, pos=pos):
                """Pairs that touch within the step when the vehicles move at the step velocity times the scales `sa`, `sb`."""
                va, vb = step_v[ia] * sa[:, None], step_v[ja] * sb[:, None]
                t_c, s_now = pair_geometry(ia, ja, va, vb)
                over = np.isnan(t_c)
                if not over.any():
                    return t_c < dt
                _, s_end = pair_geometry(ia, ja, va, vb, rel=pos[ja] - pos[ia] + (vb - va) * dt)
                return np.where(over, s_end < s_now - 1e-9, t_c < dt)  # an overlap that exists is not made deeper

            t0c, _ = pair_geometry(pi, pj, step_v[pi], step_v[pj])
            contact = np.isnan(t0c) | (t0c < dt)
            if contact.any():
                ci, cj = pi[contact], pj[contact]
                newly = now > col_until[ci, cj]
                ecol[ci[newly], cj[newly]] += 1
                col_until[ci, cj] = now + collision_gap
                if interactions:
                    for _ in range(4):
                        scale = np.where(stopped, 0.0, 1.0)
                        bad = bad_pairs(pi, pj, scale[pi], scale[pj])
                        if not bad.any():
                            break
                        bi_, bj_ = pi[bad], pj[bad]
                        low_first = rank[bi_] < rank[bj_]
                        lo, hi = np.where(low_first, bi_, bj_), np.where(low_first, bj_, bi_)
                        zero_lo = bad_pairs(
                            bi_, bj_, np.where(bi_ == lo, 0.0, scale[bi_]), np.where(bj_ == lo, 0.0, scale[bj_])
                        )
                        zero_hi = bad_pairs(
                            bi_, bj_, np.where(bi_ == hi, 0.0, scale[bi_]), np.where(bj_ == hi, 0.0, scale[bj_])
                        )
                        stopped[lo[~zero_lo]] = True
                        only_hi = zero_lo & ~zero_hi
                        stopped[hi[only_hi]] = True
                        both = zero_lo & zero_hi
                        stopped[lo[both]] = True
                        stopped[hi[both]] = True
        stopped &= planned
        m_new = np.where(stopped, 0.0, m_new)
        if now >= warmup_s:
            contact_hold += float(stopped.sum()) * dt
        held += float(((m_new < 1.0) & (spd > 1e-9) & is_truck).sum()) * dt if now >= warmup_s else 0.0
        tau_new = np.where(stopped, tau, tau + 0.5 * (m + m_new) * dt)
        # deliveries of the truck events crossed in this step, at the time interpolated inside the step
        for q in np.nonzero(tau_new >= nxt)[0]:
            while ev_ptr[q] < len(ev_tau[q]) and tau_new[q] >= ev_tau[q][ev_ptr[q]] and tau_new[q] > tau[q]:
                frac = (ev_tau[q][ev_ptr[q]] - tau[q]) / (tau_new[q] - tau[q])
                t_del = now + dt * min(max(frac, 0.0), 1.0)
                if warmup_s <= t_del <= horizon_s:
                    tonnes_delivered += float(ev_t[q][ev_ptr[q]])
                ev_ptr[q] += 1
            nxt[q] = ev_tau[q][ev_ptr[q]] if ev_ptr[q] < len(ev_tau[q]) else np.inf
        tau, m = tau_new, m_new
    finalize(active)
    enc = np.array(out, dtype=ENC_DTYPE) if out else np.zeros(0, dtype=ENC_DTYPE)
    nm = int((enc["min_ttc"] < nm_ttc).sum()) if len(enc) else 0
    collisions = int(enc["collisions"].sum()) if len(enc) else 0
    return TrafficResult(
        n,
        enc,
        nm,
        collisions,
        n * (horizon_s - warmup_s) / 3600.0,
        tonnes_des,
        tonnes_delivered,
        held,
        releases,
        tau,
        contact_hold,
        tr_pos,
        tr_m,
        tr_cand,
    )


# ---------------------------------------------------------------------------------------------------------------------
# the agents of one scenario


def _rng(seed: int, stream: int) -> np.random.Generator:
    return np.random.Generator(np.random.Philox(np.random.SeedSequence([int(seed), 0xB1, int(stream)])))


def autonomous_trucks(truck_ids: list[int], share: float, seed: int) -> set[int]:
    """The trucks that are autonomous: the first round(share * N) of a seeded permutation, so the sets nest as the share grows."""
    if not 0.0 <= share <= 1.0:
        raise ValueError(f"the autonomous share must be in [0, 1]: {share!r}")
    order = _rng(seed, 999).permutation(sorted(truck_ids))
    return {int(t) for t in order[: round(share * len(truck_ids))]}


def truck_vehicles(net: RoadNet, run: Any, bundle: dict, lane_offset_m: float, autonomous: set[int]) -> list[Vehicle]:
    """One Vehicle per truck of a `legs.LegRun`: the lane trajectory of its legs and the return events (tonnes) of its cyclelog."""
    by_truck: dict[int, list[Leg]] = defaultdict(list)
    for leg in run.legs:
        by_truck[leg.truck].append(leg)
    payload: dict[int, float] = {}
    events: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for r in run.result.cyclelog:
        if r["event"] == "dump":
            payload[r["truck"]] = r["payload_t"]
        elif r["event"] == "return":
            events[r["truck"]].append((r["t_s"], payload.pop(r["truck"], 0.0)))
    out = []
    for t in sorted(bundle["fleet"], key=lambda t: t["id"]):
        tl = truck_timeline(net, by_truck.get(t["id"], []), t["start_loader"], lane_offset_m)
        out.append(Vehicle(t["id"], TRUCK, t["id"] in autonomous, tl, events.get(t["id"], [])))
    return out


def light_vehicles(
    net: RoadNet, node_ids: list[int], seed: int, count: int, horizon_s: float, cfg: dict[str, Any], first_id: int
) -> list[Vehicle]:
    """`count` manned light vehicles; vehicle k draws from its own stream (seed, k), so a larger fleet contains the smaller one."""
    lv = cfg["light_vehicle"]
    return [
        Vehicle(
            first_id + k, LIGHT, False,
            light_vehicle_timeline(net, node_ids, _rng(seed, k), horizon_s, lv["speed_factor"], lv["dwell_mean_s"], cfg["lane_offset_m"]),
        )
        for k in range(count)
    ]  # fmt: skip
