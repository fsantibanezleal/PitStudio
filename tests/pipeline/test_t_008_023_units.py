# ruff: noqa: E501, PT018
"""T-008-023: definition-exact unit conversions after validation, their three metamorphic relations, `UnitError`.

Requirements: FR-008-25, FR-008-46, P-008-11.

Spec: specs/008-data-pipeline/spec.md FR-008-25 (ft -> m x 0.3048 exact by definition; mm -> m / 1,000; km/h -> m/s / 3.6;
US gallon -> L x 3.785411784; never inside a schema), FR-008-46 (non-finite value or unknown unit pair raises `UnitError`
naming the value and the pair; never NaN or Infinity), P-008-11 (round trip, composition and linearity within 1 ulp for finite
float64 in [-1e9, 1e9]).

Oracle: the definition constants written out in the test (the international foot is 0.3048 m exactly, 1959; the US liquid
gallon is 231 cubic inches = 3.785411784 L exactly; 1 km/h = 1/3.6 m/s), hand values (1 ft = 0.3048 m, 1000 mm = 1 m,
3.6 km/h = 1 m/s, 1 gal = 3.785411784 L) and the metamorphic relations of P-008-11 with `math.ulp` as the measure.

Expected API of the implementation: `pitstudio_pipeline.ingest.units.convert(value, from_unit, to_unit) -> float` for the
unit symbols `"ft"`, `"m"`, `"mm"`, `"km/h"`, `"m/s"`, `"gal"` (US liquid gallon) and `"L"`, with the pairs ft<->m, mm<->m,
ft<->mm, km/h<->m/s, gal<->L; `pitstudio_pipeline.errors.UnitError(Exception)` whose message names the value and the unit
pair. A conversion whose result would not be finite (overflow) also raises `UnitError`. `pitstudio_pipeline.ingest.schemas`
holds no conversion constant.
"""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest
from pitstudio_pipeline.errors import UnitError
from pitstudio_pipeline.ingest import schemas, units

# isort: split
from hypothesis import given, settings
from hypothesis import strategies as st

convert = units.convert
PAIRS = [
    ("ft", "m"),
    ("m", "ft"),
    ("mm", "m"),
    ("m", "mm"),
    ("ft", "mm"),
    ("mm", "ft"),
    ("km/h", "m/s"),
    ("m/s", "km/h"),
    ("gal", "L"),
    ("L", "gal"),
]
# P-008-11 domain: finite float64 in [-1e9, 1e9]. Magnitudes below 1e-200 are excluded: there a result falls into the
# subnormal range, where "within 1 ulp" has no meaning (gradual underflow) and no implementation could satisfy it.
finite = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False).filter(
    lambda v: v == 0.0 or abs(v) >= 1e-200
)


def within_ulp(a: float, b: float, n: int = 1) -> bool:
    return abs(a - b) <= n * math.ulp(max(abs(a), abs(b)))


# ------------------------------------------------------------------------------------------------ FR-008-25
@pytest.mark.req("FR-008-25")
@pytest.mark.parametrize(
    ("value", "src", "dst", "expected"),
    [
        (1.0, "ft", "m", 0.3048),
        (0.0, "ft", "m", 0.0),
        (-2.0, "ft", "m", -0.6096),
        (1000.0, "mm", "m", 1.0),
        (1.0, "mm", "m", 0.001),
        (3.6, "km/h", "m/s", 1.0),
        (36.0, "km/h", "m/s", 10.0),
        (1.0, "gal", "L", 3.785411784),
        (0.0, "gal", "L", 0.0),
    ],
)
def test_definition_values(value: float, src: str, dst: str, expected: float) -> None:
    assert within_ulp(convert(value, src, dst), expected)


@pytest.mark.req("FR-008-25")
@settings(max_examples=200, deadline=None)
@given(finite)
def test_each_conversion_is_the_definition_formula_exactly(x: float) -> None:
    assert convert(x, "ft", "m") == x * 0.3048
    assert convert(x, "mm", "m") == x / 1000.0
    assert convert(x, "km/h", "m/s") == x / 3.6
    assert convert(x, "gal", "L") == x * 3.785411784


@pytest.mark.req("FR-008-25")
def test_numpy_scalars_and_python_numbers_are_accepted_and_return_floats() -> None:
    for v in (3, 3.0, np.float64(3.0), np.float32(3.0), np.int64(3)):
        out = convert(v, "ft", "m")
        assert isinstance(out, float | np.floating) and within_ulp(float(out), 0.9144)


@pytest.mark.req("FR-008-25")
def test_the_schema_module_never_converts_units() -> None:
    src = inspect.getsource(schemas)
    for constant in ("0.3048", "3.785411784", "/ 3.6", "/3.6"):
        assert constant not in src, "unit conversions happen after validation, never inside a schema"


# ------------------------------------------------------------------------------------------------ P-008-11
@pytest.mark.req("P-008-11")
@settings(max_examples=300, deadline=None)
@given(finite, st.sampled_from([("ft", "m"), ("mm", "m"), ("km/h", "m/s"), ("gal", "L")]))
def test_round_trip_within_one_ulp(x: float, pair: tuple[str, str]) -> None:
    src, dst = pair
    assert within_ulp(convert(convert(x, src, dst), dst, src), x)


@pytest.mark.req("P-008-11")
@settings(max_examples=300, deadline=None)
@given(finite)
def test_composition_ft_to_m_to_mm_equals_ft_to_mm_within_one_ulp(x: float) -> None:
    assert within_ulp(convert(convert(x, "ft", "m"), "m", "mm"), convert(x, "ft", "mm"))


@pytest.mark.req("P-008-11")
@settings(max_examples=300, deadline=None)
@given(finite, st.sampled_from([2.0**k for k in range(-8, 9)]), st.sampled_from(PAIRS))
def test_linearity_for_powers_of_two(x: float, a: float, pair: tuple[str, str]) -> None:
    src, dst = pair
    assert within_ulp(convert(a * x, src, dst), a * convert(x, src, dst))


# ------------------------------------------------------------------------------------------------ FR-008-46
@pytest.mark.req("FR-008-46")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), np.float64("nan"), np.float32("inf")])
@pytest.mark.parametrize(("src", "dst"), PAIRS)
def test_non_finite_values_raise_unit_error_naming_value_and_pair(bad: float, src: str, dst: str) -> None:
    with pytest.raises(UnitError) as info:
        convert(bad, src, dst)
    msg = str(info.value).lower()
    assert src.lower() in msg and dst.lower() in msg and ("nan" in msg or "inf" in msg)


@pytest.mark.req("FR-008-46")
@pytest.mark.parametrize(
    ("src", "dst"),
    [("ft", "gal"), ("kg", "m"), ("", "m"), ("m", ""), ("ft", "µm☃"), ("km/h", "L"), ("furlong", "m"), ("gal", "m/s")],
)
def test_unknown_unit_pairs_raise_unit_error_naming_the_pair(src: str, dst: str) -> None:
    with pytest.raises(UnitError) as info:
        convert(1.0, src, dst)
    msg = str(info.value)
    assert repr(1.0) in msg or "1.0" in msg
    if src and dst:
        assert src in msg and dst in msg


@pytest.mark.req("FR-008-46")
def test_a_result_that_would_overflow_is_an_error_never_infinity() -> None:
    with pytest.raises(UnitError):
        convert(1.7e308, "ft", "mm")
    with pytest.raises(UnitError):
        convert(1.7e308, "gal", "L")
    assert math.isfinite(convert(1.0e300, "mm", "m"))
