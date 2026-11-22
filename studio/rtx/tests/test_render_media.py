# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: PT018  (compound assertions read as one fact in these tests)
"""PNG writer and FFmpeg encode helpers (no real FFmpeg process is started)."""

from __future__ import annotations

import struct
import subprocess
import zlib
from pathlib import Path

import numpy as np
import pytest
from pitstudio_rtx.render.encode import RenderEncodeError, encode_clip, encode_command, find_ffmpeg, pick_encoder
from pitstudio_rtx.render.imageio import write_png

OUTPUT = {
    "clip": "flyover.mp4",
    "encoder": {
        "codec": "h264",
        "name": "h264_nvenc",
        "preset": "p5",
        "cq": 23,
        "gop_frames": 60,
        "pix_fmt": "yuv420p",
    },
}


def _read_png(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, ihdr = 8, b"", None
    while pos < len(raw):
        (n,) = struct.unpack(">I", raw[pos : pos + 4])
        kind, body = raw[pos + 4 : pos + 8], raw[pos + 8 : pos + 8 + n]
        assert zlib.crc32(kind + body) == struct.unpack(">I", raw[pos + 8 + n : pos + 12 + n])[0]
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    w, h, depth, color, *_ = ihdr
    assert (depth, color) == (8, 2)
    rows = np.frombuffer(zlib.decompress(idat), dtype=np.uint8).reshape(h, 1 + 3 * w)
    assert (rows[:, 0] == 0).all()
    return rows[:, 1:].reshape(h, w, 3)


def test_png_round_trip_and_atomic(tmp_path):
    image = np.random.default_rng(1).integers(0, 256, (18, 32, 3), dtype=np.uint8)
    out = tmp_path / "sub" / "a.png"
    write_png(out, image)
    assert np.array_equal(_read_png(out), image)
    assert [p.name for p in out.parent.iterdir()] == ["a.png"]  # no .part left behind


@pytest.mark.parametrize(
    "bad", [np.zeros((4, 4), np.uint8), np.zeros((4, 4, 4), np.uint8), np.zeros((4, 4, 3), np.float32)]
)
def test_png_rejects_other_layouts(tmp_path, bad):
    with pytest.raises(ValueError, match="uint8"):
        write_png(tmp_path / "x.png", bad)


def test_encode_command_nvenc():
    cmd = encode_command("ffmpeg", Path("f"), "frame_%05d.png", 30, Path("o.mp4"), OUTPUT, "h264_nvenc")
    joined = " ".join(cmd)
    for part in (
        "-framerate 30",
        "-start_number 0",
        "-c:v h264_nvenc",
        "-preset p5",
        "-rc vbr",
        "-cq 23",
        "-b:v 0",
        "-g 60",
        "-pix_fmt yuv420p",
        "-movflags +faststart",
    ):
        assert part in joined
    assert cmd[0] == "ffmpeg" and cmd[-1] == "o.mp4"


def test_encode_command_libx264_fallback():
    joined = " ".join(encode_command("ffmpeg", Path("f"), "frame_%05d.png", 30, Path("o.mp4"), OUTPUT, "libx264"))
    assert "-c:v libx264" in joined and "-crf 23" in joined and "-cq" not in joined


def _runner(encoders: str, version: str = "ffmpeg version n8.1.3-14-gabc Copyright"):
    def run(cmd, **kwargs):
        if "-encoders" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=encoders, stderr="")
        if "-version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=version + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return run


def test_pick_encoder_prefers_nvenc_and_falls_back_only_when_missing():
    assert pick_encoder("ffmpeg", "h264_nvenc", _runner(" V....D h264_nvenc NVIDIA NVENC\n V....D libx264 x")) == (
        "h264_nvenc",
        False,
    )
    assert pick_encoder("ffmpeg", "h264_nvenc", _runner(" V....D libx264 x")) == ("libx264", True)
    with pytest.raises(RenderEncodeError, match=r"no H\.264 encoder"):
        pick_encoder("ffmpeg", "h264_nvenc", _runner(" V....D mpeg4 x"))


def test_find_ffmpeg(tmp_path, monkeypatch):
    exe = tmp_path / "ffmpeg.exe"
    exe.write_bytes(b"x")
    assert find_ffmpeg({"PITSTUDIO_FFMPEG": str(exe)}) == str(exe)
    with pytest.raises(RenderEncodeError, match="PITSTUDIO_FFMPEG"):
        find_ffmpeg({"PITSTUDIO_FFMPEG": str(tmp_path / "missing.exe")})
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(RenderEncodeError, match="FFmpeg not found"):
        find_ffmpeg({})


def test_encode_clip_reports_version_and_args(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    info = encode_clip(
        frames,
        "frame_%05d.png",
        30,
        tmp_path / "o.mp4",
        OUTPUT,
        ffmpeg="ffmpeg",
        runner=_runner(" V....D h264_nvenc x"),
    )
    assert info.name == "h264_nvenc" and not info.fallback
    assert info.ffmpeg_version == "n8.1.3"
    assert "-c:v" in info.args and str(tmp_path) not in " ".join(info.args)  # no machine path in the recorded args


def test_encode_clip_failure_names_the_tail(tmp_path):
    def run(cmd, **kwargs):
        if "-encoders" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=" V....D h264_nvenc x", stderr="")
        if "-version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="ffmpeg version n8.1", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="line1\nCannot load nvcuda.dll")

    with pytest.raises(RenderEncodeError, match="nvcuda"):
        encode_clip(tmp_path, "frame_%05d.png", 30, tmp_path / "o.mp4", OUTPUT, ffmpeg="ffmpeg", runner=run)
