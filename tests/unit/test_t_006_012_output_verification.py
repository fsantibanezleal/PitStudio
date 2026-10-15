# ruff: noqa: E501, PT018
"""T-006-012: output verification of an encoded MP4: full decode, frame count, duration, `moov` before `mdat`.

Requirements: FR-006-05.

Spec: specs/006-media-telemetry/spec.md FR-006-05 (decode fully with the same FFmpeg (`-v error -f null`, empty error output),
a decoded frame count equal to the source frame count, a duration of frames/fps within one frame period, and an MP4 top-level
box order in which `moov` precedes `mdat`; a failing file is deleted and the stage fails with error class `decode-failed`);
plan.md "Key decisions" (a short reader of top-level ISO base-media boxes (size, type) asserting `ftyp`, then `moov` before
`mdat`) and section 7 (`+faststart` puts `moov` first).

Oracle: hand-built ISO/IEC 14496-12 box sequences (32-bit sizes and the 64-bit `largesize` form, section 4.2 of the standard),
fake FFmpeg output in the documented `-progress` form, hand-calculated durations (300 frames at 30 fps = 10 s; one frame period =
1/30 s). The tests use half and one-and-a-half frame periods so that no boundary convention matters.

Expected API (module `pitstudio_studio.media.encode`; errors in `pitstudio_studio.media.errors`):
    errors.DecodeFailed(EncodeError)    error_class "decode-failed"
    top_level_boxes(data: bytes) -> list[tuple[str, int]]
        the (type, size) of every top-level box in order; size 1 means a 64-bit `largesize` follows and the returned size is that
        value; size 0 means "to the end of the data" and the returned size is the remaining length; raises DecodeFailed for a box
        whose size is below its header size or runs past the end of the data, and for trailing bytes too short to be a header;
        empty data gives an empty list.
    check_box_order(data: bytes) -> None   raises DecodeFailed unless the first box is `ftyp`, and a `moov` box exists and precedes
        the first `mdat` box (a file without `moov` or without `mdat` fails).
    verify_output(path: Path, *, ffmpeg, runner, source_frames: int, fps: float) -> Verification
        1. reads the file and runs `check_box_order` on it;
        2. decodes it with `runner([str(ffmpeg), "-v", "error", ..., "-i", str(path), ..., "-f", "null", ..., "-progress", "pipe:1", ...,
           "-"])` (an argument list, never a shell; any other flags are free): stderr must be empty, the return code 0, the last
           `frame=<n>` of stdout must equal `source_frames`, and the last `out_time_us=<t>` must be within one frame period (1/fps) of
           source_frames / fps seconds;
        3. returns Verification(frames: int, duration_s: float) with the decoded frame count and out_time_us / 1e6.
        On any failure the file at `path` is deleted first and DecodeFailed is raised (message `decode-failed: ...`).
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_studio.media.encode import check_box_order, top_level_boxes, verify_output
from pitstudio_studio.media.errors import DecodeFailed

N, FPS = 300, 30


def write_mp4(tmp: Path, *, moov_first: bool = True, name: str = "clip.av1.mp4", total: int = 5000) -> Path:
    p = tmp / name
    p.write_bytes(kit.mp4_bytes(total, moov_first=moov_first))
    return p


def fake(**kw) -> kit.FakeFFmpeg:
    return kit.FakeFFmpeg(frames=N, fps=FPS, **kw)


def verify(p: Path, ff: kit.FakeFFmpeg, **kw):
    return verify_output(
        p, ffmpeg=Path("ffmpeg-stand-in"), runner=ff, source_frames=kw.pop("source_frames", N), fps=kw.pop("fps", FPS)
    )


# ---------------------------------------------------------------------------------------------------------------------
# the box reader (hand-built boxes)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-05")
def test_top_level_boxes_of_a_hand_built_faststart_file():
    data = kit.mp4_bytes(5000, moov_first=True)
    assert top_level_boxes(data) == [("ftyp", 24), ("moov", 128), ("mdat", 5000 - 24 - 128)]
    assert kit.box_types(data) == top_level_boxes(data)


@pytest.mark.req("FR-006-05")
def test_top_level_boxes_understands_largesize_and_to_end_of_file():
    ftyp = struct.pack(">I4s4sI4s4s", 24, b"ftyp", b"isom", 512, b"isom", b"iso2")
    moov = struct.pack(">I4s", 16, b"moov") + b"\x00" * 8
    mdat_large = (
        struct.pack(">I4sQ", 1, b"mdat", 16 + 40) + b"\x00" * 40
    )  # size 1: the real size is the next 8 bytes (ISO 14496-12, 4.2)
    assert top_level_boxes(ftyp + moov + mdat_large) == [("ftyp", 24), ("moov", 16), ("mdat", 56)]
    mdat_to_end = struct.pack(">I4s", 0, b"mdat") + b"\x00" * 30  # size 0: extends to the end of the file
    assert top_level_boxes(ftyp + moov + mdat_to_end) == [("ftyp", 24), ("moov", 16), ("mdat", 38)]


@pytest.mark.req("FR-006-05")
@pytest.mark.parametrize(
    "data",
    [
        kit.mp4_bytes(5000, moov_first=True)[:3000],  # truncated inside mdat: declared size runs past the data
        struct.pack(">I4s", 4, b"free"),  # size below the 8-byte header
        b"\x00\x00\x00",  # shorter than one header (a trailing fragment)
    ],
)
def test_top_level_boxes_rejects_truncated_or_impossible_boxes(data):
    with pytest.raises(DecodeFailed):
        top_level_boxes(data)


@pytest.mark.req("FR-006-05")
def test_box_order_accepts_moov_before_mdat():
    check_box_order(kit.mp4_bytes(5000, moov_first=True))


@pytest.mark.req("FR-006-05")
@pytest.mark.parametrize(
    "data",
    [
        kit.mp4_bytes(5000, moov_first=False),  # mdat before moov (no +faststart)
        b"",  # empty file
        kit.mp4_bytes(5000, moov_first=True)[24:],  # no ftyp first
        kit.mp4_bytes(5000, moov_first=True)[:24],  # ftyp only: no moov, no mdat
        kit.mp4_bytes(5000, moov_first=True)[:24] + kit.mp4_bytes(5000, moov_first=True)[152:],  # mdat without moov
    ],
)
def test_box_order_rejects_every_other_layout(data):
    with pytest.raises(DecodeFailed):
        check_box_order(data)


# ---------------------------------------------------------------------------------------------------------------------
# the full verification with the fake FFmpeg
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-05")
def test_a_good_file_passes_and_the_decode_uses_an_argument_list_with_v_error_and_f_null(tmp_path):
    p = write_mp4(tmp_path)
    ff = fake()
    v = verify(p, ff)
    assert p.is_file()
    assert v.frames == N and v.duration_s == pytest.approx(10.0, abs=1e-6)  # 300 frames / 30 fps
    assert ff.kinds() == ["decode"]
    argv = ff.calls[0]
    assert argv[0] == "ffmpeg-stand-in"
    assert argv[argv.index("-v") + 1] == "error" and argv[argv.index("-f") + 1] == "null"
    assert str(p) in argv


@pytest.mark.req("FR-006-05")
@pytest.mark.parametrize(
    ("override", "why"),
    [
        ({"stderr": "[av1 @ 0x55] Error parsing OBU data\n"}, "decoder error output"),
        ({"stderr": "x"}, "any error output at all"),
        ({"returncode": 1}, "non-zero exit"),
        ({"frames": N - 1}, "a dropped frame"),
        ({"frames": N + 1}, "an extra frame"),
        ({"out_time_s": 10.0 + 1.5 / FPS}, "duration over by 1.5 frame periods"),
        ({"out_time_s": 10.0 - 1.5 / FPS}, "duration short by 1.5 frame periods"),
    ],
)
def test_every_failed_check_deletes_the_file_and_raises_decode_failed(tmp_path, override, why):
    p = write_mp4(tmp_path)
    ff = fake(decode_overrides={"clip.av1.mp4": override})
    with pytest.raises(DecodeFailed) as ei:
        verify(p, ff)
    assert ei.value.error_class == "decode-failed" and str(ei.value).startswith("decode-failed: "), why
    assert not p.exists(), why  # a failing file is deleted


@pytest.mark.req("FR-006-05")
def test_duration_within_half_a_frame_period_is_accepted(tmp_path):
    p = write_mp4(tmp_path)
    ff = fake(decode_overrides={"clip.av1.mp4": {"out_time_s": 10.0 + 0.5 / FPS}})
    assert verify(p, ff).frames == N


@pytest.mark.req("FR-006-05")
def test_mdat_before_moov_fails_even_when_the_decode_is_clean_and_deletes_the_file(tmp_path):
    p = write_mp4(tmp_path, moov_first=False)
    with pytest.raises(DecodeFailed):
        verify(p, fake())
    assert not p.exists()


@pytest.mark.req("FR-006-05")
def test_empty_and_truncated_files_fail(tmp_path):
    p = tmp_path / "empty.mp4"
    p.write_bytes(b"")
    with pytest.raises(DecodeFailed):
        verify(p, fake())
    assert not p.exists()
    q = tmp_path / "cut.mp4"
    q.write_bytes(kit.mp4_bytes(5000, moov_first=True)[:2500])
    with pytest.raises(DecodeFailed):
        verify(q, fake())
    assert not q.exists()


@pytest.mark.req("FR-006-05")
def test_the_expected_frame_count_is_the_source_count_not_the_decoders(tmp_path):
    p = write_mp4(tmp_path)
    with pytest.raises(DecodeFailed):
        verify(p, fake(), source_frames=299)  # the decoder returns 300 frames; the source had 299
    assert not p.exists()


@pytest.mark.req("FR-006-05")
@pytest.mark.parametrize("fps", [24, 25, 50, 60])
def test_duration_rule_scales_with_the_source_frame_rate(tmp_path, fps):
    p = write_mp4(tmp_path)
    ff = kit.FakeFFmpeg(frames=N, fps=fps)  # out_time = 300 / fps
    v = verify_output(p, ffmpeg=Path("ffmpeg-stand-in"), runner=ff, source_frames=N, fps=fps)
    assert v.duration_s == pytest.approx(N / fps, abs=1e-6)
