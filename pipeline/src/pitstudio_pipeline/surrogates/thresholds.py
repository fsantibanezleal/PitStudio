"""Read the project thresholds (`specs/000-foundation/thresholds.yaml`, ratchet-only) for the surrogate checks.

The file is found by walking up from this module, or through the environment variable `PITSTUDIO_THRESHOLDS` when the
package runs outside a checkout. Nothing is hard-coded here: a missing file or key is an error, never a default.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from typing import Any

import yaml

RELATIVE = Path("specs") / "000-foundation" / "thresholds.yaml"


@cache
def load_thresholds() -> dict[str, Any]:
    override = os.environ.get("PITSTUDIO_THRESHOLDS")
    candidates = [Path(override)] if override else [parent / RELATIVE for parent in Path(__file__).resolve().parents]
    for path in candidates:
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    raise FileNotFoundError(f"thresholds.yaml not found (looked for {RELATIVE}; set PITSTUDIO_THRESHOLDS)")


def model_threshold(key: str) -> Any:
    """`models.<key>` of the thresholds file."""
    models = load_thresholds()["models"]
    if key not in models:
        raise KeyError(f"thresholds.yaml has no models.{key}")
    return models[key]
