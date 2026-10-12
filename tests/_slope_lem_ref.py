"""Independent textbook reference for the C1 limit-equilibrium tests of spec 010 (numpy and the stdlib only).

This module is an ORACLE, not a product module: it re-implements, from the published formulas, what the tests of
T-010-010 ... T-010-018 compare `pitstudio.slope` against. It never imports the code under test.

Sources written out in the formulas below:
- Bishop (1955), simplified method: F = sum[(c' b + (W - u b) tan(phi)) / m_a] / sum[W sin(a)],
  m_a = cos(a) (1 + tan(a) tan(phi) / F)  (docs/methods/m13-slope-stability-lem.md, worked example with 1.866 ...).
- Spencer (1967): slice equilibrium parallel and normal to the base with parallel interslice forces at angle theta;
  force factor F_f solves sum(dQ) = 0, moment factor F_m solves sum(dQ cos(a + theta)) = 0 (derived in the comments of
  `spencer_one`; at theta = 0 the moment factor is exactly Bishop's, verified in test_t_010_010).
- Hoek and Brown (2018) generalised criterion and Balmer (1952) parametric form of the normal and shear stress.
- Geometry: the planar ground of `planar_section` makes every trial circle "clean" (its arc lies below the ground
  between the entry and exit points), so no clipping rule is needed (the spec leaves that open, see the report).
- Slices: equal width over [x_entry, x_exit], weights by the midpoint rule, base angle at the slice-base midpoint
  (sin a = (x_c - x_mid) / R; a > 0 on the side where the base descends in the sliding direction +x), as the plan's
  tolerance section (P-010-06, "midpoint-rule slice weights") assumes.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]


def schema_errors(document: object, stem: str, definition: str | None = None) -> list[str]:
    """Violations of `contracts/<stem>.schema.json` (or of one of its `$defs`) by a document (jsonschema, 2020-12)."""
    from jsonschema import Draft202012Validator

    schema = json.loads((REPO / "contracts" / f"{stem}.schema.json").read_text(encoding="utf-8"))
    if definition is not None:
        schema = {"$schema": schema["$schema"], "$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]}
    return [
        f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
        for e in Draft202012Validator(schema).iter_errors(document)
    ]


# ----------------------------------------------------------------------------------------------------------------------
# sections


def planar_section(
    *,
    height_m: float = 20.0,
    slope_deg: float = 45.0,
    unit_weight: float = 20.0,
    cohesion: float = 20.0,
    friction: float = 30.0,
    ru: float = 0.0,
    mode: str = "baked",
    slices: int = 200,
    methods: tuple[str, ...] = ("bishop", "spencer"),
    search: dict | None = None,
    section_id: str = "c1-planar-ref",
    pof: dict | None = None,
    material: dict | None = None,
) -> dict:
    """A DC-010-01 document whose ground is ONE straight line through crest and toe (extended on both sides)."""
    t = math.tan(math.radians(slope_deg))
    x_c, x_t = 0.0, height_m / t
    x_left, x_right = x_c - 3 * height_m, x_t + 2 * height_m
    ground = [[x_left, height_m - (x_left - x_c) * t], [x_right, height_m - (x_right - x_c) * t]]
    mat = material or {
        "id": "fill",
        "model": "mohr-coulomb",
        "unit_weight_kn_per_m3": unit_weight,
        "cohesion_kpa": cohesion,
        "friction_angle_deg": friction,
    }
    analysis: dict = {
        "mode": mode,
        "methods": list(methods),
        "slices": slices,
        "search": search
        or {"entry_points": 40, "exit_points": 40, "radius_ratios": 8, "rho_min": 1.02, "rho_max": 4.0},
    }
    if pof is not None:
        analysis["pof"] = pof
    return {
        "schema_version": "1.0",
        "section_id": section_id,
        "source": {"kind": "fixture"},
        "ground": ground,
        "crest_x_m": x_c,
        "toe_x_m": x_t,
        "materials": [mat],
        "pore_pressure_ratio": ru,
        "analysis": analysis,
    }


def ground_fn(section: dict) -> Callable[[np.ndarray], np.ndarray]:
    (xa, za), (xb, zb) = section["ground"][0], section["ground"][-1]
    slope = (zb - za) / (xb - xa)
    return lambda x: za + slope * (np.asarray(x, dtype=float) - xa)


def mc_params(section: dict) -> tuple[float, float, float]:
    m = section["materials"][0]
    return m["unit_weight_kn_per_m3"], m.get("cohesion_kpa", 0.0), m.get("friction_angle_deg", 0.0)


# ----------------------------------------------------------------------------------------------------------------------
# the deterministic search grid of spec 010 section 7


def grid_axes(section: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Entry x, exit x and radius-ratio axes exactly as the section 7 parameter table states them."""
    x_c, x_t = section["crest_x_m"], section["toe_x_m"]
    z = ground_fn(section)
    height = float(z(x_c) - z(x_t))
    s = section["analysis"]["search"]
    mid = x_c + 0.5 * (x_t - x_c)
    entry = np.linspace(x_c - 2 * height, mid, s["entry_points"])
    exit_ = np.linspace(mid, x_t + height, s["exit_points"])
    rho = np.geomspace(s["rho_min"], s["rho_max"], s["radius_ratios"])
    return entry, exit_, rho


