"""GNS v2 (FR-011-04): the noise scale chosen on validation by the rollout error of short validation rollouts.

The one-step validation loss does not see error accumulation: run-002 chose the largest noise by that loss and then
19 of 20
held-out rollouts left the domain within 18 to 78 steps. `train.rollout_probe` rolls a step function out from frame 0 of
validation rollouts and reports where it diverges and how far it drifts; `train.choose_by_rollout` ranks the candidates;
`train_gns(..., noise_selection="rollout")` uses both. The default selection (`"val_loss"`) is unchanged (T-011-014).

Oracles (independent of the code under test, by hand):
- a step that reproduces the static reference completes every step with zero error; a step that adds 0.5 d per step
along x
  has the position error 0.5 d s at step s, so the mean over steps 1 ... S is 0.5 d (S + 1) / 2, i.e. 0.5 (S + 1) / 2 in
  units of d; a step that throws the first particle out of the bounds at step k diverges at k and completes k - 1
  steps (the
  rollout loop's convention, `pitstudio.granular.rollout`);
- the ranking, written out from the rule: the larger completed fraction first, then the smaller error, then the
smaller scale.
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest
import torch
from pitstudio_pipeline.surrogates.gns import train

D = 0.04
DT = 0.01


def static_rollout(n: int = 12, frames: int = 30, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    x0 = rng.uniform(0.2, 0.8, (n, 2)).astype(np.float32)
    return {
        "positions": np.repeat(x0[None], frames, axis=0),
        "particle_types": np.zeros(n, dtype=np.int64),
        "bounds": np.array([0.0, 0.0, 1.0, 1.0], dtype=np.float32),
        "d": D,
        "dt": DT,
        "geometry_id": f"g{seed}",
    }


def hold_step(pos, vel, types, bounds, index, mask):
    return pos.copy(), vel.copy()


def drift_step(per_step: float):
    def step(pos, vel, types, bounds, index, mask):
        new = pos.copy()
        new[:, 0] += per_step
        return new, vel.copy()

    return step


def explode_step(k: int):
    calls = {"n": 0}

    def step(pos, vel, types, bounds, index, mask):
        calls["n"] += 1
        new = pos.copy()
        if calls["n"] >= k:
            new[0, 0] = 50.0  # far beyond the bounds plus R
        return new, vel.copy()

    return step


@pytest.mark.req("FR-011-04")
def test_011_a_step_that_holds_the_static_reference_completes_every_step_with_zero_error() -> None:
    probe = train.rollout_probe(hold_step, [static_rollout(seed=1), static_rollout(seed=2)], steps=20)
    assert probe["steps_requested"] == 20
    assert probe["divergence_steps"] == [None, None]
    assert probe["steps_completed"] == [20, 20]
    assert probe["completed_fraction"] == pytest.approx(1.0)
    assert probe["position_error_d"] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.req("FR-011-04")
def test_011_the_position_error_of_a_drifting_step_is_the_hand_computed_mean_in_particle_diameters() -> None:
    steps = 10
    probe = train.rollout_probe(drift_step(0.5 * D), [static_rollout(seed=3)], steps=steps)
    expected = 0.5 * (steps + 1) / 2.0  # mean over s = 1 ... S of 0.5 s (in d)
    assert probe["position_error_d"] == pytest.approx(expected, rel=1e-4)
    assert probe["divergence_steps"] == [None]


@pytest.mark.req("FR-011-04")
def test_011_a_step_that_leaves_the_domain_diverges_at_that_step_and_counts_the_completed_steps() -> None:
    probe = train.rollout_probe(explode_step(7), [static_rollout(seed=4)], steps=20)
    assert probe["divergence_steps"] == [7]
    assert probe["steps_completed"] == [6]
    assert probe["completed_fraction"] == pytest.approx(6 / 20)
    assert math.isfinite(probe["position_error_d"])  # the error of the steps that were completed


@pytest.mark.req("FR-011-04")
def test_011_the_probe_never_asks_for_more_steps_than_a_rollout_has_frames() -> None:
    short = static_rollout(frames=6, seed=5)  # 5 reference steps after frame 0
    probe = train.rollout_probe(hold_step, [short], steps=40)
    assert probe["steps_requested"] == 5
    assert probe["steps_completed"] == [5]


@pytest.mark.req("FR-011-04")
@pytest.mark.parametrize("steps", [0, -3, 2.5, True])
def test_011_hostile_probe_arguments_are_refused(steps) -> None:
    with pytest.raises(ValueError, match=r".+"):
        train.rollout_probe(hold_step, [static_rollout()], steps=steps)


@pytest.mark.req("FR-011-04")
def test_011_a_probe_without_rollouts_is_refused() -> None:
    with pytest.raises(ValueError, match=r".+"):
        train.rollout_probe(hold_step, [], steps=5)


def cand(scale: float, completed: float, error: float) -> dict:
    return {"scale": scale, "val_loss": 0.3, "rollout": {"completed_fraction": completed, "position_error_d": error}}


@pytest.mark.req("FR-011-04")
def test_011_the_ranking_prefers_completion_then_error_then_the_smaller_scale() -> None:
    cands = [cand(0.0, 0.4, 0.1), cand(0.05, 1.0, 3.0), cand(0.1, 1.0, 1.0), cand(0.2, 0.9, 0.0)]
    assert train.choose_by_rollout(cands) == 0.1  # 1.0 completed, the smaller error of the two complete candidates
    tie = [cand(0.2, 1.0, 1.0), cand(0.05, 1.0, 1.0)]
    assert train.choose_by_rollout(tie) == 0.05
    assert (
        train.choose_by_rollout([cand(0.2, 0.0, math.inf)]) == 0.2
    )  # a single candidate is chosen even if it diverges


@pytest.mark.req("FR-011-04")
def test_011_the_ranking_refuses_candidates_without_a_rollout_record() -> None:
    with pytest.raises(ValueError, match=r".+"):
        train.choose_by_rollout([{"scale": 0.1, "val_loss": 0.3}])
    with pytest.raises(ValueError, match=r".+"):
        train.choose_by_rollout([])


@pytest.mark.req("FR-011-04")
def test_011_the_config_validates_the_selection_mode_and_the_probe_sizes() -> None:
    base = {"noise_scales": [0.0], "epochs": 1, "batch_size": 1, "lr": 1e-3, "connectivity_radius": 0.1}
    cfg = train.validate_config(base)
    assert cfg["noise_selection"] == "val_loss"  # the default keeps the validation-loss rule of T-011-014
    assert cfg["rollout_steps"] >= 1
    assert cfg["rollout_geometries"] >= 1
    assert train.validate_config({**base, "noise_selection": "rollout"})["noise_selection"] == "rollout"
    for bad in ({"noise_selection": "nope"}, {"rollout_steps": 0}, {"rollout_geometries": 0}, {"rollout_steps": 1.5}):
        with pytest.raises(ValueError, match=r".+"):
            train.validate_config({**base, **bad})


class Splits:
    def __init__(self, train_r, val_r):
        self._data = {"train": train_r, "val": val_r}
        self.reads: list[str] = []

    def rollouts(self, name: str):
        self.reads.append(name)
        if name == "test":
            raise AssertionError("the test split was read during training")
        return self._data[name]


def free_fall_rollout(seed: int, accel: tuple[float, float], n: int = 8, frames: int = 14) -> dict:
    rng = np.random.default_rng(seed)
    x0 = rng.uniform(0.3, 0.7, (n, 2))
    t = np.arange(frames)[:, None, None] * DT
    pos = (x0[None] + 0.5 * np.array(accel)[None, None, :] * t**2).astype(np.float32)
    return {
        "positions": pos,
        "particle_types": np.zeros(n, dtype=np.int64),
        "bounds": np.array([-5, -5, 5, 5], dtype=np.float32),
        "d": D,
        "dt": DT,
        "geometry_id": f"g{seed}",
    }


CONFIG = {
    "noise_scales": [0.0, 0.01, 0.05],
    "epochs": 4,
    "pilot_epochs": 2,
    "batch_size": 2,
    "lr": 3e-3,
    "latent": 8,
    "steps": 1,
    "connectivity_radius": 0.1,
    "noise_selection": "rollout",
    "rollout_steps": 6,
    "rollout_geometries": 2,
}


@pytest.mark.req("FR-011-04")
def test_011_training_with_rollout_selection_records_every_candidate_and_chooses_by_the_rule() -> None:
    splits = Splits(
        [free_fall_rollout(i, a) for i, a in enumerate(((1.0, -9.8), (2.0, -9.0), (-1.0, -10.5)))],
        [free_fall_rollout(100 + i, a) for i, a in enumerate(((1.5, -9.4), (0.0, -9.9), (0.5, -9.7)))],
    )
    res = train.train_gns(splits, dict(CONFIG), seed=0)
    assert "test" not in splits.reads
    cands = res.log["noise_candidates"]
    assert [c["scale"] for c in cands] == CONFIG["noise_scales"]
    for c in cands:
        probe = c["rollout"]
        assert len(probe["divergence_steps"]) == CONFIG["rollout_geometries"]
        assert probe["steps_requested"] == CONFIG["rollout_steps"]
        assert 0.0 <= probe["completed_fraction"] <= 1.0
        assert np.isfinite(c["val_loss"])  # the one-step loss stays recorded
    assert res.log["chosen_noise_scale"] == train.choose_by_rollout(copy.deepcopy(cands))
    assert res.checkpoint["noise_scale"] == res.log["chosen_noise_scale"]
    assert res.log["noise_selection"] == "rollout"
    assert res.checkpoint["selected_on"] == "validation"
    assert isinstance(next(res.model.parameters()), torch.nn.Parameter)


@pytest.mark.req("FR-011-04")
def test_011_the_default_selection_still_records_no_rollout_probe() -> None:
    splits = Splits([free_fall_rollout(1, (1.0, -9.8))], [free_fall_rollout(101, (1.5, -9.4))])
    res = train.train_gns(splits, dict(CONFIG, noise_selection="val_loss"), seed=0)
    assert res.log["noise_selection"] == "val_loss"
    assert all("rollout" not in c for c in res.log["noise_candidates"])
    best = min(res.log["noise_candidates"], key=lambda c: c["val_loss"])["scale"]
    assert res.log["chosen_noise_scale"] == best


# ------------------------------------------------------------------ sample weighting (long steady-pour rollouts)


def frame_index(frames_per_rollout: list[int]) -> list[tuple[int, int]]:
    return [(r, t) for r, n in enumerate(frames_per_rollout) for t in range(5, n - 1)]


@pytest.mark.req("FR-011-04")
def test_011_rollout_weighting_gives_every_rollout_the_same_share_of_the_samples() -> None:
    """A 3,000-frame steady pour next to 250-frame collapses must not take 86 % of the samples (hand shares: 1/3
    each)."""
    sizes = [3000, 250, 250]
    rollouts = [{"positions": np.zeros((n, 1, 2), dtype=np.float32)} for n in sizes]
    index = frame_index(sizes)
    rng = np.random.default_rng(0)
    by_frames = train.sample_order(index, rollouts, 300, rng, weighting="frames")
    by_rollout = train.sample_order(index, rollouts, 300, np.random.default_rng(0), weighting="rollout")
    share_frames = np.bincount([index[i][0] for i in by_frames], minlength=3) / 300
    share_rollout = np.bincount([index[i][0] for i in by_rollout], minlength=3) / 300
    assert share_frames[0] > 0.8  # the default is the uniform draw over (rollout, frame) pairs: unchanged
    assert np.allclose(share_rollout, 1 / 3, atol=0.08)
    assert len(set(by_rollout.tolist())) == 300  # without replacement
    assert len(by_frames) == len(by_rollout) == 300


@pytest.mark.req("FR-011-04")
def test_011_the_default_weighting_is_the_original_permutation_prefix() -> None:
    sizes = [30, 20]
    rollouts = [{"positions": np.zeros((n, 1, 2), dtype=np.float32)} for n in sizes]
    index = frame_index(sizes)
    got = train.sample_order(index, rollouts, 17, np.random.default_rng([3, 4]), weighting="frames")
    assert np.array_equal(got, np.random.default_rng([3, 4]).permutation(len(index))[:17])


@pytest.mark.req("FR-011-04")
def test_011_the_config_validates_the_weighting() -> None:
    base = {"noise_scales": [0.0], "epochs": 1, "batch_size": 1, "lr": 1e-3, "connectivity_radius": 0.1}
    assert train.validate_config(base)["sample_weighting"] == "frames"
    assert train.validate_config({**base, "sample_weighting": "rollout"})["sample_weighting"] == "rollout"
    with pytest.raises(ValueError, match=r".+"):
        train.validate_config({**base, "sample_weighting": "family"})
