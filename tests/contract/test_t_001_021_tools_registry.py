"""T-001-021 · the tool-registry schema and the committed ``studio/tools.yaml``: FR-001-25, FR-001-26, FR-001-28.

Oracles: the entry table, the version forms and the 20 tool ids with their statuses of data-model 4.1-4.3 and the
performance-restricted licence list of 5.3 (hand-transcribed in ``contract_support``); the ids of the existing pages
in ``docs/frameworks/`` (``tools.yaml`` ids equal their stems); corpus fixtures with fixed pointers; python
``jsonschema`` as reference validator; lock fixtures written here with known package names.

Expected API: ``contracts/tools.schema.json``, the committed ``studio/tools.yaml`` and ``tools/check_contracts.py``
(``rule: FR-001-25`` for a studio-tool count other than 20; ``rule: FR-001-26`` for an unresolvable lock reference or a
pinned-binary version on a tool without the ``external`` environment, pointer ``/tools/<i>/version``; schema violations
are findings of any rule id with the file and the JSON pointer).
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
VALID = json.loads((cs.FIXTURES / "tools/valid/tools.valid.json").read_text(encoding="utf-8"))
ENTRY = VALID["tools"][0]  # warp: studio-tool, lock version, public
ENVS = ["root", "runner", "studio", "isaac", "rtx", "isaaclab", "kit", "reason", "pipeline", "accel", "web", "external"]
LOCKS = [
    "uv.lock",
    "studio/uv.lock",
    "studio/isaac/uv.lock",
    "studio/rtx/uv.lock",
    "studio/isaaclab/uv.lock",
    "pipeline/uv.lock",
    "pipeline/accel/uv.lock",
    "web/pnpm-lock.yaml",
]
ARTEFACT_KINDS = [
    "video",
    "image",
    "figure",
    "point-cloud",
    "mesh",
    "tiles",
    "splat",
    "onnx",
    "table",
    "trace",
    "shard",
    "field",
    "text",
    "model-card",
    "telemetry",
    "usd",
]


def pairs(doc: Any) -> set[tuple[str, str]]:
    return cs.error_pairs("tools", "#", doc)


def ok(doc: Any) -> bool:
    return cs.accepts("tools", "#", doc)


def with_entry(**changes: Any) -> dict:
    e = {**copy.deepcopy(ENTRY), **changes}
    return {"tools": [e]}


def without(*names: str) -> dict:
    e = copy.deepcopy(ENTRY)
    for n in names:
        del e[n]
    return {"tools": [e]}


def assert_corpus(rule: str, minimum: int) -> None:
    items = [e for e in cs.schema_level(schema="tools") if e["rule"] == rule and not e["valid"]]
    assert len(items) >= minimum, (rule, len(items))
    for e in items:
        assert (e["pointer"], e["keyword"]) in pairs(cs.fixture_json(e)), (e["file"], e["pointer"], e["keyword"])


# ----------------------------------------------------------------------------------------------------------------
# FR-001-25 · schema
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-25")
def test_fr_001_25_valid_example_is_accepted_and_the_document_is_bounded() -> None:
    assert ok(VALID)
    one = VALID["tools"][0]
    many = []
    for i in range(65):
        e = copy.deepcopy(one)
        e["id"], e["docs_page"] = f"tool{i:02d}", f"docs/frameworks/tool{i:02d}.md"
        many.append(e)
    assert ok({"tools": many[:64]})
    assert ("/tools", "maxItems") in pairs({"tools": many})
    assert ("/tools", "minItems") in pairs({"tools": []})
    assert ("", "required") in pairs({})
    assert ("", "additionalProperties") in pairs({"tools": [one], "extra": 1})
    assert ok({"$schema": "../contracts/tools.schema.json", "tools": [one]})


ENTRY_REQUIRED = [
    "id",
    "name",
    "category",
    "envs",
    "version",
    "spdx",
    "osi",
    "licence_class",
    "ring",
    "lane",
    "performance",
    "role",
    "cases",
    "produces",
    "status",
]


@pytest.mark.req("FR-001-25")
@pytest.mark.parametrize("field", ENTRY_REQUIRED)
def test_fr_001_25_every_entry_field_of_data_model_4_1_is_required(field: str) -> None:
    assert ("/tools/0", "required") in pairs(without(field))


@pytest.mark.req("FR-001-25")
@pytest.mark.parametrize("field", ["alternatives_rejected", "notice"])
def test_fr_001_25_optional_entry_fields(field: str) -> None:
    holder = next(t for t in VALID["tools"] if field in t)
    assert ok({"tools": [holder]})
    stripped = {k: v for k, v in holder.items() if k != field}
    assert ok({"tools": [stripped]})


ENTRY_BOUNDS: list[tuple[str, list[Any], list[Any]]] = [
    ("id", ["ab", "warp", "mujoco-warp", "a" * 48], ["a", "", "Warp", "a" * 49, "a_b", "1a", "-a", "a b", "a/b"]),
    ("name", ["x", "n" * 64], ["", "n" * 65, 1]),
    ("category", ["studio-tool", "component"], ["tool", "Studio-Tool", "", None]),
    ("osi", [True, False], ["yes", 1, None]),
    ("licence_class", cs.LICENCE_ORDER, ["Own", "copyleft", "", None]),
    ("ring", ["Adopt", "Trial", "Assess", "Hold"], ["adopt", "Pilot", "", None]),
    ("lane", ["live", "replay", "local-only"], ["static", "Live", "", None]),
    ("performance", ["public", "local-only"], ["private", "Public", None]),
    ("role", ["r", "r" * 300], ["", "r" * 301, 1]),
    ("cases", [[], ["A1"], list(cs.CASE_IDS)], [["Z9"], ["A1", "A1"], [*cs.CASE_IDS, "A1"], "A1", ["a1"]]),
    (
        "produces",
        [[], ["video"], ARTEFACT_KINDS],
        [["hologram"], ["video", "video"], [*ARTEFACT_KINDS, "video"], "video"],
    ),
    ("status", ["not-yet-run", "done"], ["Done", "pending", "", None]),
    ("notice", ["n", "n" * 300], ["n" * 301, 1]),
    (
        "envs",
        [["studio"], ENVS[:4], ["external"]],
        [[], ["studio", "studio"], ENVS[:5], ["docker"], ["Studio"], "studio"],
    ),
    (
        "spdx",
        [["Apache-2.0"], cs.SPDX_ALLOWLIST[:4]],
        [[], ["GPL-3.0-only"], ["MIT", "MIT"], cs.SPDX_ALLOWLIST[:5], "MIT", ["mit"], ["MIT "]],
    ),
]


@pytest.mark.req("FR-001-25")
@pytest.mark.parametrize(("field", "good", "bad"), ENTRY_BOUNDS, ids=[b[0] for b in ENTRY_BOUNDS])
def test_fr_001_25_entry_field_bounds(field: str, good: list[Any], bad: list[Any]) -> None:
    for v in good:
        changes: dict[str, Any] = {field: v}
        if field == "spdx":
            changes["performance"] = "local-only"  # keep the restricted-licence rule out of this test
        if field == "id":
            changes["docs_page"] = f"docs/frameworks/{v}.md"
        got = pairs(with_entry(**changes))
        assert got == set(), (field, v, sorted(got)[:3])
    for v in bad:
        got = pairs(with_entry(**{field: v}))
        assert any(p.startswith(f"/tools/0/{field}") or p == "/tools/0" for p, _ in got), (field, v)


@pytest.mark.req("FR-001-25")
@pytest.mark.parametrize("spdx", cs.SPDX_ALLOWLIST)
def test_fr_001_25_every_allowlisted_spdx_id_is_accepted(spdx: str) -> None:
    assert ok(with_entry(spdx=[spdx], performance="local-only"))


@pytest.mark.req("FR-001-25")
def test_fr_001_25_docs_page_is_required_for_studio_tools_and_has_a_fixed_shape() -> None:
    assert ("/tools/0", "required") in pairs(without("docs_page"))
    component = {**copy.deepcopy(VALID["tools"][3])}  # pitstudio: no docs page
    assert "docs_page" not in component
    assert ok({"tools": [component]})
    for good in ("docs/frameworks/warp.md", "docs/frameworks/a-1.md"):
        assert ok(with_entry(docs_page=good)), good
    not_adopted = {"status": "evaluated-not-adopted", "reason": "Dispatch is per-truck and event-driven; no gain."}
    assert ok(with_entry(docs_page="docs/frameworks/not-adopted-warp.md", **not_adopted))  # the prefix marks them
    assert not ok(with_entry(docs_page="docs/frameworks/warp.md", **not_adopted))
    for bad in (
        "docs/frameworks/not-adopted-warp.md",
        "docs/frameworks/../x.md",
        "/docs/frameworks/warp.md",
        "docs/frameworks/warp.txt",
        "docs/other/warp.md",
        "docs/frameworks/Warp.md",
        "docs/frameworks/a_b.md",
        "docs/frameworks/" + "a" * 65 + ".md",
        "docs\\frameworks\\warp.md",
        "docs/frameworks/sub/warp.md",
        "",
        "docs/frameworks/.md",
    ):
        assert not ok(with_entry(docs_page=bad)), bad


@pytest.mark.req("FR-001-25")
def test_fr_001_25_alternatives_rejected_bounds() -> None:
    alt = {"name": "OR-Tools routing", "reason": "same batch formulation"}
    assert ok(with_entry(alternatives_rejected=[alt] * 8))
    assert not ok(with_entry(alternatives_rejected=[alt] * 9))
    assert not ok(with_entry(alternatives_rejected=[{"name": "", "reason": "r"}]))
    assert not ok(with_entry(alternatives_rejected=[{"name": "n" * 65, "reason": "r"}]))
    assert not ok(with_entry(alternatives_rejected=[{"name": "n", "reason": "r" * 301}]))
    assert not ok(with_entry(alternatives_rejected=[{"name": "n"}]))
    assert not ok(with_entry(alternatives_rejected=[{"name": "n", "reason": "r", "extra": 1}]))


@pytest.mark.req("FR-001-25")
def test_fr_001_25_unknown_entry_fields_are_rejected() -> None:
    for f in ("licence", "license", "version_string", "homepage", "path", "host"):
        assert ("/tools/0", "additionalProperties") in pairs(with_entry(**{f: "x"})), f


@pytest.mark.req("FR-001-25")
def test_fr_001_25_corpus_fixtures() -> None:
    assert_corpus("FR-001-25", 8)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-25 · the committed registry
# ----------------------------------------------------------------------------------------------------------------
def committed() -> dict:
    return yaml.safe_load((cs.ROOT / TOOLS_YAML).read_text(encoding="utf-8"))  # PyYAML is the reference parser


@pytest.mark.req("FR-001-25")
def test_fr_001_25_committed_registry_validates_and_loads_with_the_strict_loader() -> None:
    from pitstudio.contracts import load_yaml

    doc = committed()
    assert ok(doc), sorted(pairs(doc))[:5]
    assert load_yaml(cs.ROOT / TOOLS_YAML) == doc


@pytest.mark.req("FR-001-25")
def test_fr_001_25_exactly_the_20_studio_tools_of_data_model_4_3() -> None:
    tools = committed()["tools"]
    studio = {t["id"]: t["status"] for t in tools if t["category"] == "studio-tool"}
    assert len([t for t in tools if t["category"] == "studio-tool"]) == 20
    assert set(studio) == set(cs.STUDIO_TOOLS_NOT_YET_RUN) | set(cs.STUDIO_TOOLS_NOT_ADOPTED)
    for tid in cs.STUDIO_TOOLS_NOT_YET_RUN:
        assert studio[tid] in ("not-yet-run", "done"), tid
    for tid in cs.STUDIO_TOOLS_NOT_ADOPTED:
        assert studio[tid] == "evaluated-not-adopted", tid
    assert len({t["id"] for t in tools}) == len(tools)


@pytest.mark.req("FR-001-25")
def test_fr_001_25_components_include_the_first_commit_set_and_have_no_docs_page_requirement() -> None:
    comps = {t["id"] for t in committed()["tools"] if t["category"] == "component"}
    assert {"pitstudio", "minephys", "minehaulsim", "oreblocks", "colmap", "brush"} <= comps


@pytest.mark.req("FR-001-25")
def test_fr_001_25_every_studio_tool_has_the_docs_page_its_id_names() -> None:
    for t in committed()["tools"]:
        if t["category"] != "studio-tool":
            continue
        prefix = "not-adopted-" if t["status"] == "evaluated-not-adopted" else ""
        assert t["docs_page"] == f"docs/frameworks/{prefix}{t['id']}.md"
        assert (cs.ROOT / t["docs_page"]).is_file(), t["docs_page"]  # the existing pages of docs/frameworks/


@pytest.mark.req("FR-001-25")
def test_fr_001_25_committed_versions_are_references_and_not_adopted_tools_carry_a_reason() -> None:
    for t in committed()["tools"]:
        assert isinstance(t["version"], dict), t["id"]
        if t["status"] == "evaluated-not-adopted":
            assert len(t["reason"]) >= 20
        else:
            assert "reason" not in t


def repo_with_tools(tmp: Path, fn: Any) -> Path:
    root = cs.clean_repo(tmp)
    cs.edit_yaml(root, TOOLS_YAML, fn)
    return root


def index_of(doc: dict, tool_id: str) -> int:
    return next(i for i, t in enumerate(doc["tools"]) if t["id"] == tool_id)


@pytest.mark.req("FR-001-25")
def test_fr_001_25_checker_requires_exactly_20_studio_tool_entries(tmp_path: Path) -> None:
    clean = cs.run_checker(cs.clean_repo(tmp_path / "ok"))
    assert clean.of("FR-001-25") == [], clean.findings
    assert clean.code == 0

    def drop(d: dict) -> None:
        d["tools"].pop(index_of(d, "openusd"))

    short = cs.run_checker(repo_with_tools(tmp_path / "short", drop))
    assert short.of("FR-001-25"), short.findings

    def add(d: dict) -> None:
        extra = copy.deepcopy(d["tools"][0])
        extra["id"], extra["docs_page"] = "extra-tool", "docs/frameworks/extra-tool.md"
        d["tools"].append(extra)

    long = cs.run_checker(repo_with_tools(tmp_path / "long", add))
    assert long.of("FR-001-25")

    def to_component(d: dict) -> None:  # 19 studio tools + 1 more component
        t = d["tools"][index_of(d, "openusd")]
        t["category"] = "component"
        t.pop("docs_page")

    assert cs.run_checker(repo_with_tools(tmp_path / "comp", to_component)).of("FR-001-25")


# ----------------------------------------------------------------------------------------------------------------
# FR-001-26 · versions are references
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-26")
@pytest.mark.parametrize(
    "literal", ["1.17.0", "v1.17.0", "latest", "", "2.14.1+cu130", 1.17, 1, None, ["1.17.0"], True]
)
def test_fr_001_26_a_literal_version_is_rejected(literal: Any) -> None:
    assert any(p.startswith("/tools/0/version") for p, _ in pairs(with_entry(version=literal)))


@pytest.mark.req("FR-001-26")
@pytest.mark.parametrize(
    ("version", "expected"),
    [({"from_lock": lock, "package": "warp-lang"}, True) for lock in LOCKS]
    + [
        ({"from_binary": "colmap", "release": "3.12.0", "sha256": "a" * 64}, True),
        ({"from_git_tag": "v25.08.00", "repository": "https://github.com/NVIDIA/cuopt"}, True),
        ({"own": True}, True),
        ({"from_lock": "poetry.lock", "package": "warp-lang"}, False),
        ({"from_lock": "../uv.lock", "package": "warp-lang"}, False),
        ({"from_lock": "/abs/uv.lock", "package": "warp-lang"}, False),
        ({"from_lock": "uv.lock ", "package": "warp-lang"}, False),
        ({"from_lock": "web/package-lock.json", "package": "three"}, False),
        ({"from_lock": "uv.lock"}, False),
        ({"package": "warp-lang"}, False),
        ({"from_lock": "uv.lock", "package": "-bad"}, False),
        ({"from_lock": "uv.lock", "package": "a" * 101}, False),
        ({"from_lock": "uv.lock", "package": "p", "version": "1.0"}, False),
        ({"from_lock": "uv.lock", "package": "p", "own": True}, False),
        ({"own": False}, False),
        ({"own": "yes"}, False),
        ({}, False),
        ({"from_binary": "colmap", "release": "3.12.0"}, False),
        ({"from_binary": "COLMAP", "release": "3.12.0", "sha256": "a" * 64}, False),
        ({"from_binary": "colmap", "release": "3.12.0", "sha256": "A" * 64}, False),
        ({"from_git_tag": "v1", "repository": "http://github.com/x/y"}, False),
        ({"from_git_tag": "v1", "repository": "https://u:p@github.com/x/y"}, False),
        ({"from_git_tag": "v1"}, False),
    ],
    ids=lambda v: json.dumps(v)[:70] if isinstance(v, dict) else str(v),
)
def test_fr_001_26_version_reference_forms(version: dict, expected: bool) -> None:
    assert ok(with_entry(version=version)) is expected


@pytest.mark.req("FR-001-26")
def test_fr_001_26_corpus_literal_version_fixture() -> None:
    assert_corpus("FR-001-26", 1)


@pytest.mark.req("FR-001-26")
def test_fr_001_26_clean_registry_resolves_every_lock_reference(tmp_path: Path) -> None:
    assert cs.run_checker(cs.clean_repo(tmp_path)).of("FR-001-26") == []


def _lock_ref(d: dict, tool_id: str, lock: str, package: str) -> None:
    d["tools"][index_of(d, tool_id)]["version"] = {"from_lock": lock, "package": package}


@pytest.mark.req("FR-001-26")
@pytest.mark.parametrize(
    ("tool_id", "lock", "package", "fails"),
    [
        ("warp", "studio/uv.lock", "warp-lang", False),
        ("warp", "studio/uv.lock", "warp-lang-missing", True),
        ("warp", "uv.lock", "warp-lang", True),  # a package of studio/uv.lock is not in the root lock
        ("pytorch", "pipeline/uv.lock", "torch", False),
        ("pytorch", "pipeline/uv.lock", "torchvision", True),
        ("tensorrt", "pipeline/accel/uv.lock", "tensorrt", False),
        ("threejs-r3f-3d-tiles", "web/pnpm-lock.yaml", "three", False),
        ("threejs-r3f-3d-tiles", "web/pnpm-lock.yaml", "three-missing", True),
        ("threejs-r3f-3d-tiles", "web/pnpm-lock.yaml", "pyodide", False),
        ("ovrtx", "studio/rtx/uv.lock", "ovrtx", False),
        ("ovrtx", "studio/rtx/uv.lock", "ovrtx-x", True),
    ],
)
def test_fr_001_26_checker_resolves_lock_references_against_the_lock_files(
    tmp_path: Path, tool_id: str, lock: str, package: str, fails: bool
) -> None:
    root = repo_with_tools(tmp_path, lambda d: _lock_ref(d, tool_id, lock, package))
    res = cs.run_checker(root)
    doc = yaml.safe_load((root / TOOLS_YAML).read_text(encoding="utf-8"))
    pointer = f"/tools/{index_of(doc, tool_id)}"
    hits = res.at("FR-001-26", pointer)
    assert bool(hits) is fails, (tool_id, lock, package, res.findings)
    for f in hits:
        assert tool_id in f["message"]
        assert len(f["message"]) <= 300


@pytest.mark.req("FR-001-26")
def test_fr_001_26_a_lock_file_that_does_not_exist_fails_every_entry_that_refers_to_it(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    (root / "studio/uv.lock").unlink()
    res = cs.run_checker(root)
    doc = yaml.safe_load((root / TOOLS_YAML).read_text(encoding="utf-8"))
    for tid in ("warp", "openusd", "newton", "nvenc-ffmpeg"):  # all refer to studio/uv.lock
        assert res.at("FR-001-26", f"/tools/{index_of(doc, tid)}"), tid
    assert not res.at("FR-001-26", f"/tools/{index_of(doc, 'pytorch')}")


@pytest.mark.req("FR-001-26")
def test_fr_001_26_a_malformed_lock_file_is_a_finding_not_a_traceback(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    (root / "studio/uv.lock").write_bytes(b"\xff\xfe not toml [[[")
    res = cs.run_checker(root)
    assert "Traceback" not in res.stderr
    assert res.code == 1
    assert res.of("FR-001-26")


@pytest.mark.req("FR-001-26")
def test_fr_001_26_a_pinned_binary_version_needs_the_external_environment(tmp_path: Path) -> None:
    def no_external(d: dict) -> None:
        d["tools"][index_of(d, "colmap")]["envs"] = ["pipeline"]

    root = repo_with_tools(tmp_path, no_external)
    res = cs.run_checker(root)
    doc = yaml.safe_load((root / TOOLS_YAML).read_text(encoding="utf-8"))
    assert res.at("FR-001-26", f"/tools/{index_of(doc, 'colmap')}")
    assert not res.at("FR-001-26", f"/tools/{index_of(doc, 'brush')}")


# ----------------------------------------------------------------------------------------------------------------
# FR-001-28 · performance-restricted licences
# ----------------------------------------------------------------------------------------------------------------
UNRESTRICTED = [s for s in cs.SPDX_ALLOWLIST if s not in cs.PERFORMANCE_RESTRICTED]


@pytest.mark.req("FR-001-28")
@pytest.mark.parametrize("spdx", cs.PERFORMANCE_RESTRICTED)
def test_fr_001_28_a_restricted_licence_forces_performance_local_only(spdx: str) -> None:
    assert any(p == "/tools/0/performance" for p, _ in pairs(with_entry(spdx=[spdx], performance="public")))
    assert ok(with_entry(spdx=[spdx], performance="local-only"))


@pytest.mark.req("FR-001-28")
@pytest.mark.parametrize("spdx", UNRESTRICTED)
def test_fr_001_28_other_licences_may_declare_either_marker(spdx: str) -> None:
    assert ok(with_entry(spdx=[spdx], performance="public"))
    assert ok(with_entry(spdx=[spdx], performance="local-only"))


@pytest.mark.req("FR-001-28")
@pytest.mark.parametrize("position", [0, 1, 2, 3])
def test_fr_001_28_a_restricted_id_anywhere_in_the_list_counts(position: int) -> None:
    ids = ["Apache-2.0", "MIT", "BSD-3-Clause", "MPL-2.0"]
    ids[position] = "LicenseRef-NVIDIA-SLA"
    assert any(p == "/tools/0/performance" for p, _ in pairs(with_entry(spdx=ids, performance="public")))
    assert ok(with_entry(spdx=ids, performance="local-only"))


@pytest.mark.req("FR-001-28")
def test_fr_001_28_regular_tensorrt_is_not_restricted_but_tensorrt_rtx_is() -> None:
    assert ok(with_entry(spdx=["LicenseRef-TensorRT-SLA"], performance="public"))
    assert not ok(with_entry(spdx=["LicenseRef-TensorRT-RTX-SLA"], performance="public"))


@pytest.mark.req("FR-001-28")
def test_fr_001_28_corpus_fixture_and_the_committed_registry_obey_the_rule() -> None:
    assert_corpus("FR-001-28", 1)
    for t in committed()["tools"]:
        if set(t["spdx"]) & set(cs.PERFORMANCE_RESTRICTED):
            assert t["performance"] == "local-only", t["id"]
