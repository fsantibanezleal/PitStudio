"""`s30_train` inputs: training configuration, pinned checkpoints, training-input licence guard (FR-009-18, FR-009-19).

The detectors are fine-tuned from the upstream COCO-pretrained Apache-2.0 checkpoints (D-FINE-N, D-FINE-S) and the
upstream
segmentation-nano checkpoint (RF-DETR-Seg-N), each pinned by SHA-256, on the synthetic training split only, with bf16
autocast and no FP8 training and the upstream default loss coefficients. The run is recorded by `training_record`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MODELS: tuple[str, ...] = ("d-fine-n", "d-fine-s", "rf-detr-seg-n")
MAX_SEED = 2**63 - 1
# RF-DETR 1.11.1 `SegmentationTrainConfig` defaults (spec 009 section 7); D-FINE keeps its upstream loss configuration
_LOSS_COEFFICIENTS = {
    "rf-detr-seg-n": {"mask_ce_loss_coef": 5.0, "mask_dice_loss_coef": 5.0, "cls_loss_coef": 1.0},
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_LICENCE_CLASSES = frozenset(
    {"public-domain", "open-no-attribution", "own", "attribution", "share-alike", "display-only", "reference-only"}
)
_REFUSED_LICENCE_CLASSES = frozenset({"display-only", "reference-only"})
_REAL_PROBE = "real-probe"


class TrainError(Exception):
    """`code`: checkpoint-digest or training-input-licence; `inputs` names every offending input or file."""

    def __init__(self, code: str, message: str, inputs: Sequence[str] = ()) -> None:
        self.code = code
        self.inputs = tuple(inputs)
        shown = f": {', '.join(self.inputs)}" if self.inputs else ""
        super().__init__(f"{code}: {message}{shown}")


@dataclass(frozen=True)
class TrainConfig:
    """What one training run is allowed to be (FR-009-18)."""

    model: str
    base_checkpoint_id: str
    base_checkpoint_sha256: str
    seed: int
    epochs: int
    loss_coefficients: dict[str, float] = field(default_factory=dict)
    licence: str = "Apache-2.0"
    precision: str = "bf16"
    autocast_dtype: str = "bfloat16"
    fp8: bool = False
    split: str = "train"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def build_training_config(
    model: str, *, seed: int, epochs: int, pins: Mapping[str, Mapping[str, str]], precision: str = "bf16"
) -> TrainConfig:
    """The configuration of a run of `model` from its pinned checkpoint; ValueError names the offending argument."""
    if model not in MODELS:
        raise ValueError(f"model must be one of {MODELS}, got {model!r}")
    if not _is_int(seed) or not 0 <= seed <= MAX_SEED:
        raise ValueError(f"seed must be an int in 0..2**63-1, got {seed!r}")
    if not _is_int(epochs) or epochs < 1:
        raise ValueError(f"epochs must be an int >= 1, got {epochs!r}")
    if precision != "bf16":
        raise ValueError(f"precision must be 'bf16' (no fp8, fp16 or fp32 training), got {precision!r}")
    pin = pins.get(model) if isinstance(pins, Mapping) else None
    if (
        not isinstance(pin, Mapping)
        or not isinstance(pin.get("id"), str)
        or not pin["id"]
        or not isinstance(pin.get("sha256"), str)
        or not _HEX64.match(pin["sha256"])
    ):
        raise ValueError(f"pins[{model!r}] must hold a non-empty `id` and a 64 lower-case hex `sha256`, got {pin!r}")
    return TrainConfig(
        model=model,
        base_checkpoint_id=pin["id"],
        base_checkpoint_sha256=pin["sha256"],
        seed=seed,
        epochs=epochs,
        loss_coefficients=dict(_LOSS_COEFFICIENTS.get(model, {})),
    )


def file_sha256(path: Path) -> str:
    """SHA-256 of a file, read in blocks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_checkpoint(path: Path, expected_sha256: str) -> str:
    """The file's SHA-256 when it equals the pin; `TrainError("checkpoint-digest")` otherwise."""
    actual = file_sha256(path)  # FileNotFoundError when absent
    if actual != expected_sha256:
        raise TrainError(
            "checkpoint-digest",
            f"the file has SHA-256 {actual}, the pin is {expected_sha256}",
            (Path(path).name,),
        )
    return actual


def select_training_records(records: Sequence[Mapping[str, Any]], *, arm: str) -> list[dict[str, Any]]:
    """Training-split records of an ablation arm, input order kept: S = structured pit and crusher, U = unstructured pit
    and structured crusher. Validation and test records are never returned."""
    if arm not in ("S", "U"):
        raise ValueError(f"arm must be 'S' or 'U', got {arm!r}")
    out = []
    for r in records:
        if r.get("split") != "train":
            continue
        kind, family = r.get("arm"), r.get("family")
        if (arm == "S" and kind == "structured") or (
            arm == "U"
            and ((kind == "unstructured" and family == "pit") or (kind == "structured" and family == "crusher"))
        ):
            out.append(dict(r))
    return out


def training_set_digest(records: Sequence[Mapping[str, Any]]) -> str:
    """SHA-256 of the UTF-8 text of the lines `<record_id> <image sha256>` (newline-ended), sorted by record id."""
    if len(records) == 0:
        raise ValueError("records must not be empty")
    lines = sorted((r["record_id"], r["image"]["sha256"]) for r in records)
    text = "".join(f"{rid} {sha}\n" for rid, sha in lines)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def training_record(cfg: TrainConfig, *, checkpoint_sha256: str, training_set_sha256: str) -> dict[str, Any]:
    """The manifest `params` record of a run (DC-000-01): scalar values under snake_case keys."""
    return {
        "model": cfg.model,
        "base_checkpoint_id": cfg.base_checkpoint_id,
        "base_checkpoint_sha256": cfg.base_checkpoint_sha256,
        "checkpoint_sha256": checkpoint_sha256,
        "training_set_sha256": training_set_sha256,
        "seed": cfg.seed,
        "epochs": cfg.epochs,
        "precision": cfg.precision,
        "fp8": cfg.fp8,
        "split": cfg.split,
    }


def check_training_inputs(inputs: Sequence[Mapping[str, Any]]) -> None:
    """Refuse a manifest with a display-only or reference-only input or a real-probe image, naming every one."""
    offenders: list[str] = []
    for item in inputs:
        if not isinstance(item, Mapping):
            raise ValueError(f"training input {item!r} is not a mapping with id, licence_class and source")
        licence = item.get("licence_class")
        if licence not in _LICENCE_CLASSES:
            raise ValueError(
                f"licence_class {licence!r} of input {item.get('id')!r} is not one of {sorted(_LICENCE_CLASSES)}"
            )
        name = str(item.get("id"))
        if (licence in _REFUSED_LICENCE_CLASSES or item.get("source") == _REAL_PROBE) and name not in offenders:
            offenders.append(name)
    if offenders:
        raise TrainError(
            "training-input-licence",
            "inputs with a display-only or reference-only licence, or real-probe images",
            offenders,
        )
