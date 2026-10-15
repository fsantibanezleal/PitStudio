"""Limit-equilibrium core of case C1: slip-circle search, Bishop and Spencer, Hoek-Brown slices (FR-010-01, FR-010-02,
FR-010-09), numpy only.

Conventions (sliding direction +x; a section that faces -x is analysed as its mirror image and mapped back):
- A trial circle is given by its entry and exit abscissas on the ground, its centre and its radius. The grid of
section 7
  places the centre above the chord so that the lower (minor) arc is the slip surface.
- Slices: ``n`` equal-width slices over [entry_x, exit_x]; weights by the midpoint rule; the base angle alpha at the
slice
  base midpoint, sin(alpha) = (x_c - x_mid) / R, alpha > 0 where the base descends in the sliding direction. The slice
  weight integrates the unit weight of the horizontal layers over the column between the base and the ground.
- Bishop (1955): F = sum[(c' b + W (1 - r_u) tan(phi')) / m_alpha] / sum[W sin(alpha)], m_alpha = cos(alpha)
  (1 + tan(alpha) tan(phi') / F), F0 = 1. The pore pressure is r_u W / b. For a Hoek-Brown base the pair (c', phi') is
  re-evaluated at every iteration at the effective normal stress N'/l of the slice (N' from vertical equilibrium).
- Spencer (1967): parallel interslice forces at the angle theta (added to the base angle). With
  A = c' l + (W cos(alpha) - r_u W / cos(alpha)) tan(phi'), the interslice force increment of a slice is
  dQ = (A - F W sin(alpha)) / (F cos(alpha + theta) + sin(alpha + theta) tan(phi')). Force equilibrium (sum dQ = 0)
  gives
  the force factor and moment equilibrium (sum dQ cos(alpha + theta) = 0) the moment factor; theta solves F_force =
  F_moment
  and the root nearest to zero is taken. At theta = 0 the moment factor is Bishop's.
- Stop rule (FR-010-02): the fixed point stops when |F_k+1 - F_k| <= tolerance (default 1e-9; relative to F above
  F = 1, because the float noise of the slice sums scales with F) after at most 100 iterations. The residual of a
  contraction after such a step is rho/(1 - rho) times the last step, so the returned F adds that tail (geometric
  extrapolation with the observed ratio, ratio capped at 0.95): the error of the returned factor is then second order
  in the tolerance, which keeps the exact identities of P-010-03 to P-010-05 below 1e-9 (the decision of 2026-10-12
  to tighten the stop rule instead of loosening the locked test).
- Rejection (FR-010-09): a circle is rejected with a reason when its mass is empty or has no driving moment
  ("empty-mass"), when m_alpha <= 0.2 on a slice at the final factor ("m_alpha"), when the iteration does not converge
  ("non-convergence") or when no theta in (-90, 90) degrees equalises Spencer's factors ("no-theta").
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NamedTuple

import numpy as np

from pitstudio.slope import section as _section
from pitstudio.slope.hoekbrown import (
    hoek_brown_parameters,
    hoek_brown_sigma1,
    hoek_brown_to_mohr_coulomb,
)

__all__ = [
    "Circle",
    "CircleRejected",
    "CircleResult",
    "analyse_section",
    "bishop_fos",
    "circle_grid",
    "hoek_brown_parameters",
    "hoek_brown_sigma1",
    "hoek_brown_to_mohr_coulomb",
    "spencer_force_factor",
    "spencer_fos",
    "spencer_moment_factor",
]

M_ALPHA_MIN = 0.2
LIVE_SPENCER_CIRCLES = 64
_OK, _NONCONV, _MALPHA, _EMPTY, _NOTHETA = 0, 1, 2, 3, 4
_REASONS = {_NONCONV: "non-convergence", _MALPHA: "m_alpha", _EMPTY: "empty-mass", _NOTHETA: "no-theta"}
_CHUNK_ELEMENTS = 400_000  # circles x slices per chunk of the batch solver


class Circle(NamedTuple):
    """A trial slip circle in the frame of the section document (metres)."""

    entry_x_m: float
    exit_x_m: float
    centre_x_m: float
    centre_z_m: float
    radius_m: float


class CircleResult(NamedTuple):
    """Factor of safety of one circle, the iterations of the fixed point and (Spencer) the interslice angle."""

    fos: float
    iterations: int
    theta_deg: float | None = None


class CircleRejected(Exception):
    """The circle is excluded from the minimum; ``reason`` is one of the four classes of FR-010-09."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ----------------------------------------------------------------------------------------------------------------------
