"""Asset hosts: git or release (FR-016-14, P-016-10)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

GIT_FILE_BYTES_MAX = 10_485_760
GIT_BAKED_BYTES_MAX = 100_000_000


@dataclass(frozen=True)
class HostPlan:
    files: list[dict[str, Any]]
    archives: list[dict[str, Any]]
    git_bytes: int


def assign_hosts(files: Sequence[Mapping[str, Any]]) -> HostPlan:
    """Host of every file: large files are release assets; whole classes move, largest total first, until git fits."""
    rows = [
        {k: v for k, v in f.items() if k not in ("host", "archive")} for f in sorted(files, key=lambda f: f["path"])
    ]
    for row in rows:
        row["host"] = "release" if row["bytes"] >= GIT_FILE_BYTES_MAX else "git"
        row["archive"] = None
    totals: dict[str, int] = {}
    for row in rows:
        if row["host"] == "git":
            totals[row["budget_class"]] = totals.get(row["budget_class"], 0) + row["bytes"]
    moved: list[str] = []
    while sum(totals.values()) > GIT_BAKED_BYTES_MAX:
        cls = min(totals, key=lambda c: (-totals[c], c))
        moved.append(cls)
        del totals[cls]
    archives = []
    for cls in sorted(moved):
        members = []
        for row in rows:
            if row["host"] == "git" and row["budget_class"] == cls:
                row["host"], row["archive"] = "release", f"{cls}.tar"
                members.append(row["path"])
        archives.append({"name": f"{cls}.tar", "class": cls, "members": sorted(members)})
    return HostPlan(rows, archives, sum(totals.values()))
