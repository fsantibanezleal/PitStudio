# ruff: noqa: E501, PT018
"""T-006-021: hostile frames and names; FFmpeg called with argument lists and never through a shell.

Requirements: FR-006-12, FR-006-13.

Spec: specs/006-media-telemetry/spec.md FR-006-12 (a frame that cannot be decoded or is truncated, frames that differ in size or bit
depth, a missing frame index, a frame-list SHA-256 that differs from the frame manifest, fewer than 2 frames, a resolution below
1920 x 1080 and a frame rate other than 24, 25, 30, 50 or 60 fps give error class `frames-invalid` naming the first bad frame, before
any encode) and FR-006-13 (a clip name with anything outside `[a-z0-9-]` or longer than 64 characters, or a frame path that resolves
outside the stage's input folder, gives error class `name-invalid`; FFmpeg is always called with an argument list, never through a
shell); spec section 8 (a clip name starts with a letter or digit, so that it never reads as an FFmpeg option; frames are named by a
printf pattern inside an optional relative folder); plan.md test strategy (corrupt fixtures: truncated PNG, a 1919 x 1080 frame, a
16-bit frame in an 8-bit sequence, a missing index, a tampered digest, a single frame, 29.97 fps; names with `/`, `\\`, `..`, upper
case, 65 characters; a frame path escaping the input folder; a spy on `subprocess.run` asserting `shell=False` and a list argument).

Oracle: PNG files written byte by byte by the test kit (PNG specification, ISO/IEC 15948) and then damaged by hand (bytes cut, a CRC byte
flipped, a signature byte changed); `hashlib` for digests; the hand-written lists of valid and invalid names and frame rates.

Expected API of the implementation (module `pitstudio_studio.media.frames`; errors in `pitstudio_studio.media.errors`):
    errors.FramesInvalid(EncodeError)  error_class "frames-invalid"      errors.NameInvalid(EncodeError)  error_class "name-invalid"
    validate_clip_name(name: str) -> None      raises NameInvalid unless `^[a-z0-9][a-z0-9-]{0,63}$` fully matches (no trailing newline)
    validate_sequence(manifest: dict, input_dir: Path) -> ValidatedSequence
        `manifest` is a parsed DC-006-01 document (not necessarily schema-valid: hostile values are the point), `input_dir` the folder
        that holds the manifest file. Frame k (0-based) is `input_dir / manifest.get("directory", ".") / (frame_pattern % (first_index + k))`.
        Checks in this order: clip name; every frame path resolves inside `input_dir` (else NameInvalid; a pattern containing a path
        separator or `..`, an absolute or `..` directory also give NameInvalid); frames >= 2, width >= 1920, height >= 1080, fps in
        {24, 25, 30, 50, 60}; then frame by frame in index order the first frame that is missing, truncated, undecodable (signature, chunk
        CRCs, zlib stream and its length against IHDR), of another size or bit depth than the manifest, or (when the manifest lists
        `frame_sha256`) of another digest -> FramesInvalid whose message contains that frame's file name; finally the frame-list digest
        against `source_frames_sha256` -> FramesInvalid. No image data is allocated for a frame whose IHDR already disagrees.
        Returns ValidatedSequence(paths: list[Path], width, height, bit_depth, fps, frames, source_frames_sha256) (frozen dataclass).
    encode.run(job, ...) calls `validate_sequence` before any encode (FFmpeg discovery may already have run); FFmpeg is run with
        `runner(list_of_str, shell=False-or-absent, ...)`; the default runner is `subprocess.run` looked up at call time.
"""

from __future__ import annotations

import copy
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_studio.media.errors import FramesInvalid, NameInvalid
from pitstudio_studio.media.frames import validate_clip_name, validate_sequence


def make(tmp_path, n=3, **kw) -> kit.Sequence3:
    return kit.Sequence3(tmp_path, n, **kw)


def refresh(seq: kit.Sequence3) -> None:
    """Recompute the manifest digests from the files as they are now (so that only the intended defect remains)."""
    per = [kit.file_sha256(p) for p in seq.frames if p.is_file()]
    seq.manifest["frame_sha256"] = per
    seq.manifest["source_frames_sha256"] = kit.frames_digest(per)
    seq.write_manifest()


def check(seq: kit.Sequence3, manifest=None):
    return validate_sequence(manifest if manifest is not None else seq.manifest, seq.input_dir)