def grid_circles(section: dict) -> tuple[np.ndarray, ...]:
    """(entry_x, exit_x, centre_x, centre_z, radius) of every trial circle, pairs with exit <= entry dropped."""
    entry, exit_, rho = grid_axes(section)
    ee, xx, rr = np.meshgrid(entry, exit_, rho, indexing="ij")
    keep = (xx > ee).ravel()
    ee, xx, rr = ee.ravel()[keep], xx.ravel()[keep], rr.ravel()[keep]
    g = ground_fn(section)
    ze, zx = g(ee), g(xx)
    dx, dz = xx - ee, zx - ze
    length = np.hypot(dx, dz)
    half = length / 2
    radius = rr * half
    off = half * np.sqrt(rr**2 - 1)
    cx = (ee + xx) / 2 + (-dz / length) * off
    cz = (ze + zx) / 2 + (dx / length) * off
    return ee, xx, cx, cz, radius


def circle_from_points(section: dict, entry_x: float, exit_x: float, rho: float) -> tuple[float, ...]:
    """(entry_x, exit_x, centre_x, centre_z, radius) of one circle of the grid family."""
    out = grid_circles_for(section, np.array([entry_x]), np.array([exit_x]), np.array([rho]))
    return tuple(float(a[0]) for a in out)


def grid_circles_for(section: dict, ee: np.ndarray, xx: np.ndarray, rr: np.ndarray) -> tuple[np.ndarray, ...]:
    g = ground_fn(section)
    ze, zx = g(ee), g(xx)
    dx, dz = xx - ee, zx - ze
    length = np.hypot(dx, dz)
    half = length / 2
    off = half * np.sqrt(rr**2 - 1)
    cx = (ee + xx) / 2 + (-dz / length) * off
    cz = (ze + zx) / 2 + (dx / length) * off
    return ee, xx, cx, cz, rr * half


# ----------------------------------------------------------------------------------------------------------------------
# slices


def slices_of(section: dict, circle: tuple[float, ...], n: int) -> dict[str, np.ndarray]:
    """Midpoint-rule slices of one circle on the single-material planar section."""
    xe, xx, xc, zc, radius = circle
    gamma, _, _ = mc_params(section)
    b = (xx - xe) / n
    xm = xe + (np.arange(n) + 0.5) * b
    sin_a = (xc - xm) / radius
    cos_a = np.sqrt(1.0 - sin_a**2)
    zarc = zc - radius * cos_a
    height = ground_fn(section)(xm) - zarc
    return {"b": b, "xm": xm, "sin": sin_a, "cos": cos_a, "tan": sin_a / cos_a, "h": height, "W": gamma * height * b}


# ----------------------------------------------------------------------------------------------------------------------
# Bishop (vectorised over circles)


