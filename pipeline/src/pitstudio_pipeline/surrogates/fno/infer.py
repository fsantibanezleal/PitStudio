"""FNO inference with the input guards of FR-011-40 (PyTorch and ONNX Runtime share them).

`FnoPredictor(backend, io, known_patches)` checks, before any model evaluation, the shape of `x` ([1, C_in, 64, 64]),
the channel
order against the DC-011-02 description, the finiteness of `x` and the patch id; any failure raises
`InvalidFieldInputError`
naming the argument and returns no field. The ONNX Runtime backend uses the CPU provider.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_pipeline.surrogates.errors import InvalidFieldInputError
from pitstudio_pipeline.surrogates.fno.model import FnoModel

GRID = 64


class FnoPredictor:
    """The FNO as a guarded callable; `backend` is an `FnoModel` or the path of an exported ONNX file."""

    def __init__(self, backend: FnoModel | str | Path, io: Mapping[str, Any], known_patches: Collection[str]) -> None:
        self.channels = [c["name"] for c in io["inputs"][0]["channels"]]
        self.n_out = len(io["outputs"][0]["channels"])
        self.known_patches = frozenset(known_patches)
        self._model: FnoModel | None = None
        self._session: Any = None
        self._input_name = io["inputs"][0]["name"]
        if isinstance(backend, FnoModel):
            self._model = backend.eval()
        else:
            import onnxruntime as ort

            self._session = ort.InferenceSession(str(backend), providers=["CPUExecutionProvider"])

    def validate(self, x: Any, channels: Sequence[str], patch_id: Any) -> np.ndarray:
        arr = np.asarray(x)
        expected = (1, len(self.channels), GRID, GRID)
        if arr.shape != expected:
            raise InvalidFieldInputError(f"x: shape {list(arr.shape)} is not {list(expected)}")
        if list(channels) != self.channels:
            raise InvalidFieldInputError(
                f"channels: {list(channels)} differ from the model's channel order {self.channels}"
            )
        if not np.issubdtype(arr.dtype, np.floating) or not np.isfinite(arr).all():
            raise InvalidFieldInputError("x: the field holds a non-finite value (or is not a float array)")
        if not isinstance(patch_id, str) or patch_id not in self.known_patches:
            raise InvalidFieldInputError(f"patch_id: {patch_id!r} is not a known patch")
        return arr.astype(np.float32, copy=False)

    def __call__(self, x: Any, *, channels: Sequence[str], patch_id: Any) -> np.ndarray:
        arr = self.validate(x, channels, patch_id)
        if self._model is not None:
            import torch

            with torch.no_grad():
                out = self._model(torch.from_numpy(np.ascontiguousarray(arr))).numpy()
        else:
            out = self._session.run(None, {self._input_name: np.ascontiguousarray(arr)})[0]
        return np.asarray(out, dtype=np.float32)
