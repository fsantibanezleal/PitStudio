"""FNO input builder (FR-011-33, FR-011-40): the normalisation rules of DC-011-02, applied channel by channel.

`build_fno_input(fields, io)` stacks the named fields in the channel order of the model's description and applies each
channel's
rule when the graph does not (`applied_in_graph` false): none; standardise (x - mean) / std; log-standardise (ln x -
mean) / std;
patch-relief (x - patch mean) / patch relief, the relief being the range (max - min) of the patch. A scalar fills its
whole channel.
Anything that is not a clean [64, 64] field of finite numbers raises `InvalidFieldInputError` and nothing is built.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from pitstudio_pipeline.surrogates.errors import InvalidFieldInputError

GRID = 64


def wind_direction_channels(direction_deg: float) -> tuple[float, float]:
    """(cos, sin) of the wind direction angle, in degrees, as the dust model's two constant channels."""
    angle = math.radians(direction_deg)
    return math.cos(angle), math.sin(angle)


def _field(name: str, value: Any) -> np.ndarray:
    if isinstance(value, bool):
        raise InvalidFieldInputError(f"{name}: a boolean is not a field value")
    if np.isscalar(value) or (isinstance(value, np.ndarray) and value.ndim == 0):
        arr = np.full((GRID, GRID), float(value), dtype=np.float64)
    else:
        arr = np.asarray(value, dtype=np.float64)
        if arr.shape != (GRID, GRID):
            raise InvalidFieldInputError(f"{name}: a field must have shape [{GRID}, {GRID}], got {list(arr.shape)}")
    if not np.isfinite(arr).all():
        raise InvalidFieldInputError(f"{name}: the field contains a non-finite value")
    return arr


def build_fno_input(fields: Mapping[str, Any], io: Mapping[str, Any]) -> np.ndarray:
    """The network input [1, C_in, 64, 64] float32 for `fields` under the description `io` of an FNO."""
    channels = io["inputs"][0]["channels"]
    names = [c["name"] for c in channels]
    missing = [n for n in names if n not in fields]
    extra = [k for k in fields if k not in names]
    if missing or extra:
        raise InvalidFieldInputError(f"channels do not match the model: missing {missing}, unexpected {extra}")
    planes = []
    for channel in channels:
        name = channel["name"]
        arr = _field(name, fields[name])
        rule = channel.get("normalisation", {"rule": "none", "applied_in_graph": False})
        if not rule.get("applied_in_graph", False):
            arr = _normalise(name, arr, rule)
        planes.append(arr)
    return np.stack(planes)[None].astype(np.float32)


def _normalise(name: str, arr: np.ndarray, rule: Mapping[str, Any]) -> np.ndarray:
    kind = rule["rule"]
    if kind == "none":
        return arr
    if kind == "standardise":
        return (arr - rule["mean"][0]) / rule["std"][0]
    if kind == "log-standardise":
        if not (arr > 0).all():
            raise InvalidFieldInputError(f"{name}: log-standardise needs strictly positive values")
        return (np.log(arr) - rule["mean"][0]) / rule["std"][0]
    if kind == "patch-relief":
        relief = float(arr.max() - arr.min())
        if relief <= 0.0:
            raise InvalidFieldInputError(f"{name}: the patch relief is zero (a flat patch has no relief to scale by)")
        return (arr - arr.mean()) / relief
    raise InvalidFieldInputError(f"{name}: unsupported normalisation rule {kind!r}")
