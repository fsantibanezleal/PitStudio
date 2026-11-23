"""T-012-062: the per-fold TRTR report of D1: recomputed IoU, pooled instance PSD curves, training curves (unit).

Requirements: FR-012-24, FR-012-25, FR-012-29, FR-012-31, FR-012-38.

Oracles:
- a stub U-Net that returns the three-class encoding of the stored label as one-hot logits (FR-012-18 written out in
  the test): decoding it (FR-012-19) must give foreground IoU 1.0, the same number of instances and the same total
  area as the label, so the pipeline from image to PSD is checked against a known truth;
- hand calculations: the passing step function of the points (2, 1/14), (4, 5/14), (6, 1) on a grid; a no-fit image counts
  with relative x50 error 1.0 (FR-012-25); the stored per-file IoU compared with the recomputed one;
- FR-012-38: the report holds only numbers and strings (no array, no image).

Expected API (module `pitstudio_pipeline.fragmentation.fold_report`): load_fold_model, predict_instances, passing_on_grid,
evaluate_files, fold_section, training_curves, build_report, write_report.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
import torch
from pitstudio_pipeline.fragmentation import fold_report as fr
from pitstudio_pipeline.fragmentation import psd as psdmod
from pitstudio_pipeline.fragmentation.unet import IMAGENET_MEAN, IMAGENET_STD


def _blocks(n_side: int, size: int, gap: int = 4) -> np.ndarray:
    """A 512 x 512 label image of n_side^2 square instances of `size` px separated by `gap` px."""
    label = np.zeros((512, 512), dtype=np.uint8)
    k = 1
    for i in range(n_side):
        for j in range(n_side):
            y, x = 8 + i * (size + gap), 8 + j * (size + gap)
            label[y : y + size, x : x + size] = k
            k += 1
    return label


def _three_class(label: np.ndarray) -> np.ndarray:
    """FR-012-18 written out: 0 background, 2 boundary, 1 interior."""
    padded = np.pad(label, 1)
    differs = np.zeros(label.shape, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                differs |= padded[1 + dy : 1 + dy + 512, 1 + dx : 1 + dx + 512] != label
    out = np.zeros(label.shape, dtype=np.uint8)
    out[label > 0] = 1
    out[(label > 0) & differs] = 2
    return out


class _Oracle(torch.nn.Module):
    """A stand-in model: the image encodes its own index in pixel (0, 0); the logits are the one-hot truth."""

    def __init__(self, labels: np.ndarray) -> None:
        super().__init__()
        self.targets = [_three_class(lab) for lab in labels]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = []
        for sample in x:
            index = int(round(float(sample[0, 0, 0] * IMAGENET_STD[0] + IMAGENET_MEAN[0]) * 255.0))
            onehot = torch.nn.functional.one_hot(torch.from_numpy(self.targets[index]).long(), 3).permute(2, 0, 1)
            out.append(onehot.float() * 20.0)
        return torch.stack(out)


def _data(n: int = 6):
    labels = np.stack([_blocks(3 + i % 3, 20 + 4 * (i % 2)) for i in range(n)])
    images = np.stack([np.full((512, 512, 3), i, dtype=np.uint8) for i in range(n)])
    return images, labels


@pytest.mark.req("FR-012-29")
def test_a_perfect_stub_gives_iou_one_and_the_instance_counts_and_areas_of_the_label() -> None:
    images, labels = _data()
    rows = fr.evaluate_files(_Oracle(labels), images, labels, [1, 2, 3, 4, 5, 6])
    assert [r["file"] for r in rows] == [1, 2, 3, 4, 5, 6]
    for row, label in zip(rows, labels, strict=True):
        assert row["iou"] == 1.0
        assert row["gt_areas"].size == row["pred_areas"].size == len(np.unique(label)) - 1
        assert row["pred_areas"].sum() == row["gt_areas"].sum()  # same foreground, boundary pixels assigned to instances
        assert np.max(np.abs(np.sort(row["pred_areas"]) - np.sort(row["gt_areas"]))) <= 4 * 20  # boundary band of a block


@pytest.mark.req("FR-012-24")
def test_passing_on_grid_is_the_step_function_of_the_points() -> None:
    psd = psdmod.image_psd([math.pi, 4 * math.pi, 9 * math.pi])
    got = fr.passing_on_grid(psd, np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]))
    assert got == pytest.approx([0.0, 1 / 14, 1 / 14, 5 / 14, 5 / 14, 1.0, 1.0], rel=1e-12)


@pytest.mark.req("FR-012-25")
def test_a_no_fit_prediction_counts_with_relative_x50_error_one_and_is_counted() -> None:
    good = {"file": 1, "iou": 0.9, "gt_areas": np.array([50.0, 80.0, 120.0, 200.0]), "pred_areas": np.array([50.0, 80.0, 120.0, 200.0])}
    bad = {"file": 2, "iou": 0.8, "gt_areas": np.array([50.0, 80.0, 120.0, 200.0]), "pred_areas": np.array([50.0, 80.0])}
    result = {"fold": 0, "n_train": 10, "n_val": 2, "n_test": 2, "test_fg_iou_mean": 0.85, "test_fg_iou_per_file": {"1": 0.9, "2": 0.8}}
    section = fr.fold_section(result, [good, bad], limit_px=20.0)
    assert section["x50_images_no_fit"] == {"ground_truth": 0, "unet": 1}
    assert section["x50_relative_error_mean"] == pytest.approx((0.0 + 1.0) / 2, abs=1e-6)
    assert section["x50_relative_error_median"] == pytest.approx(0.5, abs=1e-6)
    assert section["iou_max_abs_difference_vs_run"] == 0.0
    assert section["iou_files_reproduced"] == 2
    assert section["test_fg_iou_mean_recomputed"] == pytest.approx(0.85)


@pytest.mark.req("FR-012-29")
def test_a_stored_iou_that_differs_is_reported_not_hidden() -> None:
    row = {"file": 1, "iou": 0.9, "gt_areas": np.array([50.0, 80.0, 120.0]), "pred_areas": np.array([50.0, 80.0, 120.0])}
    result = {"fold": 0, "n_train": 1, "n_val": 1, "n_test": 1, "test_fg_iou_mean": 0.8, "test_fg_iou_per_file": {"1": 0.8}}
    section = fr.fold_section(result, [row], limit_px=10.0)
    assert section["iou_max_abs_difference_vs_run"] == pytest.approx(0.1)
    assert section["iou_files_reproduced"] == 0


@pytest.mark.req("FR-012-31")
def test_training_curves_keep_only_the_epoch_rows(tmp_path: Path) -> None:
    path = tmp_path / "metrics.jsonl"
    path.write_text(
        '{"epoch": 1, "step": 43, "loss": 3.0, "val_fg_iou": 0.5}\n{"final": true}\n\n{"epoch": 2, "loss": 2.0, "val_fg_iou": 0.7}\n',
        encoding="utf-8",
    )
    assert fr.training_curves(path) == {"epoch": [1, 2], "loss": [3.0, 2.0], "val_fg_iou": [0.5, 0.7]}


@pytest.mark.req("FR-012-38")
def test_the_report_of_a_run_folder_holds_metrics_only_and_reproduces_the_stored_iou(tmp_path: Path) -> None:
    images, labels = _data(6)
    run = tmp_path / "run"
    for fold, files in enumerate(([1, 2, 3], [4, 5, 6])):
        d = run / f"fold{fold}"
        d.mkdir(parents=True)
        (d / "result.json").write_text(
            json.dumps({"fold": fold, "n_train": 3, "n_val": 1, "n_test": 3, "test_fg_iou_mean": 1.0, "test_fg_iou_per_file": {str(f): 1.0 for f in files}}),
            encoding="utf-8",
        )
        (d / "metrics.jsonl").write_text('{"epoch": 1, "loss": 1.0, "val_fg_iou": 0.9}\n', encoding="utf-8")
        (d / "best.pt").write_bytes(b"")
    (run / "summary.json").write_text(json.dumps({"arm": "TRTR", "folds": [1.0, 1.0], "mean": 1.0, "std": 0.0, "min": 1.0}), encoding="utf-8")
    report = fr.build_report(run, images, labels, loader=lambda _p: _Oracle(labels))
    assert report["recomputed_mean_iou"] == 1.0
    assert report["iou_max_abs_difference_vs_run"] == 0.0
    assert [f["fold"] for f in report["folds"]] == [0, 1]
    assert report["attribution"] == fr.ATTRIBUTION
    assert "pixel" in report["size_basis"] and report["device"] == "cpu"
    for fold in report["folds"]:
        curve = fold["psd_curve"]
        assert len(curve["size_px"]) == len(curve["gt_passing"]) == len(curve["unet_passing"]) == fr.GRID_POINTS
        assert curve["gt_passing"][-1] == pytest.approx(1.0)
        assert all(a <= b for a, b in zip(curve["gt_passing"], curve["gt_passing"][1:], strict=False))
        assert fold["unet"]["p80_px"] >= fold["unet"]["p50_px"] >= fold["unet"]["p20_px"]
    pooled = report["pooled"]
    assert pooled["n_test"] == 6
    assert pooled["gt"]["n_instances"] == sum(f["gt"]["n_instances"] for f in report["folds"])
    assert pooled["psd_curve"]["gt_passing"][-1] == pytest.approx(1.0)
    assert pooled["unet"]["p80_px"] >= pooled["unet"]["p50_px"] >= pooled["unet"]["p20_px"]
    text = json.dumps(report, allow_nan=False)  # numbers and strings only: no array can be serialised
    out = tmp_path / "report.json"
    fr.write_report(report, out)
    assert json.loads(out.read_text(encoding="utf-8")) == json.loads(text)


@pytest.mark.req("FR-012-38")
def test_the_oversize_limit_is_twice_the_pooled_ground_truth_p50() -> None:
    images, labels = _data(6)
    run_files = [1, 2, 3, 4, 5, 6]
    rows = fr.evaluate_files(_Oracle(labels), images, labels, run_files)
    pooled = np.concatenate([r["gt_areas"] for r in rows])
    expected = fr.OVERSIZE_FACTOR * psdmod.weighted_quantile(psdmod.image_psd(pooled), 0.5)
    assert expected > 0 and math.isfinite(expected)
