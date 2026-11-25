"""The C1 recipe rules that the generic recipe schema cannot state (FR-010-40).

``studio plan`` calls ``validate_recipe`` while it validates a recipe, so an invalid C1 recipe is rejected with a JSON
pointer
before the stage DAG is built: an unknown method, model or stratum (keyword ``enum``), a cut-off outside (0, 1)
(``range``),
duplicate cut-offs (``uniqueItems``) and test seeds that overlap the training (or validation) seeds (``overlap``). A
recipe of
another case is not judged here. ``load_recipe`` reads ``studio/recipes/cases/c1.yaml`` through the strict loader.
"""

from __future__ import annotations

import math
from itertools import pairwise
from pathlib import Path
from typing import Any

from pitstudio.contracts import load_yaml, validate

METHODS = ("inverse_velocity", "bayesian_ttf", "tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned")
MODELS = METHODS[2:]
STRATA = (
    "snr_obs",
    "half_snr_obs",
    "double_snr_obs",
    "snr_obs_atmospheric",
    "nominal_10",
    "nominal_30",
    "nominal_100",
)
_ENUMS = {"methods": METHODS, "models": MODELS, "strata": STRATA}


class InvalidRecipeError(ValueError):
    """An invalid C1 recipe: ``pointer`` locates the value, ``keyword`` is enum, range, uniqueItems or overlap."""

    def __init__(self, pointer: str, keyword: str, message: str) -> None:
        super().__init__(f"{pointer}: {message}")
        self.pointer = pointer
        self.keyword = keyword


def _blocks(splits: Any, n_strata: int) -> list[tuple[str, int, int]]:
    out = []
    for name, count_key in (("train", "count"), ("validation", "count"), ("test", "count_per_stratum")):
        node = splits.get(name) if isinstance(splits, dict) else None
        if not isinstance(node, dict):
            continue
        start, count = node.get("start"), node.get(count_key)
        if (
            isinstance(start, int)
            and isinstance(count, int)
            and not isinstance(start, bool)
            and not isinstance(count, bool)
        ):
            out.append((name, start, count * (n_strata if name == "test" else 1)))
    return out


def validate_recipe(recipe: Any) -> None:
    """Raise ``InvalidRecipeError`` for a C1 recipe that breaks the rules above; do nothing for other recipes."""
    if not isinstance(recipe, dict) or recipe.get("case") != "C1":
        return
    for index, stage in enumerate(recipe.get("stages") or []):
        params = stage.get("params") if isinstance(stage, dict) else None
        if not isinstance(params, dict):
            continue
        base = f"/stages/{index}/params"
        for key, allowed in _ENUMS.items():
            values = params.get(key)
            if isinstance(values, list):
                for j, v in enumerate(values):
                    if v not in allowed:
                        raise InvalidRecipeError(f"{base}/{key}/{j}", "enum", f"{v!r} is not one of {list(allowed)}")
        cutoffs = params.get("cutoffs")
        if isinstance(cutoffs, list):
            for j, c in enumerate(cutoffs):
                if isinstance(c, bool) or not isinstance(c, int | float) or not (math.isfinite(c) and 0.0 < c < 1.0):
                    raise InvalidRecipeError(f"{base}/cutoffs/{j}", "range", f"cut-off {c!r} must lie in (0, 1)")
            if len(set(cutoffs)) != len(cutoffs):
                raise InvalidRecipeError(f"{base}/cutoffs", "uniqueItems", "cut-offs must be distinct")
        splits = params.get("splits")
        if isinstance(splits, dict):
            strata = params.get("strata")
            blocks = sorted(_blocks(splits, len(strata) if isinstance(strata, list) else 4), key=lambda b: b[1])
            for (a, start_a, count_a), (b, start_b, _) in pairwise(blocks):
                if start_a + count_a > start_b:
                    raise InvalidRecipeError(f"{base}/splits", "overlap", f"the seed ranges of {a} and {b} overlap")


def load_recipe(path: str | Path) -> dict[str, Any]:
    """Read a recipe with the strict YAML loader, validate it against the schema and with ``validate_recipe``."""
    doc = load_yaml(Path(path))
    errors = validate(doc, "recipe")
    if errors:
        first = errors[0]
        raise InvalidRecipeError(first.pointer, "schema", first.message)
    validate_recipe(doc)
    return doc  # type: ignore[no-any-return]
