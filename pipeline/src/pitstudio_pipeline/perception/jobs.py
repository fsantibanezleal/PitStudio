"""Entry points of the queued perception jobs: `python -m pitstudio_pipeline.perception.jobs <job> [--dry-run]`.

GPU jobs: `train-d-fine-n`, `train-d-fine-s`, `train-d-fine-s-u` (the unstructured-arm ablation run),
`train-rf-detr-seg-n`
(s30_train on the pit-family training split of the SDG index) and `infer` (s40_infer of every trained model on the test
split). CPU job: `evaluate` (s50_evaluate over the prediction files, writes `detection-eval.json`). The crusher arm is
absent
until the spec 013 S3 producer exists, so detectors train and are scored on the pit family only and the report says so.

A dry run runs the real path on a tiny slice and stops before CUDA training: it asserts `torch.cuda.is_available()`,
checks
the pinned checkpoint digest and the D-FINE code pin, loads the pretrained weights, reads the SDG index (when present)
and
builds one training batch on the CPU. Environment: `PITSTUDIO_DATA` (data root; index at
`<root>/processed/perception/index.jsonl`), `PITSTUDIO_MODELS` (output root) and the checkpoint variables of `pins`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pitstudio_pipeline.perception import gpujob, pins
from pitstudio_pipeline.perception.train import build_training_config, run_training, verify_checkpoint

EPOCHS = {"d-fine-n": 40, "d-fine-s": 40, "rf-detr-seg-n": 30}
SEED = 20261007
TRAIN_JOBS = {
    "train-d-fine-n": ("d-fine-n", "S"),
    "train-d-fine-s": ("d-fine-s", "S"),
    "train-d-fine-s-u": ("d-fine-s", "U"),
    "train-rf-detr-seg-n": ("rf-detr-seg-n", "S"),
}


def _roots() -> tuple[Path, Path]:
    return Path(os.environ["PITSTUDIO_DATA"]), Path(os.environ["PITSTUDIO_MODELS"])


def _index_path() -> Path:
    return _roots()[0] / "processed" / "perception" / "index.jsonl"


def _records() -> list[dict[str, Any]]:
    from pitstudio_pipeline.perception.loader import read_index

    return [dict(r) for r in read_index(_index_path()).records]


def _out(model: str, arm: str) -> Path:
    return _roots()[1] / "perception" / f"{model}-{arm}"


def _dry_run_train(model: str, arm: str) -> None:
    from pitstudio_pipeline.perception.train import select_training_records

    gpujob.assert_cuda()
    ckpt = pins.checkpoint_path(model)
    digest = verify_checkpoint(ckpt, pins.CHECKPOINT_PINS[model]["sha256"])
    print(f"[dry-run] CUDA available; checkpoint {ckpt.name} sha256 {digest} matches the pin")
    if model == "rf-detr-seg-n":
        from rfdetr import RFDETRSegNano

        RFDETRSegNano(pretrain_weights=str(ckpt), num_classes=5, trust_checkpoint=True, device="cpu")
        print("[dry-run] RF-DETR-Seg-N built with 5 classes from the pinned checkpoint")
    else:
        from pitstudio_pipeline.perception import dfine

        cfg = dfine.make_config(model, num_classes=5)
        loaded, skipped = dfine.load_matched(cfg.model, dfine.read_state(ckpt))
        print(f"[dry-run] D-FINE code at the pinned commit; {loaded} weights loaded, {len(skipped)} re-initialised")
    if _index_path().is_file():
        records = _records()
        train = select_training_records(records, arm=arm)
        print(f"[dry-run] index read: {len(records)} records, {len(train)} in the arm {arm} training split")
        if not train:
            raise RuntimeError(f"the index has no arm {arm} training record")
        root = _roots()[0] / "processed" / "perception"
    else:
        print(f"[dry-run] index {_index_path()} is absent (job 29 has not written it): a 4-image fixture stands in")
        root = Path(os.environ["PITSTUDIO_TMP"])  # scratch folder of the dry run, set by the job script
        train = _fixture_records(root)
    if model != "rf-detr-seg-n":
        from pitstudio_pipeline.perception.train_dfine import smoke_step

        loss = smoke_step(model, ckpt, train[:2], root, SEED, "cpu")
        print(f"[dry-run] one real optimiser step on the CPU (bf16 forward, float32 criterion): loss {loss:.4f}")
    print("[dry-run] ok, stopping before CUDA")


def _fixture_records(tmp: Path) -> list[dict[str, Any]]:
    """Four 128 x 96 synthetic images with one known box each, as index-like records, written under `tmp`."""
    import numpy as np
    from PIL import Image

    base = tmp / "fixture"
    (base / "rgb").mkdir(parents=True, exist_ok=True)
    images, annotations, records = [], [], []
    for i in range(1, 5):
        img = np.random.default_rng(i).integers(0, 40, size=(96, 128, 3), dtype=np.uint8)
        x, y, w, h = 20 + i, 30, 40, 30
        img[y : y + h, x : x + w] = 220
        Image.fromarray(img).save(base / "rgb" / f"{i:06d}.png")
        images.append({"id": i, "file_name": f"fixture/rgb/{i:06d}.png", "width": 128, "height": 96})
        annotations.append(
            {
                "id": i,
                "image_id": i,
                "category_id": 1,
                "bbox": [x, y, w, h],
                "area": w * h,
                "iscrowd": 0,
                "segmentation": [],
            }
        )
    cats = [{"id": 1, "name": "haul_truck"}]
    (base / "coco.json").write_text(json.dumps({"images": images, "annotations": annotations, "categories": cats}))
    records.extend(
        {
            "record_id": f"fixture-{i}",
            "split": "train",
            "arm": "structured",
            "family": "pit",
            "image": {"path": f"fixture/rgb/{i:06d}.png"},
            "coco": {"path": "fixture/coco.json"},
            "coco_image_id": i,
        }
        for i in range(1, 5)
    )
    return records


def _train(model: str, arm: str) -> None:
    data, _ = _roots()
    cfg = build_training_config(model, seed=SEED, epochs=EPOCHS[model], pins=pins.pins_for_config())
    out = _out(model, arm)
    with gpujob.gpu_session() as guard:
        result = run_training(
            cfg,
            records=_records(),
            root=data / "processed" / "perception",
            checkpoint_path=pins.checkpoint_path(model),
            out_dir=out,
            guard=guard,
            arm=arm,
        )
    (out / "training_record.json").write_text(json.dumps(result.record, sort_keys=True), encoding="utf-8")
    print(f"[{model} arm {arm}] done: {result.checkpoint_path}")


def _trained() -> list[tuple[str, str, Path]]:
    """(model, arm, last checkpoint) of every training output found."""
    found = []
    for model, arm in sorted(set(TRAIN_JOBS.values())):
        ckpts = sorted(_out(model, arm).glob("checkpoint*.pth"))
        if ckpts:
            found.append((model, arm, ckpts[-1]))
    return found


def _infer(dry: bool) -> None:
    from pitstudio_pipeline.perception import infer

    gpujob.assert_cuda()
    found = _trained()
    print(f"[infer] trained models found: {[(m, a) for m, a, _ in found] or 'none'}")
    if dry:
        if _index_path().is_file():
            gt, _, _ = infer.build_test_gt(_records(), _roots()[0] / "processed" / "perception")
            print(f"[dry-run] test split: {len(gt['images'])} images, {len(gt['annotations'])} annotations")
        print("[dry-run] ok, stopping before CUDA")
        return
    if not found:
        raise RuntimeError("no trained checkpoint: run the s30_train jobs first")
    records, root = _records(), _roots()[0] / "processed" / "perception"
    out = _roots()[1] / "perception" / "predictions"
    out.mkdir(parents=True, exist_ok=True)
    with gpujob.gpu_session() as guard:
        for model, arm, ckpt in found:
            fn = infer.predict_rfdetr if model == "rf-detr-seg-n" else infer.predict_dfine
            detections = fn(ckpt, records, root, guard=guard)
            record = json.loads((ckpt.parent / "training_record.json").read_text(encoding="utf-8"))
            n_images = len(infer.test_records(records))
            body = {
                "model": model,
                "precision": "fp32",
                "arm": arm,
                "image_ids": list(range(1, n_images + 1)),
                "detections": detections,
                "provenance": {k: record[k] for k in ("checkpoint_sha256", "training_set_sha256", "seed", "epochs")},
                "fixture": False,
            }
            (out / f"{model}-{arm}-fp32.json").write_text(json.dumps(body), encoding="utf-8")
            print(f"[infer] {model} arm {arm}: {len(detections)} detections on {n_images} images")


def _evaluate(dry: bool) -> None:
    from pitstudio_pipeline.perception import infer, report, s50_evaluate

    data, models = _roots()
    if dry and not _index_path().is_file():
        print("[dry-run] index absent (job 29 has not written it): the evaluation path is checked on the index")
        return
    records = _records()
    gt, family, cluster = infer.build_test_gt(records, data / "processed" / "perception")
    preds = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((models / "perception" / "predictions").glob("*.json"))
    ]
    print(f"[evaluate] {len(gt['images'])} test images, {len(preds)} prediction sets")
    expected = [
        ("d-fine-s", "fp32", "S"),
        ("d-fine-n", "fp32", "S"),
        ("rf-detr-seg-n", "fp32", "S"),
        ("d-fine-s", "fp32", "U"),
    ]
    spec = {
        "run_id": os.environ.get("PITSTUDIO_RUN_ID", "20261015T000000Z-s50"),
        "gt": gt,
        "image_family": family,
        "image_cluster": cluster,
        "predictions": preds,
        "expected": expected,
        "bootstrap": {"seed": SEED},
        "family_status": {
            "crusher": {"status": "not run", "reason": "absent: the spec 013 S3 crusher producer is missing"}
        },
    }
    if dry:
        spec["bootstrap"] = {"seed": SEED, "resamples": 5, "ablation_resamples": 5}
        result = s50_evaluate.run_s50_evaluate(spec)
        print(f"[dry-run] evaluation path ok: partial={result.partial}, {len(result.report['per_class'])} rows")
        return
    result = s50_evaluate.run_s50_evaluate(spec)
    out = models / "perception" / "detection-eval.json"
    report.write_report(result.report, out)
    print(f"[evaluate] wrote {out} (partial={result.partial})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("job", choices=[*TRAIN_JOBS, "infer", "evaluate"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.job in TRAIN_JOBS:
        model, arm = TRAIN_JOBS[args.job]
        _dry_run_train(model, arm) if args.dry_run else _train(model, arm)
    elif args.job == "infer":
        _infer(args.dry_run)
    else:
        _evaluate(args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
