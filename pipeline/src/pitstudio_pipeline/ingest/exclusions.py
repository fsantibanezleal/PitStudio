"""Exclusion rules: the only way records leave a dataset (FR-008-22, P-008-04).

No statistical fence exists here: a value inside its physical bounds is never removed, extremes included. Rows leave
only through rules declared in the recipe parameters (so they enter the cache key), and each rule's removal count is
returned for the manifest.

A rule is a mapping with a unique `id` and exactly one of
- `{"column": c, "min": lo | None, "max": hi | None}`: keep rows with `lo <= value <= hi` (both bounds inclusive);
- `{"crop": {"x": cx, "y": cy, "bbox": [xmin, ymin, xmax, ymax]}}`: keep rows inside the area-of-interest box (edges
  inclusive).
Rules apply in order and a row is counted by the first rule that removes it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl


@dataclass(frozen=True)
class ExclusionResult:
    """The frame after the rules and, in rule order, how many records each removed."""

    frame: pl.DataFrame
    removed: list[dict[str, Any]]


def _finite_or_none(value: Any, what: str) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{what}: bound {value!r} is not finite")
    return number


def _keep_mask(rule: Mapping[str, Any], frame: pl.DataFrame) -> pl.Expr:
    rid = rule["id"]
    has_column, has_crop = "column" in rule, "crop" in rule
    if has_column == has_crop:
        raise ValueError(f"rule {rid!r} needs exactly one of `column` and `crop`")
    if has_column:
        column = rule["column"]
        if column not in frame.columns:
            raise ValueError(f"rule {rid!r}: no column {column!r}")
        low, high = _finite_or_none(rule.get("min"), f"rule {rid!r}"), _finite_or_none(rule.get("max"), f"rule {rid!r}")
        keep = pl.lit(True)
        if low is not None:
            keep &= pl.col(column) >= low
        if high is not None:
            keep &= pl.col(column) <= high
        return keep
    crop = rule["crop"]
    x, y, box = crop["x"], crop["y"], crop["bbox"]
    for name in (x, y):
        if name not in frame.columns:
            raise ValueError(f"rule {rid!r}: no column {name!r}")
    if len(box) != 4:
        raise ValueError(f"rule {rid!r}: bbox needs four numbers")
    xmin, ymin, xmax, ymax = (_finite_or_none(v, f"rule {rid!r}") for v in box)
    if None in (xmin, ymin, xmax, ymax) or xmin > xmax or ymin > ymax:  # type: ignore[operator]
        raise ValueError(f"rule {rid!r}: bbox must be finite and not inverted")
    return pl.col(x).is_between(xmin, xmax) & pl.col(y).is_between(ymin, ymax)


def apply_exclusions(frame: pl.DataFrame, rules: Sequence[Mapping[str, Any]]) -> ExclusionResult:
    """Apply the declared rules in order; a malformed rule raises before anything is removed."""
    seen: set[str] = set()
    masks = []
    for rule in rules:
        rid = rule.get("id")
        if not isinstance(rid, str) or not rid or rid in seen:
            raise ValueError(f"rule id {rid!r} is missing, empty or used twice")
        seen.add(rid)
        masks.append((rid, _keep_mask(rule, frame)))
    current, removed = frame, []
    for rid, keep in masks:
        kept = current.filter(keep.fill_null(False))
        removed.append({"rule": rid, "removed": current.height - kept.height})
        current = kept
    return ExclusionResult(current, removed)
