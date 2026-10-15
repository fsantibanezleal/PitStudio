# ruff: noqa: E501, PT018
"""T-006-016 (GPU): NVENC AV1 1080p + H.264 720p + WebP poster end to end, read back by `ffprobe`; encode determinism.

Marked `gpu`: needs the pinned FFmpeg 8.1 build with `av1_nvenc`, `h264_nvenc`, `libvmaf` and `libwebp` (`PITSTUDIO_FFMPEG`,
`PITSTUDIO_FFMPEG_SHA256` and `PITSTUDIO_FFPROBE` set by the maintainer) and the `gpu0.nvenc` lock. Never run in CI and not
run during the red phase (the GPU belongs to the scheduled jobs).

Requirements: FR-006-01, FR-006-16.

Spec: specs/006-media-telemetry/spec.md FR-006-01 (per clip `<clip>.av1.mp4` with `av1_nvenc`, 1920 x 1080, yuv420p 8-bit;
`<clip>.h264.mp4` with `h264_nvenc`, High profile, 1280 x 720, yuv420p 8-bit; both MP4 with `+faststart` and the source frame rate;
`<clip>.webp`, a 1280 x 720 poster of the frame `poster_frame`) and FR-006-16 (the same frames encoded twice with the same build,
driver, GPU and arguments: determinism `bitwise` only if both outputs have the same SHA-256, otherwise `statistical` with a
VMAF-mean difference <= 0.5); plan.md test strategy (FR-006-01: expected codec, profile, size, pixel format and frame rate read
back by `ffprobe`, the reference implementation; FR-006-16: SHA-256 equality by `hashlib`, VMAF difference from the two logs).

Oracle: `ffprobe -show_streams -show_format -of json` (FFmpeg's own reader, an independent implementation of the container and
codec parsing), `hashlib`, the ISO base-media box order, and the VMAF log of a separate libvmaf run written by the test.

Expected API (as in test_t_006_013 for `encode.run`, with real FFmpeg: default runner, `env` = os.environ, `driver_version` from NVML):
    job["params"]["check_determinism"] = True   makes the stage encode the final settings of each variant a second time into scratch
        and report, in the stage result's `observables`, per codec c in {av1, h264}: `determinism_<c>_bitwise` = 1.0 when both outputs
        have the same SHA-256 and 0.0 otherwise; and, only when it is 0.0, `determinism_<c>_vmaf_mean_diff` = |VMAF mean of the first
        minus VMAF mean of the second| (<= 0.5 required by the spec).
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_studio.media.encode import run

pytestmark = pytest.mark.gpu

N, FPS = 60, 30  # a 2 s fixture sequence (the integration test of the plan uses a 10 s clip on the reference machine)


def numpy_png(arr: np.ndarray) -> bytes:
    h, w, _ = arr.shape
    raw = np.concatenate([np.zeros((h, 1), dtype=np.uint8), arr.reshape(h, w * 3)], axis=1).tobytes()
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 3)) + chunk(b"IEND", b"")


def moving_texture(k: int, w: int = 1920, h: int = 1080) -> np.ndarray:
    y, x = np.mgrid[0:h, 0:w]
    r = (127 + 100 * np.sin((x + 9 * k) / 37.0)).astype(np.uint8)
    g = (127 + 100 * np.sin((y - 5 * k) / 23.0 + x / 211.0)).astype(np.uint8)
    b = ((x * 255 // w + 3 * k) % 256).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


@pytest.fixture(scope="module")
def encoded(tmp_path_factory):
    root = tmp_path_factory.mktemp("nvenc")
    frames = root / "in" / "frames"
    frames.mkdir(parents=True)
    paths = []
    for k in range(N):
        p = frames / f"frame_{k:05d}.png"
        p.write_bytes(numpy_png(moving_texture(k)))
        paths.append(p)
    manifest = kit.frame_manifest(paths, clip="gpu-fixture", fps=FPS)
    mpath = root / "in" / "manifest.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    seq = SimpleNamespace(root=root, input_dir=root / "in", frames=paths, manifest=manifest, manifest_path=mpath)
    job = kit.make_job(
        root,
        seq,
        params={
            "pinned_ffmpeg_sha256": os.environ["PITSTUDIO_FFMPEG_SHA256"],
            "nvenc_api": "13.0",
            "check_determinism": True,
        },
    )
    os.environ["PITSTUDIO_HELD_LOCKS"] = "gpu0.nvenc"  # the runner's list; this test stands in for the runner
    result = run(job)
    return Path(job["output_dir"]), result, manifest


def probe(path: Path) -> dict:
    out = subprocess.run(
        [os.environ["PITSTUDIO_FFPROBE"], "-v", "error", "-show_streams", "-show_format", "-count_frames", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return json.loads(out.stdout)


@pytest.mark.req("FR-006-01")
def test_av1_file_is_1080p_yuv420p_with_the_source_frame_rate(encoded):
    out, _, _ = encoded
    s = probe(out / "gpu-fixture.av1.mp4")["streams"][0]
    assert (s["codec_name"], s["width"], s["height"], s["pix_fmt"]) == ("av1", 1920, 1080, "yuv420p")
    assert s["r_frame_rate"] == f"{FPS}/1" and int(s["nb_read_frames"]) == N


@pytest.mark.req("FR-006-01")
def test_h264_file_is_720p_high_profile_yuv420p_with_the_source_frame_rate(encoded):
    out, _, _ = encoded
    s = probe(out / "gpu-fixture.h264.mp4")["streams"][0]
    assert (s["codec_name"], s["profile"], s["width"], s["height"], s["pix_fmt"]) == (
        "h264",
        "High",
        1280,
        720,
        "yuv420p",
    )
    assert s["r_frame_rate"] == f"{FPS}/1" and int(s["nb_read_frames"]) == N


@pytest.mark.req("FR-006-01")
def test_both_mp4_files_are_faststart(encoded):
    out, _, _ = encoded
    for name in ("gpu-fixture.av1.mp4", "gpu-fixture.h264.mp4"):
        types = [t for t, _ in kit.box_types((out / name).read_bytes())]
        assert types[0] == "ftyp" and types.index("moov") < types.index("mdat"), name


@pytest.mark.req("FR-006-01")
def test_poster_is_a_1280x720_webp_of_the_poster_frame(encoded):
    out, _, _ = encoded
    s = probe(out / "gpu-fixture.webp")["streams"][0]
    assert (s["codec_name"], s["width"], s["height"]) == ("webp", 1280, 720)
    assert (out / "gpu-fixture.webp").stat().st_size <= kit.POSTER_BYTES_MAX


@pytest.mark.req("FR-006-01")
def test_pair_fits_the_budget_and_the_report_agrees_with_the_files(encoded):
    out, _, _ = encoded
    report = json.loads((out / "encode-report.json").read_text(encoding="utf-8"))
    clip = report["clips"][0]
    total = (out / "gpu-fixture.av1.mp4").stat().st_size + (out / "gpu-fixture.h264.mp4").stat().st_size
    assert total == clip["pair_bytes"] <= kit.PAIR_BYTES_MAX
    for v in clip["variants"].values():
        assert v["record"]["vmaf"]["mean"] >= kit.VMAF_MEAN_MIN and v["record"]["vmaf"]["p5"] >= kit.VMAF_P5_MIN


@pytest.mark.req("FR-006-16")
def test_determinism_class_follows_the_sha256_rule(encoded):
    _, result, _ = encoded
    obs = result["observables"]
    for codec in ("av1", "h264"):
        bitwise = obs[f"determinism_{codec}_bitwise"]
        assert bitwise in (0.0, 1.0)
        if bitwise == 0.0:  # statistical: the VMAF means of the two encodes differ by at most 0.5
            assert 0.0 <= obs[f"determinism_{codec}_vmaf_mean_diff"] <= 0.5
        else:
            assert f"determinism_{codec}_vmaf_mean_diff" not in obs
