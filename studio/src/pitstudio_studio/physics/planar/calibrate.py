"""Calibration of the planar reference data against the 3-D DEM repose (spec 011, FR-011-03, FR-011-05).

Target: the 3-D DEM heap of the same material, 27.2 degrees at N = 20,000 over 5 seeds (gns-v2 job 21), accepted within
1.5 degrees. Two commands, both resumable (a JSON checkpoint after every cell, a rerun skips finished cells):

- `collapse-repro`: the gns-v2 calibration cell 12 (column collapse, mu_r 1.0, mu_s 0.8) re-run from this package, to
  prove the move from the scratch scripts (gns-v2 measured 26.9 +- 2.3 degrees over the same four seeds);
- `feed-sweep`: for each contact cell the column collapse and the quasi-static hopper feed of the pile and the dump at
  several orifice widths and seeds, each measured with the repo extractor and an independent fit.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from . import measure, space
from .space import D, SimConfig

TARGET_DEG, TOL_DEG = 27.2, 1.5
COLLAPSE_TASK = {"a": 1.5, "L0_D": 33.0, "n": int(1.5 * 33 * 33 / space.CELL_AREA)}
FEED_TASKS = {
    "pile-formation": {"x_p_D": 0.0, "z_o_D": 80.0, "n": space.N_FEED},
    "dump-over-crest": {"x_c_D": 0.0, "h_c_D": 16.0, "z_o_D": 70.0, "x_off_D": 14.0, "n": space.N_FEED},
}
REFERENCE_GEOMETRY = {
    "column-collapse": lambda p: {"column_width_m": p["L0_D"] * D},
    "pile-formation": lambda p: {"pour_point_x_m": 0.0},
    "dump-over-crest": lambda p: {"crest_x_m": 0.0},
}


def measure_collapse(res: dict, p: dict) -> dict[str, Any]:
    """One collapse result as a calibration row (repose of the final frame with both fits)."""
    row: dict[str, Any] = {"status": res["status"]}
    if res["status"] != "rest":
        return row
    fin = np.asarray(res["frames"][-1], dtype=np.float64)
    rep = measure.heap_repose(fin, family="column-collapse", geometry=REFERENCE_GEOMETRY["column-collapse"](p))
    row.update(n=res["n"], pile_height_d=res["pile_height_D"], frames=len(res["frame_times"]), rest_time_s=float(res["frame_times"][-1]), wall_s=res["wall_s"])
    if rep:
        row.update(rep)
    return row


def measure_feed(family: str, res: dict, p: dict) -> dict[str, Any]:
    """One feed result as a calibration row; a jammed or partly discharged feed keeps its status and discharged fraction."""
    row: dict[str, Any] = {"status": res["status"], "w_o_D": p["w_o_D"], "discharged_fraction": res.get("discharged_fraction"), "wall_s": res["wall_s"]}
    if res["status"] != "rest":
        return row
    fin = np.asarray(res["frames"][-1], dtype=np.float64)
    rep = measure.heap_repose(fin, family=family, geometry=REFERENCE_GEOMETRY[family](p), z_orifice=res["z_orifice_m"])
    row.update(rate=res["rate"], pile_height_d=res["pile_height_D"], frames=len(res["frame_times"]), rest_time_s=float(res["frame_times"][-1]))
    if rep:
        row.update(rep)
    return row


def summarise(rows: Sequence[dict]) -> dict[str, Any]:
    good = [r["repose_deg"] for r in rows if r.get("repose_deg") is not None]
    return {
        "n_ok": len(good),
        "n": len(rows),
        "repose_mean_deg": float(np.mean(good)) if good else None,
        "repose_sd_deg": float(np.std(good, ddof=1)) if len(good) > 1 else None,
    }


def in_band(mean_deg: float | None) -> bool:
    return mean_deg is not None and abs(mean_deg - TARGET_DEG) <= TOL_DEG


def _load(path: Path, empty: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty


def _save(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, default=float), encoding="utf-8")
    os.replace(tmp, path)


def collapse_repro(out: Path, pacer: Any, *, mu_r: float = 1.0, mu_s: float = 0.8, seeds: int = 4, reference: Path | None = None, device: str = "cuda:0") -> dict:
    """Gns-v2 cell 12 from this package: column collapse a = 1.5, L0 = 33 d, seeds 7 ... 10 (geom seed 99)."""
    from . import engine

    cfg = SimConfig(mu_r, mu_s)
    tasks = [{"p": COLLAPSE_TASK, "seed": 7 + k, "geom_seed": 99} for k in range(seeds)]
    t0 = time.perf_counter()
    rows = [measure_collapse(r, COLLAPSE_TASK) for r in engine.simulate_collapse(tasks, pacer, cfg, device)]
    rec = {"cell": [mu_r, mu_s, cfg.poly], "family": "column-collapse", "rollouts": rows, **summarise(rows), "gpu_s": time.perf_counter() - t0, "target_deg": TARGET_DEG, "tol_deg": TOL_DEG}
    if reference and Path(reference).exists():  # the gns-v2 table: cell 12, column collapse, 4 seeds
        ref = json.loads(Path(reference).read_text(encoding="utf-8"))
        old = next(c for c in ref["cells"] if c["cell"] == 12)["families"]["column-collapse"]
        rec["gns_v2_cell12"] = {"repose_mean_deg": old["repose_mean_deg"], "repose_sd_deg": old["repose_sd_deg"], "per_seed": [r.get("repose_deg") for r in old["rollouts"]]}
        if rec["repose_mean_deg"] is not None:
            rec["difference_to_gns_v2_deg"] = rec["repose_mean_deg"] - old["repose_mean_deg"]
    _save(out / "collapse-repro.json", rec)
    return rec


def feed_sweep(
    out: Path, pacer: Any, cells: Sequence[tuple[float, float]], widths: Sequence[float], *, seeds: int = 2, collapse_seeds: int = 4, device: str = "cuda:0", log=print
) -> dict:
    """Per contact cell: the column collapse and both feeds at every width. Checkpoint after every cell."""
    from . import engine

    path = out / "feed-sweep.json"
    res = _load(path, {"target_deg": TARGET_DEG, "tol_deg": TOL_DEG, "widths_d": list(widths), "cells": []})
    done = {tuple(c["cell"]) for c in res["cells"]}
    for cell in cells:
        if tuple(cell) in done:
            continue
        cfg = SimConfig(*cell)
        t0 = time.perf_counter()
        rec: dict[str, Any] = {"cell": list(cell), "families": {}}
        tasks = [{"p": COLLAPSE_TASK, "seed": 7 + k, "geom_seed": 99} for k in range(collapse_seeds)]
        rows = [measure_collapse(r, COLLAPSE_TASK) for r in engine.simulate_collapse(tasks, pacer, cfg, device)]
        rec["families"]["column-collapse"] = {"rollouts": rows, **summarise(rows)}
        log(f"[sweep] cell {cell} column-collapse: {rec['families']['column-collapse']}")
        for family in ("pile-formation", "dump-over-crest"):
            ps = [{**FEED_TASKS[family], "w_o_D": float(w)} for w in widths for _ in range(seeds)]
            tasks = [{"p": p, "seed": 7 + (i % seeds), "geom_seed": 900 + i} for i, p in enumerate(ps)]
            rows = [measure_feed(family, r, p) for r, p in zip(engine.simulate_feed(family, tasks, pacer, cfg, device), ps)]
            by_w = {}
            for w in widths:
                sel = [r for r in rows if r["w_o_D"] == float(w)]
                by_w[str(w)] = {**summarise(sel), "statuses": [r["status"] for r in sel], "rate_mean": float(np.mean([r["rate"] for r in sel if r.get("rate") is not None and math.isfinite(r["rate"])] or [float("nan")]))}
            rec["families"][family] = {"rollouts": rows, "by_width": by_w, **summarise(rows)}
            log(f"[sweep] cell {cell} {family}: {json.dumps(by_w)}")
        rec["gpu_s"] = time.perf_counter() - t0
        res["cells"].append(rec)
        res["gpu_s_total"] = res.get("gpu_s_total", 0.0) + rec["gpu_s"]
        _save(path, res)
        log(f"[sweep] cell {cell} saved ({rec['gpu_s']:.0f} s)")
    return res