def bishop_vec(
    section: dict, circles: tuple[np.ndarray, ...], n: int, *, max_iter: int = 100, tol: float = 1e-9
) -> np.ndarray:
    """Bishop F for every circle (nan where the circle is rejected: no convergence, m_a <= 0.2, no driving moment)."""
    xe, xx, xc, zc, radius = circles
    gamma, c, phi = mc_params(section)
    ru = section["pore_pressure_ratio"]
    tanphi = math.tan(math.radians(phi))
    b = (xx - xe) / n
    xm = xe[:, None] + (np.arange(n) + 0.5)[None, :] * b[:, None]
    sin_a = (xc[:, None] - xm) / radius[:, None]
    ok = np.all(np.abs(sin_a) < 1.0, axis=1)
    sin_a = np.clip(sin_a, -0.999999999, 0.999999999)
    cos_a = np.sqrt(1.0 - sin_a**2)
    tan_a = sin_a / cos_a
    height = ground_fn(section)(xm) - (zc[:, None] - radius[:, None] * cos_a)
    ok &= np.all(height > 0, axis=1)
    weight = gamma * height * b[:, None]
    drive = (weight * sin_a).sum(axis=1)
    base = c * b[:, None] + weight * (1.0 - ru) * tanphi
    f = np.ones(len(xe))
    active = np.ones(len(xe), dtype=bool)
    with np.errstate(all="ignore"):
        for _ in range(max_iter):
            m = cos_a * (1.0 + tan_a * tanphi / f[:, None])
            f_new = (base / m).sum(axis=1) / drive
            done = active & (np.abs(f_new - f) <= tol)
            f = np.where(active, f_new, f)
            active &= ~done
            if not active.any():
                break
        m_final = cos_a * (1.0 + tan_a * tanphi / f[:, None])
    valid = ok & ~active & np.all(m_final > 0.2, axis=1) & (drive > 0) & np.isfinite(f) & (f > 0)
    return np.where(valid, f, np.nan)


def min_m_alpha(section: dict, circle: tuple[float, ...], n: int, f: float) -> float:
    """Smallest m_alpha over the slices of one circle at the trial factor f."""
    _, _, phi = mc_params(section)
    s = slices_of(section, circle, n)
    return float((s["cos"] * (1.0 + s["tan"] * math.tan(math.radians(phi)) / f)).min())


def rightmost_point_circle(section: dict, exit_x: float, radius: float) -> tuple[float, ...]:
    """Circle whose rightmost point is the exit point on the (planar) ground, so the exit base is vertical.

    With u = x - exit_x and the ground slope t: (u + R)^2 + t^2 u^2 = R^2 gives the entry at u = -2R / (1 + t^2)."""
    g = ground_fn(section)
    t = -(float(g(1.0)) - float(g(0.0)))
    z_exit = float(g(exit_x))
    entry = exit_x - 2.0 * radius / (1.0 + t * t)
    return entry, exit_x, exit_x - radius, z_exit, radius


def bishop_one(section: dict, circle: tuple[float, ...], n: int) -> float:
    f = bishop_vec(section, tuple(np.array([a]) for a in circle), n)
    return float(f[0])


def bishop_fixed_point(
    weights: list[float],
    angles_deg: list[float],
    widths: list[float],
    c: float,
    phi_deg: float,
    *,
    f0: float = 1.0,
    steps: int = 5,
) -> tuple[float, list[float]]:
    """The bare fixed-point iteration of the M13 worked example: returns (sum W sin a, [F_1 ... F_steps])."""
    w, a, b = (np.asarray(v, dtype=float) for v in (weights, np.radians(angles_deg), widths))
    tanphi = math.tan(math.radians(phi_deg))
    drive = float((w * np.sin(a)).sum())
    f, out = f0, []
    for _ in range(steps):
        m = np.cos(a) * (1.0 + np.tan(a) * tanphi / f)
        f = float(((c * b + w * tanphi) / m).sum() / drive)
        out.append(f)
    return drive, out


def grid_bishop(section: dict, n: int | None = None) -> tuple[tuple[np.ndarray, ...], np.ndarray]:
    circles = grid_circles(section)
    return circles, bishop_vec(section, circles, n or section["analysis"]["slices"])


# ----------------------------------------------------------------------------------------------------------------------
# Spencer (one circle)


def _spencer_arrays(section: dict, circle: tuple[float, ...], n: int) -> dict:
    s = slices_of(section, circle, n)
    _, c, phi = mc_params(section)
    ru = section["pore_pressure_ratio"]
    w, cos_a, sin_a = s["W"], s["cos"], s["sin"]
    length = s["b"] / cos_a
    a_i = c * length + (w * cos_a - ru * w / cos_a) * math.tan(math.radians(phi))
    return {"alpha": np.arcsin(sin_a), "W": w, "sin": sin_a, "A": a_i, "tanphi": math.tan(math.radians(phi))}


