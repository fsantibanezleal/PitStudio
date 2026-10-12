"""Safe extraction of zip, tar and 7z archives by member patterns, under a size cap (FR-008-18, FR-008-19).

Every member is listed and checked before a byte is written; the bytes written are counted against the cap while
extracting; nothing reaches the destination unless the whole archive is safe. Extraction goes to a staging folder next
to the destination and is moved into place only at the end, so a rejected archive leaves nothing behind.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import tarfile
import tempfile
import zipfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO

import py7zr

from pitstudio_pipeline.errors import UnsafeArchive

DEFAULT_RATIO = 20  # FR-008-18: the cap is 20 x the compressed size when the registry declares no uncompressed size
COPY_BLOCK = 1 << 20
_DRIVE = re.compile(r"^[A-Za-z]:")
_SEVEN_ZIP_MAGIC = b"7z\xbc\xaf\x27\x1c"


@dataclass(frozen=True)
class _Member:
    name: str  # as stored in the archive
    size: int  # declared uncompressed size
    is_dir: bool
    unsafe_type: str | None  # "symlink", "hardlink", "device", "fifo" ... or None for a regular file or directory


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`*` matches any run of characters except `/`, `?` one character except `/`; everything else is literal."""
    parts = ("[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char) for char in pattern)
    return re.compile("".join(parts))


def _posix(name: str) -> str:
    return name.replace("\\", "/")


def _check_name(name: str) -> None:
    """Reject absolute paths, drive letters, `..` components and control characters (FR-008-19)."""
    path = _posix(name)
    if not path or path.startswith("/") or _DRIVE.match(path):
        raise UnsafeArchive("absolute path or drive letter", name)
    if any(part == ".." for part in path.split("/")):
        raise UnsafeArchive("a `..` component", name)
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise UnsafeArchive("control character in the name", name)


def _zip_members(archive: Path) -> list[_Member]:
    members = []
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            mode = (info.external_attr >> 16) & 0xFFFF
            kind = stat.S_IFMT(mode) if mode else 0
            unsafe = {
                stat.S_IFLNK: "symlink",
                stat.S_IFCHR: "device",
                stat.S_IFBLK: "device",
                stat.S_IFIFO: "fifo",
            }.get(kind)
            members.append(_Member(info.filename, info.file_size, info.is_dir(), unsafe))
    return members


def _tar_members(archive: Path) -> list[_Member]:
    members = []
    with tarfile.open(archive, "r:*") as tf:
        for info in tf:
            unsafe = None
            if info.issym():
                unsafe = "symlink"
            elif info.islnk():
                unsafe = "hardlink"
            elif info.isdev():
                unsafe = "device"
            elif info.isfifo():
                unsafe = "fifo"
            elif not (info.isreg() or info.isdir()):
                unsafe = "special file"
            members.append(_Member(info.name, info.size, info.isdir(), unsafe))
    return members


def _seven_zip_members(archive: Path) -> list[_Member]:
    with py7zr.SevenZipFile(archive) as sz:
        return [
            _Member(i.filename, int(i.uncompressed or 0), bool(i.is_directory), "symlink" if i.is_symlink else None)
            for i in sz.list()
        ]


def _kind(archive: Path) -> str:
    with archive.open("rb") as handle:
        head = handle.read(8)
    if head.startswith(_SEVEN_ZIP_MAGIC):
        return "7z"
    if zipfile.is_zipfile(archive):
        return "zip"
    try:
        with tarfile.open(archive, "r:*"):
            return "tar"
    except tarfile.TarError, OSError, EOFError:
        raise UnsafeArchive("the file is not a zip, tar or 7z archive") from None


def _copy_counted(source: IO[bytes], target: Path, budget: list[int], name: str) -> None:
    """Copy in blocks; `budget[0]` is what the cap still allows. Stop with `UnsafeArchive` when it runs out."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        while block := source.read(COPY_BLOCK):
            budget[0] -= len(block)
            if budget[0] < 0:
                raise UnsafeArchive("the bytes written exceed the size cap", name)
            out.write(block)


def _extract_zip(archive: Path, staging: Path, names: Sequence[str], budget: list[int]) -> None:
    with zipfile.ZipFile(archive) as zf:
        for name in names:
            with zf.open(name) as source:
                _copy_counted(source, staging / _posix(name), budget, name)


def _extract_tar(archive: Path, staging: Path, names: Sequence[str], budget: list[int]) -> None:
    with tarfile.open(archive, "r:*") as tf:
        for name in names:
            source = tf.extractfile(name)
            if source is None:
                raise UnsafeArchive("not a regular file", name)
            with source:
                _copy_counted(source, staging / _posix(name), budget, name)


def _extract_seven_zip(archive: Path, staging: Path, names: Sequence[str], budget: list[int]) -> None:
    with py7zr.SevenZipFile(archive) as sz:
        sz.extract(path=staging, targets=list(names))
    written = sum(p.stat().st_size for p in staging.rglob("*") if p.is_file())
    if written > budget[0]:
        raise UnsafeArchive("the bytes written exceed the size cap")


def _walk(root: Path) -> Iterator[Path]:
    return (p for p in sorted(root.rglob("*")) if p.is_file())


def extract_archive(
    archive: Path | str,
    dest: Path | str,
    *,
    extract: Sequence[str],
    uncompressed_bytes: int | None = None,
) -> list[str]:
    """Extract the members of `archive` that match `extract` into `dest`; return their sorted POSIX relative paths.

    `archive` is a zip, a tar (also gzip or bzip2 compressed) or a 7z file, told apart by content. `extract` are glob
    patterns over the member path (`*` does not cross `/`). The cap on the extracted bytes is `uncompressed_bytes`, or
    20 times the compressed size when that is not declared. Any hostile member of the archive, matching or not (an
    absolute path, a drive letter, a `..` component, a symlink, hardlink or device), or a total above the cap rejects
    the whole archive with `UnsafeArchive` and writes nothing.
    """
    archive, dest = Path(archive), Path(dest)
    kind = _kind(archive)
    members = {"zip": _zip_members, "tar": _tar_members, "7z": _seven_zip_members}[kind](archive)
    for member in members:
        _check_name(member.name)
        if member.unsafe_type:
            raise UnsafeArchive(f"a {member.unsafe_type} is not allowed", member.name)
    cap = uncompressed_bytes if uncompressed_bytes is not None else DEFAULT_RATIO * archive.stat().st_size
    patterns = [glob_to_regex(p) for p in extract]
    chosen = [m for m in members if not m.is_dir and any(p.fullmatch(_posix(m.name)) for p in patterns)]
    running = 0
    for member in chosen:
        running += member.size
        if running > cap:
            raise UnsafeArchive(f"the declared sizes exceed the size cap of {cap} bytes", member.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{dest.name}.extracting-", dir=dest.parent))
    try:
        names = [m.name for m in chosen]
        budget = [cap]
        {"zip": _extract_zip, "tar": _extract_tar, "7z": _extract_seven_zip}[kind](archive, staging, names, budget)
        written: list[str] = []
        for path in _walk(staging):
            rel = PurePosixPath(path.relative_to(staging).as_posix())
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, target)
            written.append(str(rel))
        return sorted(written)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
