"""Generator of the GNS reference rollouts (spec 011, FR-011-03, DC-011-01): 100 geometries x 3 packing seeds, planar
DEM.

The plan lives in `<out>/_state.json` (atomic writes, resumable: a killed run continues from the last finished batch).
Geometries are drawn deterministically from (slot, attempt); a geometry is replaced when a feed jams, a pile is lower
than
30 d, a rest is not reached, or (test set) its MEASURED contract parameters are inside the training envelope but closer
than 0.05 to a training geometry. Test geometries are drawn only after every training geometry is final.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import itertools
import json
import math
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from . import measure, space
from .space import FAMILIES, MIN_HEIGHT_D, D, SimConfig

REPO = Path(__file__).resolve().parents[5]
SCHEMA = REPO / "specs" / "011-surrogates" / "contracts" / "granular-rollout.schema.json"
PACKAGE = Path(__file__).resolve().parent
RATE_REF_FALLBACK = 0.08  # m^2/s, used only when no training geometry is final yet


# ----------------------------------------------------------------------------------------------- state
def state_path(out: Path) -> Path:
    return Path(out) / "_state.json"


def load_state(out: Path) -> dict | None:
    f = state_path(out)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def save_state(out: Path, st: dict) -> None:
    tmp = Path(out) / "_state.json.tmp"
    tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
    os.replace(tmp, state_path(out))


def new_state(cfg: SimConfig) -> dict:
    return {
        "master_seed": space.MASTER_SEED,
        "d_m": D,
        "geometry": "planar monolayer (y held at 0)",
        "contact": {"friction_rolling": cfg.mu_r, "friction_static": cfg.mu_s, "poly": cfg.poly},
        "slots": space.split_plan(),
        "wall_s": {},
        "gpu_s_total": 0.0,
        "runs": [],
    }


def generator_digest() -> dict[str, str]:
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(PACKAGE.glob("*.py"))}


def solver_version() -> str:
    import warp as wp

    sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return f"pitstudio-dem-{sha[:7]}+warp{wp.__version__}"


# ----------------------------------------------------------------------------------------------- draws
def family_slots(st: dict, family: str) -> list[dict]:
    return [s for s in st["slots"] if s["family"] == family]


def draw_slot(st: dict, slot: dict) -> None:
    """Deterministic draw for (slot, attempt); test geometries stay inside the training envelope, far from it under
    the contract metric."""
    fam = slot["family"]
    if slot["split"] != "test":
        rng = np.random.default_rng([space.MASTER_SEED, slot["idx"], slot["attempt"]])
        slot["params"] = space.draw_geometry(fam, rng)
        return
    train = [s for s in family_slots(st, fam) if s["split"] == "train" and s["done"]]
    env = space.envelope_of(fam, [s["params"] for s in train])
    if fam == "column-collapse":
        recs = [space.geometry_record(fam, s["params"]) for s in train]
        tv = np.array([space.contract_vec(fam, r) for r in recs])
        lo, hi = tv.min(axis=0), tv.max(axis=0)
        taken = [
            space.contract_vec(fam, space.geometry_record(fam, s["params"]))
            for s in family_slots(st, fam)
            if s["split"] == "test" and s["params"] and s is not slot
        ]
        for cand in range(20000):
            rng = np.random.default_rng([space.MASTER_SEED, 9000 + slot["idx"], slot["attempt"], cand])
            p = space.draw_geometry(fam, rng, env)
            v = space.contract_vec(fam, space.geometry_record(fam, p))
            if ((v < lo) | (v > hi)).any():
                continue
            if float(np.linalg.norm(tv - v, axis=1).min()) >= space.MIN_DISTANCE and all(
                float(np.linalg.norm(t - v)) > 1e-9 for t in taken
            ):
                slot["params"] = p
                return
        raise RuntimeError(f"no test geometry found for {slot['id']}")
    # feed families: the rate is measured, so the draw is the candidate farthest (contract metric) from the training
    # geometries and the other test geometries at the mean training rate; the measured rate decides afterwards.
    w_lo, w_hi = env["w_o_D"]
    env = dict(
        env, w_o_D=(w_lo + 0.1 * (w_hi - w_lo), w_hi - 0.1 * (w_hi - w_lo))
    )  # keep the 3-seed mean rate inside the training range
    rate_ref = (
        float(np.mean([s["record"][space.CONTRACT_RANGES[fam][1][0]] for s in train])) if train else RATE_REF_FALLBACK
    )
    others = [s["record"] for s in train] + [
        space.geometry_record(fam, s["params"], rate_ref)
        for s in family_slots(st, fam)
        if s["split"] == "test" and s["params"] and s is not slot
    ]
    ov = np.array([space.contract_vec(fam, r) for r in others])
    rng = np.random.default_rng([space.MASTER_SEED, 9000 + slot["idx"], slot["attempt"]])
    best, best_d = None, -1.0
    for _ in range(400):
        cand = space.draw_geometry(fam, rng, env)
        dist = float(
            np.linalg.norm(ov - space.contract_vec(fam, space.geometry_record(fam, cand, rate_ref)), axis=1).min()
        )
        if dist > best_d:
            best, best_d = cand, dist
    slot["params"] = best


def make_batch(st: dict, family: str, splits: Sequence[str], n_geometries: int) -> list[tuple[dict, dict]]:
    """(slot, task) pairs of the next `n_geometries` unfinished slots of `family` in `splits`."""
    pairs: list[tuple[dict, dict]] = []
    taken = 0
    for slot in family_slots(st, family):
        if slot["done"] or slot["split"] not in splits:
            continue
        if slot["split"] == "test" and not all(s["done"] for s in family_slots(st, family) if s["split"] == "train"):
            continue
        if slot["params"] is None:
            draw_slot(st, slot)
        used = {s["seed"] for s in slot["seeds"]} | {s["seed"] for s in slot["failed_seeds"]}
        seed = 1000 * slot["idx"] + 100 * slot["attempt"]
        for _ in range(space.SEEDS_PER_GEOMETRY - len(slot["seeds"])):
            while seed in used:
                seed += 1
            used.add(seed)
            pairs.append((slot, {"p": slot["params"], "seed": seed, "geom_seed": slot["idx"]}))
        taken += 1
        if taken >= n_geometries:
            break
    return pairs


# ----------------------------------------------------------------------------------------------- payload and metadata
def contain_bounds(bounds: Sequence[float], boundary: np.ndarray | None) -> list[float]:
    """`bounds` = (x0, z0, x1, z1) widened to contain every stored boundary particle.

    The payload stores float32 and the domain is float64: a platform row that starts exactly on the left wall of the box
    rounds to a float32 1e-8 to 1e-7 m outside it half of the time (48 of 84 dump rollouts of gns-rollouts-v2). The box
    of a rollout is the box of what it stores.
    """
    x0, z0, x1, z1 = (float(b) for b in bounds)
    if boundary is None or len(boundary) == 0:
        return [x0, z0, x1, z1]
    b = np.asarray(boundary, dtype=np.float64)
    return [
        min(x0, float(b[:, 0].min())),
        min(z0, float(b[:, 1].min())),
        max(x1, float(b[:, 0].max())),
        max(z1, float(b[:, 1].max())),
    ]


def store_digest(path: Path) -> str:
    lines = [
        f"{f.relative_to(path).as_posix()} {hashlib.sha256(f.read_bytes()).hexdigest()}\n"
        for f in sorted(p for p in path.rglob("*") if p.is_file())
    ]
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def write_rollout(
    root: Path,
    rid: str,
    family: str,
    gid: str,
    p: dict,
    record: dict,
    seed: int,
    res: dict,
    cfg: SimConfig,
    version: str,
) -> dict:
    """Write payload/<rid>.zarr and return the DC-011-01 metadata (not yet written to meta/)."""
    import zarr

    rel = f"payload/{rid}.zarr"
    store = Path(root) / rel
    if store.exists():
        shutil.rmtree(store)
    store.parent.mkdir(parents=True, exist_ok=True)
    grains = res["frames"]
    boundary = res.get("boundary")
    n_boundary = 0 if boundary is None else len(boundary)
    names = ["grain", "boundary"] if n_boundary else ["grain"]
    # grains first, then the static solids (funnel, platform): type 0 and type 1, the boundary repeated in every frame
    frames = (
        np.concatenate([grains, np.broadcast_to(boundary[None], (len(grains), n_boundary, 2))], axis=1)
        if n_boundary
        else grains
    )
    types = np.concatenate([np.zeros(grains.shape[1], dtype=np.uint8), np.ones(n_boundary, dtype=np.uint8)])
    radii = np.concatenate([res["radii"], np.full(n_boundary, 0.5 * D, dtype=np.float32)])
    g = zarr.open_group(str(store), mode="w")
    g.create_array("positions", data=frames, chunks=(min(32, len(frames)), frames.shape[1], 2))
    g.create_array("radius_m", data=radii)
    g.create_array("type_index", data=types)
    g.create_array("frame_times_s", data=res["frame_times"])
    g.attrs.update(
        {
            "axes": "positions[t, i] = (x, z) in metres, z vertical; planar monolayer (y held at 0); "
            "grains first, then the static boundary particles (type 1, same position in every frame)",
            "particle_types": names,
            "rollout_id": rid,
        }
    )
    return {
        "$schema": "https://fsantibanezleal.github.io/PitStudio/contracts/granular-rollout.schema.json",
        "family": family,
        "geometry_id": gid,
        "geometry": record,
        "packing_seed": int(seed),
        "solver": "warp-dem",
        "solver_version": version,
        "dimensions": 2,
        "particle_diameter_m": D,
        "connectivity_radius_m": 2.5 * D,
        "frame_interval_s": cfg.frame_dt,
        "bounds_m": contain_bounds(res["bounds"], boundary),
        "frame_times_s": [float(t) for t in res["frame_times"]],
        "particle_count": int(frames.shape[1]),
        "particle_types": names,
        "material": cfg.record(),
        "rest_time_s": float(res["frame_times"][-1]),
        "store": {"format": "zarr", "path": rel, "sha256": store_digest(store)},
        "label": space.LABEL,
    }


def validate_meta(meta: dict) -> None:
    import jsonschema

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(meta)
    t = meta["frame_times_s"]
    if not all(b > a for a, b in itertools.pairwise(t)):
        raise ValueError("frame times are not strictly increasing")


# ----------------------------------------------------------------------------------------------- processing of results
def _entry(rid: str, seed: int, res: dict) -> dict:
    keys = (
        "pile_height_D",
        "final_vmax",
        "wall_s",
        "x99_m",
        "x01_m",
        "min_z_over_r",
        "mass_ok",
        "max_contacts",
        "y_abs_max_m",
        "rate",
        "discharged_fraction",
        "h0_real_D",
    )
    e = {
        "seed": seed,
        "id": rid,
        "particles": res["n"],
        "boundary_particles": int(res.get("n_boundary", 0)),
        "frames": len(res["frame_times"]),
        "rest_time_s": float(res["frame_times"][-1]),
    }
    e.update({k: res[k] for k in keys if k in res and res[k] is not None})
    return e


def replace_geometry(out: Path, slot: dict, reason: str, detail: dict | None = None) -> None:
    slot["failed_geometries"].append(
        {"attempt": slot["attempt"], "params": slot["params"], "reason": reason, **(detail or {})}
    )
    for s in slot["seeds"]:
        shutil.rmtree(Path(out) / "payload" / f"{s['id']}.zarr", ignore_errors=True)
        (Path(out) / "meta" / f"{s['id']}.json").unlink(missing_ok=True)
    slot.update(seeds=[], failed_seeds=[], attempt=slot["attempt"] + 1, params=None, record=None)
    if slot["attempt"] >= space.MAX_GEOM_ATTEMPTS:
        raise RuntimeError(f"{slot['id']}: {space.MAX_GEOM_ATTEMPTS} geometry attempts failed")


def _commit_meta(out: Path, rid: str, meta: dict) -> None:
    validate_meta(meta)
    tmp = Path(out) / "meta" / f"{rid}.json.tmp"
    tmp.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    os.replace(tmp, Path(out) / "meta" / f"{rid}.json")


def process_collapse(
    out: Path,
    st: dict,
    slot: dict,
    rs: list[tuple[dict, dict]],
    cfg: SimConfig,
    version: str,
    log: Callable[[str], None],
) -> None:
    for task, res in rs:
        seed, rid = task["seed"], f"{slot['id']}-s{task['seed']}"
        if res["status"] != "rest":
            slot["failed_seeds"].append({"seed": seed, "reason": res["status"], "wall_s": res["wall_s"]})
            log(f"{rid} column-collapse FAILED({res['status']})")
            if len(slot["failed_seeds"]) >= space.MAX_SEED_ATTEMPTS:
                replace_geometry(out, slot, "too-many-no-rest-seeds")
                return
            continue
        if res["pile_height_D"] < MIN_HEIGHT_D:
            log(f"{rid} column-collapse FAILED(pile {res['pile_height_D']:.1f} d < 30 d: geometry replaced)")
            replace_geometry(out, slot, "pile-below-30d", {"pile_height_d": res["pile_height_D"], "seed": seed})
            return
        record = space.geometry_record("column-collapse", slot["params"])
        _commit_meta(
            out,
            rid,
            write_rollout(out, rid, "column-collapse", slot["id"], slot["params"], record, seed, res, cfg, version),
        )
        slot["seeds"].append(_entry(rid, seed, res))
        log(f"{rid} column-collapse particles={res['n']} frames={len(res['frame_times'])} wall={res['wall_s']:.0f}s")
    slot["record"] = space.geometry_record("column-collapse", slot["params"])
    slot["done"] = len(slot["seeds"]) >= space.SEEDS_PER_GEOMETRY


def process_feed(
    out: Path,
    st: dict,
    slot: dict,
    rs: list[tuple[dict, dict]],
    cfg: SimConfig,
    version: str,
    log: Callable[[str], None],
) -> None:
    """All seeds of a feed geometry at once: any rejected seed replaces the geometry (a jam is a property of the
    geometry)."""
    fam = slot["family"]
    bad = [
        (r["status"], round(r.get("pile_height_D", 0.0), 1), round(r.get("discharged_fraction", 0.0), 3))
        for _, r in rs
        if r["status"] != "rest" or r["pile_height_D"] < MIN_HEIGHT_D or not math.isfinite(r["rate"])
    ]
    if bad:
        log(f"{slot['id']} {fam} FAILED {bad} (geometry replaced) w_o={slot['params']['w_o_D']:.2f}")
        replace_geometry(out, slot, f"jammed / no-rest / pile < 30 d / no rate {bad}")
        return
    kept = list(slot["seeds"])  # seeds of this geometry that stay (a requeued rollout is re-simulated alone)
    rate = float(np.mean([e["rate"] for e in kept] + [r["rate"] for _, r in rs]))
    record = space.geometry_record(fam, slot["params"], rate)
    for key, lo, hi in space.CONTRACT_RANGES[fam]:
        if not lo <= record[key] <= hi:
            log(f"{slot['id']} {fam} FAILED({key} {record[key]:.4g} outside {lo} to {hi}: geometry replaced)")
            replace_geometry(out, slot, f"outside the declared envelope: {key} {record[key]:.4g}")
            return
    if slot["split"] == "test":
        train = [s["record"] for s in family_slots(st, fam) if s["split"] == "train" and s["done"]]
        ok, dist = space.split_rule_ok(fam, record, train)
        if not ok:
            log(f"{slot['id']} {fam} FAILED(test distance {dist:.3f} / envelope: geometry replaced)")
            replace_geometry(out, slot, "test-distance-or-envelope", {"distance": dist, "rate": rate})
            return
    for e in kept:  # the geometry record is shared by the seeds: the kept rollouts take the new mean rate, nothing else
        meta = json.loads((Path(out) / "meta" / f"{e['id']}.json").read_text(encoding="utf-8"))
        _commit_meta(out, e["id"], {**meta, "geometry": record})
    for task, res in rs:
        rid = f"{slot['id']}-s{task['seed']}"
        _commit_meta(
            out, rid, write_rollout(out, rid, fam, slot["id"], slot["params"], record, task["seed"], res, cfg, version)
        )
        slot["seeds"].append(_entry(rid, task["seed"], res))
    slot["record"], slot["rate"], slot["done"] = record, rate, True
    lo = min(e["pile_height_D"] for e in slot["seeds"])
    hi = max(e["pile_height_D"] for e in slot["seeds"])
    log(
        f"{slot['id']} {fam} {slot['split']} rate={rate:.5f} m2/s w_o={slot['params']['w_o_D']:.2f} d "
        f"pile={lo:.1f}-{hi:.1f} d"
    )


# ------------------------------------------------------------------------------------------- repairs of a finished set
def _grain_frames(store: Path, n: int = space.REST_FRAMES + 1) -> np.ndarray:
    """The last `n` stored frames of the grains of a rollout, (n, grains, 2) float32."""
    import zarr

    g = zarr.open_group(str(store), mode="r")
    types = np.asarray(g["type_index"][:])
    frames = g["positions"]
    return np.asarray(frames[max(0, frames.shape[0] - n) :])[:, types == 0]


def not_at_rest(out: Path, limit: float | None = None) -> list[dict]:
    """The rollouts whose stored frames still move: rest speed (`measure.rest_speed`, the verification's reading) over
    `limit`, by default the threshold with the slack of the verification. A `limit` below zero lists every rollout."""
    out = Path(out)
    limit = measure.rest_threshold() * measure.REST_SLACK if limit is None else limit
    rows = []
    for f in sorted((out / "meta").glob("*.json")):
        meta = json.loads(f.read_text(encoding="utf-8"))
        store = out / meta["store"]["path"]
        if not store.exists():
            continue  # the verification reports a missing payload
        speed = measure.rest_speed(_grain_frames(store), meta["frame_interval_s"])
        if not speed <= limit:
            rows.append({"id": f.stem, "geometry_id": meta["geometry_id"], "family": meta["family"], "speed": speed})
    return rows


def requeue_not_at_rest(out: Path, limit: float | None = None, reason: str = "not-at-rest") -> list[dict]:
    """Take the rollouts that are not at rest back to the generator (FR-011-10).

    Each one's metadata and payload move to `<out>/superseded/<reason>/` (kept, never dropped), its seed leaves the
    slot, the slot is open again and `slot["superseded"]` counts it with the old digest. `run` then simulates the
    missing seeds under the same ids; a seed that still does not come to rest is replaced by the next seed of the
    geometry (or, after too many, the geometry) by the rules the generator already has. Returns the rollouts moved; a
    set with none over the limit is not touched.
    """
    out = Path(out)
    rows = not_at_rest(out, limit)
    if not rows:
        return []
    st = load_state(out)
    if st is None:
        raise SystemExit(f"no _state.json in {out}")
    slots = {s["id"]: s for s in st["slots"]}
    dest = out / "superseded" / reason
    dest.mkdir(parents=True, exist_ok=True)
    for row in rows:
        rid, slot = row["id"], slots[row["geometry_id"]]
        meta_f = out / "meta" / f"{rid}.json"
        meta = json.loads(meta_f.read_text(encoding="utf-8"))
        n, tag = 1, rid
        while (dest / f"{tag}.json").exists():
            n += 1
            tag = f"{rid}-{n}"
        shutil.move(str(out / meta["store"]["path"]), str(dest / f"{tag}.zarr"))
        shutil.move(str(meta_f), str(dest / f"{tag}.json"))
        slot["seeds"] = [e for e in slot["seeds"] if e["id"] != rid]
        slot.setdefault("superseded", []).append(
            {
                "id": rid,
                "seed": meta["packing_seed"],
                "reason": reason,
                "rest_speed_m_per_s": row["speed"],
                "rest_time_s": meta["rest_time_s"],
                "sha256": meta["store"]["sha256"],
            }
        )
        slot["done"] = False
    save_state(out, st)
    return rows


def _boundary_of(out: Path, meta: dict) -> np.ndarray | None:
    """The stored static boundary particles of a rollout (frame 0), None for a rollout without any."""
    import zarr

    g = zarr.open_group(str(Path(out) / meta["store"]["path"]), mode="r")
    types = np.asarray(g["type_index"][:])
    if not (types == 1).any():
        return None
    return np.asarray(g["positions"][0, int(np.flatnonzero(types == 1)[0]) :, :])


def rewrite_bounds(out: Path) -> dict:
    """Repair the recorded box of every finished rollout that has boundary particles, from its static geometry.

    The static solids (funnel, platform, crest face) are rebuilt from the slot's parameters and the rollout's seeds, the
    way the generator built them, and compared with the stored particles; only when they are identical is `bounds_m`
    widened to contain them (`contain_bounds`) and the metadata rewritten. No payload is written, and the proof lists
    the digest check of every store, so the grain arrays are untouched. A rollout whose stored solids differ from its
    geometry is reported in `mismatched` and left alone.
    """
    from . import engine

    out = Path(out)
    st = load_state(out)
    if st is None:
        raise SystemExit(f"no _state.json in {out}")
    slots = {s["id"]: s for s in st["slots"]}
    cfg = SimConfig(st["contact"]["friction_rolling"], st["contact"]["friction_static"], st["contact"]["poly"])
    checked, rewritten, mismatched, proof = 0, [], [], []
    for f in sorted((out / "meta").glob("*.json")):
        meta = json.loads(f.read_text(encoding="utf-8"))
        stored = _boundary_of(out, meta)
        if stored is None:
            continue
        checked += 1
        slot = slots[meta["geometry_id"]]
        task = {"p": slot["params"], "seed": meta["packing_seed"], "geom_seed": slot["idx"]}
        (inst,) = engine.feed_instances(meta["family"], [task], cfg)
        same = bool(np.array_equal(engine.instance_boundary(meta["family"], inst), stored))
        digest = store_digest(out / meta["store"]["path"])
        proof.append(
            {
                "id": f.stem,
                "static_geometry_equals_stored": same,
                "payload_digest_matches_meta": digest == meta["store"]["sha256"],
            }
        )
        if not same:
            mismatched.append(f.stem)
            continue
        bounds = contain_bounds(meta["bounds_m"], stored)
        if bounds != [float(b) for b in meta["bounds_m"]]:
            _commit_meta(out, f.stem, {**meta, "bounds_m": bounds})
            rewritten.append(f.stem)
    return {"checked": checked, "rewritten": rewritten, "mismatched": mismatched, "proof": proof}


# ----------------------------------------------------------------------------------------------- run
@dataclasses.dataclass
class RunArgs:
    out: Path
    mu_r: float
    mu_s: float
    k_collapse: int = 16  # instances per collapse batch
    k_feed: int = 12  # instances per feed batch (a multiple of 3: whole geometries)
    phase: str = "all"  # "trainval" stops before the test geometries
    limit_batches: int = 0
    families: tuple[str, ...] = FAMILIES
    device: str = "cuda:0"


def run(
    args: RunArgs,
    *,
    session: Callable[[], tuple[Any, Any, Any]] | None = None,
    log: Callable[[str], None] | None = None,
) -> int:
    """Generate the dataset; `session` returns (guard, lock, pacer) (tests pass a stand-in). 0 on a finished or
    limited run, 4 on a guard stop."""
    from . import engine, gpujob

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta").mkdir(exist_ok=True)
    cfg = SimConfig(args.mu_r, args.mu_s)
    version = solver_version()
    logfile = out / "progress.log"

    def default_log(line: str) -> None:
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    log = log or default_log
    st = load_state(out) or new_state(cfg)
    if st["contact"] != {"friction_rolling": cfg.mu_r, "friction_static": cfg.mu_s, "poly": cfg.poly}:
        raise SystemExit(
            f"the state in {out} was generated with another contact law {st['contact']}; start a new output folder"
        )
    st.update(
        generator_files_sha256=generator_digest(),
        solver_version=version,
        dt_s=cfg.dt,
        frame_interval_s=cfg.frame_dt,
        steps_per_frame=space.STEPS_PER_FRAME,
        n_feed=space.N_FEED,
        feed_ranges=space.FEED_RANGES,
        discharged_min=engine.DISCHARGED_MIN,
    )
    save_state(out, st)
    guard, lock, pacer = (session or gpujob.start_session)()
    whea_since = getattr(guard, "since", None)
    gg = gpujob.load_guard_module() if session is None else None
    st["runs"].append(
        {
            "start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "whea_since": whea_since,
            "k_collapse": args.k_collapse,
            "k_feed": args.k_feed,
        }
    )
    t_job, n_batches, stop_reason = time.perf_counter(), 0, None
    phases = [("val",), ("train",)] + ([] if args.phase == "trainval" else [("test",)])
    try:
        for splits in phases:
            for family in args.families:
                while True:
                    k = args.k_collapse if family == "column-collapse" else args.k_feed
                    n_geom = max(1, k // space.SEEDS_PER_GEOMETRY)  # whole geometries per batch
                    pairs = make_batch(st, family, splits, n_geom)
                    if not pairs:
                        break
                    if args.limit_batches and n_batches >= args.limit_batches:
                        raise KeyboardInterrupt
                    save_state(out, st)
                    pacer.max_temp = -1
                    tb = time.perf_counter()
                    tasks = [t for _, t in pairs]
                    try:
                        results = (
                            engine.simulate_collapse(tasks, pacer, cfg, args.device)
                            if family == "column-collapse"
                            else engine.simulate_feed(family, tasks, pacer, cfg, args.device)
                        )
                    except Exception as exc:
                        if type(exc).__name__ == "GuardStop":
                            raise
                        results = [{"status": f"error:{type(exc).__name__}:{exc}", "wall_s": 0.0} for _ in pairs]
                    n_batches += 1
                    bw = sum(r["wall_s"] for r in results)
                    st["wall_s"][family] = st["wall_s"].get(family, 0.0) + bw
                    st["gpu_s_total"] += bw
                    st.setdefault("batch_log", []).append(
                        {
                            "family": family,
                            "k": len(pairs),
                            "ok": sum(r["status"] == "rest" for r in results),
                            "gpu_s": bw,
                            "real_s": time.perf_counter() - tb,
                            "maxC": pacer.max_temp,
                            "splits": list(splits),
                        }
                    )
                    ok = st["batch_log"][-1]["ok"]
                    print(
                        f"batch {n_batches} {family} k={len(pairs)} ok={ok} gpu_wall={bw:.0f}s "
                        f"real={time.perf_counter() - tb:.0f}s maxC={pacer.max_temp}",
                        flush=True,
                    )

                    for slot in {id(s): s for s, _ in pairs}.values():
                        rs = [(t, r) for (s, t), r in zip(pairs, results, strict=True) if s is slot]
                        (process_collapse if family == "column-collapse" else process_feed)(
                            out, st, slot, rs, cfg, version, log
                        )
                    save_state(out, st)
    except KeyboardInterrupt:
        stop_reason = "batch limit"
    except BaseException as exc:
        if type(exc).__name__ != "GuardStop":
            raise
        stop_reason = f"GuardStop {exc}"
        print(stop_reason, flush=True)
    finally:
        wh = gg.whea_count(whea_since) if gg is not None else None
        st["runs"][-1].update(
            end=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            whea_new=wh,
            stop=stop_reason,
            wall_s=time.perf_counter() - t_job,
            guard_pause_s=getattr(guard, "paused_s", 0.0),
            batches=n_batches,
        )
        save_state(out, st)
        with contextlib.suppress(Exception):
            lock.release()
    return 0 if stop_reason in (None, "batch limit") else 4
