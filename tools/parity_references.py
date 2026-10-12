"""Reference runs of the parity fixtures (spec 018 section 7.1, T-018-005): `make_parity_fixtures.py generate`.

Each engine of the engine table that has a Python reference gets a generator here. A generator draws a seeded set of
input vectors (both ends of the validity ranges), calls the reference, and writes DC-018-04 fixtures with SHA-256 pins.
The reference is `minephys`; point `PITSTUDIO_MINEPHYS_SRC` at a `src` directory that holds the package when it is not
installed complete (it needs only numpy and PyYAML). Engines whose reference lives in another spec (DES, haulage, LP,
routing, twins) have no generator: asking for one is reported, never faked.
"""

from __future__ import annotations

import importlib
import math
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_parity_fixtures as mpf

SEED = 20261012
ANALYTICAL = {"class": "analytical-closed-form", "rtol": 1e-9, "atol_scale": 1e-12}
ITERATIVE = {"class": "analytical-iterative", "rtol": 1e-9, "atol_scale": 1e-12, "solver_tol": 1e-12}
N_VECTORS = 220


def minephys() -> Any:
    """The reference package (from `PITSTUDIO_MINEPHYS_SRC` when set)."""
    src = os.environ.get("PITSTUDIO_MINEPHYS_SRC")
    if src:
        sys.path.insert(0, src)
    import minephys as mp

    return mp


def reference(mp: Any, callable_path: str) -> dict[str, str]:
    version = "0.0.0"
    src = os.environ.get("PITSTUDIO_MINEPHYS_SRC")
    if src and (Path(src).parent / "VERSION").is_file():
        version = (Path(src).parent / "VERSION").read_text(encoding="utf-8").strip()
    return {"name": "minephys", "version": version, "callable": callable_path}


def _f(x: Any) -> float:
    return float(x)


def _slices(rng: np.random.Generator, n: int, pore_max: float) -> list[dict[str, float]]:
    """A slice set with a positive driving moment: a dominant steep slice is always present."""
    out = []
    for _ in range(n):
        w = rng.uniform(1e4, 5e6)
        b = rng.uniform(0.5, 10.0)
        out.append(
            {
                "width_m": round(_f(b), 6),
                "weight_n_per_m": round(_f(w), 3),
                "base_angle_rad": round(_f(rng.uniform(-0.15, 0.95)), 9),
                "pore_pressure_pa": round(_f(rng.uniform(0, pore_max) * w / b), 3),
            }
        )
    out.append({"width_m": 4.0, "weight_n_per_m": 6e6, "base_angle_rad": 0.8, "pore_pressure_pa": 0.0})
    return out


def _arrays(slices: list[dict[str, float]]) -> tuple[list[float], list[float], list[float], list[float]]:
    return (
        [s["width_m"] for s in slices],
        [s["weight_n_per_m"] for s in slices],
        [s["base_angle_rad"] for s in slices],
        [s["pore_pressure_pa"] for s in slices],
    )


def _iterations(run: Callable[[int], Any], hi: int = 200) -> int:
    """Smallest max_iter for which the reference converges: the iteration count of a deterministic solver."""
    lo = 1
    while lo < hi:
        mid = (lo + hi) // 2
        try:
            run(mid)
            hi = mid
        except Exception:
            lo = mid + 1
    return lo


def _stable_count(run: Callable[[int, float], Any], k: int) -> bool:
    """The iteration count must not move when the tolerance moves by 0.1 %, so another summation order agrees."""
    for tol in (1e-12 * 0.999, 1e-12 * 1.001):
        try:
            if _iterations(lambda m, tol=tol: run(m, tol)) != k:
                return False
        except Exception:
            return False
    return True


def _geotech_strength(rng: np.random.Generator, i: int) -> tuple[float, float]:
    # the first vectors pin both ends of the validity ranges
    corner = [(0.0, 0.0), (0.0, math.pi / 3), (1e5, 0.0), (1e5, math.pi / 3), (5e3, 0.4363323129985824)]
    if i < len(corner):
        return corner[i]
    return round(_f(rng.uniform(0, 8e4)), 3), round(_f(rng.uniform(0, math.pi / 3)), 9)


