"""T-001-025 · post-schema path and string rules of ``validate``: FR-001-56, FR-001-57.

Oracles:
* FR-001-56: the Windows reserved device names (CON, PRN, AUX, NUL, COM1-COM9, LPT1-LPT9) of the Microsoft naming
  conventions for files, applied by hand to a table of paths; case folding with ``str.casefold``.
* FR-001-57: three reference regex engines evaluated on the same strings: Python ``re`` (accepts ``"id\\n"`` for
  ``^...$``), pydantic-core's Rust engine and Node's ``RegExp`` (both reject it); the characters U+0000-U+001F.

Expected API: ``pitstudio.contracts.validate(document, schema_name)`` returns error objects with ``pointer``,
``keyword`` and ``message``; the post-schema rules add an error at the JSON pointer of the offending string (for a
case-folded duplicate: the pointer of the later path), and report nothing for strings the schema does not
constrain by ``pattern``.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_support as cs


def load(rel: str) -> Any:
    return json.loads((cs.FIXTURES / rel).read_text(encoding="utf-8"))


RUN = load("manifest/valid/manifest.valid.json")
WEB = load("manifest/valid/manifest.valid-web-index.json")
REC = load("recipe/valid/recipe.valid.json")
TOOLS = load("tools/valid/tools.valid.json")
SRC = load("sources/valid/sources.valid.json")
CAP = load("capabilities/valid/capabilities.valid.json")
JOB = load("recipe/valid/recipe.valid-job-request.json")


def validate(doc: Any, name: str) -> list[Any]:
    from pitstudio.contracts import validate as impl

    return impl(doc, name)


def pointers(doc: Any, name: str) -> list[str]:
    return [cs.get(e, "pointer") for e in validate(doc, name)]


def setp(doc: Any, path: list[Any], value: Any) -> Any:
    d = copy.deepcopy(doc)
    node = d
    for p in path[:-1]:
        node = node[p]
    node[path[-1]] = value
    return d


def ptr(path: list[Any]) -> str:
    return "/" + "/".join(str(p) for p in path)


DEVICE_VALUES = {
    dn: [dn, dn.lower(), dn.title(), dn + ".txt", dn.lower() + ".log", dn.title() + ".JSON"]
    for dn in cs.WINDOWS_DEVICE_NAMES
}
ACCEPTED_NAMES = [
    "console.txt",
    "com10",
    "com10.txt",
    "com0",
    "lpt0.log",
    "aux1",
    "auxiliary",
    "communicate.json",
    "nulls",
    "prn_1",
    "con-1",
    "lpt",
    "com",
    "xcon",
    "nul0",
    "a.con",
    "a.aux.txt",
    "cons",
]


def recipe_with_outputs(paths: list[str]) -> tuple[dict, list[str]]:
    """A recipe whose single stage lists ``paths`` as outputs; returns the document and the expected pointers."""
    stage = copy.deepcopy(REC["stages"][0])
    stage["outputs"] = [{"path": p, "schema": "json-file"} for p in paths]
    doc = copy.deepcopy(REC)
    doc["stages"] = [stage]
    return doc, [f"/stages/0/outputs/{i}/path" for i in range(len(paths))]


# ----------------------------------------------------------------------------------------------------------------
# FR-001-56 · Windows device names
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-56")
@pytest.mark.parametrize("device", cs.WINDOWS_DEVICE_NAMES)
def test_fr_001_56_every_device_name_in_any_case_with_or_without_an_extension_is_rejected(device: str) -> None:
    for value in DEVICE_VALUES[device]:
        doc, expected = recipe_with_outputs([value])
        assert expected[0] in pointers(doc, "recipe"), value
    for value in (f"raw/{device}/x.json", f"{device.lower()}/a/b.json", f"a/b/{device.title()}.txt"):
        doc, expected = recipe_with_outputs([value])
        assert expected[0] in pointers(doc, "recipe"), value  # a directory segment counts as well


@pytest.mark.req("FR-001-56")
def test_fr_001_56_names_that_only_look_like_device_names_are_accepted() -> None:
    doc, _ = recipe_with_outputs(ACCEPTED_NAMES)
    assert pointers(doc, "recipe") == []
    doc, _ = recipe_with_outputs([f"raw/{n}/x.json" for n in ACCEPTED_NAMES])
    assert pointers(doc, "recipe") == []


@pytest.mark.req("FR-001-56")
def test_fr_001_56_each_flagged_value_is_reported_at_its_own_pointer_in_one_call() -> None:
    values = ["ok-1.json", "con.txt", "ok-2.json", "Lpt1.log", "COM9.json", "ok-3.json", "aux"]
    doc, expected = recipe_with_outputs(values)
    got = set(pointers(doc, "recipe"))
    assert {expected[1], expected[3], expected[4], expected[6]} <= got
    assert not {expected[0], expected[2], expected[5]} & got


@pytest.mark.req("FR-001-56")
@pytest.mark.parametrize(
    ("name", "path", "value"),
    [
        ("manifest#/$defs/run", ["artefacts", 1, "path"], "assets/runs/20261007T120000Z-a2-haulage/con.txt"),
        ("manifest#/$defs/run", ["artefacts", 1, "path"], "assets/AUX/x.json"),
        ("manifest#/$defs/run", ["stages", 0, "outputs", 0, "name"], "media/Lpt1.log"),
        ("manifest#/$defs/run", ["stages", 0, "outputs", 0, "name"], "nul"),
        ("recipe", ["stages", 0, "outputs", 0, "path"], "raw/prn.json"),
        ("sources", ["sources", 0, "card"], "data/cards/aux.md"),
        ("sources", ["sources", 0, "files", 0, "name"], "com1.zip"),
        ("sources", ["sources", 0, "files", 1, "extract", 0], "tiles/aux/*.laz"),
        ("sources", ["sources", 0, "files", 1, "extract", 1], "con.txt"),
        ("tools", ["tools", 0, "docs_page"], "docs/frameworks/con.md"),
    ],
    ids=[
        "run-artefact-file",
        "run-artefact-dir",
        "run-output-name",
        "run-output-bare",
        "recipe-output",
        "source-card",
        "source-file-name",
        "source-extract-dir",
        "source-extract-file",
        "tool-docs-page",
    ],
)
def test_fr_001_56_rule_applies_to_every_relative_path_kind(name: str, path: list[Any], value: str) -> None:
    base = {"manifest": RUN, "recipe": REC, "sources": SRC, "tools": TOOLS}[name.split("#")[0]]
    doc = setp(base, path, value)
    if path[:3] == ["tools", 0, "docs_page"]:
        doc = setp(doc, ["tools", 0, "id"], "con")
    assert ptr(path) in pointers(doc, name), (name, ptr(path), value)


@pytest.mark.req("FR-001-56")
def test_fr_001_56_web_index_paths_too() -> None:
    doc = setp(WEB, ["artefacts", 1, "path"], "assets/runs/x/Lpt1.log")
    assert "/artefacts/1/path" in pointers(doc, "manifest#/$defs/web_index")
    assert pointers(WEB, "manifest#/$defs/web_index") == []


@pytest.mark.req("FR-001-56")
def test_fr_001_56_valid_documents_of_every_path_bearing_kind_report_nothing() -> None:
    assert pointers(RUN, "manifest#/$defs/run") == []
    assert pointers(REC, "recipe") == []
    assert pointers(SRC, "sources") == []
    assert pointers(TOOLS, "tools") == []


@pytest.mark.req("FR-001-56")
@pytest.mark.parametrize(
    ("paths", "second_flagged"),
    [
        (["raw/A.json", "raw/a.json"], True),
        (["Raw/a.json", "raw/A.JSON"], True),
        (["a.json", "a.json"], True),  # identical paths are equal after case folding too
        (["a.json", "b.json"], False),
        (["a.json", "a.json.bak"], False),
        (["a/b.json", "a/B.json", "c.json"], True),
        (["x/y.json", "X/Z.json"], False),
    ],
)
def test_fr_001_56_two_paths_equal_after_case_folding_are_rejected_at_the_later_pointer(
    paths: list[str], second_flagged: bool
) -> None:
    doc, expected = recipe_with_outputs(paths)
    got = pointers(doc, "recipe")
    later = next(
        (expected[j] for j in range(1, len(paths)) if paths[j].casefold() in [p.casefold() for p in paths[:j]]), None
    )
    assert (later is not None) is second_flagged  # the table agrees with the casefold oracle
    if later is not None:
        assert later in got, (paths, got)
        assert expected[0] not in got  # the first occurrence is never the one reported
    else:
        assert got == []


@pytest.mark.req("FR-001-56")
def test_fr_001_56_case_folded_duplicates_in_manifests_and_sources() -> None:
    art = copy.deepcopy(RUN["artefacts"][1])
    art["id"], art["path"] = "a2-encode-report-2", RUN["artefacts"][1]["path"].upper().replace("ASSETS/", "assets/")
    doc = copy.deepcopy(RUN)
    doc["artefacts"].append(art)
    assert "/artefacts/2/path" in pointers(doc, "manifest#/$defs/run")
    src = copy.deepcopy(SRC)
    src["sources"][0]["files"][0]["name"] = "Tile.laz"
    src["sources"][0]["files"][1]["name"] = "tile.LAZ"
    assert "/sources/0/files/1/name" in pointers(src, "sources")
    extract = copy.deepcopy(SRC)
    extract["sources"][0]["files"][1]["extract"] = ["tiles/*.laz", "TILES/*.LAZ"]
    assert "/sources/0/files/1/extract/1" in pointers(extract, "sources")


@pytest.mark.req("FR-001-56")
def test_fr_001_56_corpus_fixtures_of_the_class() -> None:
    items = [e for e in cs.entries(rule="FR-001-56", tag_in=("post-schema",))]
    assert {e["kind"] for e in items} >= {"run", "web-index", "recipe", "tools", "sources"}
    for e in items:
        target = f"{e['schema']}{e['target']}" if e["target"] != "#" else e["schema"]
        assert e["pointer"] in pointers(cs.fixture_json(e), target), e["file"]


# ----------------------------------------------------------------------------------------------------------------
# FR-001-57 · control characters in patterned strings
# ----------------------------------------------------------------------------------------------------------------
NODE = "const [p, s] = JSON.parse(process.argv[1]); process.stdout.write(String(new RegExp(p).test(s)));"


def node_accepts(pattern: str, value: str) -> bool:
    proc = subprocess.run(
        ["node", "-e", NODE, json.dumps([pattern, value])], capture_output=True, text=True, check=True, timeout=60
    )
    return proc.stdout == "true"


@pytest.mark.req("FR-001-57")
def test_fr_001_57_the_reference_engines_disagree_on_a_trailing_newline() -> None:
    """The gap the rule closes: Python re accepts 'id\\n' for ^...$, the Rust engine and ECMAScript do not."""
    from pydantic_core import SchemaValidator, ValidationError, core_schema

    pattern = cs.PATTERNS["slug"][0]
    assert re.search(pattern, "a2-haulage\n") is not None  # Python re (what python jsonschema uses)
    assert not node_accepts(pattern, "a2-haulage\n")  # ECMAScript
    validator = SchemaValidator(core_schema.str_schema(pattern=pattern))
    assert validator.validate_python("a2-haulage") == "a2-haulage"
    with pytest.raises(ValidationError):
        validator.validate_python("a2-haulage\n")  # pydantic-core, Rust regex


CONTROL_CHARS = [chr(c) for c in range(0x20)]


@pytest.mark.req("FR-001-57")
@pytest.mark.parametrize("char", CONTROL_CHARS, ids=lambda c: f"U+{ord(c):04X}")
def test_fr_001_57_every_control_character_in_a_patterned_string_is_reported(char: str) -> None:
    for position in ("end", "middle"):
        value = "a2-haulage" + char if position == "end" else "a2" + char + "haulage"
        doc = setp(JOB, ["recipe"], value)
        assert "/recipe" in pointers(doc, "recipe#/$defs/job_request"), (position, repr(value))


@pytest.mark.req("FR-001-57")
@pytest.mark.parametrize(
    ("name", "base", "path"),
    [
        ("manifest#/$defs/run", RUN, ["profile"]),
        ("manifest#/$defs/run", RUN, ["artefacts", 0, "id"]),
        ("manifest#/$defs/run", RUN, ["artefacts", 0, "sha256"]),
        ("manifest#/$defs/web_index", WEB, ["artefacts", 0, "id"]),
        ("manifest#/$defs/web_index", WEB, ["generated"]),
        ("recipe", REC, ["id"]),
        ("recipe", REC, ["stages", 0, "entry"]),
        ("recipe", REC, ["stages", 0, "outputs", 0, "path"]),
        ("recipe#/$defs/job_request", JOB, ["profile"]),
        ("tools", TOOLS, ["tools", 0, "id"]),
        ("sources", SRC, ["sources", 0, "id"]),
        ("sources", SRC, ["sources", 0, "landing_url"]),
        ("capabilities", CAP, ["driver"]),
        ("capabilities", CAP, ["generated"]),
    ],
    ids=[
        "run-profile",
        "run-artefact-id",
        "run-artefact-sha",
        "web-artefact-id",
        "web-generated",
        "recipe-id",
        "recipe-entry",
        "recipe-output",
        "job-profile",
        "tools-id",
        "sources-id",
        "sources-url",
        "caps-driver",
        "caps-generated",
    ],
)
def test_fr_001_57_trailing_newline_after_an_anchored_value_is_reported_in_every_document_kind(
    name: str, base: Any, path: list[Any]
) -> None:
    node = base
    for p in path:
        node = node[p]
    assert pointers(base, name) == []
    assert ptr(path) in pointers(setp(base, path, node + "\n"), name), (name, path)
    assert ptr(path) in pointers(setp(base, path, node + "\t"), name)
    assert ptr(path) in pointers(setp(base, path, node + "\x00"), name)


@pytest.mark.req("FR-001-57")
def test_fr_001_57_strings_without_a_pattern_may_hold_line_breaks_and_tabs() -> None:
    assert pointers(setp(REC, ["description"], "line one\nline two\ttabbed"), "recipe") == []
    assert pointers(setp(RUN, ["notes", 0], "line one\nline two"), "manifest#/$defs/run") == []
    failed = copy.deepcopy(RUN)
    failed["stages"][0].update(status="failed", error_class="oom", exit_code=1, log_tail="trace:\n\tline 1\n\tline 2\n")
    assert pointers(failed, "manifest#/$defs/run") == []
    assert pointers(setp(SRC, ["sources", 0, "title"], "multi\nline\ttitle"), "sources") == []
    assert pointers(setp(CAP, ["probes", "isaacsim", "notes", 0], "a\nb"), "capabilities") == []
    assert pointers(setp(TOOLS, ["tools", 0, "role"], "a\nb"), "tools") == []


@pytest.mark.req("FR-001-57")
def test_fr_001_57_corpus_fixtures_of_the_class_in_all_seven_document_kinds() -> None:
    items = [e for e in cs.entries(rule="FR-001-57", tag_in=("post-schema",))]
    assert {e["kind"] for e in items} == {
        "run",
        "web-index",
        "recipe",
        "job-request",
        "tools",
        "sources",
        "capabilities",
    }
    for e in items:
        target = f"{e['schema']}{e['target']}" if e["target"] != "#" else e["schema"]
        doc = cs.fixture_json(e)
        assert cs.accepts(e["schema"], e["target"], doc), e["file"]  # the schema alone lets it through (the gap)
        assert e["pointer"] in pointers(doc, target), e["file"]


@pytest.mark.req("FR-001-57")
def test_fr_001_57_error_messages_stay_short_and_name_no_absolute_path() -> None:
    doc = setp(JOB, ["recipe"], "a2-haulage\n")
    for e in validate(doc, "recipe#/$defs/job_request"):
        msg = cs.get(e, "message")
        assert len(msg) <= 300
        assert not cs.has_absolute_path(msg)
