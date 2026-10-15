"""Class budgets and size caps of the web bake (FR-016-17, FR-016-18, NFR-016-04, NFR-016-05; spec section 7 Table B)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

CLASS_CAPS_BYTES: dict[str, int] = {
    "videos": 150_000_000,
    "tiles-glb": 95_000_000,
    "shards-clouds": 60_000_000,
    "splats": 25_000_000,
    "onnx": 80_000_000,
    "runtimes": 55_000_000,
    "own-code": 10_000_000,
    "studio-showcase": 25_000_000,
}
SITE_BYTES_MAX = 500_000_000
LIVE_ONNX_BYTES_MAX = 25_000_000
SHARD_BYTES_MAX = 10_000_000
GIT_FILE_BYTES_LIMIT = 10_485_760
GIT_TOTAL_BYTES_MAX = 100_000_000


@dataclass
class BudgetReport:
    classes: dict[str, dict[str, int]]
    site_total: int
    site_cap: int
    site_margin: int
    git_total: int
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


class BudgetError(Exception):
    """A bake that cannot be accounted (`.path`) or that exceeds a cap (`.report`)."""

    def __init__(self, message: str, *, path: str | None = None, report: BudgetReport | None = None) -> None:
        super().__init__(message)
        self.path = path
        self.report = report


def _validated(files: Sequence[Mapping[str, Any]]) -> list[tuple[str, int, str, Mapping[str, Any]]]:
    rows = []
    for entry in files:
        path = entry.get("path")
        name = path if isinstance(path, str) else repr(path)
        cls = entry.get("budget_class")
        if not isinstance(cls, str) or cls not in CLASS_CAPS_BYTES:
            raise BudgetError(f"{name}: budget class {cls!r} is missing or not in Table B", path=name)
        nbytes = entry.get("bytes")
        if isinstance(nbytes, bool) or not isinstance(nbytes, int) or nbytes < 0:
            raise BudgetError(f"{name}: bytes {nbytes!r} is not a non-negative integer", path=name)
        rows.append((name, nbytes, cls, entry))
    return rows


def budget_report(files: Sequence[Mapping[str, Any]]) -> BudgetReport:
    """Class totals, caps and margins plus every failed rule; raises BudgetError only for an unaccountable entry."""
    rows = _validated(files)
    totals = dict.fromkeys(CLASS_CAPS_BYTES, 0)
    git_total = 0
    for _, nbytes, cls, entry in rows:
        totals[cls] += nbytes
        if entry.get("host") == "git":
            git_total += nbytes
    classes = {c: {"total": totals[c], "cap": cap, "margin": cap - totals[c]} for c, cap in CLASS_CAPS_BYTES.items()}
    site_total = sum(totals.values())
    failures: list[dict[str, Any]] = []

    def fail(scope: str, name: str, total: int, cap: int) -> None:
        failures.append({"scope": scope, "name": name, "total": total, "cap": cap})

    for cls, row in classes.items():
        if row["total"] > row["cap"]:
            fail("class", cls, row["total"], row["cap"])
    if site_total > SITE_BYTES_MAX:
        fail("site", "site", site_total, SITE_BYTES_MAX)
    for name, nbytes, _, entry in rows:
        if entry.get("kind") == "onnx" and entry.get("lane") == "live" and nbytes > LIVE_ONNX_BYTES_MAX:
            fail("live-onnx", name, nbytes, LIVE_ONNX_BYTES_MAX)
        if entry.get("kind") == "shard" and nbytes > SHARD_BYTES_MAX:
            fail("shard", name, nbytes, SHARD_BYTES_MAX)
        if entry.get("host") == "git" and nbytes >= GIT_FILE_BYTES_LIMIT:
            fail("git-file", name, nbytes, GIT_FILE_BYTES_LIMIT - 1)
    if git_total > GIT_TOTAL_BYTES_MAX:
        fail("git-total", "git", git_total, GIT_TOTAL_BYTES_MAX)
    return BudgetReport(classes, site_total, SITE_BYTES_MAX, SITE_BYTES_MAX - site_total, git_total, failures)


def enforce_budgets(files: Sequence[Mapping[str, Any]]) -> BudgetReport:
    """The report when every rule holds; BudgetError carrying the report otherwise."""
    report = budget_report(files)
    if not report.ok:
        names = ", ".join(f"{f['scope']}:{f['name']}" for f in report.failures)
        raise BudgetError(f"budget exceeded ({names})", report=report)
    return report
