"""T-020-090 (NFR-020-09): coverage and mutation run on the cores of spec 020; scores checked.

The scope is `web/src/charts/**`, `web/src/theory/fn/**`, `web/src/results/verdict*` and `web/src/knowledge/search*`
(the numerical and display cores of spec 020).

Expected: the coverage run (Vitest) and the mutation run (Stryker) are executed on that scope and their scores
recorded in the log line of task T-020-090 in `specs/020-web-knowledge/tasks.md`: the task is ticked `[x]` and the
line carries `branch coverage 0.NN` and `mutation score 0.NN` (a leading `.NN` is accepted), as for T-018-090 and
T-019-090. The test fails below `coverage.branch_core_min` (0.85) and `mutation.numerical_core_min` (0.80) of
`specs/000-foundation/thresholds.yaml`; a mutation score below `mutation.numerical_core_fail_below` (0.70) is a hard
failure whatever else is recorded. The exact record format is an open point listed in the red-phase report.

Oracle: the threshold file (a hand-written gate that only ratchets upwards) and the recorded scores; the existence of
the files the run covers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "specs" / "020-web-knowledge" / "tasks.md"
THRESHOLDS = ROOT / "specs" / "000-foundation" / "thresholds.yaml"


def _thresholds() -> dict:
    return yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))


def _log_line() -> str:
    for line in TASKS.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("- [") and "T-020-090" in line:
            return line
    raise AssertionError("task T-020-090 not found in specs/020-web-knowledge/tasks.md")


def _score(line: str, label: str) -> float:
    m = re.search(rf"{label}[:= ]+\s*(0?\.\d+|1(?:\.0+)?)", line, flags=re.IGNORECASE)
    assert m, f"no '{label} 0.NN' recorded on the T-020-090 line of tasks.md"
    return float(m.group(1))


@pytest.mark.req("NFR-020-09")
def test_the_thresholds_are_the_ones_of_the_spec() -> None:
    data = _thresholds()
    assert data["coverage"]["branch_core_min"] >= 0.85
    assert data["mutation"]["numerical_core_min"] >= 0.80
    assert data["mutation"]["numerical_core_fail_below"] >= 0.70


@pytest.mark.req("NFR-020-09")
def test_the_run_covers_the_sources_of_the_scope() -> None:
    web = ROOT / "web" / "src"
    for rel in (
        "charts/decimate.ts",
        "charts/viewTransform.ts",
        "charts/series.ts",
        "theory/fn/beverloo.ts",
        "theory/fn/ritter.ts",
        "theory/fn/lidarRange.ts",
        "theory/fn/ppoClip.ts",
        "theory/fn/mcnemar.ts",
        "theory/fn/gaussianAuc.ts",
        "theory/fn/pairedTCi.ts",
        "results/verdict.ts",
        "knowledge/search.ts",
    ):
        assert (web / rel).is_file(), f"web/src/{rel} exists and is in the quality scope"


@pytest.mark.req("NFR-020-09")
def test_the_task_is_ticked_and_records_both_scores() -> None:
    line = _log_line()
    assert re.match(r"\s*-\s*\[[xX]\]", line), "T-020-090 is not ticked"
    _score(line, "branch coverage")
    _score(line, "mutation score")


@pytest.mark.req("NFR-020-09")
def test_the_recorded_branch_coverage_meets_the_threshold() -> None:
    assert _score(_log_line(), "branch coverage") >= _thresholds()["coverage"]["branch_core_min"]


@pytest.mark.req("NFR-020-09")
def test_the_recorded_mutation_score_meets_the_threshold_and_is_not_in_the_failure_band() -> None:
    score = _score(_log_line(), "mutation score")
    thresholds = _thresholds()["mutation"]
    assert score >= thresholds["numerical_core_fail_below"], "below 0.70 is a hard failure"
    assert score >= thresholds["numerical_core_min"]
