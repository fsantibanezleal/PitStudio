# ruff: noqa: E501, PERF401, B007
"""KPI layer over a DES trace (FR-007-08, FR-007-42, P-007-20).

From a des-trace document it computes, per loader and for the fleet, over the closed evaluation window [warm-up, horizon]:
production (t/h), cycles per hour, queue time at loaders and dumps (mean and P90, minutes per visit), loader utilisation, the
match factor (from `minephys.haulage`), truck-hours and loader-hours per kilotonne, and cost per tonne only when both hourly
rates are supplied. A trace that fails its schema, is not strictly ordered by (t_s, seq), holds a non-finite time or payload,
or has warm-up >= horizon is rejected with `InvalidTrace` naming the first offending row; no KPI is returned then.

Counting rules: tonnes and cycles by `return` row inside the window, attributed to the loader of the truck's last load; the
queue wait of a loader visit is load start minus the arrival event, of a dump visit dump start minus the arrival event, for
starts inside the window; busy time is the sum of (haul - load) intersected with the window; t_L is the mean (haul - load)
over load starts inside the window.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import numpy as np
from minephys import haulage as _mp

from pitstudio_pipeline._contracts import _validator

from .errors import InvalidTrace
from .honesty import BIAS_NOTE, LABEL

NOT_COMPUTED = "not-computed (rates not supplied)"
_SECTIONS = ("events", "cyclelog", "header")


def match_factor(n_trucks: int, n_loaders: int, load_time: float, cycle_time: float) -> float:
    """n_trucks x load_time / (n_loaders x cycle_time), from `minephys.haulage`."""
    return float(_mp.match_factor(n_trucks, n_loaders, load_time, cycle_time))


def _first_non_finite(rows: Any, section: str, fields: tuple[str, ...]) -> InvalidTrace | None:
    if not isinstance(rows, list):
        return None
    for i, r in enumerate(rows):
        if isinstance(r, dict):
            for f in fields:
                v = r.get(f)
                if isinstance(v, float) and not math.isfinite(v):
                    return InvalidTrace(f"{f} is not finite ({v!r})", section=section, row=i)
    return None


def _validate_trace(trace: Any) -> None:
    if not isinstance(trace, dict):
        raise InvalidTrace("a trace must be a JSON object")
    for section, fields in (("events", ("t_s", "seq")), ("cyclelog", ("t_s", "payload_t"))):
        err = _first_non_finite(trace.get(section), section, fields)
        if err:
            raise err
    hdr = trace.get("header")
    if isinstance(hdr, dict):
        for k in ("horizon_s",):
            if isinstance(hdr.get(k), float) and not math.isfinite(hdr[k]):
                raise InvalidTrace(f"{k} is not finite", section="header")
        kw = hdr.get("kpi_window")
        if isinstance(kw, dict) and isinstance(kw.get("warmup_s"), float) and not math.isfinite(kw["warmup_s"]):
            raise InvalidTrace("warmup_s is not finite", section="header")
    errors = sorted(
        _validator("des-trace.schema.json").iter_errors(trace),
        key=lambda e: tuple(str(p).zfill(9) for p in e.absolute_path),
    )
    if errors:
        e = errors[0]
        path = list(e.absolute_path)
        section = path[0] if path and path[0] in _SECTIONS else "trace"
        row = path[1] if section in ("events", "cyclelog") and len(path) > 1 and isinstance(path[1], int) else None
        raise InvalidTrace(e.message[:200], section=section, row=row)
    ev = trace["events"]
    for i in range(1, len(ev)):
        if (ev[i]["t_s"], ev[i]["seq"]) <= (ev[i - 1]["t_s"], ev[i - 1]["seq"]):
            raise InvalidTrace("events must be strictly ordered by (t_s, seq)", section="events", row=i)
    if trace["header"]["kpi_window"]["warmup_s"] >= trace["header"]["horizon_s"]:
        raise InvalidTrace("the evaluation window needs warm-up < horizon", section="header")


def _wait_stats(waits_s: list[float]) -> dict[str, float]:
    if not waits_s:
        return {"mean": 0.0, "p90": 0.0}
    arr = np.asarray(waits_s, dtype=float) / 60.0
    return {"mean": float(arr.mean()), "p90": float(np.percentile(arr, 90, method="linear"))}


def _visits(arrivals: dict[int, list[tuple[float, int]]], starts: dict[int, list[tuple[float, int]]]):
    """Pair the k-th arrival of each truck with its k-th service start: (arrival, start, node)."""
    for truck, st in starts.items():
        arr = arrivals.get(truck, [])
        for k, (t_start, node) in enumerate(st):
            if k < len(arr):
                yield arr[k][0], t_start, node


def compute_kpis(
    trace: dict,
    *,
    fleet: list[dict],
    loaders: list[dict],
    free_flow_cycle_s: dict[str, float],
    cost_rates: dict | None = None,
    time_unit: str = "s",
    arrivals: list[tuple[str, float, int, int]] | None = None,
) -> dict:
    """The KPI table of a trace; see the module docstring. `time_unit` names the unit of every time of the trace and of T_c*.
    `arrivals` (kind, t, truck, node) replaces the arrival events of the trace as the source of the queue waits."""
    if time_unit not in ("s", "h"):
        raise ValueError(f"time_unit must be 's' or 'h': {time_unit!r}")
    _validate_trace(trace)
    to_s = 3600.0 if time_unit == "h" else 1.0
    h = trace["header"]
    w0, w1 = float(h["kpi_window"]["warmup_s"]), float(h["horizon_s"])
    window_s = (w1 - w0) * to_s
    window_h = window_s / 3600.0
    inside = lambda t: w0 <= t <= w1  # noqa: E731  (the window is closed at both ends)

    arr_loader: dict[int, list[tuple[float, int]]] = defaultdict(list)
    arr_dump: dict[int, list[tuple[float, int]]] = defaultdict(list)
    # arrivals come from the engine's own arrival hook when the caller has it (a traffic traversal ends without a heap event, so
    # the trace alone misses those arrivals); otherwise from the arrival events of the trace
    source = (
        list(arrivals)
        if arrivals is not None
        else [(e["kind"], e["t_s"], e["truck"], e["node"]) for e in trace["events"]]
    )
    for kind, t, tr, node in source:
        if kind == "arrive-loader":
            arr_loader[tr].append((t, node))
        elif kind == "arrive-dump":
            arr_dump[tr].append((t, node))

    load_start: dict[int, list[tuple[float, int]]] = defaultdict(list)
    dump_start: dict[int, list[tuple[float, int]]] = defaultdict(list)
    open_load: dict[int, tuple[float, int]] = {}
    last_loader: dict[int, int] = {}
    pending_payload: dict[int, float] = {}
    busy: dict[int, float] = defaultdict(float)
    t_l: list[float] = []
    tonnes: dict[int, float] = defaultdict(float)
    cycles: dict[int, int] = defaultdict(int)
    for r in trace["cyclelog"]:
        tr, ev, t, node = r["truck"], r["event"], r["t_s"], r["node"]
        if ev == "load":
            load_start[tr].append((t, node))
            open_load[tr] = (t, node)
            last_loader[tr] = node
        elif ev == "haul":
            if tr in open_load:
                t0, ld = open_load.pop(tr)
                lo, hi = max(t0, w0), min(t, w1)
                if hi > lo:
                    busy[ld] += (hi - lo) * to_s
                if inside(t0):
                    t_l.append((t - t0) * to_s)
        elif ev == "dump":
            dump_start[tr].append((t, node))
            pending_payload[tr] = r["payload_t"]
        elif ev == "return":
            payload = pending_payload.pop(tr, 0.0)
            if inside(t) and tr in last_loader:
                tonnes[last_loader[tr]] += payload
                cycles[last_loader[tr]] += 1
    for tr, (t0, ld) in open_load.items():  # a loading still running at the horizon: busy until the window ends
        lo, hi = max(t0, w0), w1
        if hi > lo:
            busy[ld] += (hi - lo) * to_s

    loader_waits: dict[int, list[float]] = defaultdict(list)
    for a, s, node in _visits(arr_loader, load_start):
        if inside(s):
            loader_waits[node].append((s - a) * to_s)
    dump_waits = [(s - a) * to_s for a, s, _ in _visits(arr_dump, dump_start) if inside(s)]

    spots = {ld["node"]: ld["n_spots"] for ld in loaders}
    n_trucks, n_loaders = len(fleet), len(loaders)
    total_t = float(sum(tonnes.values()))
    total_c = int(sum(cycles.values()))
    per_loader = []
    for ld in sorted(spots):
        per_loader.append(
            {
                "loader": ld,
                "tonnes_t": float(tonnes.get(ld, 0.0)),
                "production_tph": float(tonnes.get(ld, 0.0)) / window_h,
                "cycles": int(cycles.get(ld, 0)),
                "cycles_per_h": int(cycles.get(ld, 0)) / window_h,
                "queue_min": _wait_stats(loader_waits.get(ld, [])),
                "utilisation": busy.get(ld, 0.0) / (window_s * spots[ld]),
            }
        )
    mean_tl = float(np.mean(t_l)) if t_l else None
    mf = None
    if mean_tl is not None and mean_tl > 0.0:
        by_class: dict[str, int] = defaultdict(int)
        for t in fleet:
            by_class[t["truck_class"]] += 1
        mf = float(
            sum(
                match_factor(n, n_loaders, mean_tl, free_flow_cycle_s[cls] * to_s)
                for cls, n in sorted(by_class.items())
            )
        )
    kt = total_t / 1000.0
    if cost_rates is not None and "truck_per_h" in cost_rates and "loader_per_h" in cost_rates:
        cost: Any = (
            None
            if total_t <= 0.0
            else (n_trucks * cost_rates["truck_per_h"] + n_loaders * cost_rates["loader_per_h"]) * window_h / total_t
        )
    else:
        cost = NOT_COMPUTED
    all_waits = [w for ws in loader_waits.values() for w in ws]
    return {
        "label": LABEL,
        "bias_note": BIAS_NOTE,
        "window": {"start": w0, "end": w1, "hours": window_h},
        "fleet": {
            "tonnes_t": total_t,
            "production_tph": total_t / window_h,
            "cycles": total_c,
            "cycles_per_h": total_c / window_h,
            "queue_loader_min": _wait_stats(all_waits),
            "queue_dump_min": _wait_stats(dump_waits),
            "loader_utilisation": float(sum(busy.values())) / (window_s * sum(spots.values())),
            "match_factor": mf,
            "truck_h_per_kt": (n_trucks * window_h / kt) if kt > 0.0 else None,
            "loader_h_per_kt": (n_loaders * window_h / kt) if kt > 0.0 else None,
            "cost_per_t": cost,
        },
        "loaders": per_loader,
    }