# the search grid


def _grid_arrays(prep: _section.Section) -> tuple[np.ndarray, ...]:
    """(entry, exit, centre_x, centre_z, radius) of every trial circle in the solver frame (section 7 of spec 010)."""
    xc, xt = prep.crest_x, prep.toe_x
    height = prep.height
    s = prep.search
    mid = xc + 0.5 * (xt - xc)
    entry = np.linspace(xc - 2.0 * height, mid, int(s["entry_points"]))
    exit_ = np.linspace(mid, xt + height, int(s["exit_points"]))
    rho = np.geomspace(float(s["rho_min"]), float(s["rho_max"]), int(s["radius_ratios"]))
    ee, xx, rr = np.meshgrid(entry, exit_, rho, indexing="ij")
    keep = (xx > ee).ravel()
    return _circles_through(prep, ee.ravel()[keep], xx.ravel()[keep], rr.ravel()[keep])


def _circles_through(prep: _section.Section, ee: np.ndarray, xx: np.ndarray, rho: np.ndarray) -> tuple[np.ndarray, ...]:
    ze, zx = prep.ground_at(ee), prep.ground_at(xx)
    dx, dz = xx - ee, zx - ze
    length = np.hypot(dx, dz)
    half = length / 2.0
    off = half * np.sqrt(rho**2 - 1.0)
    cx = (ee + xx) / 2.0 + (-dz / length) * off
    cz = (ze + zx) / 2.0 + (dx / length) * off
    return ee, xx, cx, cz, rho * half


def _to_user(prep: _section.Section, arrays: tuple[np.ndarray, ...]) -> tuple[np.ndarray, ...]:
    ee, xx, cx, cz, rad = arrays
    return (-ee, -xx, -cx, cz, rad) if prep.mirrored else (ee, xx, cx, cz, rad)


def _circle_arrays(prep: _section.Section, circles: list[Circle]) -> tuple[np.ndarray, ...]:
    a = np.asarray([tuple(c) for c in circles], dtype=float).reshape(-1, 5)
    ee, xx, cx, cz, rad = (a[:, i] for i in range(5))
    return (-ee, -xx, -cx, cz, rad) if prep.mirrored else (ee, xx, cx, cz, rad)


def circle_grid(section: Any) -> list[Circle]:
    """The deterministic trial circles of section 7, entry-major, then exit, then radius ratio (document frame)."""
    prep = _section.prepare(section)
    arrays = _to_user(prep, _grid_arrays(prep))
    return [Circle(*(float(v) for v in row)) for row in zip(*arrays, strict=True)]


# ----------------------------------------------------------------------------------------------------------------------
# slice geometry and strength tables


@dataclass
class _Geo:
    ok: np.ndarray  # (m,) the circle has a non-empty mass with slices inside the circle
    b: np.ndarray  # (m,)
    sin: np.ndarray  # (m, n)
    cos: np.ndarray
    tan: np.ndarray
    ib: np.ndarray  # (m, n) index of the layer at the slice base
    thick: np.ndarray  # (L, m, n) thickness of each layer inside the column


def _geometry(prep: _section.Section, arrays: tuple[np.ndarray, ...], n: int) -> _Geo:
    ee, xx, cx, cz, rad = arrays
    b = (xx - ee) / n
    xm = ee[:, None] + (np.arange(n) + 0.5)[None, :] * b[:, None]
    with np.errstate(all="ignore"):
        sin_a = (cx[:, None] - xm) / rad[:, None]
        ok = np.all(np.abs(sin_a) < 1.0, axis=1) & np.isfinite(b) & (b > 0.0)
        sin_a = np.clip(sin_a, -0.999999999, 0.999999999)
        cos_a = np.sqrt(1.0 - sin_a**2)
        zbase = cz[:, None] - rad[:, None] * cos_a
        zg = prep.ground_at(xm)
        height = zg - zbase
        ok &= np.all(height > 0.0, axis=1)
        mats = prep.materials
        bottoms = np.asarray([m.bottom_z for m in mats])
        thick = np.empty((len(mats), *xm.shape))
        for i in range(len(mats)):
            top = np.inf if i == 0 else bottoms[i - 1]
            thick[i] = np.clip(np.minimum(zg, top) - np.maximum(zbase, bottoms[i]), 0.0, None)
        ib = (zbase[..., None] <= bottoms[None, None, :-1]).sum(axis=2) if len(mats) > 1 else np.zeros(xm.shape, int)
    return _Geo(ok, b, sin_a, cos_a, sin_a / cos_a, ib, thick)