def gen_geotech(root: Path) -> list[Path]:
    mp = minephys()
    g = importlib.import_module("minephys.geotech")
    rng = np.random.default_rng(SEED)
    written: list[Path] = []

    for method, ref_name, cls in (
        ("bishop", "bishop_simplified_fos", ITERATIVE),
        ("spencer", "spencer_fos", ITERATIVE),
    ):
        cases: list[dict[str, Any]] = []
        i = 0
        while len(cases) < N_VECTORS:
            slices = _slices(rng, int(rng.integers(1 if method == "bishop" else 2, 24)), 0.3)
            c, phi = _geotech_strength(rng, i)
            i += 1
            width, weight, alpha, u = _arrays(slices)
            fn = getattr(g, ref_name)
            try:
                result = fn(width, weight, alpha, u, c, phi)
            except Exception:
                continue
            fos = result if method == "bishop" else result[0]
            if not (0 < float(fos) < 1e6):
                continue
            args = (width, weight, alpha, u, c, phi)

            def run(m: int, tol: float = 1e-12, fn: Callable[..., Any] = fn, args: tuple[Any, ...] = args) -> Any:
                return fn(*args, tol=tol, max_iter=m)

            iterations = _iterations(run)
            if not _stable_count(run, iterations):
                continue  # the count sits on the stopping criterion: rounding alone could change it
            out: dict[str, Any] = {"fos": _f(fos), "iterations": iterations}
            if method == "spencer":
                out["theta_rad"] = _f(result[1])
            cases.append(
                {
                    "name": f"v{len(cases)}",
                    "input": {"slices": slices, "cohesion_pa": c, "friction_angle_rad": phi},
                    "output": out,
                }
            )
        doc = mpf.build_fixture("geotech", method, method, reference(mp, f"minephys.geotech.{ref_name}"), cls, cases)
        written.append(mpf.write_fixture(root, doc, gzip=True))

    cases = []
    while len(cases) < N_VECTORS:
        n = int(rng.integers(3, 40))
        tf = _f(rng.uniform(1e6, 5e7))
        amp = _f(rng.uniform(5, 100))
        times = np.sort(rng.uniform(0, 0.9 * tf, n))
        times = np.unique(np.round(times, 3))
        if times.size < 3:
            continue
        noise = rng.normal(0, rng.choice([0.0, 0.02, 0.1, 0.5]), times.size)
        # decelerating records are part of the validity range (no failure time)
        decel = rng.random() < 0.15
        inv_v = amp * (tf - times) * (1 + noise) if not decel else 1e4 + 50 * times
        v = 1.0 / np.maximum(inv_v, 1.0)
        v = np.minimum(v, 0.01)
        if np.any(v <= 0):
            continue
        record = [{"t_s": _f(t), "velocity_m_per_s": _f(x)} for t, x in zip(times, v, strict=True)]
        window = int(rng.integers(3, times.size + 1)) if times.size > 3 and rng.random() < 0.3 else None
        try:
            r = g.inverse_velocity_ttf(times, v, window)
        except Exception:
            continue
        out = {
            "accelerating": bool(r.accelerating),
            "slope_per_m": _f(r.slope),
            "intercept_s_per_m": _f(r.intercept),
            "r_squared": min(1.0, _f(r.r_squared)),  # rounding can give 1 + 4e-16; the contract caps at 1
            "n_used": int(r.n_used),
        }
        if r.accelerating:
            if not -1e12 <= _f(r.failure_time) <= 1e12:
                continue
            out["failure_time_s"] = _f(r.failure_time)
        args: dict[str, Any] = {"record": record}
        if window is not None:
            args["window"] = window
        cases.append({"name": f"v{len(cases)}", "input": args, "output": out})
    doc = mpf.build_fixture(
        "geotech",
        "inverse_velocity",
        "inverse-velocity",
        reference(mp, "minephys.geotech.inverse_velocity_ttf"),
        ANALYTICAL,
        cases,
    )
    written.append(mpf.write_fixture(root, doc, gzip=True))

    cases = []
    while len(cases) < N_VECTORS:
        pixels = int(rng.integers(1, 9))
        radar = [round(_f(x), 3) for x in rng.uniform(-3000, 3000, 3)]
        targets = rng.uniform(-3000, 3000, (pixels, 3))
        if np.any(np.abs(targets - np.array(radar)).max(axis=1) < 1.0):
            continue
        disp = rng.uniform(-0.5, 0.5, (pixels, 3))
        los = g.slope_radar_los(disp, np.array(radar), targets)
        cases.append(
            {
                "name": f"v{len(cases)}",
                "input": {
                    "radar_position_m": radar,
                    "targets_m": [_f(x) for x in targets.reshape(-1)],
                    "displacements_m": [_f(x) for x in disp.reshape(-1)],
                },
                "output": {"los_m": [_f(x) for x in np.atleast_1d(los)]},
            }
        )
    doc = mpf.build_fixture(
        "geotech",
        "slope_radar_los",
        "slope-radar-los",
        reference(mp, "minephys.geotech.slope_radar_los"),
        ANALYTICAL,
        cases,
    )
    written.append(mpf.write_fixture(root, doc, gzip=True))

    cases = []
    for k in range(8):
        method = "bishop" if k < 6 else "spencer"
        n_samples = 400 if method == "bishop" else 60
        surfaces = [_slices(rng, int(rng.integers(2, 10)), 0.1) for _ in range(int(rng.integers(1, 4)))]
        entropy = int(rng.integers(1, 2**40))
        spawn_key = [k]
        stream = np.random.Generator(np.random.PCG64(np.random.SeedSequence(entropy, spawn_key=spawn_key)))
        c_mean = _f(rng.uniform(3e3, 3e4))
        samples = np.column_stack(
            [
                np.clip(stream.normal(c_mean, 0.3 * c_mean, n_samples), 0, 1e8),
                np.clip(stream.normal(0.45, 0.08, n_samples), 0, math.pi / 3),
            ]
        )
        samples = np.round(samples, 6)
        failures = 0
        for c, phi in samples:
            fails = False
            for sl in surfaces:
                width, weight, alpha, u = _arrays(sl)
                fn = g.bishop_simplified_fos if method == "bishop" else g.spencer_fos
                f = fn(width, weight, alpha, u, float(c), float(phi))
                f = f if method == "bishop" else f[0]
                if f < 1:
                    fails = True
                    break
            failures += int(fails)
        z2 = 1.96 * 1.96
        p = failures / n_samples
        denom = 1 + z2 / n_samples
        centre = (p + z2 / (2 * n_samples)) / denom
        half = 1.96 * math.sqrt(p * (1 - p) / n_samples + z2 / (4 * n_samples**2)) / denom
        cases.append(
            {
                "name": f"v{k}",
                "input": {
                    "surfaces": surfaces,
                    "method": method,
                    "samples": [{"cohesion_pa": _f(c), "friction_angle_rad": _f(phi)} for c, phi in samples],
                },
                "output": {
                    "n_samples": n_samples,
                    "failures": failures,
                    "pof": p,
                    "wilson_low": max(0.0, centre - half),
                    "wilson_high": min(1.0, centre + half),
                },
                "variates": {
                    "generator": "pcg64",
                    "entropy": str(entropy),
                    "spawn_key": spawn_key,
                    "samples": [[_f(c), _f(phi)] for c, phi in samples],
                },
            }
        )
    doc = mpf.build_fixture(
        "geotech",
        "pof_from_samples",
        "pof-from-samples",
        reference(mp, "minephys.geotech.bishop_simplified_fos"),
        {"class": "monte-carlo-count"},
        cases,
    )
    written.append(mpf.write_fixture(root, doc, gzip=True))
    return written


