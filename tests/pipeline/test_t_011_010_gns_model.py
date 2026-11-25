"""T-011-010 - FR-011-01, P-011-01, P-011-02, P-011-05: GNS step (inputs, features, encode-process-decode, Euler,
    symmetries).

Oracles (independent of the code under test; plan 011 test strategy FR-011-01):
- shapes from DC-011-02 (positions [N, 2], velocities [N, 5, 2], particle type [N], bounds [4], neighbour index and mask
  [N, 32] in; acceleration [N, 2] out);
- parameter count by hand from the layer sizes (Sanchez-Gonzalez et al. 2020, "Learning to Simulate Complex Physics with
  Graph Networks", MLPs of two hidden layers of width 128): one processor step has an edge MLP 3 x 128 -> 128 ->
      128 -> 128
  and a node MLP 2 x 128 -> 128 -> 128 -> 128, i.e. at least (384 x 128 + 128) + (256 x 128 + 128) = 82,176 weights
      in its two
  input layers alone, so 10 steps carry at least 821,760 parameters; with the hidden layers, the encoders and the
      decoder the
  hand total is about 1.6 x 10^6 (the spec says about 1.5 x 10^6): accepted range [1.2 x 10^6, 1.8 x 10^6];
- semi-implicit Euler by hand (FR-011-01): a = (0.3, -0.4) m/s^2, dt_f = 0.01 s, v_last = (0.5, -0.25) m/s, x = (1,
    2) m give
  v_new = v_last + a dt_f = (0.503, -0.254) and x_new = x + v_new dt_f = (1.00503, 1.99746); the history is shifted
      by one;
- the metamorphic relations P-011-01 (permutation equivariance), P-011-02 (translation invariance), P-011-05
    (padded gather
  aggregation equals scatter-add), and the wall-distance clipping at R (moving the bounds outwards beyond R of
      every particle
  changes nothing), checked on random weights and random packings;
- the radius graph of tests/property/test_t_011_011_radius_graph.py as the graph source (brute-force verified there).

Expected public API (module `pitstudio_pipeline.surrogates.gns.model`, package under `pipeline/src/`; the graph
    builder is
`pitstudio.granular.graph.build_radius_graph`):

    GnsStep(*, connectivity_radius: float, frame_interval: float, n_particle_types: int, latent: int = 128, steps:
        int = 10,
            aggregation: str = "padded", acceleration_mean=(0.0, 0.0), acceleration_std=(1.0, 1.0))   (torch.nn.Module)
        attributes: latent, steps, history (= 5), k_max (= 32), connectivity_radius, frame_interval, aggregation
        ("padded" = Gather + masked sum, "scatter" = scatter-add with the same weights; assignable), decoder (a
        torch.nn.Sequential whose last module is the torch.nn.Linear(latent, 2) output layer, so that its bias can
            be set).
        forward(positions, velocities, particle_type, bounds, neighbour_index, neighbour_mask) -> acceleration [N,
            2] float32
            node features: the 5 velocities, a type embedding, wall distances clipped at R; edge features: (x_i -
                x_j) / R and
            its norm; no absolute position feature; acceleration = decoder output * acceleration_std +
                acceleration_mean (m/s^2).
        advance(positions, velocities, particle_type, bounds, neighbour_index, neighbour_mask) -> (positions_next
            [N, 2],
            velocities_next [N, 5, 2]): v_new = v[:, -1] + a dt_f, x_new = x + v_new dt_f, history shifted by one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")  # runs in the pipeline/ job; skipped in the root job (plan 011, technical context)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.gns.model import GnsStep  # noqa: E402

from pitstudio.granular.graph import build_radius_graph  # noqa: E402

R = 0.5
DT = 0.01
K = 32


def make_model(seed: int, *, aggregation: str = "padded", n_types: int = 2) -> GnsStep:
    torch.manual_seed(seed)
    model = GnsStep(connectivity_radius=R, frame_interval=DT, n_particle_types=n_types, aggregation=aggregation)
    with torch.no_grad():
        for p in model.parameters():
            p.normal_(0.0, 0.1)  # random weights (P-011-01 domain)
    return model


def packing(seed: int, n: int, side: float = 3.0):
    rng = np.random.default_rng(seed)
    pos = rng.uniform(0.2, side, (n, 2)).astype(np.float32)
    vel = rng.normal(0.0, 0.3, (n, 5, 2)).astype(np.float32)
    types = rng.integers(0, 2, n)
    bounds = np.array([0.0, 0.0, side + 0.2, side + 0.2], dtype=np.float32)
    return pos, vel, types, bounds


def tensors(pos, vel, types, bounds, graph=None, *, index=None, mask=None):
    index = graph.neighbour_index if index is None else index
    mask = graph.neighbour_mask if mask is None else mask
    return (
        torch.from_numpy(pos),
        torch.from_numpy(vel),
        torch.from_numpy(np.asarray(types, dtype=np.int64)),
        torch.from_numpy(bounds),
        torch.from_numpy(np.asarray(index, dtype=np.int64)),
        torch.from_numpy(np.asarray(mask, dtype=bool)),
    )


def run(model: GnsStep, pos, vel, types, bounds, graph=None) -> np.ndarray:
    graph = graph if graph is not None else build_radius_graph(pos, R)
    with torch.no_grad():
        return model(*tensors(pos, vel, types, bounds, graph)).numpy()


# ------------------------------------------------------------------ FR-011-01


@pytest.mark.req("FR-011-01")
def test_the_step_maps_the_dc_011_02_inputs_to_an_acceleration_of_shape_n_by_2() -> None:
    pos, vel, types, bounds = packing(1, 40)
    graph = build_radius_graph(pos, R)
    with torch.no_grad():
        a = make_model(1)(*tensors(pos, vel, types, bounds, graph))
    assert tuple(a.shape) == (40, 2)
    assert a.dtype == torch.float32
    assert torch.isfinite(a).all()


@pytest.mark.req("FR-011-01")
def test_architecture_constants_and_parameter_count_match_the_hand_calculation() -> None:
    model = make_model(2)
    assert model.latent == 128
    assert model.steps == 10
    assert model.history == 5
    assert model.k_max == 32
    n_params = sum(p.numel() for p in model.parameters())
    assert 1_200_000 <= n_params <= 1_800_000  # about 1.5 x 10^6; processor alone >= 821,760


@pytest.mark.req("FR-011-01")
def test_a_zero_network_gives_zero_acceleration_and_the_euler_update_is_a_constant_velocity_drift() -> None:
    model = GnsStep(connectivity_radius=R, frame_interval=DT, n_particle_types=1)
    with torch.no_grad():
        for p in model.parameters():
            p.zero_()
    pos = np.array([[1.0, 2.0], [1.3, 2.1]], dtype=np.float32)
    vel = np.zeros((2, 5, 2), dtype=np.float32)
    vel[:, -1, :] = [[0.5, -0.25], [0.1, 0.2]]
    graph = build_radius_graph(pos, R)
    args = tensors(pos, vel, np.zeros(2), np.array([0, 0, 4, 4], dtype=np.float32), graph)
    with torch.no_grad():
        a = model(*args)
        new_pos, new_vel = model.advance(*args)
    assert np.allclose(a.numpy(), 0.0, atol=1e-7)
    assert np.allclose(new_pos.numpy(), pos + vel[:, -1, :] * DT, atol=1e-6)
    assert np.allclose(new_vel.numpy()[:, -1, :], vel[:, -1, :], atol=1e-7)


@pytest.mark.req("FR-011-01")
def test_semi_implicit_euler_uses_the_new_velocity_for_the_position_by_hand() -> None:
    model = GnsStep(connectivity_radius=R, frame_interval=DT, n_particle_types=1)
    with torch.no_grad():
        for p in model.parameters():
            p.zero_()
        model.decoder[-1].bias.copy_(torch.tensor([0.3, -0.4]))  # constant decoder output, identity normalisation
    pos = np.array([[1.0, 2.0]], dtype=np.float32)
    vel = np.zeros((1, 5, 2), dtype=np.float32)
    vel[0, :, :] = np.arange(10, dtype=np.float32).reshape(5, 2) * 0.01
    vel[0, -1, :] = [0.5, -0.25]
    args = tensors(  # a single particle without neighbours
        pos,
        vel,
        np.zeros(1),
        np.array([0, 0, 4, 4], dtype=np.float32),
        index=np.zeros((1, K), dtype=np.int64),
        mask=np.zeros((1, K), dtype=bool),
    )
    with torch.no_grad():
        a = model(*args)
        new_pos, new_vel = model.advance(*args)
    assert np.allclose(a.numpy(), [[0.3, -0.4]], atol=1e-6)
    assert np.allclose(new_vel.numpy()[0, -1], [0.503, -0.254], atol=1e-6)  # v_last + a dt_f
    assert np.allclose(new_pos.numpy()[0], [1.00503, 1.99746], atol=1e-6)  # x + v_new dt_f
    assert np.allclose(new_vel.numpy()[0, :-1], vel[0, 1:], atol=1e-7)  # history shifted by one


@pytest.mark.req("FR-011-01")
def test_wall_distances_are_clipped_at_r_so_far_walls_do_not_matter() -> None:
    model = make_model(3)
    pos, vel, types, _ = packing(3, 30, side=2.0)
    graph = build_radius_graph(pos, R)
    near = np.array(
        [-8.0, -8.0, 10.0, 10.0], dtype=np.float32
    )  # every wall is farther than R = 0.5 from every particle
    far = np.array([-20.0, -20.0, 25.0, 25.0], dtype=np.float32)
    assert np.allclose(run(model, pos, vel, types, near, graph), run(model, pos, vel, types, far, graph), atol=1e-6)


@pytest.mark.req("FR-011-01")
def test_a_wall_inside_the_radius_changes_the_acceleration() -> None:
    model = make_model(4)
    pos, vel, types, _ = packing(4, 30, side=2.0)
    graph = build_radius_graph(pos, R)
    clear = np.array([-8.0, -8.0, 10.0, 10.0], dtype=np.float32)
    close = np.array(
        [float(pos[:, 0].min()) - 0.1, -8.0, 10.0, 10.0], dtype=np.float32
    )  # left wall 0.1 < R from a particle
    assert not np.allclose(
        run(model, pos, vel, types, clear, graph), run(model, pos, vel, types, close, graph), atol=1e-6
    )


@pytest.mark.req("FR-011-01")
def test_the_particle_type_changes_the_acceleration_through_the_embedding() -> None:
    model = make_model(5)
    pos, vel, types, bounds = packing(5, 25)
    graph = build_radius_graph(pos, R)
    other = 1 - np.asarray(types)
    assert not np.allclose(
        run(model, pos, vel, types, bounds, graph), run(model, pos, vel, other, bounds, graph), atol=1e-6
    )


# ------------------------------------------------------------------ P-011-01 / P-011-02 / P-011-05


@pytest.mark.req("P-011-01")
@pytest.mark.parametrize("seed", range(6))
def test_permuting_the_particles_permutes_the_accelerations(seed: int) -> None:
    n = 20 + 17 * seed
    model = make_model(seed)
    pos, vel, types, bounds = packing(seed + 10, n)
    base_graph = build_radius_graph(pos, R)
    assert base_graph.overflow_count == 0
    perm = np.random.default_rng(seed).permutation(n)
    a = run(model, pos, vel, types, bounds, base_graph)
    a_perm = run(model, pos[perm], vel[perm], np.asarray(types)[perm], bounds)
    scale = np.abs(a).max()
    assert scale > 1e-6
    assert np.abs(a_perm - a[perm]).max() <= 1e-5 * scale


@pytest.mark.req("P-011-02")
@pytest.mark.parametrize("shift", [-10.0, -3.7, 0.0, 2.5, 10.0])
def test_shifting_every_particle_and_the_bounds_in_x_leaves_the_accelerations_unchanged(shift: float) -> None:
    model = make_model(7)
    pos, vel, types, bounds = packing(7, 60)
    graph = build_radius_graph(pos, R)
    a = run(model, pos, vel, types, bounds, graph)
    moved = pos + np.array([shift, 0.0], dtype=np.float32)
    bounds_moved = bounds + np.array([shift, 0.0, shift, 0.0], dtype=np.float32)
    b = run(model, moved, vel, types, bounds_moved, graph)  # same graph: the relation is exact under a shift
    assert np.abs(b - a).max() <= 1e-5 * np.abs(a).max()


@pytest.mark.req("P-011-05")
@pytest.mark.parametrize("seed", range(4))
def test_padded_gather_aggregation_equals_scatter_add_on_the_same_graph(seed: int) -> None:
    pos, vel, types, bounds = packing(seed + 20, 50 + 30 * seed)
    graph = build_radius_graph(pos, R)
    padded = make_model(seed, aggregation="padded")
    scatter = make_model(seed, aggregation="scatter")  # the same seed gives the same weights
    a = run(padded, pos, vel, types, bounds, graph)
    b = run(scatter, pos, vel, types, bounds, graph)
    assert np.allclose(a, b, rtol=1e-5, atol=1e-6 * np.abs(a).max())


@pytest.mark.req("P-011-05")
def test_switching_the_aggregation_attribute_on_one_model_gives_the_same_result() -> None:
    pos, vel, types, bounds = packing(30, 70)
    graph = build_radius_graph(pos, R)
    model = make_model(30)
    a = run(model, pos, vel, types, bounds, graph)
    model.aggregation = "scatter"
    b = run(model, pos, vel, types, bounds, graph)
    assert np.allclose(a, b, rtol=1e-5, atol=1e-6 * np.abs(a).max())


@pytest.mark.req("P-011-05")
def test_masked_entries_of_the_padded_layout_do_not_contribute() -> None:
    model = make_model(31)
    pos, vel, types, bounds = packing(31, 40)
    graph = build_radius_graph(pos, R)
    a = run(model, pos, vel, types, bounds, graph)
    index = graph.neighbour_index.copy()
    rng = np.random.default_rng(0)
    index[~graph.neighbour_mask] = rng.integers(0, 40, int((~graph.neighbour_mask).sum()))  # junk, but in range
    with torch.no_grad():
        b = model(*tensors(pos, vel, types, bounds, index=index, mask=graph.neighbour_mask)).numpy()
    assert np.allclose(a, b, atol=1e-6)
