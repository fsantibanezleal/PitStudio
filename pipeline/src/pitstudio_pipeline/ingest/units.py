"""Unit conversions, applied after validation and never inside a schema (FR-008-25, FR-008-46).

Each factor is a definition, not a measurement: the international foot is 0.3048 m exactly (1959), a millimetre is a
thousandth of a metre, 1 km/h is 1/3.6 m/s, and the US liquid gallon is 231 cubic inches, 3.785411784 L exactly. The
combined pair ft <-> mm is the composition ft <-> m <-> mm, so that composing conversions never drifts (P-008-11).
"""

from __future__ import annotations

import math
from collections.abc import Callable

from pitstudio_pipeline.errors import UnitError

FT_TO_M = 0.3048
MM_PER_M = 1000.0
KMH_PER_MS = 3.6
L_PER_GAL = 3.785411784

_CONVERSIONS: dict[tuple[str, str], Callable[[float], float]] = {
    ("ft", "m"): lambda x: x * FT_TO_M,
    ("m", "ft"): lambda x: x / FT_TO_M,
    ("mm", "m"): lambda x: x / MM_PER_M,
    ("m", "mm"): lambda x: x * MM_PER_M,
    ("ft", "mm"): lambda x: (x * FT_TO_M) * MM_PER_M,
    ("mm", "ft"): lambda x: (x / MM_PER_M) / FT_TO_M,
    ("km/h", "m/s"): lambda x: x / KMH_PER_MS,
    ("m/s", "km/h"): lambda x: x * KMH_PER_MS,
    ("gal", "L"): lambda x: x * L_PER_GAL,
    ("L", "gal"): lambda x: x / L_PER_GAL,
}


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """`value` expressed in `to_unit`; `UnitError` for a non-finite value, an unknown pair or an overflowing result."""
    pair = f"{from_unit!r} -> {to_unit!r}"
    try:
        number = float(value)
    except TypeError, ValueError:
        raise UnitError(f"value {value!r} is not a number ({pair})") from None
    if not math.isfinite(number):
        raise UnitError(f"value {number!r} is not finite ({pair})")
    function = _CONVERSIONS.get((from_unit, to_unit))
    if function is None:
        raise UnitError(f"no conversion for the unit pair {pair} (value {number!r})")
    result = function(number)
    if not math.isfinite(result):
        raise UnitError(f"value {number!r} overflows in the conversion {pair}")
    return result
