"""T-019-088 (SC-019-01, SC-019-02): the release gate of the studio showcase.

SC-019-01: each of the 17 studio tools has at least one published artefact or an "Evaluated, not adopted" page with its
reason (17 of 17 at the release gate, the honesty report of DC-019-03). SC-019-02: the deployed commit passes every
showcase honesty check (0 violations of FR-019-33 to FR-019-36).

Spec: specs/019-web-studio/ (spec.md section 5, DC-019-03 `honesty`; tasks.md T-019-088).

What is checked: the generated studio index `web/public/studio/index.json` (DC-019-03, produced by
`web/scripts/build-studio-index.mjs` at build) that the release workflow runs against. The test is a gate: it passes
only on a release commit whose index says so, and the checks themselves are independent of the index:
  * the index validates against `specs/019-web-studio/contracts/studio-index.schema.json` (reference implementation
    `jsonschema`);
  * its `honesty.checks` list the six checks `done-needs-artefact`, `not-yet-run-has-artefact`, `outputs-only`,
    `our-scenes`, `local-only-scrub`, `file-guards` once each, every one `pass` with no violation (SC-019-02);
  * its `definition_of_done` reads `studio_tools: 17`, `satisfied: 17`, `missing: []`, `met: true` (SC-019-01);
  * the report is consistent with the index body: a tool counts as satisfied when it lists at least one artefact or
    its page is the evaluated-not-adopted page of the registry (hand re-computation from `tools[].artefacts` and
    `studio/tools.yaml`), so a report that claims 17 of 17 over an empty tool list fails;
  * `tools/check_showcase.py --root <repo>` exits 0 on the committed tree (the CI check of FR-019-33..36 agrees).

Oracle: the schema and a hand re-computation of the definition of done from the registry and the tool entries of the
index; no number is taken from the code that produced the index.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "web" / "public" / "studio" / "index.json"
SCHEMA = ROOT / "specs" / "019-web-studio" / "contracts" / "studio-index.schema.json"
REGISTRY = ROOT / "studio" / "tools.yaml"
CHECK = ROOT / "tools" / "check_showcase.py"
SIX = [
    "done-needs-artefact",
    "not-yet-run-has-artefact",
    "outputs-only",
    "our-scenes",
    "local-only-scrub",
    "file-guards",
]


def _index() -> dict:
    assert INDEX.is_file(), (
        "web/public/studio/index.json is generated at build (DC-019-03) and exists on the release commit"
    )
    return json.loads(INDEX.read_text(encoding="utf-8"))


def _registry() -> list[dict]:
    assert REGISTRY.is_file(), "studio/tools.yaml exists (DC-001-03)"
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["tools"]


@pytest.mark.req("SC-019-01")
def test_the_index_validates_against_the_schema() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(_index()), key=lambda e: list(e.path))
    assert errors == [], [f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors[:5]]


@pytest.mark.req("SC-019-02")
def test_the_six_honesty_checks_are_present_once_and_all_pass_with_no_violation() -> None:
    checks = _index()["honesty"]["checks"]
    assert [c["id"] for c in checks] == SIX
    for c in checks:
        assert c["status"] == "pass", f"{c['id']}: {c['violations']}"
        assert c["violations"] == []


@pytest.mark.req("SC-019-01")
def test_the_definition_of_done_is_17_of_17() -> None:
    done = _index()["honesty"]["definition_of_done"]
    assert done["studio_tools"] == 17
    assert done["satisfied"] == 17
    assert done["missing"] == []
    assert done["met"] is True


@pytest.mark.req("SC-019-01")
def test_the_report_agrees_with_a_hand_recomputation_from_the_registry_and_the_tool_entries() -> None:
    index = _index()
    registry = _registry()
    adopted = [t for t in registry if t["category"] == "studio-tool" and t["status"] != "evaluated-not-adopted"]
    assert len(adopted) == 17, "the registry holds the 17 studio tools of data-model 001 section 4.3"
    listed = {t["id"]: t for t in index["tools"]}
    satisfied = [t["id"] for t in adopted if listed.get(t["id"], {}).get("artefacts")]
    not_adopted_pages = [t["id"] for t in registry if t["status"] == "evaluated-not-adopted" and t["id"] in listed]
    assert sorted(satisfied) == sorted(t["id"] for t in adopted), (
        "each of the 17 studio tools lists at least one artefact; "
        f"missing: {sorted(set(t['id'] for t in adopted) - set(satisfied))}"
    )
    assert len(not_adopted_pages) == 3, "the three evaluated-not-adopted entries have their page"
    reported = index["honesty"]["definition_of_done"]
    assert reported["satisfied"] == len(satisfied)


@pytest.mark.req("SC-019-02")
def test_the_ci_check_agrees_on_the_committed_tree() -> None:
    assert CHECK.is_file(), "tools/check_showcase.py exists (T-019-004)"
    done = subprocess.run(
        [sys.executable, str(CHECK), "--root", str(ROOT)], capture_output=True, text=True, timeout=300, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr
