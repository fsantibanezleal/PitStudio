"""T-010-092: cross-field rules of a slope-section document that a JSON schema cannot express.

Requirement: FR-010-43 ("If a slope-section document has a crest or toe outside the ground x range, `rho_min` not below
`rho_max`, repeated material ids, or a distribution naming an undefined material, then the section loader shall reject
it
with error class `section-invalid` naming the field").
Spec: specs/010-slope/spec.md section 3.4 (G5 hostile-input classes); plan.md row FR-010-43.

Expected API (module `pitstudio.slope.section`, shared with T-010-014): `parse_section(document)`, `load_section(path)`,
`InvalidSectionError(ValueError)` with `.error_class == "section-invalid"` and `.field` (JSON pointer).

Oracle: hand calculation, one fixture per rule: the base section is a two-layer section written out in the test (ground
x range [-60, 100], crest 0, toe 20); each case changes exactly one fact and names the pointer the error must carry;
the valid controls (crest at the first ground vertex, toe at the last, rho_min just below rho_max, two distinct ids, a
distribution naming a defined material, a pore-pressure distribution without material id) are accepted.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as ref
from pitstudio.slope import section


def _base() -> dict:
    doc = ref.planar_section(height_m=20.0, slope_deg=45.0, mode="baked", slices=50)
    doc["ground"] = [[-60.0, 20.0], [0.0, 20.0], [20.0, 0.0], [100.0, 0.0]]
    doc["crest_x_m"], doc["toe_x_m"] = 0.0, 20.0
    doc["materials"] = [
        {
            "id": "overburden",
            "model": "mohr-coulomb",
            "unit_weight_kn_per_m3": 19.0,
            "cohesion_kpa": 5.0,
            "friction_angle_deg": 28.0,
            "bottom_z_m": 10.0,
        },
        {
            "id": "bedrock",
            "model": "mohr-coulomb",
            "unit_weight_kn_per_m3": 25.0,
            "cohesion_kpa": 60.0,
            "friction_angle_deg": 38.0,
        },
    ]
    doc["analysis"]["pof"] = {
        "samples": 2000,
        "candidates": 64,
        "seed": 7,
        "distributions": [
            {
                "material_id": "overburden",
                "parameter": "cohesion_kpa",
                "distribution": "normal",
                "mean": 5.0,
                "sd": 1.0,
            },
            {"parameter": "pore_pressure_ratio", "distribution": "uniform", "lower": 0.0, "upper": 0.3},
        ],
    }
    return doc


def _mut(fn) -> dict:
    doc = copy.deepcopy(_base())
    fn(doc)
    return doc


CASES = [
    ("crest-left-of-ground", lambda d: d.update(crest_x_m=-60.001), "/crest_x_m"),
    ("crest-right-of-ground", lambda d: d.update(crest_x_m=100.001), "/crest_x_m"),
    ("toe-left-of-ground", lambda d: d.update(toe_x_m=-61.0), "/toe_x_m"),
    ("toe-right-of-ground", lambda d: d.update(toe_x_m=1000.0), "/toe_x_m"),
    ("rho-equal", lambda d: d["analysis"]["search"].update(rho_min=2.0, rho_max=2.0), "/analysis/search"),
    ("rho-reversed", lambda d: d["analysis"]["search"].update(rho_min=3.0, rho_max=1.5), "/analysis/search"),
    ("material-id-repeated", lambda d: d["materials"][1].update(id="overburden"), "/materials/1/id"),
    (
        "distribution-undefined-material",
        lambda d: d["analysis"]["pof"]["distributions"][0].update(material_id="granite"),
        "/analysis/pof/distributions/0/material_id",
    ),
    (
        "distribution-material-case-differs",
        lambda d: d["analysis"]["pof"]["distributions"][0].update(material_id="Overburden"),
        "/analysis/pof/distributions/0/material_id",
    ),
]


@pytest.mark.req("FR-010-43")
@pytest.mark.parametrize(("name", "mutate", "field"), CASES, ids=[c[0] for c in CASES])
def test_cross_field_violation_is_rejected_with_error_class_section_invalid_naming_the_field(
    name, mutate, field
) -> None:
    doc = _mut(mutate)
    with pytest.raises(section.InvalidSectionError) as exc:
        section.parse_section(doc)
    assert exc.value.error_class == "section-invalid"
    assert exc.value.field.startswith(field), (name, exc.value.field)
    assert exc.value.field.rsplit("/", 1)[-1] in str(exc.value)


@pytest.mark.req("FR-010-43")
@pytest.mark.parametrize(("name", "mutate", "field"), CASES, ids=[c[0] for c in CASES])
def test_the_section_loader_rejects_the_same_documents_from_a_file(name, mutate, field, tmp_path: Path) -> None:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(_mut(mutate)), encoding="utf-8")
    with pytest.raises(section.InvalidSectionError) as exc:
        section.load_section(path)
    assert exc.value.error_class == "section-invalid"
    assert exc.value.field.startswith(field)


@pytest.mark.req("FR-010-43")
def test_the_valid_controls_are_accepted() -> None:
    assert section.parse_section(_base()) is not None
    for mutate in (
        lambda d: d.update(crest_x_m=-60.0),  # on the first ground vertex: inside the closed range
        lambda d: d.update(toe_x_m=100.0),  # on the last
        lambda d: d["analysis"]["search"].update(rho_min=1.5, rho_max=1.5000001),
        lambda d: d["analysis"]["pof"]["distributions"].pop(0),  # only the pore-pressure distribution (no material id)
    ):
        assert section.parse_section(_mut(mutate)) is not None


@pytest.mark.req("FR-010-43")
def test_a_rejected_document_reports_the_first_violated_field_not_a_traceback() -> None:
    doc = _mut(lambda d: (d.update(crest_x_m=500.0), d["materials"][1].update(id="overburden")))
    with pytest.raises(section.InvalidSectionError) as exc:
        section.parse_section(doc)
    assert exc.value.field in {"/crest_x_m", "/materials/1/id"}  # either violation may be reported first, never neither
