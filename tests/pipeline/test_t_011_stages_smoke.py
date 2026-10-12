"""Smoke test of the GNS stages as the GPU runner calls them (train, evaluate, export, speed), on a tiny synthetic rollout
directory written by the test: Parquet payloads of an analytic collapse pile, four geometries (2 train, 1 val, 1 test), CPU.

Not a locked test: it checks that the stage functions chain (the stale-input guard, the fixture and label flags, the GPU-hour
record, the held-out report, the export card) and that the files the runner expects are written. Accuracy is not asserted.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("onnxruntime")
pq = pytest.importorskip("pyarrow.parquet")
import pyarrow as pa  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import _surrogate_fixtures as fx  # noqa: E402
from pitstudio_pipeline.surrogates.gns import stages  # noqa: E402

from pitstudio.surrogate_inputs import InputStaleError  # noqa: E402

VALID = json.loads(
    (ROOT / "specs" / "011-surrogates" / "contracts" / "examples" / "granular-rollout.valid.json").read_text(encoding="utf-8")
)
FRAMES = 8
GEOMS = {  # id -> (aspect ratio, column width, split)
    "g001": (0.5, 0.1, "train"),
    "g002": (4.0, 0.4, "train"),
    "g003": (1.0, 0.2, "val"),
    "g004": (2.2, 0.25, "test"),
}


def write_dataset(root: Path) -> None:
    (root / "meta").mkdir()
    (root / "payload").mkdir()
    for gid, (aspect, width, _) in GEOMS.items():
        for k, theta in enumerate(fx.REF_THETA):
            final = fx.collapse_cloud(theta, fx.REF_TAIL[k]).astype(np.float32)
            n = final.shape[0]
            frames = [final + np.float32(0.01 * (FRAMES - 1 - t)) for t in range(FRAMES)]
            table = {
                "frame": np.repeat(np.arange(FRAMES), n).astype(np.int32),
                "particle": np.tile(np.arange(n), FRAMES).astype(np.int32),
                "type": np.zeros(FRAMES * n, dtype=np.int32),
                "x": np.stack(frames)[:, :, 0].reshape(-1),
                "y": np.stack(frames)[:, :, 1].reshape(-1),
            }
            name = f"{gid}-s{1000 + k}"
            pq.write_table(pa.table(table), root / "payload" / f"{name}.parquet")
            meta = copy.deepcopy(VALID)
            meta.update(
                geometry_id=gid,
                packing_seed=1000 + k,
                particle_diameter_m=fx.D,
                connectivity_radius_m=2.5 * fx.D,
                frame_interval_s=fx.DT,
                particle_count=n,
                frame_times_s=[round(fx.DT * t, 6) for t in range(FRAMES)],
                rest_time_s=round(fx.DT * (FRAMES - 1), 6),
                bounds_m=[-2.0, 0.0, 3.0, 1.0],
            )
            meta["geometry"] = {"aspect_ratio": aspect, "column_width_m": fx.L0 if width else fx.L0}
            meta["geometry"]["column_width_m"] = width
            meta["store"] = {
                "format": "parquet",
                "path": f"payload/{name}.parquet",
                "sha256": hashlib.sha256((root / "payload" / f"{name}.parquet").read_bytes()).hexdigest(),
            }
            (root / "meta" / f"{name}.json").write_text(json.dumps(meta), encoding="utf-8")


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> tuple[stages.Dataset, Path, dict]:
    root = tmp_path_factory.mktemp("rollouts")
    write_dataset(root)
    split = {name: [g for g, (_, _, s) in GEOMS.items() if s == name] for name in ("train", "val", "test")}
    dataset = stages.Dataset(root, split=split)
    out = tmp_path_factory.mktemp("run")
    config = {
        "noise_scales": [0.0],
        "epochs": 1,
        "batch_size": 2,
        "lr": 1e-3,
        "latent": 8,
        "steps": 1,
        "samples_per_epoch": 4,
        "val_samples": 2,
        "connectivity_radius": 2.5 * fx.D,
        "checkpoint_steps": False,
    }
    manifest = stages.s30_train(dataset, out, config, seed=0, device="cpu", env={})
    return dataset, out, manifest


def test_train_writes_checkpoint_log_and_a_manifest_with_gpu_hours_label_and_inputs(run_dir) -> None:
    dataset, out, manifest = run_dir
    assert (out / "checkpoint.pt").is_file()
    assert (out / "train_log.json").is_file()
    saved = json.loads((out / "train_manifest.json").read_text(encoding="utf-8"))
    assert saved["gpu_hours"]["gns"]["budget_gpu_hours"] == 15.0
    assert "calibrated synthetic" in saved["label"]
    assert [i["id"] for i in saved["inputs"]][:2] == ["g001-s1000", "g001-s1001"]
    assert len(saved["inputs"]) == 9  # 2 train + 1 val geometries, 3 packings each
    assert manifest["dataset"] == {"id": "gns-rollouts", "fixture": False}


def test_train_refuses_a_changed_input_before_any_step(run_dir, tmp_path: Path) -> None:
    dataset, _, _ = run_dir
    payload = dataset.root / "payload" / "g001-s1000.parquet"
    original = payload.read_bytes()
    payload.write_bytes(original + b"\x00")
    try:
        with pytest.raises(InputStaleError, match="g001-s1000"):
            stages.s30_train(dataset, tmp_path / "again", {"noise_scales": [0.0], "epochs": 1, "batch_size": 1, "lr": 1e-3}, seed=0, device="cpu", env={})
    finally:
        payload.write_bytes(original)
    assert not (tmp_path / "again" / "checkpoint.pt").exists()


def test_a_cuda_stage_without_the_machine_lock_is_refused(run_dir, tmp_path: Path) -> None:
    from pitstudio.surrogate_runtime import LockNotHeldError

    dataset, _, _ = run_dir
    with pytest.raises(LockNotHeldError):
        stages.s30_train(dataset, tmp_path / "x", {"noise_scales": [0.0], "epochs": 1, "batch_size": 1, "lr": 1e-3}, seed=0, device="cuda", env={})


def test_evaluate_reports_the_held_out_geometry_complete_and_labelled(run_dir) -> None:
    dataset, out, _ = run_dir
    report = stages.s50_evaluate(dataset, out, device="cpu", env={})
    assert report["status"] == "complete"
    assert report["n_geometries"] == 1
    assert report["geometries"][0]["geometry_id"] == "g004"
    assert "calibrated synthetic" in report["label"]
    assert (out / "evaluation.published.json").is_file()  # not a fixture dataset


def test_export_writes_the_three_graphs_the_card_and_keeps_fp32_without_evidence_of_fp16(run_dir) -> None:
    dataset, out, _ = run_dir
    card = stages.s60_export(dataset, out, ort_provider="cpu", model_id="gns-smoke")
    assert card["parity"]["passed"] is True
    assert card["live_precision"] in ("fp16", "fp32")
    for key in ("fp32", "fp16", "scatter-bench"):
        assert (out / "models" / f"gns-smoke-{key}.onnx").is_file()
        assert (out / "models" / f"gns-smoke-{key}.io.json").is_file()
    assert len(card["fp16_rollout_deltas"]) == 1


def test_speed_report_names_measurements_and_marks_the_gpu_not_run_on_cpu(run_dir) -> None:
    dataset, out, _ = run_dir
    report = stages.s_speed(dataset, out, device="cpu", env={}, n_steps=3)
    assert report["surrogate"]["python_gpu"]["status"] == "not run"
    assert report["surrogate"]["python_cpu"]["steps_per_s"] > 0
