"""T-018-090 (NFR-018-05): coverage and mutation run on the numerical cores of spec 018, scores checked and recorded.

The scores are checked against `thresholds.yaml`.

Scope of the run (NFR-018-05): `web/src/engines/**`, `web/src/sim/**`, `web/src/assets/shard*` and `web/src/lane/**`
(Vitest coverage; Stryker mutation).

Expected: the coverage run and the mutation run are executed on that scope and their scores are recorded in the log
line of task T-018-090 in `specs/018-web-cases/tasks.md`: the task is ticked `[x]` and the line carries
`branch coverage 0.NN` and `mutation score 0.NN` (a leading `.NN` is accepted).
The test fails below `coverage.branch_core_min` (0.85) and `mutation.numerical_core_min` (0.80) of
`specs/000-foundation/thresholds.yaml`; a mutation score below `mutation.numerical_core_fail_below` (0.70) is a hard
failure whatever else is recorded. The record location and format follow the convention of the minephys quality-gate
tasks ("record the score in the task log"); the exact line format is an open point listed in the red-phase report.

Oracle: the threshold file (a hand-written gate that only ratchets upwards) and the recorded scores; the existence
of the files the run covers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "specs" / "018-web-cases" / "tasks.md"
THRESHOLDS = ROOT / "specs" / "000-foundation" / "thresholds.yaml"


def _thresholds() -> dict:
    return yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))


def _log_line() -> str:
    for line in TASKS.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("- [") and "T-018-090" in line:
            return line
    raise AssertionError("task T-018-090 not found in specs/018-web-cases/tasks.md")


def _score(line: str, label: str) -> float:
    m = re.search(rf"{label}[:= ]+\s*(0?\.\d+|1(?:\.0+)?)", line, flags=re.IGNORECASE)
    assert m, f"no '{label} 0.NN' recorded on the T-018-090 line of tasks.md"
    return float(m.group(1))


@pytest.mark.req("NFR-018-05")
def test_the_thresholds_are_the_ones_of_the_spec() -> None:
    data = _thresholds()
    assert data["coverage"]["branch_core_min"] >= 0.85
    assert data["mutation"]["numerical_core_min"] >= 0.80
    assert data["mutation"]["numerical_core_fail_below"] >= 0.70


@pytest.mark.req("NFR-018-05")
def test_the_run_covers_the_numerical_cores_of_spec_018() -> None:
    web = ROOT / "web" / "src"
    # source files of the scope (not the tests): the engine registry, the clock, the shard reader and the lane gate
    for rel in ("engines/registry.ts", "sim/clock.ts", "assets/shard.ts", "lane/derive.ts"):
        assert (web / rel).is_file(), f"web/src/{rel} exists and is in the quality scope"
    sources = [p for p in (web / "engines").rglob("*.ts") if ".test." not in p.name]
    assert len(sources) >= 10, "the engines directory holds the engine implementations"


@pytest.mark.req("NFR-018-05")
def test_the_task_is_ticked_and_records_both_scores() -> None:
    line = _log_line()
    assert re.match(r"\s*-\s*\[[xX]\]", line), "T-018-090 is not ticked"
    _score(line, "branch coverage")
    _score(line, "mutation score")


@pytest.mark.req("NFR-018-05")
def test_the_recorded_branch_coverage_meets_the_threshold() -> None:
    assert _score(_log_line(), "branch coverage") >= _thresholds()["coverage"]["branch_core_min"]


@pytest.mark.req("NFR-018-05")
def test_the_recorded_mutation_score_meets_the_threshold_and_is_not_in_the_failure_band() -> None:
    score = _score(_log_line(), "mutation score")
    thresholds = _thresholds()["mutation"]
    assert score >= thresholds["numerical_core_fail_below"], "below 0.70 is a hard failure"
    assert score >= thresholds["numerical_core_min"]