# ---------------------------------------------------------------------------------------------------------------------
# the happy path and the manifest variants
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-12")
def test_a_clean_sequence_is_accepted_and_described(tmp_path):
    seq = make(tmp_path, 3)
    v = check(seq)
    assert v.frames == 3 and (v.width, v.height, v.bit_depth, v.fps) == (1920, 1080, 8, 30)
    assert v.paths == seq.frames and v.source_frames_sha256 == seq.manifest["source_frames_sha256"]


@pytest.mark.req("FR-006-12")
def test_a_16_bit_sequence_with_a_pattern_without_prefix_and_a_first_index_is_accepted(tmp_path):
    seq = make(tmp_path, 3, depth=16, pattern="%04d.png", first_index=1, fps=60)
    v = check(seq)
    assert v.bit_depth == 16 and v.fps == 60 and [p.name for p in v.paths] == ["0001.png", "0002.png", "0003.png"]


@pytest.mark.req("FR-006-12")
@pytest.mark.parametrize("fps", [24, 25, 30, 50, 60])
def test_the_five_allowed_frame_rates_are_accepted(tmp_path, fps):
    assert check(make(tmp_path, 2, fps=fps)).fps == fps


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-12: hostile sequences (each case has exactly one defect)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-12")
@pytest.mark.parametrize("fps", [29.97, 23, 0, -30, 120, 61, 30.5, "30", None, float("nan")])
def test_frame_rates_outside_the_five_allowed_values_are_invalid(tmp_path, fps):
    seq = make(tmp_path, 2)
    m = copy.deepcopy(seq.manifest)
    m["fps"] = fps
    with pytest.raises(FramesInvalid):
        check(seq, m)


@pytest.mark.req("FR-006-12")
def test_fewer_than_two_frames_is_invalid(tmp_path):
    seq = make(tmp_path, 1)
    with pytest.raises(FramesInvalid):
        check(seq)
    m = copy.deepcopy(seq.manifest)
    m["frames"] = 0
    with pytest.raises(FramesInvalid):
        check(seq, m)


@pytest.mark.req("FR-006-12")
@pytest.mark.parametrize(("w", "h"), [(1919, 1080), (1920, 1079), (640, 480), (1, 1)])
def test_a_resolution_below_1920_by_1080_is_invalid(tmp_path, w, h):
    seq = make(tmp_path, 2, width=w, height=h)
    with pytest.raises(FramesInvalid):
        check(seq)