def _factor(
    arr: dict, theta: float, kind: str, f0: float = 1.0, tol: float = 1e-13, max_iter: int = 500
) -> float | None:
    """Fixed-point solution of F = sum(A k / den) / sum(W sin k / den), den = F cos(a + th) + sin(a + th) tan(phi);
    k = 1 for the force factor (sum dQ = 0) and cos(a + th) for the moment factor (sum dQ cos(a + th) = 0)."""
    ang = arr["alpha"] + theta
    k = np.ones_like(ang) if kind == "force" else np.cos(ang)
    f = f0
    for _ in range(max_iter):
        den = f * np.cos(ang) + np.sin(ang) * arr["tanphi"]
        if np.any(den <= 0.0):
            return None
        top = float((arr["A"] * k / den).sum())
        bottom = float((arr["W"] * arr["sin"] * k / den).sum())
        if bottom == 0.0:
            return None
        f_new = top / bottom
        if not math.isfinite(f_new) or f_new <= 0.0:
            return None
        if abs(f_new - f) <= tol * max(1.0, abs(f)):
            return f_new
        f = f_new
    return None


def spencer_moment_factor(section: dict, circle: tuple[float, ...], theta_deg: float, n: int) -> float | None:
    return _factor(_spencer_arrays(section, circle, n), math.radians(theta_deg), "moment")


def spencer_force_factor(section: dict, circle: tuple[float, ...], theta_deg: float, n: int) -> float | None:
    return _factor(_spencer_arrays(section, circle, n), math.radians(theta_deg), "force")


def spencer_one(section: dict, circle: tuple[float, ...], n: int) -> tuple[float, float] | None:
    """Spencer's F and interslice angle (degrees) on one circle, or None when no theta equalises the two factors.

    Per slice (sliding direction +x, a > 0 where the base descends in +x), with d the unit vector along the base and
    q the interslice direction at angle theta, equilibrium along and normal to the base gives
        S = W sin a + dQ cos(a + theta),   N' = W cos a - u l - dQ sin(a + theta),   S = (c' l + N' tan phi) / F
    hence dQ = [A - F W sin a] / [F cos(a + theta) + sin(a + theta) tan phi], A = c' l + (W cos a - u l) tan phi.
    Force equilibrium of the whole mass (no thrust at the ends) is sum(dQ) = 0; moment equilibrium about the centre,
    where base normals and pore forces have no arm and interslice pairs cancel, is sum(S) = sum(W sin a), i.e.
    sum(dQ cos(a + theta)) = 0.  The two factors coincide at the solution theta.
    """
    arr = _spencer_arrays(section, circle, n)
    thetas = np.radians(np.linspace(-80.0, 80.0, 321))
    diff = []
    for th in thetas:
        ff, fm = _factor(arr, th, "force"), _factor(arr, th, "moment")
        diff.append(np.nan if ff is None or fm is None else ff - fm)
    diff_a = np.asarray(diff)
    idx = [
        i
        for i in range(len(thetas) - 1)
        if np.isfinite(diff_a[i]) and np.isfinite(diff_a[i + 1]) and diff_a[i] * diff_a[i + 1] <= 0
    ]
    if not idx:
        return None
    # the root nearest to theta = 0 (the physically meaningful one for slopes)
    i = min(idx, key=lambda j: abs(thetas[j]))
    lo, hi = thetas[i], thetas[i + 1]
    f_lo = diff_a[i]
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        ff, fm = _factor(arr, mid, "force"), _factor(arr, mid, "moment")
        if ff is None or fm is None:
            return None
        d = ff - fm
        if d * f_lo <= 0:
            hi = mid
        else:
            lo, f_lo = mid, d
    th = 0.5 * (lo + hi)
    fm = _factor(arr, th, "moment")
    return None if fm is None else (fm, math.degrees(th))


def lowest_bishop(section: dict, count: int, n: int) -> tuple[np.ndarray, list[tuple[float, ...]]]:
    circles, f = grid_bishop(section, n)
    order = np.argsort(np.where(np.isnan(f), np.inf, f))[:count]
    return f[order], [tuple(float(a[i]) for a in circles) for i in order]


def spencer_search_min(section: dict, count: int, n: int) -> float:
    """Minimum Spencer F over the `count` lowest-Bishop circles (live mode: count = 64)."""
    _, circles = lowest_bishop(section, count, n)
    vals = [r[0] for c in circles if (r := spencer_one(section, c, n)) is not None]
    return min(vals)


# ----------------------------------------------------------------------------------------------------------------------
# Hoek-Brown (Hoek and Brown 2018) and Balmer (1952)


def hb_parameters(gsi: float, m_i: float, d: float) -> tuple[float, float, float]:
    m_b = m_i * math.exp((gsi - 100.0) / (28.0 - 14.0 * d))
    s = math.exp((gsi - 100.0) / (9.0 - 3.0 * d))
    a = 0.5 + (math.exp(-gsi / 15.0) - math.exp(-20.0 / 3.0)) / 6.0
    return m_b, s, a


