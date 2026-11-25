"""T-001-031 · cross-file rules of the contract checker: FR-001-53, FR-001-29, FR-001-33.

Oracles: hand-built repository trees derived from the committed clean fixture repository (a registry of 26 tools, a
source registry with three pinned sources, one published run manifest and the web index), each with one seeded
inconsistency and the pointer it must be reported at; corpus fixtures for the schema-level part of FR-001-53.

Expected API: ``tools/check_contracts.py`` findings with ``rule`` ``FR-001-53`` (pointer ``/tools/<i>/docs_page``),
``FR-001-29`` (``/stages/<i>/tool``, ``/stages/<i>/env`` and ``/artefacts/<i>/producer/tool`` of a manifest) and
``FR-001-33`` (``/stages/<i>/inputs/<j>/id`` and ``/artefacts/<i>/inputs/<j>/id`` for an unknown input,
``.../inputs/<j>`` for an unpinned source); every message names the tool, source or artefact and is at most 300
characters. Knowledge rows of the ``minephys`` tables (``kind: knowledge``) cannot be resolved without the pinned
tables and are not exercised here.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_support as cs

TOOLS_YAML = "studio/tools.yaml"
SOURCES_YAML = "data/sources.yaml"
INDEX = "web/public/assets/manifest.json"
VALID_TOOLS = json.loads((cs.FIXTURES / "tools/valid/tools.valid.json").read_text(encoding="utf-8"))


def run_rel(root: Path) -> str:
    return next(p.relative_to(root).as_posix() for p in (root / "web/public/assets/runs").glob("*/manifest.json"))


def tool_index(root: Path, tool_id: str) -> int:
    doc = yaml.safe_load((root / TOOLS_YAML).read_text(encoding="utf-8"))
    return next(i for i, t in enumerate(doc["tools"]) if t["id"] == tool_id)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-53 · evaluated-not-adopted tools
# ----------------------------------------------------------------------------------------------------------------
def not_adopted(**changes: Any) -> dict:
    e = copy.deepcopy(VALID_TOOLS["tools"][2])  # cuopt
    e.update(changes)
    return {"tools": [e]}


@pytest.mark.req("FR-001-53")
@pytest.mark.parametrize(
    ("n", "expected"), [(0, False), (1, False), (19, False), (20, True), (21, True), (600, True), (601, False)]
)
def test_fr_001_53_reason_is_20_to_600_characters(n: int, expected: bool) -> None:
    assert cs.accepts("tools", "#", not_adopted(reason="r" * n)) is expected


@pytest.mark.req("FR-001-53")
def test_fr_001_53_reason_is_required_for_evaluated_not_adopted_and_forbidden_otherwise() -> None:
    doc = not_adopted()
    del doc["tools"][0]["reason"]
    assert ("/tools/0", "required") in cs.error_pairs("tools", "#", doc)
    adopted = copy.deepcopy(VALID_TOOLS)
    adopted["tools"][0]["reason"] = "A reason that is long enough to pass the length bound."
    assert not cs.accepts("tools", "#", adopted)
    for status in ("not-yet-run", "done"):
        d = not_adopted(status=status, docs_page="docs/frameworks/cuopt.md")
        assert not cs.accepts("tools", "#", d), status  # still carries a reason


@pytest.mark.req("FR-001-53")
def test_fr_001_53_not_adopted_pages_use_the_prefix_and_other_pages_do_not() -> None:
    assert cs.accepts("tools", "#", not_adopted(docs_page="docs/frameworks/not-adopted-cuopt.md"))
    assert not cs.accepts("tools", "#", not_adopted(docs_page="docs/frameworks/cuopt.md"))


@pytest.mark.req("FR-001-53")
def test_fr_001_53_corpus_fixtures_of_the_class() -> None:
    items = [e for e in cs.schema_level(schema="tools") if e["rule"] == "FR-001-53" and not e["valid"]]
    assert len(items) >= 4
    for e in items:
        assert (e["pointer"], e["keyword"]) in cs.error_pairs("tools", "#", cs.fixture_json(e)), e["file"]


@pytest.mark.req("FR-001-53")
def test_fr_001_53_clean_registry_has_no_docs_page_finding(tmp_path: Path) -> None:
    assert cs.run_checker(cs.clean_repo(tmp_path)).of("FR-001-53") == []


@pytest.mark.req("FR-001-53")
@pytest.mark.parametrize(
    ("tool_id", "page"),
    [
        ("cuopt", "docs/frameworks/not-adopted-cuopt.md"),
        ("physicsnemo", "docs/frameworks/not-adopted-physicsnemo.md"),
        ("warp", "docs/frameworks/warp.md"),
        ("pytorch", "docs/frameworks/pytorch.md"),
    ],
)
def test_fr_001_53_a_missing_docs_page_is_reported_at_the_entry(tmp_path: Path, tool_id: str, page: str) -> None:
    root = cs.clean_repo(tmp_path)
    (root / page).unlink()
    res = cs.run_checker(root)
    hits = res.at("FR-001-53", f"/tools/{tool_index(root, tool_id)}")
    assert hits, res.findings
    assert all(tool_id in f["message"] and len(f["message"]) <= 300 for f in hits)
    others = [f for f in res.of("FR-001-53") if not f["pointer"].startswith(f"/tools/{tool_index(root, tool_id)}")]
    assert others == []


@pytest.mark.req("FR-001-53")
def test_fr_001_53_a_page_that_exists_but_is_not_the_entrys_own_is_reported(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)

    def swap(d: dict) -> None:
        d["tools"][tool_index_of(d, "warp")]["docs_page"] = "docs/frameworks/newton.md"  # exists, but not warp's

    cs.edit_yaml(root, TOOLS_YAML, swap)
    res = cs.run_checker(root)
    assert res.at("FR-001-53", f"/tools/{tool_index(root, 'warp')}")


def tool_index_of(doc: dict, tool_id: str) -> int:
    return next(i for i, t in enumerate(doc["tools"]) if t["id"] == tool_id)


@pytest.mark.req("FR-001-53")
def test_fr_001_53_a_short_reason_and_a_reason_on_an_adopted_tool_fail_the_checker_with_the_pointer(
    tmp_path: Path,
) -> None:
    root = cs.clean_repo(tmp_path)
    cs.edit_yaml(root, TOOLS_YAML, lambda d: d["tools"][tool_index_of(d, "cuopt")].update(reason="too short"))
    res = cs.run_checker(root)
    i = tool_index(root, "cuopt")
    assert res.in_file(TOOLS_YAML, f"/tools/{i}/reason")
    assert res.code == 1
    root2 = cs.clean_repo(tmp_path / "b")
    cs.edit_yaml(
        root2,
        TOOLS_YAML,
        lambda d: d["tools"][tool_index_of(d, "warp")].update(reason="A reason on an adopted tool, long."),
    )
    assert cs.run_checker(root2).in_file(TOOLS_YAML, f"/tools/{tool_index(root2, 'warp')}")


# ----------------------------------------------------------------------------------------------------------------
# FR-001-29 · producer tool and stage environment against the registry
# ----------------------------------------------------------------------------------------------------------------
def edit_run(root: Path, fn: Any) -> None:
    cs.edit_json(root, run_rel(root), fn)


@pytest.mark.req("FR-001-29")
def test_fr_001_29_clean_manifests_pass(tmp_path: Path) -> None:
    assert cs.run_checker(cs.clean_repo(tmp_path)).of("FR-001-29") == []


@pytest.mark.req("FR-001-29")
@pytest.mark.parametrize("bad_tool", ["no-such-tool", "nvenc-ffmpeg-2", "warp-lang", "x" * 20])
def test_fr_001_29_a_stage_tool_that_is_not_a_registry_id_is_reported(tmp_path: Path, bad_tool: str) -> None:
    root = cs.clean_repo(tmp_path)
    edit_run(root, lambda d: d["stages"][0].update(tool=bad_tool))
    res = cs.run_checker(root)
    hits = [f for f in res.at("FR-001-29", "/stages/0") if f["file"] == run_rel(root)]
    assert hits, res.findings
    assert all(bad_tool in f["message"] and len(f["message"]) <= 300 for f in hits)


@pytest.mark.req("FR-001-29")
@pytest.mark.parametrize(
    ("stage", "tool", "env", "fails"),
    [
        (0, "nvenc-ffmpeg", "studio", False),  # nvenc-ffmpeg runs in studio
        (0, "nvenc-ffmpeg", "pipeline", True),
        (0, "nvenc-ffmpeg", "isaac", True),
        (1, "ovrtx", "rtx", False),
        (1, "ovrtx", "studio", True),
        (2, "pitstudio", "pipeline", False),  # components are valid producers in their envs
        (2, "pitstudio", "accel", True),
        (2, "pitstudio", "studio", True),
    ],
)
def test_fr_001_29_the_stage_environment_must_be_one_of_the_tools_envs(
    tmp_path: Path, stage: int, tool: str, env: str, fails: bool
) -> None:
    root = cs.clean_repo(tmp_path)
    edit_run(root, lambda d: d["stages"][stage]["env"].update(name=env))
    res = cs.run_checker(root)
    hits = [f for f in res.at("FR-001-29", f"/stages/{stage}") if f["file"] == run_rel(root)]
    assert bool(hits) is fails, (tool, env, res.findings)
    for f in hits:
        assert tool in f["message"]
        assert len(f["message"]) <= 300


@pytest.mark.req("FR-001-29")
@pytest.mark.parametrize("where", ["run", "index"])
def test_fr_001_29_an_artefact_producer_that_is_not_a_registry_id_is_reported(tmp_path: Path, where: str) -> None:
    root = cs.clean_repo(tmp_path)
    if where == "run":
        edit_run(root, lambda d: d["artefacts"][0]["producer"].update(tool="no-such-tool"))
        file = run_rel(root)
    else:
        cs.edit_json(root, INDEX, lambda d: d["artefacts"][0]["producer"].update(tool="no-such-tool"))
        file = INDEX
    res = cs.run_checker(root)
    hits = [f for f in res.at("FR-001-29", "/artefacts/0/producer") if f["file"] == file]
    assert hits, res.findings
    assert all("no-such-tool" in f["message"] for f in hits)
    assert [f for f in res.at("FR-001-29", "/artefacts/1") if f["file"] == file] == []


@pytest.mark.req("FR-001-29")
def test_fr_001_29_a_recipe_stage_tool_must_exist_in_the_registry(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    rel = "studio/recipes/cases/a2-haulage.yaml"
    cs.edit_yaml(root, rel, lambda d: d["stages"][1].update(tool="no-such-tool"))
    res = cs.run_checker(root)
    assert res.in_file(rel, "/stages/1/tool"), res.findings
    assert res.in_file(rel, "/stages/0") == []


# ----------------------------------------------------------------------------------------------------------------
# FR-001-33 · manifest inputs against sources and same-run artefacts; unpinned sources
# ----------------------------------------------------------------------------------------------------------------
def at33(res: cs.CheckResult, file: str, prefix: str) -> list[dict]:
    return [f for f in res.at("FR-001-33", prefix) if f["file"] == file]


@pytest.mark.req("FR-001-33")
def test_fr_001_33_clean_manifests_pass(tmp_path: Path) -> None:
    assert cs.run_checker(cs.clean_repo(tmp_path)).of("FR-001-33") == []


@pytest.mark.req("FR-001-33")
@pytest.mark.parametrize(
    "input_id", ["no-such-source", "example-station", "Example-station-hourly".lower() + "-x", "a2-frames"]
)
def test_fr_001_33_a_stage_input_must_be_a_source_or_a_same_run_artefact(tmp_path: Path, input_id: str) -> None:
    root = cs.clean_repo(tmp_path)
    edit_run(root, lambda d: d["stages"][0]["inputs"][0].update(id=input_id))
    res = cs.run_checker(root)
    hits = at33(res, run_rel(root), "/stages/0/inputs/0")
    assert hits, res.findings
    assert all(input_id in f["message"] and len(f["message"]) <= 300 for f in hits)


@pytest.mark.req("FR-001-33")
def test_fr_001_33_an_artefact_input_may_name_a_source_or_an_artefact_of_the_same_run(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    ok_inputs = [
        {"id": "example-station-hourly", "sha256": "7" * 64, "kind": "source"},
        {"id": "a2-haul-clip", "sha256": "0" * 64, "kind": "artefact"},
    ]
    edit_run(
        root,
        lambda d: d["artefacts"][1].update(
            inputs=ok_inputs,
            licence_class="attribution",
            attribution="Station data: Example Weather Service, CC BY 4.0.",
        ),
    )
    assert at33(cs.run_checker(root), run_rel(root), "/artefacts/1/inputs") == []
    bad = [
        {"id": "example-station-hourly", "sha256": "7" * 64, "kind": "source"},
        {"id": "no-such-artefact", "sha256": "0" * 64, "kind": "artefact"},
    ]
    root2 = cs.clean_repo(tmp_path / "b")
    edit_run(root2, lambda d: d["artefacts"][1].update(inputs=bad))
    res = cs.run_checker(root2)
    hits = at33(res, run_rel(root2), "/artefacts/1/inputs/1")
    assert hits
    assert all("no-such-artefact" in f["message"] for f in hits)
    assert at33(res, run_rel(root2), "/artefacts/1/inputs/0") == []


@pytest.mark.req("FR-001-33")
def test_fr_001_33_the_web_index_checks_its_source_inputs_too(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    cs.edit_json(root, INDEX, lambda d: d["artefacts"][0]["inputs"][0].update(id="no-such-source"))
    res = cs.run_checker(root)
    assert at33(res, INDEX, "/artefacts/0/inputs/0")


def unpin(d: dict, which: int = 0) -> None:
    d["sources"][1]["files"][which]["sha256"] = None  # example-station-hourly


@pytest.mark.req("FR-001-33")
def test_fr_001_33_a_published_run_may_not_use_a_source_without_a_pinned_sha256(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    cs.edit_yaml(root, SOURCES_YAML, unpin)
    res = cs.run_checker(root)
    stage_hits = at33(res, run_rel(root), "/stages/0/inputs/0")
    assert stage_hits, res.findings
    assert all("example-station-hourly" in f["message"] and len(f["message"]) <= 300 for f in stage_hits)
    assert at33(res, run_rel(root), "/artefacts/0/inputs/0")  # the artefact built from it as well
    assert at33(res, INDEX, "/artefacts/0/inputs/0")  # and the web index, whose artefacts are all published
    assert at33(res, run_rel(root), "/stages/1") == []  # other stages use no source


@pytest.mark.req("FR-001-33")
def test_fr_001_33_one_unpinned_file_among_pinned_ones_is_enough(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)

    def add_unpinned_second_file(d: dict) -> None:
        extra = copy.deepcopy(d["sources"][1]["files"][0])
        extra["url"], extra["sha256"] = "https://example.org/api/stations?id=124&format=csv", None
        d["sources"][1]["files"].append(extra)

    cs.edit_yaml(root, SOURCES_YAML, add_unpinned_second_file)
    assert at33(cs.run_checker(root), run_rel(root), "/stages/0/inputs/0")


@pytest.mark.req("FR-001-33")
def test_fr_001_33_sources_without_files_and_fully_pinned_sources_are_fine(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    cs.edit_yaml(root, SOURCES_YAML, lambda d: d["sources"][1].update(files=[]))
    assert at33(cs.run_checker(root), run_rel(root), "/stages/0/inputs/0") == []


@pytest.mark.req("FR-001-33")
def test_fr_001_33_an_unpublished_run_may_use_an_unpinned_source(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    cs.edit_yaml(root, SOURCES_YAML, unpin)
    edit_run(root, lambda d: d.update(published=False))
    res = cs.run_checker(root)
    assert at33(res, run_rel(root), "/stages/0/inputs/0") == []
