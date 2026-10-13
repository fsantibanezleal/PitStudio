"""Licence and honesty guards of the reason lane (FR-015-06, FR-015-39, FR-015-42).

- No model weight or conversion (`.gguf`, `.safetensors`, `.pt`, `.pth`, `.bin`, a Hugging Face cache folder) is
  tracked in git, listed for release upload or copied into the Pages artefact; an artefact of licence class
  `reference-only` never appears in a publish list.
- A stage `s05_*` to `s30_*` never takes an artefact produced by the Cosmos tool (the `st59*` stages) as input.
- No metric produced by the Cosmos tool is a headline KPI.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
import tarfile
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

WEIGHT_EXTENSIONS = frozenset({".gguf", ".safetensors", ".pt", ".pth", ".bin"})
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz")
_HF_MODEL_FOLDER = re.compile(r"models--.+--.+")


@dataclass(frozen=True)
class Violation:
    """One offence: the offending path (or `archive!member`, or `<run>:<stage>`) and the rule it breaks."""

    path: str
    rule: str


def _path_violations(path: str) -> list[Violation]:
    parts = path.split("/")
    found = []
    if posixpath.splitext(parts[-1])[1].lower() in WEIGHT_EXTENSIONS:
        found.append(Violation(path, "weight-extension"))
    cache = any(_HF_MODEL_FOLDER.fullmatch(p) for p in parts) or any(
        a == ".cache" and b == "huggingface" for a, b in pairwise(parts)
    )
    if cache:
        found.append(Violation(path, "hf-cache-folder"))
    return found


def scan_tracked_files(paths: Iterable[str]) -> list[Violation]:
    """Violations among repository-relative POSIX paths."""
    return [v for p in paths for v in _path_violations(p)]


def scan_publish_list(entries: Iterable[Any]) -> list[Violation]:
    """Violations in a release-asset upload list: paths or `{"path", "licence_class"}` entries."""
    found: list[Violation] = []
    for entry in entries:
        if isinstance(entry, str):
            path, cls = entry, None
        elif isinstance(entry, Mapping) and isinstance(entry.get("path"), str):
            path, cls = entry["path"], entry.get("licence_class")
        else:
            raise ValueError(f"malformed publish-list entry: {entry!r}")
        found.extend(_path_violations(path))
        if cls == "reference-only":
            found.append(Violation(path, "reference-only"))
    return found


def _archive_members(path: Path) -> list[str]:
    name = path.name.lower()
    try:
        if name.endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                return z.namelist()
        with tarfile.open(path) as t:
            return t.getnames()
    except zipfile.BadZipFile, tarfile.TarError, EOFError, OSError:
        return []


def scan_directory(root: Path) -> list[Violation]:
    """The same rules over every file below `root` (the Pages artefact) and over the members of its archives."""
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")
    found: list[Violation] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        found.extend(_path_violations(rel))
        if path.name.lower().endswith(ARCHIVE_SUFFIXES):
            found.extend(
                Violation(f"{rel}!{member}", "archive-member")
                for member in _archive_members(path)
                if _path_violations(member)
            )
    return found


def _git_ls_files(repo_root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"], capture_output=True, check=True, timeout=120
    ).stdout
    return [p for p in out.decode("utf-8", errors="replace").split("\0") if p]


def check_repository(repo_root: Path, *, ls_files: Callable[[Path], Sequence[str]] | None = None) -> list[Violation]:
    """`scan_tracked_files` over the tracked files of the repository (`git ls-files`, or the injected listing)."""
    return scan_tracked_files((ls_files or _git_ls_files)(Path(repo_root)))
