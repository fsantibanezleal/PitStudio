# ruff: noqa: E501
"""T-008-051 (GPU half): CPU and GPU embeddings of the same image agree (cosine >= 0.999) and the GPU path runs under the
`gpu0.compute` lock. Marked `gpu`: never run in CI and not run during the red phase (the GPU belongs to the scheduled jobs).

Requirements: FR-008-40.

Spec: specs/008-data-pipeline/spec.md FR-008-40 ("CPU and GPU embeddings of the same image shall have cosine similarity
>= 0.999"; "under the `gpu0.compute` lock"); plan.md tolerances (fp32 with TF32 disabled; the statistical class).

Oracle: the CPU embedding of the same image computed by the same code path (the reference), cosine similarity written out
with numpy. The lock itself is covered by the runner's own fake-GPU tests (spec 002); this test covers the agreement.

Expected API of the implementation: as in tests/pipeline/test_t_008_051_embeddings.py, with `embed_images(..., device="cuda")`
acquiring the machine-wide `gpu0.compute` lock for the duration of the model call (spec 002 runner lock) and releasing it
afterwards, also when the model raises; `EmbeddingResult.device == "cuda"`.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.features import embed_images

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import _p008_kit as kit

REVISION = "0123456789abcdef0123456789abcdef01234567"


def _model():
    import torch

    class Tiny(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            g = torch.Generator().manual_seed(0)
            self.w = torch.nn.Parameter(torch.randn(3, 64, generator=g), requires_grad=False)

        def forward(self, x):
            return x.mean(dim=(2, 3)) @ self.w

    return Tiny().eval()


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


@pytest.mark.gpu
@pytest.mark.req("FR-008-40")
def test_cpu_and_gpu_embeddings_of_the_same_images_have_cosine_at_least_0_999(tmp_path: Path) -> None:
    import torch

    assert torch.cuda.is_available(), (
        "this test needs a CUDA device (it is marked gpu and runs only in the scheduled GPU job)"
    )
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    weights = tmp_path / "w.bin"
    weights.write_bytes(kit.payload(1024, 3))
    pin = {
        "model_id": "facebook/dinov2-small",
        "revision": REVISION,
        "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
        "licence": "Apache-2.0",
    }
    images = [np.random.default_rng(s).integers(0, 256, size=(56, 56, 3), dtype=np.uint8) for s in range(8)]
    kw = dict(weights_path=weights, pin=pin, revision=REVISION, licence="Apache-2.0")
    cpu = embed_images(images, model=_model(), device="cpu", **kw)
    gpu = embed_images(images, model=_model().to("cuda"), device="cuda", **kw)
    assert gpu.device == "cuda"
    for a, b in zip(cpu.embeddings, gpu.embeddings, strict=True):
        assert _cos(a.astype(np.float64), b.astype(np.float64)) >= 0.999
