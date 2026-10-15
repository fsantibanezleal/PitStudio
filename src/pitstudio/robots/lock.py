# SPDX-License-Identifier: Apache-2.0
"""Lock check of ``studio/isaaclab/uv.lock`` and the performance marker derived from it (FR-014-01, FR-014-04).

Standard library only. The lock is the single source of the versions every IL stage manifest reports, and the marker
``performance: public`` or ``local-only`` follows from the package names it holds (NVIDIA SLA 8.9).
"""

from __future__ import annotations

import ast
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

__all__ = [
    "LockInfo",
    "check_isaaclab_lock",
    "forbidden_imports",
    "lock_versions",
    "parse_lock",
    "performance_marker",
]

TAG = "v3.0.0-EA"
COMMIT_PREFIX = "ae37b02"
CUDA_INDEX_SUFFIX = "/whl/cu128"
RESTRICTED_EXACT = frozenset({"ovrtx", "ovstage", "ovphysx"})
RESTRICTED_PREFIXES = ("isaacsim", "omni")
KIT_TOP_LEVEL = frozenset({"isaacsim", "omni", "carb", "ovrtx", "ovstage", "ovphysx"})
VERSION_KEYS = {
    "isaaclab": "isaaclab",
    "isaaclab_newton": "isaaclab-newton",
    "isaaclab_tasks": "isaaclab-tasks",
    "isaaclab_rl": "isaaclab-rl",
    "torch": "torch",
    "torchvision": "torchvision",
    "warp_lang": "warp-lang",
    "newton": "newton",
    "mujoco": "mujoco",
    "mujoco_warp": "mujoco-warp",
    "rsl_rl_lib": "rsl-rl-lib",
}
# (package, exact version or None, version prefix or None, registry URL suffix or None)
_PINS: tuple[tuple[str, str | None, str | None, str | None], ...] = (
    ("torch", "2.11.0+cu128", None, CUDA_INDEX_SUFFIX),
    ("torchvision", "0.26.0+cu128", None, CUDA_INDEX_SUFFIX),
    ("warp-lang", "1.16.0", None, None),
    ("newton", "1.5.2", None, None),
    ("mujoco", None, "3.11.", None),
    ("mujoco-warp", None, "3.11.", None),
    ("rsl-rl-lib", "5.4.1", None, None),
)


@dataclass(frozen=True)
class LockInfo:
    packages: dict[str, list[dict[str, Any]]]


def parse_lock(source: Path | str) -> LockInfo:
    """Parse a uv.lock file (a Path) or its text (a str)."""
    if isinstance(source, Path):
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"cannot read the lock file {source.name}: {exc.strerror or exc}") from exc
        label = source.name
    else:
        text, label = source, "lock text"
    if not text.strip():
        raise ValueError(f"{label} is empty")
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{label} is not valid TOML: {exc}") from exc
    entries = raw.get("package")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{label} has no [[package]] table")
    packages: dict[str, list[dict[str, Any]]] = {}
    for i, entry in enumerate(entries):
        name = entry.get("name") if isinstance(entry, dict) else None
        version = entry.get("version") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not name:
            raise ValueError(f"{label}: package #{i} has no name")
        if not isinstance(version, str) or not version:
            raise ValueError(f"{label}: package {name!r} has no version")
        source_table = entry.get("source")
        packages.setdefault(name, []).append(
            {"version": version, "source": source_table if isinstance(source_table, dict) else {}}
        )
    return LockInfo(packages)


def _restricted(name: str) -> bool:
    low = name.lower()
    return low.startswith(RESTRICTED_PREFIXES) or low in RESTRICTED_EXACT


def performance_marker(lock: LockInfo) -> str:
    """local-only when the lock holds a package covered by SLA 8.9, else public."""
    return "local-only" if any(_restricted(n) for n in lock.packages) else "public"


def lock_versions(lock: LockInfo) -> dict[str, str]:
    """The versions the manifests report, read from the lock (the first entry of each package)."""
    out = {}
    for key, name in VERSION_KEYS.items():
        entries = lock.packages.get(name)
        if not entries:
            raise ValueError(f"the lock holds no package {name!r}")
        out[key] = entries[0]["version"]
    return out


def _problem(rule: str, package: str, message: str) -> dict[str, str]:
    return {"rule": rule, "package": package, "message": message}


def check_isaaclab_lock(lock: LockInfo) -> list[dict[str, str]]:
    """Problems of the lock against FR-014-01 and FR-014-04, sorted by (package, rule); empty when it conforms."""
    problems: list[dict[str, str]] = []
    commits: dict[str, str] = {}
    for name, entries in lock.packages.items():
        if name.lower().startswith("isaacsim"):
            problems.append(_problem("FR-014-04", name, "an isaacsim package is in the lock: Isaac Sim is not installed"))
        if not name.startswith("isaaclab"):
            continue
        for entry in entries:
            url = entry["source"].get("git")
            if not isinstance(url, str):
                problems.append(_problem("FR-014-01", name, f"{name} must come from the git tag {TAG}, not an index"))
                continue
            parts = urlsplit(url)
            tag = parse_qs(parts.query).get("tag", [""])[0]
            if tag != TAG:
                problems.append(_problem("FR-014-01", name, f"{name} is at tag {tag!r}, expected {TAG}"))
            elif not parts.fragment.startswith(COMMIT_PREFIX):
                problems.append(_problem("FR-014-01", name, f"{name} is at commit {parts.fragment[:12]!r}, expected {COMMIT_PREFIX}*"))
            else:
                commits[name] = parts.fragment
    if len(set(commits.values())) > 1:
        common = max(set(commits.values()), key=list(commits.values()).count)
        for name, commit in commits.items():
            if commit != common:
                problems.append(_problem("FR-014-01", name, f"{name} is at commit {commit[:12]}, the others at {common[:12]}"))
    for name, exact, prefix, index_suffix in _PINS:
        entries = lock.packages.get(name)
        if not entries:
            problems.append(_problem("FR-014-01", name, f"{name} is missing from the lock"))
            continue
        for entry in entries:
            version = entry["version"]
            if exact is not None and version != exact:
                problems.append(_problem("FR-014-01", name, f"{name} is {version}, expected {exact}"))
            if prefix is not None and not version.startswith(prefix):
                problems.append(_problem("FR-014-01", name, f"{name} is {version}, expected {prefix}x"))
            if index_suffix is not None:
                registry = entry["source"].get("registry")
                if not isinstance(registry, str) or not registry.rstrip("/").endswith(index_suffix):
                    problems.append(_problem("FR-014-01", name, f"{name} must come from an index ending in {index_suffix}"))
    return sorted(problems, key=lambda p: (p["package"], p["rule"], p["message"]))


def forbidden_imports(root: Path | str) -> list[tuple[str, str]]:
    """(relative POSIX path, module) of every import of an Isaac Sim or Kit module under root (ast, nested imports too)."""
    base = Path(root)
    if not base.is_dir():
        raise ValueError(f"root is not a directory: {base.name}")
    found: list[tuple[str, str]] = []
    for path in sorted(base.rglob("*.py")):
        rel = path.relative_to(base).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
            raise ValueError(f"cannot parse {rel}: {exc}") from exc
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            found.extend((rel, n) for n in names if re.split(r"\.", n, maxsplit=1)[0] in KIT_TOP_LEVEL)
    return found
