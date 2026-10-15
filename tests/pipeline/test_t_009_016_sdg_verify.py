# ruff: noqa: PT018, E501
"""T-009-016 (fix): the pipeline steps of the SDG job split by layout and verify the index (FR-009-16, FR-009-17, NFR-009-05).

Requirements: FR-009-02, FR-009-16, FR-009-17, NFR-009-05.

`sdg_job splits` assigns whole layouts to train / validation / test from the studio sampler's plan, and `sdg_job verify`
reads the index through the dataset loader and fails on a rejected frame, a short arm or a seed or layout shared between
splits. The index here is built by hand from small real PNG, NPY and JSON files.

Oracles: the partition of the scenarios (every seed in exactly one split, every layout in one split), the 95 % rule of
NFR-009-05 as integer arithmetic, and the loader's own digest and schema checks on tampered files.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pitstudio_pipeline.perception import sdg_job


def _entry(root: Path, rel: str, data: bytes) -> dict:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _png(path_bytes: np.ndarray) -> bytes:
    import io

    buf = io.BytesIO()
    Image.fromarray(path_bytes).save(buf, format="PNG")
    return buf.getvalue()


def _record(
    root: Path,
    i: int,
    *,
    arm: str = "structured",
    split: str = "train",
    seed: int | None = None,
    layout: str = "edge-a",
) -> dict:
    rid = f"pit-{arm[0]}-{i:05d}"
    base = f"frames/{rid}"
    rng = np.random.default_rng(i)
    size = {"width_px": 1280, "height_px": 720}
    image = _entry(root, f"{base}/rgb/000000.png", _png(rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8)))
    sem = _entry(root, f"{base}/semantic/000000.png", _png(np.zeros((720, 1280), dtype=np.uint8)))
    buffer = __import__("io").BytesIO()
    np.save(buffer, np.full((720, 1280), 10.0, dtype=np.float32))
    depth = _entry(root, f"{base}/depth/000000.npy", buffer.getvalue())
    coco = {
        "images": [{"id": 1, "file_name": "rgb/000000.png", "width": 1280, "height": 720}],
        "annotations": [],
        "categories": [
            {"id": k + 1, "name": n}
            for k, n in enumerate(["haul_truck", "shovel", "light_vehicle", "person", "boulder"])
        ],
    }
    coco_entry = _entry(root, f"{base}/coco_instances.json", json.dumps(coco).encode())
    state = _entry(root, f"frame_state/{rid}.json", b"{}")
    dr = (
        {
            "sun_utc": "2025-06-21T18:00:00Z",
            "sun_elevation_deg": 60.0,
            "sun_azimuth_deg": 180.0,
            "dust_extinction_per_km": 0.1,
            "wet_segments": [],
            "rock_texture_ids": ["tex-1"],
            "placements": [],
        }
        if arm == "structured"
        else {
            "texture_ids": ["tex-1"],
            "light_intensity_factor": 1.0,
            "colour_temperature_k": 5000.0,
            "sun_elevation_deg": 30.0,
            "sun_azimuth_deg": 10.0,
            "distractor_count": 0,
            "placements": [],
        }
    )
    return {
        "record_id": rid,
        "synthetic": True,
        "family": "pit",
        "arm": arm,
        "split": split,
        "scenario_seed": i if seed is None else seed,
        "layout_id": layout,
        "image": {**image, **size, "format": "png", "colour_space": "srgb"},
        "coco": coco_entry,
        "coco_image_id": 1,
        "semantic_mask": {**sem, **size, "format": "png"},
        "depth": {
            **depth,
            **size,
            "format": "npy",
            "dtype": "float32",
            "unit": "m",
            "quantity": "distance-to-image-plane",
        },
        "intrinsics": {"model": "pinhole", "fx_px": 1108.5, "fy_px": 1108.5, "cx_px": 640.0, "cy_px": 360.0},
        "frame_state": state,
        "instance_source": "replicator",
        "dr": dr,
        "licence": {"spdx": "CC-BY-4.0", "licence_class": "own"},
    }


def _write_index(root: Path, records: list[dict]) -> None:
    (root / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


@pytest.mark.req("FR-009-16")
def test_splits_put_every_seed_in_one_split_and_every_layout_in_one_split(tmp_path: Path) -> None:
    scenarios = [{"seed": 1000 + i, "layout_id": f"edge-{i % 10}"} for i in range(100)]
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"recipe_seed": 7, "scenarios": scenarios}), encoding="utf-8")
    out = tmp_path / "splits.json"
    assert sdg_job.main(["splits", "--plan", str(plan), "--out", str(out)]) == 0
    splits = json.loads(out.read_text(encoding="utf-8"))
    seeds = [s["seed"] for s in scenarios]
    assert sorted(seed for members in splits.values() for seed in members) == sorted(
        seeds
    )  # a partition: every seed once
    layout_of = {s["seed"]: s["layout_id"] for s in scenarios}
    where: dict[str, str] = {}
    for name, members in splits.items():
        for seed in members:
            assert where.setdefault(layout_of[seed], name) == name  # a layout never spans two splits
    assert len(splits["train"]) == 80 and len(splits["validation"]) == 10 and len(splits["test"]) == 10


@pytest.mark.req("NFR-009-05")
def test_a_clean_index_with_enough_frames_verifies(tmp_path: Path) -> None:
    records = [_record(tmp_path, i) for i in range(4)] + [
        _record(tmp_path, i, arm="unstructured", seed=i) for i in range(4)
    ]
    _write_index(tmp_path, records)
    report = sdg_job.verify(tmp_path, {"structured": 4, "unstructured": 4}, phash=False)
    assert report["ok"] and report["accepted_by_arm"] == {"structured": 4, "unstructured": 4}


@pytest.mark.req("FR-009-02")
def test_a_tampered_frame_is_rejected_by_the_loader_checks(tmp_path: Path) -> None:
    records = [_record(tmp_path, i) for i in range(4)]
    _write_index(tmp_path, records)
    (tmp_path / "frames" / "pit-s-00002" / "depth" / "000000.npy").write_bytes(b"tampered")
    report = sdg_job.verify(tmp_path, {"structured": 4}, phash=False)
    assert not report["ok"] and report["frames_rejected"] == 1 and report["accepted_by_arm"] == {"structured": 3}


@pytest.mark.req("NFR-009-05")
def test_an_arm_below_ninety_five_percent_of_its_request_fails(tmp_path: Path) -> None:
    _write_index(tmp_path, [_record(tmp_path, i) for i in range(19)])
    assert sdg_job.verify(tmp_path, {"structured": 20}, phash=False)["ok"]  # 19 of 20 is exactly 95 %
    assert not sdg_job.verify(tmp_path, {"structured": 21}, phash=False)["ok"]


@pytest.mark.req("FR-009-17")
def test_a_seed_or_layout_shared_between_splits_fails(tmp_path: Path) -> None:
    records = [
        _record(tmp_path, 0, split="train", seed=5, layout="edge-a"),
        _record(tmp_path, 1, split="test", seed=5, layout="edge-b"),
    ]
    _write_index(tmp_path, records)
    report = sdg_job.verify(tmp_path, {"structured": 2}, phash=False)
    assert not report["ok"] and report["seed_or_layout_leaks"] == 1
    records = [
        _record(tmp_path, 0, split="train", seed=5, layout="edge-a"),
        _record(tmp_path, 1, split="test", seed=6, layout="edge-a"),
    ]
    _write_index(tmp_path, records)
    assert sdg_job.verify(tmp_path, {"structured": 2}, phash=False)["seed_or_layout_leaks"] == 1


@pytest.mark.req("FR-009-17")
def test_the_perceptual_hash_leaks_are_counted_and_do_not_fail_the_job(tmp_path: Path) -> None:
    records = [
        _record(tmp_path, 0, split="train", layout="edge-a"),
        _record(tmp_path, 1, split="test", layout="edge-b"),
    ]
    twin = (tmp_path / records[0]["image"]["path"]).read_bytes()
    records[1]["image"] = {
        **records[1]["image"],
        **_entry(tmp_path, records[1]["image"]["path"], twin),
    }  # the same picture
    _write_index(tmp_path, records)
    report = sdg_job.verify(tmp_path, {"structured": 2}, phash=True)
    assert report["phash_leak_pairs"] == 1 and report["ok"]