@pytest.mark.req("FR-006-12")
def test_a_truncated_frame_is_invalid_and_the_first_bad_frame_is_named(tmp_path):
    seq = make(tmp_path, 3)
    for k in (2, 1):  # frames 1 and 2 are both damaged: the message must name frame 1
        data = seq.frames[k].read_bytes()
        seq.frames[k].write_bytes(data[: len(data) // 2])
    refresh(seq)
    with pytest.raises(FramesInvalid) as ei:
        check(seq)
    assert ei.value.error_class == "frames-invalid" and str(ei.value).startswith("frames-invalid: ")
    assert "frame_00001.png" in str(ei.value) and "frame_00002.png" not in str(ei.value)


def damage(path: Path, how: str) -> None:
    data = bytearray(path.read_bytes())
    if how == "signature":
        data[1] ^= 0x01
    elif how == "crc":  # flip one byte inside the IDAT payload (its CRC no longer matches)
        i = data.index(b"IDAT") + 8
        data[i] ^= 0xFF
    elif how == "zero":
        data = bytearray()
    elif how == "text":
        data = bytearray(b"this is not a png\n" * 100)
    elif how == "no-iend":
        data = data[:-12]
    elif (
        how == "idat-short"
    ):  # a valid chunk structure whose zlib stream ends early: replace IDAT by a shorter valid stream
        w, h = struct.unpack(">II", bytes(data[16:24]))
        raw = (b"\x00" + b"\x01\x02\x03" * w) * (h // 2)
        body = zlib.compress(raw, 1)
        ihdr = bytes(data[8 : 8 + 8 + 13 + 4])
        idat = (
            struct.pack(">I", len(body)) + b"IDAT" + body + struct.pack(">I", zlib.crc32(b"IDAT" + body) & 0xFFFFFFFF)
        )
        iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
        data = bytearray(b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend)
    path.write_bytes(bytes(data))


@pytest.mark.req("FR-006-12")
@pytest.mark.parametrize("how", ["signature", "crc", "zero", "text", "no-iend", "idat-short"])
def test_undecodable_frames_are_invalid_and_named(tmp_path, how):
    seq = make(tmp_path, 3)
    damage(seq.frames[1], how)
    refresh(seq)  # digests of the damaged files: only the decode check can catch it
    with pytest.raises(FramesInvalid) as ei:
        check(seq)
    assert "frame_00001.png" in str(ei.value)


@pytest.mark.req("FR-006-12")
def test_a_frame_of_another_size_is_invalid_and_named(tmp_path):
    seq = make(tmp_path, 3)
    seq.frames[2].write_bytes(
        kit.png_bytes(1930, 1080, rgb=(1, 2, 3))
    )  # still >= 1920 x 1080, but not the sequence's size
    refresh(seq)
    with pytest.raises(FramesInvalid) as ei:
        check(seq)
    assert "frame_00002.png" in str(ei.value)


@pytest.mark.req("FR-006-12")
def test_a_16_bit_frame_in_an_8_bit_sequence_is_invalid_and_named(tmp_path):
    seq = make(tmp_path, 3)
    seq.frames[1].write_bytes(kit.png_bytes(1920, 1080, depth=16, rgb=(9, 9, 9)))
    refresh(seq)
    with pytest.raises(FramesInvalid) as ei:
        check(seq)
    assert "frame_00001.png" in str(ei.value)


@pytest.mark.req("FR-006-12")
def test_an_ihdr_that_claims_a_gigantic_image_is_rejected_without_allocating_it(tmp_path):
    seq = make(tmp_path, 3)
    ihdr = struct.pack(">IIBBBBB", 60000, 60000, 8, 2, 0, 0, 0)
    ck = struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
    seq.frames[1].write_bytes(b"\x89PNG\r\n\x1a\n" + ck)  # no data follows
    refresh(seq)
    with pytest.raises(FramesInvalid) as ei:
        check(seq)
    assert "frame_00001.png" in str(ei.value)


@pytest.mark.req("FR-006-12")
def test_a_missing_frame_index_is_invalid_and_named(tmp_path):
    seq = make(tmp_path, 4)
    seq.frames[2].unlink()
    with pytest.raises(FramesInvalid) as ei:
        check(seq)
    assert "frame_00002.png" in str(ei.value)


@pytest.mark.req("FR-006-12")
def test_a_manifest_that_promises_more_frames_than_exist_names_the_first_missing_one(tmp_path):
    seq = make(tmp_path, 3)
    m = copy.deepcopy(seq.manifest)
    m["frames"] = 5
    m.pop("frame_sha256")
    with pytest.raises(FramesInvalid) as ei:
        check(seq, m)
    assert "frame_00003.png" in str(ei.value)


@pytest.mark.req("FR-006-12")
def test_a_tampered_frame_list_digest_is_invalid(tmp_path):
    seq = make(tmp_path, 3)
    m = copy.deepcopy(seq.manifest)
    m["source_frames_sha256"] = "0" * 64
    with pytest.raises(FramesInvalid):
        check(seq, m)


@pytest.mark.req("FR-006-12")
def test_a_tampered_per_frame_digest_names_that_frame(tmp_path):
    seq = make(tmp_path, 3)
    m = copy.deepcopy(seq.manifest)
    m["frame_sha256"][1] = "f" * 64
    with pytest.raises(FramesInvalid) as ei:
        check(seq, m)
    assert "frame_00001.png" in str(ei.value)


@pytest.mark.req("FR-006-12")
def test_a_frame_changed_after_the_manifest_was_written_is_invalid(tmp_path):
    seq = make(tmp_path, 3)
    seq.frames[0].write_bytes(
        kit.png_bytes(1920, 1080, rgb=(200, 100, 50), stripe=1)
    )  # valid PNG, other pixels, manifest not refreshed
    with pytest.raises(FramesInvalid):
        check(seq)


@pytest.mark.req("FR-006-12")
def test_manifest_values_that_disagree_with_the_frames_are_invalid(tmp_path):
    seq = make(tmp_path, 3)
    for key, bad in (("width", 1921), ("height", 1081), ("bit_depth", 16)):
        m = copy.deepcopy(seq.manifest)
        m[key] = bad
        with pytest.raises(FramesInvalid):
            check(seq, m)


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-13: names and paths
# ---------------------------------------------------------------------------------------------------------------------
VALID_NAMES = ["a", "0", "c2-breach-replay", "x" * 64, "a-b-c", "0a", "9-"]
INVALID_NAMES = [
    "", "x" * 65, "Upper", "clip name", "clip_name", "clip.mp4", "a/b", "a\\b", "..", "../x", "x/../y", "/abs", "C:\\x",
    "-leading-hyphen", "clíp", "клип", "clip\n", "clip\x00", "clip\u202e", "a b", "clip;rm", "$(x)", "`x`", "*", "a" * 64 + "b",
]  # fmt: skip


@pytest.mark.req("FR-006-13")
@pytest.mark.parametrize("name", VALID_NAMES)
def test_valid_clip_names_are_accepted(name):
    validate_clip_name(name)


@pytest.mark.req("FR-006-13")
@pytest.mark.parametrize("name", INVALID_NAMES, ids=[repr(n)[:40] for n in INVALID_NAMES])
def test_invalid_clip_names_give_name_invalid(name):
    with pytest.raises(NameInvalid) as ei:
        validate_clip_name(name)
    assert ei.value.error_class == "name-invalid" and str(ei.value).startswith("name-invalid: ")


@pytest.mark.req("FR-006-13")
@pytest.mark.parametrize("name", ["Upper", "a/b", "x" * 65, "..", "-x"])
def test_an_invalid_clip_name_in_the_manifest_is_rejected_before_any_frame_is_read(tmp_path, name):
    seq = make(tmp_path, 2)
    m = copy.deepcopy(seq.manifest)
    m["clip"] = name
    for p in seq.frames:
        p.unlink()  # nothing to read: a name check that comes first still reports name-invalid
    with pytest.raises(NameInvalid):
        check(seq, m)


@pytest.mark.req("FR-006-13")
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("directory", "../outside"),
        ("directory", "frames/../../outside"),
        ("directory", "/etc"),
        ("directory", "C:\\Windows"),
        ("directory", "..\\outside"),
        ("frame_pattern", "../frame_%05d.png"),
        ("frame_pattern", "sub/frame_%05d.png"),
        ("frame_pattern", "..\\frame_%05d.png"),
        ("frame_pattern", "/tmp/frame_%05d.png"),
    ],
)
def test_a_frame_path_that_leaves_the_input_folder_is_name_invalid(tmp_path, key, value):
    seq = make(tmp_path, 2)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "frame_00000.png").write_bytes(seq.frames[0].read_bytes())
    (outside / "frame_00001.png").write_bytes(seq.frames[1].read_bytes())
    m = copy.deepcopy(seq.manifest)
    m[key] = value
    with pytest.raises(NameInvalid):
        check(seq, m)


