"""The release rule of tools/trace.py: every spec Converged and every requirement tested; CI rules stay per status."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import trace as trace_tool  # noqa: E402


def req(spec: str, phase: str, tasks: list[str], tests: list[str]) -> dict:
    return {"spec": spec, "retired": False, "draft": phase in {"draft", "clarified"}, "phase": phase,
            "tasks": tasks, "tests": tests}


def data(**reqs: dict) -> dict:
    return {"requirements": {k.replace("_", "-"): v for k, v in reqs.items()}, "tasks": {}, "unknown": []}


def test_ci_rule_lets_an_approved_spec_wait_for_its_tests() -> None:
    d = data(FR_001_01=req("001-contracts", "approved", ["T-001-001"], []))
    assert trace_tool.problems(d) == []


def test_release_rule_demands_tests_and_converged_specs() -> None:
    d = data(FR_001_01=req("001-contracts", "approved", ["T-001-001"], []))
    probs = trace_tool.problems(d, release=True)
    assert "FR-001-01 has no test" in probs
    assert any("001-contracts (approved) is not Converged" in p for p in probs)


def test_release_rule_also_checks_clarified_specs() -> None:
    d = data(FR_002_01=req("002-runner", "clarified", [], []))
    assert trace_tool.problems(d) == []  # CI: no checks while Clarified
    probs = trace_tool.problems(d, release=True)
    assert "FR-002-01 has no task" in probs and "FR-002-01 has no test" in probs


def test_release_rule_passes_a_converged_tested_spec() -> None:
    d = data(FR_003_01=req("003-console", "converged", ["T-003-001"], ["tests/unit/test_x.py"]),
             US_003_1=req("003-console", "converged", ["T-003-001"], []))
    assert trace_tool.problems(d, release=True) == []
