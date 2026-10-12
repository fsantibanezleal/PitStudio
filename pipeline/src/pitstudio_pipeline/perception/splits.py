"""Seed-grouped train / validation / test splits, leak checks and arm volume of the perception dataset (FR-009-16,
FR-009-17, NFR-009-05, P-009-13).

Splits are made per family over scenario seeds, never over images: every image of a scenario, and every scenario of a
layout, stays in one split. The unstructured arm is in training only and reuses the structured pit training seeds.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

MAX_SEED = 2**63 - 1
HAMMING_LEAK = 4  # a test image within this Hamming distance of a train / validation image leaks (FR-009-17)
_SPLIT_NAMES = ("train", "validation", "test")
_PROPORTIONS = (0.8, 0.1, 0.1)


class SplitError(Exception):
    """Split or leak failure: `code` is split-leak, scenario-invalid or volume-invalid; `pairs` lists the leaking pairs
    (record id a, record id b, reason: scenario_seed, layout_id or phash)."""

    def __init__(self, code: str, message: str, pairs: Sequence[tuple[str, str, str]] = ()) -> None:
        self.code = code
        self.pairs = tuple(pairs)
        shown = "; ".join(f"{a} / {b} ({why})" for a, b, why in self.pairs[:50])
        more = f" (and {len(self.pairs) - 50} more)" if len(self.pairs) > 50 else ""
        super().__init__(f"{code}: {message}" + (f": {shown}{more}" if shown else ""))


@dataclass(frozen=True)
class SplitAssignment:
    """Scenario seeds of the three splits, each ascending."""

    train: tuple[int, ...]
    validation: tuple[int, ...]
    test: tuple[int, ...]


@dataclass(frozen=True)
class ArmSplits:
    """Splits of both rendered families; the unstructured arm trains on the structured pit training seeds."""

    pit: SplitAssignment
    crusher: SplitAssignment
    unstructured_train: tuple[int, ...]


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validated_scenarios(scenarios: Sequence[tuple[int, str]], rng_seed: object) -> dict[str, list[int]]:
    if not _is_int(rng_seed) or rng_seed < 0:  # type: ignore[operator]
        raise SplitError("scenario-invalid", f"rng_seed must be a non-negative int, got {rng_seed!r}")
    if len(scenarios) == 0:
        raise SplitError("scenario-invalid", "no scenario to split")
    layouts: dict[str, list[int]] = {}
    seen: set[int] = set()
    for item in scenarios:
        try:
            seed, layout = item
        except (TypeError, ValueError):
            raise SplitError("scenario-invalid", f"scenario {item!r} is not a (seed, layout_id) pair") from None
        if not _is_int(seed) or not 0 <= seed <= MAX_SEED:
            raise SplitError("scenario-invalid", f"scenario seed {seed!r} is not an int in 0..2**63-1")
        if not isinstance(layout, str) or layout == "":
            raise SplitError("scenario-invalid", f"layout id {layout!r} is not a non-empty string")
        if seed in seen:
            raise SplitError("scenario-invalid", f"scenario seed {seed} is duplicated")
        seen.add(seed)
        layouts.setdefault(layout, []).append(seed)
    return layouts


def _assign(layouts: dict[str, list[int]], entropy: list[int]) -> SplitAssignment:
    """Quota assignment of layouts (shuffled by the seeded generator) to the three splits at 80 / 10 / 10 %."""
    names = sorted(layouts)
    order = np.random.default_rng(np.random.SeedSequence(entropy)).permutation(len(names))
    total = sum(len(v) for v in layouts.values())
    placed = 0
    buckets: list[list[int]] = [[], [], []]
    for idx in order:
        seeds = layouts[names[int(idx)]]
        placed += len(seeds)
        # the split furthest below its proportional quota after this layout is added (ties: the larger share first)
        deficits = [p * placed - len(b) for p, b in zip(_PROPORTIONS, buckets, strict=True)]
        best = max(range(3), key=lambda i: (deficits[i], -i))
        buckets[best].extend(seeds)
    assert sum(len(b) for b in buckets) == total
    return SplitAssignment(*(tuple(sorted(b)) for b in buckets))


def assign_splits(scenarios: Sequence[tuple[int, str]], *, rng_seed: int) -> SplitAssignment:
    """Assign the (scenario_seed, layout_id) pairs of one family to train / validation / test (80 / 10 / 10 %).

    All seeds of a layout land in one split. The result is deterministic for the input and `rng_seed` and independent
    of the input order; with one seed per layout each count is within +-1 of its target, in general within the size of
    the largest layout.
    """
    return _assign(_validated_scenarios(scenarios, rng_seed), [rng_seed])


def build_arm_splits(
    pit: Sequence[tuple[int, str]], crusher: Sequence[tuple[int, str]], *, rng_seed: int
) -> ArmSplits:
    """Splits per family; the unstructured arm reuses exactly the structured pit training seeds."""
    pit_split = _assign(_validated_scenarios(pit, rng_seed), [rng_seed, 0])
    crusher_split = _assign(_validated_scenarios(crusher, rng_seed), [rng_seed, 1])
    return ArmSplits(pit=pit_split, crusher=crusher_split, unstructured_train=pit_split.train)


# ----------------------------------------------------------------------------------------------------------------
# perceptual hashes and leaks
# ----------------------------------------------------------------------------------------------------------------
def hamming64(a: int, b: int) -> int:
    """Number of differing bits of two 64-bit hashes."""
    for h in (a, b):
        if not _is_int(h) or not 0 <= h <= 2**64 - 1:
            raise ValueError(f"hash must be an int in 0..2**64-1, got {h!r}")
    return (a ^ b).bit_count()


def phash64(path: Path) -> int:
    """64-bit perceptual hash of an image file: `imagehash.phash` (hash_size 8) as an integer."""
    import imagehash
    from PIL import Image

    with Image.open(path) as img:
        return int(str(imagehash.phash(img)), 16)


def _checked_records(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    for r in records:
        if (
            not isinstance(r, Mapping)
            or not isinstance(r.get("record_id"), str)
            or not _is_int(r.get("scenario_seed"))
            or not isinstance(r.get("layout_id"), str)
            or r.get("split") not in _SPLIT_NAMES
        ):
            raise SplitError("scenario-invalid", f"malformed record {r!r}: needs record_id, scenario_seed, layout_id, split")
    return list(records)


def _cross_split_pairs(records: list[Mapping[str, Any]], key: str, reason: str) -> list[tuple[str, str, str]]:
    groups: dict[Any, list[Mapping[str, Any]]] = {}
    for r in records:
        groups.setdefault(r[key], []).append(r)
    pairs = []
    for members in groups.values():
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                if a["split"] != b["split"]:
                    pairs.append((a["record_id"], b["record_id"], reason))
    return pairs


def check_leaks(
    records: Sequence[Mapping[str, Any]], *, root: Path | None = None, hashes: Mapping[str, int] | None = None
) -> None:
    """Raise `SplitError("split-leak")` listing every leaking pair; return `None` when there is none.

    A leak is a scenario seed or a layout id in two splits, or a test image whose 64-bit perceptual hash is within
    Hamming distance 4 of a training or validation image. Hashes come from `hashes[record_id]`, else from the image file
    below `root`; without either, the hash check is not made.
    """
    recs = _checked_records(records)
    pairs = _cross_split_pairs(recs, "scenario_seed", "scenario_seed") + _cross_split_pairs(recs, "layout_id", "layout_id")
    if hashes is not None or root is not None:
        values: dict[str, int] = {}
        for r in recs:
            rid = r["record_id"]
            if hashes is not None and rid in hashes:
                values[rid] = int(hashes[rid])
                continue
            image = r.get("image")
            if root is None or not isinstance(image, Mapping) or not isinstance(image.get("path"), str):
                raise SplitError("scenario-invalid", f"no perceptual hash and no image file for record {rid}")
            values[rid] = phash64(Path(root) / image["path"])
        others = [r for r in recs if r["split"] != "test"]
        other_hashes = np.array([values[r["record_id"]] for r in others], dtype=np.uint64)
        for t in (r for r in recs if r["split"] == "test"):
            if other_hashes.size == 0:
                break
            distance = np.bitwise_count(other_hashes ^ np.uint64(values[t["record_id"]]))
            for k in np.nonzero(distance <= HAMMING_LEAK)[0]:
                pairs.append((others[int(k)]["record_id"], t["record_id"], "phash"))
    if pairs:
        raise SplitError("split-leak", f"{len(pairs)} leaking pair(s) between splits", pairs)


def arm_volume_ok(requested: int, valid: int) -> bool:
    """True iff at least 95 % of the requested images of an arm are valid (exact integer arithmetic)."""
    if not _is_int(requested) or not _is_int(valid) or requested < 1 or valid < 0 or valid > requested:
        raise SplitError("volume-invalid", f"requested {requested!r} and valid {valid!r} must be ints with 0 <= valid <= requested >= 1")
    return 100 * valid >= 95 * requested
