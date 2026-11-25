"""T-010-014: hostile slope sections are rejected before any analysis.

Requirement: FR-010-07 ("If a section has a non-finite coordinate or parameter, fewer than 2 ground vertices, ... then
the
C1 analysis shall raise `InvalidSectionError` naming the field and its valid range and shall return no FoS").
Spec: specs/010-slope/spec.md section 3.1; plan.md "Interfaces and their hostile-input requirements".

Expected API:
- module `pitstudio.slope.section`: `InvalidSectionError(ValueError)` with `.field` (JSON pointer of the offending
  field, e.g. "/materials/0/cohesion_kpa"), `.valid_range` (non-empty human-readable range or enum) and
  `.error_class == "section-invalid"`; `str(error)` contains the field name and the valid range;
  `parse_section(document: dict) -> Section` validates a DC-010-01 document (schema and the rules of FR-010-07);
  `load_section(path) -> Section` reads a JSON file through the strict loader of `pitstudio.contracts`.
- `pitstudio.slope.lem.analyse_section(document, *, bishop=..., spencer=...)` validates first: for a hostile section it
  raises `InvalidSectionError` and calls neither per-circle solver (nothing is computed, no factor is returned).

Oracle: each case is one invalid class of the spec's list, the expected field and the violated range written in the test
(hand specification, no computation); a valid control per mutation proves the mutation, not the baseline, is rejected.
The ranges are FR-010-07 verbatim: unit weight (0, 40] kN/m3, c' >= 0, phi' in [0, 60] deg, r_u in [0, 1), GSI in
[0, 100], m_i > 0, sigma_ci > 0, D in [0, 1], n_s in [10, 500], at most 1e5 trial circles, methods bishop / spencer,
material models mohr-coulomb / hoek-brown.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as ref
from pitstudio.slope import lem, section

HB = {
    "id": "rock",
    "model": "hoek-brown",
    "unit_weight_kn_per_m3": 26.0,
    "gsi": 55.0,
    "m_i": 12.0,
    "sigma_ci_mpa": 60.0,
    "disturbance_d": 0.3,
}


def _mc() -> dict:
    return ref.planar_section(height_m=20.0, slope_deg=40.0, cohesion=15.0, friction=30.0, ru=0.1, mode="baked")


def _hb() -> dict:
    return ref.planar_section(height_m=40.0, slope_deg=50.0, material=dict(HB), mode="baked")


def _set(doc: dict, path: str, value) -> dict:
    out = copy.deepcopy(doc)
    node = out
    parts = [int(p) if p.lstrip("-").isdigit() else p for p in path.strip("/").split("/")]
    for key in parts[:-1]:
        node = node[key]
    node[parts[-1]] = value
    return out


def _del(doc: dict, path: str) -> dict:
    out = copy.deepcopy(doc)
    node = out
    parts = [int(p) if p.isdigit() else p for p in path.strip("/").split("/")]
    for key in parts[:-1]:
        node = node[key]
    del node[parts[-1]]
    return out


# (id, builder of the hostile document, accepted field prefixes)
NAN, INF = float("nan"), float("inf")
_MC, _HB = _mc, _hb
CASES = [
    # non-finite coordinates and parameters
    ("ground-nan-x", lambda: _set(_MC(), "/ground/1/0", NAN), ("/ground",)),
    ("ground-inf-z", lambda: _set(_MC(), "/ground/0/1", INF), ("/ground",)),
    ("ground-neg-inf-z", lambda: _set(_MC(), "/ground/1/1", -INF), ("/ground",)),
    ("crest-nan", lambda: _set(_MC(), "/crest_x_m", NAN), ("/crest_x_m",)),
    ("toe-inf", lambda: _set(_MC(), "/toe_x_m", INF), ("/toe_x_m",)),
    ("cohesion-nan", lambda: _set(_MC(), "/materials/0/cohesion_kpa", NAN), ("/materials/0/cohesion_kpa",)),
    ("friction-inf", lambda: _set(_MC(), "/materials/0/friction_angle_deg", INF), ("/materials/0/friction_angle_deg",)),
    (
        "unit-weight-nan",
        lambda: _set(_MC(), "/materials/0/unit_weight_kn_per_m3", NAN),
        ("/materials/0/unit_weight_kn_per_m3",),
    ),
    ("ru-nan", lambda: _set(_MC(), "/pore_pressure_ratio", NAN), ("/pore_pressure_ratio",)),
    ("gsi-nan", lambda: _set(_HB(), "/materials/0/gsi", NAN), ("/materials/0/gsi",)),
    # ground polyline
    ("ground-empty", lambda: _set(_MC(), "/ground", []), ("/ground",)),
    ("ground-one-vertex", lambda: _set(_MC(), "/ground", [[0.0, 0.0]]), ("/ground",)),
    ("ground-x-equal", lambda: _set(_MC(), "/ground/1/0", _MC()["ground"][0][0]), ("/ground",)),
    ("ground-x-decreasing", lambda: _set(_MC(), "/ground", list(reversed(_MC()["ground"]))), ("/ground",)),
    # slope height <= 0
    (
        "height-zero",
        lambda: _set(_set(_MC(), "/ground", [[-60.0, 10.0], [100.0, 10.0]]), "/crest_x_m", 0.0),
        ("/crest_x_m", "/toe_x_m", "/ground"),
    ),
    (
        "height-negative",
        lambda: _set(_set(_MC(), "/ground", [[-60.0, 0.0], [100.0, 40.0]]), "/crest_x_m", 0.0),
        ("/crest_x_m", "/toe_x_m", "/ground"),
    ),
    # unit weight
    (
        "gamma-zero",
        lambda: _set(_MC(), "/materials/0/unit_weight_kn_per_m3", 0.0),
        ("/materials/0/unit_weight_kn_per_m3",),
    ),
    (
        "gamma-negative",
        lambda: _set(_MC(), "/materials/0/unit_weight_kn_per_m3", -20.0),
        ("/materials/0/unit_weight_kn_per_m3",),
    ),
    (
        "gamma-above-40",
        lambda: _set(_MC(), "/materials/0/unit_weight_kn_per_m3", 40.001),
        ("/materials/0/unit_weight_kn_per_m3",),
    ),
    # strength
    ("cohesion-negative", lambda: _set(_MC(), "/materials/0/cohesion_kpa", -0.001), ("/materials/0/cohesion_kpa",)),
    (
        "phi-negative",
        lambda: _set(_MC(), "/materials/0/friction_angle_deg", -0.1),
        ("/materials/0/friction_angle_deg",),
    ),
    (
        "phi-above-60",
        lambda: _set(_MC(), "/materials/0/friction_angle_deg", 60.1),
        ("/materials/0/friction_angle_deg",),
    ),
    ("ru-negative", lambda: _set(_MC(), "/pore_pressure_ratio", -0.01), ("/pore_pressure_ratio",)),
    ("ru-one", lambda: _set(_MC(), "/pore_pressure_ratio", 1.0), ("/pore_pressure_ratio",)),
    ("ru-above-one", lambda: _set(_MC(), "/pore_pressure_ratio", 1.5), ("/pore_pressure_ratio",)),
    ("gsi-negative", lambda: _set(_HB(), "/materials/0/gsi", -1.0), ("/materials/0/gsi",)),
    ("gsi-above-100", lambda: _set(_HB(), "/materials/0/gsi", 100.5), ("/materials/0/gsi",)),
    ("mi-zero", lambda: _set(_HB(), "/materials/0/m_i", 0.0), ("/materials/0/m_i",)),
    ("mi-negative", lambda: _set(_HB(), "/materials/0/m_i", -5.0), ("/materials/0/m_i",)),
    ("sigma-ci-zero", lambda: _set(_HB(), "/materials/0/sigma_ci_mpa", 0.0), ("/materials/0/sigma_ci_mpa",)),
    ("sigma-ci-negative", lambda: _set(_HB(), "/materials/0/sigma_ci_mpa", -1.0), ("/materials/0/sigma_ci_mpa",)),
    ("d-negative", lambda: _set(_HB(), "/materials/0/disturbance_d", -0.01), ("/materials/0/disturbance_d",)),
    ("d-above-one", lambda: _set(_HB(), "/materials/0/disturbance_d", 1.01), ("/materials/0/disturbance_d",)),
    # enums
    ("method-unknown", lambda: _set(_MC(), "/analysis/methods", ["janbu"]), ("/analysis/methods",)),
    ("method-empty", lambda: _set(_MC(), "/analysis/methods", []), ("/analysis/methods",)),
    ("model-unknown", lambda: _set(_MC(), "/materials/0/model", "von-mises"), ("/materials/0",)),
    ("mode-unknown", lambda: _set(_MC(), "/analysis/mode", "turbo"), ("/analysis/mode",)),
    # slices
    ("slices-9", lambda: _set(_MC(), "/analysis/slices", 9), ("/analysis/slices",)),
    ("slices-501", lambda: _set(_MC(), "/analysis/slices", 501), ("/analysis/slices",)),
    ("slices-zero", lambda: _set(_MC(), "/analysis/slices", 0), ("/analysis/slices",)),
    ("slices-negative", lambda: _set(_MC(), "/analysis/slices", -50), ("/analysis/slices",)),
    ("slices-float", lambda: _set(_MC(), "/analysis/slices", 50.5), ("/analysis/slices",)),
    ("slices-string", lambda: _set(_MC(), "/analysis/slices", "50"), ("/analysis/slices",)),
    (
        "live-slices-201",
        lambda: _set(_set(_MC(), "/analysis/mode", "live"), "/analysis/slices", 201),
        ("/analysis/slices",),
    ),
    # too many trial circles (schema bounds each axis at 1,000; the product at 1e5 in total)
    (
        "circles-over-1e5",
        lambda: _set(
            _MC(),
            "/analysis/search",
            {"entry_points": 50, "exit_points": 50, "radius_ratios": 41, "rho_min": 1.02, "rho_max": 4.0},
        ),
        ("/analysis/search",),
    ),
    (
        "circles-1e6",
        lambda: _set(
            _MC(),
            "/analysis/search",
            {"entry_points": 1000, "exit_points": 1000, "radius_ratios": 1, "rho_min": 1.02, "rho_max": 4.0},
        ),
        ("/analysis/search",),
    ),
    # schema failures
    ("type-ground-string", lambda: _set(_MC(), "/ground", "0,0 10,10"), ("/ground",)),
    ("type-cohesion-string", lambda: _set(_MC(), "/materials/0/cohesion_kpa", "20"), ("/materials/0/cohesion_kpa",)),
    ("type-cohesion-bool", lambda: _set(_MC(), "/materials/0/cohesion_kpa", True), ("/materials/0/cohesion_kpa",)),
    ("missing-ground", lambda: _del(_MC(), "/ground"), ("/ground", "")),
    ("missing-materials", lambda: _del(_MC(), "/materials"), ("/materials", "")),
    (
        "missing-cohesion",
        lambda: _del(_MC(), "/materials/0/cohesion_kpa"),
        ("/materials/0", "/materials/0/cohesion_kpa"),
    ),
    ("unknown-field", lambda: _set(_MC(), "/surprise", 1), ("/surprise", "")),
    ("mixed-material", lambda: _set(_MC(), "/materials/0/gsi", 50.0), ("/materials/0", "/materials/0/gsi")),
    ("section-id-unicode", lambda: _set(_MC(), "/section_id", "pendiente-ñáΩ"), ("/section_id",)),
    ("section-id-huge", lambda: _set(_MC(), "/section_id", "a" * 100000), ("/section_id",)),
    ("empty-document", lambda: {}, ("",)),
]


@pytest.mark.req("FR-010-07")
@pytest.mark.parametrize(("name", "build", "prefixes"), CASES, ids=[c[0] for c in CASES])
def test_hostile_section_raises_invalid_section_error_naming_the_field_and_range(name, build, prefixes) -> None:
    doc = build()
    with pytest.raises(section.InvalidSectionError) as exc:
        section.parse_section(doc)
    err = exc.value
    assert isinstance(err, ValueError)
    assert err.error_class == "section-invalid"
    assert any(err.field.startswith(p) for p in prefixes), (name, err.field)
    assert err.valid_range
    if err.field:
        assert err.field.rsplit("/", 1)[-1] in str(err)
    assert err.valid_range in str(err)


@pytest.mark.req("FR-010-07")
@pytest.mark.parametrize(("name", "build", "prefixes"), CASES, ids=[c[0] for c in CASES])
def test_the_analysis_returns_no_factor_and_runs_no_solver_for_a_hostile_section(name, build, prefixes) -> None:
    calls: list = []

    def spy(*args, **kwargs):
        calls.append(args)
        raise AssertionError("a solver ran on a hostile section")

    with pytest.raises(section.InvalidSectionError):
        lem.analyse_section(build(), bishop=spy, spencer=spy)
    assert calls == []


@pytest.mark.req("FR-010-07")
def test_the_valid_controls_are_accepted() -> None:
    for doc in (_mc(), _hb()):
        parsed = section.parse_section(doc)
        assert parsed is not None
    # boundary values that are valid: gamma 40, phi 0 and 60, r_u 0, GSI 0 and 100, D 0 and 1, n_s 10 and 500
    for path, value in [
        ("/materials/0/unit_weight_kn_per_m3", 40.0),
        ("/materials/0/friction_angle_deg", 0.0),
        ("/materials/0/friction_angle_deg", 60.0),
        ("/pore_pressure_ratio", 0.0),
        ("/analysis/slices", 10),
        ("/analysis/slices", 500),
    ]:
        assert section.parse_section(_set(_mc(), path, value)) is not None
    for path, value in [
        ("/materials/0/gsi", 0.0),
        ("/materials/0/gsi", 100.0),
        ("/materials/0/disturbance_d", 0.0),
        ("/materials/0/disturbance_d", 1.0),
    ]:
        assert section.parse_section(_set(_hb(), path, value)) is not None


@pytest.mark.req("FR-010-07")
def test_the_published_valid_examples_are_accepted_and_a_published_hostile_one_is_rejected() -> None:
    root = Path(__file__).resolve().parents[2] / "specs" / "010-slope" / "contracts" / "examples"
    for name in ("slope-section.valid.json", "slope-section.valid-hoek-brown.json"):
        assert section.parse_section(json.loads((root / name).read_text(encoding="utf-8"))) is not None
    for name in ("slope-section.hostile-negative-cohesion.json", "slope-section.hostile-gsi-out-of-range.json"):
        with pytest.raises(section.InvalidSectionError):
            section.parse_section(json.loads((root / name).read_text(encoding="utf-8")))


@pytest.mark.req("FR-010-07")
def test_load_section_reads_a_file_and_rejects_malformed_and_non_finite_json(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_mc()), encoding="utf-8")
    assert section.load_section(good) is not None
    text = json.dumps(_mc())
    for name, payload in {
        "truncated.json": text[: len(text) // 2],
        "nan.json": text.replace('"cohesion_kpa": 15.0', '"cohesion_kpa": NaN'),
        "empty.json": "",
        "array.json": "[1, 2, 3]",
        "bom-garbage.json": "﻿{not json",
    }.items():
        path = tmp_path / name
        path.write_text(payload, encoding="utf-8")
        with pytest.raises(ValueError, match=r"."):  # InvalidSectionError or the loader's ContractError
            section.load_section(path)


@pytest.mark.req("FR-010-07")
def test_the_valid_range_of_a_numeric_field_states_its_bounds() -> None:
    with pytest.raises(section.InvalidSectionError) as exc:
        section.parse_section(_set(_mc(), "/materials/0/friction_angle_deg", 75.0))
    assert "60" in exc.value.valid_range
    with pytest.raises(section.InvalidSectionError) as exc:
        section.parse_section(_set(_mc(), "/analysis/slices", 9))
    assert "10" in exc.value.valid_range
    assert "500" in exc.value.valid_range
