# ruff: noqa: E501
"""T-014-011: planner skip, `evaluated-not-adopted` registry status and reason for every non-pass probe state.

Requirements: FR-014-03.

Spec: specs/014-robot-learning/spec.md FR-014-03: "If the `isaaclab` probe status in `studio/capabilities.json` is not `pass` (fail, skip, missing entry or invalid file), then `studio plan` shall mark `st60_il_train` and
`st61_il_mpm_eval` as skipped with the reason, the `isaaclab` entry of `studio/tools.yaml` shall be set to `evaluated-not-adopted` with the recorded reason, no IL artefact shall be published, and the Isaac Lab tool page and
the A2/A3 policy panels shall show 'evaluated, not adopted' with the reason." Plan: "capabilities fixtures (fail, skip, missing, invalid) -> planner and registry states". The page and panel states are the E2E task T-014-054.

Oracle: hand-built capability documents in the layout of `contracts/capabilities.schema.json` (one `isaaclab` probe record with status, versions, notes) for each state; the registry `contracts/tools.schema.json` (reference JSON Schema
validation of the resulting registry through `pitstudio.contracts.validate`): an `evaluated-not-adopted` entry needs a `reason` of 20 to 600 characters and a `docs_page` matching `docs/frameworks/not-adopted-<slug>.md`; the committed
`studio/tools.yaml` (entry id `isaac-lab`, the registry id of the tool whose environment and probe id are `isaaclab`) as the base document.

Expected API of the implementation (module `pitstudio.robots.lane_gate`; documents are plain dicts):
    STAGES = ("st60_il_train", "st61_il_mpm_eval") ; TOOL_ID = "isaac-lab" ; PROBE = "isaaclab"
    LaneState: frozen dataclass: adopted (bool), probe_status ("pass" | "fail" | "skip" | "missing" | "invalid"), reason (str | None), skipped (dict[str, str]: stage id -> reason), publish_artefacts (bool),
        panel_state ("available" | "evaluated, not adopted"); method skip_reason(stage_id) -> str | None (the reason for a skipped stage, None for any other stage)
    evaluate_lane(capabilities) -> LaneState
        capabilities: the parsed document (dict), the JSON text (str or bytes) or None (file absent). "pass": adopted, no reason, nothing skipped, publish_artefacts True, panel "available". Every other state (probe
        status fail or skip; no `isaaclab` entry; a document or text that is not valid JSON or not valid against the capability schema; None): not adopted, `skipped` holds BOTH stage ids with the reason, publish_artefacts
        False, panel "evaluated, not adopted"; the reason is a text of at least 20 characters that names the state ("fail", "skip", "missing" or "invalid") and, when the probe record has notes or an `error`, contains the first of
        them; it is at most 600 characters.
    apply_to_tools(tools_doc, state) -> dict
        a deep copy of the registry document; when the lane is not adopted the entry with id "isaac-lab" gets status "evaluated-not-adopted", reason = state.reason and docs_page "docs/frameworks/not-adopted-isaac-lab.md", and every other
        entry is unchanged; when adopted the document is returned unchanged (equal). ValueError naming `tools_doc` when it has no `tools` list or no entry "isaac-lab".
    filter_publishable(artefacts, state) -> list[dict]
        artefacts are dicts with a "stage" key; when the lane is not adopted every artefact of st60_il_train or st61_il_mpm_eval is dropped, the rest kept in order; when adopted the list is returned unchanged
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from pitstudio.robots.lane_gate import (
    PROBE,
    STAGES,
    TOOL_ID,
    apply_to_tools,
    evaluate_lane,
    filter_publishable,
)

from pitstudio.contracts.validate import validate

ROOT = Path(__file__).resolve().parents[2]
TOOLS = yaml.safe_load((ROOT / "studio" / "tools.yaml").read_text("utf-8"))
REAL_CAPS = json.loads((ROOT / "studio" / "capabilities.json").read_text("utf-8"))


def caps(status="pass", *, notes=None, entry=True, other=None) -> dict:
    probes = dict(other or {})
    if entry:
        rec = {"status": status, "versions": {"python": "3.12.15", "torch": "2.11.0+cu128"}}
        if notes is not None:
            rec["notes"] = notes
        probes[PROBE] = rec
    return {
        "generated": "2026-10-12",
        "gpu": "NVIDIA RTX 5000 Ada Generation Laptop GPU",
        "driver": "582.78",
        "probes": probes,
    }


def not_adopted(state) -> None:
    assert state.adopted is False
    assert set(state.skipped) == set(STAGES)
    assert all(isinstance(r, str) and len(r) >= 20 for r in state.skipped.values())
    assert state.publish_artefacts is False
    assert state.panel_state == "evaluated, not adopted"
    assert isinstance(state.reason, str)
    assert 20 <= len(state.reason) <= 600


@pytest.mark.req("FR-014-03")
def test_constants() -> None:
    assert STAGES == ("st60_il_train", "st61_il_mpm_eval")
    assert TOOL_ID == "isaac-lab"
    assert PROBE == "isaaclab"


# ------------------------------------------------------------------------------------------------ pass
@pytest.mark.req("FR-014-03")
def test_a_passing_probe_adopts_the_lane() -> None:
    st = evaluate_lane(caps("pass"))
    assert st.adopted is True
    assert st.probe_status == "pass"
    assert st.reason is None
    assert st.skipped == {}
    assert st.publish_artefacts is True
    assert st.panel_state == "available"
    assert st.skip_reason("st60_il_train") is None


@pytest.mark.req("FR-014-03")
def test_the_committed_report_of_this_repository_is_read_without_error() -> None:
    st = evaluate_lane(REAL_CAPS)
    assert st.probe_status == REAL_CAPS["probes"]["isaaclab"]["status"]
    assert st.adopted is (REAL_CAPS["probes"]["isaaclab"]["status"] == "pass")


@pytest.mark.req("FR-014-03")
def test_the_json_text_form_gives_the_same_state_as_the_document() -> None:
    doc = caps("fail", notes=["Cartpole training diverged: non-finite loss at iteration 3"])
    assert evaluate_lane(json.dumps(doc)) == evaluate_lane(doc)
    assert evaluate_lane(json.dumps(doc).encode("utf-8")) == evaluate_lane(doc)


# ------------------------------------------------------------------------------------------------ non-pass states
@pytest.mark.req("FR-014-03")
@pytest.mark.parametrize(("status", "word"), [("fail", "fail"), ("skip", "skip")])
def test_a_failed_or_skipped_probe_skips_both_stages_with_the_recorded_reason(status, word) -> None:
    note = "kit-less smoke failed: torch sees no CUDA device on this host"
    st = evaluate_lane(caps(status, notes=[note, "second note"]))
    not_adopted(st)
    assert st.probe_status == status
    assert word in st.reason
    assert note in st.reason  # the recorded reason travels to the registry and the panels
    assert note in st.skip_reason("st60_il_train")
    assert note in st.skip_reason("st61_il_mpm_eval")
    assert st.skip_reason("s50_evaluate") is None
    assert st.skip_reason("") is None


@pytest.mark.req("FR-014-03")
@pytest.mark.parametrize("status", ["fail", "skip"])
def test_a_non_pass_probe_without_notes_still_gets_a_reason_naming_the_state(status) -> None:
    st = evaluate_lane(caps(status, notes=None))
    not_adopted(st)
    assert status in st.reason
    st = evaluate_lane(caps(status, notes=[]))
    not_adopted(st)


@pytest.mark.req("FR-014-03")
def test_a_missing_probe_entry_is_not_adopted_and_says_missing() -> None:
    st = evaluate_lane(caps(entry=False, other={"warp_newton": {"status": "pass", "versions": {"python": "3.14.4"}}}))
    not_adopted(st)
    assert st.probe_status == "missing"
    assert "missing" in st.reason


@pytest.mark.req("FR-014-03")
def test_an_absent_file_is_the_missing_state() -> None:
    st = evaluate_lane(None)
    not_adopted(st)
    assert st.probe_status in ("missing", "invalid")


@pytest.mark.req("FR-014-03")
@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "not json at all",
        "{",
        "[]",
        "null",
        "42",
        '{"probes": 5}',
        '{"generated": "2026-10-12"}',
        b"\xff\xfe\x00\x00",
        "\x00\x01",
    ],
)
def test_text_that_is_not_a_valid_capability_document_is_the_invalid_state(bad) -> None:
    st = evaluate_lane(bad)
    not_adopted(st)
    assert st.probe_status in ("invalid", "missing")


@pytest.mark.req("FR-014-03")
@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["probes"]["isaaclab"].update(status="maybe"),
        lambda d: d["probes"]["isaaclab"].update(status=None),
        lambda d: d["probes"]["isaaclab"].pop("versions"),
        lambda d: d["probes"]["isaaclab"].update(zz_unknown=1),
        lambda d: d.update(driver="not-a-version"),
        lambda d: d.update(generated="12/10/2026"),
        lambda d: d.pop("gpu"),
        lambda d: d.update(zz_extra=True),
    ],
    ids=[
        "status-maybe",
        "status-null",
        "no-versions",
        "unknown-member",
        "bad-driver",
        "bad-date",
        "no-gpu",
        "extra-root-member",
    ],
)
def test_a_document_that_breaks_the_capability_schema_is_invalid_even_if_the_status_says_pass(mutate) -> None:
    doc = caps("pass")
    mutate(doc)
    st = evaluate_lane(doc)
    not_adopted(st)
    assert st.probe_status == "invalid"
    assert "invalid" in st.reason


@pytest.mark.req("FR-014-03")
def test_other_probes_failing_do_not_affect_the_isaaclab_lane() -> None:
    other = {
        "warp_newton": {"status": "fail", "versions": {"python": "3.14.4"}},
        "nvenc": {"status": "skip", "versions": {"python": "3.14.4"}},
    }
    st = evaluate_lane(caps("pass", other=other))
    assert st.adopted is True


@pytest.mark.req("FR-014-03")
def test_a_very_long_or_unicode_note_still_gives_a_bounded_reason() -> None:
    long_note = "x" * 5000
    st = evaluate_lane(caps("fail", notes=[long_note]))
    assert 20 <= len(st.reason) <= 600
    uni = evaluate_lane(caps("fail", notes=["falla: dispositivo CUDA no disponible 中文 \U0001f6a7"]))
    assert "CUDA" in uni.reason
    assert 20 <= len(uni.reason) <= 600


# ------------------------------------------------------------------------------------------------ registry
def entry(doc: dict, tool_id: str = TOOL_ID) -> dict:
    return next(t for t in doc["tools"] if t["id"] == tool_id)


@pytest.mark.req("FR-014-03")
@pytest.mark.parametrize("status", ["fail", "skip"])
def test_the_registry_entry_becomes_evaluated_not_adopted_with_the_recorded_reason(status) -> None:
    note = "kit-less smoke failed: torch sees no CUDA device on this host"
    st = evaluate_lane(caps(status, notes=[note]))
    out = apply_to_tools(TOOLS, st)
    e = entry(out)
    assert e["status"] == "evaluated-not-adopted"
    assert e["reason"] == st.reason
    assert note in e["reason"]
    assert e["docs_page"] == "docs/frameworks/not-adopted-isaac-lab.md"


@pytest.mark.req("FR-014-03")
@pytest.mark.parametrize(
    "state_doc",
    [caps("fail", notes=["x" * 40]), caps("skip"), caps(entry=False), "not json", None],
    ids=["fail", "skip", "missing", "invalid", "absent"],
)
def test_the_resulting_registry_is_valid_against_the_tools_schema_for_every_non_pass_state(state_doc) -> None:
    out = apply_to_tools(TOOLS, evaluate_lane(state_doc))
    assert validate(out, "tools") == []


@pytest.mark.req("FR-014-03")
@pytest.mark.parametrize("state_doc", [caps("fail"), caps("skip"), caps(entry=False)], ids=["fail", "skip", "missing"])
def test_every_other_registry_entry_and_the_input_are_untouched(state_doc) -> None:
    before = copy.deepcopy(TOOLS)
    out = apply_to_tools(TOOLS, evaluate_lane(state_doc))
    assert before == TOOLS  # the input document is not modified
    assert [t for t in out["tools"] if t["id"] != TOOL_ID] == [t for t in before["tools"] if t["id"] != TOOL_ID]
    assert {k: v for k, v in entry(out).items() if k not in ("status", "reason", "docs_page")} == {
        k: v for k, v in entry(before).items() if k not in ("status", "reason", "docs_page")
    }


@pytest.mark.req("FR-014-03")
def test_an_adopted_lane_leaves_the_registry_unchanged() -> None:
    assert apply_to_tools(TOOLS, evaluate_lane(caps("pass"))) == TOOLS


@pytest.mark.req("FR-014-03")
@pytest.mark.parametrize("bad", [{}, {"tools": []}, {"tools": [{"id": "newton"}]}, {"tools": "x"}, [], None])
def test_a_registry_without_the_isaac_lab_entry_is_rejected_naming_the_argument(bad) -> None:
    with pytest.raises(ValueError, match=r"tools_doc"):
        apply_to_tools(bad, evaluate_lane(caps("fail")))


# ------------------------------------------------------------------------------------------------ artefacts
@pytest.mark.req("FR-014-03")
def test_no_il_artefact_is_published_when_the_lane_is_not_adopted() -> None:
    arts = [
        {"stage": "s50_evaluate", "id": "table"},
        {"stage": "st60_il_train", "id": "il1-policy"},
        {"stage": "st61_il_mpm_eval", "id": "il2b-table"},
        {"stage": "s60_export", "id": "model"},
        {"stage": "st60_il_train", "id": "il2-policy"},
    ]
    kept = filter_publishable(arts, evaluate_lane(caps("fail")))
    assert [a["id"] for a in kept] == ["table", "model"]
    kept_pass = filter_publishable(arts, evaluate_lane(caps("pass")))
    assert kept_pass == arts
    assert filter_publishable([], evaluate_lane(caps("skip"))) == []
