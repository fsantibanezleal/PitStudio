# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""Provenance scan of the robot-learning task code (NFR-014-05).

Rules: every task-code file carries the Apache-2.0 SPDX header in its first 10 lines; no file holds an Isaac Lab licence
marker (copied source); no file or recipe references an NVIDIA or Isaac Lab asset. The marker and asset patterns are built
from fragments so that this file does not match its own rules.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["SCAN_ROOTS", "Violation", "scan_repository"]

SCAN_ROOTS = (
    "studio/isaaclab/src",
    "src/pitstudio/robots",
    "pipeline/src/pitstudio_pipeline/evaluate",
    "web/src/engines/robots",
    "studio/recipes",
)
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", ".venv"})
_CODE_SUFFIXES = (".py", ".ts", ".tsx")
_RECIPE_SUFFIXES = (".yaml", ".yml")
_SPDX = re.compile(r"^\s*(?:#|//)\s*SPDX-License-Identifier:\s*(\S.*?)\s*$")
_HEADER_LINES = 10


def _lit(*parts: str) -> str:
    return re.escape("".join(parts))


_COPIED = (
    re.compile(_lit("Isaac Lab ", "Project Developers")),
    re.compile(_lit("Copyright (c) ", "2022")),
    re.compile(_lit("BSD", "-3-Clause")),
)
_ASSET = (
    re.compile(_lit("isaaclab", "_assets")),
    re.compile(_lit("ISAAC", "_NUCLEUS_DIR")),
    re.compile(_lit("ISAACLAB", "_NUCLEUS_DIR")),
    re.compile(_lit("omniverse", "://")),
    re.compile(_lit("Isaac/", "IsaacLab")),
    re.compile(_lit("/NVID", "IA/")),
    re.compile(_lit("nvidia", ".com") + r"/\S*\.usd"),
)


@dataclass(frozen=True)
class Violation:
    path: str  # relative to the repository root, POSIX form
    line: int  # 1-based
    rule: str  # "spdx" | "copied_source" | "asset"
    text: str


def _files(root: Path) -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        out.extend(Path(dirpath) / name for name in filenames)
    return sorted(out)


def _scan_file(path: Path, rel: str, *, code: bool) -> list[Violation]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{rel} is not valid UTF-8: {exc.reason}") from exc
    lines = text.splitlines()
    found: list[Violation] = []
    if code:
        identifiers = [m.group(1) for line in lines[:_HEADER_LINES] if (m := _SPDX.match(line))]
        if "Apache-2.0" not in identifiers:
            found.append(Violation(rel, 1, "spdx", "no Apache-2.0 SPDX-License-Identifier in the first 10 lines"))
    for number, line in enumerate(lines, start=1):
        if code:
            for pattern in _COPIED:
                if pattern.search(line):
                    found.append(Violation(rel, number, "copied_source", line.strip()[:200]))
                    break
        for pattern in _ASSET:
            if pattern.search(line):
                found.append(Violation(rel, number, "asset", line.strip()[:200]))
                break
    return found


def scan_repository(repo_root: Path | str) -> list[Violation]:
    """Violations under the scan roots that exist, sorted by (path, line, rule)."""
    base = Path(repo_root)
    if not base.is_dir():
        raise ValueError(f"repo_root is not a directory: {base.name}")
    found: list[Violation] = []
    for root in SCAN_ROOTS:
        folder = base / root
        if not folder.is_dir():
            continue
        recipes = root == "studio/recipes"
        for path in _files(folder):
            suffixes = _RECIPE_SUFFIXES if recipes else _CODE_SUFFIXES
            if path.suffix not in suffixes:
                continue
            found.extend(_scan_file(path, path.relative_to(base).as_posix(), code=not recipes))
    return sorted(set(found), key=lambda v: (v.path, v.line, v.rule, v.text))
