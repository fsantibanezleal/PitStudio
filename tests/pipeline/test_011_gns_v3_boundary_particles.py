"""GNS boundary particles (T-011-014 loss and noise, T-011-015 evaluation, T-011-017 rollout; FR-011-03, -04, -05, -12).

Rigid obstacles (a funnel, a platform) are nodes of the graph with a type of their own, as in Sanchez-Gonzalez et al.
2020 (arXiv:2002.09405), Appendix B.2 (particle type as a node feature) and B.3 (obstacles as boundary particles,
masked out of the loss). Here, further: they get no input noise, they are not in the normalisation statistics, a rollout
takes their positions from the reference instead of predicting them, and the observables read grains only.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch
from pitstudio.granular.observables import observables
from pitstudio.granular.rollout import run_rollout
from pitstudio_pipeline.surrogates.gns import data, evaluate, infer, train
from pitstudio_pipeline.surrogates.gns.model import GnsStep

D, DT = 0.01, 0.01
NAMES = ["grain", "boundary"]


def _rollout(t: int = 12, n_grain: int = 6, n_wall: int = 4, seed: int = 0) -> dict:
    """Grains fall onto a static wall row; the last `n_wall` particles are the wall."""
    rng = np.random.default_rng(seed)
    pos = np.zeros((t, n_grain + n_wall, 2), dtype=np.float32)
    pos[:, :n_grain, 0] = rng.uniform(0.1, 0.2, n_grain)[None]
    pos[:, :n_grain, 1] = 0.5 - np.arange(t)[:, None] * 0.002
    pos[:, n_grain:, 0] = np.linspace(0.05, 0.25, n_wall)[None]
    pos[:, n_grain:, 1] = 0.1
    types = np.array([0] * n_grain + [1] * n_wall)
    return {
        "positions": pos,
        "particle_types": types,
        "boundary": types == 1,
        "bounds": np.array([0.0, 0.0, 0.5, 1.0], dtype=np.float32),
        "d": D,
        "dt": DT,
        "geometry_id": "g",
        "family": "column-collapse",
        "seed": 1,
    }


@pytest.mark.req("FR-011-03")
def test_011_the_boundary_mask_is_read_from_the_type_names_not_from_an_index_guess() -> None:
    types = np.array([0, 1, 1, 0])
    assert data.boundary_mask(NAMES, types).tolist() == [False, True, True, False]
    assert data.boundary_mask(["grain"], np.zeros(3, dtype=np.int64)).tolist() == [False] * 3
    assert data.boundary_mask(["boundary", "grain"], np.array([0, 1])).tolist() == [True, False]


@pytest.mark.req("FR-011-03")
def test_011_the_loader_gives_training_and_evaluation_views_a_boundary_mask(tmp_path) -> None:
    import json

    import zarr

    t, n = 3, 5
    types = np.array([0, 0, 0, 1, 1], dtype=np.uint8)
    store = tmp_path / "payload" / "r.zarr"
    g = zarr.open_group(str(store), mode="w")
    g.create_array("positions", data=np.zeros((t, n, 2), dtype=np.float32))
    g.create_array("type_index", data=types)
    g.create_array("frame_times_s", data=np.arange(t) * DT)
    from pitstudio_pipeline.surrogates.digest import zarr_digest

    meta = json.loads(
        (
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "specs/011-surrogates/contracts/examples/granular-rollout.valid.json"
        ).read_text(encoding="utf-8")
    )
    meta.update(
        particle_count=n,
        particle_types=NAMES,
        frame_times_s=[0.0, DT, 2 * DT],
        store={"format": "zarr", "path": "payload/r.zarr", "sha256": zarr_digest(store)},
        particle_diameter_m=D,
        connectivity_radius_m=2.5 * D,
        bounds_m=[0.0, 0.0, 1.0, 1.0],
        frame_interval_s=DT,
    )
    (tmp_path / "meta").mkdir()
    mp = tmp_path / "meta" / "r.json"
    mp.write_text(json.dumps(meta), encoding="utf-8")
    pre = data.s10_preprocess(mp, root=tmp_path)
    assert pre.boundary.tolist() == [False, False, False, True, True]
    assert data.to_training_rollout(pre)["boundary"].tolist() == [False, False, False, True, True]
    geometry = data.evaluation_geometries(tmp_path / "meta", root=tmp_path, geometry_ids=[meta["geometry_id"]])[0]
    assert geometry["references"][0]["boundary"].tolist() == [False, False, False, True, True]


@pytest.mark.req("FR-011-04")
def test_011_a_sample_masks_the_boundary_out_of_the_loss_and_gives_it_no_noise() -> None:
    r = _rollout()
    s = train.make_sample(r, 6, noise_scale=0.5, velocity_std=(1.0, 1.0), seed=3)
    assert s["loss_mask"].tolist() == [True] * 6 + [False] * 4
    assert (s["velocities"][6:] == 0.0).all()  # static solids: no velocity, no noise on it
    assert np.abs(s["velocities"][:6]).max() > 0.0
    plain = train.make_sample(r, 6, noise_scale=0.0)
    assert np.array_equal(s["target_acceleration"][6:], plain["target_acceleration"][6:])


@pytest.mark.req("FR-011-04")
def test_011_a_rollout_without_a_boundary_key_trains_on_every_particle() -> None:
    r = _rollout()
    del r["boundary"]
    assert train.make_sample(r, 6)["loss_mask"].all()


@pytest.mark.req("FR-011-04")
def test_011_the_one_step_loss_ignores_the_boundary_nodes() -> None:
    torch.manual_seed(0)
    model = GnsStep(connectivity_radius=2.5 * D, frame_interval=DT, n_particle_types=2, latent=8, steps=2)
    r = _rollout()
    stats = train.compute_stats([r])
    sample = train.make_sample(r, 6, radius=2.5 * D)
    batch = train.collate([sample], torch.device("cpu"))
    base = float(train.one_step_loss(model, batch, stats=stats))
    poisoned = dict(batch)
    target = batch["target_acceleration"].clone()
    target[6:] = 1.0e6  # an absurd target on the wall: it must not matter
    poisoned["target_acceleration"] = target
    assert float(train.one_step_loss(model, poisoned, stats=stats)) == pytest.approx(base)
    unmasked = {k: v for k, v in poisoned.items() if k != "loss_mask"}
    assert float(train.one_step_loss(model, unmasked, stats=stats)) > 1.0e3  # the mask is what protects the loss
    grains_only = torch.mean(
        (
            (
                model.acceleration_unchecked(
                    batch["positions"],
                    batch["velocities"],
                    batch["particle_type"],
                    batch["bounds"],
                    batch["neighbour_index"],
                    batch["neighbour_mask"],
                )[:6]
                - torch.as_tensor(stats["acceleration"]["mean"])
            )
            / torch.as_tensor(stats["acceleration"]["std"])
            - (batch["target_acceleration"][:6] - torch.as_tensor(stats["acceleration"]["mean"]))
            / torch.as_tensor(stats["acceleration"]["std"])
        )
        ** 2
    )
    assert base == pytest.approx(float(grains_only), rel=1e-5)


@pytest.mark.req("FR-011-04")
def test_011_the_normalisation_statistics_come_from_grains_alone() -> None:
    r = _rollout()
    with_wall = train.compute_stats([r])
    grains = {**r, "positions": r["positions"][:, :6], "boundary": np.zeros(6, dtype=bool)}
    assert with_wall["velocities"] == train.compute_stats([grains])["velocities"]
    assert with_wall["acceleration"] == train.compute_stats([grains])["acceleration"]


def _fall(pos, vel, types, bounds, index, mask):
    """A model-free 'surrogate': every particle falls 1 mm per step, unless a wall particle lies just below it."""
    new = pos.copy()
    below = np.zeros(len(pos), dtype=bool)
    for i in range(len(pos)):
        for k in range(index.shape[1]):
            if mask[i, k]:
                j = index[i, k]
                if types[j] == 1 and abs(pos[j, 0] - pos[i, 0]) < 0.6 * D and 0.0 < pos[i, 1] - pos[j, 1] < 1.2 * D:
                    below[i] = True
    new[~below, 1] -= 0.001
    new[types == 1, 1] -= 0.001  # a model that 'predicts' the wall lets it fall too
    history = np.concatenate([vel[:, 1:], np.zeros((len(pos), 1, 2), dtype=np.float32)], axis=1)
    return new.astype(np.float32), history.astype(np.float32)


def _held_state() -> dict:
    """Grains resting a hair above a wall row."""
    pos = np.array([[0.100, 0.1105], [0.110, 0.1105], [0.100, 0.1], [0.110, 0.1]], dtype=np.float32)
    types = np.array([0, 0, 1, 1])
    return {
        "positions": pos,
        "velocities": np.zeros((4, 5, 2), dtype=np.float32),
        "particle_type": types,
        "bounds": np.array([0.0, 0.0, 0.5, 1.0], dtype=np.float32),
        "d": D,
        "dt": DT,
        "boundary": types == 1,
        "boundary_positions": np.repeat(pos[None, 2:], 21, axis=0),
    }


@pytest.mark.req("FR-011-12")
def test_011_a_rollout_that_keeps_the_wall_keeps_the_grains_it_holds_held() -> None:
    state = _held_state()
    kept = infer.make_surrogate(_fall)(state, 20)
    assert kept.status == "ok"
    assert np.array_equal(kept.positions[-1][2:], state["positions"][2:])  # the wall is the reference, not predicted
    assert np.array_equal(kept.positions[-1][:2], state["positions"][:2])  # and the grains it holds stay on it
    # the same step with no reference wall: the wall is predicted, falls, and the grains go with it
    free = {k: v for k, v in state.items() if k not in ("boundary", "boundary_positions")}
    fallen = infer.make_surrogate(_fall)(free, 20)
    assert fallen.positions[-1][:2, 1].max() < state["positions"][:2, 1].min() - 0.015


@pytest.mark.req("FR-011-12")
def test_011_the_held_boundary_takes_its_reference_velocity_and_follows_a_moving_solid() -> None:
    state = _held_state()
    ref = np.repeat(state["positions"][None, 2:], 6, axis=0)
    ref[:, :, 0] += np.arange(6)[:, None] * 0.001  # a solid sliding in x
    state["boundary_positions"] = ref
    seen = []

    def spy(pos, vel, types, bounds, index, mask):
        seen.append(vel[2:, -1].copy())
        return pos, vel

    out = infer.make_surrogate(spy)(state, 5)
    assert np.allclose(out.positions[3, 2:], ref[3], atol=1e-7)
    assert np.allclose(seen[-1][:, 0], 0.001 / DT, atol=1e-4)  # the velocity history of the solid is the reference one


@pytest.mark.req("FR-011-12")
def test_011_the_rollout_probe_holds_the_wall_and_measures_the_error_on_grains() -> None:
    r = _rollout(t=8)
    out = train.rollout_probe(lambda pos, vel, types, b, i, m: (pos.copy(), vel.copy()), [r], steps=5)
    # a frozen surrogate: the wall (held at its reference) adds no error, so the error is the grains' alone
    ref = r["positions"]
    expect = np.mean([np.linalg.norm(ref[0][:6] - ref[s][:6], axis=1).mean() / D for s in range(1, 6)])
    assert out["position_error_d"] == pytest.approx(float(expect), rel=1e-5)


@pytest.mark.req("FR-011-05")
def test_011_the_evaluation_reads_the_observables_on_grains_and_holds_the_wall() -> None:
    d = 0.01
    rng = np.random.default_rng(4)
    n = 600
    # a settled column heap (grains) plus a wall of boundary particles standing far to the right
    x = rng.uniform(0.0, 0.3, n)
    y = rng.uniform(0.0, 1.0, n) * np.maximum(0.0, 0.3 - x) * 0.6 + 0.005
    wall = np.column_stack([np.full(40, 0.9), np.linspace(0.0, 0.6, 40)])
    frames = np.concatenate([np.column_stack([x, y]), wall])[None].repeat(4, axis=0).astype(np.float32)
    types = np.array([0] * n + [1] * 40)
    boundary = types == 1
    geom = {
        "geometry_id": "g",
        "family": "column-collapse",
        "geometry": {"aspect_ratio": 1.0, "column_width_m": 0.3},
        "d": d,
        "dt": DT,
        "bounds": [0.0, 0.0, 1.0, 1.0],
        "references": [
            {"seed": s, "positions": frames, "particle_types": types, "boundary": boundary} for s in (1, 2, 3)
        ],
    }
    truth = observables(frames[-1][:n], d=d, family="column-collapse", geometry=geom["geometry"])
    polluted = observables(frames[-1], d=d, family="column-collapse", geometry=geom["geometry"])
    assert polluted["run_out_m"] != pytest.approx(truth["run_out_m"])  # the wall would have changed the run-out
    surrogate = infer.make_surrogate(lambda pos, vel, t, b, i, m: (pos.copy(), vel.copy()))
    rec = evaluate.evaluate_held_out([geom], surrogate)["geometries"][0]
    assert rec["reference_runout_m"] == pytest.approx(truth["run_out_m"])
    assert rec["reference_repose_deg"] == pytest.approx(truth["repose_deg"])
    assert rec["surrogate_runout_m"] == pytest.approx(truth["run_out_m"])
    assert rec["delta_repose_deg"] == pytest.approx(0.0, abs=1e-9)
    assert max(rec["position_error_growth"]) == 0.0


@pytest.mark.req("FR-011-12")
def test_011_run_rollout_itself_is_unchanged_a_wrapped_step_is_all_it_sees() -> None:
    state = _held_state()
    res = run_rollout(
        lambda p, v, t, b, i, m: (p.copy(), v.copy()),
        state["positions"],
        state["velocities"],
        state["particle_type"],
        bounds=state["bounds"],
        radius=2.5 * D,
        n_steps=3,
    )
    assert res.status == "ok"
    assert np.array_equal(res.particle_types, state["particle_type"])
