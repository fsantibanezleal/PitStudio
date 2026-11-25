# ruff: noqa: E501
"""Leg recorder of the haulage reference engine: where every truck is, leg by leg, for the traffic layer of case B1 (spec 018
FR-018-55, docs M20 "haul trucks follow trajectories from the DES").

The pinned engine in traffic mode records an event only for some callbacks; the passage of a truck through a road segment is
not among them. `run_shift_with_legs` runs the same shift through the adapter (`adapter.run_shift`, so the variate source, the
pin guard and the KPI layer are unchanged) while three engine methods are wrapped by recorders that only read:

- `_Sim._go` names the truck that starts a leg,
- `TrafficState.traverse` opens a leg record (call time, loaded flag, the route's segment uses),
- `TrafficState._enter_zone_then_segment` times each segment: the request time, the exit time and the kinematic traversal time
  (`traverse_time_s` with the engine's own cruise speed and entry speed, the very value the engine used).

The recorders add no event and draw no random number, so the trace, the cyclelog and the KPIs of the run equal those of
`adapter.run_shift` (checked by `tests/pipeline/test_b1_traffic_legs.py`). All wrappers are removed on exit, also on error.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .adapter import RunResult, run_shift


@dataclass
class SegmentPass:
    """One truck passage through one road segment."""

    segment_id: int
    direction: int  # +1 from a to b, -1 from b to a
    t_request_s: float
    t_exit_s: float
    t_kinematic_s: float  # the engine's kinematic traversal time of the segment (cruise plus the acceleration penalty)


@dataclass
class Leg:
    truck: int
    t_call_s: float
    loaded: bool
    passes: list[SegmentPass] = field(default_factory=list)


@dataclass
class LegRun:
    result: RunResult
    legs: list[Leg]
    arrivals: list[tuple[str, float, int, int]]  # (kind, t_s, truck, node) at every loader and dump arrival


class _StateProxy:
    """The traffic state as the engine's `traverse` sees it, with the segment entry replaced by the recording one."""

    def __init__(self, real: Any, leg: Leg, enter: Any, traverse_time_s: Any) -> None:
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_leg", leg)
        object.__setattr__(self, "_enter", enter)
        object.__setattr__(self, "_tt", traverse_time_s)

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_real"), name)

    def _enter_zone_then_segment(self, unit, gvw_t, loaded, seg, direction, v_entry, caps, done):
        real = object.__getattribute__(self, "_real")
        leg = object.__getattribute__(self, "_leg")
        tt = object.__getattribute__(self, "_tt")
        t_req = real.engine.now

        def done_recorded(v_exit: float) -> None:
            leg.passes.append(
                SegmentPass(seg.id, direction, t_req, real.engine.now, float(tt(seg.length_m, v_exit, v_entry, loaded)))
            )
            done(v_exit)

        return object.__getattribute__(self, "_enter")(
            real, unit, gvw_t, loaded, seg, direction, v_entry, caps, done_recorded
        )


def run_shift_with_legs(bundle_path: Path, *, seed: int, **kwargs: Any) -> LegRun:
    """`adapter.run_shift` with the leg recorders installed. Keyword arguments are those of `run_shift`."""
    from minehaulsim.des import sim, traversal

    state_cls = traversal.TrafficState
    orig_go, orig_traverse, orig_enter = sim._Sim._go, state_cls.traverse, state_cls._enter_zone_then_segment
    orig_go_load, orig_arrive_dump = sim._Sim._go_load, sim._Sim._arrive_dump
    legs: list[Leg] = []
    arrivals: list[tuple[str, float, int, int]] = []
    current: dict[str, int | None] = {"truck": None}

    def go(self, truck, a, b, loaded, payload, arrive_cb, *cb_args):
        before = current["truck"]
        current["truck"] = truck.truck_id
        try:
            return orig_go(self, truck, a, b, loaded, payload, arrive_cb, *cb_args)
        finally:
            current["truck"] = before

    def traverse(self, unit, gvw_t, loaded, route, speed_caps, on_done):
        leg = Leg(int(current["truck"]), self.engine.now, bool(loaded))  # type: ignore[arg-type]
        legs.append(leg)
        proxy = _StateProxy(self, leg, orig_enter, traversal.traverse_time_s)
        return orig_traverse(proxy, unit, gvw_t, loaded, route, speed_caps, on_done)

    @functools.wraps(orig_go_load)  # the recorder of the adapter names callbacks by __name__
    def go_load(self, tid, loader):
        arrivals.append(("arrive-loader", self.engine.now, tid, loader))
        return orig_go_load(self, tid, loader)

    @functools.wraps(orig_arrive_dump)
    def arrive_dump(self, tid, dump, payload):
        arrivals.append(("arrive-dump", self.engine.now, tid, dump))
        return orig_arrive_dump(self, tid, dump, payload)

    sim._Sim._go, state_cls.traverse = go, traverse
    sim._Sim._go_load, sim._Sim._arrive_dump = go_load, arrive_dump
    try:
        result = run_shift(bundle_path, seed=seed, **kwargs)
    finally:
        sim._Sim._go, state_cls.traverse = orig_go, orig_traverse
        sim._Sim._go_load, sim._Sim._arrive_dump = orig_go_load, orig_arrive_dump
    return LegRun(result, legs, arrivals)
