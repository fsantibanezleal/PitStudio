"""Command line of the planar reference-data generator; every queue job calls this module, never a script from a temp
folder."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

from .space import FAMILIES, SimConfig


def _cells(text: str) -> list[tuple[float, float]]:
    return [(float(a), float(b)) for a, b in (c.split(":") for c in text.split(","))]


def dry_run(allow_cpu: bool) -> int:
    """The real code path without GPU work: states of every family at the extremes of the design ranges, the contact
    law,
    the extractors, the guard module, the lock plumbing and a tiny planar step on the CPU."""
    import numpy as np
    import warp as wp

    from . import engine, gpujob, measure, packing, space

    if not allow_cpu:
        assert wp.get_cuda_device_count() > 0, "no CUDA device: the real run could not start"
    rng = np.random.default_rng(3)
    cfg = SimConfig(1.0, 0.5)
    assert 0 < cfg.dt < 1e-4, cfg.dt
    for fam in FAMILIES:
        for _ in range(3):
            p = space.draw_geometry(fam, rng)
            if fam == "column-collapse":
                pos, rad = packing.column_state(p, rng)
                assert len(pos) == len(rad) > 0
            else:
                geo = engine.feed_geometry(fam, p)
                h = packing.hopper_state(p, rng, x_center=geo["x_center"], z_orifice=geo["z_orifice"])
                assert h.n_grains == space.N_FEED
                assert h.frozen.sum() == h.n_walls
                assert h.top_z < 256 * 0.025, "hopper taller than the z span of the hash grid"
    assert measure.RestJudge(0.003, discharged_min=0.9).update(1.0, 0.0, 0.1) == "run"
    gg = gpujob.load_guard_module()
    assert gg.START_MAX_C == 80
    try:
        gpujob.import_filelock()
        lock_note = "filelock importable"
    except RuntimeError as exc:
        lock_note = f"filelock missing ({exc})"
        if not allow_cpu:
            raise
    p = {"x_p_D": 0.0, "z_o_D": 15.0, "w_o_D": 9.0, "n": 30}
    geo = engine.feed_geometry("pile-formation", p)
    h = packing.hopper_state(p, rng, x_center=geo["x_center"], z_orifice=geo["z_orifice"])
    ps = engine.PlanarSim(
        h.positions,
        h.radii,
        h.frozen,
        engine.feed_walls("pile-formation", [{"X0": geo["lx0"], "X1": geo["lx1"], "geo": geo, "shift": 0.0}]),
        cfg,
        device="cpu",
    )
    ps.advance(20)
    assert abs(ps.sim.positions[:, 1]).max() == 0.0
    print(
        f"[planar] dry-run ok: 3 families, contact law dt {cfg.dt:.3e} s, {lock_note}, "
        f"CUDA devices {wp.get_cuda_device_count()}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pitstudio_studio.physics.planar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    dr = sub.add_parser("dry-run", help="real code path on the CPU, asserts CUDA exists unless --allow-cpu")
    dr.add_argument("--allow-cpu", action="store_true")
    cr = sub.add_parser("collapse-repro", help="gns-v2 calibration cell 12 from this package")
    cr.add_argument("--out", required=True)
    cr.add_argument("--reference", default="", help="the gns-v2 calib_repose.json to compare with")
    cr.add_argument("--seeds", type=int, default=4)
    fs = sub.add_parser("feed-sweep", help="collapse and both quasi-static feeds per contact cell and orifice width")
    fs.add_argument("--out", required=True)
    fs.add_argument("--cells", required=True, help="mu_r:mu_s,mu_r:mu_s,...")
    fs.add_argument("--widths", default="13,17")
    fs.add_argument("--seeds", type=int, default=2)
    g = sub.add_parser("generate", help="resumable dataset run")
    g.add_argument("--out", required=True)
    g.add_argument("--mu-r", type=float, required=True)
    g.add_argument("--mu-s", type=float, required=True)
    g.add_argument("--phase", choices=("trainval", "all"), default="all")
    g.add_argument("--k-collapse", type=int, default=16)
    g.add_argument("--k-feed", type=int, default=12)
    g.add_argument("--limit-batches", type=int, default=0)
    g.add_argument("--families", default=",".join(FAMILIES))
    v = sub.add_parser(
        "verify", help="recompute every dataset rule from the files; writes index.json and DATASET_CARD.md"
    )
    v.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "dry-run":
        return dry_run(a.allow_cpu)
    if a.cmd == "verify":
        from . import verify

        report = verify.verify(Path(a.out))
        print(
            json.dumps(
                {k: report[k] for k in ("ok", "geometries", "split", "family", "envelope")}, indent=1, default=float
            )
        )
        for p in report["problems"][:40]:
            print("PROBLEM", p)
        return 0 if report["ok"] else 1
    from . import gpujob

    guard, lock, pacer = gpujob.start_session()
    try:
        if a.cmd == "collapse-repro":
            from . import calibrate

            rec = calibrate.collapse_repro(
                Path(a.out), pacer, seeds=a.seeds, reference=Path(a.reference) if a.reference else None
            )
            print(json.dumps({k: rec[k] for k in rec if k != "rollouts"}, indent=1, default=float))
            return 0
        if a.cmd == "feed-sweep":
            from . import calibrate

            calibrate.feed_sweep(
                Path(a.out), pacer, _cells(a.cells), [float(w) for w in a.widths.split(",")], seeds=a.seeds
            )
            return 0
        from . import generate

        args = generate.RunArgs(
            out=Path(a.out),
            mu_r=a.mu_r,
            mu_s=a.mu_s,
            k_collapse=a.k_collapse,
            k_feed=a.k_feed,
            phase=a.phase,
            limit_batches=a.limit_batches,
            families=tuple(a.families.split(",")),
        )
        return generate.run(args, session=lambda: (guard, lock, pacer))
    finally:
        with contextlib.suppress(Exception):
            lock.release()


if __name__ == "__main__":
    sys.exit(main())
