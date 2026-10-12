"""The `s30_train` loop: out-of-memory fallback and resume at epoch granularity (FR-009-20, FR-009-21, NFR-009-03).

The loop owns what must not change between a run that fits, a run that fell back and a run that resumed: the sample order of
each epoch, the optimiser-step count and the cosine learning-rate schedule. The model work is an injected `step_fn` that
receives one micro-batch; the checkpoint store receives exactly one state per finished epoch. A CUDA out-of-memory error
restarts the current epoch from its first optimiser step with the batch halved and the gradient accumulation doubled (the
effective batch never changes); below a batch of 1 the loop stops with `oom-exhausted`.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

OOM_PATTERN = re.compile(
    r"CUDA out of memory|OutOfMemoryError|cudaErrorMemoryAllocation|CUDA_ERROR_OUT_OF_MEMORY", re.IGNORECASE
)
MAX_SEGMENT = dt.timedelta(hours=8)  # one overnight slot (NFR-009-03)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_cuda_oom(exc: BaseException) -> bool:
    """True iff the exception text or its class name carries one of the runner's out-of-memory patterns (FR-002-33)."""
    return bool(OOM_PATTERN.search(str(exc)) or OOM_PATTERN.search(type(exc).__name__))


def lr_at(step: int, total_steps: int, base_lr: float) -> float:
    """Cosine learning rate at optimiser step `step` of `total_steps`: base_lr * (1 + cos(pi step / total)) / 2."""
    if not _is_int(total_steps) or total_steps < 1:
        raise ValueError(f"total_steps must be an int >= 1, got {total_steps!r}")
    if not _is_int(step) or not 0 <= step < total_steps:
        raise ValueError(f"step must be an int in 0..{total_steps - 1}, got {step!r}")
    if not isinstance(base_lr, int | float) or isinstance(base_lr, bool) or not math.isfinite(base_lr) or base_lr <= 0:
        raise ValueError(f"base_lr must be finite and > 0, got {base_lr!r}")
    return float(base_lr) * (1.0 + math.cos(math.pi * step / total_steps)) / 2.0


def epoch_order(n_samples: int, seed: int, epoch: int) -> tuple[int, ...]:
    """Sample order of one epoch: a permutation of range(n_samples), deterministic in (seed, epoch) only."""
    if not _is_int(n_samples) or n_samples < 1:
        raise ValueError(f"n_samples must be an int >= 1, got {n_samples!r}")
    if not _is_int(seed) or seed < 0:
        raise ValueError(f"seed must be an int >= 0, got {seed!r}")
    if not _is_int(epoch) or epoch < 0:
        raise ValueError(f"epoch must be an int >= 0, got {epoch!r}")
    rng = np.random.default_rng(np.random.SeedSequence([seed, epoch]))
    return tuple(int(i) for i in rng.permutation(n_samples))


@dataclass(frozen=True)
class LoopConfig:
    """Loop settings; the effective batch is `batch_size * accum_steps` and divides `n_samples`."""

    n_samples: int
    epochs: int
    batch_size: int
    accum_steps: int
    seed: int
    base_lr: float

    def __post_init__(self) -> None:
        for name in ("n_samples", "epochs", "batch_size", "accum_steps"):
            value = getattr(self, name)
            if not _is_int(value) or value < 1:
                raise ValueError(f"{name} must be an int >= 1, got {value!r}")
        if self.n_samples % (self.batch_size * self.accum_steps) != 0:
            raise ValueError(
                f"n_samples {self.n_samples} must be a multiple of the effective batch "
                f"{self.batch_size * self.accum_steps} (batch_size * accum_steps)"
            )

    @property
    def effective_batch(self) -> int:
        return self.batch_size * self.accum_steps

    @property
    def steps_per_epoch(self) -> int:
        return self.n_samples // self.effective_batch

    @property
    def total_steps(self) -> int:
        return self.epochs * self.steps_per_epoch


@dataclass(frozen=True)
class MicroBatch:
    """One micro-batch handed to the step function."""

    epoch: int
    optimiser_step: int
    micro_index: int
    sample_indices: tuple[int, ...]
    lr: float
    batch_size: int
    accum_steps: int


@dataclass(frozen=True)
class LoopResult:
    """Epochs done, the (batch size, accumulation) that finished the run and every attempt in order."""

    epochs_done: int
    batch_size: int
    accum_steps: int
    attempts: tuple[tuple[int, int], ...]


