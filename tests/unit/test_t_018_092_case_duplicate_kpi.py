"""T-018-092: a KPI id repeated within one case fails the case check with the error class `case-duplicate-kpi`.

The finding names the case and the id.

Requirements: FR-018-69 (hostile-input class found by the G5 review; the cross-checks of FR-018-10 are T-018-001).

Spec: specs/018-web-cases/ (spec.md FR-018-69, plan.md test strategy row "FR-018-69", tasks.md T-018-092).

Expected API of the implementation: `tools/check_cases.py [--root DIR]` (the CLI fixed by T-018-001: exit 0 when
clean, 1 on findings with one line per finding naming the offending id, 2 on a usage error, never a traceback); for
FR-018-69 the finding line carries the error class `case-duplicate-kpi`, the case id and the repeated KPI id. The tool
reads `<root>/studio/cases.yaml` (and, when present, `<root>/studio/tools.yaml`, `<root>/studio/methods.yaml`,
`<root>/data/sources.yaml` and `<root>/contracts/`).

Oracle: hand calculation. A registry built from the spec's valid example
(specs/018-web-cases/contracts/examples/cases.valid.json, already schema-checked by T-018-001) in which one case
declares the KPI id `throughput` twice must give exactly the finding "case-duplicate-kpi" for that case and id; the
unmodified example, and the same KPI id used once in each of two DIFFERENT cases, must not.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "specs" / "018-web-cases" / "contracts" / "examples" / "cases.valid.json"
TOOL = ROOT / "tools" / "check_cases.py"


def _registry() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _fixture_root(tmp_path: Path, doc: dict) -> Path:
    """A repository copy holding what `tools/check_cases.py --root` reads, with `doc` as studio/cases.yaml."""
    root = tmp_path / "repo"
    (root / "studio").mkdir(parents=True)
    (root / "studio" / "cases.yaml").write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    for rel in ("studio/tools.yaml", "studio/methods.yaml", "data/sources.yaml"):
        src = ROOT / rel
        if src.is_file():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, root / rel)
    if (ROOT / "contracts").is_dir():
        shutil.copytree(ROOT / "contracts", root / "contracts")
    return root


def _check(root: Path) -> tuple[int, str]:
    assert TOOL.is_file(), "tools/check_cases.py exists (T-018-001)"
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--root", str(root)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _duplicate_findings(output: str) -> list[str]:
    return [line for line in output.splitlines() if "case-duplicate-kpi" in line]


@pytest.mark.req("FR-018-69")
def test_a_kpi_id_declared_twice_in_a_case_is_reported_with_the_case_and_the_id(tmp_path: Path) -> None:
    doc = _registry()
    kpis = doc["cases"]["A1"]["kpis"]
    assert kpis[0]["id"] == "throughput"  # the example's first KPI of A1
    kpis.append(copy.deepcopy(kpis[0]))
    code, out = _check(_fixture_root(tmp_path, doc))
    assert code == 1, out
    findings = _duplicate_findings(out)
    assert len(findings) == 1, out
    assert "A1" in findings[0]
    assert "throughput" in findings[0]
    assert "Traceback" not in out


@pytest.mark.req("FR-018-69")
def test_the_second_declaration_may_differ_in_everything_but_the_id(tmp_path: Path) -> None:
    doc = _registry()
    second = copy.deepcopy(doc["cases"]["B1"]["kpis"][0])
    first_id = doc["cases"]["B1"]["kpis"][0]["id"]
    second["name"] = {"en": "Another name", "es": "Otro nombre"}
    second["headline"] = not second["headline"]
    doc["cases"]["B1"]["kpis"].append(second)
    code, out = _check(_fixture_root(tmp_path, doc))
    assert code == 1, out
    findings = _duplicate_findings(out)
    assert len(findings) == 1, out
    assert "B1" in findings[0], out
    assert first_id in findings[0], out


@pytest.mark.req("FR-018-69")
def test_an_id_repeated_three_times_and_two_different_ids_repeated_are_all_named(tmp_path: Path) -> None:
    doc = _registry()
    a = doc["cases"]["C1"]["kpis"]
    a.append(copy.deepcopy(a[0]))
    a.append(copy.deepcopy(a[0]))
    a.append(copy.deepcopy(a[1]))
    code, out = _check(_fixture_root(tmp_path, doc))
    assert code == 1, out
    text = "\n".join(_duplicate_findings(out))
    assert "C1" in text, out
    assert a[0]["id"] in text, out
    assert a[1]["id"] in text, out


@pytest.mark.req("FR-018-69")
def test_duplicates_in_two_different_cases_are_reported_for_each_case(tmp_path: Path) -> None:
    doc = _registry()
    for case_id in ("D1", "E2"):
        kpis = doc["cases"][case_id]["kpis"]
        kpis.append(copy.deepcopy(kpis[0]))
    code, out = _check(_fixture_root(tmp_path, doc))
    assert code == 1, out
    findings = _duplicate_findings(out)
    assert any("D1" in line for line in findings), out
    assert any("E2" in line for line in findings), out


@pytest.mark.req("FR-018-69")
def test_the_unmodified_registry_has_no_duplicate_finding(tmp_path: Path) -> None:
    _code, out = _check(_fixture_root(tmp_path, _registry()))
    assert _duplicate_findings(out) == [], out


@pytest.mark.req("FR-018-69")
def test_the_same_kpi_id_in_two_different_cases_is_not_a_duplicate(tmp_path: Path) -> None:
    doc = _registry()
    shared = copy.deepcopy(doc["cases"]["A1"]["kpis"][0])
    doc["cases"]["A2"]["kpis"].append(shared)  # KPI ids are scoped to their case
    _code, out = _check(_fixture_root(tmp_path, doc))
    assert _duplicate_findings(out) == [], out


@pytest.mark.req("FR-018-69")
def test_the_committed_registry_passes_the_duplicate_check() -> None:
    assert TOOL.is_file(), "tools/check_cases.py exists (T-018-001)"
    proc = subprocess.run(
        [sys.executable, str(TOOL)], capture_output=True, text=True, cwd=ROOT, timeout=120, check=False
    )
    assert "case-duplicate-kpi" not in proc.stdout + proc.stderr
    assert proc.returncode == 0, proc.stdout + proc.stderr
