# ruff: noqa: E501, PT018
"""T-002-090: mutation score of the runner's numerical core (NFR-002-05).

Requirement: NFR-002-05 (>= `mutation.numerical_core_min` = 0.80 for the cache key, seed, guard and telemetry-summary modules).

A mutation run cannot be repeated inside a unit test (minutes of CPU, a mutation tool in the environment); the task records its
result and this test enforces it. Expected product fact: `specs/002-runner/mutation.json`, written by the implementer's mutation
run (mutmut or an equivalent tool), shaped as
  {"tool": "<name and version>", "date": "YYYY-MM-DD", "git_sha": "<40 hex>", "modules": {
      "src/pitstudio/runner/cache.py": {"killed": int, "survived": int, "timeout": int, "total": int},
      "src/pitstudio/runner/guards.py": {...}, "src/pitstudio/runner/telemetry.py": {...}}, "score": float}
where each module's counts add up (killed + survived + timeout == total, a timeout counting as killed), `score` equals
sum(killed + timeout) / sum(total) over the modules (recomputed here, never trusted), every module file exists, the record
names a commit that exists in the repository, and the score is at least the threshold read from thresholds.yaml.
Oracle: the arithmetic above and the committed thresholds file.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "specs" / "002-runner" / "mutation.json"
REQUIRED = {"src/pitstudio/runner/cache.py", "src/pitstudio/runner/guards.py", "src/pitstudio/runner/telemetry.py"}


@pytest.mark.req("NFR-002-05")
def test_nfr_002_05_the_recorded_mutation_score_of_the_numerical_core_meets_the_threshold() -> None:
    assert RECORD.is_file(), "specs/002-runner/mutation.json: no mutation run is recorded"
    rec = json.loads(RECORD.read_text(encoding="utf-8"))
    threshold = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
        "mutation"
    ]["numerical_core_min"]
    assert threshold == 0.80
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", rec["date"]) and rec["tool"]
    assert set(rec["modules"]) >= REQUIRED, f"the run must cover {sorted(REQUIRED)}"
    killed = total = 0
    for path, m in rec["modules"].items():
        assert (ROOT / path).is_file(), f"{path} does not exist"
        assert m["killed"] + m["survived"] + m["timeout"] == m["total"] and m["total"] > 0, path
        killed += m["killed"] + m["timeout"]
        total += m["total"]
    score = killed / total
    assert abs(rec["score"] - score) < 1e-9, "the recorded score must equal killed / total"
    assert score >= threshold, f"mutation score {score:.3f} is below {threshold}"
    assert re.fullmatch(r"[0-9a-f]{40}", rec["git_sha"])
    r = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", f"{rec['git_sha']}^{{commit}}"], capture_output=True, text=True
    )
    assert r.returncode == 0, "the recorded commit is not in the repository"
