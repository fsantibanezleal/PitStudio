"""T-005-014 - FR-005-08, FR-005-09: time-step guard `dt-unstable`; reduced-modulus record and re-benchmark flag.

Oracles (hand calculation; plan 005 test strategy):
- FR-005-08: Delta t_R = pi R_min sqrt(rho / G) / (0.1631 nu + 0.8766) with G = E / (2 (1 + nu)), the guard's own
  definition in the spec (its constants are UNVERIFIED as physics, spec 005 section 7, but they define the guard).
  Worked example (R = 5 mm, E = 50 MPa, nu = 0.25, rho = 2650 kg/m^3): G = 2.0e7 Pa, sqrt(rho / G) = 1.1511e-2 s/m,
  pi * 5e-3 * 1.1511e-2 = 1.8081e-4, / 0.917375 = 1.9710e-4 s (plan: 0.197 ms); limit 0.2 * Delta t_R = 3.942e-5 s.
- FR-005-09: hand-written expectation of the record (both moduli in the observables metadata, DC-005-03
  `youngs_modulus {used_pa, real_pa}`; both in the benchmark report's material reference, DC-005-05
  `$defs/material_ref`) and of the re-benchmark flag (the Beverloo and repose benchmarks of that material).

Expected public API (module `pitstudio_studio.physics.dem.step`; constructor in T-005-011):
    DemSimulation(..., rayleigh_fraction=0.2, ...)
        raises PhysicsError("dt-unstable: ...") at construction when dt > rayleigh_fraction * Delta t_R of the
        smallest particle; details {"dt": dt, "dt_limit": rayleigh_fraction * Delta t_R}; the message states both
        values as numbers
        .rayleigh_dt                 Delta t_R [s] of the smallest particle, computed with the modulus in use
        .observables_metadata()      dict for the observables file (DC-005-03); when the material's modulus is
                                     reduced it holds "youngs_modulus": {"used_pa": E_used, "real_pa": E_real},
                                     otherwise it has no "youngs_modulus" key
    DemMaterial.from_card(card)      reads a DC-005-01 material card (model "dem-sphere")
    material_ref(card) -> dict       the report's material reference (DC-005-05 $defs/material_ref): id,
                                     card_sha256, youngs_modulus_pa and, when reduced, youngs_modulus_real_pa
    rebenchmark_required(card) -> frozenset[str]
                                     benchmark ids that must be run at the reduced modulus before the material's
                                     rollouts are used: contains "dem-beverloo-silo" and "dem-repose" when the
                                     card's modulus is reduced, empty otherwise
Errors: `pitstudio_studio.physics.errors.PhysicsError` (.error_class, .details), see T-005-013.
"""

from __future__ import annotations

import copy
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)

from pitstudio_studio.physics.dem.step import (  # noqa: E402
    DemMaterial,
    DemSimulation,
    material_ref,
    rebenchmark_required,
)
from pitstudio_studio.physics.errors import PhysicsError  # noqa: E402

DEVICE = "cpu"
R = 5.0e-3
E = 50.0e6
NU = 0.25
RHO = 2650.0

# Schemas: the promoted copies (T-005-001) when present, else the drafts of spec 005 / 018
_PROMOTED = ROOT / "contracts"
_DRAFT = ROOT / "specs" / "005-physics" / "contracts"
SCHEMA_DIR = _PROMOTED if (_PROMOTED / "physics-scenario.schema.json").is_file() else _DRAFT


def _registry() -> tuple[Registry, dict[str, dict]]:
    schemas = {}
    for name in ("physics-scenario", "physics-observables", "physics-benchmark-report"):
        schemas[name] = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    reg = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())
    return reg, schemas


REGISTRY, SCHEMAS = _registry()


def validator(schema_name: str, pointer: str) -> Draft202012Validator:
    sid = SCHEMAS[schema_name]["$id"]
    return Draft202012Validator({"$ref": f"{sid}#{pointer}"}, registry=REGISTRY)


def rayleigh_hand(r_min: float, e: float, nu: float, rho: float) -> float:
    g = e / (2.0 * (1.0 + nu))
    return math.pi * r_min * math.sqrt(rho / g) / (0.1631 * nu + 0.8766)


def material(e: float = E, **kw) -> DemMaterial:
    return DemMaterial(
        density=RHO, youngs_modulus=e, poisson_ratio=NU, restitution=0.5, friction_static=0.5,
        friction_rolling=0.1, **kw,
    )  # fmt: skip


def two_spheres(radii=(R, R)) -> tuple[np.ndarray, np.ndarray]:
    pos = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    return pos, np.asarray(radii, dtype=float)


def numbers_in(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)]


