# ruff: noqa: E501
"""T-009-031 - FR-009-20, FR-009-21, NFR-009-03: OOM fallback and resume of the `s30_train` loop on a fake GPU backend.

Oracles (independent of the code under test):
- FR-009-20, hand calculation of plan 009 (test strategy row): batch / accumulation 16/1 -> 8/2 -> 4/4 -> 2/8 -> 1/16 -> then
  `oom-exhausted` (the effective batch 16 never changes, so the learning-rate schedule and the number of optimiser steps do
  not change); a CUDA OOM is recognised by the text patterns of FR-002-33 (`CUDA out of memory`, `OutOfMemoryError`,
  `cudaErrorMemoryAllocation`, `CUDA_ERROR_OUT_OF_MEMORY`, case-insensitive); any other exception is not an OOM and is not retried;
- FR-009-21, closed-form cosine schedule written in this file: lr(k) = base * (1 + cos(pi k / T)) / 2 for optimiser step k = 0 ..
  T-1, T = epochs x steps per epoch (analytical); metamorphic: an interrupted run resumed from its last per-epoch checkpoint
  produces, from the resumed epoch on, exactly the micro-batches (epoch, step, samples, lr) of an uninterrupted run;
- NFR-009-03, hand calculation: a resume segment of 8 h 00 min 00 s is allowed (<= 8 h), 8 h 00 min 01 s is not; every epoch needs a
  checkpoint; the checkpoint store sees exactly one save per epoch.
The fake GPU backend of spec 002 is not imported: the loop takes an injected `step_fn`, and this file's `FakeGpu` raises the
OOM the real backend would report (the runner side of the retry, FR-002-33, is spec 002's).

Expected public API (module `pitstudio_pipeline.perception.train_loop`, package under `pipeline/src/`):

    OOM_PATTERN: re.Pattern    case-insensitive: CUDA out of memory|OutOfMemoryError|cudaErrorMemoryAllocation|CUDA_ERROR_OUT_OF_MEMORY
    is_cuda_oom(exc: BaseException) -> bool       True iff OOM_PATTERN matches str(exc) or the exception class name
    lr_at(step: int, total_steps: int, base_lr: float) -> float
        base_lr * (1 + cos(pi * step / total_steps)) / 2; ValueError (message names the argument) unless 0 <= step < total_steps,
        total_steps >= 1 and base_lr is finite and > 0
    epoch_order(n_samples: int, seed: int, epoch: int) -> tuple[int, ...]
        the sample order of one epoch: a permutation of range(n_samples), deterministic in (seed, epoch), independent of
        batch size and accumulation; ValueError for n_samples < 1, a negative seed or epoch, or a non-int
    LoopConfig                    frozen dataclass: n_samples, epochs, batch_size, accum_steps, seed, base_lr; the effective batch is
                                  batch_size * accum_steps; one optimiser step consumes that many samples (n_samples must be a multiple of
                                  it: ValueError otherwise); steps per epoch = n_samples // effective batch
    MicroBatch                    frozen dataclass: epoch, optimiser_step (global, 0-based), micro_index (0-based inside the optimiser
                                  step), sample_indices: tuple[int, ...] (batch_size samples), lr (lr_at of the optimiser step),
                                  batch_size, accum_steps
    LoopResult                    frozen dataclass: epochs_done: int, batch_size: int, accum_steps: int, attempts: tuple[tuple[int, int], ...]
                                  ((batch_size, accum_steps) of every attempt, in order, the successful one last)
    TrainLoopError(Exception)     .code ("oom-exhausted", "segment-too-long", "checkpoint-missing", "segment-invalid"); .attempts: tuple
                                  (for oom-exhausted); str(error) contains the code
    run_training_loop(cfg: LoopConfig, step_fn: Callable[[MicroBatch], None], store) -> LoopResult
        `store.load() -> dict | None` and `store.save(state: dict) -> None`; the saved state has at least "epochs_done",
        "optimiser_step", "batch_size", "accum_steps". Starts from the stored state (epoch index = epochs_done, optimiser step =
        optimiser_step) or from scratch; for each epoch calls step_fn once per micro-batch, in order, then saves exactly one checkpoint
        (state after the epoch). When step_fn raises a CUDA OOM the loop restarts the CURRENT epoch from its first optimiser step (the
        last checkpoint) with batch_size halved and accum_steps doubled; if batch_size would fall below 1 it raises
        TrainLoopError("oom-exhausted", attempts=...). Any other exception propagates unchanged and nothing is saved for the unfinished
        epoch. Returns when `cfg.epochs` epochs are done.
    check_training_segments(segments: Sequence[Mapping]) -> None
        segment = {"start_utc": datetime, "end_utc": datetime, "epochs": [int, ...], "checkpoints": [int, ...]} (timezone-aware); raises
        TrainLoopError("segment-too-long") when end - start > 8 h, ("checkpoint-missing") when an epoch of `epochs` is not in `checkpoints`,
        ("segment-invalid") for end < start, naive datetimes or a non-mapping segment.
"""

