# ruff: noqa: E501
"""T-006-015: frame-list digest `source_frames_sha256`: invariant to renaming, sensitive to a pixel and to frame order.

Requirements: P-006-06.

Spec: specs/006-media-telemetry/spec.md P-006-06 (renaming frame files without changing content or order leaves
`source_frames_sha256` unchanged; changing one pixel of one frame or swapping two frames changes it) and DC-006-01 (the schema
describes `source_frames_sha256` as the SHA-256 of the ordered list of per-frame SHA-256 digests); plan.md test strategy
("SHA-256 of per-frame digests on a hand-built 3-frame fixture").

Oracle: `hashlib.sha256` called directly in the test. The serialisation of "the ordered list of per-frame SHA-256 digests" is not
fixed by the spec; these tests fix it as the raw 32-byte per-frame digests concatenated in frame order (see the report).

Expected API (module `pitstudio_studio.media.frames`):
    frame_digests(paths: Sequence[Path]) -> list[str]      lowercase hex SHA-256 of each file's bytes, in the order given
    source_frames_sha256(paths: Sequence[Path]) -> str     SHA-256 (lowercase hex) of b"".join(bytes.fromhex(d) for d in frame_digests(paths));
                                                           raises ValueError for an empty sequence
    digest_of_digests(digests: Sequence[str]) -> str       the same final step from per-frame hex digests (validated: 64 lowercase hex
                                                           characters each, else ValueError)
The functions hash file bytes only; they do not decode the frames.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit  # noqa: F401
from pitstudio_studio.media.frames import digest_of_digests, frame_digests, source_frames_sha256

SETTINGS = settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def write(folder: Path, names: list[str], blobs: list[bytes]) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for n, b in zip(names, blobs, strict=True):
        (folder / n).write_bytes(b)
        out.append(folder / n)
    return out


def oracle(blobs: list[bytes]) -> str:
    return hashlib.sha256(b"".join(hashlib.sha256(b).digest() for b in blobs)).hexdigest()


BLOBS = [b"frame zero", b"frame one", b"frame two"]


@pytest.mark.req("P-006-06")
def test_hand_built_three_frame_fixture(tmp_path):
    paths = write(tmp_path, ["frame_00000.png", "frame_00001.png", "frame_00002.png"], BLOBS)
    per = [hashlib.sha256(b).hexdigest() for b in BLOBS]
    assert frame_digests(paths) == per
    assert source_frames_sha256(paths) == oracle(BLOBS)
    assert digest_of_digests(per) == oracle(BLOBS)
    assert len(source_frames_sha256(paths)) == 64


@pytest.mark.req("P-006-06")
def test_renaming_the_files_leaves_the_digest_unchanged(tmp_path):
    a = write(tmp_path / "a", ["frame_00000.png", "frame_00001.png", "frame_00002.png"], BLOBS)
    b = write(
        tmp_path / "b" / "deeper", ["x.png", "y.png", "z.png"], BLOBS
    )  # other names, other folder, same content and order
    assert source_frames_sha256(a) == source_frames_sha256(b)


@pytest.mark.req("P-006-06")
def test_changing_one_byte_of_one_frame_changes_the_digest(tmp_path):
    base = source_frames_sha256(write(tmp_path / "a", ["0", "1", "2"], BLOBS))
    for k in range(3):
        blobs = list(BLOBS)
        blobs[k] = bytes([blobs[k][0] ^ 0x01]) + blobs[k][1:]  # one bit of the first byte of frame k
        assert source_frames_sha256(write(tmp_path / f"m{k}", ["0", "1", "2"], blobs)) != base


@pytest.mark.req("P-006-06")
def test_swapping_two_frames_changes_the_digest(tmp_path):
    base = source_frames_sha256(write(tmp_path / "a", ["0", "1", "2"], BLOBS))
    swapped = [BLOBS[1], BLOBS[0], BLOBS[2]]
    assert source_frames_sha256(write(tmp_path / "b", ["0", "1", "2"], swapped)) != base


@pytest.mark.req("P-006-06")
def test_a_missing_or_extra_frame_changes_the_digest(tmp_path):
    full = write(tmp_path / "a", ["0", "1", "2"], BLOBS)
    assert source_frames_sha256(full[:2]) != source_frames_sha256(full)
    assert source_frames_sha256([*full, full[0]]) != source_frames_sha256(full)


@pytest.mark.req("P-006-06")
@SETTINGS
@given(st.lists(st.binary(min_size=0, max_size=64), min_size=1, max_size=12, unique=True), st.data())
def test_property_rename_pixel_and_order(blobs, data):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        n = len(blobs)
        names = [f"f{k:03d}.png" for k in range(n)]
        base = source_frames_sha256(write(root / "a", names, blobs))
        assert base == oracle(blobs)
        # (1) renaming (any other names, same order) leaves it unchanged
        other = [f"{(n - k) * 7:05d}.dat" for k in range(n)]
        assert source_frames_sha256(write(root / "b", other, blobs)) == base
        # (2) changing one bit of one frame changes it (frames may be empty: then append a byte instead)
        k = data.draw(st.integers(0, n - 1))
        changed = list(blobs)
        changed[k] = (bytes([changed[k][0] ^ 0x80]) + changed[k][1:]) if changed[k] else b"\x00"
        if changed[k] not in blobs[:k] + blobs[k + 1 :]:
            assert source_frames_sha256(write(root / "c", names, changed)) != base
        # (3) swapping two different frames changes it
        if n >= 2:
            i, j = data.draw(st.permutations(range(n)).map(lambda p: (p[0], p[1])))
            swapped = list(blobs)
            swapped[i], swapped[j] = swapped[j], swapped[i]
            assert source_frames_sha256(write(root / "d", names, swapped)) != base  # unique=True: the frames differ


@pytest.mark.req("P-006-06")
def test_empty_sequence_and_malformed_digests_are_rejected():
    with pytest.raises(ValueError):  # noqa: PT011
        source_frames_sha256([])
    for bad in ("", "00", "G" * 64, "A" * 64, "0" * 63, "0" * 65):
        with pytest.raises(ValueError):  # noqa: PT011
            digest_of_digests([hashlib.sha256(b"x").hexdigest(), bad])
