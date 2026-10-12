"""The detector stages `s30_train` and `s40_infer` around an injected trainer and predictor, with the availability states of
spec 009: fixture propagation (FR-009-51) and stale-input refusal (FR-009-53).

The stage functions own what is checked and recorded, never the model work: the trainer and the predictor are callables, so a
fake can stand in for the GPU (and the contract-fixture index runs through the same code as a real one). A checkpoint, a
prediction file and a report made from a contract-fixture index carry `fixture: true`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitstudio_pipeline.perception.train import (
    TrainConfig,
    check_training_inputs,
    select_training_records,
    training_record,
    training_set_digest,
    verify_checkpoint,
)

PROVENANCES: tuple[str, ...] = ("fixture", "real")
_DRIVE = re.compile(r"^[A-Za-z]:")


class InputStaleError(Exception):
    """An image of the SDG index differs from the digest recorded there (`input-stale`, FR-002-69): the stage fails
    before any step and trains on nothing. `record_ids` lists every stale record in index order."""

    code = "input-stale"

    def __init__(self, record_ids: Sequence[str], expected: str, actual: str) -> None:
        self.record_ids = tuple(record_ids)
        self.record_id = self.record_ids[0]
        self.expected, self.actual = expected, actual
        super().__init__(f"{self.code}: image of record(s) {', '.join(self.record_ids)} differs from the recorded SHA-256")


def _check_provenance(provenance: object) -> str:
    if not isinstance(provenance, str) or provenance not in PROVENANCES:
        raise ValueError(f"provenance must be one of {PROVENANCES}, got {provenance!r}")
    return provenance


def _safe_relative(path: object) -> str:
    if (
        not isinstance(path, str)
        or path == ""
        or path.startswith(("/", "\\"))
        or "\\" in path
        or _DRIVE.match(path)
        or ".." in path.split("/")
    ):
        raise ValueError(f"image path {path!r} must be relative, without '..', a drive letter or a backslash")
    return path


def check_index_fresh(records: Sequence[Mapping[str, Any]], root: Path) -> None:
    """The SHA-256 of every record's image under `root` must equal the one in the index; else `InputStaleError`."""
    stale: list[str] = []
    first: tuple[str, str] | None = None
    for record in records:
        rel = _safe_relative(record["image"]["path"])
        digest = hashlib.sha256()
        with (Path(root) / rel).open("rb") as handle:  # FileNotFoundError for an absent image
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        if digest.hexdigest() != record["image"]["sha256"]:
            stale.append(record["record_id"])
            if first is None:
                first = (record["image"]["sha256"], digest.hexdigest())
    if stale and first is not None:
        raise InputStaleError(stale, *first)


@dataclass(frozen=True)
class TrainStageResult:
    """The training record (with `fixture`) and the path of the checkpoint written by the stage."""

    record: dict[str, Any]
    checkpoint_path: Path


def s30_train(
    *,
    records: Sequence[Mapping[str, Any]],
    provenance: str,
    config: TrainConfig,
    trainer: Callable[[list[dict[str, Any]], TrainConfig], bytes],
    out_dir: Path,
    root: Path | None = None,
    arm: str = "S",
) -> TrainStageResult:
    """Train on the training split of an arm: freshness (with `root`), licence guard, then the trainer; write the checkpoint
    and its record to `out_dir`. Nothing is written when a check fails."""
    provenance = _check_provenance(provenance)
    if root is not None:
        check_index_fresh(records, root)
    check_training_inputs(
        [
            {"id": r["record_id"], "licence_class": r["licence"]["licence_class"], "source": "synthetic"}
            for r in records
        ]
    )
    selected = select_training_records(records, arm=arm)
    set_digest = training_set_digest(selected)
    blob = trainer(selected, config)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = out / "checkpoint.bin"
    checkpoint.write_bytes(blob)
    record = training_record(
        config, checkpoint_sha256=hashlib.sha256(blob).hexdigest(), training_set_sha256=set_digest
    )
    record["fixture"] = provenance == "fixture"
    (out / "checkpoint.json").write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    return TrainStageResult(record, checkpoint)


def s40_infer(
    *,
    checkpoint: Mapping[str, Any],
    checkpoint_path: Path,
    records: Sequence[Mapping[str, Any]],
    provenance: str,
    predictor: Callable[[bytes, list[dict[str, Any]]], list[dict[str, Any]]],
    out_path: Path,
    precision: str = "fp32",
    arm: str = "S",
) -> dict[str, Any]:
    """Predict the test records with a verified checkpoint; the prediction file is `fixture` when the index or the
    checkpoint is."""
    provenance = _check_provenance(provenance)
    verify_checkpoint(Path(checkpoint_path), checkpoint["checkpoint_sha256"])
    blob = Path(checkpoint_path).read_bytes()
    recs = [dict(r) for r in records]
    detections = predictor(blob, recs)
    prediction = {
        "model": checkpoint["model"],
        "precision": precision,
        "arm": arm,
        "image_ids": [r["coco_image_id"] for r in recs],
        "detections": detections,
        "fixture": provenance == "fixture" or checkpoint.get("fixture") is True,
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(prediction, sort_keys=True), encoding="utf-8")
    return prediction