from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.perception import train_loop as tl  # noqa: E402

N, EPOCHS, BASE_LR = 64, 5, 1e-3


class Store:
    """In-memory checkpoint store: the test double of the per-epoch checkpoint file."""

    def __init__(self) -> None:
        self.saved: list[dict] = []

    def load(self) -> dict | None:
        return dict(self.saved[-1]) if self.saved else None

    def save(self, state: dict) -> None:
        self.saved.append(dict(state))


class FakeGpu:
    """step_fn that records every micro-batch and raises a CUDA OOM while batch_size > limit."""

    def __init__(self, limit: int = 10**9, message: str = "CUDA out of memory. Tried to allocate 2.00 GiB") -> None:
        self.limit, self.message, self.log = limit, message, []

    def __call__(self, mb: tl.MicroBatch) -> None:
        if mb.batch_size > self.limit:
            raise RuntimeError(self.message)
        self.log.append(mb)


def _cfg(batch: int = 16, accum: int = 1, n: int = N, epochs: int = EPOCHS) -> tl.LoopConfig:
    return tl.LoopConfig(n_samples=n, epochs=epochs, batch_size=batch, accum_steps=accum, seed=7, base_lr=BASE_LR)


def _key(mb: tl.MicroBatch) -> tuple:
    return (mb.epoch, mb.optimiser_step, mb.micro_index, mb.sample_indices, mb.lr, mb.batch_size, mb.accum_steps)


# ---------------------------------------------------------------- helpers: closed-form schedule and order


@pytest.mark.req("FR-009-21")
@pytest.mark.parametrize(("step", "total"), [(0, 20), (1, 20), (10, 20), (19, 20), (0, 1), (5, 6)])
def test_the_learning_rate_follows_the_closed_form_cosine(step: int, total: int) -> None:
    want = BASE_LR * (1.0 + math.cos(math.pi * step / total)) / 2.0
    assert tl.lr_at(step, total, BASE_LR) == pytest.approx(want, rel=1e-12, abs=0.0)
    assert tl.lr_at(0, total, BASE_LR) == pytest.approx(BASE_LR, rel=1e-12)  # k = 0: the base rate
    assert tl.lr_at(10, 20, BASE_LR) == pytest.approx(BASE_LR / 2.0, rel=1e-12)  # k = T/2: half the base rate


@pytest.mark.req("FR-009-21")
@pytest.mark.parametrize(
    ("step", "total", "base", "arg"),
    [
        (-1, 20, 1e-3, "step"),
        (20, 20, 1e-3, "step"),
        (0, 0, 1e-3, "total_steps"),
        (0, 20, 0.0, "base_lr"),
        (0, 20, float("nan"), "base_lr"),
        (0, 20, -1.0, "base_lr"),
    ],
)
def test_hostile_schedule_arguments_are_rejected(step: int, total: int, base: float, arg: str) -> None:
    with pytest.raises(ValueError, match=arg):
        tl.lr_at(step, total, base)


