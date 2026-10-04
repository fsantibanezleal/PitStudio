"""Pipeline-lane environment smoke test: the locked heavy dependencies import and compute (CPU)."""

import numpy as np


def test_torch_cpu_matmul() -> None:
    import torch

    a = torch.arange(6, dtype=torch.float64).reshape(2, 3)
    assert torch.equal(a @ a.T, torch.tensor([[5.0, 14.0], [14.0, 50.0]], dtype=torch.float64))


def test_onnxruntime_has_cpu_provider() -> None:
    import onnxruntime as ort

    assert "CPUExecutionProvider" in ort.get_available_providers()


def test_polars_roundtrip_numpy() -> None:
    import polars as pl

    df = pl.DataFrame({"x": [1.0, 2.0, 3.0]})
    assert np.allclose(df["x"].to_numpy(), [1.0, 2.0, 3.0])
