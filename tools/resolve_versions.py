"""Resolve the version and release date of every registry tool from the lock that names it (FR-019-09, FR-019-10).

Usage:  python tools/resolve_versions.py --root DIR [--json]
Output: one line "<tool id> <version> <release date|->" per tool, or a JSON object with --json.
Exit:   0 resolved, 1 a tool failed (its id is on stderr), 2 usage error or unreadable registry. Never a traceback.

A registry entry holds no literal version (data-model 001 section 4.2); it holds a reference that this tool resolves:
  {from_lock, package}              a `uv.lock` (TOML, `[[package]]` tables) or `web/pnpm-lock.yaml` (lockfile 9)
  {from_binary, release, sha256}    the record of `studio/external-binaries.yaml`
  {from_git_tag, repository}        the tag pinned in `[tool.uv.sources]` of the entry's environments
  {own: true}                       the first line of `VERSION`
A reference that cannot be resolved, or that differs from what the lock says, fails the build naming the tool.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

# Directory of the environment (the folder of its pyproject.toml and lock) by environment id; "external" has none.
ENV_DIRS = {
    "root": "",
    "runner": "",
    "studio": "studio",
    "isaac": "studio/isaac",
    "rtx": "studio/rtx",
    "isaaclab": "studio/isaaclab",
    "reason": "studio/reason",
    "kit": "studio/kit",
    "pipeline": "pipeline",
    "accel": "pipeline/accel",
    "web": "web",
}
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?$")


@dataclass(frozen=True)
class Resolved:
    version: str
    release_date: str | None


class VersionError(Exception):
    """A version that cannot be resolved; `tool` is the registry id and is always part of the message."""

    def __init__(self, tool: str, message: str) -> None:
        super().__init__(f"{tool}: {message}")
        self.tool = tool


def _normalise(name: str) -> str:
    """PEP 503: lower case, runs of `-`, `_` and `.` collapsed to one `-`."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _safe_path(root: Path, rel: object, tool: str) -> Path:
    if not isinstance(rel, str) or not rel:
        raise VersionError(tool, "the lock path is not a string")
    pure = PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts or "\\" in rel or ":" in rel:
        raise VersionError(tool, f"the lock path {rel!r} is not a path inside the repository")
    return root / Path(*pure.parts)


def _read_text(path: Path, tool: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VersionError(tool, f"cannot read {path.name}: {exc.strerror or exc}") from exc


def _date(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC).date().isoformat() if value.tzinfo else value.date().isoformat()
    if hasattr(value, "isoformat"):
        return str(value.isoformat())[:10]
    if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value):
        return value[:10]
    return None


def _from_uv_lock(tool: str, text: str, package: str) -> Resolved:
    try:
        lock = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise VersionError(tool, f"the lock is not valid TOML: {exc}") from exc
    wanted = _normalise(package)
    found = [p for p in lock.get("package", []) if isinstance(p, dict) and _normalise(str(p.get("name", ""))) == wanted]
    if not found:
        raise VersionError(tool, f"package {package!r} is not in the lock")
    versions = {str(p.get("version")) for p in found}
    if len(versions) > 1:
        raise VersionError(
            tool, f"package {package!r} has several versions in the lock ({', '.join(sorted(versions))})"
        )
    times: list[datetime] = []
    for p in found:
        files = list(p.get("wheels", []))
        if isinstance(p.get("sdist"), dict):
            files.append(p["sdist"])
        for f in files:
            stamp = f.get("upload-time") if isinstance(f, dict) else None
            if isinstance(stamp, str):
                try:
                    times.append(datetime.fromisoformat(stamp.replace("Z", "+00:00")))
                except ValueError:
                    continue
    release = min(times).astimezone(UTC).date().isoformat() if times else None
    return Resolved(versions.pop(), release)


def _pnpm_version(raw: object) -> str:
    """`12.12.0(react-dom@19.3.0)(react@19.3.0)` -> `12.12.0` (the peer suffix is not part of the version)."""
    return str(raw).split("(", 1)[0]


def _from_pnpm_lock(tool: str, text: str, package: str) -> Resolved:
    try:
        lock = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise VersionError(tool, f"the lock is not valid YAML: {exc}") from exc
    if not isinstance(lock, dict):
        raise VersionError(tool, "the lock is empty or not a mapping")
    importer = (lock.get("importers") or {}).get(".") or {}
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        direct = (importer.get(section) or {}).get(package)
        if isinstance(direct, dict) and "version" in direct:
            return Resolved(_pnpm_version(direct["version"]), None)
    versions: set[str] = set()
    for key in (lock.get("packages") or {}) if isinstance(lock.get("packages"), dict) else []:
        name, _, version = str(key).split("(", 1)[0].rpartition("@")
        if name == package and version:
            versions.add(version)
    if not versions:
        raise VersionError(tool, f"package {package!r} is not in the lock")
    if len(versions) > 1:
        raise VersionError(
            tool, f"package {package!r} has several versions in the lock ({', '.join(sorted(versions))})"
        )
    return Resolved(versions.pop(), None)