@pytest.mark.req("FR-009-21")
def test_the_epoch_order_is_a_deterministic_permutation_that_changes_with_epoch_and_seed() -> None:
    a = tl.epoch_order(64, 7, 0)
    assert sorted(a) == list(range(64))
    assert a == tl.epoch_order(64, 7, 0)
    assert a != tl.epoch_order(64, 7, 1)
    assert a != tl.epoch_order(64, 8, 0)


@pytest.mark.req("FR-009-21")
@pytest.mark.parametrize("args", [(0, 1, 0), (-5, 1, 0), (10, -1, 0), (10, 1, -1), (10.0, 1, 0), (10, True, 0)])
def test_hostile_epoch_order_arguments_are_rejected(args: tuple) -> None:
    with pytest.raises(ValueError, match=r"n_samples|seed|epoch"):
        tl.epoch_order(*args)


# ---------------------------------------------------------------- FR-009-20


@pytest.mark.req("FR-009-20")
def test_the_ladder_16_8_4_2_ends_at_2_by_8_when_the_gpu_fits_batch_2() -> None:
    gpu, store = FakeGpu(limit=2), Store()
    res = tl.run_training_loop(_cfg(16, 1), gpu, store)
    assert res.attempts == ((16, 1), (8, 2), (4, 4), (2, 8))
    assert (res.batch_size, res.accum_steps) == (2, 8)
    assert res.epochs_done == EPOCHS
    assert {mb.batch_size * mb.accum_steps for mb in gpu.log} == {16}  # the effective batch never changes


@pytest.mark.req("FR-009-20")
def test_the_ladder_ends_with_oom_exhausted_after_one_by_sixteen() -> None:
    gpu, store = FakeGpu(limit=0), Store()
    with pytest.raises(tl.TrainLoopError) as exc:
        tl.run_training_loop(_cfg(16, 1), gpu, store)
    assert exc.value.code == "oom-exhausted"
    assert "oom-exhausted" in str(exc.value)
    assert tuple(exc.value.attempts) == ((16, 1), (8, 2), (4, 4), (2, 8), (1, 16))
    assert gpu.log == []  # no micro-batch ever completed
    assert store.saved == []  # and nothing was checkpointed


@pytest.mark.req("FR-009-20")
def test_a_run_that_fits_never_falls_back() -> None:
    res = tl.run_training_loop(_cfg(16, 1), FakeGpu(), Store())
    assert res.attempts == ((16, 1),)


