"""CI check of the studio build (spec 019): the tool map and the generated studio index.

Usage:  python tools/check_studio.py [--root DIR]
Output: one line per finding, "<check>: <subject>: <pointer or size>".
Exit:   0 clean, 1 findings, 2 usage error or unreadable input (the message names the file). Never a traceback.

Checks:
  toolmap-self-edge        an edge of the tool map from a tool to itself (FR-019-46); the subject is the tool, the
                           pointer is `/edges/<index>` into studio/toolmap.yaml
  studio-index-too-large   `web/public/studio/index.json` has more than 1,000,000 bytes (FR-019-47, NFR-019-03);
                           a missing file is not an error (nothing was generated yet)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

INDEX_CAP_BYTES = 1_000_000
INDEX_RELATIVE = Path("web") / "public" / "studio" / "index.json"


@dataclass(frozen=True)
class Finding:
    check: str
    subject: str
    pointer: str | None
    detail: str
    value: str | None = None

    def line(self) -> str:
        return f"{self.check}: {self.subject}: {self.value if self.value is not None else self.pointer}"


def check_toolmap(toolmap: Any, tools: list[dict[str, Any]]) -> list[Finding]:
    """Findings of the tool map: an edge from a tool to itself (ids compared exactly, never case-folded)."""
    edges = toolmap.get("edges") if isinstance(toolmap, dict) else None
    if not isinstance(edges, list):
        return []
    out = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("from"), edge.get("to")
        if isinstance(source, str) and isinstance(target, str) and source == target:
            out.append(
                Finding(
                    "toolmap-self-edge", source, f"/edges/{index}", f"the edge {index} leads from {source} to itself"
                )
            )
    return out


def check_index_size(path: Path, root: Path | None = None) -> list[Finding]:
    """The studio index holds at most 1,000,000 bytes (bytes, not characters); OSError when `path` is missing."""
    size = path.stat().st_size
    if size <= INDEX_CAP_BYTES:
        return []
    shown = path.relative_to(root).as_posix() if root is not None else path.as_posix()
    return [
        Finding(
            "studio-index-too-large",
            shown,
            None,
            f"{size} bytes, the cap is {INDEX_CAP_BYTES}",
            value=str(size),
        )
    ]


class InputError(Exception):
    pass


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InputError(f"{path.name}: cannot read ({path}): {exc}") from exc


def run(root: Path) -> list[Finding]:
    if not root.is_dir():
        raise InputError(f"{root}: not a directory")
    toolmap = _load_yaml(root / "studio" / "toolmap.yaml")
    tools_doc = _load_yaml(root / "studio" / "tools.yaml")
    tools = tools_doc.get("tools") if isinstance(tools_doc, dict) else None
    findings = check_toolmap(toolmap, tools if isinstance(tools, list) else [])
    index = root / INDEX_RELATIVE
    if index.is_file():
        findings.extend(check_index_size(index, root))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the tool map and the studio index of the build.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    try:
        findings = run(args.root)
    except InputError as exc:
        print(f"check_studio: {exc}", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding.line())
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
