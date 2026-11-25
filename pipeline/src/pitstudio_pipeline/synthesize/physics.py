"""Reference physics of the CPU synthetic generators (FR-008-32).

The companion package `minephys` is the home of these models (`minephys.blasting`, `.geotech`, `.environment`,
`.comminution`). At the locked revision it ships none of them (its `__init__` exports nothing), so the textbook
formulas live here, each with its citation, until `minephys` provides them; the generators call only the functions of
this module. Every function is deterministic: the stochastic part of a generator is a `numpy.random.Generator` seeded
by the caller.

Sources (formulas as published; the page numbers of the cards' priors are written by the card author, not here):
- Kuz-Ram: Cunningham, C.V.B. (1983), "The Kuz-Ram model for prediction of fragmentation from blasting", Proc. 1st Int.
  Symp. on Rock Fragmentation by Blasting, Lulea; Cunningham (1987), "Fragmentation estimations and the Kuz-Ram model -
  four years on", 2nd Int. Symp. on Rock Fragmentation by Blasting, Keystone.
- Swebrec function: Ouchterlony, F. (2005), "The Swebrec function: linking fragmentation by blasting and crushing",
  Trans. IMM Section A 114(1):29-44.
- Voight relation: Voight, B. (1989), "A relation to describe rate-dependent material failure", Science 243:200-203.
- Gaussian plume with Briggs open-country, neutral (class D) dispersion: Briggs, G.A. (1973), "Diffusion estimation for
  small emissions", ATDL Contribution File 79.
- Bond's third theory of comminution: Bond, F.C. (1952), "The third theory of comminution", Trans. AIME 193:484-494.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


# ------------------------------------------------------------------------------------------------------- blasting
def kuz_ram_x50_cm(
    burden_m: float, spacing_m: float, bench_m: float, charge_kg: float, rock_factor: float, rws: float
) -> float:
    """Kuznetsov mean fragment size X50 (cm): X50 = A (V/Q)^0.8 Q^(1/6) (E/115)^(-19/30), V = B S H per hole (m3)."""
    volume = burden_m * spacing_m * bench_m
    return rock_factor * (volume / charge_kg) ** 0.8 * charge_kg ** (1 / 6) * (rws / 115.0) ** (-19.0 / 30.0)


def kuz_ram_n(
    burden_m: float,
    spacing_m: float,
    diameter_mm: float,
    drill_sd_m: float,
    bottom_charge_m: float,
    column_charge_m: float,
    bench_m: float,
) -> float:
    """Cunningham's uniformity index n = (2.2 - 14 B/D) sqrt((1 + S/B)/2) (1 - W/B) (|BCL - CCL|/L + 0.1)^0.1 (L/H)."""
    total = bottom_charge_m + column_charge_m
    return (
        (2.2 - 14.0 * burden_m / diameter_mm)
        * math.sqrt((1.0 + spacing_m / burden_m) / 2.0)
        * (1.0 - drill_sd_m / burden_m)
        * (abs(bottom_charge_m - column_charge_m) / total + 0.1) ** 0.1
        * (total / bench_m)
    )


def rosin_rammler_passing(x_cm: np.ndarray, x50_cm: float, n: float) -> np.ndarray:
    """Cumulative fraction passing size x of the Rosin-Rammler distribution through X50: 1 - exp(-ln2 (x/X50)^n)."""
    return 1.0 - np.exp(-math.log(2.0) * (x_cm / x50_cm) ** n)


def swebrec_passing(x_cm: np.ndarray, x50_cm: float, x_max_cm: float, b: float) -> np.ndarray:
    """Swebrec function F(x) = 1 / (1 + [ln(xmax/x) / ln(xmax/x50)]^b) for 0 < x < xmax, 1 at xmax and above."""
    out = np.ones_like(x_cm, dtype=float)
    inside = x_cm < x_max_cm
    ratio = np.log(x_max_cm / x_cm[inside]) / math.log(x_max_cm / x50_cm)
    out[inside] = 1.0 / (1.0 + ratio**b)
    return out


# --------------------------------------------------------------------------------------------------------- geotech
def voight_displacement(t: np.ndarray, alpha: float, a: float, t_failure: float, x0: float = 0.0) -> np.ndarray:
    """Displacement of the Voight relation d2x/dt2 = A (dx/dt)^alpha from rest-free start, failing at `t_failure`.

    The velocity is v(t) = [A (alpha - 1) (tf - t)]^(-1/(alpha - 1)) for alpha > 1 and the displacement its integral
    from t = 0 (x(0) = x0); alpha = 2 integrates to a logarithm.
    """
    if alpha <= 1.0 or a <= 0.0 or t_failure <= 0.0 or np.any(t >= t_failure):
        raise ValueError("the Voight relation needs alpha > 1, A > 0 and every sample before the failure time")
    k = (a * (alpha - 1.0)) ** (-1.0 / (alpha - 1.0))
    if math.isclose(alpha, 2.0):
        return x0 + k * np.log(t_failure / (t_failure - t))
    p = (alpha - 2.0) / (alpha - 1.0)
    return x0 + (k / p) * (t_failure**p - (t_failure - t) ** p)


# ----------------------------------------------------------------------------------------------------- environment
def briggs_sigma_class_d(x_m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Briggs open-country, neutral: sigma_y = 0.08 x (1 + 1e-4 x)^-1/2, sigma_z = 0.06 x (1 + 1.5e-3 x)^-1/2."""
    return 0.08 * x_m / np.sqrt(1.0 + 1e-4 * x_m), 0.06 * x_m / np.sqrt(1.0 + 1.5e-3 * x_m)


def plume_ground_concentration(
    x_m: np.ndarray, y_m: np.ndarray, emission_g_s: float, wind_m_s: float, release_height_m: float
) -> np.ndarray:
    """Ground-level concentration (g/m3) of a continuous point source: Q / (pi u sy sz) exp(-y^2/2sy^2) exp(-H^2/2sz^2).

    `x_m` (downwind, > 0) and `y_m` (crosswind) are meshed; the ground reflection doubles the plume-centre term.
    """
    xx, yy = np.meshgrid(x_m, y_m, indexing="ij")
    sy, sz = briggs_sigma_class_d(xx)
    return (
        emission_g_s
        / (math.pi * wind_m_s * sy * sz)
        * np.exp(-(yy**2) / (2.0 * sy**2))
        * np.exp(-(release_height_m**2) / (2.0 * sz**2))
    )


# ---------------------------------------------------------------------------------------------------- comminution
def bond_energy_kwh_t(work_index_kwh_t: float, p80_um: float, f80_um: float) -> float:
    """Bond's law: W = 10 Wi (1/sqrt(P80) - 1/sqrt(F80)) in kWh per tonne, sizes in micrometres."""
    return 10.0 * work_index_kwh_t * (1.0 / math.sqrt(p80_um) - 1.0 / math.sqrt(f80_um))


def default_blast() -> dict[str, Any]:
    """A typical open-pit blast pattern used when the configuration names none (metric units, ANFO = 100 RWS)."""
    return {
        "burden_m": 4.5,
        "spacing_m": 5.5,
        "bench_m": 12.0,
        "diameter_mm": 229.0,
        "charge_kg": 340.0,
        "rock_factor": 8.0,
        "rws": 100.0,
        "drill_sd_m": 0.3,
        "bottom_charge_m": 4.0,
        "column_charge_m": 5.0,
        "swebrec_b": 2.0,
    }
