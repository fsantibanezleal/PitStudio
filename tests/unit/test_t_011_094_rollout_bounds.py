"""T-011-094 - FR-011-48: the bounds of a granular rollout must be ordered, checked before any step is read.

Oracles (independent of the code under test; plan 011 test strategy FR-011-48): hand calculation from the spec text
    on the spec's
own example (`granular-rollout.valid.json`, `bounds_m` = [x_min, y_min, x_max, y_max] = [0.0, 0.0, 1.6, 0.8]):
  x_min == x_max (e.g. [1.0, 0.0, 1.0, 0.8])          -> `rollout-bounds-invalid`
  x_min  > x_max, y_min == y_max, y_min > y_max        -> `rollout-bounds-invalid`
  ordered bounds (including negative and tiny extents) -> accepted
and a read spy: the payload reader is never called for a rejected document ("before any step is read").

Expected public API (module `pitstudio.granular.loader`, under `src/pitstudio/granular/`; errors in
    `pitstudio.granular.errors`):

    validate_rollout_metadata(meta: dict) -> dict
        returns the metadata when valid; raises `RolloutError` with `error_class == "rollout-bounds-invalid"` and a
            message naming
        `bounds_m` when x_min is not below x_max or y_min is not below y_max (NaN counts as "not below").
    load_rollout(meta: dict, *, read_frames) -> Rollout
        validates the metadata first, then calls `read_frames(meta)` exactly once and returns Rollout(meta, frames)
            with frames the
        array it returned; `read_frames` is not called when the metadata is rejected.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio.granular.errors import RolloutError  # noqa: E402
from pitstudio.granular.loader import load_rollout, validate_rollout_metadata  # noqa: E402

EX = ROOT / "specs" / "011-surrogates" / "contracts" / "examples"
VALID = json.loads((EX / "granular-rollout.valid.json").read_text(encoding="utf-8"))
NAN = float("nan")


def with_bounds(bounds: list[float]) -> dict:
    meta = copy.deepcopy(VALID)
    meta["bounds_m"] = list(bounds)
    return meta


BAD = [
    ([1.0, 0.0, 1.0, 0.8], "x-equal"),
    ([2.0, 0.0, 1.0, 0.8], "x-reversed"),
    ([0.0, 0.5, 1.6, 0.5], "y-equal"),
    ([0.0, 0.9, 1.6, 0.8], "y-reversed"),
    ([1.6, 0.8, 0.0, 0.0], "both-reversed"),
    ([0.0, 0.0, 0.0, 0.0], "all-zero"),
    ([NAN, 0.0, 1.6, 0.8], "x-min-nan"),
    ([0.0, 0.0, 1.6, NAN], "y-max-nan"),
    ([-1.0, -1.0, -2.0, 0.0], "negative-reversed"),
]


@pytest.mark.req("FR-011-48")
@pytest.mark.parametrize(("bounds", "label"), BAD, ids=[b[1] for b in BAD])
def test_unordered_bounds_are_rejected_with_the_error_class_and_the_field(bounds: list[float], label: str) -> None:
    with pytest.raises(RolloutError, match="bounds_m") as info:
        validate_rollout_metadata(with_bounds(bounds))
    assert info.value.error_class == "rollout-bounds-invalid"


@pytest.mark.req("FR-011-48")
@pytest.mark.parametrize(
    "bounds",
    [[0.0, 0.0, 1.6, 0.8], [-5.0, -2.0, -1.0, 0.0], [0.0, 0.0, 1e-9, 1e-9], [-1000.0, -1000.0, 1000.0, 1000.0]],
    ids=["example", "negative", "tiny", "widest-legal"],
)
def test_ordered_bounds_are_accepted(bounds: list[float]) -> None:
    meta = with_bounds(bounds)
    assert validate_rollout_metadata(meta)["bounds_m"] == bounds


@pytest.mark.req("FR-011-48")
@pytest.mark.parametrize(("bounds", "label"), BAD, ids=[b[1] for b in BAD])
def test_no_step_is_read_for_a_rejected_document(bounds: list[float], label: str) -> None:
    calls: list[dict] = []

    def spy(meta: dict) -> np.ndarray:
        calls.append(meta)
        return np.zeros((61, 2400, 2), dtype=np.float32)

    with pytest.raises(RolloutError) as info:
        load_rollout(with_bounds(bounds), read_frames=spy)
    assert info.value.error_class == "rollout-bounds-invalid"
    assert calls == []


@pytest.mark.req("FR-011-48")
def test_the_reader_is_called_exactly_once_for_a_valid_document_and_its_frames_are_returned() -> None:
    frames = np.arange(61 * 5 * 2, dtype=np.float32).reshape(61, 5, 2)
    calls: list[dict] = []

    def reader(meta: dict) -> np.ndarray:
        calls.append(meta)
        return frames

    rollout = load_rollout(copy.deepcopy(VALID), read_frames=reader)
    assert len(calls) == 1
    assert rollout.meta["geometry_id"] == "g017"
    assert np.array_equal(rollout.frames, frames)


@pytest.mark.req("FR-011-48")
def test_the_validator_does_not_mutate_the_metadata() -> None:
    meta = with_bounds([0.0, 0.0, 1.6, 0.8])
    before = copy.deepcopy(meta)
    validate_rollout_metadata(meta)
    assert meta == before
