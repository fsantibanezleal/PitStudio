"""Chronos-Bolt-tiny arms of case C1: zero-shot and fine-tuned (FR-010-21, FR-010-31).

The package ``chronos-forecasting`` (Apache-2.0) and the weights ``amazon/chronos-bolt-tiny`` (staged on the machine,
pinned
by revision) are optional: when either is missing the arms are reported "not run" with the reason, TCN and PatchTST are
unaffected. The wrapper maps the C1 context (B, 2, 128) to the quantiles (B, 9, 64): channel 0 with the masked blocks
as NaN
(Chronos-Bolt treats NaN as missing and scales by the context itself), so the output is in the units of the scaled
context.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

import torch
from torch import nn

MODEL_ID = "amazon/chronos-bolt-tiny"
CONTEXT_LENGTH = 128
PREDICTION_LENGTH = 64
QUANTILES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
ARMS = ("zero-shot", "fine-tuned")
WEIGHTS_ENV = "PITSTUDIO_CHRONOS_DIR"


class ChronosUnavailableError(ValueError):
    """The Chronos-Bolt arm cannot be built; the message is the reason stored in the acceptance row."""


def weights_dir(explicit: str | Path | None = None) -> Path | None:
    """The staged weights folder: the argument, else ``PITSTUDIO_CHRONOS_DIR``, else None."""
    raw = explicit or os.environ.get(WEIGHTS_ENV)
    return Path(raw) if raw else None


def availability(weights: str | Path | None = None) -> dict[str, Any]:
    """{"available", "reason"}: the package must import and the weights folder must hold config.json."""
    if importlib.util.find_spec("chronos") is None:
        return {"available": False, "reason": "the package chronos-forecasting is not installed"}
    folder = weights_dir(weights)
    if folder is None or not (folder / "config.json").is_file():
        return {"available": False, "reason": f"no staged weights of {MODEL_ID} (set {WEIGHTS_ENV})"}
    return {"available": True, "reason": None}


def not_run_reason(mode: str, av: dict[str, Any]) -> str:
    return f"chronos-bolt {mode} not run: {av['reason']}"


class ChronosArm(nn.Module):
    """Chronos-Bolt as a C1 forecaster: ``forward(context (B, 2, 128)) -> quantiles (B, 9, 64)``."""

    def __init__(self, bolt: nn.Module) -> None:
        super().__init__()
        self.bolt = bolt

    def forward(self, context: torch.Tensor) -> torch.Tensor:
        y = torch.where(context[:, 1] > 0.5, context[:, 0], torch.full_like(context[:, 0], float("nan")))
        out = self.bolt(context=y)
        return out.quantile_preds[:, :, :PREDICTION_LENGTH]

    def loss(self, context: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        y = torch.where(context[:, 1] > 0.5, context[:, 0], torch.full_like(context[:, 0], float("nan")))
        return self.bolt(context=y, target=target).loss  # type: ignore[no-any-return]


def build_arm(mode: str, *, weights_dir: str | Path | None = None) -> ChronosArm:
    """The zero-shot or fine-tunable arm; ``ChronosUnavailableError`` if it cannot be built; ValueError if bad."""
    if mode not in ARMS:
        raise ValueError(f"mode must be one of {list(ARMS)}, got {mode!r}")
    av = availability(weights_dir)
    if not av["available"]:
        raise ChronosUnavailableError(not_run_reason(mode, av))
    from chronos import ChronosBoltPipeline

    folder = globals()["weights_dir"](weights_dir)
    pipeline = ChronosBoltPipeline.from_pretrained(str(folder), device_map="cpu", torch_dtype=torch.float32)
    return ChronosArm(pipeline.model)
