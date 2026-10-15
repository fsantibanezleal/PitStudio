"""Golden sets: seeded selection from validation or held-out data, the recorded list and the hostile guards
(FR-016-06, FR-016-07)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

import numpy as np

GOLDEN_MIN = 200
GOLDEN_SPLITS = ("validation", "held-out")


class GoldenInvalid(Exception):
    """The parity stage refuses a golden set: `.code == "golden-invalid"`, `.reason` says why."""

    code = "golden-invalid"

    def __init__(self, reason: str) -> None:
        super().__init__(f"{self.code}: {reason}")
        self.reason = reason


def _digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _check_split(split: str) -> None:
    if split not in GOLDEN_SPLITS:
        raise GoldenInvalid(f"golden inputs come from validation or held-out data, not {split!r}")


def select_golden_inputs(pool: Sequence[Mapping[str, str]], *, split: str, n: int = GOLDEN_MIN, seed: int) -> list[str]:
    """`n` unique digests drawn with `default_rng(seed)` from the items of `split`; never training data."""
    _check_split(split)
    if n < GOLDEN_MIN:
        raise GoldenInvalid(f"a golden set holds at least {GOLDEN_MIN} inputs, {n} requested")
    eligible = sorted({p["sha256"] for p in pool if p["split"] == split})
    if len(eligible) < n:
        raise GoldenInvalid(f"only {len(eligible)} {split} items are available, {n} needed")
    picked = np.random.default_rng(seed).choice(len(eligible), size=n, replace=False)
    return [eligible[i] for i in picked]


def golden_set_record(golden_id: str, split: str, inputs: Sequence[np.ndarray]) -> dict:
    """The DC-016-03 `golden_set` object: id, split and the SHA-256 of every input in order."""
    _check_split(split)
    digests = [_digest(np.asarray(a)) for a in inputs]
    if len(set(digests)) != len(digests):
        raise GoldenInvalid("golden inputs repeat")
    return {"id": golden_id, "split": split, "inputs": digests}


def _finite(array: np.ndarray) -> bool:
    return array.dtype.kind not in "fc" or bool(np.isfinite(array).all())


def validate_golden(
    inputs: Sequence[np.ndarray],
    references: Sequence[Sequence[np.ndarray]],
    *,
    input_shape: tuple[int, ...],
    input_dtype: str,
) -> None:
    """Raise GoldenInvalid for too few inputs, mismatched references, non-finite data or a wrong shape or dtype."""
    if len(inputs) < GOLDEN_MIN:
        raise GoldenInvalid(f"{len(inputs)} inputs, at least {GOLDEN_MIN} are needed")
    if len(references) != len(inputs):
        raise GoldenInvalid(f"{len(references)} reference outputs for {len(inputs)} inputs")
    for i, (x, outputs) in enumerate(zip(inputs, references, strict=True)):
        x = np.asarray(x)
        if tuple(x.shape) != tuple(input_shape):
            raise GoldenInvalid(f"input {i} has shape {tuple(x.shape)}, the graph declares {tuple(input_shape)}")
        if x.dtype.name != input_dtype:
            raise GoldenInvalid(f"input {i} has dtype {x.dtype.name}, the graph declares {input_dtype}")
        if not _finite(x):
            raise GoldenInvalid(f"input {i} holds a non-finite value")
        for j, out in enumerate(outputs):
            if not _finite(np.asarray(out)):
                raise GoldenInvalid(f"reference output {j} of input {i} holds a non-finite value")