def gen_plume(root: Path) -> list[Path]:
    mp = minephys()
    env = importlib.import_module("minephys.environment")
    rng = np.random.default_rng(SEED + 1)
    written: list[Path] = []
    classes = list("ABCDEF")

    cases: list[dict[str, Any]] = []
    sizes = ["PM2.5", "PM10", "PM30"]
    corners = [(0.018, 1814.36948), (0.252, 263083.5746), (0.018, 263083.5746), (0.252, 1814.36948)]
    for i in range(N_VECTORS):
        silt, weight = corners[i % 4] if i < 12 else (rng.uniform(0.018, 0.252), rng.uniform(1814.36948, 263083.5746))
        size = sizes[i % 3]
        e = env.ap42_unpaved_emission_factor(float(silt), float(weight), size)
        cases.append(
            {
                "name": f"v{i}",
                "input": {"silt_fraction": _f(silt), "mean_weight_kg": _f(weight), "size_class": size},
                "output": {"emission_factor_kg_per_m": _f(e)},
            }
        )
    doc = mpf.build_fixture(
        "plume",
        "ap42_emission_factor",
        "ap42-emission-factor",
        reference(mp, "minephys.environment.ap42_unpaved_emission_factor"),
        ANALYTICAL,
        cases,
    )
    written.append(mpf.write_fixture(root, doc, gzip=True))

    cases = []
    while len(cases) < N_VECTORS:
        x = _f(10 ** rng.uniform(0, 5))
        cls = classes[len(cases) % 6]
        terrain = "rural" if rng.random() < 0.6 else "urban"
        sy, sz = env.pasquill_sigmas(x, cls, terrain)
        if not (0 < _f(sz) <= 5000 and _f(sy) > 0):
            continue
        cases.append(
            {
                "name": f"v{len(cases)}",
                "input": {"downwind_distance_m": x, "stability_class": cls, "terrain": terrain},
                "output": {"sigma_y_m": _f(sy), "sigma_z_m": _f(sz)},
            }
        )
    doc = mpf.build_fixture(
        "plume",
        "pasquill_sigmas",
        "pasquill-sigmas",
        reference(mp, "minephys.environment.pasquill_sigmas"),
        ANALYTICAL,
        cases,
    )
    written.append(mpf.write_fixture(root, doc, gzip=True))

    cases = []
    while len(cases) < N_VECTORS:
        nx, ny = int(rng.integers(1, 7)), int(rng.integers(1, 7))
        cls = classes[len(cases) % 6]
        terrain = "rural" if rng.random() < 0.5 else "urban"
        args: dict[str, Any] = {
            "source_strength_kg_per_s": round(_f(rng.uniform(0, 5)), 6),
            "wind_speed_m_per_s": round(_f(rng.uniform(0.5, 15)), 6),
            "stability_class": cls,
            "terrain": terrain,
            "release_height_m": round(_f(rng.uniform(0, 80)), 6),
            "x_start_m": round(_f(rng.uniform(100, 3000)), 6),
            "x_step_m": round(_f(rng.uniform(10, 1500)), 6),
            "nx": nx,
            "y_start_m": round(_f(rng.uniform(-300, 0)), 6),
            "y_step_m": round(_f(rng.uniform(5, 150)), 6),
            "ny": ny,
            "receptor_height_m": round(_f(rng.uniform(0, 30)), 6),
        }
        if rng.random() < 0.4:
            args["mixing_height_m"] = round(_f(rng.uniform(20, 3000)), 6)
        x = args["x_start_m"] + args["x_step_m"] * np.arange(nx)
        y = (args["y_start_m"] + args["y_step_m"] * np.arange(ny))[:, None]
        sy, sz = env.pasquill_sigmas(x, cls, terrain)
        grid = env.gaussian_plume(
            args["source_strength_kg_per_s"],
            args["wind_speed_m_per_s"],
            y,
            args["receptor_height_m"],
            args["release_height_m"],
            sy,
            sz,
            args.get("mixing_height_m"),
        )
        grid = np.asarray(grid, dtype=np.float64).reshape(ny, nx)
        if not np.all(np.isfinite(grid)):
            continue
        k = int(np.argmax(grid))
        iy, ix = divmod(k, nx)
        cases.append(
            {
                "name": f"v{len(cases)}",
                "input": args,
                "output": {
                    "concentration_kg_per_m3": [_f(v) for v in grid.reshape(-1)],
                    "max_concentration_kg_per_m3": _f(grid.reshape(-1)[k]),
                    "max_x_m": _f(x[ix]),
                    "max_y_m": _f(y[iy, 0]),
                },
            }
        )
    doc = mpf.build_fixture(
        "plume",
        "plume_grid",
        "plume-grid",
        reference(mp, "minephys.environment.gaussian_plume"),
        ANALYTICAL,
        cases,
    )
    written.append(mpf.write_fixture(root, doc, gzip=True))
    return written


GENERATORS: dict[str, Callable[[Path], list[Path]]] = {
    "geotech": gen_geotech,
    "plume": gen_plume,
}


def generate(root: Path, engines: list[str] | None) -> int:
    wanted = engines or sorted(GENERATORS)
    status = 0
    for engine in wanted:
        gen = GENERATORS.get(engine)
        if gen is None:
            print(
                f"{engine}: no Python reference generator in this repository (the reference belongs to another spec)",
                file=sys.stderr,
            )
            status = 1
            continue
        for path in gen(root):
            print(f"wrote {path}")
    problems = mpf.check_fixtures(root, engines=[e for e in wanted if e in GENERATORS])
    for p in problems:
        print(p, file=sys.stderr)
        status = 1
    return status
