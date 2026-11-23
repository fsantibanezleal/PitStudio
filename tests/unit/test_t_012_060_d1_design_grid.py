"""T-012-060: the D1 design grid from `minephys.blasting`; hostile design inputs (unit, metamorphic).

Requirements: FR-012-41, FR-012-46, DC-012-05.

Spec: specs/012-fragmentation/spec.md
- FR-012-41: the D1 design grid (DC-012-05: x50, x80, % oversize, PPV and flyrock radius over the recipe's design inputs)
  is computed by calling `minephys.blasting`, with no re-implementation of those models in PitStudio, and records the
  `minephys` version;
- FR-012-46: a design-grid input that is non-finite, non-positive where a positive quantity is required, or rejected by
  `minephys.blasting` stops the grid builder with the input name and writes no grid.
plan.md test strategy row FR-012-41: reference implementation, `minephys.blasting` called directly on the grid (exact
float64 equality); FR-012-46: hand calculation (burden NaN, spacing 0, an input `minephys.blasting` rejects: no grid).

Oracles:
- the spec's own valid example (`d1-design-grid.valid.json`: x50 0.2994063 and 0.33870247 m, PPV 0.00599072 m/s, flyrock
  163.15459 m for the stated inputs, written when the contract was drafted);
- hand calculations: Kuznetsov x50 = A K^-0.8 Q^(1/6) (115 / RWS)^e cm with Q = rho_e pi d^2 L / 4 and K = Q / (B S H);
  PPV = K_site (D / sqrt(W))^-beta; the drag-free range v^2 / g at 45 degrees; the Rosin-Rammler size at 80 % passing
  x50 (ln 5 / ln 2)^(1 / n) and its oversize 100 exp(-ln 2 (x_l / x50)^n);
- the direct `minephys.blasting` calls written out in the test (exact equality);
- metamorphic: x50 grows with the burden and with the rock factor; PPV does not depend on the burden.

Expected public API (module `pitstudio.cases.d1.design_grid`, numpy + `minephys` + the standard library):
    INPUT_RANGES: dict[str, tuple[float, float, bool, bool]]   # (low, high, low_open, high_open) per design input
    LAUNCH_ANGLE_RAD = pi / 4                                   # the flyrock radius is the range at 45 degrees
    build_design_grid(fixed, axes, *, kuzram_variant="cunningham2005", distribution="kco-swebrec") -> dict
        axes: mapping input name -> sequence of values (1 to 4 axes, 1 to 64 distinct values, at most 4096 points);
        the document of DC-012-05 (case_id "D1"), computed point by point; ValueError naming the input and no document
        for a hostile input;
    write_design_grid(path, fixed, axes, **kw) -> dict          # builds first, writes the JSON only after success
    minephys_identity() -> str                                  # the pinned minephys version string
"""

from __future__ import annotations

import ast
import itertools
import json
import math
import warnings
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from minephys import blasting
from pitstudio.cases.d1 import design_grid as dg

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts" / "d1-design-grid.schema.json").read_text("utf-8"))
EXAMPLE = json.loads((ROOT / "specs/012-fragmentation/contracts/examples/d1-design-grid.valid.json").read_text("utf-8"))
G = 9.80665

FIXED = EXAMPLE["fixed_inputs"]
AXES = {"burden_m": [6.0, 7.0]}


