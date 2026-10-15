"""Generalised Hoek-Brown strength and its instantaneous Mohr-Coulomb pair (FR-010-02), numpy only.

Hoek, Carranza-Torres and Corkum (2002) and Hoek and Brown (2018) form of the criterion
    sigma1 = sigma3 + sigma_ci (m_b sigma3 / sigma_ci + s)^a,
    m_b = m_i exp((GSI - 100) / (28 - 14 D)), s = exp((GSI - 100) / (9 - 3 D)),
    a = 1/2 + (exp(-GSI / 15) - exp(-20 / 3)) / 6,
and Balmer's (1952) parametric form of the normal and shear stress on the envelope,
    k = d sigma1 / d sigma3, sigma_n = (sigma1 + k sigma3) / (k + 1), tau = (sigma1 - sigma3) sqrt(k) / (k + 1),
whose tangent line at the contact point is the Mohr-Coulomb pair
    sin phi' = (k - 1) / (k + 1), c' = (sigma1 - k sigma3) / (2 sqrt(k)).
The pair is found from the normal stress by solving sigma_n(sigma3) = target. sigma_n is increasing in sigma3 and
sigma_n >= sigma3 (sigma1 >= sigma3), so the root lies in [0, target]; a bracketed Newton iteration finds it to machine
precision.
All functions broadcast over numpy arrays; scalar arguments give scalars. Stresses in MPa except where a name says kPa.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

_E_A = math.exp(-20.0 / 3.0)


def hoek_brown_parameters(gsi: Any, m_i: Any, d: Any) -> tuple[Any, Any, Any]:
    """(m_b, s, a) of the generalised criterion (Hoek and Brown 2018)."""
    gsi, m_i, d = np.asarray(gsi, dtype=float), np.asarray(m_i, dtype=float), np.asarray(d, dtype=float)
    m_b = m_i * np.exp((gsi - 100.0) / (28.0 - 14.0 * d))
    s = np.exp((gsi - 100.0) / (9.0 - 3.0 * d))
    a = 0.5 + (np.exp(-gsi / 15.0) - _E_A) / 6.0
    return _out(m_b), _out(s), _out(a)


def hoek_brown_sigma1(sigma3_mpa: Any, gsi: Any, m_i: Any, sigma_ci_mpa: Any, d: Any) -> Any:
    """Major principal stress at failure (MPa) for the confining stress ``sigma3_mpa``."""
    m_b, s, a = hoek_brown_parameters(gsi, m_i, d)
    s3 = np.asarray(sigma3_mpa, dtype=float)
    sci = np.asarray(sigma_ci_mpa, dtype=float)
    return _out(s3 + sci * (m_b * s3 / sci + s) ** a)


def _out(x: Any) -> Any:
    return float(x) if np.ndim(x) == 0 else x


def _balmer(s3: np.ndarray, m_b: Any, s: Any, a: Any, sci: Any) -> tuple[np.ndarray, ...]:
    """(sigma1, k, sigma_n, d sigma_n / d sigma3) at the confining stress ``s3``."""
    t = m_b * s3 / sci + s
    s1 = s3 + sci * t**a
    k = 1.0 + a * m_b * t ** (a - 1.0)
    dk = a * (a - 1.0) * m_b * (m_b / sci) * t ** (a - 2.0)
    sn = (s1 + k * s3) / (k + 1.0)
    dsn = (2.0 * k * (k + 1.0) + dk * (s3 - s1)) / (k + 1.0) ** 2
    return s1, k, sn, dsn


def hoek_brown_to_mohr_coulomb(gsi: Any, m_i: Any, sigma_ci_mpa: Any, d: Any, sigma_n_kpa: Any) -> tuple[Any, Any]:
    """Instantaneous (c' kPa, phi' deg) of the envelope at the effective normal stress ``sigma_n_kpa`` (kPa)."""
    scalar = all(np.ndim(v) == 0 for v in (gsi, m_i, sigma_ci_mpa, d, sigma_n_kpa))
    gsi, m_i, sci, d, sn_kpa = np.broadcast_arrays(
        *(np.asarray(v, dtype=float) for v in (gsi, m_i, sigma_ci_mpa, d, sigma_n_kpa))
    )
    m_b, s, a = hoek_brown_parameters(gsi, m_i, d)
    target = np.maximum(sn_kpa, 0.0) / 1000.0
    _, _, sn0, _ = _balmer(np.zeros_like(target), m_b, s, a, sci)
    at_zero = sn0 >= target
    lo, hi = np.zeros_like(target), target.copy()
    x = 0.5 * target
    for _ in range(100):
        _, _, sn, dsn = _balmer(x, m_b, s, a, sci)
        f = sn - target
        lo = np.where(f < 0.0, x, lo)
        hi = np.where(f > 0.0, x, hi)
        with np.errstate(all="ignore"):
            step = x - f / dsn
        bad = ~np.isfinite(step) | (step <= lo) | (step >= hi)
        new = np.where(bad, 0.5 * (lo + hi), step)
        done = np.abs(new - x) <= 1e-15 * np.maximum(target, 1e-300) + 1e-300
        x = new
        if bool(np.all(done)):
            break
    s3 = np.where(at_zero, 0.0, x)
    s1, k, _, _ = _balmer(s3, m_b, s, a, sci)
    phi = np.degrees(np.arcsin((k - 1.0) / (k + 1.0)))
    c = (s1 - k * s3) / (2.0 * np.sqrt(k)) * 1000.0
    c = np.maximum(c, 0.0)
    return (float(c), float(phi)) if scalar else (c, phi)
