"""Pinned upstream artefacts of the perception detectors (FR-009-18): checkpoints by SHA-256 and the D-FINE code by commit.

Values were read on 2026-10-12 from the staged files (`Data/Models/pitstudio/hub/MANIFEST.json`): the SHA-256 is of the
upstream file itself, computed after download. Every checkpoint is Apache-2.0.
"""

from __future__ import annotations

import os
from pathlib import Path

# upstream D-FINE code (Apache-2.0), github.com/Peterande/D-FINE, the head of the default branch on 2026-10-12
DFINE_CODE_REPOSITORY = "https://github.com/Peterande/D-FINE"
DFINE_CODE_COMMIT = "956d1709314c2c6a4df6f34de232054578a7449f"

# model -> pin: `id` names the upstream artefact, `sha256` is its digest; `source` says where it comes from
CHECKPOINT_PINS: dict[str, dict[str, str]] = {
    "d-fine-n": {
        "id": "dfine-n-coco",
        "sha256": "41973938d2784d38a9836990d805b8392855ebf611aba55f0f7add90e110744c",
        "source": "github.com/Peterande/storage release dfinev1.0, dfine_n_coco.pth",
    },
    "d-fine-s": {
        "id": "dfine-s-coco",
        "sha256": "48a6c8cc43eb57186843f752e2e8461ddd3326e0d3c575e71e6e960844683e89",
        "source": "huggingface.co/Peterande/D-FINE at 19214e91f5ce4c1e609022c38b1fc953c47404e7, dfine_s_coco.pth",
    },
    "rf-detr-seg-n": {
        "id": "rf-detr-seg-nano",
        "sha256": "a44613a4ecd6b5ba61a62002c600b0b6cb7a9da2936a45317ec4b62c635fb99b",
        "source": "rfdetr 1.11.1 model_weights (rf-detr-seg-n-ft.pth)",
    },
}

# environment variables that locate the staged files on a machine (never a path in the repository)
CHECKPOINT_ENV = {
    "d-fine-n": "PITSTUDIO_DFINE_N_CHECKPOINT",
    "d-fine-s": "PITSTUDIO_DFINE_S_CHECKPOINT",
    "rf-detr-seg-n": "PITSTUDIO_RFDETR_SEG_N_CHECKPOINT",
}
DFINE_CODE_ENV = "PITSTUDIO_DFINE_CODE"  # a checkout of DFINE_CODE_REPOSITORY at DFINE_CODE_COMMIT


def pins_for_config() -> dict[str, dict[str, str]]:
    """The pins as `build_training_config` takes them: model -> {"id", "sha256"}."""
    return {m: {"id": p["id"], "sha256": p["sha256"]} for m, p in CHECKPOINT_PINS.items()}


def checkpoint_path(model: str) -> Path:
    """Path of the staged upstream checkpoint of `model`, from its environment variable."""
    name = CHECKPOINT_ENV[model]
    value = os.environ.get(name)
    if not value:
        raise FileNotFoundError(f"environment variable {name} is not set: it locates the staged {model} checkpoint")
    return Path(value)
