"""Planar DEM batches on the Warp solver of spec 005 (spec 011, FR-011-03): true 2-D granular rollouts.

Spheres are held in the x-z plane: after every step a Warp kernel inside the CUDA graph zeroes y position and velocity
and
the x and z spin (the y spin stays, so the rolling spring of the contact law stays active); the solver is untouched.
FROZEN spheres (the funnel walls of a feed) are reset to their start position with zero velocity by the same kernel, so
they are static obstacles. K independent rollouts run side by side in ONE particle system, separated along x by GAP_D
with their own limiting walls and no interaction. On the CPU device the graph is replaced by plain stepping (tests).

`simulate_collapse` and `simulate_feed` return one result dict per task; `status` is "rest", or why the rollout was
rejected ("jammed", "no-rest", "no-settle", "underfilled", "non-finite"): a rejected rollout is never written.
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from typing import Any

import numpy as np
import warp as wp

from pitstudio_studio.physics.dem.grid import CTL_HALT, CTL_STEP
from pitstudio_studio.physics.dem.step import DemSimulation, Plane

from . import measure, packing, space
from .space import BOX_HALF, GAP_D, REST_FRAC, STEPS_PER_FRAME, D, G, SimConfig

# a feed is at rest only after this fraction of its grains has left the orifice (brief: above 0.75)
DISCHARGED_MIN = 0.9
# a feed that gained under 2 percent of discharge in this many seconds is a jam, not a slow run
STALL_S = 6.0


class NoPacer:
    """Stand-in for the guard and lock handling of a GPU job (tests on the CPU device)."""

    idle_s = 0.0
    max_temp = 0

    def check(self) -> None:
        return None


@wp.kernel
def _planar_frozen(
    pos: wp.array(dtype=wp.vec3d),
    vel: wp.array(dtype=wp.vec3),
    ang: wp.array(dtype=wp.vec3),
    frozen: wp.array(dtype=int),
    pos0: wp.array(dtype=wp.vec3d),
):
    i = wp.tid()
    if frozen[i] != 0:
        pos[i] = pos0[i]
        vel[i] = wp.vec3(0.0, 0.0, 0.0)
        ang[i] = wp.vec3(0.0, 0.0, 0.0)
        return
    p = pos[i]
    pos[i] = wp.vec3d(p[0], wp.float64(0.0), p[2])
    v = vel[i]
    vel[i] = wp.vec3(v[0], 0.0, v[2])
    a = ang[i]
    ang[i] = wp.vec3(0.0, a[1], 0.0)


class PlanarSim:
    """DemSimulation advanced in CUDA-graph batches (plain stepping on the CPU) with the planar and frozen
    constraints."""

    def __init__(
        self,
        positions,
        radii,
        frozen,
        walls: Sequence[Plane],
        cfg: SimConfig,
        *,
        velocities=None,
        angular_velocities=None,
        device: str = "cuda:0",
        k: int = space.GRAPH_K,
    ) -> None:
        sim = DemSimulation(
            positions,
            radii,
            cfg.material,
            cfg.dt,
            velocities=velocities,
            angular_velocities=angular_velocities,
            walls=tuple(walls),
            contact_capacity=16,
            device=device,
        )
        self.is_cuda = device.startswith("cuda")
        # x long, z tall: the stock 128^3 grid wraps every 1.5 m
        sim.hash_grid = wp.HashGrid(8192 if self.is_cuda else 2048, 4, 256 if self.is_cuda else 128, device=device)
        self.sim, self.k, self.device, self.graph = sim, k, device, None
        self._frozen = wp.array(np.asarray(frozen, dtype=np.int32), dtype=int, device=device)
        self._pos0 = wp.array(np.asarray(positions, dtype=np.float64).reshape(-1, 3), dtype=wp.vec3d, device=device)
        sim.step(0)
        if sim._cmds is None:
            sim._cmds = sim._record()
        if self.is_cuda:
            cmds, cell, cur = sim._cmds, 2.0 * (sim._r_max + sim._pad), sim._current
            with wp.ScopedCapture(device=device) as cap:
                for _ in range(k):
                    c = cmds[cur]
                    c[0].launch()
                    sim.hash_grid.build(sim._local, cell)
                    for x in c[1:]:
                        x.launch()
                    wp.launch(
                        _planar_frozen,
                        dim=sim.n,
                        inputs=[sim._pos, sim._vel, sim._ang, self._frozen, self._pos0],
                        device=device,
                    )
                    cur = 1 - cur
            assert cur == sim._current
            assert k % 2 == 0
            self.graph = cap.graph

    def _constrain(self) -> None:
        wp.launch(
            _planar_frozen,
            dim=self.sim.n,
            inputs=[self.sim._pos, self.sim._vel, self.sim._ang, self._frozen, self._pos0],
            device=self.device,
        )

    def advance(self, steps: int) -> None:
        if not self.is_cuda:
            for _ in range(steps):
                self.sim.step(1)
                self._constrain()
            return
        assert steps % self.k == 0
        for _ in range(steps // self.k):
            wp.capture_launch(self.graph)
        ctl = self.sim._ctl.numpy()
        self.sim.step_index = int(ctl[CTL_STEP])
        if ctl[CTL_HALT]:
            self.sim.step(1)  # raises the solver's own contact-overflow error


# ----------------------------------------------------------------------------------------------- column collapse
def collapse_walls(insts: list[dict], released: bool) -> list[Plane]:
    g2 = 0.5 * GAP_D * D
    walls = [Plane(point=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0))]
    for it in insts:
        p, xl, xr = it["p"], it["X0"], it["X1"]
        right = xr if released else p["L0_D"] * D + it["shift"]
        walls.append(Plane((xl, 0.0, 0.0), (1.0, 0.0, 0.0), tangent_range=(0, xl - g2, math.inf)))
        walls.append(Plane((right, 0.0, 0.0), (-1.0, 0.0, 0.0), tangent_range=(0, -math.inf, right + g2)))
    return walls


def simulate_collapse(
    tasks: list[dict],
    pacer: Any,
    cfg: SimConfig,
    device: str = "cuda:0",
    *,
    t_cap: float | None = None,
    settle_cap: float = 4.0,
) -> list[dict]:
    """Column collapses: settle each packing against its retaining wall (not recorded), trim to a L0, release,
    record to rest."""
    t0 = time.perf_counter()
    idle0 = pacer.idle_s
    thr = REST_FRAC * math.sqrt(G * D)
    insts, pos_l, rad_l = [], [], []
    x_cursor = 0.0
    for t in tasks:
        p = t["p"]
        rng = np.random.default_rng([space.MASTER_SEED, t["geom_seed"], t["seed"]])
        lx0, lx1 = 0.0, (p["L0_D"] + 3.5 * p["a"] * p["L0_D"] + 20.0) * D
        shift = x_cursor - lx0
        x_cursor += (lx1 - lx0) + GAP_D * D
        pos, rad = packing.column_state(p, rng, cfg.poly)
        pos = pos.copy()
        pos[:, 0] += shift
        insts.append(
            {
                "p": p,
                "shift": shift,
                "X0": lx0 + shift,
                "X1": lx1 + shift,
                "lx0": lx0,
                "lx1": lx1,
                "status": "run",
                "h0_real": None,
            }
        )
        pos_l.append(pos)
        rad_l.append(rad)
    pos, rad = np.concatenate(pos_l), np.concatenate(rad_l)
    counts = [len(r) for r in rad_l]
    sl = np.cumsum([0, *counts])
    ps = PlanarSim(pos, rad, np.zeros(len(pos), dtype=np.int32), collapse_walls(insts, False), cfg, device=device)
    sim = ps.sim
    quiet = np.zeros(len(insts), dtype=int)
    while sim.time < settle_cap and not (quiet >= 3).all():
        pacer.check()
        ps.advance(STEPS_PER_FRAME)
        v = np.linalg.norm(sim.velocities, axis=1)
        for k in range(len(insts)):
            vk = v[sl[k] : sl[k + 1]]
            quiet[k] = quiet[k] + 1 if (sim.time > 0.4 and np.percentile(vk, 99) < 0.03 and vk.max() < 0.2) else 0
    pos3, vel, ang = sim.positions, sim.velocities, sim.angular_velocities
    keep_all, new_counts = [], []
    for k, it in enumerate(insts):
        a, b = sl[k], sl[k + 1]
        if quiet[k] < 3:
            it["status"] = "no-settle"
        top = it["p"]["a"] * it["p"]["L0_D"] * D
        zt = pos3[a:b, 2] + rad[a:b]
        if it["status"] == "run" and zt.max() < top:
            it["status"] = "underfilled"
        keep = zt <= top
        if it["status"] != "run":
            keep = np.zeros(b - a, dtype=bool)
            keep[: min(8, b - a)] = True
        keep_all.append(np.where(keep)[0] + a)
        new_counts.append(int(keep.sum()))
        it["h0_real"] = float(zt[keep].max() / D) if it["status"] == "run" else None
    idx = np.concatenate(keep_all)
    pos, vel, ang, rad = pos3[idx], vel[idx], ang[idx], rad[idx]
    counts = new_counts
    del ps, sim
    ps = PlanarSim(
        pos,
        rad,
        np.zeros(len(pos), dtype=np.int32),
        collapse_walls(insts, True),
        cfg,
        velocities=vel,
        angular_velocities=ang,
        device=device,
    )
    sim = ps.sim
    sl = np.cumsum([0, *counts])
    fr, ft = [[] for _ in insts], [[] for _ in insts]
    judges = [measure.RestJudge(thr) for _ in insts]
    last_v = [0.0] * len(insts)
    cap_t = space.T_CAP["column-collapse"] if t_cap is None else t_cap
    p0 = sim.positions
    for k, it in enumerate(insts):
        if it["status"] != "run":
            continue
        a, b = sl[k], sl[k + 1]
        fr[k].append(np.stack([p0[a:b, 0] - it["shift"], p0[a:b, 2]], axis=1).astype(np.float32))
        ft[k].append(0.0)
        it["z_top0"] = float((p0[a:b, 2] + rad[a:b]).max())
    while sim.time < cap_t and any(i["status"] == "run" for i in insts):
        pacer.check()
        ps.advance(STEPS_PER_FRAME)
        p3 = sim.positions
        v = np.linalg.norm(sim.velocities, axis=1)
        if not np.isfinite(p3).all():
            for it in insts:
                if it["status"] == "run":
                    it["status"] = "non-finite"
            break
        for k, it in enumerate(insts):
            if it["status"] != "run":
                continue
            a, b = sl[k], sl[k + 1]
            fr[k].append(np.stack([p3[a:b, 0] - it["shift"], p3[a:b, 2]], axis=1).astype(np.float32))
            ft[k].append(sim.time)
            last_v[k] = float(v[a:b].max())
            if judges[k].update(sim.time, last_v[k]) == "rest":
                it["status"] = "rest"
    cc = sim.contact_counts()
    y_max = float(np.abs(sim.positions[:, 1]).max())
    total_mass = float(sim.masses.sum())
    mass_ok = bool(abs(sim.mass_inside() - total_mass) < 1e-6 * total_mass)
    wall = time.perf_counter() - t0 - (pacer.idle_s - idle0)
    out = []
    for k, it in enumerate(insts):
        a, b = sl[k], sl[k + 1]
        if it["status"] == "run":
            it["status"] = "no-rest"
        if it["status"] != "rest":
            out.append({"status": it["status"], "wall_s": wall / len(insts)})
            continue
        frames = np.stack(fr[k])
        r = rad[a:b]
        fin = frames[-1]
        zt = float(max(it["z_top0"], max((f[:, 1] + r).max() for f in frames[:: max(1, len(frames) // 40)])))
        out.append(
            {
                "status": "rest",
                "frames": frames,
                "frame_times": np.array(ft[k]),
                "radii": r.astype(np.float32),
                "wall_s": wall / len(insts),
                "final_vmax": last_v[k],
                "rest_threshold": thr,
                "pile_height_D": float((fin[:, 1] + r).max() / D),
                "x99_m": float(np.percentile(fin[:, 0], 99)),
                "x01_m": float(np.percentile(fin[:, 0], 1)),
                "bounds": [it["lx0"], 0.0, it["lx1"], zt * 1.05],
                "n": int(b - a),
                "h0_real_D": it["h0_real"],
                "min_z_over_r": float((fin[:, 1] / r).min()),
                "mass_ok": mass_ok,
                "max_contacts": int(cc[a:b].max()),
                "y_abs_max_m": y_max,
            }
        )
    return out


# ----------------------------------------------------------------------------------------------- hopper feeds
def feed_geometry(family: str, p: dict) -> dict[str, float]:
    """Frame of a feed instance (metres): hopper centre, orifice height, domain x limits and the crest data of a
    dump."""
    if family == "pile-formation":
        xc = p["x_p_D"] * D
        return {"x_center": xc, "z_orifice": p["z_o_D"] * D, "lx0": xc - BOX_HALF * D, "lx1": xc + BOX_HALF * D}
    crest, hc = p["x_c_D"] * D, p["h_c_D"] * D
    return {
        "x_center": crest - p["x_off_D"] * D,
        "z_orifice": hc + p["z_o_D"] * D,
        "lx0": crest - BOX_HALF * D,
        "lx1": crest + BOX_HALF * D,
        "crest": crest,
        "crest_z": hc,
    }


def feed_walls(family: str, insts: list[dict]) -> list[Plane]:
    g2 = 0.5 * GAP_D * D
    walls = [Plane((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))]
    for it in insts:
        xl, xr = it["X0"], it["X1"]
        if family == "dump-over-crest":
            xc, hc = it["geo"]["crest"] + it["shift"], it["geo"]["crest_z"]
            walls.append(Plane((0.0, 0.0, hc), (0.0, 0.0, 1.0), tangent_range=(0, xl - g2, xc)))
            walls.append(Plane((xc, 0.0, 0.0), (1.0, 0.0, 0.0), tangent_range=(2, -math.inf, hc)))
        walls.append(Plane((xl, 0.0, 0.0), (1.0, 0.0, 0.0), tangent_range=(0, xl - g2, math.inf)))
        walls.append(Plane((xr, 0.0, 0.0), (-1.0, 0.0, 0.0), tangent_range=(0, -math.inf, xr + g2)))
    return walls


def simulate_feed(
    family: str, tasks: list[dict], pacer: Any, cfg: SimConfig, device: str = "cuda:0", *, t_cap: float | None = None
) -> list[dict]:
    """Pile or dump rollouts from a funnel hopper, K side by side. Only the grains are recorded (the funnel is a
    generator-side obstacle). A rollout is "rest" only when it is static AND at least DISCHARGED_MIN of its grains have
    left the orifice; static before that is "jammed"."""
    t0 = time.perf_counter()
    idle0 = pacer.idle_s
    thr = REST_FRAC * math.sqrt(G * D)
    insts, pos_l, rad_l, frz_l = [], [], [], []
    x_cursor = 0.0
    for t in tasks:
        p = t["p"]
        rng = np.random.default_rng([space.MASTER_SEED, 77, t["geom_seed"], t["seed"]])
        geo = feed_geometry(family, p)
        shift = x_cursor - geo["lx0"]
        x_cursor += (geo["lx1"] - geo["lx0"]) + GAP_D * D
        h = packing.hopper_state(p, rng, x_center=geo["x_center"], z_orifice=geo["z_orifice"], poly=cfg.poly)
        pos = h.positions.copy()
        pos[:, 0] += shift
        insts.append(
            {
                "p": p,
                "geo": geo,
                "shift": shift,
                "X0": geo["lx0"] + shift,
                "X1": geo["lx1"] + shift,
                "status": "run",
                "hopper": h,
                "n": len(pos),
            }
        )
        pos_l.append(pos)
        rad_l.append(h.radii)
        frz_l.append(h.frozen)
    pos, rad, frz = np.concatenate(pos_l), np.concatenate(rad_l), np.concatenate(frz_l)
    sl = np.cumsum([0] + [i["n"] for i in insts])
    grain_idx = [np.arange(sl[k], sl[k + 1])[insts[k]["hopper"].frozen == 0] for k in range(len(insts))]
    ps = PlanarSim(pos, rad, frz, feed_walls(family, insts), cfg, device=device)
    sim = ps.sim
    fr, ft = [[] for _ in insts], [[] for _ in insts]
    judges = [measure.RestJudge(thr, discharged_min=DISCHARGED_MIN, stall_s=STALL_S) for _ in insts]
    last_v, frac_now = [0.0] * len(insts), [0.0] * len(insts)
    cap_t = space.T_CAP[family] if t_cap is None else t_cap

    def snap(k: int, p3: np.ndarray, tm: float) -> None:
        g = grain_idx[k]
        fr[k].append(np.stack([p3[g, 0] - insts[k]["shift"], p3[g, 2]], axis=1).astype(np.float32))
        ft[k].append(tm)

    p0 = sim.positions
    for k in range(len(insts)):
        snap(k, p0, 0.0)
    while sim.time < cap_t and any(i["status"] == "run" for i in insts):
        pacer.check()
        ps.advance(STEPS_PER_FRAME)
        p3 = sim.positions
        v = np.linalg.norm(sim.velocities, axis=1)
        if not np.isfinite(p3).all():
            for it in insts:
                if it["status"] == "run":
                    it["status"] = "non-finite"
            break
        for k, it in enumerate(insts):
            if it["status"] != "run":
                continue
            snap(k, p3, sim.time)
            g = grain_idx[k]
            last_v[k] = float(v[g].max())
            frac_now[k] = measure.discharged_fraction(p3[g, 2], it["geo"]["z_orifice"])
            verdict = judges[k].update(sim.time, last_v[k], frac_now[k])
            if verdict != "run":
                it["status"] = verdict
    cc = sim.contact_counts()
    y_max = float(np.abs(sim.positions[:, 1]).max())
    total_mass = float(sim.masses.sum())
    mass_ok = bool(abs(sim.mass_inside() - total_mass) < 1e-6 * total_mass)
    wall = time.perf_counter() - t0 - (pacer.idle_s - idle0)
    out = []
    for k, it in enumerate(insts):
        if it["status"] == "run":
            it["status"] = "no-rest"
        if it["status"] != "rest":
            out.append({"status": it["status"], "wall_s": wall / len(insts), "discharged_fraction": frac_now[k]})
            continue
        frames, tt = np.stack(fr[k]), np.array(ft[k])
        r = rad[grain_idx[k]].astype(np.float32)
        z_o = it["geo"]["z_orifice"]
        rate, frac = measure.measure_rate(frames[:, :, 1], tt, r, z_o)
        fin = frames[-1]
        low = fin[:, 1] < z_o - measure.ORIFICE_MARGIN_D * D
        height = float((fin[low, 1] + r[low]).max() / D) if low.any() else 0.0
        zt = float(max((f[:, 1] + r).max() for f in frames[:: max(1, len(frames) // 40)]))
        out.append(
            {
                "status": "rest",
                "frames": frames,
                "frame_times": tt,
                "radii": r,
                "wall_s": wall / len(insts),
                "final_vmax": last_v[k],
                "pile_height_D": height,
                "rate": rate,
                "discharged_fraction": frac,
                "n": len(r),
                "bounds": [it["geo"]["lx0"], 0.0, it["geo"]["lx1"], zt * 1.05],
                "max_contacts": int(cc[grain_idx[k]].max()),
                "y_abs_max_m": y_max,
                "mass_ok": mass_ok,
                "x99_m": float(np.percentile(fin[low, 0], 99)) if low.any() else 0.0,
                "x01_m": float(np.percentile(fin[low, 0], 1)) if low.any() else 0.0,
                "z_orifice_m": z_o,
            }
        )
    return out