def _build(fixed=None, axes=None, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the 1983 exponent is an UNVERIFIED knowledge row and says so
        return dg.build_design_grid(fixed or FIXED, axes or AXES, **kw)


def _direct(inputs: dict, variant: str = "cunningham1983") -> dict:
    """The five outputs by direct `minephys.blasting` calls (the reference implementation of the plan)."""
    i = inputs
    q = blasting.charge_per_hole(i["explosive_density_kg_per_m3"], i["hole_diameter_m"], i["charge_length_m"])
    k = blasting.powder_factor(q, i["burden_m"], i["spacing_m"], i["bench_height_m"])
    x50 = blasting.kuznetsov_x50(i["rock_factor"], k, q, i["rws"], variant)
    n = blasting.uniformity_index(
        i["burden_m"], i["spacing_m"], i["hole_diameter_m"], i["drilling_deviation_m"], i["charge_length_m"], i["bench_height_m"]
    )
    b = blasting.kco_undulation(n, x50, i["x_max_m"])
    return {
        "x50_m": float(x50),
        "x80_m": float(blasting.swebrec_size(0.8, x50, i["x_max_m"], b)),
        "oversize_pct": float(100.0 * (1.0 - blasting.swebrec_passing(i["oversize_limit_m"], x50, i["x_max_m"], b))),
        "ppv_m_per_s": float(
            blasting.ppv_scaled_distance(i["distance_m"], i["charge_per_delay_kg"], i["k_site_m_per_s"], i["beta"])
        ),
        "flyrock_radius_m": float(
            blasting.flyrock_trajectory(
                i["launch_speed_m_per_s"],
                math.pi / 4,
                i["fragment_diameter_m"],
                i["rock_density_kg_per_m3"],
                i["drag_coefficient"],
                i["air_density_kg_per_m3"],
            ).range
        ),
    }


@pytest.mark.req("FR-012-41")
def test_the_spec_example_is_reproduced_for_its_inputs() -> None:
    doc = _build(kuzram_variant="cunningham1983")
    assert len(doc["points"]) == len(EXAMPLE["points"]) == 2
    for got, want in zip(doc["points"], EXAMPLE["points"], strict=True):
        assert got["inputs"] == want["inputs"]
        for key in ("x50_m", "x80_m", "oversize_pct", "ppv_m_per_s", "flyrock_radius_m"):
            assert got[key] == pytest.approx(want[key], rel=2e-6), key


@pytest.mark.req("FR-012-41")
def test_every_grid_point_equals_the_direct_minephys_blasting_calls_exactly() -> None:
    axes = {"burden_m": [5.0, 6.0, 7.5], "spacing_m": [6.0, 8.0], "charge_length_m": [6.0, 7.2]}
    doc = _build(axes=axes, kuzram_variant="cunningham2005")
    combos = list(itertools.product(*axes.values()))
    assert len(doc["points"]) == len(combos) == 12
    for point, combo in zip(doc["points"], combos, strict=True):
        inputs = {**FIXED, **dict(zip(axes, combo, strict=True))}
        assert point["inputs"] == dict(zip(axes, combo, strict=True))
        want = _direct(inputs, "cunningham2005")
        for key, value in want.items():
            assert point[key] == value, (combo, key)  # exact float64 equality


@pytest.mark.req("FR-012-41")
def test_the_outputs_equal_their_hand_calculations() -> None:
    doc = _build(kuzram_variant="cunningham2005")
    f = FIXED
    point = doc["points"][0]  # burden 6 m
    q = f["explosive_density_kg_per_m3"] * math.pi / 4 * f["hole_diameter_m"] ** 2 * f["charge_length_m"]
    k = q / (6.0 * f["spacing_m"] * f["bench_height_m"])
    x50 = f["rock_factor"] * k**-0.8 * q ** (1 / 6) * (115.0 / f["rws"]) ** (19 / 20) / 100.0
    assert point["x50_m"] == pytest.approx(x50, rel=1e-12)
    assert point["ppv_m_per_s"] == pytest.approx(
        f["k_site_m_per_s"] * (f["distance_m"] / math.sqrt(f["charge_per_delay_kg"])) ** -f["beta"], rel=1e-12
    )
    assert point["flyrock_radius_m"] == pytest.approx(f["launch_speed_m_per_s"] ** 2 / G, rel=1e-5)  # drag-free, 45 deg
    assert 0.0 < point["oversize_pct"] < 100.0
    assert point["x80_m"] > point["x50_m"]


@pytest.mark.req("FR-012-41")
def test_the_rosin_rammler_distribution_gives_its_closed_form_x80_and_oversize() -> None:
    doc = _build(kuzram_variant="cunningham2005", distribution="rosin-rammler")
    assert doc["distribution"] == "rosin-rammler"
    f = FIXED
    point = doc["points"][0]
    n = float(
        blasting.uniformity_index(
            6.0, f["spacing_m"], f["hole_diameter_m"], f["drilling_deviation_m"], f["charge_length_m"], f["bench_height_m"]
        )
    )
    x50 = point["x50_m"]
    assert point["x80_m"] == pytest.approx(x50 * (math.log(5.0) / math.log(2.0)) ** (1.0 / n), rel=1e-12)
    expected = 100.0 * math.exp(-math.log(2.0) * (f["oversize_limit_m"] / x50) ** n)
    assert point["oversize_pct"] == pytest.approx(expected, rel=1e-9)


@pytest.mark.req("FR-012-41")
def test_the_document_validates_against_dc_012_05_and_records_the_producer_facts() -> None:
    doc = _build(axes={"burden_m": [6.0, 7.0], "spacing_m": [6.0, 7.0, 8.0]}, kuzram_variant="cunningham2005")
    assert list(Draft202012Validator(SCHEMA).iter_errors(doc)) == []
    assert doc["case_id"] == "D1"
    assert doc["kuzram_variant"] == "cunningham2005"
    assert doc["distribution"] == "kco-swebrec"
    assert doc["units"] == EXAMPLE["units"]
    assert doc["minephys_version"] == dg.minephys_identity()
    assert [a["input"] for a in doc["axes"]] == ["burden_m", "spacing_m"]
    assert set(doc["fixed_inputs"]) == set(FIXED) - {"spacing_m"}  # spacing is swept here


@pytest.mark.req("FR-012-41")
def test_the_swept_inputs_are_not_in_the_fixed_inputs_of_the_document() -> None:
    fixed = {**FIXED, "burden_m": 5.0}  # a fixed value that an axis overrides
    doc = _build(fixed=fixed, axes={"burden_m": [6.0]})
    assert "burden_m" not in doc["fixed_inputs"]
    assert doc["points"][0]["inputs"] == {"burden_m": 6.0}


@pytest.mark.req("FR-012-41")
def test_the_ranges_of_the_builder_are_the_ranges_of_the_schema() -> None:
    props = SCHEMA["$defs"]["design_inputs"]["properties"]
    assert set(dg.INPUT_RANGES) == set(props)
    for name, (lo, hi, lo_open, hi_open) in dg.INPUT_RANGES.items():
        spec = props[name]
        assert hi == spec["maximum"], name
        assert (lo, lo_open) == ((spec["exclusiveMinimum"], True) if "exclusiveMinimum" in spec else (spec["minimum"], False)), name
        assert hi_open is False


@pytest.mark.req("FR-012-41")
def test_the_builder_calls_minephys_and_defines_no_blasting_model_of_its_own() -> None:
    source = (ROOT / "src" / "pitstudio" / "cases" / "d1" / "design_grid.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots = {
        (a.name if isinstance(n, ast.Import) else n.module).split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom) and getattr(n, "module", "x") is not None
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    assert roots <= {"minephys", "numpy", "math", "json", "itertools", "pathlib", "importlib", "os", "collections", "typing", "__future__", "dataclasses"}
    assert "minephys" in roots
    for node in ast.walk(tree):  # no ** exponent with a model constant, no sqrt of a charge: those are minephys's job
        if isinstance(node, ast.FunctionDef):
            assert node.name not in {"kuznetsov_x50", "swebrec_size", "ppv_scaled_distance", "powder_factor"}


# ----------------------------------------------------------------------------------------------------------------------
# metamorphic
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-012-41")
@settings(max_examples=30, deadline=None)
@given(
    burden=st.floats(4.0, 6.0),
    delta=st.floats(0.1, 1.5),
    rock=st.floats(3.0, 12.0),
    rock_delta=st.floats(0.5, 5.0),
)
def test_x50_grows_with_the_burden_and_the_rock_factor_and_ppv_ignores_the_burden(burden, delta, rock, rock_delta):
    fixed = {**FIXED, "rock_factor": rock}
    doc = _build(fixed=fixed, axes={"burden_m": [burden, burden + delta]}, kuzram_variant="cunningham2005")
    a, b = doc["points"]
    assert b["x50_m"] > a["x50_m"]
    assert a["ppv_m_per_s"] == b["ppv_m_per_s"]
    coarser = _build(fixed={**FIXED, "rock_factor": rock + rock_delta}, axes={"burden_m": [burden]}, kuzram_variant="cunningham2005")
    finer = _build(fixed=fixed, axes={"burden_m": [burden]}, kuzram_variant="cunningham2005")
    assert coarser["points"][0]["x50_m"] > finer["points"][0]["x50_m"]


# ----------------------------------------------------------------------------------------------------------------------
# FR-012-46: hostile inputs
# ----------------------------------------------------------------------------------------------------------------------

HOSTILE = [
    ("burden_nan", {"burden_m": [float("nan")]}, {}, "burden_m"),
    ("burden_inf", {"burden_m": [float("inf")]}, {}, "burden_m"),
    ("burden_zero", {"burden_m": [0.0]}, {}, "burden_m"),
    ("burden_negative", {"burden_m": [-6.0]}, {}, "burden_m"),
    ("spacing_zero", {"burden_m": [6.0]}, {"spacing_m": 0.0}, "spacing_m"),
    ("spacing_nan_axis", {"spacing_m": [float("nan"), 7.0]}, {"burden_m": 6.0}, "spacing_m"),
    ("diameter_in_mm", {"burden_m": [6.0]}, {"hole_diameter_m": 250.0}, "hole_diameter_m"),
    ("rock_factor_out_of_range", {"burden_m": [6.0]}, {"rock_factor": 40.0}, "rock_factor"),
    ("deviation_not_below_burden", {"burden_m": [0.25]}, {"drilling_deviation_m": 0.3}, "drilling_deviation_m"),
    ("burden_too_large_for_the_hole", {"burden_m": [20.0]}, {"hole_diameter_m": 0.05}, "burden_m"),
    ("xmax_below_x50", {"burden_m": [6.0]}, {"x_max_m": 0.01}, "x_max_m"),
    ("distance_zero", {"burden_m": [6.0]}, {"distance_m": 0.0}, "distance_m"),
    ("drag_negative", {"burden_m": [6.0]}, {"drag_coefficient": -0.1}, "drag_coefficient"),
]


@pytest.mark.req("FR-012-46")
@pytest.mark.parametrize(("label", "axes", "override", "name"), HOSTILE, ids=[h[0] for h in HOSTILE])
def test_a_hostile_input_stops_the_builder_with_its_name_and_writes_nothing(tmp_path, label, axes, override, name):
    fixed = {k: v for k, v in {**FIXED, **override}.items() if k not in axes}
    target = tmp_path / "grid.json"
    with pytest.raises(ValueError, match=name):
        _build(fixed=fixed, axes=axes)
    with pytest.raises(ValueError, match=name), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dg.write_design_grid(target, fixed, axes)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.req("FR-012-46")
def test_a_missing_or_unknown_input_and_a_bad_axis_shape_are_refused_naming_the_cause() -> None:
    fixed = {k: v for k, v in FIXED.items() if k != "rws"}
    with pytest.raises(ValueError, match="rws"):
        _build(fixed=fixed)
    with pytest.raises(ValueError, match="bogus_m"):
        _build(fixed={**FIXED, "bogus_m": 1.0})
    with pytest.raises(ValueError, match="bogus_m"):
        _build(axes={"bogus_m": [1.0]})
    with pytest.raises(ValueError, match="axes"):
        dg.build_design_grid(FIXED, {})
    with pytest.raises(ValueError, match="burden_m"):
        _build(axes={"burden_m": [6.0, 6.0]})  # duplicate values
    with pytest.raises(ValueError, match="burden_m"):
        _build(axes={"burden_m": [4.0 + 0.01 * i for i in range(65)]})  # more than 64 values
    with pytest.raises(ValueError, match="axes"):
        _build(
            fixed={k: v for k, v in FIXED.items() if k not in ("spacing_m", "bench_height_m", "charge_length_m", "rock_factor", "rws")},
            axes={"burden_m": [6.0], "spacing_m": [7.0], "bench_height_m": [12.0], "charge_length_m": [7.2], "rock_factor": [7.0], "rws": [100.0]},
        )
    with pytest.raises(ValueError, match="distribution"):
        _build(distribution="lognormal")
    with pytest.raises(ValueError, match="kuzram_variant"):
        _build(kuzram_variant="cunningham1999")


@pytest.mark.req("FR-012-46")
def test_more_than_4096_points_are_refused() -> None:
    axes = {
        "burden_m": [4.0 + 0.1 * i for i in range(20)],
        "spacing_m": [5.0 + 0.1 * i for i in range(20)],
        "charge_length_m": [5.0 + 0.1 * i for i in range(11)],
    }
    with pytest.raises(ValueError, match="4096"):
        _build(axes=axes)


@pytest.mark.req("FR-012-41")
def test_a_written_grid_reads_back_equal_and_is_deterministic(tmp_path) -> None:
    path = tmp_path / "grid.json"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc = dg.write_design_grid(path, FIXED, {"burden_m": [6.0, 7.0]})
        again = dg.build_design_grid(FIXED, {"burden_m": [6.0, 7.0]})
    assert json.loads(path.read_text("utf-8")) == doc == again