# ---------------------------------------------------------------- FR-005-08


@pytest.mark.req("FR-005-08")
def test_rayleigh_time_step_hand_value() -> None:
    """Oracle self-check against the plan's 0.197 ms."""
    assert abs(rayleigh_hand(R, E, NU, RHO) - 1.9710e-4) <= 1e-8


@pytest.mark.req("FR-005-08")
def test_rayleigh_time_step_of_the_simulation() -> None:
    pos, radii = two_spheres()
    sim = DemSimulation(pos, radii, material(), 1.0e-5, device=DEVICE)
    assert sim.rayleigh_dt == pytest.approx(rayleigh_hand(R, E, NU, RHO), rel=1e-6)


@pytest.mark.req("FR-005-08")
def test_time_step_below_the_limit_is_accepted() -> None:
    pos, radii = two_spheres()
    dt = 0.99 * 0.2 * rayleigh_hand(R, E, NU, RHO)
    sim = DemSimulation(pos, radii, material(), dt, device=DEVICE)
    sim.step(2)
    assert sim.step_index == 2


@pytest.mark.req("FR-005-08")
@pytest.mark.parametrize(
    ("radii", "fraction"),
    [
        ((R, R), 0.2),  # default fraction, worked example: limit 3.942e-5 s
        ((R, 2.0e-3, 8.0e-3), 0.2),  # the smallest particle (2 mm) sets the limit: 1.577e-5 s
        ((R, R), 0.1),  # declared fraction: limit 1.971e-5 s
    ],
)
def test_time_step_above_the_limit_is_rejected(radii, fraction: float) -> None:
    limit = fraction * rayleigh_hand(min(radii), E, NU, RHO)
    dt = 1.05 * limit  # 5 % apart, so that the two stated numbers cannot be confused
    pos = np.c_[np.arange(len(radii)) * 1.0, np.zeros(len(radii)), np.zeros(len(radii))]
    with pytest.raises(PhysicsError) as info:
        DemSimulation(pos, np.asarray(radii), material(), dt, rayleigh_fraction=fraction, device=DEVICE)
    err = info.value
    assert err.error_class == "dt-unstable"
    assert str(err).startswith("dt-unstable: ")
    assert err.details["dt"] == pytest.approx(dt, rel=1e-12)
    assert err.details["dt_limit"] == pytest.approx(limit, rel=1e-6)
    nums = numbers_in(str(err))
    assert any(abs(x / dt - 1.0) <= 5e-3 for x in nums if x > 0), f"dt not stated in: {err}"
    assert any(abs(x / limit - 1.0) <= 5e-3 for x in nums if x > 0), f"limit not stated in: {err}"


@pytest.mark.req("FR-005-08")
def test_the_default_fraction_is_one_fifth() -> None:
    pos, radii = two_spheres()
    limit = 0.2 * rayleigh_hand(R, E, NU, RHO)
    DemSimulation(pos, radii, material(), 0.999 * limit, device=DEVICE)  # accepted
    with pytest.raises(PhysicsError) as info:
        DemSimulation(pos, radii, material(), 1.001 * limit, device=DEVICE)
    assert info.value.error_class == "dt-unstable"


@pytest.mark.req("FR-005-08")
def test_infinite_time_step_is_rejected_as_unstable() -> None:
    pos, radii = two_spheres()
    with pytest.raises(PhysicsError) as info:
        DemSimulation(pos, radii, material(), math.inf, device=DEVICE)
    assert info.value.error_class == "dt-unstable"


@pytest.mark.req("FR-005-08")
@pytest.mark.parametrize("dt", [math.nan, 0.0, -1.0e-6])
def test_non_finite_or_non_positive_time_step_is_rejected(dt: float) -> None:
    """Hostile input: a NaN step compares false against the limit and must not slip through the guard."""
    pos, radii = two_spheres()
    with pytest.raises(PhysicsError) as info:
        DemSimulation(pos, radii, material(), dt, device=DEVICE)
    assert info.value.error_class in {"dt-unstable", "physics-params-invalid"}


@pytest.mark.req("FR-005-08")
@pytest.mark.parametrize("fraction", [0.0, -0.2, 1.5, math.nan])
def test_out_of_domain_rayleigh_fraction_is_rejected(fraction: float) -> None:
    """Hostile input: f_R is declared in (0, 1] (DC-005-01 dem block `rayleigh_fraction`)."""
    pos, radii = two_spheres()
    with pytest.raises(PhysicsError) as info:
        DemSimulation(pos, radii, material(), 1.0e-6, rayleigh_fraction=fraction, device=DEVICE)
    assert info.value.error_class in {"dt-unstable", "physics-params-invalid"}


