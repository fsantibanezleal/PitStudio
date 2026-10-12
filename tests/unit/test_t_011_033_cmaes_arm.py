"""T-011-033 - FR-011-20, FR-011-21: CMA-ES calibration arm, common budget and stopping, on the fake simulator.

Oracles (independent of the code under test; plan 011 test strategy FR-011-20 / FR-011-21):
- the fake linear simulator of tests/_calib_fake.py: theta(mu, seed) = a + b mu + sigma z(seed), so the loss of any
    mu is
  computed here in closed form: L(mu) = mean over the packing seeds of (theta - theta*)^2, and the exact optimum is
  mu = (theta* - a) / b for sigma = 0;
- default population of the `cma` package for one dimension, Hansen's rule lambda = 4 + floor(3 ln n) = 4 for n = 1
  (N. Hansen, "The CMA Evolution Strategy: A Tutorial", 2016, eq. 48), so one generation costs 4 candidates x S = 2
  packing seeds = 8 forward simulations;
- budget arithmetic by hand: 60 forward-equivalent simulations hold 7 generations of 8 (56 used, 8 would exceed 60);
  a flat response with theta* = a gives L = 0 <= (0.1 deg)^2 = 0.01 after the first generation (8 simulations);
- call counting by the fake (every forward simulation is logged), so the reported simulation count is checked against
  the number of calls actually made.

Expected public API (module `pitstudio_studio.physics.calibration.cmaes`, package under `studio/src/`; the numpy
protocol core lives in `src/pitstudio/calibration/`):

    run_cmaes_arm(simulator, *, theta_star, packing_seeds, mu0=0.55, bounds=(0.1, 1.0), budget=60, sigma0=0.1,
                  rng_seed=0, loss_tolerance_deg=0.1) -> ArmResult
        simulator: the protocol of tests/_calib_fake.py (`theta(mu, seed)` -> repose angle in degrees);
        packing_seeds: the S optimisation seeds; every candidate is evaluated on all of them,
        L(mu) = mean over seeds of (theta(mu, seed) - theta_star)^2 (the loss of FR-011-18);
        stops when L <= loss_tolerance_deg^2 or when another generation would exceed `budget` forward-equivalent
        simulations; the budget is never exceeded.
        ArmResult attributes: mu_hat (the best evaluated candidate), best_loss, simulations (int, forward-equivalent),
        wall_time_s (float >= 0), stop_reason in {"loss-tolerance", "budget"}, path (list of the distribution mean per
        generation, path[0] = mu0), evaluations (list of (mu, loss) pairs, one per candidate, in evaluation order),
        population (int), sigma0 (float).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _calib_fake import FakeDem  # noqa: E402
from pitstudio_studio.physics.calibration.cmaes import run_cmaes_arm  # noqa: E402

SEEDS = [101, 102]  # S = 2 packing seeds


def arm(fake: FakeDem, theta_star: float, **kw):
    return run_cmaes_arm(fake, theta_star=theta_star, packing_seeds=SEEDS, **kw)


@pytest.mark.req("FR-011-20")
def test_population_is_four_for_one_dimension_and_sigma0_is_a_tenth() -> None:
    res = arm(FakeDem(24.0, 20.0), 32.0)
    assert res.population == 4  # 4 + floor(3 ln 1)
    assert res.sigma0 == pytest.approx(0.1, rel=1e-12)
    assert len(res.evaluations) % 4 == 0


@pytest.mark.req("FR-011-20")
def test_the_search_starts_from_mu0_and_stays_inside_the_bounds() -> None:
    fake = FakeDem(24.0, 20.0)
    res = arm(fake, 24.0 + 20.0 * 0.4)
    assert res.path[0] == pytest.approx(0.55, rel=1e-12)
    assert all(0.1 <= mu <= 1.0 for mu, _ in res.evaluations)
    assert all(0.1 <= mu <= 1.0 for mu, _ in fake.forward_calls)
    assert 0.1 <= res.mu_hat <= 1.0


@pytest.mark.req("FR-011-20")
def test_an_optimum_outside_the_bounds_is_approached_but_never_crossed() -> None:
    fake = FakeDem(24.0, 20.0)
    res = arm(fake, 24.0 + 20.0 * 3.0)  # optimum mu = 3.0, upper bound 1.0
    assert res.mu_hat <= 1.0
    assert res.mu_hat > 0.65  # the best candidate moved towards the bound (start 0.55, sigma0 = 0.1)
    assert all(mu <= 1.0 for mu, _ in fake.forward_calls)


@pytest.mark.req("FR-011-20")
def test_the_recorded_loss_is_the_common_seed_averaged_squared_error() -> None:
    fake = FakeDem(24.0, 20.0, sigma=0.3)
    theta_star = 24.0 + 20.0 * 0.45
    res = arm(fake, theta_star)
    for mu, loss in res.evaluations:
        assert loss == pytest.approx(fake.loss(mu, SEEDS, theta_star), rel=1e-9, abs=1e-12)


@pytest.mark.req("FR-011-20")
def test_every_candidate_is_evaluated_on_every_packing_seed_and_only_those() -> None:
    fake = FakeDem(24.0, 20.0, sigma=0.3)
    res = arm(fake, 24.0 + 20.0 * 0.45)
    assert {s for _, s in fake.forward_calls} == set(SEEDS)
    assert len(fake.forward_calls) == len(SEEDS) * len(res.evaluations)


@pytest.mark.req("FR-011-20")
def test_the_best_evaluated_candidate_is_returned() -> None:
    fake = FakeDem(24.0, 20.0, sigma=0.3)
    theta_star = 24.0 + 20.0 * 0.42
    res = arm(fake, theta_star)
    losses = [fake.loss(mu, SEEDS, theta_star) for mu, _ in res.evaluations]
    best_mu = res.evaluations[losses.index(min(losses))][0]
    assert res.mu_hat == pytest.approx(best_mu, rel=1e-12)
    assert res.best_loss == pytest.approx(min(losses), rel=1e-9, abs=1e-12)


@pytest.mark.req("FR-011-20")
def test_the_search_improves_on_the_start_for_the_noise_free_fake() -> None:
    fake = FakeDem(24.0, 20.0)
    theta_star = 24.0 + 20.0 * 0.40
    res = arm(fake, theta_star)
    assert res.best_loss < fake.loss(0.55, SEEDS, theta_star)  # (20 * 0.15)^2 = 9 at the start


@pytest.mark.req("FR-011-20")
def test_the_same_rng_seed_reproduces_the_run_and_another_seed_changes_it() -> None:
    def go(seed: int):
        f = FakeDem(24.0, 20.0)
        return arm(f, 24.0 + 20.0 * 0.40, rng_seed=seed).evaluations

    assert go(5) == go(5)
    assert go(5) != go(6)


@pytest.mark.req("FR-011-21")
def test_a_flat_response_matching_the_target_stops_after_one_generation_on_the_loss_tolerance() -> None:
    fake = FakeDem(24.0, 0.0)
    res = arm(fake, 24.0)  # L = 0 <= 0.01 for every candidate
    assert res.stop_reason == "loss-tolerance"
    assert res.simulations == 8  # 4 candidates x 2 seeds
    assert fake.equivalent_simulations == 8
    assert res.best_loss <= 0.1**2


@pytest.mark.req("FR-011-21")
def test_an_unreachable_target_runs_to_the_budget_without_exceeding_it() -> None:
    fake = FakeDem(24.0, 0.0)
    res = arm(fake, 24.0 + 40.0)  # L = 1600 everywhere
    assert res.stop_reason == "budget"
    assert 52 < res.simulations <= 60  # 7 generations of 8 = 56; an 8th would reach 64 > 60
    assert fake.equivalent_simulations == res.simulations


@pytest.mark.req("FR-011-21")
@pytest.mark.parametrize("budget", [16, 24, 60])
def test_the_reported_simulation_count_equals_the_calls_made_and_respects_the_budget(budget: int) -> None:
    fake = FakeDem(24.0, 0.0)
    res = arm(fake, 24.0 + 40.0, budget=budget)
    assert res.simulations == fake.equivalent_simulations
    assert res.simulations <= budget
    assert res.simulations > budget - 8  # no unused room for a whole generation


@pytest.mark.req("FR-011-21")
def test_the_wall_time_is_reported_as_a_non_negative_number() -> None:
    res = arm(FakeDem(24.0, 20.0), 32.0)
    assert isinstance(res.wall_time_s, float)
    assert res.wall_time_s >= 0.0


@pytest.mark.req("FR-011-21")
@pytest.mark.parametrize("tol", [0.1, 0.5])
def test_the_stopping_tolerance_is_the_square_of_the_loss_tolerance_in_degrees(tol: float) -> None:
    fake = FakeDem(24.0, 0.0)
    theta_star = 24.0 + 0.3  # L = 0.09 everywhere: above 0.1^2 = 0.01, below 0.5^2 = 0.25
    res = arm(fake, theta_star, loss_tolerance_deg=tol)
    assert res.stop_reason == ("budget" if tol == 0.1 else "loss-tolerance")
