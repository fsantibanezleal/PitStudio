"""T-010-029 (GPU part): forecaster training smoke test on a CUDA device, through the runner conventions.

Requirement: FR-010-33. Marked `gpu`: not run by the red phase or by CI without a GPU (the GPU belongs to scheduled
jobs); the fake
backend half is tests/unit/test_t_010_029_training_fake_gpu.py.

Expected API: `pitstudio_pipeline.slope.train.train_arm(arm, contexts, targets, *, config, seed, device)` as in
T-010-027, with
`device="cuda"` requiring the held lock `gpu0.compute` in `PITSTUDIO_HELD_LOCKS` and honouring `gpu0.hold` in
`GPU_LOCK_DIR`
(`pitstudio.slope.runtime`); for PatchTST the forward pass runs under `torch.autocast("cuda", dtype=torch.bfloat16)`
and the
TCN under none; the manifest carries `device` "cuda", a positive `gpu_hours`, `oom_fallback` False for a run that fits
in memory,
and `autocast` "bfloat16" for PatchTST, None for TCN.

Oracle: the declared behaviour (spy on `torch.autocast`); the pinball loss must decrease on a constant target.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from pitstudio_pipeline.slope import train  # noqa: E402

torch = pytest.importorskip("torch")

pytestmark = pytest.mark.gpu


def _data(n=96):
    rng = np.random.default_rng(1)
    ctx = rng.normal(size=(n, 2, 128)).astype(np.float32)
    ctx[:, 1] = 1.0
    return ctx, np.full((n, 64), 1.0, dtype=np.float32)


@pytest.mark.req("FR-010-33")
@pytest.mark.parametrize(("arm", "autocast"), [("tcn", None), ("patchtst", "bfloat16")])
def test_training_on_cuda_records_gpu_hours_and_uses_bf16_autocast_for_patchtst(arm, autocast, monkeypatch) -> None:
    assert torch.cuda.is_available()
    monkeypatch.setenv("PITSTUDIO_HELD_LOCKS", "gpu0.compute")
    ctx, tgt = _data()
    used: list = []
    real = torch.autocast

    def spy(device_type, *a, **k):
        used.append((device_type, k.get("dtype", a[0] if a else None)))
        return real(device_type, *a, **k)

    monkeypatch.setattr(torch, "autocast", spy)
    res = train.train_arm(
        arm, ctx, tgt, config={"epochs": 4, "batch_size": 16, "learning_rate": 1e-2}, seed=1, device="cuda"
    )
    assert res.manifest["device"] == "cuda"
    assert res.manifest["gpu_hours"]["gpu_hours"] > 0.0
    assert res.manifest["oom_fallback"] is False
    assert res.manifest["autocast"] == autocast
    assert (("cuda", torch.bfloat16) in used) == (autocast == "bfloat16")
    assert res.history[-1] < res.history[0]


@pytest.mark.req("FR-010-33")
def test_a_hold_file_stops_the_cuda_training_before_any_step(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PITSTUDIO_HELD_LOCKS", "gpu0.compute")
    monkeypatch.setenv("GPU_LOCK_DIR", str(tmp_path))
    (tmp_path / "gpu0.hold").write_text("thermal", encoding="utf-8")
    ctx, tgt = _data(32)
    with pytest.raises(Exception, match=r".") as exc:
        train.train_arm(
            "tcn", ctx, tgt, config={"epochs": 1, "batch_size": 16, "learning_rate": 1e-2}, seed=1, device="cuda"
        )
    assert getattr(exc.value, "error_class", None) == "hold"
    assert os.environ["GPU_LOCK_DIR"] == str(tmp_path)
