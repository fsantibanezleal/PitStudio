"""T-019-092: a tool-map edge from a tool to itself fails the studio build check, naming the tool.

Requirements: FR-019-46 (hostile-input class found by the G5 review; the other tool-map checks of FR-019-38 are
T-019-001 and the layout of FR-019-02 is T-019-003).

Spec: specs/019-web-studio/ (spec.md FR-019-46, plan.md test strategy row "FR-019-46", tasks.md T-019-092; the example
corpus lists "edge from a tool to itself" as `not_schema_checkable`, by the checker).

Expected API of the implementation (new module `tools/check_studio.py`, imported through `sys.path`; the spec names no
Python module for the build check, so the name is fixed here and flagged in the red report):
  Finding                          an object with attributes `check` (error class), `subject` (tool id), `pointer`
                                   (JSON pointer into the tool map, "/edges/<index>"), `detail`
  check_toolmap(toolmap: dict, tools: list[dict]) -> list[Finding]
      `toolmap` is studio/toolmap.yaml (DC-019-02: bands[{id, tools[]}], edges[{from, to, kind}]); `tools` the registry
      entries (studio/tools.yaml). For FR-019-46 a finding of class "toolmap-self-edge" is returned for every edge whose
      `from` equals its `to`, subject = that tool id, pointer = "/edges/<index of the edge>".
  CLI: `python tools/check_studio.py --root DIR` reads DIR/studio/toolmap.yaml and DIR/studio/tools.yaml, prints one
  line "<check>: <subject>: <pointer>" per finding, exit 0 when clean, 1 with findings, 2 on a usage error or unreadable
  input (message naming the file, never a traceback).

Oracle: hand calculation (a map fixture with the edge (a, a) gives exactly one failure naming `a`; the same fixture
without it, and the edges (a, b) and (b, a), give none).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "check_studio.py"
sys.path.insert(0, str(ROOT / "tools"))

BANDS = ["scene", "physics", "sensors-synthetic-data", "training", "acceleration", "encoding", "web"]


def _mod():
    assert TOOL.is_file(), "tools/check_studio.py exists (T-019-092)"
    import check_studio

    return check_studio


def _tool(tid: str) -> dict:
    return {
        "id": tid,
        "name": tid,
        "category": "studio-tool",
        "envs": ["studio"],
        "version": {"own": True},
        "spdx": ["Apache-2.0"],
        "osi": True,
        "licence_class": "attribution",
        "ring": "Adopt",
        "lane": "replay",
        "performance": "public",
        "role": "r",
        "cases": [],
        "produces": [],
        "status": "not-yet-run",
        "docs_page": f"docs/frameworks/{tid}.md",
    }


def _map(tools: list[str], edges: list[tuple[str, str]]) -> dict:
    bands = [{"id": b, "tools": []} for b in BANDS]
    for i, t in enumerate(tools):
        bands[i % len(BANDS)]["tools"].append(t)
    return {"bands": bands, "edges": [{"from": a, "to": b, "kind": "table"} for a, b in edges]}


def _self_edges(findings) -> list[tuple[str, str]]:
    return [(f.subject, f.pointer) for f in findings if f.check == "toolmap-self-edge"]


@pytest.mark.req("FR-019-46")
def test_an_edge_from_a_tool_to_itself_fails_naming_the_tool_and_the_edge() -> None:
    m = _mod()
    found = m.check_toolmap(_map(["a", "b"], [("a", "b"), ("a", "a")]), [_tool("a"), _tool("b")])
    assert _self_edges(found) == [("a", "/edges/1")]


@pytest.mark.req("FR-019-46")
def test_the_same_map_without_the_self_edge_and_a_two_tool_cycle_are_clean() -> None:
    m = _mod()
    tools = [_tool("a"), _tool("b")]
    assert _self_edges(m.check_toolmap(_map(["a", "b"], [("a", "b")]), tools)) == []
    assert _self_edges(m.check_toolmap(_map(["a", "b"], [("a", "b"), ("b", "a")]), tools)) == []
    assert _self_edges(m.check_toolmap(_map(["a", "b"], []), tools)) == []


@pytest.mark.req("FR-019-46")
def test_every_self_edge_is_reported_with_its_own_index() -> None:
    m = _mod()
    tools = [_tool(t) for t in "abc"]
    found = m.check_toolmap(_map(["a", "b", "c"], [("a", "a"), ("a", "b"), ("c", "c"), ("b", "b"), ("c", "c")]), tools)
    assert _self_edges(found) == [("a", "/edges/0"), ("c", "/edges/2"), ("b", "/edges/3"), ("c", "/edges/4")]


@pytest.mark.req("FR-019-46")
def test_a_self_edge_is_reported_whether_or_not_the_tool_is_in_the_registry() -> None:
    m = _mod()
    found = m.check_toolmap(_map(["a"], [("ghost", "ghost")]), [_tool("a")])
    assert ("ghost", "/edges/0") in _self_edges(found)


@pytest.mark.req("FR-019-46")
def test_ids_are_compared_exactly_not_case_folded_or_normalised() -> None:
    m = _mod()
    tools = [_tool("a"), _tool("b")]
    assert _self_edges(m.check_toolmap(_map(["a", "b"], [("a", "A")]), tools)) == []
    assert _self_edges(m.check_toolmap(_map(["a", "b"], [("a", "a ")]), tools)) == []


@pytest.mark.req("FR-019-46")
@pytest.mark.parametrize("tid", ["hélice-中", "x" * 48, "a-b-c-d"])
def test_hostile_and_long_ids_are_reported_verbatim(tid: str) -> None:
    m = _mod()
    found = m.check_toolmap(_map([tid], [(tid, tid)]), [_tool(tid)])
    assert _self_edges(found) == [(tid, "/edges/0")]


@pytest.mark.req("FR-019-46")
@pytest.mark.parametrize(
    "edges",
    [None, "edges", 3, [None], [{}], [{"from": "a"}], [{"from": 1, "to": 1}], [["a", "a"]]],
    ids=["none", "string", "number", "null-edge", "empty-edge", "no-to", "non-string", "list-edge"],
)
def test_malformed_edge_lists_do_not_raise(edges) -> None:
    m = _mod()
    doc = {"bands": [{"id": "scene", "tools": ["a"]}], "edges": edges}
    result = m.check_toolmap(doc, [_tool("a")])
    assert isinstance(result, list)
    assert _self_edges(result) == []


@pytest.mark.req("FR-019-46")
def test_the_valid_example_of_the_spec_has_no_self_edge() -> None:
    import json

    m = _mod()
    doc = json.loads((ROOT / "specs/019-web-studio/contracts/examples/toolmap.valid.json").read_text("utf-8"))
    listed = [t for b in doc["bands"] for t in b["tools"]]
    assert _self_edges(m.check_toolmap(doc, [_tool(t) for t in listed])) == []


def _root(tmp_path: Path, toolmap: dict, tools: list[str]) -> Path:
    (tmp_path / "studio").mkdir(parents=True)
    (tmp_path / "studio" / "toolmap.yaml").write_text(yaml.safe_dump(toolmap, sort_keys=False), encoding="utf-8")
    (tmp_path / "studio" / "tools.yaml").write_text(
        yaml.safe_dump({"tools": [_tool(t) for t in tools]}, sort_keys=False), encoding="utf-8"
    )
    return tmp_path


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    assert TOOL.is_file(), "tools/check_studio.py exists (T-019-092)"
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=120, check=False)


@pytest.mark.req("FR-019-46")
def test_cli_fails_with_exit_one_naming_the_tool_for_a_self_edge(tmp_path: Path) -> None:
    root = _root(tmp_path, _map(["a", "b"], [("a", "b"), ("b", "b")]), ["a", "b"])
    done = _cli("--root", str(root))
    assert done.returncode == 1, done.stdout + done.stderr
    assert "toolmap-self-edge: b: /edges/1" in done.stdout
    assert "Traceback" not in done.stderr


@pytest.mark.req("FR-019-46")
def test_cli_clean_map_exits_zero(tmp_path: Path) -> None:
    root = _root(tmp_path, _map(["a", "b"], [("a", "b")]), ["a", "b"])
    done = _cli("--root", str(root))
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.req("FR-019-46")
def test_cli_usage_error_and_unreadable_map_exit_two(tmp_path: Path) -> None:
    assert _cli("--bogus").returncode == 2
    missing = _cli("--root", str(tmp_path / "nowhere"))
    assert missing.returncode == 2
    assert "Traceback" not in missing.stderr
    (tmp_path / "studio").mkdir()
    (tmp_path / "studio" / "toolmap.yaml").write_text("bands: [ {", encoding="utf-8")
    (tmp_path / "studio" / "tools.yaml").write_text("tools: []", encoding="utf-8")
    broken = _cli("--root", str(tmp_path))
    assert broken.returncode == 2
    assert "toolmap.yaml" in broken.stderr
    assert "Traceback" not in broken.stderr
