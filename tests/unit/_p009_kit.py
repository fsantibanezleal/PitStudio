"""Shared fixtures of the spec 009 acceptance tests (perception). Holds no test.

Imported by `tests/*/test_t_009_*.py` after `sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))`.
Locked with the first task that uses it. Standard library and numpy only (so every lane can import it); nothing here
calls the code under test. Provides:
- the spec's own contract examples (valid and hostile) as fresh deep copies: `example(name)`;
- builders of a valid COCO document and of a valid dataset-index record that tests then damage one field at a time;
- `sha256_hex`, a seeded byte payload, and the honesty label of FR-009-32 (U+2014 em dash).
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPEC009 = ROOT / "specs" / "009-perception"
EXAMPLES = SPEC009 / "contracts" / "examples"

HONESTY_LABEL = "calibrated synthetic — not validated against real data"  # FR-009-32 exact label
CLASS_NAMES = ("haul_truck", "shovel", "light_vehicle", "person", "boulder")  # FR-009-01, ids 1..5
HEX64 = "0123456789abcdef" * 4


def example(name: str) -> Any:
    """A fresh deep copy of a contract example of spec 009 (e.g. `coco-instances.valid.json`)."""
    return copy.deepcopy(json.loads((EXAMPLES / name).read_text(encoding="utf-8")))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def payload(n: int, seed: int = 0) -> bytes:
    """Deterministic pseudo-random bytes (numpy PCG64)."""
    return np.random.default_rng(seed).integers(0, 256, size=n, dtype=np.uint8).tobytes()


def coco_doc() -> dict[str, Any]:
    """The valid COCO example of DC-009-02 (two images 1280 x 720, three annotations, five categories)."""
    return example("coco-instances.valid.json")


def index_record(kind: str = "valid") -> dict[str, Any]:
    """A valid DC-009-01 record: `valid` (structured pit), `valid-unstructured` or `valid-crusher`."""
    return example(f"perception-dataset.{kind}.json")


def rect_ann(ann_id: int, image_id: int, category_id: int, x: float, y: float, w: float, h: float) -> dict[str, Any]:
    """A COCO annotation with an axis-aligned rectangle polygon (area w * h)."""
    return {
        "id": ann_id,
        "image_id": image_id,
        "category_id": category_id,
        "bbox": [x, y, w, h],
        "segmentation": [[x, y, x + w, y, x + w, y + h, x, y + h]],
        "area": w * h,
        "iscrowd": 0,
    }
