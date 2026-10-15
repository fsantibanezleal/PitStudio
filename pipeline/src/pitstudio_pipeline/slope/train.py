"""Training of the C1 forecasters (FR-010-21, FR-010-33, NFR-010-06).

Pinball loss on the training split only; every hyper-parameter is chosen on the validation split only
(``select_hyperparameters``); the split seeds are checked (``check_split_membership``); a CUDA run needs the runner lock
``gpu0.compute``, honours ``gpu0.hold``, uses bf16 autocast for PatchTST and Chronos-Bolt, halves the batch on
out-of-memory
(at most twice) and records its GPU hours; without CUDA it trains on the CPU and says so.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
from torch import nn

from pitstudio.slope import budget, runtime
from pitstudio_pipeline.slope import models

QUANTILES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
TEST_STRATA = 4


class SplitLeakError(ValueError):
    """An event outside the seed range of its split, or listed in two splits."""

    def __init__(self, event_id: str, message: str) -> None:
        super().__init__(f"{event_id}: {message}")
        self.event_id = event_id


@dataclass
class Selection:
    best: Any
    scores: list[float]


@dataclass
class TrainResult:
    model: nn.Module
    history: list[float]
    manifest: dict[str, Any]


def pinball_loss(pred: torch.Tensor, target: torch.Tensor, quantiles: Sequence[float] = QUANTILES) -> torch.Tensor:
    """Mean over batch, quantile and step of max(tau (y - q), (tau - 1) (y - q)); pred (B, Q, S), target (B, S)."""
    tau = torch.as_tensor(quantiles, dtype=pred.dtype, device=pred.device).reshape(1, -1, 1)
    diff = target[:, None, :] - pred
    return torch.maximum(tau * diff, (tau - 1.0) * diff).mean()


def check_split_membership(events: Mapping[str, Sequence[Mapping[str, Any]]], config: Mapping[str, Any]) -> None:
    """Raise ``SplitLeakError`` for an event outside the seed range of its split or listed in two splits."""
    ranges = {
        "train": (config["train"]["start"], config["train"]["start"] + config["train"]["count"]),
        "validation": (config["validation"]["start"], config["validation"]["start"] + config["validation"]["count"]),
        "test": (config["test"]["start"], config["test"]["start"] + TEST_STRATA * config["test"]["count_per_stratum"]),
    }
    seen: dict[str, str] = {}
    for split, docs in events.items():
        lo, hi = ranges[split]
        for doc in docs:
            if not lo <= doc["seed"] < hi:
                raise SplitLeakError(doc["event_id"], f"seed {doc['seed']} is outside the {split} range [{lo}, {hi})")
            if doc["event_id"] in seen:
                raise SplitLeakError(doc["event_id"], f"listed in {seen[doc['event_id']]} and {split}")
            seen[doc["event_id"]] = split


def select_hyperparameters(
    candidates: Sequence[Any],
    *,
    fit: Callable[[Any, Any], Any],
    score: Callable[[Any, Any], float],
    train: Any,
    validation: Any,
) -> Selection:
    """Fit each candidate on the training events only and score it on the validation events only; lowest score wins."""
    scores = [float(score(fit(c, train), validation)) for c in candidates]
    return Selection(candidates[int(np.argmin(scores))], scores)


def train_arm(
    arm: str,
    contexts: np.ndarray,
    targets: np.ndarray,
    *,
    config: Mapping[str, Any],
    seed: int,
    device: str = "cpu",
    model: nn.Module | None = None,
    on_step: Callable[[], Any] | None = None,
) -> TrainResult:
    """Train one arm with the pinball loss; ``contexts`` (N, 2, 128) and ``targets`` (N, 64) in scaled units."""
    manifest: dict[str, Any] = {"arm": arm, "seed": seed, "epochs": int(config["epochs"])}
    kind = "cuda" if str(device).startswith("cuda") else "cpu"
    if kind == "cuda":
        runtime.require_gpu_lock(device, env=os.environ)
        runtime.check_hold(device, lock_dir=os.environ.get("GPU_LOCK_DIR", "."))
    started = time.monotonic()

    def attempt(params: dict[str, Any]) -> TrainResult:
        net = model if model is not None else models.build_model(arm, seed=seed)
        history = _fit(net, arm, contexts, targets, params, seed, device, on_step)
        return TrainResult(net, history, {})

    result = (
        runtime.run_with_oom_fallback(dict(config), attempt, manifest=manifest)
        if kind == "cuda"
        else attempt(dict(config))
    )
    record_arm = arm if arm in budget.TRAINED_ARMS else "chronos_bolt_fine_tuned"
    manifest.update(device=kind, batch_size=int(config["batch_size"]))
    manifest["gpu_hours"] = budget.gpu_hours_record(record_arm, time.monotonic() - started, device=kind)
    result.manifest = manifest
    return result


def _fit(
    net: nn.Module,
    arm: str,
    contexts: np.ndarray,
    targets: np.ndarray,
    params: Mapping[str, Any],
    seed: int,
    device: str,
    on_step: Callable[[], Any] | None,
) -> list[float]:
    torch.manual_seed(seed)
    gen = torch.Generator().manual_seed(seed)
    net.to(device).train()
    x = torch.as_tensor(contexts, dtype=torch.float32)
    y = torch.as_tensor(targets, dtype=torch.float32)
    opt = torch.optim.AdamW(net.parameters(), lr=float(params["learning_rate"]))
    dtype = runtime.autocast_dtype(arm, device) if arm in runtime.ARMS else None
    history = []
    for _ in range(int(params["epochs"])):
        order = torch.randperm(len(x), generator=gen)
        total, count = 0.0, 0
        for lo in range(0, len(x), int(params["batch_size"])):
            idx = order[lo : lo + int(params["batch_size"])]
            xb, yb = x[idx].to(device), y[idx].to(device)
            opt.zero_grad()
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=dtype == "bfloat16"):
                loss = net.loss(xb, yb) if hasattr(net, "loss") else pinball_loss(net(xb), yb)
            loss.backward()
            opt.step()
            total += float(loss) * len(idx)
            count += len(idx)
            if on_step is not None:
                on_step()
        history.append(total / count)
    net.eval()
    return history