def _from_binary(tool: str, ref: dict[str, Any], root: Path) -> Resolved:
    text = _read_text(root / "studio" / "external-binaries.yaml", tool)
    try:
        records = (yaml.safe_load(text) or {}).get("binaries", [])
    except (yaml.YAMLError, AttributeError) as exc:
        raise VersionError(tool, f"external-binaries.yaml is not readable: {exc}") from exc
    record = next((r for r in records if isinstance(r, dict) and r.get("id") == ref.get("from_binary")), None)
    if record is None:
        raise VersionError(tool, f"no record of the binary {ref.get('from_binary')!r}")
    if record.get("release") != ref.get("release"):
        raise VersionError(tool, f"release {ref.get('release')!r} differs from the record ({record.get('release')!r})")
    if record.get("sha256") != ref.get("sha256"):
        raise VersionError(tool, "the SHA-256 differs from the record")
    return Resolved(str(record["release"]), _date(record.get("date")))


def _from_git_tag(tool: str, ref: dict[str, Any], envs: list[str], root: Path) -> Resolved:
    tag, repository = ref.get("from_git_tag"), ref.get("repository")
    for env in envs:
        folder = ENV_DIRS.get(env)
        if folder is None:
            continue
        pyproject = root / folder / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            sources = (
                tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {}).get("uv", {}).get("sources", {})
            )
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise VersionError(tool, f"{pyproject.name} is not readable: {exc}") from exc
        for source in sources.values():
            if isinstance(source, dict) and source.get("git") == repository and source.get("tag") == tag:
                return Resolved(str(tag), None)
    raise VersionError(tool, f"no environment pins {repository!r} at tag {tag!r}")


def _own(tool: str, root: Path) -> Resolved:
    first = _read_text(root / "VERSION", tool).splitlines()
    line = first[0].strip() if first else ""
    if not SEMVER.match(line):
        raise VersionError(tool, f"VERSION does not start with a semantic version (got {line!r})")
    return Resolved(line, None)


def resolve_entry(entry: dict[str, Any], root: Path) -> Resolved:
    tool = str(entry.get("id", "?")) if isinstance(entry, dict) else "?"
    ref = entry.get("version") if isinstance(entry, dict) else None
    if not isinstance(ref, dict):
        raise VersionError(tool, "the version is not a reference (a literal version string is not allowed)")
    if "from_lock" in ref:
        path = _safe_path(root, ref["from_lock"], tool)
        package = ref.get("package")
        if not isinstance(package, str) or not package:
            raise VersionError(tool, "the reference names no package")
        text = _read_text(path, tool)
        if path.name == "pnpm-lock.yaml":
            return _from_pnpm_lock(tool, text, package)
        return _from_uv_lock(tool, text, package)
    if "from_binary" in ref:
        return _from_binary(tool, ref, root)
    if "from_git_tag" in ref:
        envs = entry.get("envs") if isinstance(entry.get("envs"), list) else []
        return _from_git_tag(tool, ref, [str(e) for e in envs], root)
    if ref.get("own") is True:
        return _own(tool, root)
    raise VersionError(tool, "the version reference is not one of from_lock, from_binary, from_git_tag or own")


def resolve_registry(root: Path) -> dict[str, Resolved]:
    """The resolved version of every tool of `root/studio/tools.yaml`, in registry order; fails on the first."""
    document = yaml.safe_load((root / "studio" / "tools.yaml").read_text(encoding="utf-8"))
    tools = document.get("tools") if isinstance(document, dict) else None
    if not isinstance(tools, list):
        raise ValueError("studio/tools.yaml has no `tools` list")
    out: dict[str, Resolved] = {}
    for entry in tools:
        resolved = resolve_entry(entry, root)
        out[str(entry["id"])] = resolved
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve the version of every registry tool from its lock.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--json", action="store_true", help="print a JSON object instead of one line per tool")
    args = parser.parse_args(argv)
    try:
        resolved = resolve_registry(args.root)
    except VersionError as exc:
        print(f"resolve_versions: {exc}", file=sys.stderr)
        return 1
    except (OSError, yaml.YAMLError, ValueError, KeyError, TypeError) as exc:
        print(f"resolve_versions: cannot read studio/tools.yaml in {args.root}: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({k: {"version": v.version, "release_date": v.release_date} for k, v in resolved.items()}))
    else:
        for tool_id, value in resolved.items():
            print(f"{tool_id} {value.version} {value.release_date or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
