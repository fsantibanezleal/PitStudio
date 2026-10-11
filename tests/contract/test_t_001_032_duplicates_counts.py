"""T-001-032 · duplicate ids and shard counts: FR-001-54, FR-001-55.

Oracles: hand-built documents (two artefacts sharing an id, a registry with a repeated tool id, a stage with
``shards.done`` = ``total`` + 1 and = ``total``) with the expected pointers fixed by construction; corpus fixtures of
the classes (tagged ``post-schema``: the JSON Schema alone accepts them).

Expected API: ``pitstudio.contracts.validate`` reports, for a duplicate id, an error at the pointer of the later entry
whose pointer or message also names the pointer of the first one; for ``shards.done > shards.total`` an error at a
pointer below ``/stages/<i>/shards``; ``tools/check_contracts.py`` reports the same as ``rule: FR-001-54`` /
``FR-001-55`` findings (file, pointer, message).
"""

from __future__ import annotations

import copy
import json
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
TOOLS = load("tools/valid/tools.valid.json")


def validate(doc: Any, name: str) -> list[Any]:
    from pitstudio.contracts import validate as impl

    return impl(doc, name)


def text_of(errors: list[Any]) -> str:
    return " ".join(f"{cs.get(e, 'pointer')} {cs.get(e, 'message')}" for e in errors)


def with_ids(doc: dict, key: str, ids: list[str]) -> dict:
    d = copy.deepcopy(doc)
    base = d[key]
    d[key] = [copy.deepcopy(base[i % len(base)]) for i in range(len(ids))]
    for entry, ident in zip(d[key], ids, strict=True):
        entry["id"] = ident
    if key == "artefacts":
        for i, entry in enumerate(d[key]):
            entry["path"] = f"assets/runs/r/file-{i}.json"  # distinct paths: keep FR-001-56 out of this test
    return d


# ----------------------------------------------------------------------------------------------------------------
# FR-001-54
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-54")
@pytest.mark.parametrize(
    ("ids", "expected_dups"),
    [
        (["a", "b"], []),
        (["a", "a"], [(0, 1)]),
        (["a", "b", "a"], [(0, 2)]),
        (["a", "a", "a"], [(0, 1), (0, 2)]),
        (["a", "b", "b", "c", "a"], [(1, 2), (0, 4)]),
        (["a"], []),
        (["a-1", "a_1", "a1"], []),  # different ids that merely look alike
    ],
)
def test_fr_001_54_duplicate_artefact_ids_in_a_run_manifest_name_both_pointers(
    ids: list[str], expected_dups: list[tuple[int, int]]
) -> None:
    doc = with_ids(RUN, "artefacts", ids)
    errors = validate(doc, "manifest#/$defs/run")
    flagged = {cs.get(e, "pointer") for e in errors}
    if not expected_dups:
        assert errors == []
        return
    text = text_of(errors)
    for first, later in expected_dups:
        assert f"/artefacts/{later}" in flagged, (ids, flagged)
        assert f"/artefacts/{first}" in text, (ids, text)  # the first occurrence is named as well
    for e in errors:
        assert len(cs.get(e, "message")) <= 300


@pytest.mark.req("FR-001-54")
def test_fr_001_54_web_index_and_tool_registry_have_the_same_rule() -> None:
    web = with_ids(WEB, "artefacts", ["same-id", "other", "same-id"])
    errors = validate(web, "manifest#/$defs/web_index")
    assert "/artefacts/2" in {cs.get(e, "pointer") for e in errors}
    assert "/artefacts/0" in text_of(errors)
    tools = with_ids(TOOLS, "tools", ["warp", "ovrtx", "cuopt", "pitstudio", "colmap"])
    assert validate(tools, "tools") == []
    tools["tools"][3]["id"] = "warp"
    errors = validate(tools, "tools")
    assert "/tools/3" in {cs.get(e, "pointer") for e in errors}
    assert "/tools/0" in text_of(errors)


@pytest.mark.req("FR-001-54")
def test_fr_001_54_the_run_manifest_and_registry_examples_are_accepted() -> None:
    assert validate(RUN, "manifest#/$defs/run") == []
    assert validate(WEB, "manifest#/$defs/web_index") == []
    assert validate(TOOLS, "tools") == []


@pytest.mark.req("FR-001-54")
def test_fr_001_54_the_same_id_in_two_different_documents_is_fine() -> None:
    assert validate(RUN, "manifest#/$defs/run") == []
    assert validate(WEB, "manifest#/$defs/web_index") == []
    assert RUN["artefacts"][0]["id"] == WEB["artefacts"][1]["id"]  # a2-haul-clip appears in both documents