def _param_table(prep: _section.Section) -> dict[str, np.ndarray]:
    mats = prep.materials
    col = lambda values: np.asarray(values, dtype=float)[:, None]  # noqa: E731
    return {
        "gamma": col([m.unit_weight for m in mats]),
        "c": col([m.cohesion for m in mats]),
        "phi": col([m.friction_deg for m in mats]),
        "gsi": col([m.gsi for m in mats]),
        "m_i": col([m.m_i for m in mats]),
        "sigma_ci": col([m.sigma_ci_mpa for m in mats]),
        "d": col([m.disturbance for m in mats]),
    }


def _weights(geo: _Geo, gamma: np.ndarray) -> np.ndarray:
    w = 0.0
    for i in range(gamma.shape[0]):
        w = w + gamma[i][:, None] * geo.thick[i]
    return w * geo.b[:, None]


class _Mix:
    """Strength per slice: Mohr-Coulomb values, with the Hoek-Brown entries converted at the normal stress."""

    def __init__(
        self, c: np.ndarray, tp: np.ndarray, mask: np.ndarray | None, hb: dict[str, np.ndarray] | None
    ) -> None:
        self.c, self.tp, self.mask, self.hb = c, tp, mask, hb

    @classmethod
    def build(cls, table: dict[str, np.ndarray], hb_layers: np.ndarray, ib: np.ndarray) -> _Mix:
        rows = np.arange(ib.shape[0])[:, None] if table["c"].shape[1] > 1 else 0
        pick = lambda name: table[name][ib, rows]  # noqa: E731
        c, tp = pick("c"), np.tan(np.radians(pick("phi")))
        mask = hb_layers[ib]
        if not mask.any():
            return cls(c, tp, None, None)
        hb = {k: pick(k)[mask] for k in ("gsi", "m_i", "sigma_ci", "d")}
        return cls(c, tp, mask, hb)

    def take(self, keep: np.ndarray) -> _Mix:
        mask = None if self.mask is None else self.mask[keep]
        hb = None
        if self.mask is not None and self.hb is not None:
            # entries of the kept rows, in row-major order as the boolean mask selects them
            sel = np.repeat(keep, self.mask.shape[1]).reshape(self.mask.shape)[self.mask]
            hb = {k: v[sel] for k, v in self.hb.items()}
        return _Mix(self.c[keep], self.tp[keep], mask, hb)

    def convert(self, sn: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.mask is None or self.hb is None:
            return self.c, self.tp
        c, tp = self.c.copy(), self.tp.copy()
        hb = self.hb
        cc, phi = hoek_brown_to_mohr_coulomb(hb["gsi"], hb["m_i"], hb["sigma_ci"], hb["d"], sn[self.mask])
        c[self.mask] = cc
        tp[self.mask] = np.tan(np.radians(phi))
        return c, tp


# ----------------------------------------------------------------------------------------------------------------------
# Bishop


def _bishop_core(
    w: np.ndarray,
    sin_a: np.ndarray,
    cos_a: np.ndarray,
    tan_a: np.ndarray,
    b: np.ndarray,
    ru: np.ndarray,
    mix: _Mix,
    tol: float,
    max_iter: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bishop's fixed point for B rows at once; returns (F, iterations, status) with the codes of ``_REASONS``."""
    n_rows = max(w.shape[0], sin_a.shape[0], b.shape[0], ru.shape[0], mix.c.shape[0])
    n = w.shape[1]
    shape = (n_rows, n)
    w, sin_a, cos_a, tan_a = (np.broadcast_to(a, shape) for a in (w, sin_a, cos_a, tan_a))
    b = np.broadcast_to(b, (n_rows,))
    ru = np.broadcast_to(ru, (n_rows,))
    if mix.c.shape[0] != n_rows:
        mix = _Mix(np.broadcast_to(mix.c, shape), np.broadcast_to(mix.tp, shape), mix.mask, mix.hb)
    out_f = np.full(n_rows, np.nan)
    out_it = np.zeros(n_rows, dtype=int)
    out_st = np.full(n_rows, _OK, dtype=int)
    with np.errstate(all="ignore"):
        drive = (w * sin_a).sum(axis=1)
        dead = ~(drive > 0.0)
        out_st[dead] = _EMPTY
        rows = np.flatnonzero(~dead)
        if rows.size == 0:
            return out_f, out_it, out_st
        s = {
            "w": w[rows],
            "sin": sin_a[rows],
            "cos": cos_a[rows],
            "tan": tan_a[rows],
            "b": b[rows],
            "ru": ru[rows],
            "drive": drive[rows],
            "f": np.ones(rows.size),
            "dprev": np.zeros(rows.size),
        }
        hb_active = mix.mask is not None
        if hb_active:
            mix = mix.take(rows) if rows.size != n_rows else mix
            length = s["b"][:, None] / s["cos"]
            s["sn"] = s["w"] * s["cos"] / length
        else:
            c0, tp0 = mix.c[rows], mix.tp[rows]
            s["base"] = c0 * s["b"][:, None] + s["w"] * (1.0 - s["ru"][:, None]) * tp0
            s["stp"] = s["sin"] * tp0
        for it in range(1, max_iter + 1):
            f = s["f"]
            if hb_active:
                c, tp = mix.convert(s["sn"])
                m = s["cos"] * (1.0 + s["tan"] * tp / f[:, None])
                base = c * s["b"][:, None] + s["w"] * (1.0 - s["ru"][:, None]) * tp
            else:
                m = s["cos"] + s["stp"] / f[:, None]
                base = s["base"]
            f_new = (base / m).sum(axis=1) / s["drive"]
            if hb_active:
                length = s["b"][:, None] / s["cos"]
                n_eff = (s["w"] * (1.0 - s["ru"][:, None]) - c * s["b"][:, None] * s["tan"] / f_new[:, None]) / (
                    s["cos"] * (1.0 + s["tan"] * tp / f_new[:, None])
                )
                s["sn"] = np.maximum(n_eff / length, 0.0)
            d = f_new - f
            finite = np.isfinite(f_new) & (f_new > 0.0)
            conv = finite & (np.abs(d) <= tol * np.maximum(1.0, np.abs(f_new)))  # relative above F = 1: float noise
            stop = conv | ~finite
            if stop.any():
                idx = np.flatnonzero(stop)
                ratio = np.where(s["dprev"][idx] != 0.0, d[idx] / s["dprev"][idx], 0.0)
                ratio = np.clip(np.where(np.isfinite(ratio), ratio, 0.0), 0.0, 0.95)
                f_fin = np.where(conv[idx], f_new[idx] + d[idx] * ratio / (1.0 - ratio), np.nan)
                if hb_active:
                    mm = (s["cos"][idx] * (1.0 + s["tan"][idx] * tp[idx] / f_new[idx][:, None])).min(axis=1)
                else:
                    mm = (s["cos"][idx] + s["stp"][idx] / f_new[idx][:, None]).min(axis=1)
                bad_m = ~(mm > M_ALPHA_MIN)
                st = np.where(bad_m & np.isfinite(mm), _MALPHA, np.where(conv[idx], _OK, _NONCONV))
                st = np.where(conv[idx] & ~(f_fin > 0.0) & ~bad_m, _NONCONV, st)
                gi = rows[idx]
                out_f[gi] = np.where(st == _OK, f_fin, np.nan)
                out_it[gi] = it
                out_st[gi] = st
                keep = ~stop
                if not keep.any():
                    return out_f, out_it, out_st
                rows = rows[keep]
                s = {k: v[keep] for k, v in s.items()}
                f_new, d = f_new[keep], d[keep]
                if hb_active:
                    c, tp = c[keep], tp[keep]
                if hb_active:
                    mix = mix.take(keep)
            s["dprev"] = d
            s["f"] = f_new
        # not converged within the cap: m_alpha at the last factor decides the reason
        f = s["f"]
        if hb_active:
            mm = (s["cos"] * (1.0 + s["tan"] * tp / f[:, None])).min(axis=1)
        else:
            mm = (s["cos"] + s["stp"] / f[:, None]).min(axis=1)
        out_it[rows] = max_iter
        out_st[rows] = np.where(np.isfinite(mm) & ~(mm > M_ALPHA_MIN), _MALPHA, _NONCONV)
    return out_f, out_it, out_st


def _bishop_batch(
    prep: _section.Section, arrays: tuple[np.ndarray, ...], n: int, tol: float, max_iter: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bishop on every circle of ``arrays`` (solver frame) in chunks; (F, iterations, status)."""
    m_all = arrays[0].shape[0]
    f = np.full(m_all, np.nan)
    it = np.zeros(m_all, dtype=int)
    st = np.full(m_all, _EMPTY, dtype=int)
    table = _param_table(prep)
    hb_layers = np.asarray([m.hoek_brown for m in prep.materials])
    ru = np.asarray([prep.pore_pressure_ratio])
    step = max(1, _CHUNK_ELEMENTS // (n * max(1, len(prep.materials))))
    for lo in range(0, m_all, step):
        sl = slice(lo, lo + step)
        geo = _geometry(prep, tuple(a[sl] for a in arrays), n)
        good = np.flatnonzero(geo.ok)
        if good.size == 0:
            continue
        sub = _Geo(
            geo.ok[good], geo.b[good], geo.sin[good], geo.cos[good], geo.tan[good], geo.ib[good], geo.thick[:, good]
        )
        w = _weights(sub, table["gamma"])
        mix = _Mix.build(table, hb_layers, sub.ib)
        ff, ii, ss = _bishop_core(w, sub.sin, sub.cos, sub.tan, sub.b, ru, mix, tol, max_iter)
        gi = lo + good
        f[gi], it[gi], st[gi] = ff, ii, ss
    return f, it, st


def bishop_fos(
    section: Any, circle: Circle, *, slices: int | None = None, max_iterations: int = 100, tolerance: float = 1e-9
) -> CircleResult:
    """Bishop's simplified factor of safety on one circle (raises ``CircleRejected``)."""
    prep = _section.prepare(section)
    n = int(slices or prep.slices)
    arrays = _circle_arrays(prep, [circle])
    f, it, st = _bishop_batch(prep, arrays, n, tolerance, max_iterations)
    if st[0] != _OK:
        raise CircleRejected(_REASONS[int(st[0])])
    return CircleResult(float(f[0]), int(it[0]))


# ----------------------------------------------------------------------------------------------------------------------
# Spencer


@dataclass
class _SpencerSlices:
    alpha: np.ndarray
    w: np.ndarray
    sin: np.ndarray
    cos: np.ndarray
    length: np.ndarray
    a_i: np.ndarray
    tp: np.ndarray
    ib: np.ndarray
    ru: float
    hb: dict[str, np.ndarray] | None


def _spencer_slices(prep: _section.Section, circle: Circle, n: int) -> _SpencerSlices:
    arrays = _circle_arrays(prep, [circle])
    geo = _geometry(prep, arrays, n)
    if not bool(geo.ok[0]):
        raise CircleRejected("empty-mass")
    table = _param_table(prep)
    w = _weights(geo, table["gamma"])[0]
    sin_a, cos_a = geo.sin[0], geo.cos[0]
    ib = geo.ib[0]
    length = geo.b[0] / cos_a
    hb = None
    c = table["c"][ib, 0]
    tp = np.tan(np.radians(table["phi"][ib, 0]))
    mask = np.asarray([m.hoek_brown for m in prep.materials])[ib]
    if mask.any():
        hb = {k: table[k][ib, 0] for k in ("gsi", "m_i", "sigma_ci", "d")}
        hb["mask"] = mask
        hb["c"], hb["tp"] = c, tp
    ru = prep.pore_pressure_ratio
    a_i = c * length + (w * cos_a - ru * w / cos_a) * tp
    return _SpencerSlices(np.arcsin(sin_a), w, sin_a, cos_a, length, a_i, tp, ib, ru, hb)


def _spencer_factors(
    sl: _SpencerSlices, thetas: np.ndarray, kind: str, *, tol: float = 1e-11, max_iter: int = 100
) -> tuple[np.ndarray, np.ndarray]:
    """Force or moment factor for each theta (radians); (F with nan where invalid, iterations)."""
    ang = sl.alpha[None, :] + thetas[:, None]
    cosang, sinang = np.cos(ang), np.sin(ang)
    k = 1.0 if kind == "force" else cosang
    top_w = sl.a_i[None, :] * k
    bot_w = (sl.w * sl.sin)[None, :] * k
    t = thetas.size
    f = np.ones(t)
    out = np.full(t, np.nan)
    iters = np.zeros(t, dtype=int)
    live = np.ones(t, dtype=bool)
    dprev = np.zeros(t)
    with np.errstate(all="ignore"):
        for it in range(1, max_iter + 1):
            den = f[:, None] * cosang + sinang * sl.tp[None, :]
            invalid = (den <= 0.0).any(axis=1)
            f_new = (top_w / den).sum(axis=1) / (bot_w / den).sum(axis=1)
            invalid |= ~np.isfinite(f_new) | (f_new <= 0.0)
            d = f_new - f
            conv = live & ~invalid & (np.abs(d) <= tol * np.maximum(1.0, np.abs(f)))
            ratio = np.clip(np.where(dprev != 0.0, d / dprev, 0.0), 0.0, 0.95)
            out = np.where(conv, f_new + d * ratio / (1.0 - ratio), out)
            iters = np.where(conv, it, iters)
            live &= ~conv & ~invalid
            if not live.any():
                break
            dprev = d
            f = np.where(live, f_new, f)
    return out, iters


def _spencer_root(sl: _SpencerSlices, max_iter: int) -> tuple[float, float, int, float]:
    """(F, theta radians, iterations, force-factor residual) at the root of F_force - F_moment nearest to zero."""
    grid = np.radians(np.linspace(-80.0, 80.0, 81))
    ff, _ = _spencer_factors(sl, grid, "force", max_iter=max_iter)
    fm, _ = _spencer_factors(sl, grid, "moment", max_iter=max_iter)
    diff = ff - fm
    ok = np.isfinite(diff)
    cand = [i for i in range(len(grid) - 1) if ok[i] and ok[i + 1] and diff[i] * diff[i + 1] <= 0.0]
    if not cand:
        raise CircleRejected("no-theta")
    i = min(cand, key=lambda j: abs(grid[j]))
    lo, hi, f_lo, f_hi = float(grid[i]), float(grid[i + 1]), float(diff[i]), float(diff[i + 1])

    def evaluate(theta: float) -> tuple[float, float, int]:
        a, _ = _spencer_factors(sl, np.asarray([theta]), "force", max_iter=max_iter)
        m, it = _spencer_factors(sl, np.asarray([theta]), "moment", max_iter=max_iter)
        return float(a[0]), float(m[0]), int(it[0])

    side = 0
    theta = lo if f_lo == 0.0 else hi if f_hi == 0.0 else 0.5 * (lo + hi)
    f_force, f_mom, iters = evaluate(theta)
    if f_lo != 0.0 and f_hi != 0.0:
        for _ in range(80):
            theta = hi - f_hi * (hi - lo) / (f_hi - f_lo)
            f_force, f_mom, iters = evaluate(theta)
            val = f_force - f_mom
            if not math.isfinite(val):
                theta = 0.5 * (lo + hi)
                f_force, f_mom, iters = evaluate(theta)
                val = f_force - f_mom
                if not math.isfinite(val):
                    raise CircleRejected("no-theta")
            if abs(val) <= 1e-13 * max(1.0, abs(f_mom)) or abs(hi - lo) < 1e-14:
                break
            if val * f_hi > 0.0:
                hi, f_hi = theta, val
                if side == -1:
                    f_lo *= 0.5
                side = -1
            else:
                lo, f_lo = theta, val
                if side == 1:
                    f_hi *= 0.5
                side = 1
    if not (math.isfinite(f_mom) and iters > 0):
        raise CircleRejected("non-convergence")
    return f_mom, theta, iters, f_force - f_mom


def _normal_stress(sl: _SpencerSlices, f: float, theta: float) -> np.ndarray:
    ang = sl.alpha + theta
    with np.errstate(all="ignore"):
        den = f * np.cos(ang) + np.sin(ang) * sl.tp
        dq = (sl.a_i - f * sl.w * sl.sin) / den
        n_eff = sl.w * sl.cos - sl.ru * sl.w / sl.cos - dq * np.sin(ang)
    return np.maximum(n_eff / sl.length, 0.0)


def _spencer_solve(prep: _section.Section, circle: Circle, n: int, max_iter: int) -> tuple[float, float, int]:
    sl = _spencer_slices(prep, circle, n)
    if sl.hb is None:
        f, theta, it, _ = _spencer_root(sl, max_iter)
    else:  # Hoek-Brown: re-evaluate (c', phi') at the slice-base normal stress, as for Bishop, until F settles
        hb = sl.hb
        mask = hb["mask"]
        sn = sl.w * sl.cos / sl.length
        previous = math.nan
        f = theta = math.nan
        it = 0
        for _ in range(100):
            cc, phi = hoek_brown_to_mohr_coulomb(
                hb["gsi"][mask], hb["m_i"][mask], hb["sigma_ci"][mask], hb["d"][mask], sn[mask]
            )
            c, tp = hb["c"].copy(), hb["tp"].copy()
            c[mask], tp[mask] = cc, np.tan(np.radians(phi))
            sl.tp = tp
            sl.a_i = c * sl.length + (sl.w * sl.cos - sl.ru * sl.w / sl.cos) * tp
            f, theta, it, _ = _spencer_root(sl, max_iter)
            if abs(f - previous) <= 1e-10:
                break
            previous = f
            sn = _normal_stress(sl, f, theta)
        else:
            raise CircleRejected("non-convergence")
    return f, math.degrees(theta), it


def spencer_fos(section: Any, circle: Circle, *, slices: int | None = None, max_iterations: int = 100) -> CircleResult:
    """Spencer's factor of safety and interslice angle on one circle (raises ``CircleRejected``)."""
    prep = _section.prepare(section)
    n = int(slices or prep.slices)
    f, theta_deg, it = _spencer_solve(prep, circle, n, max_iterations)
    if not (-90.0 < theta_deg < 90.0):
        raise CircleRejected("no-theta")
    return CircleResult(f, max(1, min(it, 100)), -theta_deg if prep.mirrored else theta_deg)


def _spencer_one_factor(section: Any, circle: Circle, theta_deg: float, slices: int | None, kind: str) -> float:
    prep = _section.prepare(section)
    n = int(slices or prep.slices)
    sl = _spencer_slices(prep, circle, n)
    if sl.hb is not None:
        sn = sl.w * sl.cos / sl.length
        hb, mask = sl.hb, sl.hb["mask"]
        cc, phi = hoek_brown_to_mohr_coulomb(
            hb["gsi"][mask], hb["m_i"][mask], hb["sigma_ci"][mask], hb["d"][mask], sn[mask]
        )
        c, tp = hb["c"].copy(), hb["tp"].copy()
        c[mask], tp[mask] = cc, np.tan(np.radians(phi))
        sl.tp = tp
        sl.a_i = c * sl.length + (sl.w * sl.cos - sl.ru * sl.w / sl.cos) * tp
    theta = math.radians(-theta_deg if prep.mirrored else theta_deg)
    f, _ = _spencer_factors(sl, np.asarray([theta]), kind, tol=1e-12, max_iter=500)
    if not math.isfinite(float(f[0])):
        raise CircleRejected("m_alpha")
    return float(f[0])


def spencer_moment_factor(section: Any, circle: Circle, theta_deg: float, *, slices: int | None = None) -> float:
    """Moment-equilibrium factor of Spencer's method at the interslice angle ``theta_deg`` (Bishop's F at 0)."""
    return _spencer_one_factor(section, circle, theta_deg, slices, "moment")


def spencer_force_factor(section: Any, circle: Circle, theta_deg: float, *, slices: int | None = None) -> float:
    """Force-equilibrium factor of Spencer's method at the interslice angle ``theta_deg``."""
    return _spencer_one_factor(section, circle, theta_deg, slices, "force")


# ----------------------------------------------------------------------------------------------------------------------
# the search over the grid


def _circle_dict(c: Circle) -> dict[str, float]:
    return {
        "centre_x_m": float(c.centre_x_m),
        "centre_z_m": float(c.centre_z_m),
        "radius_m": float(c.radius_m),
        "entry_x_m": float(c.entry_x_m),
        "exit_x_m": float(c.exit_x_m),
    }


def _row(
    method: str, n: int, evaluated: int, rejected: int, best: tuple[Circle, CircleResult] | None
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "method": method,
        "status": "ok" if best is not None else "no valid slip surface",
        "slices": n,
        "circles_evaluated": evaluated,
        "rejected_circles": rejected,
    }
    if best is not None:
        circle, res = best
        row["fos"] = float(res.fos)
        row["critical_circle"] = _circle_dict(circle)
        row["iterations"] = int(res.iterations)
        if method == "spencer":
            row["theta_deg"] = float(res.theta_deg if res.theta_deg is not None else 0.0)
    return row


Solver = Callable[..., CircleResult]


def analyse_section(section: Any, *, bishop: Solver | None = None, spencer: Solver | None = None) -> dict[str, Any]:
    """Minimum factor of safety of a section by Bishop and/or Spencer over the search grid (FR-010-01, FR-010-09).

    The section is validated first (``InvalidSectionError``); ``bishop`` and ``spencer`` are the per-circle solvers (a
    test seam; by default the vectorised product solvers are used). Spencer runs on the 64 lowest-Bishop circles in live
    mode and on every circle in baked mode; in live mode the rejected count of the Spencer row also includes the
    circles Bishop rejected (the candidate set is drawn from the valid ones)."""
    prep = _section.parse_section(section) if not isinstance(section, _section.Section) else section
    doc = prep.document
    n = prep.slices
    arrays = _grid_arrays(prep)
    circles = [Circle(*(float(v) for v in row)) for row in zip(*_to_user(prep, arrays), strict=True)]
    total = len(circles)
    default_bishop = bishop is None or bishop is bishop_fos
    methods = prep.methods
    need_bishop = "bishop" in methods or ("spencer" in methods and prep.mode == "live")

    b_results: list[CircleResult | None] = []
    b_rejected = 0
    if need_bishop:
        if default_bishop:
            f, it, st = _bishop_batch(prep, arrays, n, 1e-9, 100)
            b_results = [CircleResult(float(f[i]), int(it[i])) if st[i] == _OK else None for i in range(total)]
        else:
            assert bishop is not None
            for c in circles:
                try:
                    b_results.append(bishop(doc, c, slices=n))
                except CircleRejected:
                    b_results.append(None)
        b_rejected = sum(r is None for r in b_results)

    def best_of(results: list[CircleResult | None], pool: list[int]) -> tuple[Circle, CircleResult] | None:
        valid = [i for i in pool if results[i] is not None]
        if not valid:
            return None
        i = min(valid, key=lambda j: results[j].fos)  # type: ignore[union-attr]
        res = results[i]
        assert res is not None
        return circles[i], res

    rows = []
    for method in methods:
        if method == "bishop":
            rows.append(_row("bishop", n, total, b_rejected, best_of(b_results, list(range(total)))))
            continue
        solve = spencer if spencer is not None else spencer_fos
        if prep.mode == "live":
            valid = [i for i in range(total) if b_results[i] is not None]
            pool = sorted(valid, key=lambda j: b_results[j].fos)[:LIVE_SPENCER_CIRCLES]  # type: ignore[union-attr]
            base_rejected = b_rejected
        else:
            pool, base_rejected = list(range(total)), 0
        s_results: list[CircleResult | None] = [None] * total
        s_rejected = 0
        for i in pool:
            try:
                s_results[i] = solve(doc, circles[i], slices=n)
            except CircleRejected:
                s_rejected += 1
        rows.append(_row("spencer", n, total, base_rejected + s_rejected, best_of(s_results, pool)))
    return {"section_id": prep.section_id, "fos": rows}
