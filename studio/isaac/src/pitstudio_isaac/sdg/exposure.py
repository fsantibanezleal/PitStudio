"""Exposure and fog of the `st55_sdg` renderer: RTX settings as pure functions of a table row (FR-009-02, FR-009-05).

Measured on Isaac Sim 6.1 (probes of 2026-11-22, report sdg-exposure-2026-11-22):

- the setting `/rtx/fog/fogDensity` that the renderer used until then does not exist: the transmittance was the default
  fog's whatever the dust extinction. The simple fog is `/rtx/fog/fogDistanceDensity` with the height fog off
  (`fogHeightDensity` 0): its density is the extinction sigma in 1/km, and the plane colour at 100, 300 and 1000 m
  blends towards the fog colour by T = exp(-sigma * d) (linear tonemapper, 8-bit sRGB decoded; measured / modelled):
  sigma 0.75 per km 0.939/0.928, 0.815/0.799, 0.473/0.472; sigma 3 0.741/0.741, 0.413/0.407, 0.034/0.050; sigma 12
  0.290/0.301, 0.013/0.027 at 100, 300, 1000 m. Wherever T is at least 0.1 the error is below 4 percent; below 0.1 the
  8-bit floor dominates (such a frame is haze-limited by definition);
- the histogram auto exposure (`/rtx/post/histogram/enabled`) is off by default and made a frame depend on the frames
  before it when switched on (mean luminance differences of 5 to 69 levels between the same row rendered after two
  different predecessors), so the exposure is the film ISO of the tonemapper, set per row and never adapted;
- `/rtx/post/tonemap/exposure/compensation` has no effect while the auto exposure is off; `filmIso` scales the image
  linearly in radiance.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

FOG_COLOUR = (0.55, 0.49, 0.40)  # the dust colour of the scene
FOG_COLOUR_INTENSITY = 0.25  # in-scattered radiance of the fog colour; the fog also carries the dome's ambient light
FOG_END_DISTANCE_M = 5000.0  # the simple fog's end distance does not change the transmittance (measured with 100 km)
FILM_ISO = {"structured": 100.0, "unstructured": 100.0}
TONEMAP_OP = 6  # the renderer's default tonemapper
DOME_FILL_GAIN = 1000.0  # the nominal dome reached the pit terrain about 1000 times weaker than the sun (probes)


def fog_settings(sigma_per_km: float) -> dict[str, Any]:
    """RTX fog settings of a dust extinction in 1/km: Beer-Lambert transmittance exp(-sigma * d); none for no dust."""
    if sigma_per_km < 0.0:
        raise ValueError(f"the dust extinction cannot be negative ({sigma_per_km})")
    if sigma_per_km == 0.0:
        return {"/rtx/fog/enabled": False}
    return {
        "/rtx/fog/enabled": True,
        "/rtx/fog/fogColor": list(FOG_COLOUR),
        "/rtx/fog/fogColorIntensity": FOG_COLOUR_INTENSITY,
        "/rtx/fog/fogHeightDensity": 0.0,
        "/rtx/fog/fogStartDist": 0.0,
        "/rtx/fog/fogEndDist": FOG_END_DISTANCE_M,
        "/rtx/fog/fogDistanceDensity": float(sigma_per_km),
    }


def transmittance_of(settings: Mapping[str, Any], distance_m: float) -> float:
    """Transmittance the fog settings give at a distance (1 when the fog is off): the model the fog check verifies."""
    if not settings.get("/rtx/fog/enabled", False):
        return 1.0
    return math.exp(-float(settings["/rtx/fog/fogDistanceDensity"]) * distance_m / 1000.0)


def render_settings(row: Mapping[str, Any]) -> dict[str, Any]:
    """Every RTX exposure and fog setting of a row: a function of the row only, never of the frames rendered before."""
    sigma = float(row["dr"]["dust_extinction_per_km"]) if row["arm"] == "structured" else 0.0
    return {
        "/rtx/post/histogram/enabled": False,
        "/rtx/post/tonemap/op": TONEMAP_OP,
        "/rtx/post/tonemap/filmIso": FILM_ISO[row["arm"]],
        **fog_settings(sigma),
    }


def describe() -> dict[str, Any]:
    """The render-settings model, recorded in `run.json` (ADR-0039: never in the DC-009-01 record)."""
    return {
        "auto_exposure": False,
        "film_iso": dict(FILM_ISO),
        "tonemap_op": TONEMAP_OP,
        "dome_fill_gain": DOME_FILL_GAIN,
        "fog": {
            "setting": "/rtx/fog/fogDistanceDensity",
            "density_per_km_equals_sigma": True,
            "height_density": 0.0,
            "colour": list(FOG_COLOUR),
            "colour_intensity": FOG_COLOUR_INTENSITY,
        },
    }
