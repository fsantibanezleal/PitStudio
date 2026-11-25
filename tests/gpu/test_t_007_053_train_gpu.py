# ruff: noqa: E501
"""T-007-053 (GPU half): a short PPO run on the real CUDA device under the `gpu0.compute` lock.

Requirements: FR-007-26.

Spec: specs/007-haulage-dispatch/spec.md FR-007-26 (where a CUDA device passes the runner's guards, `s30_train` trains M4 and M5 with PPO under the `gpu0.compute` lock, checkpoints after every block and resumes).

GPU job list entry: one run of 4 iterations x batch 8 x 16 decisions for each of M4 and M5 (about 1 GiB VRAM, under a minute), needs the machine-wide `gpu0.compute` lock (the test sets `PITSTUDIO_HELD_LOCKS=gpu0.compute` as the runner would after acquiring it).

Oracle: the CPU run of the same configuration (a CUDA run is not bit-equal to a CPU run, so the comparison is on shape, finiteness, the checkpoint and manifest layout and a loose parameter distance after one iteration), the lock rule of FR-002-63 and
a resume of the CUDA run against its own uninterrupted run (same device, same kernels: identical parameters).

Expected API: as in tests/pipeline/test_t_007_053_train_stage.py (`pitstudio_pipeline.dispatch.train.train`, `TrainConfig`), with `device="cuda"` and `backend=None` (the real device).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_env as hand
from pitstudio_pipeline.dispatch.train import TrainConfig, train

pytestmark = pytest.mark.gpu


def cfg(arch: str, device: str) -> TrainConfig:
    return TrainConfig(
        arch=arch, bundle=hand.family_bundle(3, horizon_s=1800.0), iterations=4, block_iters=2, batch=8, decisions_per_iter=16,
        seed=3, seed_pool=list(range(100, 140)), dt_s=10.0, device=device,
    )  # fmt: skip


@pytest.fixture
def cuda_lock(monkeypatch):
    if not torch.cuda.is_available():
        pytest.fail("CUDA is required for the GPU lane (the lane is selected with -m gpu on a machine with a device)")
    monkeypatch.setenv("PITSTUDIO_HELD_LOCKS", "gpu0.compute")


@pytest.mark.req("FR-007-26")
@pytest.mark.parametrize("arch", ["m4", "m5"])
def test_a_short_cuda_run_trains_checkpoints_and_resumes_to_the_same_parameters(tmp_path, cuda_lock, arch):
    full = train(cfg(arch, "cuda"), out_dir=tmp_path / "full")
    assert full.blocks_done == 2
    assert len(full.metrics) == 4
    assert all(torch.isfinite(v).all() for v in full.model_state.values())
    assert all(v.device.type == "cpu" for v in full.model_state.values())  # the returned state is portable
    assert sorted(p.name for p in (tmp_path / "full" / "checkpoints").glob("*.pt")) == ["block_1.pt", "block_2.pt"]
    part = train(cfg(arch, "cuda"), out_dir=tmp_path / "part", max_blocks=1)
    rest = train(cfg(arch, "cuda"), out_dir=tmp_path / "part", resume=True)
    assert part.blocks_done == 1
    assert rest.blocks_done == 2
    assert all(torch.equal(full.model_state[k], rest.model_state[k]) for k in full.model_state)


@pytest.mark.req("FR-007-26")
def test_the_cuda_run_agrees_with_the_cpu_run_after_one_iteration_up_to_float_noise(tmp_path, cuda_lock):
    one = TrainConfig(**{**cfg("m4", "cuda").__dict__, "iterations": 1, "block_iters": 1})
    cpu = TrainConfig(**{**one.__dict__, "device": "cpu"})
    a = train(one, out_dir=tmp_path / "gpu")
    b = train(cpu, out_dir=tmp_path / "cpu")
    for k in a.model_state:
        assert torch.allclose(a.model_state[k], b.model_state[k], rtol=1e-3, atol=1e-4), k


@pytest.mark.req("FR-007-26")
def test_a_cuda_run_without_the_lock_is_refused_before_a_context_exists(tmp_path, monkeypatch):
    from pitstudio_stagekit import LockNotHeldError

    monkeypatch.setenv("PITSTUDIO_HELD_LOCKS", "")
    with pytest.raises(LockNotHeldError):
        train(cfg("m4", "cuda"), out_dir=tmp_path)
    assert not (tmp_path / "checkpoints").exists()
