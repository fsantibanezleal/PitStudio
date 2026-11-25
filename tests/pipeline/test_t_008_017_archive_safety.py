# ruff: noqa: E501, PT018
"""T-008-017: archive extraction by patterns under a size cap; hostile members reject the whole archive with nothing written.

Requirements: FR-008-18, FR-008-19, P-008-05.

Spec: specs/008-data-pipeline/spec.md FR-008-18 (only members matching `files[].extract`; list and check declared sizes
first; stop at the cap = `uncompressed_bytes`, else 20 x the compressed size; zip, tar, 7z), FR-008-19 (absolute path, drive
letter, `..` component, resolution outside the root, symlink, hardlink, device, or a total above the cap: reject the whole
archive with `UnsafeArchive` naming the member, leave nothing behind), P-008-05.

Oracle: hand-built archives written with the standard library (`zipfile`, `tarfile`; for 7z `py7zr`, the reference
writer): safe members with known contents, hostile members listed one by one (names, member types), a deflated block of
zeros as the bomb (ratio far above 20), and cap boundaries computed by hand (1,000 + 500 = 1,500 declared bytes).

Expected API of the implementation:
- `pitstudio_pipeline.archive.extract_archive(archive, dest, *, extract, uncompressed_bytes=None) -> list[str]`:
  `archive` is a path to a zip, tar (also tar.gz) or 7z file (type from content, not from the name); `dest` the extraction
  root; `extract` a list of glob patterns (`fnmatch` semantics over the POSIX member path, `*` does not cross `/`);
  returns the sorted POSIX relative paths written under `dest`. The member path is kept under `dest`. Nothing is written
  unless every member of the archive (matching or not) is safe; on rejection `dest` holds no file and no temporary
  sibling file remains.
- `pitstudio_pipeline.errors.UnsafeArchive(Exception)` with `.member` (the offending member name, also in `str(exc)`).
- Through `run_download`: a verified file of kind `archive` with `extract` is unpacked into `interim/<id>/`; an unsafe
  archive puts `UnsafeArchive` in `result.errors[id]` and leaves `interim/<id>/` without files.
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import _p008_kit as kit
import pytest
from pitstudio_pipeline.archive import extract_archive
from pitstudio_pipeline.errors import UnsafeArchive

# isort: split
from hypothesis import given, settings
from hypothesis import strategies as st

PATTERNS = ["data/*.csv", "top.csv"]
SAFE_FILES = {
    "data/a.csv": b"a,b\n1,2\n",
    "data/b.csv": b"c,d\n3,4\n",
    "top.csv": b"t\n9\n",
    "docs/readme.txt": b"not extracted",
    "data/skip.bin": b"\x00\x01\x02",
}
EXTRACTED = {"data/a.csv", "data/b.csv", "top.csv"}  # the members that match PATTERNS


def make_zip(path: Path, members: list[tuple[str, str, bytes]], compression: int = zipfile.ZIP_STORED) -> Path:
    with zipfile.ZipFile(path, "w", compression) as z:
        for name, kind, data in members:
            zi = zipfile.ZipInfo(name)
            zi.compress_type = compression
            if kind == "symlink":
                zi.external_attr = 0o120777 << 16
                z.writestr(zi, "data/a.csv")
            else:
                z.writestr(zi, data)
    return path


def make_tar(path: Path, members: list[tuple[str, str, bytes]], mode: str = "w") -> Path:
    with tarfile.open(path, mode) as t:  # type: ignore[call-overload]
        for name, kind, data in members:
            ti = tarfile.TarInfo(name)
            if kind == "file":
                ti.size = len(data)
                t.addfile(ti, io.BytesIO(data))
            elif kind == "symlink":
                ti.type, ti.linkname = tarfile.SYMTYPE, "data/a.csv"
                t.addfile(ti)
            elif kind == "hardlink":
                ti.type, ti.linkname = tarfile.LNKTYPE, "data/a.csv"
                t.addfile(ti)
            elif kind == "device":
                ti.type, ti.devmajor, ti.devminor = tarfile.CHRTYPE, 1, 3
                t.addfile(ti)
            elif kind == "blockdev":
                ti.type, ti.devmajor, ti.devminor = tarfile.BLKTYPE, 7, 0
                t.addfile(ti)
            elif kind == "fifo":
                ti.type = tarfile.FIFOTYPE
                t.addfile(ti)
            else:
                raise AssertionError(kind)
    return path


def safe_members() -> list[tuple[str, str, bytes]]:
    return [(n, "file", d) for n, d in SAFE_FILES.items()]


def written(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for p in kit.files_under(root)]


# ------------------------------------------------------------------------------------------------ FR-008-18
@pytest.mark.req("FR-008-18")
@pytest.mark.parametrize("fmt", ["zip", "tar", "tar.gz"])
def test_only_matching_members_are_extracted_under_the_root(fmt: str, tmp_path: Path) -> None:
    arc = tmp_path / ("arc." + fmt)
    {"zip": make_zip, "tar": make_tar, "tar.gz": lambda p, m: make_tar(p, m, "w:gz")}[fmt](arc, safe_members())
    dest = tmp_path / "out"
    got = extract_archive(arc, dest, extract=PATTERNS)
    assert sorted(got) == sorted(EXTRACTED)
    assert written(dest) == sorted(EXTRACTED)
    for name in EXTRACTED:
        assert (dest / name).read_bytes() == SAFE_FILES[name]


@pytest.mark.req("FR-008-18")
def test_seven_zip_archive_is_supported(tmp_path: Path) -> None:
    import py7zr as sz  # reference writer for the 7z fixture; locked into the pipeline env by T-008-002

    arc = tmp_path / "arc.7z"
    with sz.SevenZipFile(arc, "w") as z:
        for name, data in SAFE_FILES.items():
            z.writestr(data, name)
    got = extract_archive(arc, tmp_path / "out", extract=PATTERNS)
    assert sorted(got) == sorted(EXTRACTED)
    assert (tmp_path / "out" / "data" / "a.csv").read_bytes() == SAFE_FILES["data/a.csv"]


@pytest.mark.req("FR-008-18")
def test_declared_size_cap_is_inclusive_at_the_declared_total(tmp_path: Path) -> None:
    members = [("data/a.csv", "file", b"x" * 1000), ("data/b.csv", "file", b"y" * 500)]
    arc = make_zip(tmp_path / "a.zip", members)
    assert sorted(extract_archive(arc, tmp_path / "ok", extract=["data/*.csv"], uncompressed_bytes=1500)) == [
        "data/a.csv",
        "data/b.csv",
    ]
    with pytest.raises(UnsafeArchive):
        extract_archive(arc, tmp_path / "bad", extract=["data/*.csv"], uncompressed_bytes=1499)
    assert written(tmp_path / "bad") == []


@pytest.mark.req("FR-008-18")
@pytest.mark.parametrize("fmt", ["zip", "tar.gz"])
def test_undeclared_cap_is_twenty_times_the_compressed_size(fmt: str, tmp_path: Path) -> None:
    bomb = [("data/zeros.csv", "file", b"\0" * (4 << 20))]  # 4 MiB of zeros deflate to a few KiB: ratio >> 20
    arc = tmp_path / ("bomb." + fmt)
    if fmt == "zip":
        make_zip(arc, bomb, zipfile.ZIP_DEFLATED)
    else:
        make_tar(arc, bomb, "w:gz")
    assert arc.stat().st_size * 20 < 4 << 20
    with pytest.raises(UnsafeArchive) as info:
        extract_archive(arc, tmp_path / "out", extract=["data/*.csv"])
    assert info.value.member == "data/zeros.csv" and "data/zeros.csv" in str(info.value)
    assert written(tmp_path / "out") == []
    # a declared cap that admits the content makes the same archive acceptable
    got = extract_archive(arc, tmp_path / "out2", extract=["data/*.csv"], uncompressed_bytes=4 << 20)
    assert got == ["data/zeros.csv"]


@pytest.mark.req("FR-008-18")
def test_seven_zip_bomb_is_rejected(tmp_path: Path) -> None:
    import py7zr as sz

    arc = tmp_path / "bomb.7z"
    with sz.SevenZipFile(arc, "w") as z:
        z.writestr(b"\0" * (8 << 20), "data/zeros.csv")
    with pytest.raises(UnsafeArchive):
        extract_archive(arc, tmp_path / "out", extract=["data/*.csv"])
    assert written(tmp_path / "out") == []


@pytest.mark.req("FR-008-18")
def test_ratio_one_content_passes_the_default_cap(tmp_path: Path) -> None:
    members = [("data/rand.csv", "file", kit.payload(50_000, 1))]
    arc = make_zip(tmp_path / "r.zip", members)
    assert extract_archive(arc, tmp_path / "out", extract=["data/*.csv"]) == ["data/rand.csv"]


@pytest.mark.req("FR-008-18")
def test_garbage_that_is_no_archive_is_rejected_without_writing(tmp_path: Path) -> None:
    arc = tmp_path / "junk.bin"
    arc.write_bytes(kit.payload(2048, 2))
    with pytest.raises(Exception):  # noqa: B017, PT011  (the error class for a non-archive is not fixed by the spec)
        extract_archive(arc, tmp_path / "out", extract=["*"])
    assert written(tmp_path / "out") == []


# ------------------------------------------------------------------------------------------------ FR-008-19
HOSTILE_NAMES = {
    "absolute": "/abs.csv",
    "drive-slash": "C:/abs.csv",
    "drive-relative": "C:abs.csv",
    "dotdot": "../esc.csv",
    "nested-dotdot": "data/../../esc.csv",
    "deep-dotdot": "data/../../../esc.csv",
    "backslash-dotdot": "..\\esc.csv",
    "only-dotdot": "..",
}


@pytest.mark.req("FR-008-19")
@pytest.mark.parametrize("fmt", ["zip", "tar"])
@pytest.mark.parametrize("name", list(HOSTILE_NAMES.values()), ids=list(HOSTILE_NAMES))
def test_hostile_member_names_reject_the_whole_archive_and_leave_nothing(fmt: str, name: str, tmp_path: Path) -> None:
    arc = tmp_path / ("h." + fmt)
    members = [*safe_members(), (name, "file", b"pwned")]
    (make_zip if fmt == "zip" else make_tar)(arc, members)
    before = written(tmp_path)
    with pytest.raises(UnsafeArchive) as info:
        extract_archive(arc, tmp_path / "out", extract=PATTERNS)
    assert info.value.member is not None and info.value.member.replace("\\", "/") in {name, name.replace("\\", "/")}
    assert written(tmp_path / "out") == [], "safe members must not be left behind either"
    assert written(tmp_path) == before, "no file anywhere else (no escape, no temporary leftovers)"
    assert not (tmp_path.parent / "esc.csv").exists() and not (tmp_path / "esc.csv").exists()


@pytest.mark.req("FR-008-19")
@pytest.mark.parametrize(
    ("kind", "fmt"),
    [
        ("symlink", "zip"),
        ("symlink", "tar"),
        ("hardlink", "tar"),
        ("device", "tar"),
        ("blockdev", "tar"),
        ("fifo", "tar"),
    ],
)
def test_links_and_devices_reject_the_archive(kind: str, fmt: str, tmp_path: Path) -> None:
    arc = tmp_path / ("h." + fmt)
    members = [*safe_members(), ("data/link.csv", kind, b"")]
    (make_zip if fmt == "zip" else make_tar)(arc, members)
    with pytest.raises(UnsafeArchive) as info:
        extract_archive(arc, tmp_path / "out", extract=PATTERNS)
    assert info.value.member == "data/link.csv" and "data/link.csv" in str(info.value)
    assert written(tmp_path / "out") == []


@pytest.mark.req("FR-008-19")
def test_a_hostile_member_that_matches_no_pattern_still_rejects_the_archive(tmp_path: Path) -> None:
    arc = make_tar(tmp_path / "h.tar", [*safe_members(), ("docs/evil.lnk", "symlink", b"")])
    with pytest.raises(UnsafeArchive) as info:
        extract_archive(arc, tmp_path / "out", extract=["data/*.csv"])
    assert info.value.member == "docs/evil.lnk"
    assert written(tmp_path / "out") == []


@pytest.mark.req("FR-008-19")
def test_a_member_total_above_the_cap_rejects_before_writing(tmp_path: Path) -> None:
    arc = make_tar(tmp_path / "big.tar", [("data/a.csv", "file", b"x" * 600), ("data/b.csv", "file", b"y" * 600)])
    with pytest.raises(UnsafeArchive):
        extract_archive(arc, tmp_path / "out", extract=["data/*.csv"], uncompressed_bytes=1000)
    assert written(tmp_path / "out") == []


# ------------------------------------------------------------------------------------------------ P-008-05
MEMBER_POOL = st.sampled_from(
    [
        ("data/a.csv", "file"),
        ("data/b.csv", "file"),
        ("top.csv", "file"),
        ("docs/readme.txt", "file"),
        ("data/skip.bin", "file"),
    ]
)
HOSTILE_POOL = st.one_of(
    st.sampled_from([(n, "file") for n in HOSTILE_NAMES.values()]),
    st.sampled_from([("data/ln.csv", "symlink")]),
)


@pytest.mark.req("P-008-05")
@settings(max_examples=80, deadline=None)
@given(
    safe=st.lists(MEMBER_POOL, unique=True, max_size=5),
    hostile=st.lists(HOSTILE_POOL, unique=True, max_size=2),
    fmt=st.sampled_from(["zip", "tar"]),
    seed=st.integers(0, 3),
)
def test_every_write_stays_under_the_root_and_any_hostile_member_means_nothing_is_written(
    safe, hostile, fmt, seed, tmp_path_factory
) -> None:
    tmp = tmp_path_factory.mktemp("arc")
    members = [(n, k, SAFE_FILES[n]) for n, k in safe] + [(n, k, b"pwned") for n, k in hostile]
    rotated = members[seed % len(members) :] + members[: seed % len(members)] if members else members
    arc = (make_zip if fmt == "zip" else make_tar)(tmp / f"p.{fmt}", rotated)
    before = written(tmp)
    if hostile:
        with pytest.raises(UnsafeArchive):
            extract_archive(arc, tmp / "out", extract=PATTERNS)
        assert written(tmp) == before and written(tmp / "out") == []
    else:
        got = extract_archive(arc, tmp / "out", extract=PATTERNS)
        expected = sorted(n for n, _ in safe if n in EXTRACTED)
        assert sorted(got) == expected
        assert written(tmp / "out") == expected
        assert written(tmp) == sorted(before + [f"out/{n}" for n in expected])


# ------------------------------------------------------------------------------------------------ through the stage
@pytest.mark.req("FR-008-18")
def test_stage_extracts_a_verified_archive_into_interim(tmp_path: Path) -> None:
    arc = make_zip(tmp_path / "src.zip", safe_members())
    data = arc.read_bytes()
    url = "https://example.org/d/pack.zip"
    f = kit.file_rec(url, data, kind="archive", extract=PATTERNS, uncompressed_bytes=1 << 20)
    result = kit.run(tmp_path, [kit.entry("pk", [f])], kit.Net({url: data}))
    assert result.exit_status == 0, result.errors
    assert written(tmp_path / "data" / "interim" / "pk") == sorted(EXTRACTED)


@pytest.mark.req("FR-008-19")
def test_stage_rejects_an_unsafe_archive_and_extracts_nothing(tmp_path: Path) -> None:
    arc = make_zip(tmp_path / "src.zip", [*safe_members(), ("../esc.csv", "file", b"pwned")])
    data = arc.read_bytes()
    url = "https://example.org/d/pack.zip"
    f = kit.file_rec(url, data, kind="archive", extract=PATTERNS, uncompressed_bytes=1 << 20)
    result = kit.run(tmp_path, [kit.entry("pk", [f])], kit.Net({url: data}))
    assert isinstance(result.errors["pk"], UnsafeArchive) and result.exit_status != 0
    assert written(tmp_path / "data" / "interim" / "pk") == []
    assert not (tmp_path / "data" / "esc.csv").exists() and not (tmp_path / "esc.csv").exists()