# ---------------------------------------------------------------- FR-005-09

E_USED = 5.0e6  # reduced modulus, Pa
E_REAL = 5.0e10  # the material's real modulus, Pa

REDUCED_CARD = {
    "id": "test-rock-reduced",
    "label": "test rock with a reduced Young's modulus",
    "model": "dem-sphere",
    "density_kg_m3": {"value": RHO, "status": "assumed", "note": "test fixture"},
    "youngs_modulus_pa": {"value": E_USED, "status": "reduced", "note": "lowered 1e4 times for the time step"},
    "youngs_modulus_real_pa": {"value": E_REAL, "status": "assumed", "note": "order of magnitude of intact rock"},
    "poisson_ratio": {"value": NU, "status": "assumed", "note": "test fixture"},
    "restitution": {"value": 0.5, "status": "assumed", "note": "test fixture"},
    "friction_static": {"value": 0.5, "status": "assumed", "note": "test fixture"},
    "friction_rolling": {"value": 0.1, "status": "assumed", "note": "test fixture"},
    "diameter_m": {"value": 2.0 * R, "status": "assumed", "note": "test fixture"},
}


def real_card() -> dict:
    card = copy.deepcopy(REDUCED_CARD)
    card["id"] = "test-rock"
    card["youngs_modulus_pa"] = {"value": E, "status": "assumed", "note": "test fixture"}
    del card["youngs_modulus_real_pa"]
    return card


@pytest.mark.req("FR-005-09")
def test_fixture_cards_are_valid_material_cards() -> None:
    v = validator("physics-scenario", "/$defs/material_card")
    v.validate(REDUCED_CARD)
    v.validate(real_card())


@pytest.mark.req("FR-005-09")
def test_reduced_modulus_is_used_by_the_solver() -> None:
    pos, radii = two_spheres()
    sim = DemSimulation(pos, radii, DemMaterial.from_card(REDUCED_CARD), 1.0e-5, device=DEVICE)
    # the guard and the contact law run at the reduced value: Delta t_R(5 MPa) = 6.233e-4 s
    assert sim.rayleigh_dt == pytest.approx(rayleigh_hand(R, E_USED, NU, RHO), rel=1e-6)


@pytest.mark.req("FR-005-09")
def test_observables_record_both_moduli() -> None:
    pos, radii = two_spheres()
    sim = DemSimulation(pos, radii, DemMaterial.from_card(REDUCED_CARD), 1.0e-5, device=DEVICE)
    meta = sim.observables_metadata()
    assert meta["youngs_modulus"] == {"used_pa": E_USED, "real_pa": E_REAL}
    Draft202012Validator(SCHEMAS["physics-observables"]["properties"]["youngs_modulus"]).validate(
        meta["youngs_modulus"]
    )


@pytest.mark.req("FR-005-09")
def test_observables_of_an_unreduced_material_hold_no_modulus_pair() -> None:
    pos, radii = two_spheres()
    sim = DemSimulation(pos, radii, DemMaterial.from_card(real_card()), 1.0e-5, device=DEVICE)
    assert "youngs_modulus" not in sim.observables_metadata()


@pytest.mark.req("FR-005-09")
def test_material_constructed_directly_records_the_real_value() -> None:
    pos, radii = two_spheres()
    sim = DemSimulation(pos, radii, material(E_USED, youngs_modulus_real=E_REAL), 1.0e-5, device=DEVICE)
    assert sim.observables_metadata()["youngs_modulus"] == {"used_pa": E_USED, "real_pa": E_REAL}


@pytest.mark.req("FR-005-09")
def test_benchmark_report_material_reference_carries_both_moduli() -> None:
    ref = material_ref(REDUCED_CARD)
    validator("physics-benchmark-report", "/$defs/material_ref").validate(ref)
    assert ref["id"] == "test-rock-reduced"
    assert ref["youngs_modulus_pa"] == E_USED
    assert ref["youngs_modulus_real_pa"] == E_REAL
    assert re.fullmatch(r"[0-9a-f]{64}", ref["card_sha256"])
    plain = material_ref(real_card())
    validator("physics-benchmark-report", "/$defs/material_ref").validate(plain)
    assert "youngs_modulus_real_pa" not in plain


@pytest.mark.req("FR-005-09")
def test_reduced_material_must_be_rebenchmarked() -> None:
    flagged = rebenchmark_required(REDUCED_CARD)
    assert {"dem-beverloo-silo", "dem-repose"} <= set(flagged)
    assert set(flagged) <= set(SCHEMAS["physics-scenario"]["$defs"]["benchmark_id"]["enum"])
    assert not rebenchmark_required(real_card())
