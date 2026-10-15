"""Entry points of the queued perception GPU jobs: `python -m pitstudio_pipeline.perception.jobs <job> [--dry-run]`.

Jobs: `train-d-fine-n`, `train-d-fine-s`, `train-rf-detr-seg-n` (s30_train on the arm S training split).
A dry run runs on the CPU and stops before CUDA is used: it asserts
`torch.cuda.is_available()`, checks the pinned checkpoint digest and the D-FINE code pin, builds the model and loads the
pretrained weights. Environment: `PITSTUDIO_DATA` (data root; index at `<root>/processed/perception/index.jsonl`),
`PITSTUDIO_MODELS` (output root) and the checkpoint variables of `pins`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pitstudio_pipeline.perception import gpujob, pins
from pitstudio_pipeline.perception.train import build_training_config, run_training, verify_checkpoint

EPOCHS = {"d-fine-n": 40, "d-fine-s": 40, "rf-detr-seg-n": 30}
SEED = 20261007


def _roots() -> tuple[Path, Path]:
    return Path(os.environ["PITSTUDIO_DATA"]), Path(os.environ["PITSTUDIO_MODELS"])


def _dry_run(model: str) -> None:
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
    index = _roots()[0] / "processed" / "perception" / "index.jsonl"
    print(f"[dry-run] index {index}: {'present' if index.is_file() else 'ABSENT (the SDG job has not produced it)'}")
    print("[dry-run] ok, stopping before CUDA")


def _train(model: str) -> None:
    from pitstudio_pipeline.perception.loader import read_index

    data, models = _roots()
    index = read_index(data / "processed" / "perception" / "index.jsonl")
    cfg = build_training_config(model, seed=SEED, epochs=EPOCHS[model], pins=pins.pins_for_config())
    out = models / "perception" / model
    with gpujob.gpu_session() as guard:
        result = run_training(
            cfg,
            records=list(index.records),
            root=data / "processed" / "perception",
            checkpoint_path=pins.checkpoint_path(model),
            out_dir=out,
            guard=guard,
        )
    (out / "training_record.json").write_text(json.dumps(result.record, sort_keys=True), encoding="utf-8")
    print(f"[{model}] done: {result.checkpoint_path}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("job", choices=["train-d-fine-n", "train-d-fine-s", "train-rf-detr-seg-n"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    model = args.job.removeprefix("train-")
    _dry_run(model) if args.dry_run else _train(model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
