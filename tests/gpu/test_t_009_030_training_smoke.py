# ruff: noqa: E501
"""T-009-030 (GPU half): a bf16 fine-tune smoke run of D-FINE-N from its pinned upstream checkpoint (FR-009-18). Marked `gpu`:
never run in CI and not run during the red phase (the GPU belongs to the scheduled jobs).

Oracles (independent of the code under test): `hashlib.sha256` of the base checkpoint, of the written checkpoint and of the
fixture images; `math.isfinite` for every loss; the manifest record is compared with the one built by the CPU-tested
`training_record` from digests computed here; the fixture data set is 16 synthetic rectangles drawn with Pillow (the exact
boxes are known by construction), so no model output is used as a label.

Environment of the scheduled job: `PITSTUDIO_DFINE_N_CHECKPOINT` = path of the upstream COCO-pretrained D-FINE-N checkpoint (downloaded
by the asset staging; its SHA-256 is computed here and used as the pin).

Expected public API (module `pitstudio_pipeline.perception.train`, in addition to tests/unit/test_t_009_030_training_inputs.py):

    TrainResult                      frozen dataclass: checkpoint_path: pathlib.Path, record: dict (training_record of the run),
                                     losses: tuple[float, ...] (one per optimisation step), autocast_dtype: str, fp8_used: bool,
                                     steps: int
    run_training(cfg: TrainConfig, *, records: Sequence[Mapping], root: pathlib.Path, checkpoint_path: pathlib.Path,
                 out_dir: pathlib.Path, max_steps: int | None = None) -> TrainResult
        verifies `checkpoint_path` against cfg.base_checkpoint_sha256 (TrainError "checkpoint-digest"), runs
        check_training_inputs and select_training_records, fine-tunes with torch.autocast(device_type="cuda", dtype=torch.bfloat16)
        for cfg.epochs epochs (at most `max_steps` optimisation steps when given), writes one checkpoint per epoch
        under out_dir and returns the last; `record` = training_record(cfg, checkpoint_sha256=<digest of the checkpoint written>,
        training_set_sha256=training_set_digest(selected records)).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_pipeline.perception import train  # noqa: E402


def _fixture(root: Path, n: int = 16) -> list[dict]:
    """16 crusher-family records over 96 x 96 images with one known boulder rectangle each; one shared COCO file."""
    import numpy as np
    from PIL import Image

    base = "sensors/s3-crusher/shard-0001"
    (root / base / "rgb").mkdir(parents=True, exist_ok=True)
    (root / base / "semantic").mkdir(parents=True, exist_ok=True)
    (root / base / "depth").mkdir(parents=True, exist_ok=True)
    images, annotations, records = [], [], []
    rng = np.random.default_rng(3)
    for i in range(1, n + 1):
        img = rng.integers(0, 40, size=(96, 96, 3), dtype=np.uint8)
        x, y, w, h = 20 + i, 30, 30, 24
        img[y : y + h, x : x + w] = 220
        sem = np.zeros((96, 96), dtype=np.uint8)
        sem[y : y + h, x : x + w] = 5
        Image.fromarray(img).save(root / base / "rgb" / f"{i:06d}.png")
        Image.fromarray(sem).save(root / base / "semantic" / f"{i:06d}.png")
        np.save(root / base / "depth" / f"{i:06d}.npy", np.full((96, 96), 9.0, dtype=np.float32))
        images.append({"id": i, "file_name": f"rgb/{i:06d}.png", "width": 96, "height": 96})
        annotations.append(kit.rect_ann(i, i, 5, float(x), float(y), float(w), float(h)))
    coco = {"images": images, "annotations": annotations, "categories": kit.coco_doc()["categories"]}
    (root / base / "coco_instances.json").write_text(json.dumps(coco), encoding="utf-8")

    def entry(rel: str, extra: dict | None = None) -> dict:
        data = (root / rel).read_bytes()
        return {"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), **(extra or {})}

    for i in range(1, n + 1):
        rec = kit.index_record("valid-crusher")
        rec["record_id"] = f"crusher-s-{i:06d}"
        rec["split"] = "train"
        rec["coco_image_id"] = i
        rec["image"] = entry(
            f"{base}/rgb/{i:06d}.png", {"width_px": 96, "height_px": 96, "format": "png", "colour_space": "srgb"}
        )
        rec["semantic_mask"] = entry(f"{base}/semantic/{i:06d}.png", {"width_px": 96, "height_px": 96, "format": "png"})
        rec["depth"] = entry(
            f"{base}/depth/{i:06d}.npy",
            {
                "width_px": 96,
                "height_px": 96,
                "format": "npy",
                "dtype": "float32",
                "unit": "m",
                "quantity": "distance-to-camera",
            },
        )
        rec["coco"] = entry(f"{base}/coco_instances.json")
        records.append(rec)
    return records


@pytest.mark.gpu
@pytest.mark.req("FR-009-18")
def test_a_bf16_fine_tune_smoke_run_writes_a_checkpoint_losses_and_the_manifest_record(tmp_path: Path) -> None:
    import torch

    assert torch.cuda.is_available(), "this test needs a CUDA device (marked gpu; runs only in the scheduled GPU job)"
    assert torch.cuda.is_bf16_supported()
    base = Path(os.environ["PITSTUDIO_DFINE_N_CHECKPOINT"])
    base_sha = hashlib.sha256(base.read_bytes()).hexdigest()
    pins = {"d-fine-n": {"id": "dfine-n-coco", "sha256": base_sha}}
    cfg = train.build_training_config("d-fine-n", seed=20261007, epochs=1, pins=pins)
    records = _fixture(tmp_path / "data")
    result = train.run_training(
        cfg, records=records, root=tmp_path / "data", checkpoint_path=base, out_dir=tmp_path / "out", max_steps=4
    )
    assert result.checkpoint_path.is_file()
    assert result.autocast_dtype == "bfloat16"
    assert result.fp8_used is False
    assert 1 <= result.steps <= 4
    assert len(result.losses) == result.steps
    assert all(math.isfinite(x) for x in result.losses)
    ckpt_sha = hashlib.sha256(result.checkpoint_path.read_bytes()).hexdigest()
    selected = train.select_training_records(records, arm="S")
    assert len(selected) == 16
    assert result.record == train.training_record(
        cfg, checkpoint_sha256=ckpt_sha, training_set_sha256=train.training_set_digest(selected)
    )
    assert result.record["base_checkpoint_sha256"] == base_sha
    assert result.record["checkpoint_sha256"] != base_sha  # the weights moved


@pytest.mark.gpu
@pytest.mark.req("FR-009-18")
def test_a_tampered_base_checkpoint_is_refused_before_any_training_step(tmp_path: Path) -> None:
    base = tmp_path / "fake.pth"
    base.write_bytes(kit.payload(2048, 5))
    pins = {"d-fine-n": {"id": "dfine-n-coco", "sha256": "0" * 64}}
    cfg = train.build_training_config("d-fine-n", seed=1, epochs=1, pins=pins)
    with pytest.raises(train.TrainError) as exc:
        train.run_training(
            cfg,
            records=_fixture(tmp_path / "data", 2),
            root=tmp_path / "data",
            checkpoint_path=base,
            out_dir=tmp_path / "out",
        )
    assert exc.value.code == "checkpoint-digest"
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())
