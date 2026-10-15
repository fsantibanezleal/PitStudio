# ruff: noqa: E501
"""T-014-063 (GPU, local): coupled rigid-MPM smoke.

Requirements: FR-014-22.

Spec: specs/014-robot-learning/spec.md FR-014-22: "Where the coupled rigid-MPM smoke passes (through Isaac Lab or Newton directly, whichever passes), `st61_il_mpm_eval` shall run the trained IL-2 policy unchanged in Newton's implicit MPM coupled
to the rigid bucket ... and measure k_f = (particle mass inside the bucket volume) / (V_h rho_loose)." FR-014-23: a failed smoke means IL-2b is "not run". Marked `gpu`: runs on the reference machine under the `gpu0.compute` lock, not in CI.

Oracle: conservation and bounds by hand: the total particle mass is the particle count times the particle mass of the material (rho_loose V_cell), the mass inside the bucket volume lies between 0 and that total, an empty bucket
far from the pile holds 0 kg, and the bucket pushed through the pile holds a positive mass; the k_f formula of the requirement applied to the reported masses; every reported number finite.

Expected API of the implementation (module `pitstudio_isaaclab.mpm_smoke`, `python -m pitstudio_isaaclab.mpm_smoke --backend isaaclab|newton --particles N --steps K`, last stdout line JSON):
{"status": "pass" | "fail", "backend": "isaaclab" | "newton", "particles": int, "particle_mass_kg": float, "total_mass_kg": float, "bucket_mass_empty_run_kg": float, "bucket_mass_scoop_run_kg": float, "bucket_volume_m3": float,
"rho_loose_kg_m3": float, "finite": bool, "wall_s": float, "reason": str | null}. The smoke passes through at least one backend; a failing backend reports status "fail" with its reason (never a crash without JSON).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "support"))
import il_gpu_kit as kit  # noqa: E402


@pytest.fixture(scope="module")
def smokes():
    return {
        b: kit.run_module("mpm_smoke", "--backend", b, "--particles", "20000", "--steps", "240", timeout=3600)
        for b in ("isaaclab", "newton")
    }


@pytest.mark.gpu
@pytest.mark.req("FR-014-22")
def test_at_least_one_backend_passes_the_coupled_smoke(smokes) -> None:
    passing = [b for b, r in smokes.items() if r["status"] == "pass"]
    assert passing, {b: r.get("reason") for b, r in smokes.items()}


@pytest.mark.gpu
@pytest.mark.req("FR-014-22")
def test_a_failing_backend_reports_its_reason_instead_of_crashing(smokes) -> None:
    for r in smokes.values():
        assert r["status"] in ("pass", "fail")
        if r["status"] == "fail":
            assert isinstance(r["reason"], str)
            assert r["reason"]


@pytest.mark.gpu
@pytest.mark.req("FR-014-22")
def test_the_particle_mass_is_conserved_and_every_number_is_finite(smokes) -> None:
    for r in (x for x in smokes.values() if x["status"] == "pass"):
        assert r["finite"] is True
        assert r["particles"] == 20000
        assert r["total_mass_kg"] == pytest.approx(r["particles"] * r["particle_mass_kg"], rel=1e-9)
        for k in (
            "particle_mass_kg",
            "total_mass_kg",
            "bucket_mass_empty_run_kg",
            "bucket_mass_scoop_run_kg",
            "bucket_volume_m3",
            "rho_loose_kg_m3",
            "wall_s",
        ):
            assert math.isfinite(r[k])


@pytest.mark.gpu
@pytest.mark.req("FR-014-22")
def test_an_empty_bucket_holds_nothing_and_a_scoop_holds_some_but_never_more_than_the_pile(smokes) -> None:
    for r in (x for x in smokes.values() if x["status"] == "pass"):
        assert r["bucket_mass_empty_run_kg"] == pytest.approx(0.0, abs=1e-9)
        assert 0.0 < r["bucket_mass_scoop_run_kg"] <= r["total_mass_kg"]


@pytest.mark.gpu
@pytest.mark.req("FR-014-22")
def test_k_f_from_the_reported_masses_is_finite_and_positive_by_the_requirement_formula(smokes) -> None:
    for r in (x for x in smokes.values() if x["status"] == "pass"):
        k_f = r["bucket_mass_scoop_run_kg"] / (r["bucket_volume_m3"] * r["rho_loose_kg_m3"])
        assert math.isfinite(k_f)  # k_f = (particle mass inside the bucket volume) / (V_h rho_loose), FR-014-22
        assert k_f > 0.0
