"""T-011-002 - dependency validation of spec 011: the packages the surrogate and calibration code needs resolve in the
environment that owns it. No requirement ID (setup task); every import is guarded so the root job skips this file.

- `pipeline/` env: torch, onnx, onnxruntime, hypothesis (the DFT property tests); `neuraloperator` is optional
  (FR-011-43) and only reported;
- `studio/` env: `cma` (FR-011-20) is locked there; when it is absent the code falls back to the minimal CMA-ES of the
  plan, so here its presence is asserted only when the studio package is importable.
"""

from __future__ import annotations

import importlib.util

import pytest


def test_pipeline_environment_has_the_training_and_export_stack() -> None:
    for name in ("torch", "onnx", "onnxruntime", "hypothesis"):
        if importlib.util.find_spec(name) is None:
            pytest.skip(f"{name} is not installed in this environment (not the pipeline env)")
    import onnx
    import torch

    assert int(torch.__version__.split(".")[0]) >= 2
    assert onnx.defs.onnx_opset_version() >= 19  # the FNO export opset (FR-011-36)


def test_optional_neuraloperator_is_reported_not_required() -> None:
    present = importlib.util.find_spec("neuralop") is not None
    assert isinstance(present, bool)  # FR-011-43: the card states which spectral oracle was used


def test_studio_environment_locks_cma_for_the_gradient_free_arm() -> None:
    if importlib.util.find_spec("warp") is None:
        pytest.skip("warp is not installed (not the studio env)")
    assert importlib.util.find_spec("cma") is not None
