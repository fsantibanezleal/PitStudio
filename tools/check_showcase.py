"""CI check: the honesty rules of the studio showcase (spec 019, DC-019-03 honesty report).

Usage:  python tools/check_showcase.py [--root DIR]
Output: one line per finding, "<check>: <subject>: <detail>".
Exit:   0 clean, 1 findings, 2 usage error or an unreadable input (the message names the file). Never a traceback.

Six checks (FR-019-33..36, FR-019-43):
  done-needs-artefact          a tool with status `done` has at least one published artefact
  not-yet-run-has-artefact     a tool with status `not-yet-run` has none
  outputs-only                 a `reference-only` tool publishes only images, videos, point clouds, tables and text
  our-scenes                   every image or video of such a tool descends from our scene-composition stage
  local-only-scrub             a local-only stage carries no number in a run card or in published telemetry
  file-guards                  no engine, cache, template-licensed or `omniverse://` file in the tree
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ALLOWED_KINDS = frozenset({"image", "video", "point-cloud", "table", "text"})
RENDER_KINDS = frozenset({"image", "video"})
SCENE_STAGE = "st40_compose"
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "docs",
        "specs",
        "tests",
        "e2e",
        "test-support",
        "test-results",
        "__pycache__",
    }
)
BINARY_SUFFIXES = frozenset({".engine", ".plan", ".trt", ".gguf"})
CACHE_MARKERS = (
    ".nv/ComputeCache/",
    "/torch_extensions/",
    "cache/warp/",
    ".triton/cache/",
    "/shadercache/",
)
TEXT_SUFFIXES = frozenset(
    {".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".kit", ".toml", ".cpp", ".h", ".usda", ".yaml", ".yml"}
)
HEADER_PATTERNS = (
    re.compile(r"^\s*(?:#|//|/\*|--)\s*SPDX-License-Identifier:\s*LicenseRef-NvidiaProprietary", re.MULTILINE),
    re.compile(
        r"^\s*(?:#|//|/\*|--)\s*NVIDIA CORPORATION and its licensors retain all intellectual property", re.MULTILINE
    ),
)
OMNIVERSE_URL = re.compile(r"omniverse://")
MAX_SCAN_BYTES = 2_000_000
NUMERIC_STAGE_FIELDS = ("wall_s", "throughput", "telemetry", "attempts", "points")


@dataclass(frozen=True)
class Finding:
    check: str
    subject: str
    detail: str
    pointer: str | None = None


def _producer(artefact: dict[str, Any]) -> str | None:
    producer = artefact.get("producer")
    tool = producer.get("tool") if isinstance(producer, dict) else None
    return tool if isinstance(tool, str) else None


def _makers(artefacts: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for a in artefacts:
        if isinstance(a, dict) and (tool := _producer(a)) is not None:
            out.setdefault(tool, []).append(a)
    return out


def check_done_needs_artefact(tools: list[dict[str, Any]], artefacts: list[dict[str, Any]]) -> list[Finding]:
    made = _makers(artefacts)
    return [
        Finding(
            "done-needs-artefact", str(t["id"]), "the tool is `done` but no published artefact names it as producer"
        )
        for t in tools
        if t.get("status") == "done" and str(t.get("id")) not in made
    ]


def check_not_yet_run_has_artefact(tools: list[dict[str, Any]], artefacts: list[dict[str, Any]]) -> list[Finding]:
    made = _makers(artefacts)
    out = []
    for t in tools:
        mine = made.get(str(t.get("id")), [])
        if t.get("status") == "not-yet-run" and mine:
            names = ", ".join(sorted(str(a.get("id")) for a in mine))
            out.append(
                Finding("not-yet-run-has-artefact", str(t["id"]), f"the tool is `not-yet-run` but produced: {names}")
            )
    return out


def _reference_only(tools: list[dict[str, Any]]) -> set[str]:
    return {str(t["id"]) for t in tools if t.get("licence_class") == "reference-only"}


def check_outputs_only(tools: list[dict[str, Any]], artefacts: list[dict[str, Any]]) -> list[Finding]:
    restricted = _reference_only(tools)
    out = []
    for a in artefacts:
        tool = _producer(a) if isinstance(a, dict) else None
        if tool in restricted and a.get("kind") not in ALLOWED_KINDS:
            out.append(
                Finding(
                    "outputs-only",
                    str(a.get("id")),
                    f"artefact of kind {a.get('kind')!r} published by the reference-only tool {tool}",
                )
            )
    return out


def _descends_from_scene(start: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> bool:
    """True when an artefact reachable through `inputs` of kind `artefact` is made by the scene-composition stage."""
    seen = {str(start.get("id"))}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for item in node.get("inputs") or []:
            if not isinstance(item, dict) or item.get("kind") != "artefact":
                continue
            parent = by_id.get(str(item.get("id")))
            if parent is None or str(parent.get("id")) in seen:
                continue
            producer = parent.get("producer")
            stage = producer.get("stage") if isinstance(producer, dict) else None
            if isinstance(stage, dict) and stage.get("id") == SCENE_STAGE:
                return True
            seen.add(str(parent.get("id")))
            queue.append(parent)
    return False


def check_our_scenes(tools: list[dict[str, Any]], artefacts: list[dict[str, Any]]) -> list[Finding]:
    restricted = _reference_only(tools)
    by_id = {str(a.get("id")): a for a in artefacts if isinstance(a, dict)}
    out = []
    for a in artefacts:
        if not isinstance(a, dict) or _producer(a) not in restricted or a.get("kind") not in RENDER_KINDS:
            continue
        if not _descends_from_scene(a, by_id):
            out.append(
                Finding(
                    "our-scenes",
                    str(a.get("id")),
                    f"{a.get('kind')} of {_producer(a)} does not descend from the {SCENE_STAGE} stage",
                )
            )
    return out


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _numbers(value: Any, pointer: str) -> Iterator[str]:
    """Pointers of the numbers (not booleans) inside a value."""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield pointer
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _numbers(v, f"{pointer}/{_escape(str(k))}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _numbers(v, f"{pointer}/{i}")


def check_local_only_scrub(doc: Any, file: str = "run-card") -> list[Finding]:
    """A run card or a published-telemetry document: a `local-only` stage holds no numeric metric or telemetry value."""
    stages = doc.get("stages") if isinstance(doc, dict) else None
    if not isinstance(stages, list):
        return []
    out = []
    for i, stage in enumerate(stages):
        if not isinstance(stage, dict) or stage.get("performance") != "local-only":
            continue
        base = f"/stages/{i}"
        key = stage.get("key")
        sid = key.get("id") if isinstance(key, dict) else None
        pointers: list[str] = []
        for name in ("wall_s", "throughput", "telemetry", "points"):
            if name in stage:
                pointers.extend(_numbers(stage[name], f"{base}/{name}"))
        attempts = stage.get("attempts")
        if isinstance(attempts, list):
            for n, attempt in enumerate(attempts):
                if isinstance(attempt, dict) and "duration_s" in attempt:
                    pointers.extend(_numbers(attempt["duration_s"], f"{base}/attempts/{n}/duration_s"))
        out.extend(
            Finding("local-only-scrub", file, f"stage {sid!r} is local-only but holds a number at {p}", p)
            for p in pointers
        )
    return out


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _walk(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts
        if any(p in SKIP_DIRS for p in parts[:-1]) or parts[:2] == ("web", "build") or parts[:2] == ("web", "dist"):
            continue
        if path.is_file():
            yield path


def check_file_guards(root: Path) -> list[Finding]:
    """Engines, caches, licence headers of the Kit template and `omniverse://` URLs are not in the tree (FR-019-34)."""
    out = []
    for path in _walk(root):
        rel = _relative(root, path)
        reason: str | None = None
        slashed = f"/{rel}"
        if path.suffix.lower() in BINARY_SUFFIXES:
            reason = f"a {path.suffix.lower()} file (engines and model files are never committed)"
        elif any(marker in slashed for marker in CACHE_MARKERS):
            reason = "a file of a compiler or driver cache"
        elif path.suffix.lower() in TEXT_SUFFIXES and rel != "tools/check_showcase.py":
            try:
                with path.open("rb") as handle:
                    text = handle.read(MAX_SCAN_BYTES).decode("utf-8", errors="ignore")
            except OSError:
                continue
            if any(p.search(text) for p in HEADER_PATTERNS):
                reason = "a file that carries the proprietary licence header of the kit-app-template"
            elif OMNIVERSE_URL.search(text):
                reason = "a file that refers to an omniverse:// location"
        if reason:
            out.append(Finding("file-guards", rel, reason))
    return out


class InputError(Exception):
    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path.name}: {message} ({path})")


def _load(path: Path, *, as_yaml: bool = False) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
        return yaml.safe_load(text) if as_yaml else json.loads(text)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise InputError(path, f"cannot read: {exc}") from exc


def run(root: Path) -> list[Finding]:
    if not root.is_dir():
        raise InputError(root, "not a directory")
    tools_doc = _load(root / "studio" / "tools.yaml", as_yaml=True)
    tools = tools_doc.get("tools") if isinstance(tools_doc, dict) else None
    if not isinstance(tools, list):
        raise InputError(root / "studio" / "tools.yaml", "has no `tools` list")
    tools = [t for t in tools if isinstance(t, dict)]
    assets = root / "web" / "public" / "assets"
    manifest = _load(assets / "manifest.json")
    artefacts = manifest.get("artefacts") if isinstance(manifest, dict) else None
    if not isinstance(artefacts, list):
        raise InputError(assets / "manifest.json", "has no `artefacts` list")
    artefacts = [a for a in artefacts if isinstance(a, dict)]
    findings = [
        *check_done_needs_artefact(tools, artefacts),
        *check_not_yet_run_has_artefact(tools, artefacts),
        *check_outputs_only(tools, artefacts),
        *check_our_scenes(tools, artefacts),
    ]
    runs = assets / "runs"
    if runs.is_dir():
        for folder in sorted(p for p in runs.iterdir() if p.is_dir()):
            for name in ("manifest.json", "telemetry.json"):
                path = folder / name
                if path.is_file():
                    findings.extend(check_local_only_scrub(_load(path), file=_relative(root, path)))
    findings.extend(check_file_guards(root))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the honesty rules of the studio showcase.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    try:
        findings = run(args.root)
    except InputError as exc:
        print(f"check_showcase: {exc}", file=sys.stderr)
        return 2
    for f in findings:
        print(f"{f.check}: {f.subject}: {f.detail}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