def balmer(sigma3: float, gsi: float, m_i: float, sigma_ci: float, d: float) -> dict[str, float]:
    """Stresses in MPa; k = d sigma1 / d sigma3; envelope tangent at the contact point of the Mohr circle."""
    m_b, s, a = hb_parameters(gsi, m_i, d)
    t = m_b * sigma3 / sigma_ci + s
    s1 = sigma3 + sigma_ci * t**a
    k = 1.0 + a * m_b * t ** (a - 1.0)
    sn = (s1 + k * sigma3) / (k + 1.0)
    tau = (s1 - sigma3) * math.sqrt(k) / (k + 1.0)
    sin_phi = (k - 1.0) / (k + 1.0)
    phi = math.asin(sin_phi)
    return {
        "sigma1": s1,
        "sigma_n": sn,
        "tau": tau,
        "phi_deg": math.degrees(phi),
        "c": tau - sn * math.tan(phi),
        "c_closed_form": (s1 - k * sigma3) / (2.0 * math.sqrt(k)),
    }


def hb_to_mc(sigma_n_kpa: float, gsi: float, m_i: float, sigma_ci_mpa: float, d: float) -> tuple[float, float]:
    """(c' kPa, phi' deg) of the instantaneous Mohr-Coulomb line at the effective normal stress sigma_n (kPa)."""
    target = sigma_n_kpa / 1000.0
    lo, hi = 0.0, 1.0
    while balmer(hi, gsi, m_i, sigma_ci_mpa, d)["sigma_n"] < target:
        hi *= 2.0
        if hi > 1e6:
            break
    if balmer(lo, gsi, m_i, sigma_ci_mpa, d)["sigma_n"] >= target:
        point = balmer(lo, gsi, m_i, sigma_ci_mpa, d)
    else:
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if balmer(mid, gsi, m_i, sigma_ci_mpa, d)["sigma_n"] < target:
                lo = mid
            else:
                hi = mid
        point = balmer(0.5 * (lo + hi), gsi, m_i, sigma_ci_mpa, d)
    return point["c"] * 1000.0, point["phi_deg"]


def bishop_hb_one(
    section: dict, circle: tuple[float, ...], n: int, *, tol: float = 1e-12, max_iter: int = 200, details: bool = False
) -> float | tuple[float, float, int]:
    """Bishop F on one circle for a Hoek-Brown material: c', phi' re-evaluated at the slice-base normal stress
    N'/l (N' from vertical equilibrium, N' = [W - u b - c' b tan a / F] / m_a) at every fixed-point iteration.
    With details=True returns (F, smallest m_alpha at the solution, number of iterations)."""
    mat = section["materials"][0]
    ru = section["pore_pressure_ratio"]
    s = slices_of(section, circle, n)
    w, b, sin_a, cos_a, tan_a = s["W"], s["b"], s["sin"], s["cos"], s["tan"]
    length = b / cos_a
    drive = float((w * sin_a).sum())
    f = 1.0
    sn = w * cos_a / length  # first guess of the base normal stress (kPa): the slice weight resolved on the base
    c_i = np.zeros(n)
    phi_i = np.zeros(n)
    for iteration in range(1, max_iter + 1):
        for i in range(n):
            c_i[i], phi_i[i] = hb_to_mc(float(sn[i]), mat["gsi"], mat["m_i"], mat["sigma_ci_mpa"], mat["disturbance_d"])
        tanphi = np.tan(np.radians(phi_i))
        m = cos_a * (1.0 + tan_a * tanphi / f)
        f_new = float(((c_i * b + w * (1.0 - ru) * tanphi) / m).sum() / drive)
        n_eff = (w * (1.0 - ru) - c_i * b * tan_a / f_new) / (cos_a * (1.0 + tan_a * tanphi / f_new))
        sn = np.maximum(n_eff / length, 0.0)
        if abs(f_new - f) <= tol:
            if details:
                return f_new, float((cos_a * (1.0 + tan_a * tanphi / f_new)).min()), iteration
            return f_new
        f = f_new
    raise RuntimeError("reference did not converge")


# ----------------------------------------------------------------------------------------------------------------------
# Wilson interval (Wilson 1927; z = 1.96)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    denom = 1 + z * z / n
    return (centre - half) / denom, (centre + half) / denom
