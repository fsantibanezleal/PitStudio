"""Verification and card of the generated GNS reference dataset (spec 011, FR-011-03, FR-011-10, FR-011-14).

Every rule is recomputed from the files on disk, not trusted from the generator's state: schema and Zarr digest of every
rollout, 100 geometries with 3 seeds and the 70 / 10 / 20 split by geometry, pile at least 30 d, rest on the last
frames,
radius-graph overflow under 1 percent at rest, the test geometries inside the training envelope and at least 0.05 from
every training geometry under the contract metric, every contract parameter inside the declared envelope, and the repose
angle per family against the 3-D DEM target. Writes `index.json` and `DATASET_CARD.md` beside the data.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from . import generate, space
from .space import FAMILIES, D

TARGET_DEG, TOL_DEG = 27.2, 1.5
REAL_RANGE_DEG = (25.0, 35.0)  # the real granular range: a family outside it is not trained on (gns-walls decision 2)
OVERFLOW_MAX = 0.01
EXPECTED = {fam: sum(space.SPLIT_COUNTS[s][fam] for s in space.SPLIT_COUNTS) for fam in FAMILIES}


def _reference(family: str, geometry: dict) -> dict:
    return {
        "column-collapse": {"column_width_m": geometry.get("column_width_m")},
        "pile-formation": {"pour_point_x_m": geometry.get("pour_point_x_m")},
        "dump-over-crest": {"crest_x_m": geometry.get("crest_x_m")},
    }[family]


def check_rollout(root: Path, meta: dict, params: dict) -> dict[str, Any]:
    """The per-rollout checks of one meta file; returns the row (values and a `problems` list)."""
    import zarr

    from pitstudio.granular import observables as obs
    from pitstudio.granular.graph import build_radius_graph
    from pitstudio.granular.loader import validate_rollout_metadata

    from . import measure

    problems: list[str] = []
    family = meta["family"]
    try:
        generate.validate_meta(meta)
        validate_rollout_metadata(meta)
    except Exception as exc:
        problems.append(f"schema: {exc}")
    store = root / meta["store"]["path"]
    if not store.exists():
        return {"id": store.stem, "family": family, "problems": [*problems, "payload missing"]}
    if generate.store_digest(store) != meta["store"]["sha256"]:
        return {
            "id": store.stem,
            "family": family,
            "problems": [*problems, "digest mismatch"],
        }  # no read of a corrupt payload
    g = zarr.open_group(str(store), mode="r")
    pos_arr = g["positions"]
    n_frames = pos_arr.shape[0]
    tail = np.asarray(pos_arr[max(0, n_frames - space.REST_FRAMES - 1) :], dtype=np.float64)
    types = np.asarray(g["type_index"][:])
    is_boundary = types == 1
    n_boundary = int(is_boundary.sum())
    if family != "column-collapse" and n_boundary == 0:
        problems.append("boundary particles missing: the funnel of a pile or dump is not in the rollout")
    if n_boundary:
        start = int(np.flatnonzero(is_boundary)[0])
        if not is_boundary[start:].all():
            problems.append("boundary particles are not stored after the grains")
        every = np.asarray(pos_arr[:, start:, :], dtype=np.float64)  # (T, Nb, 2): every frame of the solids
        first = every[0]
        if not (every == first[None]).all():
            problems.append("boundary particles move between frames (the generator's solids are static)")
        x0, z0, x1, z1 = meta["bounds_m"]
        if (first[:, 0] < x0).any() or (first[:, 0] > x1).any() or (first[:, 1] < z0).any() or (first[:, 1] > z1).any():
            problems.append("boundary particles outside the bounds of the rollout")
    rad_all = np.asarray(g["radius_m"][:], dtype=np.float64)
    fin_all = tail[-1]
    grains = ~is_boundary
    rad = rad_all[grains]
    fin = fin_all[grains]  # every measurement below reads grains only; the graph below reads every node
    dt = meta["frame_interval_s"]
    speed = float((np.linalg.norm(np.diff(tail[:, grains], axis=0), axis=2) / dt).max())
    thr = space.REST_FRAC * math.sqrt(space.G * D)
    if not speed <= thr * 1.05:
        problems.append(f"not at rest: {speed:.4f} m/s over the last frames (threshold {thr:.4f})")
    z_o = None
    if family == "pile-formation":
        z_o = params["z_o_D"] * D
    elif family == "dump-over-crest":
        z_o = (params["h_c_D"] + params["z_o_D"]) * D
    low = np.ones(len(fin), dtype=bool) if z_o is None else fin[:, 1] < z_o - measure.ORIFICE_MARGIN_D * D
    heap = fin[low]
    top = float((fin[low, 1] + rad[low]).max() / D) if low.any() else 0.0
    if top < space.MIN_HEIGHT_D:
        problems.append(f"pile {top:.1f} d below the 30 d floor")
    graph = build_radius_graph(fin_all.astype(np.float32), meta["connectivity_radius_m"])
    overflow = float(graph.overflow_count) / len(fin_all)  # counted with the boundary particles
    if overflow >= OVERFLOW_MAX:
        problems.append(f"radius-graph overflow {overflow:.4f} at rest")
    left_in_feed = float((~low).mean())
    try:
        o = obs.observables(heap, d=D, family=family, geometry=_reference(family, meta["geometry"]))
        repose, run_out = float(o["repose_deg"]), float(o["run_out_m"])
    except ValueError as exc:
        problems.append(f"extractor: {exc}")
        repose = run_out = float("nan")
    return {
        "id": meta["geometry_id"] + "-s" + str(meta["packing_seed"]),
        "geometry_id": meta["geometry_id"],
        "family": family,
        "repose_deg": repose,
        "run_out_m": run_out,
        "pile_height_d": top,
        "overflow_fraction": overflow,
        "rest_speed_m_per_s": speed,
        "left_in_feed_fraction": left_in_feed,
        "frames": int(n_frames),
        "particles": len(fin_all),
        "boundary_particles": n_boundary,
        "problems": problems,
    }


def verify(out: Path) -> dict[str, Any]:
    """Run every check; the report has `ok` (no problem anywhere), the rows and the per-family summary."""
    out = Path(out)
    st = generate.load_state(out)
    if st is None:
        raise SystemExit(f"no _state.json in {out}")
    problems: list[str] = []
    metas, rows = {}, []
    slots = {s["id"]: s for s in st["slots"]}
    for f in sorted((out / "meta").glob("*.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        metas[f.stem] = m
    by_geom: dict[str, list[dict]] = {}
    for m in metas.values():
        by_geom.setdefault(m["geometry_id"], []).append(m)
    if len(by_geom) != 100:
        problems.append(f"{len(by_geom)} geometries on disk, 100 required")
    for gid, ms in sorted(by_geom.items()):
        slot = slots.get(gid)
        if slot is None:
            problems.append(f"{gid}: not in the state")
            continue
        if len(ms) != space.SEEDS_PER_GEOMETRY:
            problems.append(f"{gid}: {len(ms)} seeds, {space.SEEDS_PER_GEOMETRY} required")
        if len({json.dumps(m["geometry"], sort_keys=True) for m in ms}) != 1:
            problems.append(f"{gid}: the seeds do not share one geometry record")
        for m in ms:
            row = check_rollout(out, m, slot["params"])
            row["split"] = slot["split"]
            rows.append(row)
            problems += [f"{row['id']}: {p}" for p in row["problems"]]
    counts = {fam: len({r["geometry_id"] for r in rows if r["family"] == fam}) for fam in FAMILIES}
    if counts != EXPECTED:
        problems.append(f"geometries per family {counts}, expected {EXPECTED}")
    split_counts = {s: len({r["geometry_id"] for r in rows if r["split"] == s}) for s in ("train", "val", "test")}
    if split_counts != {"train": 70, "val": 10, "test": 20}:
        problems.append(f"split by geometry {split_counts}, expected 70 / 10 / 20")
    # contract metric: envelope of the declared ranges, test inside the training envelope and >= 0.05 from every
    # training geometry
    record = {gid: ms[0]["geometry"] for gid, ms in by_geom.items()}
    fam_of = {gid: ms[0]["family"] for gid, ms in by_geom.items()}
    envelope: dict[str, dict[str, list[float]]] = {}
    for fam in FAMILIES:
        for key, lo, hi in space.CONTRACT_RANGES[fam]:
            vals = [record[g][key] for g in record if fam_of[g] == fam]
            envelope.setdefault(fam, {})[key] = [min(vals), max(vals)] if vals else [math.nan, math.nan]
            if vals and (min(vals) < lo - 1e-9 or max(vals) > hi + 1e-9):
                problems.append(
                    f"{fam}: {key} spans {min(vals):.4g} to {max(vals):.4g}, outside the declared range {lo} to {hi}"
                )
    test_rows = []
    for gid, slot in slots.items():
        if slot["split"] != "test" or gid not in record:
            continue
        fam = slot["family"]
        train = [record[g] for g in record if slots[g]["split"] == "train" and fam_of[g] == fam]
        ok, dist = space.split_rule_ok(fam, record[gid], train)
        test_rows.append({"geometry_id": gid, "family": fam, "distance": dist, "ok": ok})
        if not ok:
            problems.append(f"{gid}: test geometry fails the envelope or the 0.05 distance rule (nearest {dist:.4f})")
    summary: dict[str, Any] = {}
    for fam in FAMILIES:
        v = [r["repose_deg"] for r in rows if r["family"] == fam and math.isfinite(r["repose_deg"])]
        summary[fam] = {
            "n": len(v),
            "repose_mean_deg": float(np.mean(v)) if v else None,
            "repose_sd_deg": float(np.std(v, ddof=1)) if len(v) > 1 else None,
            "repose_min_deg": float(min(v)) if v else None,
            "repose_max_deg": float(max(v)) if v else None,
            "within_target": bool(v) and abs(float(np.mean(v)) - TARGET_DEG) <= TOL_DEG,
            "pile_height_d_min": float(min(r["pile_height_d"] for r in rows if r["family"] == fam)) if v else None,
            "max_left_in_feed_fraction": float(max(r["left_in_feed_fraction"] for r in rows if r["family"] == fam))
            if v
            else None,
            "boundary_particles_min": min(r["boundary_particles"] for r in rows if r["family"] == fam) if v else None,
            "max_overflow_fraction": float(max(r["overflow_fraction"] for r in rows if r["family"] == fam))
            if v
            else None,
        }
    problems += range_problems(summary)
    report = {
        "ok": not problems,
        "problems": problems,
        "geometries": counts,
        "split": split_counts,
        "target_deg": TARGET_DEG,
        "tol_deg": TOL_DEG,
        "family": summary,
        "envelope": envelope,
        "test_geometries": test_rows,
        "rows": rows,
        "contact": st.get("contact"),
        "solver_version": st.get("solver_version"),
        "gpu_s_total": st.get("gpu_s_total"),
        "generator_files_sha256": st.get("generator_files_sha256"),
    }
    (out / "index.json").write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")
    (out / "DATASET_CARD.md").write_text(card(report), encoding="utf-8")
    return report


def range_problems(summary: dict[str, Any]) -> list[str]:
    """One problem per family whose mean repose is missing or outside the real granular range."""
    lo, hi = REAL_RANGE_DEG
    out = []
    for fam, s in summary.items():
        mean = s.get("repose_mean_deg")
        if mean is None:
            out.append(f"{fam}: no repose angle could be measured")
        elif not lo <= mean <= hi:
            out.append(f"{fam}: mean repose {mean:.1f} degrees is outside the real granular range {lo:g} to {hi:g}")
    return out


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f}"


def card(r: dict[str, Any]) -> str:
    c = r["contact"] or {}
    state = "all checks pass" if r["ok"] else "PROBLEMS FOUND"
    lines = [
        "# GNS reference rollouts (planar DEM)",
        "",
        "Producing tool: `pitstudio_studio.physics.planar` (`generate`, `verify`), Warp DEM of spec 005, "
        f"solver `{r['solver_version']}`. Planar monolayer: spheres held in the x-z plane, d = 0.01 m, "
        "size spread +-20 percent.",
        f"Contact law: sliding friction {c.get('friction_static')}, rolling resistance {c.get('friction_rolling')} "
        "(a planar effective value, not a material property; spec 005 slot card otherwise). "
        "Label: calibrated synthetic, not validated against real data.",
        "",
        f"Geometries: {r['geometries']}; split by geometry {r['split']}; 3 packing seeds each. Verified: {state}.",
        "",
        f"## Repose per family (target {r['target_deg']} +- {r['tol_deg']} degrees, "
        "3-D DEM of the same material, job 21)",
        "",
        "| family | rollouts | mean | sd | min | max | within target | smallest pile (d) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for fam, s in r["family"].items():
        within = "yes" if s["within_target"] else "no"
        lines.append(
            f"| {fam} | {s['n']} | {_fmt(s['repose_mean_deg'])} | {_fmt(s['repose_sd_deg'])} | "
            f"{_fmt(s['repose_min_deg'])} | {_fmt(s['repose_max_deg'])} | {within} | {_fmt(s['pile_height_d_min'])} |"
        )
    lines += ["", "## Design envelope recorded by the dataset", ""]
    for fam, params in r["envelope"].items():
        lines.append(f"- {fam}: " + ", ".join(f"{k} {lo:.4g} to {hi:.4g}" for k, (lo, hi) in params.items()))
    lines += [
        "",
        "Pile and dump are built by a quasi-static funnel-hopper feed; the recorded rate is the measured discharge "
        "rate. The funnel spheres (and, for a dump, the platform and crest face) are recorded as static boundary "
        "particles (type 1, after the grains, the same position in every frame; the GNS sees them and does not "
        "predict them, and every observable reads the grains only). Hopper leftovers on the funnel plates are "
        "reported per family in `index.json` (`max_left_in_feed_fraction`).",
        "",
    ]
    if r["problems"]:
        lines += ["## Problems", "", *[f"- {p}" for p in r["problems"][:50]]]
    return "\n".join(lines) + "\n"