@pytest.mark.req("FR-001-54")
def test_fr_001_54_corpus_fixtures_of_the_class() -> None:
    items = [e for e in cs.entries(rule="FR-001-54", tag_in=("post-schema",))]
    assert {e["kind"] for e in items} == {"run", "web-index", "tools"}
    for e in items:
        name = f"{e['schema']}{e['target']}" if e["target"] != "#" else e["schema"]
        doc = cs.fixture_json(e)
        assert cs.accepts(e["schema"], e["target"], doc)  # only validate() can see it
        errors = validate(doc, name)
        assert e["pointer"] in {cs.get(x, "pointer") for x in errors}, e["file"]
        assert e["first_pointer"] in text_of(errors), e["file"]


# ----------------------------------------------------------------------------------------------------------------
# FR-001-55
# ----------------------------------------------------------------------------------------------------------------
def with_shards(total: int, done: int) -> dict:
    d = copy.deepcopy(RUN)
    d["stages"][0]["shards"] = {"total": total, "done": done}
    return d


@pytest.mark.req("FR-001-55")
@pytest.mark.parametrize(
    ("total", "done", "fails"),
    [
        (3, 3, False),
        (3, 4, True),
        (3, 0, False),
        (3, 2, False),
        (1, 1, False),
        (1, 2, True),
        (10_000, 10_000, False),
        (4, 5, True),
        (100, 101, True),
        (100, 1_000, True),
    ],
)
def test_fr_001_55_done_may_not_exceed_total_in_a_run_manifest(total: int, done: int, fails: bool) -> None:
    errors = validate(with_shards(total, done), "manifest#/$defs/run")
    flagged = [cs.get(e, "pointer") for e in errors if cs.get(e, "pointer").startswith("/stages/0/shards")]
    assert bool(flagged) is fails, (total, done, errors)
    for e in errors:
        assert len(cs.get(e, "message")) <= 300


@pytest.mark.req("FR-001-55")
def test_fr_001_55_the_rule_applies_to_every_stage_that_has_shards() -> None:
    d = copy.deepcopy(RUN)
    d["stages"][0]["shards"] = {"total": 2, "done": 2}
    d["stages"][1]["shards"] = {"total": 2, "done": 3}
    errors = validate(d, "manifest#/$defs/run")
    pointers = {cs.get(e, "pointer") for e in errors}
    assert any(p.startswith("/stages/1/shards") for p in pointers)
    assert not any(p.startswith("/stages/0/shards") for p in pointers)


@pytest.mark.req("FR-001-55")
def test_fr_001_55_stages_without_shards_are_unaffected() -> None:
    assert "shards" not in RUN["stages"][0]
    assert validate(RUN, "manifest#/$defs/run") == []


@pytest.mark.req("FR-001-55")
def test_fr_001_55_corpus_fixture() -> None:
    items = cs.entries(rule="FR-001-55", tag_in=("post-schema",))
    assert items
    for e in items:
        doc = cs.fixture_json(e)
        assert cs.accepts(e["schema"], e["target"], doc)
        assert any(
            cs.get(x, "pointer").startswith(e["pointer"]) for x in validate(doc, f"{e['schema']}{e['target']}")
        ), e["file"]


# ----------------------------------------------------------------------------------------------------------------
# both rules through the checker
# ----------------------------------------------------------------------------------------------------------------
def run_manifest(root: Path) -> str:
    return next(p.relative_to(root).as_posix() for p in (root / "web/public/assets/runs").glob("*/manifest.json"))


@pytest.mark.req("FR-001-54")
def test_fr_001_54_checker_reports_duplicate_artefact_ids_in_the_web_index_and_registry(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    cs.edit_json(
        root, "web/public/assets/manifest.json", lambda d: d["artefacts"][1].update(id=d["artefacts"][0]["id"])
    )
    res = cs.run_checker(root)
    hits = res.at("FR-001-54", "/artefacts/1")
    assert hits
    assert "/artefacts/0" in (hits[0]["pointer"] + hits[0]["message"])
    assert all(len(f["message"]) <= 300 for f in hits)
    root2 = cs.clean_repo(tmp_path / "t")
    cs.edit_yaml(root2, "studio/tools.yaml", lambda d: d["tools"][3].update(id=d["tools"][0]["id"]))
    res2 = cs.run_checker(root2)
    assert res2.at("FR-001-54", "/tools/3")


@pytest.mark.req("FR-001-55")
def test_fr_001_55_checker_reports_shards_done_above_total_in_a_published_run(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    cs.edit_json(root, run_manifest(root), lambda d: d["stages"][0].update(shards={"total": 3, "done": 4}))
    res = cs.run_checker(root)
    assert res.at("FR-001-55", "/stages/0/shards")
    ok_root = cs.clean_repo(tmp_path / "ok")
    cs.edit_json(ok_root, run_manifest(ok_root), lambda d: d["stages"][0].update(shards={"total": 3, "done": 3}))
    assert cs.run_checker(ok_root).of("FR-001-55") == []
