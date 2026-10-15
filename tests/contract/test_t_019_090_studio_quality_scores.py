"""T-019-090 (NFR-019-06): coverage and mutation run on the studio code; scores checked and recorded.

The code is `web/src/studio/**` and `tools/check_showcase.py`.

The scores are checked against `thresholds.yaml`.

Scope of the run (NFR-019-06): `web/src/studio/**` (Vitest coverage; Stryker mutation) and `tools/check_showcase.py`
(pytest coverage; mutmut).

Expected: the coverage runs and the mutation runs are executed on that scope and their scores are recorded in the log
line of task T-019-090 in `specs/019-web-studio/tasks.md`: the task is ticked `[x]` and the line carries
`branch coverage 0.NN` and `mutation score 0.NN` (a leading `.NN` is accepted), as for T-018-090. The test fails below
`coverage.branch_core_min` (0.85) of `specs/000-foundation/thresholds.yaml` and below `mutation.other_min` (0.60);
the record location and format follow the convention of the quality-gate tasks of spec 018 (an open point listed in the
red-phase report).

Oracle: the threshold file (a hand-written gate that only ratchets upwards) and the recorded scores; the existence of
the files the run covers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "specs" / "019-web-studio" / "tasks.md"
THRESHOLDS = ROOT / "specs" / "000-foundation" / "thresholds.yaml"


def _thresholds() -> dict:
    return yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))


def _log_line() -> str:
    for line in TASKS.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("- [") and "T-019-090" in line:
            return line
    raise AssertionError("task T-019-090 not found in specs/019-web-studio/tasks.md")


def _score(line: str, label: str) -> float:
    m = re.search(rf"{label}[:= ]+\s*(0?\.\d+|1(?:\.0+)?)", line, flags=re.IGNORECASE)
    assert m, f"no '{label} 0.NN' recorded on the T-019-090 line of tasks.md"
    return float(m.group(1))


@pytest.mark.req("NFR-019-06")
def test_the_thresholds_are_the_ones_of_the_spec() -> None:
    data = _thresholds()
    assert data["coverage"]["branch_core_min"] >= 0.85
    assert data["mutation"]["other_min"] >= 0.60


@pytest.mark.req("NFR-019-06")
def test_the_run_covers_the_studio_sources() -> None:
    studio = ROOT / "web" / "src" / "studio"
    for rel in (
        "buildIndex.ts",
        "connect.ts",
        "ConnectControl.tsx",
        "ManifestTree.tsx",
        "StageDag.tsx",
        "SafeText.tsx",
    ):
        assert (studio / rel).is_file(), f"web/src/studio/{rel} exists and is in the quality scope"
    for rel in ("Identity.tsx", "Artefacts.tsx", "Provenance.tsx", "Limits.tsx"):
        assert (studio / "blocks" / rel).is_file(), f"web/src/studio/blocks/{rel} exists and is in the quality scope"
    sources = [p for p in studio.rglob("*.ts*") if ".test." not in p.name]
    assert len(sources) >= 20, "the studio directory holds the studio components"
    assert (ROOT / "tools" / "check_showcase.py").is_file(), (
        "tools/check_showcase.py exists and is in the quality scope"
    )


@pytest.mark.req("NFR-019-06")
def test_the_task_is_ticked_and_records_both_scores() -> None:
    line = _log_line()
    assert re.match(r"\s*-\s*\[[xX]\]", line), "T-019-090 is not ticked"
    _score(line, "branch coverage")
    _score(line, "mutation score")


@pytest.mark.req("NFR-019-06")
def test_the_recorded_branch_coverage_meets_the_threshold() -> None:
    assert _score(_log_line(), "branch coverage") >= _thresholds()["coverage"]["branch_core_min"]


@pytest.mark.req("NFR-019-06")
def test_the_recorded_mutation_score_meets_the_threshold() -> None:
    assert _score(_log_line(), "mutation score") >= _thresholds()["mutation"]["other_min"]
