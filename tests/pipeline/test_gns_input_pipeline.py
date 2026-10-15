"""GNS input pipeline (priority-0 fix of the green phase): torch radius graph, device sample path, prefetch, step log.

Oracles: the CPU builder `pitstudio.granular.graph.build_radius_graph` (FR-011-02, P-011-04: exact index and mask
arrays), the numpy `make_sample` path (the same samples through the device path), a lattice whose neighbour
distances tie (the order is by squared distance, then index) and hand-counted overflow.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
import torch
from pitstudio_pipeline.surrogates.gns import run_train, train
from pitstudio_pipeline.surrogates.gns.graph_torch import build_radius_graph_torch

from pitstudio.granular.graph import K_MAX, build_radius_graph

CPU = torch.device("cpu")


def both(pos: np.ndarray, radius: float, k_max: int = K_MAX, **kw):
    want = build_radius_graph(pos, radius, k_max)
    index, mask, overflow = build_radius_graph_torch(torch.as_tensor(pos), radius, k_max, **kw)
    return want, index.numpy(), mask.numpy(), overflow


@pytest.mark.parametrize(
    ("n", "radius", "k_max", "block"),
    [(1, 0.1, 32, 512), (5, 0.5, 32, 512), (300, 0.05, 32, 64), (900, 0.04, 8, 100), (1200, 0.02, 32, 512)],
)
def test_the_torch_radius_graph_equals_the_cpu_oracle_on_random_packings(n, radius, k_max, block) -> None:
    rng = np.random.default_rng(n)
    pos = rng.uniform(0.0, 0.4, size=(n, 2)).astype(np.float32)
    want, index, mask, overflow = both(pos, radius, k_max, block=block)
    assert index.dtype == np.int64
    assert mask.dtype == np.bool_
    assert np.array_equal(index, want.neighbour_index)
    assert np.array_equal(mask, want.neighbour_mask)
    assert overflow == want.overflow_count


def test_a_lattice_with_tied_distances_is_ordered_by_distance_then_index_like_the_oracle() -> None:
    xs, ys = np.meshgrid(np.arange(12), np.arange(12))
    pos = (np.stack([xs.ravel(), ys.ravel()], axis=1) * 0.01).astype(np.float32)
    want, index, mask, overflow = both(pos, 0.055)
    assert np.array_equal(index, want.neighbour_index)
    assert np.array_equal(mask, want.neighbour_mask)
    assert overflow == want.overflow_count > 0


def test_a_dense_slab_overflows_like_the_oracle_and_keeps_the_nearest_32() -> None:
    rng = np.random.default_rng(7)
    pos = rng.uniform(0.0, 0.1, size=(800, 2)).astype(np.float32)
    want, index, mask, overflow = both(pos, 0.05)
    assert overflow == want.overflow_count > 400
    assert mask.all(axis=1)[:10].any()
    assert np.array_equal(index, want.neighbour_index)


def test_a_pair_at_exactly_the_radius_is_not_connected_and_a_lonely_particle_points_at_itself() -> None:
    pos = np.array([[0.0, 0.0], [0.5, 0.0], [5.0, 5.0]], dtype=np.float32)
    want, index, mask, _ = both(pos, 0.5)
    assert not mask.any()
    assert np.array_equal(index, np.repeat(np.arange(3)[:, None], K_MAX, axis=1))
    assert np.array_equal(index, want.neighbour_index)


def rollout(seed: int, n: int = 40, frames: int = 9) -> dict:
    rng = np.random.default_rng(seed)
    start = rng.uniform(0.0, 0.2, size=(n, 2))
    drift = rng.normal(0.0, 1e-3, size=(1, n, 2))
    pos = start[None] + drift * np.arange(frames)[:, None, None]
    return {
        "positions": pos.astype(np.float32),
        "particle_types": np.zeros(n, dtype=np.int64),
        "bounds": np.array([0.0, 0.2, 0.0, 0.2]),
        "d": 0.01,
        "dt": 0.01,
    }


def test_the_device_sample_equals_the_numpy_sample_with_noise() -> None:
    r = rollout(3)
    kw = dict(radius=0.025, noise_scale=0.1, velocity_std=(0.2, 0.3), seed=11)
    old = train.make_sample(r, 6, **kw)
    new = train.make_sample(r, 6, device=CPU, **kw)
    for key, value in old.items():
        assert np.array_equal(np.asarray(value), torch.as_tensor(new[key]).numpy()), key
    a = train.collate([old, train.make_sample(r, 7, radius=0.025)], CPU)
    b = train.collate([new, train.make_sample(r, 7, radius=0.025, device=CPU)], CPU)
    for key in a:
        assert torch.equal(a[key], b[key]), key


def test_prefetch_keeps_the_order_and_ends() -> None:
    assert list(train._Prefetch(lambda: iter(range(50)), depth=2)) == list(range(50))


def test_prefetch_runs_ahead_of_the_consumer() -> None:
    made: list[int] = []

    def gen():
        for i in range(6):
            made.append(i)
            yield i

    feed = train._Prefetch(gen, depth=3)
    deadline = time.time() + 5
    while len(made) < 4 and time.time() < deadline:
        time.sleep(0.01)
    assert len(made) >= 4  # produced before the first item was consumed
    assert list(feed) == list(range(6))


def test_prefetch_raises_the_worker_error_in_the_consumer_and_stops_on_close() -> None:
    def boom():
        yield 1
        raise ValueError("bad sample")

    it = iter(train._Prefetch(boom))
    assert next(it) == 1
    with pytest.raises(ValueError, match="bad sample"):
        next(it)

    feed = train._Prefetch(lambda: iter(range(10_000)), depth=1)
    next(iter(feed))
    feed.close()
    assert not feed._thread.is_alive()


CONFIG = {
    "noise_scales": [0.05],
    "epochs": 2,
    "batch_size": 2,
    "lr": 1e-3,
    "latent": 8,
    "steps": 1,
    "samples_per_epoch": 6,
    "val_samples": 2,
    "connectivity_radius": 0.025,
    "checkpoint_steps": False,
    "device": "cpu",
}


class Splits:
    def __init__(self) -> None:
        self.sets = {"train": [rollout(1), rollout(2)], "val": [rollout(3)], "test": [rollout(4)]}

    def rollouts(self, name: str):
        return self.sets[name]


def test_training_through_the_device_graph_equals_training_through_the_cpu_graph(monkeypatch) -> None:
    monkeypatch.setattr(train, "DEVICE_GRAPH", True)
    fast = train.train_gns(Splits(), CONFIG, seed=5)
    monkeypatch.setattr(train, "DEVICE_GRAPH", False)
    slow = train.train_gns(Splits(), CONFIG, seed=5)
    assert fast.log["epochs"] == slow.log["epochs"]
    for key, value in slow.checkpoint["model_state"].items():
        assert torch.equal(value, fast.checkpoint["model_state"][key]), key


def test_the_step_hook_logs_one_flushed_line_per_n_steps_with_loss_rate_and_temperature(tmp_path: Path, capsys) -> None:
    class Guard:
        @staticmethod
        def read_temp() -> float:
            return 71.0

    session = run_train.GpuSession(tmp_path, cuda=False)
    session.cuda, session.guard = True, Guard()  # a session reading a temperature without a real lock
    hooks = run_train.JobHooks(tmp_path, session, digest="d", inputs=[], save_every=0, log_every=3)
    for k in range(7):
        hooks.steps += 1
        hooks.on_log(0, k + 1, 2.0, 2)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("[train]")]
    assert len(lines) == 2
    assert "step=3" in lines[0]
    assert "loss=2" in lines[0]
    assert "gpu_temp_c=71" in lines[0]
    assert "samples_per_s=" in lines[0]
    assert (tmp_path / "train_log.txt").read_text(encoding="utf-8").splitlines() == lines


def test_the_graph_self_check_passes_on_cpu() -> None:
    assert run_train.graph_self_check("cpu", log=lambda m: None) is True
