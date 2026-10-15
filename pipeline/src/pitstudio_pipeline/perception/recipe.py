"""The default SDG recipe (DC-009-03) and the plan of its three arms (FR-009-03)."""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_SEED = 20261007
_STRUCTURED_PIT_TRAIN = "structured-pit-train"

# Texture pool of the default recipe: the contract example's entries. The digests belong to the example pool; the SDG
# job
# passes the staged CC0 pool (ids, source, SHA-256 of the real files) to `default_recipe(texture_pool=...)`.
_EXAMPLE_POOL: tuple[dict[str, str], ...] = (
    {
        "id": "rock-quartz-monzonite-01",
        "source_id": "ambientcg",
        "sha256": "a0b1c2d3e4f5061728394a5b6c7d8e9f0f1e2d3c4b5a69788796a5b4c3d2e1f0",
        "spdx": "CC0-1.0",
    },
    {
        "id": "rock-gravel-02",
        "source_id": "polyhaven",
        "sha256": "28394a5b6c7d8e9f8796a5b4c3d2e1f092a3b4c5d6e7f80928394a5b6c7d8e9f",
        "spdx": "CC0-1.0",
    },
    {
        "id": "rock-limestone-01",
        "source_id": "ambientcg",
        "sha256": "0f1e2d3c4b5a697892a3b4c5d6e7f8090f1e2d3c4b5a697892a3b4c5d6e7f809",
        "spdx": "CC0-1.0",
    },
    {
        "id": "tex-rusty-metal-03",
        "source_id": "polyhaven",
        "sha256": "8796a5b4c3d2e1f028394a5b6c7d8e9f92a3b4c5d6e7f8098796a5b4c3d2e1f0",
        "spdx": "CC0-1.0",
    },
)


@dataclass(frozen=True)
class ArmPlan:
    """One requested arm: the image count and, for the unstructured arm, the seeds and layouts it reuses."""

    image_count: int
    scenario_seeds: tuple[int, ...] | None
    layout_ids: tuple[str, ...] | None


def default_recipe(
    texture_pool: Sequence[dict[str, str]] | None = None, lithologies: dict[str, list[str]] | None = None
) -> dict[str, Any]:
    """The default DC-009-03 document: three arms of 10,000 images, `x_os` 1.0 m, drying time 60 min."""
    pool = [dict(t) for t in (texture_pool if texture_pool is not None else _EXAMPLE_POOL)]
    litho = (
        lithologies
        if lithologies is not None
        else {"quartz_monzonite": ["rock-quartz-monzonite-01", "rock-gravel-02"], "limestone": ["rock-limestone-01"]}
    )
    return {
        "schema_version": "1.0",
        "seed": DEFAULT_SEED,
        "x_os_m": 1.0,
        "drying_time_min": 60,
        "arms": [
            {"family": "pit", "arm": "structured", "image_count": 10000, "seed_source": "own"},
            {"family": "crusher", "arm": "structured", "image_count": 10000, "seed_source": "own"},
            {"family": "pit", "arm": "unstructured", "image_count": 10000, "seed_source": _STRUCTURED_PIT_TRAIN},
        ],
        "structured": {
            "sun": {"source": "solar-position", "year": 2025, "min_elevation_deg": 5},
            "dust": {"source": "plume-field"},
            "wet_roads": {"source": "watering-schedule"},
            "placement": {"source": "pit-design", "max_base_offset_m": 0.05},
            "rock_textures": {"source": "lithology-cc0", "lithologies": copy.deepcopy(litho)},
        },
        "unstructured": {
            "textures": "whole-pool-uniform",
            "light_intensity_factor": {"distribution": "log-uniform", "min": 0.1, "max": 10},
            "colour_temperature_k": {"distribution": "uniform", "min": 2000, "max": 12000},
            "sun_direction": "upper-hemisphere-uniform",
            "object_positions": "visible-ground-uniform",
            "distractors": {"distribution": "uniform-integer", "min": 0, "max": 20},
        },
        "texture_pool": pool,
    }


def resolve_arms(
    recipe: dict[str, Any], structured_pit_train: Sequence[tuple[int, str]]
) -> dict[tuple[str, str], ArmPlan]:
    """Plan of every arm of `recipe`, keyed by (family, arm).

    The unstructured arm holds exactly the (seed, layout) pairs of the structured pit training split, in order.
    """
    plans: dict[tuple[str, str], ArmPlan] = {}
    for arm in recipe["arms"]:
        key = (arm["family"], arm["arm"])
        if key in plans:
            raise ValueError(f"duplicate arm {key[0]}/{key[1]} in the recipe")
        if arm["arm"] == "unstructured":
            if arm.get("seed_source") != _STRUCTURED_PIT_TRAIN:
                raise ValueError(
                    f"the unstructured arm must reuse the structured pit training seeds: seed_source is "
                    f"{arm.get('seed_source')!r}, expected {_STRUCTURED_PIT_TRAIN!r}"
                )
            seeds = tuple(int(s) for s, _ in structured_pit_train)
            layouts = tuple(str(layout) for _, layout in structured_pit_train)
            plans[key] = ArmPlan(int(arm["image_count"]), seeds, layouts)
        else:
            plans[key] = ArmPlan(int(arm["image_count"]), None, None)
    return plans
