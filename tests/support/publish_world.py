# ruff: noqa: E501
"""Test support for `studio publish` (spec 002, FR-002-48..50) and `studio gc`: hand-built runs in a store.

A fake run can never be published (FR-002-49), so publish tests need runs "as an NVML run would have left them":
`build_run` writes a run folder (manifest.json, events.jsonl, telemetry.jsonl, per-execution result.json) and the
objects it references into the store, in the layout of plan.md D3, from documents valid against the manifest schema.
Nothing here calls the code under test.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import runner_world as rw
import yaml

LOCAL_ONLY = "measured locally, not published (licence)"
GIT_SHA_PLACEHOLDER = "c" * 40
RUN_ID = "20261007T120000Z-pub-case"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sources_doc(pinned: bool = True) -> dict[str, Any]:
    def src(id_: str, spdx: str, klass: str, attribution: str | None) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": id_, "kind": "real", "title": f"Example data {id_}", "landing_url": f"https://example.org/{id_}", "access": "direct",
            "files": [{"url": f"https://example.org/{id_}/a.tif", "sha256": sha(id_.encode()) if pinned else None, "bytes": 100, "kind": "raster"}],
            "spdx": spdx, "licence_url": f"https://example.org/{id_}/licence", "licence_class": klass, "redistribution": "redistributable",
            "citation": f"Example {id_} (2026).", "card": f"data/cards/{id_}.md", "account": {"needed": False},
        }  # fmt: skip
        if attribution:
            d["attribution"] = attribution
        return d

    return {
        "sources": [
            src("src-cc0", "CC0-1.0", "open-no-attribution", None),
            src("src-by", "CC-BY-4.0", "attribution", "Data (c) Example Org, CC BY 4.0."),
            src("src-by2", "CC-BY-4.0", "attribution", "Second dataset (c) Another Org, CC BY 4.0."),
            src("src-sa", "CC-BY-SA-4.0", "share-alike", "Share-alike data (c) Other Org, CC BY-SA 4.0."),
        ]
    }


def telemetry_summary(n: int = 40, hz: float = 2) -> dict[str, Any]:
    return {
        "sample_hz": hz, "n_samples": n, "gpu_busy_pct": {"mean": 61.2, "p50": 63.0, "p95": 88.5}, "mem_used_peak_bytes": 2147483648,
        "power_w": {"mean": 71.4, "p95": 96.0, "max": 103.2}, "power_at_limit_frac": 0.0, "energy_j": 1500.5,
        "sm_clock_mhz": {"mean": 1785.0, "p5": 1410.0}, "temp_c_max": 74.0,
        "clocks_event_frac": {"sw_power_cap": 0.0, "sw_thermal": 0.0, "hw_thermal": 0.0, "hw_slowdown": 0.0, "power_brake": 0.0, "idle": 0.02},
        "pcie_replays_delta": 0, "unavailable": {},
    }  # fmt: skip


def lane_measurements(**over: Any) -> dict[str, Any]:
    d = {
        "web_drivable": True,
        "max_asset_bytes": 5_242_880,
        "interaction_ms": None,
        "run_ms_t2": None,
        "trace_bytes": None,
        "measured": {"tier": "T2", "date": "2026-10-07", "browser": "Chromium 141"},
    }
    d.update(over)
    return d


def encoder_record() -> dict[str, Any]:
    return {
        "codec": "av1", "profile": "main", "pix_fmt": "yuv420p", "width": 1920, "height": 1080, "fps": 30, "frames": 600, "duration_s": 20.0, "bitrate_kbps": 2097.152,
        "vmaf": {"mean": 93.1, "p5": 88.4, "model": "vmaf_v0.6.1"}, "source_frames_sha256": "1" * 64,
        "encoder": {"ffmpeg_version": "n7.1", "build_sha256": "2" * 64, "nvenc_api": "13.0", "args": ["-c:v", "av1_nvenc", "-cq", "30"]}, "encode_fps": 240.0,
    }  # fmt: skip


@dataclass
class Built:
    run_id: str
    run_dir: Path
    manifest: dict[str, Any]
    expected_files: dict[str, bytes] = field(default_factory=dict)  # output name -> bytes
    git_sha: str = ""


def build_run(
    world: rw.World,
    *,
    run_id: str = RUN_ID,
    launcher: str = "uv",
    backend: str = "nvml",
    git_dirty: bool = False,
    finished: bool = True,
    clip_bytes: int = 5_242_880,
    encode_status: str = "succeeded",
    clip_inputs: list[str] | None = None,
    onnx: bool = False,
    notes: list[str] | None = None,
    pinned_sources: bool = True,
    n_samples: int = 40,
    sensor_status: str = "succeeded",
) -> Built:
    """Write recipe, sources, store objects, run folder; commit the repository; return what was built."""
    clip_inputs = clip_inputs or []
    recipe_doc = rw.recipe(
        "pub-case",
        [
            rw.stage(
                "st50_physics",
                gpu="exclusive",
                vram=2.0,
                outputs=[{"path": "physics/observables.json", "schema": "json", "publish": False}],
                params={"files": ["physics/observables.json"]},
            ),
            rw.stage(
                "st56_encode",
                gpu="nvenc",
                tool="nvenc-ffmpeg",
                inputs=[rw.up("st50_physics", "physics/observables.json")],
                outputs=[
                    {"path": "media/clip.mp4", "schema": "file", "publish": True},
                    {"path": "tables/summary.json", "schema": "json", "publish": True},
                ],
                params={"files": ["media/clip.mp4", "tables/summary.json"]},
            ),
            rw.stage(
                "st53_sensors",
                gpu="exclusive",
                vram=2.0,
                outputs=[{"path": "sensors/s1.bin", "schema": "file", "publish": False}],
                params={"files": ["sensors/s1.bin"]},
            ),
        ],
        seed=20261007,
        case="A2",
    )
    world.write_recipe(recipe_doc)
    (world.repo / "data").mkdir(exist_ok=True)
    (world.repo / "data" / "sources.yaml").write_text(
        yaml.safe_dump(sources_doc(pinned_sources), sort_keys=False), encoding="utf-8", newline="\n"
    )
    head = world.commit()
    recipe_sha = sha(world.recipes["pub-case"].read_bytes())

    outputs: dict[str, bytes] = {
        "physics/observables.json": b'{"repose_deg": 34.5}\n',
        "media/clip.mp4": b"\x00\x00\x00\x18ftypmp42" + b"v" * (clip_bytes - 12),
        "tables/summary.json": b'{"rows": 3}\n',
        "sensors/s1.bin": b"sensor bytes " * 100,
    }
    assert len(outputs["media/clip.mp4"]) == clip_bytes
    cas = world.store / "cas" / "sha256"
    recs: dict[str, dict[str, Any]] = {}
    for name, data in outputs.items():
        d = sha(data)
        p = cas / d[:2] / d
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        recs[name] = {"name": name, "sha256": d, "bytes": len(data)}

    def stage_rec(
        sid: str,
        tool: str,
        env: str,
        perf: str,
        outs: list[str],
        *,
        status: str = "succeeded",
        inputs: list[dict[str, Any]] | None = None,
        key_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "key": {"id": sid, **(key_extra or {})}, "tool": tool,
            "env": {"name": env, "python": "3.14.4", "lock_sha256": "3" * 64, "versions": {"warp-lang": "1.17.0"}},
            "cache_key": sha(sid.encode()), "cache": "miss", "status": status, "exit_code": 0 if status == "succeeded" else 1,
            "error_class": None if status == "succeeded" else "unknown",
            "attempts": [{"n": 1, "error_class": None if status == "succeeded" else "unknown", "duration_s": 42.5}],
            "params": {"mode": "ok"}, "seed": 123456789, "determinism": {"class": "bitwise", "rerun_check": "pending"}, "performance": perf,
            "wall_s": 42.5, "telemetry": telemetry_summary(n_samples), "throughput": {"value": 240.0, "unit": "frames/s"}, "thermal_flag": False,
            "inputs": inputs or [], "outputs": [recs[o] for o in outs] if status == "succeeded" else [],
        }  # fmt: skip
        if status != "succeeded":
            rec["log_tail"] = "stage failed: see <repo>/studio\n"
        return rec

    manifest: dict[str, Any] = {
        "kind": "run", "schema_version": "1.0", "run_id": run_id,
        "recipe": {"id": "pub-case", "path": "cases/pub-case.yaml", "sha256": recipe_sha},
        "git_sha": head, "git_dirty": git_dirty, "runner_version": "0.1.0", "created": "2026-10-07T12:00:00Z", "profile": "test-profile", "seed": 20261007,
        "published": False, "launcher": launcher,
        "gpu": {"backend": backend, "index": 0, "name": "NVIDIA RTX 5000 Ada Generation Laptop GPU" if backend == "nvml" else "fake-gpu", "driver": "582.78", "vram_total_bytes": 17171480576, "power_limit_enforced_w": 175.0},
        "stages": [
            stage_rec("st50_physics", "warp", "studio", "public", ["physics/observables.json"], inputs=[{"id": "src-cc0", "sha256": sha(b"src-cc0"), "kind": "source"}]),
            stage_rec(
                "st56_encode", "nvenc-ffmpeg", "studio", "public", ["media/clip.mp4", "tables/summary.json"], status=encode_status,
                inputs=[{"id": i, "sha256": sha(i.encode()), "kind": "source"} for i in clip_inputs],
            ),
            stage_rec("st53_sensors", "ovrtx", "rtx", "local-only", ["sensors/s1.bin"], status=sensor_status),
        ],
        "artefacts": [],
    }  # fmt: skip
    if notes:
        manifest["notes"] = notes
    run_dir = world.store / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    events = [{"seq": 1, "t": "2026-10-07T12:00:00Z", "run_id": run_id, "type": "run-started"}]
    if finished:
        events.append({"seq": 2, "t": "2026-10-07T12:05:00Z", "run_id": run_id, "type": "run-finished"})
    (run_dir / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    lines = [
        {
            "t_s": i / 2,
            "run_id": run_id,
            "stage": {"id": sid},
            "shard": 0,
            "gpu": 0,
            "mem_used_bytes": 1_000_000_000 + i,
            "mem_total_bytes": 17171480576,
            "util_pct": float(i % 100),
            "power_w": 50.0 + i % 40,
            "power_limit_w": 175.0,
            "temp_c": 60.0 + i % 15,
            "sm_clock_mhz": 1700.0 + i,
            "clocks_event_mask": 0,
            "energy_mj": i * 70_000,
            "nvenc_util_pct": None,
            "pcie_replays": 0,
        }
        for sid in ("st50_physics", "st53_sensors")
        for i in range(n_samples)
    ]
    (run_dir / "telemetry.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    # the facts the stages reported for outputs offered for publication (result.json `artefact`, job.schema.json)
    facts = {
        "media/clip.mp4": {
            "kind": "video",
            "media_type": "video/mp4",
            "budget_class": "videos",
            "cases": ["A2"],
            "lane_measurements": lane_measurements(max_asset_bytes=clip_bytes),
            "encoder": encoder_record(),
        },
        "tables/summary.json": {
            "kind": "table",
            "media_type": "application/json",
            "budget_class": "own-code",
            "cases": ["A2"],
        },
    }
    if onnx:
        facts["media/clip.mp4"] = {
            "kind": "onnx",
            "media_type": "application/octet-stream",
            "budget_class": "onnx",
            "cases": ["A2"],
            "lane_measurements": lane_measurements(max_asset_bytes=clip_bytes, interaction_ms=3.2),
        }
    tmp = run_dir / "tmp" / "st56_encode" / "0"
    tmp.mkdir(parents=True)
    result = {
        "schema_version": "1.0",
        "status": "succeeded",
        "error_class": None,
        "checkpoint": False,
        "outputs": [{"path": n, "artefact": f} for n, f in facts.items()],
    }
    (tmp / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return Built(
        run_id=run_id,
        run_dir=run_dir,
        manifest=manifest,
        expected_files={k: outputs[k] for k in ("media/clip.mp4", "tables/summary.json")},
        git_sha=head,
    )