@pytest.mark.req("FR-006-13")
def test_the_stage_refuses_a_hostile_clip_name_before_any_encode_and_writes_nothing_outside(tmp_path, monkeypatch):
    from pitstudio_studio.media.encode import run

    ctx = kit.prepare(tmp_path, monkeypatch)
    ctx.job["params"]["clip"] = "../evil"
    ctx.seq.manifest["clip"] = "../evil"
    ctx.seq.write_manifest()
    ctx.job["inputs"][0]["sha256"] = kit.file_sha256(ctx.seq.manifest_path)
    with pytest.raises(NameInvalid):
        run(ctx.job, runner=ctx.ff, clock=ctx.clock, env=ctx.env, driver_version=ctx.driver)
    assert ctx.ff.n_encodes() == 0
    assert not (tmp_path / "evil.av1.mp4").exists() and not list(ctx.out.glob("*.mp4"))


@pytest.mark.req("FR-006-12")
def test_the_stage_refuses_corrupt_frames_before_any_encode(tmp_path, monkeypatch):
    ctx = kit.prepare(tmp_path, monkeypatch)
    damage(ctx.seq.frames[1], "crc")
    refresh(ctx.seq)
    ctx.job["inputs"][0]["sha256"] = kit.file_sha256(ctx.seq.manifest_path)
    with pytest.raises(FramesInvalid) as ei:
        ctx.run()
    assert "frame_00001.png" in str(ei.value)
    assert ctx.ff.n_encodes() == 0 and "vmaf" not in ctx.ff.kinds() and not list(ctx.out.glob("*.mp4"))


@pytest.mark.req("FR-006-13")
def test_ffmpeg_is_called_with_argument_lists_and_never_through_a_shell(tmp_path, monkeypatch):
    from pitstudio_studio.media.encode import run

    ctx = kit.prepare(tmp_path, monkeypatch)
    seen: list[tuple[object, object]] = []

    def spy(argv, *args, **kw):
        seen.append((argv, kw.get("shell")))
        return ctx.ff(argv, **{k: v for k, v in kw.items() if k != "shell"})

    monkeypatch.setattr(subprocess, "run", spy)
    run(
        ctx.job, runner=None, clock=ctx.clock, env=ctx.env, driver_version=ctx.driver
    )  # the default runner is subprocess.run
    assert seen, "the default runner must be `subprocess.run`, looked up at call time"
    for argv, shell in seen:
        assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
        assert not shell  # shell=False or absent
    assert json.dumps([a for a, _ in seen])  # serialisable: nothing but strings
