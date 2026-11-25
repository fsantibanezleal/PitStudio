"""Depth-averaged shallow-water solver on Warp with a Bingham bed stress (spec 005, FR-005-23 ... FR-005-32).

Finite volumes on a uniform terrain grid: U = (h, hu, hv) per cell, the Rusanov interface flux, the hydrostatic
reconstruction of Audusse et al. (2004, SIAM J. Sci. Comput. 25(6):2050-2065, DOI 10.1137/S1064827503431090) at every
face (well balanced and positivity preserving), and the explicit step dt = C_CFL min(dx, dy) / max(max(|u|, |v|) +
sqrt(g h)) with C_CFL in (0, 0.5]. The bed stress is the Bingham law solved through the Buckingham-Reiner relation
and applied implicitly after the flux update, so that a cell whose momentum is below dt tau_y / rho comes exactly to
rest.

Arrays are float64 and indexed [row, column] = [y, x]; x grows with the column. Every kernel gathers: a cell reads its
four neighbours and writes only itself, so there are no atomics except an order-independent maximum, and a run is
deterministic. Each face flux is computed from the same inputs by both of its cells, so the mass update telescopes.

Boundaries (per side x-min, x-max, y-min, y-max): "wall" (reflective), "open" (zero gradient of depth and velocity with
the bed continued downhill, never uphill, so a uniform slope flows out at its normal depth and no edge makes water: a
velocity into the domain meets a wall; the volume leaving is accumulated) and
"inflow" (a prescribed depth and velocity over the bed continued linearly). A breach is a triangular
hydrograph of volume V and peak
Q_p injected over declared cells, integrated exactly over every step so that the injected volume is V.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import warp as wp

from pitstudio_studio.physics.errors import PhysicsError

wp.config.quiet = True

SIDES = ("x-min", "x-max", "y-min", "y-max")
BC_WALL, BC_OPEN, BC_INFLOW = 0, 1, 2
_BC_CODES = {"wall": BC_WALL, "open": BC_OPEN, "inflow": BC_INFLOW}
BATCH = 64  # steps launched between two reads of the device clock
UNREACHED = -1.0  # arrival time of a cell the flow never reached (replaced by NaN in the maps)

F64 = wp.float64
HALF = wp.constant(F64(0.5))
ZERO = wp.constant(F64(0.0))
ONE = wp.constant(F64(1.0))


def _invalid(detail: str, **details) -> PhysicsError:
    return PhysicsError("swe-input-invalid", detail, **details)


@dataclass(frozen=True)
class SweParams:
    """Physical and numerical parameters (SI units). Defaults: water, C_CFL 0.45, h_dry 1e-4 m, h_thr 0.05 m."""

    gravity: float = 9.81
    rho: float = 1000.0
    tau_y: float = 0.0  # Pa, Bingham yield stress
    mu_b: float = 0.0  # Pa s, plastic viscosity
    cfl: float = 0.45
    h_dry: float = 1.0e-4  # m: a cell below it has its velocity set to zero; no water is removed or added
    h_thr: float = 0.05  # m: arrival and inundation threshold of the maps
    max_dt: float = math.inf  # s: upper bound of the step (needed when the first step starts from a dry domain)

    def validate(self) -> None:
        for name in ("gravity", "rho", "cfl", "h_dry", "h_thr", "tau_y", "mu_b"):
            if not math.isfinite(getattr(self, name)):
                raise _invalid(f"{name} is not finite", field=name)
        if self.gravity <= 0:
            raise _invalid("gravity must be positive", field="gravity")
        if self.rho <= 0:
            raise _invalid("rho must be positive", field="rho")
        if not 0.0 < self.cfl <= 0.5:
            raise _invalid("C_CFL must be in (0, 0.5]", field="cfl", value=self.cfl)
        if self.tau_y < 0:
            raise _invalid("tau_y must not be negative", field="tau_y")
        if self.mu_b < 0:
            raise _invalid("mu_b must not be negative", field="mu_b")
        if self.h_thr <= 0:
            raise _invalid("h_thr must be positive", field="h_thr")
        if self.h_dry < 0:
            raise _invalid("h_dry must not be negative", field="h_dry")
        if not self.max_dt > 0:
            raise _invalid("max_dt must be positive", field="max_dt")


@dataclass(frozen=True)
class Breach:
    """A triangular breach hydrograph: volume V (m3), peak Q_p (m3/s), peak at `peak_fraction` of the base T = 2V/Q_p.

    `cells` are (row, column) pairs; the volume is spread evenly over them and injected at rest.
    """

    cells: Sequence[tuple[int, int]]
    volume: float
    peak_discharge: float
    peak_fraction: float = 0.5
    start: float = 0.0

    @property
    def base_time(self) -> float:
        return 2.0 * self.volume / self.peak_discharge

    def released(self, t: float) -> float:
        """Cumulative volume released at time t (m3), exact integral of the triangular hydrograph."""
        return _released(t - self.start, self.volume, self.peak_discharge, self.peak_fraction)


def _released(tau: float, volume: float, q_peak: float, frac: float) -> float:
    base = 2.0 * volume / q_peak
    tp = frac * base
    if tau <= 0.0:
        return 0.0
    if tau >= base:
        return volume
    if tau <= tp:
        return q_peak * tau * tau / (2.0 * tp)
    s = tau - tp
    return q_peak * tp / 2.0 + q_peak * s - q_peak * s * s / (2.0 * (base - tp))


@wp.func
def released_volume(tau: wp.float64, volume: wp.float64, q_peak: wp.float64, frac: wp.float64) -> wp.float64:
    out = ZERO
    if volume > ZERO and q_peak > ZERO:  # no breach: V = Q_p = 0
        base = wp.float64(2.0) * volume / q_peak
        tp = frac * base
        if tau >= base:
            out = volume
        elif tau > ZERO:
            if tau <= tp:
                out = q_peak * tau * tau / (wp.float64(2.0) * tp)
            else:
                s = tau - tp
                out = q_peak * tp * HALF + q_peak * s - q_peak * s * s / (wp.float64(2.0) * (base - tp))
    return out


@wp.func
def velocity(h: wp.float64, q: wp.float64, h_dry: wp.float64) -> wp.float64:
    out = ZERO
    if h > h_dry:
        out = q / h
    return out


@wp.func
def face_flux(
    h_l: wp.float64, qn_l: wp.float64, qt_l: wp.float64, z_l: wp.float64,
    h_r: wp.float64, qn_r: wp.float64, qt_r: wp.float64, z_r: wp.float64,
    g: wp.float64, h_dry: wp.float64,
) -> wp.vec4d:  # fmt: skip
    """Rusanov flux with hydrostatic reconstruction through a face: (mass, normal momentum for the left cell, normal
    momentum for the right cell, tangential momentum). Normal and tangential are the components across and along it."""
    zf = wp.max(z_l, z_r)
    hs_l = wp.max(ZERO, h_l + z_l - zf)
    hs_r = wp.max(ZERO, h_r + z_r - zf)
    un_l = velocity(h_l, qn_l, h_dry)
    un_r = velocity(h_r, qn_r, h_dry)
    ut_l = velocity(h_l, qt_l, h_dry)
    ut_r = velocity(h_r, qt_r, h_dry)
    a = wp.max(wp.abs(un_l) + wp.sqrt(g * hs_l), wp.abs(un_r) + wp.sqrt(g * hs_r))
    f1 = HALF * (hs_l * un_l + hs_r * un_r) - HALF * a * (hs_r - hs_l)
    f2 = (
        HALF * (hs_l * un_l * un_l + HALF * g * hs_l * hs_l + hs_r * un_r * un_r + HALF * g * hs_r * hs_r)
        - HALF * a * (hs_r * un_r - hs_l * un_l)
    )  # fmt: skip
    f3 = HALF * (hs_l * un_l * ut_l + hs_r * un_r * ut_r) - HALF * a * (hs_r * ut_r - hs_l * ut_l)
    f2_l = f2 + HALF * g * (h_l * h_l - hs_l * hs_l)
    f2_r = f2 + HALF * g * (h_r * h_r - hs_r * hs_r)
    return wp.vec4d(f1, f2_l, f2_r, f3)


@wp.func
def ghost_state(
    code: int, h: wp.float64, qn: wp.float64, qt: wp.float64, h_in: wp.float64, qn_in: wp.float64, qt_in: wp.float64,
) -> wp.vec3d:  # fmt: skip
    """The state beyond a boundary face, (h, normal momentum, tangential momentum), as seen from the cell `h, qn, qt`
    (normal pointing out of the domain). Wall: normal momentum reversed; open: copy; inflow: the prescribed state."""
    out = wp.vec3d(h, qn, qt)
    if code == 0:
        out = wp.vec3d(h, -qn, qt)
    elif code == 1:
        if qn < ZERO:  # a velocity into the domain meets a wall: an open boundary lets water out and never makes it
            out = wp.vec3d(h, -qn, qt)
    elif code == 2:
        out = wp.vec3d(h_in, qn_in, qt_in)
    return out


@wp.func
def ghost_bed(code: int, z_c: wp.float64, z_in: wp.float64) -> wp.float64:
    """The bed beyond a boundary face: the edge cell's bed continued linearly from its inner neighbour `z_in`. An open
    boundary continues it downhill only (an uphill ghost bed would hold a higher free surface and push water in); an inflow
    boundary continues it both ways (the upstream bed of the prescribed state)."""
    out = z_c
    if code == 2:
        out = wp.float64(2.0) * z_c - z_in
    elif code == 1:
        out = wp.min(z_c, wp.float64(2.0) * z_c - z_in)
    return out


@wp.func
def bingham_scale(
    m_star: wp.float64, h: wp.float64, dt: wp.float64, rho: wp.float64, tau_y: wp.float64, mu: wp.float64
) -> wp.float64:  # fmt: skip
    """The factor m / m* by which the bed stress scales the post-flux momentum magnitude m* (implicit, FR-005-29).

    The new magnitude m solves m + dt tau_b(m / h) / rho = m*, with tau_b >= tau_y the stress of the Buckingham-Reiner
    relation U = (tau_b h / (3 mu)) (1 - r)^2 (1 + r / 2), r = tau_y / tau_b (the factored form of
    1 - 3r/2 + r^3/2). The left side rises with tau_b, so the root is bracketed by [tau_y, rho m* / dt]."""
    out = ONE
    if m_star > ZERO and dt > ZERO:  # dt = 0 is the idle step after the end time: no friction acts
        stop = dt * tau_y / rho
        if mu <= ZERO:
            if tau_y > ZERO:
                out = wp.max(m_star - stop, ZERO) / m_star
        elif tau_y <= ZERO:
            out = ONE / (ONE + wp.float64(3.0) * mu * dt / (rho * h * h))
        elif m_star <= stop:
            out = ZERO
        else:
            lo = tau_y
            hi = rho * m_star / dt
            for _ in range(200):
                mid = HALF * (lo + hi)
                r = tau_y / mid
                u = mid * h / (wp.float64(3.0) * mu) * (ONE - r) * (ONE - r) * (ONE + HALF * r)
                if h * u + dt * mid / rho > m_star:
                    hi = mid
                else:
                    lo = mid
                if hi - lo <= wp.float64(1.0e-15) * hi:
                    break
            tau = HALF * (lo + hi)
            out = wp.max(m_star - dt * tau / rho, ZERO) / m_star
    return out


@wp.kernel
def speed_kernel(
    h: wp.array2d(dtype=wp.float64), qx: wp.array2d(dtype=wp.float64), qy: wp.array2d(dtype=wp.float64),
    g: wp.float64, h_dry: wp.float64, smax: wp.array(dtype=wp.float64),
):  # fmt: skip
    j, i = wp.tid()
    hh = h[j, i]
    if hh > ZERO:
        s = wp.max(wp.abs(velocity(hh, qx[j, i], h_dry)), wp.abs(velocity(hh, qy[j, i], h_dry))) + wp.sqrt(g * hh)
        wp.atomic_max(smax, 0, s)


@wp.kernel
def dt_kernel(
    smax: wp.array(dtype=wp.float64), clock: wp.array(dtype=wp.float64), t_end: wp.float64, cfl: wp.float64,
    dmin: wp.float64, max_dt: wp.float64, dt: wp.array(dtype=wp.float64),
):  # fmt: skip
    remaining = t_end - clock[0]
    step = remaining
    if remaining <= wp.float64(1.0e-12) * wp.max(ONE, wp.abs(t_end)):
        step = ZERO
    else:
        step = wp.min(step, max_dt)
        if smax[0] > ZERO:
            step = wp.min(step, cfl * dmin / smax[0])
        if step >= remaining * (ONE - wp.float64(1.0e-12)):
            step = remaining
    dt[0] = step


@wp.kernel
def step_kernel(
    h: wp.array2d(dtype=wp.float64), qx: wp.array2d(dtype=wp.float64), qy: wp.array2d(dtype=wp.float64),
    z: wp.array2d(dtype=wp.float64),
    h_new: wp.array2d(dtype=wp.float64), qx_new: wp.array2d(dtype=wp.float64), qy_new: wp.array2d(dtype=wp.float64),
    out_vol: wp.array2d(dtype=wp.float64), clipped: wp.array2d(dtype=wp.float64),
    arrival: wp.array2d(dtype=wp.float64), h_max: wp.array2d(dtype=wp.float64), v_max: wp.array2d(dtype=wp.float64),
    breach: wp.array2d(dtype=wp.int32), bparams: wp.array(dtype=wp.float64),
    bc: wp.array(dtype=wp.int32), inflow: wp.array2d(dtype=wp.float64),
    clock: wp.array(dtype=wp.float64), dt_arr: wp.array(dtype=wp.float64),
    dx: wp.float64, dy: wp.float64, g: wp.float64, h_dry: wp.float64, h_thr: wp.float64,
    rho: wp.float64, tau_y: wp.float64, mu: wp.float64, flag: wp.array(dtype=wp.int32),
):  # fmt: skip
    j, i = wp.tid()
    ny = h.shape[0]
    nx = h.shape[1]
    dt = dt_arr[0]
    t = clock[0]
    hc = h[j, i]
    qxc = qx[j, i]
    qyc = qy[j, i]
    zc = z[j, i]

    # west face: the left state is cell i-1 or the ghost of the x-min boundary
    hw = hc
    qxw = qxc
    qyw = qyc
    zw = zc
    if i > 0:
        hw = h[j, i - 1]
        qxw = qx[j, i - 1]
        qyw = qy[j, i - 1]
        zw = z[j, i - 1]
    else:
        # seen from the cell the outward normal is -x: (normal, tangential) = (-qx, qy); an inflow state is given as
        # (h, u, v) in the x-y frame, so its outward-normal momentum is -h u
        gs = ghost_state(bc[0], hc, -qxc, qyc, inflow[0, 0], -inflow[0, 0] * inflow[0, 1], inflow[0, 0] * inflow[0, 2])
        hw = gs[0]
        qxw = -gs[1]
        qyw = gs[2]
        if bc[0] != 0 and nx > 1:
            zw = ghost_bed(bc[0], zc, z[j, 1])
    fw = face_flux(hw, qxw, qyw, zw, hc, qxc, qyc, zc, g, h_dry)

    # east face
    he = hc
    qxe = qxc
    qye = qyc
    ze = zc
    if i < nx - 1:
        he = h[j, i + 1]
        qxe = qx[j, i + 1]
        qye = qy[j, i + 1]
        ze = z[j, i + 1]
    else:
        gs = ghost_state(bc[1], hc, qxc, qyc, inflow[1, 0], inflow[1, 0] * inflow[1, 1], inflow[1, 0] * inflow[1, 2])
        he = gs[0]
        qxe = gs[1]
        qye = gs[2]
        if bc[1] != 0 and nx > 1:
            ze = ghost_bed(bc[1], zc, z[j, nx - 2])
    fe = face_flux(hc, qxc, qyc, zc, he, qxe, qye, ze, g, h_dry)

    # south face: normal momentum is qy, tangential qx
    hs = hc
    qxs = qxc
    qys = qyc
    zs = zc
    if j > 0:
        hs = h[j - 1, i]
        qxs = qx[j - 1, i]
        qys = qy[j - 1, i]
        zs = z[j - 1, i]
    else:
        gs = ghost_state(bc[2], hc, -qyc, qxc, inflow[2, 0], -inflow[2, 0] * inflow[2, 2], inflow[2, 0] * inflow[2, 1])
        hs = gs[0]
        qys = -gs[1]
        qxs = gs[2]
        if bc[2] != 0 and ny > 1:
            zs = ghost_bed(bc[2], zc, z[1, i])
    gsf = face_flux(hs, qys, qxs, zs, hc, qyc, qxc, zc, g, h_dry)

    # north face
    hn = hc
    qxn = qxc
    qyn = qyc
    zn = zc
    if j < ny - 1:
        hn = h[j + 1, i]
        qxn = qx[j + 1, i]
        qyn = qy[j + 1, i]
        zn = z[j + 1, i]
    else:
        gs = ghost_state(bc[3], hc, qyc, qxc, inflow[3, 0], inflow[3, 0] * inflow[3, 2], inflow[3, 0] * inflow[3, 1])
        hn = gs[0]
        qyn = gs[1]
        qxn = gs[2]
        if bc[3] != 0 and ny > 1:
            zn = ghost_bed(bc[3], zc, z[ny - 2, i])
    gnf = face_flux(hc, qyc, qxc, zc, hn, qyn, qxn, zn, g, h_dry)

    # volume leaving through the domain boundary at this cell (negative: entering)
    leaving = ZERO
    if i == 0:
        leaving -= fw[0] * dy
    if i == nx - 1:
        leaving += fe[0] * dy
    if j == 0:
        leaving -= gsf[0] * dx
    if j == ny - 1:
        leaving += gnf[0] * dx
    out_vol[j, i] = out_vol[j, i] + leaving * dt

    hn_ = hc - dt / dx * (fe[0] - fw[0]) - dt / dy * (gnf[0] - gsf[0])
    mx = qxc - dt / dx * (fe[1] - fw[2]) - dt / dy * (gnf[3] - gsf[3])
    my = qyc - dt / dx * (fe[3] - fw[3]) - dt / dy * (gnf[1] - gsf[2])

    if breach[j, i] != 0:
        n_cells = bparams[5]
        dv = released_volume(t + dt - bparams[3], bparams[0], bparams[1], bparams[2]) - released_volume(
            t - bparams[3], bparams[0], bparams[1], bparams[2]
        )
        hn_ = hn_ + dv / (n_cells * dx * dy)

    if not wp.isfinite(hn_) or not wp.isfinite(mx) or not wp.isfinite(my):
        flag[0] = 1
    if hn_ < ZERO:
        clipped[j, i] = clipped[j, i] - hn_ * dx * dy
        hn_ = ZERO
    if hn_ < h_dry:
        mx = ZERO
        my = ZERO
    else:
        m_star = wp.sqrt(mx * mx + my * my)
        s = bingham_scale(m_star, hn_, dt, rho, tau_y, mu)
        mx = mx * s
        my = my * s

    h_new[j, i] = hn_
    qx_new[j, i] = mx
    qy_new[j, i] = my

    # maps
    if hn_ > h_max[j, i]:
        h_max[j, i] = hn_
    if hn_ > h_dry:
        speed = wp.sqrt(mx * mx + my * my) / hn_
        if speed > v_max[j, i]:
            v_max[j, i] = speed
    if arrival[j, i] < ZERO and hn_ > h_thr:
        t_hit = t + dt
        if hc < h_thr and hn_ > hc:
            t_hit = t + dt * (h_thr - hc) / (hn_ - hc)
        arrival[j, i] = t_hit


@wp.kernel
def advance_kernel(
    clock: wp.array(dtype=wp.float64), dt_arr: wp.array(dtype=wp.float64), smax: wp.array(dtype=wp.float64),
    steps: wp.array(dtype=wp.int64), injected: wp.array(dtype=wp.float64), bparams: wp.array(dtype=wp.float64),
    t_end: wp.float64,
):  # fmt: skip
    dt = dt_arr[0]
    if dt > ZERO:
        t = clock[0]
        injected[0] = (
            injected[0]
            + released_volume(t + dt - bparams[3], bparams[0], bparams[1], bparams[2])
            - released_volume(t - bparams[3], bparams[0], bparams[1], bparams[2])
        )
        steps[0] = steps[0] + wp.int64(1)
        if t + dt >= t_end * (ONE - wp.float64(1.0e-12)):
            clock[0] = t_end
        else:
            clock[0] = t + dt
    smax[0] = ZERO


def _check_array(name: str, a: np.ndarray, shape: tuple[int, ...] | None = None, nonneg: bool = False) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    if a.ndim != 2 or min(a.shape) < 1:
        raise _invalid(f"{name} must be a two-dimensional grid", field=name, shape=a.shape)
    if shape is not None and a.shape != shape:
        raise _invalid(f"{name} has shape {a.shape}, the terrain has {shape}", field=name)
    if not np.isfinite(a).all():
        raise _invalid(f"{name} holds NaN or infinity", field=name)
    if nonneg and (a < 0).any():
        raise _invalid(f"{name} holds a negative depth", field=name)
    return a


class SweSimulation:
    """One shallow-water run on a terrain grid; `advance(t)` integrates to time t and may be called repeatedly."""

    def __init__(
        self,
        bed: np.ndarray,
        depth: np.ndarray | None = None,
        *,
        dx: float,
        dy: float | None = None,
        params: SweParams | None = None,
        boundaries: Mapping[str, str] | None = None,
        inflow: Mapping[str, tuple[float, float, float]] | None = None,
        breach: Breach | None = None,
        momentum: tuple[np.ndarray, np.ndarray] | None = None,
        device: str = "cpu",
    ) -> None:
        self.params = params or SweParams()
        self.params.validate()
        dy = dx if dy is None else dy
        for name, v in (("dx", dx), ("dy", dy)):
            if not (math.isfinite(v) and v > 0):
                raise _invalid(f"{name} must be a positive finite cell size", field=name, value=v)
        z = _check_array("bed", bed)
        h0 = np.zeros_like(z) if depth is None else _check_array("depth", depth, z.shape, nonneg=True)
        ny, nx = z.shape
        if momentum is None:
            q0x, q0y = np.zeros_like(z), np.zeros_like(z)
        else:
            q0x, q0y = (
                _check_array(name, a, z.shape) for name, a in zip(("momentum_x", "momentum_y"), momentum, strict=True)
            )
        codes = [BC_WALL] * 4
        for side, kind in (boundaries or {}).items():
            if side not in SIDES or kind not in _BC_CODES:
                raise _invalid(f"unknown boundary {side!r}: {kind!r}", field="boundaries")
            codes[SIDES.index(side)] = _BC_CODES[kind]
        inflow_rows = np.zeros((4, 3))
        for side, state in (inflow or {}).items():
            if side not in SIDES or codes[SIDES.index(side)] != BC_INFLOW:
                raise _invalid(f"inflow given for {side!r}, which is not an inflow boundary", field="inflow")
            if len(state) != 3 or not all(math.isfinite(v) for v in state) or state[0] < 0:
                raise _invalid(f"inflow state of {side!r} must be a finite (h >= 0, u, v)", field="inflow")
            inflow_rows[SIDES.index(side)] = state
        for k, side in enumerate(SIDES):
            if codes[k] == BC_INFLOW and side not in (inflow or {}):
                raise _invalid(f"the inflow boundary {side!r} needs its state", field="inflow")
        mask = np.zeros((ny, nx), dtype=np.int32)
        bp = np.zeros(6)
        if breach is not None:
            if not (math.isfinite(breach.volume) and breach.volume > 0):
                raise _invalid("breach volume must be positive and finite", field="breach.volume")
            if not (math.isfinite(breach.peak_discharge) and breach.peak_discharge > 0):
                raise _invalid("breach peak discharge must be positive and finite", field="breach.peak_discharge")
            if not (0.0 < breach.peak_fraction < 1.0):
                raise _invalid("breach peak fraction must be in (0, 1)", field="breach.peak_fraction")
            if not math.isfinite(breach.start):
                raise _invalid("breach start must be finite", field="breach.start")
            cells = {(int(r), int(c)) for r, c in breach.cells}
            if not cells or any(not (0 <= r < ny and 0 <= c < nx) for r, c in cells):
                raise _invalid("breach cells must be a non-empty set inside the grid", field="breach.cells")
            for r, c in cells:
                mask[r, c] = 1
            bp[:] = [breach.volume, breach.peak_discharge, breach.peak_fraction, breach.start, 0.0, len(cells)]
        self.breach = breach
        self.dx, self.dy = float(dx), float(dy)
        self.shape = (ny, nx)
        self.device = device
        self._v0 = math.fsum((h0 * (self.dx * self.dy)).ravel())
        arr = lambda a, dt=F64: wp.array(a, dtype=dt, device=device)  # noqa: E731
        self._z = arr(z)
        self._h = [arr(h0), arr(h0)]
        self._qx = [arr(q0x), arr(q0x)]
        self._qy = [arr(q0y), arr(q0y)]
        self._flip = 0
        self._out = arr(np.zeros_like(z))
        self._clipped = arr(np.zeros_like(z))
        arrival = np.where(h0 > self.params.h_thr, 0.0, UNREACHED)
        self._arrival = arr(arrival)
        self._hmax = arr(h0.copy())
        self._vmax = arr(np.zeros_like(z))
        self._mask = arr(mask, wp.int32)
        self._bp = arr(bp)
        self._bc = arr(np.asarray(codes, dtype=np.int32), wp.int32)
        self._inflow = arr(inflow_rows)
        self._clock = arr(np.zeros(1))
        self._dt = arr(np.zeros(1))
        self._smax = arr(np.zeros(1))
        self._steps = arr(np.zeros(1, dtype=np.int64), wp.int64)
        self._injected = arr(np.zeros(1))
        self._flag = arr(np.zeros(1, dtype=np.int32), wp.int32)

    # state ----------------------------------------------------------------------------------------------------
    @property
    def time(self) -> float:
        return float(self._clock.numpy()[0])

    @property
    def steps(self) -> int:
        return int(self._steps.numpy()[0])

    @property
    def h(self) -> np.ndarray:
        return self._h[self._flip].numpy().copy()

    @property
    def qx(self) -> np.ndarray:
        return self._qx[self._flip].numpy().copy()

    @property
    def qy(self) -> np.ndarray:
        return self._qy[self._flip].numpy().copy()

    @property
    def bed(self) -> np.ndarray:
        return self._z.numpy().copy()

    def volume(self) -> float:
        """Water volume in the domain (m3), summed exactly."""
        return math.fsum((self._h[self._flip].numpy() * (self.dx * self.dy)).ravel())

    def initial_volume(self) -> float:
        return self._v0

    def boundary_outflow(self) -> float:
        """Net volume that left through the open and inflow boundaries so far (m3); negative when more entered."""
        return math.fsum(self._out.numpy().ravel())

    def injected_volume(self) -> float:
        """Volume released by the breach hydrograph so far (m3)."""
        return float(self._injected.numpy()[0])

    def clipped_volume(self) -> float:
        """Volume added by the clip of a negative depth to zero (round-off of the update; expected 0 or about 1e-16)."""
        return math.fsum(self._clipped.numpy().ravel())

    def balance_residual(self) -> float:
        """V(t) - V0 - injected + outflow - clipped, relative to the largest of V0 and the released volume
        (FR-005-28)."""
        scale = max(self._v0, self.injected_volume(), 1e-300)
        return (
            self.volume() - self._v0 - self.injected_volume() + self.boundary_outflow() - self.clipped_volume()
        ) / scale

    def maps(self) -> dict[str, np.ndarray | float]:
        """The C2 maps (FR-005-30): arrival time t_arr (s, NaN where never reached), maximum depth (m), maximum speed
        (m/s) and the inundated area A = |{h_max > h_thr}| (m2)."""
        arrival = self._arrival.numpy().copy()
        arrival[arrival < 0.0] = np.nan
        hmax = self._hmax.numpy().copy()
        return {
            "arrival_time_s": arrival,
            "max_depth_m": hmax,
            "max_speed_m_s": self._vmax.numpy().copy(),
            "inundated_area_m2": float((hmax > self.params.h_thr).sum()) * self.dx * self.dy,
        }

    # time stepping --------------------------------------------------------------------------------------------
    def _launch_step(self, t_end: float) -> None:
        p, k = self.params, self._flip
        dev = self.device
        wp.launch(
            speed_kernel, dim=self.shape, device=dev,
            inputs=[self._h[k], self._qx[k], self._qy[k], p.gravity, p.h_dry, self._smax],
        )  # fmt: skip
        wp.launch(
            dt_kernel, dim=1, device=dev,
            inputs=[self._smax, self._clock, t_end, p.cfl, min(self.dx, self.dy), p.max_dt, self._dt],
        )  # fmt: skip
        wp.launch(
            step_kernel, dim=self.shape, device=dev,
            inputs=[
                self._h[k], self._qx[k], self._qy[k], self._z,
                self._h[1 - k], self._qx[1 - k], self._qy[1 - k],
                self._out, self._clipped, self._arrival, self._hmax, self._vmax,
                self._mask, self._bp, self._bc, self._inflow, self._clock, self._dt,
                self.dx, self.dy, p.gravity, p.h_dry, p.h_thr, p.rho, p.tau_y, p.mu_b, self._flag,
            ],
        )  # fmt: skip
        wp.launch(
            advance_kernel, dim=1, device=dev,
            inputs=[self._clock, self._dt, self._smax, self._steps, self._injected, self._bp, t_end],
        )  # fmt: skip
        self._flip = 1 - k

    def advance(
        self,
        t_end: float,
        *,
        between: Callable[[SweSimulation], None] | None = None,
        max_steps: int = 50_000_000,
    ) -> None:
        """Integrate to `t_end` (s). `between` is called after each batch of steps (a guard, a progress line)."""
        if not (math.isfinite(t_end) and t_end >= self.time):
            raise _invalid("t_end must be finite and not before the current time", field="t_end", value=t_end)
        start_steps = self.steps
        while self.time < t_end:
            for _ in range(BATCH):
                self._launch_step(t_end)
            if int(self._flag.numpy()[0]):
                raise PhysicsError("nonfinite-state", "the shallow-water state became NaN or infinite", t=self.time)
            if self.steps - start_steps > max_steps:
                raise PhysicsError("dt-unstable", f"more than {max_steps} steps before t_end", t=self.time)
            if between is not None:
                between(self)
        wp.synchronize_device(self.device)


def uniform_breach_cells(row: int, col: int, rows: int = 1, cols: int = 1) -> list[tuple[int, int]]:
    """A block of `rows` x `cols` cells with its lower-left cell at (row, col)."""
    return [(row + r, col + c) for r in range(rows) for c in range(cols)]
