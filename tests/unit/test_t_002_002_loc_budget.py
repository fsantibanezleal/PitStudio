# ruff: noqa: PT018
"""T-002-002: the runner stays within its size budget (NFR-002-01 = NFR-000-08).

Requirement: NFR-002-01.

Counting rule (spec NFR-002-01): a line counts when, after stripping white space, it is not empty and does not start
with `#`; docstring lines count; modules whose first line says they are generated are excluded.
The rule is fixed here by two hand-counted fixture files (the oracle), then applied to `src/pitstudio/runner/**/*.py`.

Expected product facts: the package `src/pitstudio/runner/` exists (modules of plan.md Design) and holds at most
`runner.loc_max` lines (1,500; thresholds.yaml).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

# Hand count of FIXTURE_A: 6 blank lines and 4 comment-only lines (shebang line included) are not counted; the
# docstring has 3 counted lines (opening with text, 'line two', closing) and there are 6 code lines (import, X, def,
# return, class, pass) -> 9 counted.
FIXTURE_A = '''#!/usr/bin/env python
# a comment

"""Docstring line one.

line two of the docstring
"""

import os
# another comment
X = 1

def f(a):
    # inner comment
    return a + X


class C:
    pass
'''
FIXTURE_A_EXPECTED = 9

# Hand count: only blanks and comments -> 0; a line holding code plus a trailing comment counts once.
FIXTURE_B = "# only comments\n\n   \n\t# indented comment\nx = 1  # trailing comment still counts\n\n"
FIXTURE_B_EXPECTED = 1


def count_lines(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip() and not line.strip().startswith("#"))


def is_generated(text: str) -> bool:
    first = text.splitlines()[0] if text.strip() else ""
    return first.startswith("# Generated from")


def tree_count(pkg: Path) -> tuple[int, dict[str, int]]:
    per: dict[str, int] = {}
    for f in sorted(pkg.rglob("*.py")):
        if any(part in ("__pycache__", ".venv") for part in f.parts):
            continue
        text = f.read_text(encoding="utf-8")
        if is_generated(text):
            continue
        per[f.relative_to(pkg).as_posix()] = count_lines(text)
    return sum(per.values()), per


@pytest.mark.req("NFR-002-01")
def test_nfr_002_01_runner_package_is_within_the_line_budget() -> None:
    # the counting rule is fixed first by the two hand-counted fixtures ...
    assert count_lines(FIXTURE_A) == FIXTURE_A_EXPECTED
    assert count_lines(FIXTURE_B) == FIXTURE_B_EXPECTED
    gen = "# Generated from contracts/job.schema.json by tools/gen_types.py. Do not edit.\nx = 1\n"
    assert is_generated(gen) and not is_generated(FIXTURE_B)
    # ... then applied to the real tree
    pkg = ROOT / "src" / "pitstudio" / "runner"
    assert pkg.is_dir(), "src/pitstudio/runner/ does not exist yet"
    modules = {p.name for p in pkg.glob("*.py")}
    assert {
        "cli.py",
        "recipe.py",
        "cache.py",
        "locks.py",
        "guards.py",
        "gpu.py",
        "telemetry.py",
        "execute.py",
        "queue.py",
        "worker.py",
        "publish.py",
        "gc.py",
    } <= modules
    assert (pkg / "stagekit" / "pitstudio_stagekit.py").is_file()
    total, per = tree_count(pkg)
    limit = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
        "runner"
    ]["loc_max"]
    assert limit == 1500
    assert total <= limit, f"runner has {total} counted lines (> {limit}): {per}"