class TrainLoopError(Exception):
    """`code`: oom-exhausted (with `attempts`), segment-too-long, checkpoint-missing or segment-invalid."""

    def __init__(self, code: str, message: str, attempts: Sequence[tuple[int, int]] = ()) -> None:
        self.code = code
        self.attempts = tuple(attempts)
        super().__init__(f"{code}: {message}")


class CheckpointStore(Protocol):
    """The per-epoch checkpoint file: `load()` the last state or None, `save()` the state after an epoch."""

    def load(self) -> dict[str, Any] | None: ...

    def save(self, state: dict[str, Any]) -> None: ...


def _run_epoch(
    cfg: LoopConfig, epoch: int, batch_size: int, accum_steps: int, step_fn: Callable[[MicroBatch], None]
) -> int:
    """Run one epoch at (batch_size, accum_steps); return the optimiser step after it."""
    effective = batch_size * accum_steps
    steps = cfg.n_samples // effective
    total = cfg.epochs * steps
    order = epoch_order(cfg.n_samples, cfg.seed, epoch)
    first = epoch * steps
    for s in range(steps):
        step = first + s
        lr = lr_at(step, total, cfg.base_lr)
        for micro in range(accum_steps):
            lo = (s * accum_steps + micro) * batch_size
            step_fn(MicroBatch(epoch, step, micro, order[lo : lo + batch_size], lr, batch_size, accum_steps))
    return first + steps


def run_training_loop(
    cfg: LoopConfig,
    step_fn: Callable[[MicroBatch], None],
    store: CheckpointStore,
    *,
    restore: Callable[[dict[str, Any] | None], None] | None = None,
) -> LoopResult:
    """Run `cfg.epochs` epochs, resuming from the store's last state; see the module docstring.

    `restore(state)` (optional) is called with the last saved state, or None, before the first epoch and before every
    out-of-memory retry, so that the model owner can reload its weights from the checkpoint the epoch restarts from.
    """
    state = store.load()
    epochs_done = int(state["epochs_done"]) if state else 0
    batch_size = int(state["batch_size"]) if state else cfg.batch_size
    accum_steps = int(state["accum_steps"]) if state else cfg.accum_steps
    attempts: list[tuple[int, int]] = [(batch_size, accum_steps)]
    if restore is not None and state is not None:
        restore(state)
    effective = batch_size * accum_steps
    if effective != cfg.effective_batch:
        raise ValueError(f"the stored effective batch {effective} differs from the configured {cfg.effective_batch}")
    for epoch in range(epochs_done, cfg.epochs):
        while True:
            try:
                step_after = _run_epoch(cfg, epoch, batch_size, accum_steps, step_fn)
            except Exception as exc:
                if not is_cuda_oom(exc):
                    raise
                if batch_size < 2 or batch_size % 2 != 0:
                    raise TrainLoopError(
                        "oom-exhausted",
                        f"out of memory at batch {batch_size} x accumulation {accum_steps}; the batch cannot be halved",
                        attempts,
                    ) from exc
                batch_size, accum_steps = batch_size // 2, accum_steps * 2
                attempts.append((batch_size, accum_steps))
                if restore is not None:
                    restore(store.load())
                continue
            break
        store.save(
            {
                "epochs_done": epoch + 1,
                "optimiser_step": step_after,
                "batch_size": batch_size,
                "accum_steps": accum_steps,
                "seed": cfg.seed,
            }
        )
    return LoopResult(cfg.epochs, batch_size, accum_steps, tuple(attempts))


def check_training_segments(segments: Sequence[Mapping[str, Any]]) -> None:
    """Every resume segment lasts at most 8 h and holds a checkpoint for each of its epochs (NFR-009-03)."""
    for segment in segments:
        if not isinstance(segment, Mapping):
            raise TrainLoopError("segment-invalid", f"segment {segment!r} is not a mapping")
        start, end = segment.get("start_utc"), segment.get("end_utc")
        for value in (start, end):
            if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise TrainLoopError("segment-invalid", "start_utc and end_utc must be timezone-aware datetimes")
        assert isinstance(start, dt.datetime) and isinstance(end, dt.datetime)
        if end < start:
            raise TrainLoopError("segment-invalid", "the segment ends before it starts")
        if end - start > MAX_SEGMENT:
            raise TrainLoopError("segment-too-long", f"the segment lasts {end - start}, more than 8 h")
        missing = [e for e in segment.get("epochs", []) if e not in segment.get("checkpoints", [])]
        if missing:
            raise TrainLoopError("checkpoint-missing", f"no checkpoint for epoch(s) {missing}")
