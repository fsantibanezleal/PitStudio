# ruff: noqa: E501
"""T-014-046: MPM tier with a fake backend: pairing, 16 <= n <= 64, k_f from particle mass, "not run" paths.

Requirements: FR-014-22, FR-014-23.

Spec: specs/014-robot-learning/spec.md FR-014-22: "Where the coupled rigid-MPM smoke passes (through Isaac Lab or Newton directly, whichever passes), `st61_il_mpm_eval` shall run the trained IL-2 policy
unchanged in Newton's implicit MPM coupled to the rigid bucket, in 16-64 environments, with the dry-sand material of the DEM calibration artefact (spec 011) and the same initial profiles and seeds as the first n FEE
evaluation episodes, and measure k_f = (particle mass inside the bucket volume) / (V_h rho_loose)." FR-014-23: "If the coupled MPM smoke fails, the calibrated material artefact is missing, or fewer than 16 MPM episodes
complete, then IL-2b shall be reported 'not run' with the reason and no FEE -> MPM gap shall be published."

Oracle: hand calculation of k_f = m / (V_h rho_loose) with V_h = 1.5 m3 and rho_loose = 1,800 kg/m3 (V_h rho_loose = 2,700 kg): 1,350 kg -> 0.5, 2,700 kg -> 1.0, 4,050 kg -> 1.5 (above the FEE cap of 1.15, allowed up to 3 by
the table contract); the pairing as set equality with the first n FEE seeds and profiles; the number of backend calls as ceil(n / envs); the "not run" cases enumerated by hand, each also asserting that the backend ran no episode
(no GPU work). The backend is a fake (a recording stub); no Newton, Warp or Isaac Lab is imported.

Plan deviation (see the red report): the tier logic is torch-free and lives in the root package so that CI can run it; the Isaac Lab package supplies the real backend behind the same interface. The spec 011 calibration
artefact carries no bulk-density field, so the interface takes `rho_loose_kg_m3` of the dry-sand material explicitly.

Expected API of the implementation (module `pitstudio.robots.mpm`):
    run_mpm_tier(params, backend, policy, *, fee_seeds, profiles, material, v_heaped) -> MpmResult
        params: a valid IL-2 task document of stage `st61_il_mpm_eval` (its `mpm` block: episodes n in 16..64, envs in 16..64, material id; checked as in T-014-049, TaskParamsError exit code 2
        otherwise); backend: an object with `smoke() -> bool` and `run(policy, profiles, seeds, material, num_envs) -> list[dict | None]` (one entry per episode: {"particle_mass_kg", "cycle_time_s",
        "stalled", "lift_off"} or None for an episode that did not complete); policy: passed to the backend unchanged (the same object); fee_seeds / profiles: the seeds (ascending) and initial profiles of
        the FEE evaluation episodes; material: {"id": <slug>, "rho_loose_kg_m3": float} or None; v_heaped: V_h (m3).
        MpmResult (frozen dataclass): status ("complete" | "not run"), reason (None or text), rows (list of dig-episode rows of contracts/il-episodes.schema.json: seed, termination, fill_factor = mass / (v_heaped *
        rho_loose), cycle_time_s, productivity_per_s = fill_factor / cycle_time_s, stalled, lift_off; one per completed episode in seed order), seeds (the seeds of the rows), manifest (dict with n_requested, n_completed, envs).
        The backend is asked for exactly the first n seeds and profiles, in order, in batches of at most `envs` episodes (ceil(n / envs) calls). `smoke()` False, material None, or fewer than 16 completed
        episodes give status "not run", a reason naming "smoke", "material" or "16", rows [] and, for the first two, no call of `run`. ValueError naming `material` for an id that differs from params.mpm.material or a
        rho_loose that is not positive and finite, `particle_mass_kg` for a negative or non-finite mass, `fee_seeds` / `profiles` when fewer than n are given or the lengths differ, `v_heaped` unless positive and finite.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest
from pitstudio.robots.config import TaskParamsError
from pitstudio.robots.mpm import run_mpm_tier

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "014-robot-learning" / "contracts" / "examples"
MPM = json.loads(
    (EX / "il-task.valid-mpm.json").read_text("utf-8")
)  # episodes 32, envs 32, material dem-dry-sand-calibration
MATERIAL = {"id": MPM["mpm"]["material"], "rho_loose_kg_m3": 1800.0}
V_H = 1.5
SEEDS = [1_000_000 + i for i in range(100)]
PROFILES = [{"profile": i} for i in range(100)]


class FakeBackend:
    def __init__(self, *, smoke_ok=True, mass=1350.0, fail_seeds=(), mass_fn=None):
        self.smoke_ok = smoke_ok
        self.mass = mass
        self.fail_seeds = set(fail_seeds)
        self.mass_fn = mass_fn
        self.calls: list[dict] = []

    def smoke(self) -> bool:
        return self.smoke_ok

    def run(self, policy, profiles, seeds, material, num_envs):
        self.calls.append(
            {
                "policy": policy,
                "profiles": list(profiles),
                "seeds": list(seeds),
                "material": material,
                "num_envs": num_envs,
            }
        )
        out = []
        for s in seeds:
            if s in self.fail_seeds:
                out.append(None)
            else:
                m = self.mass_fn(s) if self.mass_fn else self.mass
                out.append({"particle_mass_kg": m, "cycle_time_s": 15.0, "stalled": False, "lift_off": True})
        return out


def params(n=32, envs=32):
    p = copy.deepcopy(MPM)
    p["mpm"]["episodes"] = n
    p["mpm"]["envs"] = envs
    return p


def run(backend, *, n=32, envs=32, material=MATERIAL, policy=None, **over):
    policy = policy if policy is not None else object()
    kw = {"fee_seeds": SEEDS, "profiles": PROFILES, "material": material, "v_heaped": V_H}
    kw.update(over)
    return run_mpm_tier(params(n, envs), backend, policy, **kw), policy


# ------------------------------------------------------------------------------------------------ k_f formula
@pytest.mark.req("FR-014-22")
@pytest.mark.parametrize(("mass", "kf"), [(1350.0, 0.5), (2700.0, 1.0), (4050.0, 1.5), (0.0, 0.0), (135.0, 0.05)])
def test_k_f_is_the_particle_mass_over_v_h_rho_loose(mass, kf) -> None:
    res, _ = run(FakeBackend(mass=mass), n=16, envs=16)
    assert res.status == "complete"
    assert res.rows[0]["fill_factor"] == pytest.approx(kf, rel=1e-12, abs=1e-15)  # m / (1.5 * 1,800) = m / 2,700


@pytest.mark.req("FR-014-22")
def test_k_f_uses_the_given_bulk_density_and_heaped_volume() -> None:
    res, _ = run(
        FakeBackend(mass=1350.0),
        n=16,
        envs=16,
        material={"id": MATERIAL["id"], "rho_loose_kg_m3": 1500.0},
        v_heaped=2.0,
    )
    assert res.rows[0]["fill_factor"] == pytest.approx(1350.0 / (2.0 * 1500.0), rel=1e-12)  # 0.45


@pytest.mark.req("FR-014-22")
def test_each_row_is_a_dig_episode_with_productivity_k_f_over_cycle_time() -> None:
    res, _ = run(FakeBackend(mass=2700.0), n=16, envs=16)
    r = res.rows[3]
    assert set(r) == {"seed", "termination", "fill_factor", "cycle_time_s", "productivity_per_s", "stalled", "lift_off"}
    assert r["seed"] == SEEDS[3]
    assert r["productivity_per_s"] == pytest.approx(1.0 / 15.0, rel=1e-12)
    assert r["termination"] == "completed"
    assert r["lift_off"] is True
    assert r["stalled"] is False


# ------------------------------------------------------------------------------------------------ pairing and envs
@pytest.mark.req("FR-014-22")
@pytest.mark.parametrize("n", [16, 17, 32, 33, 64])
def test_the_backend_receives_exactly_the_first_n_fee_seeds_and_profiles_in_order(n) -> None:
    b = FakeBackend()
    res, _ = run(b, n=n, envs=16)
    seeds = [s for c in b.calls for s in c["seeds"]]
    profiles = [p for c in b.calls for p in c["profiles"]]
    assert seeds == SEEDS[:n]
    assert profiles == PROFILES[:n]
    assert res.seeds == SEEDS[:n]
    assert [r["seed"] for r in res.rows] == SEEDS[:n]
    assert res.manifest["n_requested"] == n
    assert res.manifest["n_completed"] == n


@pytest.mark.req("FR-014-22")
@pytest.mark.parametrize(
    ("n", "envs", "calls"), [(16, 16, 1), (32, 32, 1), (33, 16, 3), (64, 16, 4), (64, 64, 1), (40, 25, 2)]
)
def test_the_episodes_run_in_batches_of_at_most_envs_environments(n, envs, calls) -> None:
    b = FakeBackend()
    run(b, n=n, envs=envs)
    assert len(b.calls) == calls == math.ceil(n / envs)
    assert all(len(c["seeds"]) <= envs for c in b.calls)
    assert all(c["num_envs"] == envs for c in b.calls)


@pytest.mark.req("FR-014-22")
def test_the_policy_and_the_material_are_passed_to_the_backend_unchanged() -> None:
    policy = {"checkpoint": "il2-ckpt-3000"}
    b = FakeBackend()
    run(b, policy=policy)
    assert all(c["policy"] is policy for c in b.calls)
    assert all(c["material"] == MATERIAL for c in b.calls)


@pytest.mark.req("FR-014-22")
@pytest.mark.parametrize(("n", "envs"), [(15, 16), (65, 16), (32, 15), (32, 65), (0, 16), (-1, 16)])
def test_the_episode_and_environment_counts_are_limited_to_16_to_64(n, envs) -> None:
    b = FakeBackend()
    with pytest.raises(TaskParamsError) as info:
        run(b, n=n, envs=envs)
    assert info.value.exit_code == 2
    assert "/mpm/" in info.value.pointer
    assert b.calls == []  # exit before any GPU work


@pytest.mark.req("FR-014-22")
def test_fewer_fee_episodes_than_requested_raises_value_error() -> None:
    with pytest.raises(ValueError, match=r"fee_seeds"):
        run(FakeBackend(), n=32, fee_seeds=SEEDS[:20])
    with pytest.raises(ValueError, match=r"profiles"):
        run(FakeBackend(), n=32, profiles=PROFILES[:20])
    with pytest.raises(ValueError, match=r"profiles|fee_seeds"):
        run(FakeBackend(), n=32, profiles=PROFILES[:50])  # lengths differ


# ------------------------------------------------------------------------------------------------ "not run" paths
@pytest.mark.req("FR-014-23")
def test_a_failed_coupled_smoke_is_not_run_without_any_episode() -> None:
    b = FakeBackend(smoke_ok=False)
    res, _ = run(b)
    assert res.status == "not run"
    assert "smoke" in res.reason
    assert res.rows == []
    assert b.calls == []


@pytest.mark.req("FR-014-23")
def test_a_missing_material_artefact_is_not_run_without_any_episode() -> None:
    b = FakeBackend()
    res, _ = run(b, material=None)
    assert res.status == "not run"
    assert "material" in res.reason
    assert res.rows == []
    assert b.calls == []


@pytest.mark.req("FR-014-23")
def test_fewer_than_16_completed_episodes_is_not_run_and_publishes_no_rows() -> None:
    fail = SEEDS[:20]  # 20 of the first 32 episodes fail: 12 complete
    b = FakeBackend(fail_seeds=fail)
    res, _ = run(b, n=32, envs=32)
    assert res.status == "not run"
    assert "16" in res.reason
    assert res.rows == []
    assert res.manifest["n_requested"] == 32
    assert res.manifest["n_completed"] == 12


@pytest.mark.req("FR-014-23")
def test_exactly_16_completed_episodes_is_enough_and_the_failed_ones_are_left_out() -> None:
    fail = SEEDS[:16]  # 16 of 32 fail, 16 complete
    res, _ = run(FakeBackend(fail_seeds=fail), n=32, envs=32)
    assert res.status == "complete"
    assert res.seeds == SEEDS[16:32]
    assert len(res.rows) == 16
    assert res.manifest["n_completed"] == 16


@pytest.mark.req("FR-014-23")
def test_every_episode_failing_is_not_run() -> None:
    res, _ = run(FakeBackend(fail_seeds=SEEDS), n=16, envs=16)
    assert res.status == "not run"
    assert res.manifest["n_completed"] == 0


# ------------------------------------------------------------------------------------------------ hostile inputs
@pytest.mark.req("FR-014-22")
@pytest.mark.parametrize("bad", [math.nan, math.inf, -1.0, -1e-9])
def test_a_negative_or_non_finite_particle_mass_raises_value_error_naming_it(bad) -> None:
    with pytest.raises(ValueError, match=r"particle_mass_kg"):
        run(FakeBackend(mass=bad), n=16, envs=16)


@pytest.mark.req("FR-014-22")
@pytest.mark.parametrize("rho", [0.0, -1800.0, math.nan, math.inf])
def test_a_bulk_density_that_is_not_positive_and_finite_raises_value_error_naming_material(rho) -> None:
    b = FakeBackend()
    with pytest.raises(ValueError, match=r"\bmaterial\b"):
        run(b, material={"id": MATERIAL["id"], "rho_loose_kg_m3": rho})
    assert b.calls == []


@pytest.mark.req("FR-014-22")
def test_a_material_that_is_not_the_one_of_the_task_raises_value_error_naming_material() -> None:
    b = FakeBackend()
    with pytest.raises(ValueError, match=r"\bmaterial\b"):
        run(b, material={"id": "some-other-sand", "rho_loose_kg_m3": 1800.0})
    assert b.calls == []


@pytest.mark.req("FR-014-22")
@pytest.mark.parametrize("bad", [0.0, -1.5, math.nan, math.inf])
def test_a_heaped_volume_that_is_not_positive_and_finite_raises_value_error_naming_it(bad) -> None:
    with pytest.raises(ValueError, match=r"\bv_heaped\b"):
        run(FakeBackend(), v_heaped=bad)


@pytest.mark.req("FR-014-22")
def test_an_il1_task_or_a_training_stage_document_is_refused() -> None:
    il1 = json.loads((EX / "il-task.valid.json").read_text("utf-8"))
    with pytest.raises((TaskParamsError, ValueError)):
        run_mpm_tier(il1, FakeBackend(), object(), fee_seeds=SEEDS, profiles=PROFILES, material=MATERIAL, v_heaped=V_H)
    il2_train = json.loads(
        (EX / "il-task.valid-il2.json").read_text("utf-8")
    )  # stage st60_il_train: it has no `mpm` block
    with pytest.raises((TaskParamsError, ValueError)):
        run_mpm_tier(
            il2_train, FakeBackend(), object(), fee_seeds=SEEDS, profiles=PROFILES, material=MATERIAL, v_heaped=V_H
        )


@pytest.mark.req("FR-014-22")
def test_a_backend_that_returns_the_wrong_number_of_results_is_rejected() -> None:
    class Short(FakeBackend):
        def run(self, policy, profiles, seeds, material, num_envs):
            return super().run(policy, profiles, seeds, material, num_envs)[:-1]

    with pytest.raises(ValueError, match=r"backend"):
        run(Short(), n=16, envs=16)
