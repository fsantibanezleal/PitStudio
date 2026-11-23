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

Measured on an open grey plane (albedo 0.18, 3,000 m above the scene, probe job 8a of 2026-11-23, report
sdg-finish-2026-11-23, ISO 100, f/16, 1/100 s, linear radiance of the 8-bit sRGB decoded centre crop):

- the plane radiance is linear in the intensity of the sun and of the dome (decades 1e3 to 1e5: 0.00566, 0.0567, 0.572
  for the sun at 45 degrees; 0.00783, 0.0779, 0.776 for the dome; doubling the intensity gives 2.04 and 2.00 times);
- per unit of sun intensity and sine of the elevation 7.97e-6 (elevations 30 to 75 degrees within 1.5 percent, 15
  degrees 19 percent lower); per unit of dome intensity 7.78e-6 whatever the elevation (within 1.3 percent);
- the p90 of the terrain pixels (linear luminance, the sunlit ground the sky is matched to) of the 96 gate frames with
  the sun at or above 30 degrees: median 0.373 (25 structured frames) and 0.183 per unit of the light factor (19
  unstructured frames), that is 0.0037 and 0.0018 in units of ISO 1; below 30 degrees the ground falls with the sine of
  the elevation while the sky colour stays constant (the locked sky tests ask for that), so the sky to ground ratio
  of low-sun frames is above 1;
- the fog colour is not scaled by the film ISO: an intensity of 0.001 (the 0.25 of ISO 0.4 scaled to ISO 100) turned the
  infinite-depth sky of 3 of 96 gate frames black, 0.25 left none black;
- the film ISO, the shutter rate (cameraShutter, 1/s) and the f-number act as the photographic law says: ISO 200
  doubles, a shutter of 1/200 s halves and f/8 quadruples the plane radiance (2.00, 0.50 and 4.00 times).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

FOG_COLOUR = (0.55, 0.49, 0.40)  # the dust colour of the scene
FOG_COLOUR_INTENSITY = 0.25  # fog colour radiance, not scaled by the film ISO (0.001 left 3 of 96 dusty skies black)
FOG_END_DISTANCE_M = 5000.0  # the simple fog's end distance does not change the transmittance (measured with 100 km)
FILM_ISO = {"structured": 100.0, "unstructured": 100.0}  # sunny 16: ISO 100 at f/16 and 1/100 s
FILM_SHUTTER_S = 0.01  # the shutter time is the reciprocal of the ISO at f/16 (sunny 16)
F_NUMBER = 16.0
TONEMAP_OP = 6  # the renderer's default tonemapper
SUN_TO_SKY_ILLUMINANCE = 6.0  # direct sun over the whole clear sky on a horizontal surface: 120,000 lux over 20,000 lux
LIGHT_CITATION = (
    "direct sunlight at noon 120,000 lux and shade lit by the whole clear sky at midday 20,000 lux, "
    "https://en.wikipedia.org/wiki/Daylight (ratio 6); sunny 16: shutter time 1/ISO at f/16, "
    "https://en.wikipedia.org/wiki/Sunny_16_rule"
)
PLANE_RADIANCE_PER_SUN_UNIT = 7.97e-6  # linear radiance of the open grey plane per unit of sun intensity at the zenith
PLANE_RADIANCE_PER_DOME_UNIT = 7.78e-6  # the same per unit of dome intensity (independent of the sun elevation)
SKY_LUMINANCE_RATIO = 1.0  # sky to sunlit ground luminance, inside the 0.6 to 1.6 of a clear day (module docstring)
SKY_TINT = (0.75, 0.88, 1.20)  # a clear sky is bluer than neutral; scaled so that its Rec. 709 luminance is 1
STRUCTURED_GROUND_RADIANCE = (
    0.0037  # sunlit ground radiance in units of ISO 1, structured arm (median p90 0.373 at ISO 100)
)
UNSTRUCTURED_GROUND_RADIANCE = (
    0.0018  # the same per unit of the light factor, unstructured arm (median p90 0.183 at ISO 100)
)
RT_SUBFRAMES = 8  # real-time subframes per capture: the smallest count of the probe grid under the history limit
HISTORY_LIMIT_LEVELS = 2.0  # a row after different predecessors keeps its mean luminance within this many levels
HISTORY_MEASURED_LEVELS = {8: 1.56, 16: 0.96, 32: 0.66, 64: 0.47}  # `aa/op` none, max over the 6 history rows (job 88f)
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


def dome_intensity_for(sun_intensity: float, elevation_deg: float) -> float:
    """Dome intensity that puts the horizontal sun to sky illuminance at the cited ratio for this sun.

    The sun lights a horizontal plane with its intensity times the sine of the elevation, the dome independent of the
    elevation, so the dome follows the sun: sun * sin(el) * k_sun = ratio * dome * k_dome.
    """
    sine = math.sin(math.radians(elevation_deg))
    return sun_intensity * sine * PLANE_RADIANCE_PER_SUN_UNIT / (SUN_TO_SKY_ILLUMINANCE * PLANE_RADIANCE_PER_DOME_UNIT)


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


def history_settings() -> dict[str, Any]:
    """The temporal history of the renderer, set on every row so that no row inherits what an earlier row left.

    `/rtx/post/aa/op` is an enum of the tokens none, taa, fxaa, dlss, rtxaa; 0 is none (the default is dlss, whose
    feedback from prior frames made a frame depend on the one before it).
    """
    return {"/rtx/post/aa/op": 0}


def render_settings(row: Mapping[str, Any]) -> dict[str, Any]:
    """Every RTX exposure, fog and sky setting of a row: a function of the row only, never of the frames before it."""
    sigma = float(row["dr"]["dust_extinction_per_km"]) if row["arm"] == "structured" else 0.0
    return {
        "/rtx/post/histogram/enabled": False,
        "/rtx/post/tonemap/op": TONEMAP_OP,
        "/rtx/post/tonemap/filmIso": FILM_ISO[row["arm"]],
        "/rtx/post/tonemap/cameraShutter": 1.0 / FILM_SHUTTER_S,
        "/rtx/post/tonemap/fNumber": F_NUMBER,
        **fog_settings(sigma),
        **sky_settings(row),
        **history_settings(),
    }


def describe() -> dict[str, Any]:
    """The render-settings model, recorded in `run.json` (ADR-0039: never in the DC-009-01 record)."""
    return {
        "auto_exposure": False,
        "film_iso": dict(FILM_ISO),
        "tonemap_op": TONEMAP_OP,
        "exposure": {"f_number": F_NUMBER, "shutter_s": FILM_SHUTTER_S},
        "light": {
            "sun_to_sky_illuminance": SUN_TO_SKY_ILLUMINANCE,
            "citation": LIGHT_CITATION,
            "plane_radiance_per_sun_unit": PLANE_RADIANCE_PER_SUN_UNIT,
            "plane_radiance_per_dome_unit": PLANE_RADIANCE_PER_DOME_UNIT,
        },
        "history": {
            "settings": history_settings(),
            "rt_subframes": RT_SUBFRAMES,
            "max_mean_diff_levels": HISTORY_MEASURED_LEVELS[RT_SUBFRAMES],
            "limit_levels": HISTORY_LIMIT_LEVELS,
        },
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
