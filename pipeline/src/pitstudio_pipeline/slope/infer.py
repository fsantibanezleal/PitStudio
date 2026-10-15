"""Inference of the C1 forecasters on PyTorch and ONNX Runtime with the context guards of FR-010-29.

``TorchForecaster`` and ``OrtForecaster`` are callables ``f(context) -> (1, 9, 64) float32`` for
``pitstudio.slope.forecast.learned_forecast``. A context that is not a float32 NumPy array of shape (1, 2, 128), that
holds a
non-finite value or whose mask channel is all zero (no positive velocity at all) raises ``InvalidWindowError`` naming
the
property, before any network runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from pitstudio.slope.errors import InvalidWindowError


def check_context(context: Any) -> np.ndarray:
    """Validate a forecaster context (see the module docstring) and return it."""
    if not isinstance(context, np.ndarray) or context.dtype != np.float32:
        raise InvalidWindowError(f"the context must be a float32 NumPy array (dtype), got {type(context).__name__}")
    if context.ndim != 3 or context.shape[0] != 1 or context.shape[1] != 2:
        raise InvalidWindowError(f"the context must have shape (1, 2, 128), got {context.shape} (shape)")
    if context.shape[2] != 128:
        raise InvalidWindowError(f"the context length must be 128, got {context.shape[2]} (length)")
    if not np.all(np.isfinite(context)):
        raise InvalidWindowError("the context holds a non-finite value")
    if not np.any(context[0, 1] > 0.5):
        raise InvalidWindowError("no block carries data: there is no positive velocity at all")
    return context


class TorchForecaster:
    def __init__(self, model: nn.Module) -> None:
        self.model = model

    def __call__(self, context: Any) -> np.ndarray:
        x = check_context(context)
        with torch.no_grad():
            return self.model(torch.from_numpy(x)).detach().cpu().numpy().astype(np.float32)  # type: ignore[no-any-return]


class OrtForecaster:
    def __init__(self, onnx_path: str | Path) -> None:
        import onnxruntime as ort

        self.session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])

    def __call__(self, context: Any) -> np.ndarray:
        x = check_context(context)
        return self.session.run(None, {"context": x})[0]  # type: ignore[no-any-return]