@pytest.mark.req("FR-009-20")
def test_the_fallback_run_sees_the_same_samples_and_learning_rates_as_a_run_that_fits() -> None:
    fits, fallback = FakeGpu(), FakeGpu(limit=4)
    tl.run_training_loop(_cfg(16, 1), fits, Store())
    tl.run_training_loop(_cfg(16, 1), fallback, Store())
    for epoch in range(EPOCHS):
        for log in (fits.log, fallback.log):
            order = tl.epoch_order(N, 7, epoch)
            seen = [i for mb in log if mb.epoch == epoch for i in mb.sample_indices]
            assert seen == list(order)  # every sample exactly once per epoch, in the epoch's order
    lr_fits = {mb.optimiser_step: mb.lr for mb in fits.log}
    lr_fallback = {mb.optimiser_step: mb.lr for mb in fallback.log}
    total = EPOCHS * (N // 16)
    assert lr_fits == lr_fallback
    assert set(lr_fits) == set(range(total))
    for k, lr in lr_fits.items():
        assert lr == pytest.approx(BASE_LR * (1 + math.cos(math.pi * k / total)) / 2, rel=1e-12)


@pytest.mark.req("FR-009-20")
def test_an_oom_in_a_later_epoch_restarts_that_epoch_from_its_last_checkpoint_only() -> None:
    class LateOom(FakeGpu):
        def __call__(self, mb: tl.MicroBatch) -> None:
            if mb.epoch == 2 and mb.batch_size == 16:
                raise RuntimeError("torch.OutOfMemoryError: CUDA out of memory")
            super().__call__(mb)

    gpu, store = LateOom(), Store()
    res = tl.run_training_loop(_cfg(16, 1), gpu, store)
    assert res.attempts == ((16, 1), (8, 2))
    assert [mb.batch_size for mb in gpu.log if mb.epoch < 2] == [16] * (2 * 4)  # epochs 0 and 1 ran once, at 16
    assert {mb.batch_size for mb in gpu.log if mb.epoch >= 2} == {8}  # epoch 2 restarted at 8 and stayed there
    assert [s["epochs_done"] for s in store.saved] == [1, 2, 3, 4, 5]  # no checkpoint was lost or duplicated
    epoch2 = [mb for mb in gpu.log if mb.epoch == 2]
    assert [i for mb in epoch2 for i in mb.sample_indices] == list(
        tl.epoch_order(N, 7, 2)
    )  # the epoch is complete, once


@pytest.mark.req("FR-009-20")
@pytest.mark.parametrize(
    "message",
    [
        "CUDA out of memory",
        "cuda OUT OF MEMORY: tried",
        "torch.cuda.OutOfMemoryError",
        "cudaErrorMemoryAllocation",
        "CUDA_ERROR_OUT_OF_MEMORY",
        "outofmemoryerror",
    ],
)
def test_every_oom_wording_of_the_runner_is_recognised(message: str) -> None:
    assert tl.is_cuda_oom(RuntimeError(message)) is True
    res = tl.run_training_loop(_cfg(16, 1), FakeGpu(limit=8, message=message), Store())
    assert res.attempts == ((16, 1), (8, 2))


@pytest.mark.req("FR-009-20")
def test_the_exception_class_name_counts_too() -> None:
    class OutOfMemoryError(RuntimeError):
        pass

    assert tl.is_cuda_oom(OutOfMemoryError("allocation failed")) is True
    assert tl.is_cuda_oom(ValueError("shape mismatch")) is False
    assert tl.is_cuda_oom(RuntimeError("disk full")) is False


@pytest.mark.req("FR-009-20")
def test_an_error_that_is_not_an_oom_propagates_without_any_fallback() -> None:
    gpu, store = FakeGpu(limit=0, message="shape mismatch in the loss"), Store()
    with pytest.raises(RuntimeError, match="shape mismatch"):
        tl.run_training_loop(_cfg(16, 1), gpu, store)
    assert store.saved == []


@pytest.mark.req("FR-009-20")
@pytest.mark.parametrize(
    ("kwargs", "arg"),
    [
        ({"n": 63}, "n_samples"),
        ({"batch": 0}, "batch_size"),
        ({"accum": 0}, "accum_steps"),
        ({"epochs": 0}, "epochs"),
        ({"batch": 3, "accum": 1}, "n_samples"),
    ],
)
def test_a_hostile_loop_configuration_is_rejected(kwargs: dict, arg: str) -> None:
    with pytest.raises(ValueError, match=arg):
        tl.run_training_loop(_cfg(**kwargs), FakeGpu(), Store())


# ---------------------------------------------------------------- FR-009-21 / NFR-009-03: resume


class Boom(Exception):
    pass


@pytest.mark.req("FR-009-21")
@pytest.mark.req("NFR-009-03")
def test_the_store_receives_exactly_one_checkpoint_per_epoch_in_order() -> None:
    store = Store()
    tl.run_training_loop(_cfg(16, 1), FakeGpu(), store)
    assert [s["epochs_done"] for s in store.saved] == [1, 2, 3, 4, 5]
    assert [s["optimiser_step"] for s in store.saved] == [4, 8, 12, 16, 20]
    assert all(s["batch_size"] == 16 and s["accum_steps"] == 1 for s in store.saved)


@pytest.mark.req("FR-009-21")
@pytest.mark.parametrize(("stop_epoch", "stop_micro"), [(1, 0), (2, 3), (3, 1), (4, 0)])
def test_an_interrupted_run_resumed_from_its_checkpoint_equals_the_uninterrupted_run(
    stop_epoch: int, stop_micro: int
) -> None:
    reference = FakeGpu()
    tl.run_training_loop(_cfg(8, 2), reference, Store())

    store, first = Store(), FakeGpu()

    def crashing(mb: tl.MicroBatch) -> None:
        if mb.epoch == stop_epoch and mb.optimiser_step == stop_epoch * 4 + 1 and mb.micro_index == stop_micro % 2:
            raise Boom
        first(mb)

    with pytest.raises(Boom):
        tl.run_training_loop(_cfg(8, 2), crashing, store)
    assert [s["epochs_done"] for s in store.saved] == list(
        range(1, stop_epoch + 1)
    )  # only completed epochs are checkpointed

    second = FakeGpu()
    res = tl.run_training_loop(_cfg(8, 2), second, store)
    assert res.epochs_done == EPOCHS
    ref_done = [_key(mb) for mb in reference.log if mb.epoch < stop_epoch]
    ref_rest = [_key(mb) for mb in reference.log if mb.epoch >= stop_epoch]
    assert [_key(mb) for mb in first.log if mb.epoch < stop_epoch] == ref_done
    assert [
        _key(mb) for mb in second.log
    ] == ref_rest  # same epoch index, lr step and data order from the resumed epoch on
    assert [s["epochs_done"] for s in store.saved] == [1, 2, 3, 4, 5]


@pytest.mark.req("FR-009-21")
def test_resuming_a_finished_run_does_nothing() -> None:
    store = Store()
    tl.run_training_loop(_cfg(16, 1), FakeGpu(), store)
    again = FakeGpu()
    res = tl.run_training_loop(_cfg(16, 1), again, store)
    assert again.log == []
    assert res.epochs_done == EPOCHS
    assert len(store.saved) == EPOCHS


def _seg(hours: float, *, epochs=(0,), checkpoints=(0,)) -> dict:
    start = dt.datetime(2026, 10, 12, 22, 0, tzinfo=dt.UTC)
    return {
        "start_utc": start,
        "end_utc": start + dt.timedelta(hours=hours),
        "epochs": list(epochs),
        "checkpoints": list(checkpoints),
    }


@pytest.mark.req("NFR-009-03")
def test_a_resume_segment_of_eight_hours_is_allowed_and_one_second_more_is_not() -> None:
    assert tl.check_training_segments([_seg(7.99), _seg(8.0, epochs=(1, 2), checkpoints=(1, 2))]) is None
    longer = _seg(8.0)
    longer["end_utc"] += dt.timedelta(seconds=1)
    with pytest.raises(tl.TrainLoopError) as exc:
        tl.check_training_segments([_seg(1.0), longer])
    assert exc.value.code == "segment-too-long"


@pytest.mark.req("NFR-009-03")
def test_every_epoch_of_a_segment_needs_a_checkpoint() -> None:
    assert tl.check_training_segments([]) is None
    with pytest.raises(tl.TrainLoopError) as exc:
        tl.check_training_segments([_seg(2.0, epochs=(3, 4, 5), checkpoints=(3, 5))])
    assert exc.value.code == "checkpoint-missing"
    assert "4" in str(exc.value)


@pytest.mark.req("NFR-009-03")
@pytest.mark.parametrize(
    "segment",
    [
        {**_seg(1.0), "end_utc": dt.datetime(2026, 10, 12, 21, 0, tzinfo=dt.UTC)},  # ends before it starts
        {**_seg(1.0), "start_utc": dt.datetime(2026, 10, 12, 22, 0)},  # naive
        "segment",
        None,
        {"start_utc": None, "end_utc": None, "epochs": [], "checkpoints": []},
    ],
)
def test_a_malformed_segment_is_rejected(segment: object) -> None:
    with pytest.raises(tl.TrainLoopError) as exc:
        tl.check_training_segments([segment])  # type: ignore[list-item]
    assert exc.value.code == "segment-invalid"
