# ruff: noqa: PT018
"""`studio import-run`: a finished GPU-queue job recorded as a run with honest provenance (decision of the main session,
2026-11-22, delegation brief publish-cases-2026-11-22). Oracles: the run manifest contract, the digests of the files
the test wrote, the label the brief fixes. The publish path of spec 002 is then applied to the imported run.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitstudio.runner import cli
from pitstudio.runner.recipe import first_errors

ROOT = Path(__file__).resolve().parents[2]
LABEL = "produced by the GPU queue, outside the runner"
JOB = "33-demo-job"
SCRIPT = "#!/bin/bash\necho job\n"
LOG = "[job] done: GPU hours 0.374 of 2.0\n"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git(repo: Path, *a: str) -> None:
    r = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr


class World:
    def __init__(self, tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.repo, self.store, self.queue, self.src = tmp / "repo", tmp / "store", tmp / "queue", tmp / "src"
        for d in (
            self.repo / "studio" / "recipes" / "cases",
            self.repo / "web" / "public" / "assets",
            self.queue / "done",
            self.src / "sub",
        ):
            d.mkdir(parents=True)
        shutil.copy(ROOT / "studio" / "tools.yaml", self.repo / "studio" / "tools.yaml")
        (self.repo / "studio" / "recipes" / "cases" / "c1.yaml").write_text("id: c1-slope\n", encoding="utf-8")
        index = {
            "kind": "web-index",
            "schema_version": "1.0",
            "generated": "2026-11-22",
            "git_sha": "a" * 40,
            "runs": [],
            "artefacts": [],
        }
        (self.repo / "web" / "public" / "assets" / "manifest.json").write_text(json.dumps(index), encoding="utf-8")
        git(self.repo, "init", "-q")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")
        self.result = {"metric": 0.5, "budget": {"total_gpu_hours": 0.374}}
        self.model = b"onnx-bytes" * 100
        (self.src / "result.json").write_text(json.dumps(self.result), encoding="utf-8")
        (self.src / "sub" / "model.onnx").write_bytes(self.model)
        (self.src / "sub" / "private.json").write_text('{"latency_ms": 7.5}', encoding="utf-8")
        (self.queue / "done" / f"{JOB}.sh").write_text(SCRIPT, encoding="utf-8", newline="\n")
        log = self.queue / f"{JOB}.log"
        log.write_text(LOG, encoding="utf-8", newline="\n")
        os.utime(log, (1_795_000_000, 1_795_000_000))  # 2026-11-18T11:06:40Z
        (self.queue / "queue.log").write_text(
            f"[queue 09:00:00] start {JOB}\n[queue 10:26:40] done {JOB}\n", encoding="utf-8", newline="\n"
        )
        monkeypatch.setenv("PITSTUDIO_REPO", str(self.repo))
        monkeypatch.setenv("PITSTUDIO_STORE", str(self.store))
        monkeypatch.setenv("PITSTUDIO_GPU_QUEUE", str(self.queue))
        self.tmp = tmp

    def doc(self) -> dict:
        common = {"licence_class": "own", "spdx": "Apache-2.0"}
        return {
            "job": JOB,
            "case": "C1",
            "recipe": "cases/c1.yaml",
            "slug": "c1-demo",
            "seed": 7,
            "label": "calibrated synthetic, not validated against real data",
            "gpu_hours": {"file": "result.json", "path": ["budget", "total_gpu_hours"]},
            "stages": [
                {
                    "id": "s30_train",
                    "tool": "pytorch",
                    "determinism": "none",
                    "outputs": [
                        {
                            "name": "result.json",
                            "from": "result.json",
                            "kind": "table",
                            "budget_class": "studio-showcase",
                            "publish": True,
                            "required_fields": ["metric"],
                            **common,
                        },
                        {
                            "name": "model.onnx",
                            "from": "sub/model.onnx",
                            "kind": "onnx",
                            "budget_class": "onnx",
                            "publish": False,
                            **common,
                        },
                        {
                            "name": "trt-latency.json",
                            "from": "sub/private.json",
                            "kind": "table",
                            "budget_class": "studio-showcase",
                            "publish": True,
                            "local_only": True,
                            **common,
                        },
                    ],
                }
            ],
        }

    def run(self, spec: dict | None = None) -> tuple[int, str]:
        p = self.tmp / "spec.json"
        p.write_text(json.dumps(spec or self.doc()), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["import-run", JOB, "--from", str(self.src), "--spec", str(p)])
        return code, err.getvalue()

    def runs(self) -> list[Path]:
        return sorted((self.store / "runs").glob("*")) if (self.store / "runs").is_dir() else []


def short(p: Path) -> Path:
    """The 8.3 form of a Windows path: the store root may not exceed 64 characters and a scratch folder can."""
    if sys.platform != "win32":
        return p
    import ctypes

    buf = ctypes.create_unicode_buffer(512)
    return Path(buf.value) if ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, 512) else p


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    # a plain folder, not tmp_path or mkdtemp: git cannot enter the owner-only folders those make on Windows
    tmp = Path(tempfile.gettempdir()) / f"ir-{uuid.uuid4().hex[:6]}"
    tmp.mkdir()
    tmp = short(tmp)
    try:
        for k, v in (("GIT_CONFIG_COUNT", "1"), ("GIT_CONFIG_KEY_0", "safe.directory"), ("GIT_CONFIG_VALUE_0", "*")):
            monkeypatch.setenv(k, v)  # the folder may be owned by the elevated account that made it
        yield World(tmp, monkeypatch)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def manifest_of(w: World) -> dict:
    (run,) = w.runs()
    return json.loads((run / "manifest.json").read_text(encoding="utf-8"))


def test_import_run_complete_job_records_a_valid_run_with_provenance(world: World) -> None:
    code, err = world.run()
    assert code == 0, err
    m = manifest_of(world)
    assert first_errors("manifest", m, "#/$defs/run", n=3) == []
    assert m["run_id"].startswith("20261118T110640Z-c1-demo")
    assert m["published"] is False and m["git_dirty"] is False
    notes = " | ".join(m["notes"])
    assert LABEL in notes
    assert JOB in notes and "script sha256 " + sha(SCRIPT.encode()) in notes
    assert "log sha256 " + sha(LOG.encode()) in notes
    assert "GPU-hours 0.374" in notes and "partial" not in notes
    (stage,) = m["stages"]
    assert stage["key"] == {"id": "s30_train"} and stage["status"] == "succeeded" and stage["tool"] == "pytorch"
    assert stage["attempts"][0]["duration_s"] == pytest.approx(5200)
    names = {o["name"]: o for o in stage["outputs"]}
    assert names["result.json"]["sha256"] == sha(json.dumps(world.result).encode())
    assert names["model.onnx"]["sha256"] == sha(world.model)
    events = [json.loads(x) for x in (world.runs()[0] / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["type"] for e in events] == ["run-started", "run-finished"]
    obj = world.store / "cas" / "sha256" / names["model.onnx"]["sha256"][:2] / names["model.onnx"]["sha256"]
    assert obj.read_bytes() == world.model


def test_import_run_missing_field_and_missing_script_label_the_run_partial(world: World) -> None:
    (world.src / "result.json").write_text(json.dumps({"budget": {"total_gpu_hours": 0.4}}), encoding="utf-8")
    (world.queue / "done" / f"{JOB}.sh").unlink()
    code, err = world.run()
    assert code == 0, err
    m = manifest_of(world)
    assert first_errors("manifest", m, "#/$defs/run", n=3) == []
    notes = " | ".join(m["notes"])
    assert "partial" in notes
    assert "result.json lacks field metric: marked missing" in notes
    assert "script missing" in notes
    assert json.loads((world.runs()[0] / "import.json").read_text(encoding="utf-8"))["partial"] is True


def test_import_run_digest_mismatch_is_refused_and_writes_nothing(world: World) -> None:
    spec = world.doc()
    spec["stages"][0]["outputs"][1]["sha256"] = "0" * 64
    code, err = world.run(spec)
    assert code == 2 and "digest" in err and "model.onnx" in err
    assert world.runs() == [] and not (world.store / "cas").exists()


def test_import_run_unknown_job_or_missing_output_is_a_usage_error(world: World) -> None:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["import-run", "99-no-such-job", "--from", str(world.src)])
    assert code == 2 and "99-no-such-job" in err.getvalue()
    (world.src / "sub" / "model.onnx").unlink()
    code, err = world.run()
    assert code == 2 and "model.onnx" in err


def test_import_run_publish_keeps_local_only_outputs_out_and_digests_match(world: World) -> None:
    from pitstudio.runner import publish

    assert world.run()[0] == 0
    run_id = world.runs()[0].name
    publish.publish(world.store, world.repo, run_id, None)
    repo = world.repo
    pub = json.loads((repo / "web/public/assets/runs" / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert pub["published"] is True
    assert [a["path"].rsplit("/", 1)[-1] for a in pub["artefacts"]] == ["result.json"]
    art = pub["artefacts"][0]
    assert art["producer"] == {"tool": "pytorch", "stage": {"id": "s30_train"}} and art["cases"] == ["C1"]
    assert sha((repo / "web" / "public" / art["path"]).read_bytes()) == art["sha256"]
    assert sorted(p.name for p in (repo / "web" / "public" / "assets" / run_id).iterdir()) == ["result.json"]
    assert LABEL in " ".join(pub["notes"])
    idx = json.loads((repo / "web/public/assets/manifest.json").read_text(encoding="utf-8"))
    assert [r["run_id"] for r in idx["runs"]] == [run_id]


def test_import_run_publish_refuses_a_machine_path_in_a_published_file(world: World) -> None:
    from pitstudio.runner import publish
    from pitstudio.runner.recipe import Usage

    (world.src / "result.json").write_text(json.dumps({"metric": 1, "p": "C:\\Users\\x\\f"}), encoding="utf-8")
    assert world.run()[0] == 0
    run_id = world.runs()[0].name
    with pytest.raises(Usage, match="absolute path"):
        publish.publish(world.store, world.repo, run_id, None)
    assert not (world.repo / "web" / "public" / "assets" / run_id).exists()


def test_import_run_is_listed_in_usage(world: World) -> None:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main([])
    assert code == 2 and "import-run" in err.getvalue()


def test_import_run_publish_starts_the_web_index_when_the_repository_has_none(world: World) -> None:
    from pitstudio.runner import publish

    (world.repo / "web" / "public" / "assets" / "manifest.json").unlink()
    git(world.repo, "add", "-A")
    git(world.repo, "commit", "-q", "-m", "no index")
    assert world.run()[0] == 0
    run_id = world.runs()[0].name
    publish.publish(world.store, world.repo, run_id, None)
    idx = json.loads((world.repo / "web/public/assets/manifest.json").read_text(encoding="utf-8"))
    assert idx["kind"] == "web-index"
    assert [r["run_id"] for r in idx["runs"]] == [run_id]


def test_import_run_publish_writes_the_results_bundle_of_the_import_spec(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pitstudio.runner import import_summaries, publish

    def bundle(src: Path, run_id: str) -> dict:
        return {
            "schema_version": "1.0",
            "kind": "comparison",
            "id": "demo-bundle",
            "tab": "learned-vs-classical",
            "title": {"en": "Demo", "es": "Demo"},
            "cases": ["C1"],
            "run_ids": [run_id],
            "criteria": [],
            "rows": [
                {
                    "kind": "estimate",
                    "metric": {
                        "id": "m",
                        "name": {"en": "M", "es": "M"},
                        "unit": "h",
                        "orientation": "lower-is-better",
                    },
                    "system": "demo",
                    "n": 3,
                    "value": 1.5,
                }
            ],
        }

    monkeypatch.setitem(import_summaries.BUILDERS, "demo-bundle", bundle)
    spec = world.doc()
    spec["bundles"] = [{"id": "demo-bundle", "derive": "demo-bundle"}]
    assert world.run(spec)[0] == 0
    run_id = world.runs()[0].name
    publish.publish(world.store, world.repo, run_id, None)
    doc = json.loads((world.repo / "web" / "public" / "results" / "demo-bundle.json").read_text(encoding="utf-8"))
    assert doc["run_ids"] == [run_id]


# --- kind "render": the RTX flyover of publish-render-2026-11-22 (ovrtx frames, NVENC pair, WebP poster and stills) ---

RENDER_JOB = "40-demo-render"
RENDER_LABEL = "Rendered with NVIDIA Omniverse RTX (ovrtx)"
PAIR = ("av1", "h264")
FRAME_BYTES = [bytes([i]) * 64 for i in range(3)]
LOCAL_ONLY_KEYS = {"wall_s", "throughput", "gpu_hours", "render_ms", "frame_ms"}


def frames_digest(frames: list[bytes]) -> str:
    return sha(b"".join(bytes.fromhex(sha(f)) for f in frames))


def render_files(w: World, *, report_digest: str | None = None, label: str | None = RENDER_LABEL) -> None:
    """The --from folder of the render job: ovrtx manifest, encode report, the pair, the poster and the stills."""
    manifest = {
        "kind": "render",
        "schema_version": "1.0",
        "run_id": "20261122T060455Z-demo-flyover",
        "producer": {"tool": "ovrtx", "version": "0.5.0.377615", "runtime": "ovrtx"},
        "scene": {"id": "a1-bingham", "sha256": "1" * 64},
        "resolution": [1920, 1080],
        "frames": {"stills": 6, "flyover": 3, "playback_fps": 30, "duration_s": 0.1},
        "gpu": {"name": "NVIDIA RTX 5000 Ada Generation Laptop GPU", "driver": "595.95"},
        "performance": "local-only",
        "artefacts": [
            {"id": f"frame-{i:05d}", "path": f"flyover/frame_{i:05d}.png", "sha256": sha(b), "kind": "image"}
            for i, b in enumerate(FRAME_BYTES)
        ],
    }
    if label is not None:
        manifest["label"] = label
    (w.src / "render.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    variants = {}
    for codec in PAIR:
        data = f"mp4-{codec}".encode() * 50
        (w.src / f"demo-flyover.{codec}.mp4").write_bytes(data)
        variants[codec] = {
            "file": f"demo-flyover.{codec}.mp4",
            "sha256": sha(data),
            "record": {
                "codec": codec,
                "profile": "main" if codec == "av1" else "high",
                "pix_fmt": "yuv420p",
                "width": 1920 if codec == "av1" else 1280,
                "height": 1080 if codec == "av1" else 720,
                "fps": 30,
                "frames": 3,
                "duration_s": 0.1,
                "bitrate_kbps": 1000.0,
                "vmaf": {"mean": 94.5, "p5": 90.1, "model": "vmaf_v0.6.1"},
                "source_frames_sha256": report_digest or frames_digest(FRAME_BYTES),
                "encoder": {
                    "ffmpeg_version": "n8.1.3",
                    "build_sha256": "2" * 64,
                    "nvenc_api": "13.0",
                    "args": ["-i", "C:\\Users\\someone\\_Temp\\frames\\frame_%05d.png", "-c:v", f"{codec}_nvenc"],
                },
                "encode_fps": 311.5,
            },
        }
    report = {"kind": "encode-report", "clips": [{"clip": "demo-flyover", "frames": 3, "variants": variants}]}
    (w.src / "encode-report.json").write_text(json.dumps(report), encoding="utf-8")
    for name in ("demo-flyover.webp", "still-0s.webp", "still-5s.webp"):
        (w.src / name).write_bytes(b"RIFFwebp" + name.encode())


def render_spec() -> dict:
    own = {"licence_class": "own", "spdx": "CC-BY-4.0"}
    video = {"kind": "video", "media_type": "video/mp4", "budget_class": "videos", "publish": True, **own}
    image = {"kind": "image", "media_type": "image/webp", "publish": True, **own}
    return {
        "job": RENDER_JOB,
        "kind": "render",
        "case": "A1",
        "all_cases": True,
        "recipe": "render/demo.yaml",
        "slug": "demo-flyover",
        "seed": 3,
        "label": "real USGS 3DEP terrain with a procedural fleet, rendered with ovrtx",
        "render": {
            "manifest": "render.manifest.json",
            "report": "encode-report.json",
            "built_with": ["openusd", "ovrtx", "nvenc-ffmpeg"],
            "title": {"en": "Flyover of the demo pit", "es": "Sobrevuelo del pit de prueba"},
        },
        "stages": [
            {
                "id": "st52_rtx_render",
                "tool": "ovrtx",
                "outputs": [
                    {
                        "name": "render.manifest.json",
                        "from": "render.manifest.json",
                        "kind": "table",
                        "budget_class": "studio-showcase",
                        "publish": False,
                        **own,
                    }
                ],
            },
            {
                "id": "st56_encode",
                "tool": "nvenc-ffmpeg",
                "outputs": [
                    {
                        "name": "demo-flyover.av1.mp4",
                        "from": "demo-flyover.av1.mp4",
                        "id": "demo-flyover-av1",
                        "encoder_from": {"codec": "av1"},
                        **video,
                    },
                    {
                        "name": "demo-flyover.h264.mp4",
                        "from": "demo-flyover.h264.mp4",
                        "id": "demo-flyover-h264",
                        "encoder_from": {"codec": "h264"},
                        **video,
                    },
                    {
                        "name": "demo-flyover.webp",
                        "from": "demo-flyover.webp",
                        "id": "demo-flyover-poster",
                        "budget_class": "videos",
                        "role": "poster",
                        **image,
                    },
                    {
                        "name": "flyover-0s.webp",
                        "from": "still-0s.webp",
                        "id": "demo-flyover-still-0s",
                        "budget_class": "studio-showcase",
                        "role": "still",
                        "t_s": 0,
                        **image,
                    },
                    {
                        "name": "flyover-5s.webp",
                        "from": "still-5s.webp",
                        "id": "demo-flyover-still-5s",
                        "budget_class": "studio-showcase",
                        "role": "still",
                        "t_s": 5,
                        **image,
                    },
                    {
                        "name": "render.json",
                        "derive": "render-summary",
                        "id": "demo-flyover-render",
                        "kind": "table",
                        "media_type": "application/json",
                        "budget_class": "studio-showcase",
                        "publish": True,
                        **own,
                    },
                ],
            },
        ],
    }


def render_world(w: World, **kw: object) -> dict:
    (w.repo / "studio" / "recipes" / "render").mkdir(parents=True)
    (w.repo / "studio" / "recipes" / "render" / "demo.yaml").write_text("id: demo-flyover\n", encoding="utf-8")
    git(w.repo, "add", ".")
    git(w.repo, "commit", "-q", "-m", "recipe")
    (w.queue / "done" / f"{RENDER_JOB}.sh").write_text(SCRIPT, encoding="utf-8", newline="\n")
    log = w.queue / f"{RENDER_JOB}.log"
    log.write_text("rendered 3 images\n[job] done\n", encoding="utf-8", newline="\n")
    os.utime(log, (1_795_000_000, 1_795_000_000))
    (w.queue / "queue.log").write_text(
        f"[queue 03:04:50] start {RENDER_JOB}\n[queue 03:35:30] done {RENDER_JOB}\n", encoding="utf-8", newline="\n"
    )
    render_files(w, **kw)
    return render_spec()


def run_job(w: World, job: str, spec: dict) -> tuple[int, str]:
    p = w.tmp / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["import-run", job, "--from", str(w.src), "--spec", str(p)])
    return code, err.getvalue()


def published_render(w: World) -> tuple[str, dict, Path]:
    from pitstudio.runner import publish

    assert run_job(w, RENDER_JOB, render_spec())[0] == 0
    run_id = w.runs()[0].name
    publish.publish(w.store, w.repo, run_id, None)
    web = w.repo / "web" / "public"
    return run_id, json.loads((web / "assets" / "runs" / run_id / "manifest.json").read_text(encoding="utf-8")), web


def test_import_run_render_records_a_valid_run_with_the_render_label_and_no_timing(world: World) -> None:
    spec = render_world(world)
    code, err = run_job(world, RENDER_JOB, spec)
    assert code == 0, err
    m = manifest_of(world)
    assert first_errors("manifest", m, "#/$defs/run", n=3) == []
    assert [s["tool"] for s in m["stages"]] == ["ovrtx", "nvenc-ffmpeg"]
    notes = " | ".join(m["notes"])
    assert RENDER_LABEL in notes and LABEL in notes and "a1-bingham" in notes
    assert "started" not in notes and "ended" not in notes and "GPU-hours" not in notes
    assert all(s["wall_s"] == 0.0 and s["attempts"][0]["duration_s"] == 0.0 for s in m["stages"])
    imp = json.loads((world.runs()[0] / "import.json").read_text(encoding="utf-8"))
    assert imp["all_cases"] is True and imp["partial"] is False


def test_import_run_render_publishes_the_pair_poster_stills_and_summary_with_matching_digests(world: World) -> None:
    render_world(world)
    run_id, pub, web = published_render(world)
    by = {a["id"]: a for a in pub["artefacts"]}
    assert sorted(by) == [
        "demo-flyover-av1",
        "demo-flyover-h264",
        "demo-flyover-poster",
        "demo-flyover-render",
        "demo-flyover-still-0s",
        "demo-flyover-still-5s",
    ]
    for a in by.values():
        assert sha((web / a["path"]).read_bytes()) == a["sha256"] and "cases" not in a
        assert a["asset_host"] == "git" and a["path"].startswith(f"assets/{run_id}/")
    for codec in PAIR:
        a = by[f"demo-flyover-{codec}"]
        assert a["kind"] == "video" and a["lane"] == "replay" and a["encoder"]["codec"] == codec
        assert a["lane_measurements"]["web_drivable"] is False and a["media_type"] == "video/mp4"
        assert a["encoder"]["vmaf"]["mean"] == 94.5
    assert by["demo-flyover-poster"]["lane"] == "static" and by["demo-flyover-poster"]["kind"] == "image"
    summary = json.loads((web / by["demo-flyover-render"]["path"]).read_text(encoding="utf-8"))
    assert summary["run_id"] == run_id and summary["label"] == RENDER_LABEL
    assert summary["producer"] == {"tool": "ovrtx", "version": "0.5.0.377615"}
    assert summary["built_with"] == ["openusd", "ovrtx", "nvenc-ffmpeg"]
    assert summary["video"] == {
        "id": "demo-flyover",
        "files": ["demo-flyover-av1", "demo-flyover-h264"],
        "poster": "demo-flyover-poster",
    }
    assert [(s["artefact"], s["t_s"]) for s in summary["stills"]] == [
        ("demo-flyover-still-0s", 0),
        ("demo-flyover-still-5s", 5),
    ]
    assert summary["title"] == {"en": "Flyover of the demo pit", "es": "Sobrevuelo del pit de prueba"}


def test_import_run_render_publishes_no_performance_number_and_no_machine_path(world: World) -> None:
    render_world(world)
    run_id, pub, web = published_render(world)
    files = [web / "assets" / "runs" / run_id / "manifest.json", *(web / "assets" / run_id).glob("*.json")]
    assert len(files) == 2
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert "C:\\" not in text and "Users" not in text and "someone" not in text, f.name
        assert "5000 Ada" not in text and "595.95" not in text, f.name  # the GPU of the local manifest stays local
        walk = [json.loads(text)]
        while walk:
            node = walk.pop()
            for k, v in node.items() if isinstance(node, dict) else enumerate(node):
                assert k not in LOCAL_ONLY_KEYS, (f.name, k)
                if k == "encode_fps":
                    assert v is None
                if isinstance(v, dict | list):
                    walk.append(v)
    notes = " ".join(pub["notes"])
    assert "started" not in notes and "03:" not in notes
    video = next(a for a in pub["artefacts"] if a["id"] == "demo-flyover-av1")
    assert video["encoder"]["encoder"]["args"] == ["-i", "frame_%05d.png", "-c:v", "av1_nvenc"]


def test_import_run_render_refuses_a_wrong_manifest_kind_a_missing_label_and_a_frame_digest_mismatch(
    world: World,
) -> None:
    spec = render_world(world, label=None)
    code, err = run_job(world, RENDER_JOB, spec)
    assert code == 2 and "label" in err and world.runs() == []
    render_files(world)
    doc = json.loads((world.src / "render.manifest.json").read_text(encoding="utf-8"))
    doc["kind"] = "run"
    (world.src / "render.manifest.json").write_text(json.dumps(doc), encoding="utf-8")
    code, err = run_job(world, RENDER_JOB, spec)
    assert code == 2 and "kind" in err and world.runs() == []
    render_files(world, report_digest="9" * 64)
    code, err = run_job(world, RENDER_JOB, spec)
    assert code == 2 and "source frames" in err
    assert world.runs() == [] and not (world.store / "cas").exists()


def test_import_run_render_refuses_a_video_without_an_encoder_record_and_an_oversized_git_file(world: World) -> None:
    from pitstudio.runner import publish
    from pitstudio.runner.recipe import Usage

    spec = render_world(world)
    del spec["stages"][1]["outputs"][0]["encoder_from"]
    code, err = run_job(world, RENDER_JOB, spec)
    assert code == 2 and "encoder" in err and world.runs() == []
    spec = render_spec()
    big = b"x" * (10 * 2**20)
    (world.src / "demo-flyover.av1.mp4").write_bytes(big)
    code, err = run_job(world, RENDER_JOB, spec)
    assert code == 2 and "digest" in err and world.runs() == []  # the encode report pins another digest
    report = json.loads((world.src / "encode-report.json").read_text(encoding="utf-8"))
    report["clips"][0]["variants"]["av1"]["sha256"] = sha(big)
    (world.src / "encode-report.json").write_text(json.dumps(report), encoding="utf-8")
    assert run_job(world, RENDER_JOB, spec)[0] == 0
    with pytest.raises(Usage, match="small static file"):
        publish.publish(world.store, world.repo, world.runs()[0].name, None)


def test_import_run_render_a_newer_run_is_listed_after_the_older_one_in_the_web_index(world: World) -> None:
    from pitstudio.runner import publish

    render_world(world)
    run_id, _, web = published_render(world)
    git(world.repo, "add", "-A")
    git(world.repo, "commit", "-q", "-m", "first render published")  # a run is only published from a clean tree
    log = world.queue / f"{RENDER_JOB}.log"
    os.utime(log, (1_795_090_000, 1_795_090_000))  # one day later: a second render of the same recipe
    assert run_job(world, RENDER_JOB, render_spec())[0] == 0
    newer = world.runs()[-1].name
    assert newer > run_id
    publish.publish(world.store, world.repo, newer, None)
    idx = json.loads((web / "assets" / "manifest.json").read_text(encoding="utf-8"))
    assert [r["run_id"] for r in idx["runs"]] == [run_id, newer]
    assert {a["run_id"] for a in idx["artefacts"] if a["id"] == "demo-flyover-render"} == {run_id, newer}


def test_manifest_contract_accepts_a_render_recipe_and_nothing_wider() -> None:
    """Contract change of publish-render-2026-11-22 (ADR-0039): a run recipe may live under studio/recipes/render/."""
    ok = {"id": "bingham-flyover", "path": "render/bingham-flyover.yaml", "sha256": "a" * 64}
    ref = "#/$defs/run/properties/recipe"
    assert first_errors("manifest", ok, ref, n=1) == []
    for path in ("cases/a1-scene.yaml", "_bench/b.yaml"):
        assert first_errors("manifest", {**ok, "path": path}, ref, n=1) == []
    for path in (
        "other/x.yaml",
        "render/../x.yaml",
        "render/a/b.yaml",
        "render/x.txt",
        "/render/x.yaml",
        "renders/x.yaml",
    ):
        assert first_errors("manifest", {**ok, "path": path}, ref, n=1), path
    spec_copy = ROOT / "specs" / "001-contracts" / "contracts" / "manifest.schema.json"
    assert spec_copy.read_bytes() == (ROOT / "contracts" / "manifest.schema.json").read_bytes()


def test_import_run_render_labels_the_run_partial_when_the_recipe_changed_since_the_render(world: World) -> None:
    spec = render_world(world)
    doc = json.loads((world.src / "render.manifest.json").read_text(encoding="utf-8"))
    doc["recipe"] = {"id": "demo-flyover", "path": "render/demo.yaml", "sha256": "f" * 64}
    (world.src / "render.manifest.json").write_text(json.dumps(doc), encoding="utf-8")
    assert run_job(world, RENDER_JOB, spec)[0] == 0
    notes = " | ".join(manifest_of(world)["notes"])
    assert "partial" in notes and "recipe render/demo.yaml changed since the render" in notes


# ----------------------------------------------------------------------------------------------------------------------
# kind "bake": the web bake of the terrain (web-terrain-3d-2026-11-23): 3D Tiles and glTF files, no queue, no GPU
# ----------------------------------------------------------------------------------------------------------------------

BAKE_JOB = "43-web-terrain-demo"
PD = {"licence_class": "public-domain", "spdx": "LicenseRef-USGov-PD"}
TILE_INPUTS = [{"id": "usgs-3dep-bingham", "sha256": "a" * 64, "kind": "source"}]
TILESET = {
    "asset": {"version": "1.1"},
    "geometricError": 12,
    "root": {"geometricError": 12, "content": {"uri": "lod0.glb"}},
}
GLB = (
    b"glTF" + b"\x02\x00\x00\x00" + b"\x00" * 40 + b"C:" + bytes([92]) + b"Users" + bytes([92]) + b"someone"
)  # binary: never scanned for paths


def bake_spec(**tileset_extra: object) -> dict:
    tile = {"budget_class": "tiles-glb", "publish": True, "stage": "s60_export", **PD}
    return {
        "job": BAKE_JOB,
        "kind": "bake",
        "case": "A1",
        "all_cases": True,
        "recipe": "cases/c1.yaml",
        "slug": "web-terrain-demo",
        "seed": 0,
        "label": "terrain tiles baked from the OpenUSD scene",
        "notes": ["baked by the web bake tool"],
        "stages": [
            {
                "id": "s60_export",
                "tool": "openusd",
                "outputs": [
                    {
                        "name": "tiles/lod0/tileset.json",
                        "from": "tiles/lod0/tileset.json",
                        "id": "demo-lod0-tileset",
                        "kind": "tiles",
                        "media_type": "application/json",
                        "inputs": TILE_INPUTS,
                        **tile,
                        **tileset_extra,
                    },
                    {
                        "name": "tiles/lod0/lod0.glb",
                        "from": "tiles/lod0/lod0.glb",
                        "id": "demo-lod0-tile",
                        "kind": "tiles",
                        "media_type": "model/gltf-binary",
                        "inputs": TILE_INPUTS,
                        **tile,
                    },
                ],
            }
        ],
    }


def bake_files(w: World, *, tileset: dict | None = None) -> None:
    (w.src / "tiles" / "lod0").mkdir(parents=True, exist_ok=True)
    (w.src / "tiles" / "lod0" / "tileset.json").write_text(json.dumps(tileset or TILESET), encoding="utf-8")
    (w.src / "tiles" / "lod0" / "lod0.glb").write_bytes(GLB)


def test_manifest_contract_accepts_tiles_on_the_static_lane_and_still_refuses_a_static_video() -> None:
    """Contract change of web-terrain-3d-2026-11-23 (ADR-0039): a baked tileset or glTF tile is a static artefact."""
    base = {
        "id": "demo-lod0-tileset",
        "run_id": "20261123T120000Z-web-terrain-demo",
        "git_sha": "a" * 40,
        "path": "assets/20261123T120000Z-web-terrain-demo/tiles/lod0/tileset.json",
        "bytes": 240,
        "sha256": "b" * 64,
        "kind": "tiles",
        "producer": {"tool": "openusd", "stage": {"id": "s60_export"}},
        "inputs": TILE_INPUTS,
        "lane": "static",
        "asset_host": "git",
        "budget_class": "tiles-glb",
        **PD,
    }
    assert first_errors("manifest", base, "#/$defs/artefact", n=3) == []
    assert first_errors("manifest", {**base, "kind": "video", "id": "v"}, "#/$defs/artefact", n=1)
    assert first_errors("manifest", {**base, "kind": "onnx"}, "#/$defs/artefact", n=1)
    spec_copy = ROOT / "specs" / "001-contracts" / "contracts" / "manifest.schema.json"
    assert spec_copy.read_bytes() == (ROOT / "contracts" / "manifest.schema.json").read_bytes()


def test_import_run_bake_records_a_valid_run_without_queue_facts_gpu_hours_or_partial_notes(world: World) -> None:
    bake_files(world)
    code, err = run_job(world, BAKE_JOB, bake_spec())
    assert code == 0, err
    m = manifest_of(world)
    assert first_errors("manifest", m, "#/$defs/run", n=3) == []
    assert [s["tool"] for s in m["stages"]] == ["openusd"]
    notes = " | ".join(m["notes"])
    assert "web bake" in notes and LABEL not in notes
    assert "GPU-hours" not in notes and "script" not in notes and "partial" not in notes
    imp = json.loads((world.runs()[0] / "import.json").read_text(encoding="utf-8"))
    assert imp["all_cases"] is True and imp["partial"] is False


def test_import_run_bake_publishes_tiles_as_static_artefacts_with_inputs_and_matching_digests(world: World) -> None:
    from pitstudio.runner import publish

    bake_files(world)
    assert run_job(world, BAKE_JOB, bake_spec())[0] == 0
    run_id = world.runs()[0].name
    publish.publish(world.store, world.repo, run_id, None)
    web = world.repo / "web" / "public"
    idx = json.loads((web / "assets" / "manifest.json").read_text(encoding="utf-8"))
    assert first_errors("manifest", idx, "#/$defs/web_index", n=3) == []
    by_id = {a["id"]: a for a in idx["artefacts"]}
    tileset, tile = by_id["demo-lod0-tileset"], by_id["demo-lod0-tile"]
    assert tileset["kind"] == tile["kind"] == "tiles" and tileset["lane"] == tile["lane"] == "static"
    assert tileset["inputs"] == TILE_INPUTS and tileset["budget_class"] == "tiles-glb"
    assert tileset["path"] == f"assets/{run_id}/tiles/lod0/tileset.json" and tileset["media_type"] == "application/json"
    for a in (tileset, tile):
        data = (web / a["path"]).read_bytes()
        assert sha(data) == a["sha256"] and len(data) == a["bytes"]
        assert "cases" not in a  # one tileset for every case page


def test_import_run_bake_scans_a_published_tileset_for_machine_paths_but_never_the_binary_tiles(world: World) -> None:
    from pitstudio.runner import publish
    from pitstudio.runner.recipe import Usage

    bake_files(world)
    assert run_job(world, BAKE_JOB, bake_spec())[0] == 0
    publish.publish(
        world.store, world.repo, world.runs()[0].name, None
    )  # the GLB holds a machine path in its bytes: not scanned
    git(world.repo, "add", "-A")
    git(world.repo, "commit", "-q", "-m", "published")
    leaking = {**TILESET, "extras": {"from": "C:" + chr(92) + "Users" + chr(92) + "someone" + chr(92) + "scene.usdc"}}
    bake_files(world, tileset=leaking)
    os.utime(world.queue / f"{JOB}.log", None)
    spec = bake_spec()
    spec["slug"] = "web-terrain-leak"
    assert run_job(world, BAKE_JOB, spec)[0] == 0
    with pytest.raises(Usage, match="absolute path"):
        publish.publish(world.store, world.repo, world.runs()[-1].name, None)
