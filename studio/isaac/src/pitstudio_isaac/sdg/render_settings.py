"""Render settings (film ISO, dome fill gain, fog) of the `st55_sdg` renderer (FR-009-02, FR-009-05).

RTX settings as pure functions of a table row.

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

Measured on the carved scene (probes of 2026-11-23, jobs 88a to 88f, report sdg-gate-2026-11-23):

- the film ISO of the buried-geometry calibration (100, cameras under the DEM where the dome fill was blocked)
  left every frame white once the cameras were above the carved surface; the sweep of 24 rows per arm puts the
  frames with more than 25 percent clipped pixels at 0 of 24 (structured) and 1 of 24 (unstructured) at ISO 0.4,
  so the ISO is 0.4 and 0.3;
- the dome seen by camera rays saturated the sky (86.4 percent of the sky pixels at 255).
  `/rtx/background/source/type` (tokens `domeLight`, `backplate`, `color`; carb `/rtx/background/source/type`,
  schema `omni.usd.schema.render_settings.rtx-1.0.3` generatedSchema.usda line 54) set to `color` shows the
  constant `/rtx/background/source/color` (line 82) and leaves the dome as fill light: terrain pixels moved by
  at most 0.21 levels;
- that colour is not scaled by the film ISO but goes through the tonemapper like the scene radiance, so the
  colour displaying the luminance of sunlit ground is the ISO times the ground radiance (units of ISO 1). The
  ground radiance (p90 of the terrain pixels) is about 1.03 times the light factor in the unstructured arm (p10
  0.77, p90 1.37 of 23 rows) and about 0.8 in the structured arm (p10 0.37, p90 1.31 of 24 rows);
- the sky to sunlit ground luminance ratio of a clear day is 0.6 to 1.6 (clear sky 3 to 5 kcd/m2, a scene in
  full sunlight 5 kcd/m2, https://en.wikipedia.org/wiki/Orders_of_magnitude_(luminance), an encyclopedia table,
  no peer-reviewed value read); the constant is 1.0.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

FOG_COLOUR = (0.55, 0.49, 0.40)  # the dust colour of the scene
FOG_COLOUR_INTENSITY = 0.25  # in-scattered radiance of the fog colour; the fog also carries the dome's ambient light
FOG_END_DISTANCE_M = 5000.0  # the simple fog's end distance does not change the transmittance (measured with 100 km)
FILM_ISO = {"structured": 0.4, "unstructured": 0.3}
TONEMAP_OP = 6  # the renderer's default tonemapper
DOME_FILL_GAIN = 1000.0  # the nominal dome reached the pit terrain about 1000 times weaker than the sun (probes)
SKY_LUMINANCE_RATIO = 1.0  # sky to sunlit ground luminance, inside the 0.6 to 1.6 of a clear day (module docstring)
SKY_TINT = (0.75, 0.88, 1.20)  # a clear sky is bluer than neutral; scaled so that its Rec. 709 luminance is 1
STRUCTURED_GROUND_RADIANCE = 0.8  # sunlit ground radiance in units of ISO 1, structured arm
UNSTRUCTURED_GROUND_RADIANCE = 1.03  # the same per unit of the light factor, unstructured arm
_REC709 = (0.2126, 0.7152, 0.0722)


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


def sky_settings(row: Mapping[str, Any]) -> dict[str, Any]:
    """The visible sky of a row: a constant background colour at the luminance of its sunlit ground.

    The dome stays the fill light but camera rays see `/rtx/background/source/color`. The colour is not scaled by the
    film ISO, so it is the ISO times the ground radiance (times the luminance ratio) in the units of the scene radiance.
    """
    if row["arm"] == "structured":
        radiance = STRUCTURED_GROUND_RADIANCE
    else:
        factor = float(row["dr"].get("light_intensity_factor", 1.0))
        if not math.isfinite(factor) or factor <= 0.0:
            raise ValueError(f"the light factor must be positive and finite ({factor})")
        radiance = UNSTRUCTURED_GROUND_RADIANCE * factor
    luminance = SKY_LUMINANCE_RATIO * FILM_ISO[row["arm"]] * radiance
    norm = sum(w * c for w, c in zip(_REC709, SKY_TINT, strict=True))
    return {
        "/rtx/background/source/type": "color",
        "/rtx/background/source/color": [luminance * c / norm for c in SKY_TINT],
    }


def render_settings(row: Mapping[str, Any]) -> dict[str, Any]:
    """Every RTX exposure, fog and sky setting of a row: a function of the row only, never of the frames before it."""
    sigma = float(row["dr"]["dust_extinction_per_km"]) if row["arm"] == "structured" else 0.0
    return {
        "/rtx/post/histogram/enabled": False,
        "/rtx/post/tonemap/op": TONEMAP_OP,
        "/rtx/post/tonemap/filmIso": FILM_ISO[row["arm"]],
        **fog_settings(sigma),
        **sky_settings(row),
    }


def describe() -> dict[str, Any]:
    """The render-settings model, recorded in `run.json` (ADR-0039: never in the DC-009-01 record)."""
    return {
        "auto_exposure": False,
        "film_iso": dict(FILM_ISO),
        "tonemap_op": TONEMAP_OP,
        "dome_fill_gain": DOME_FILL_GAIN,
        "sky": {
            "source": "color",
            "luminance_ratio_to_sunlit_ground": SKY_LUMINANCE_RATIO,
            "tint": list(SKY_TINT),
            "ground_radiance": {
                "structured": STRUCTURED_GROUND_RADIANCE,
                "unstructured_per_light_factor": UNSTRUCTURED_GROUND_RADIANCE,
            },
        },
        "fog": {
            "setting": "/rtx/fog/fogDistanceDensity",
            "density_per_km_equals_sigma": True,
            "height_density": 0.0,
            "colour": list(FOG_COLOUR),
            "colour_intensity": FOG_COLOUR_INTENSITY,
        },
    }
