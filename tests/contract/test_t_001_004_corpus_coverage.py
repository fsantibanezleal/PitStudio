"""T-001-004 · the conformance corpus (DC-001-08) and the shared strategies (data-model 8.3).

Oracles: the corpus is its own fixture set (hand-built; the draft examples of specs/001-contracts/contracts/examples
plus fixtures written for every applicable cell of data-model 8.2). The verdict of each fixture is decided by python
``jsonschema`` (reference implementation) against the promoted ``contracts/*.schema.json``; the strategy tests draw
documents that must validate and mutate them to break exactly one rule.

Expected API: none (this file tests data and test helpers); it fails until the schemas are promoted to ``contracts/``
(T-001-001) because every verdict is computed from them.
"""

from __future__ import annotations

import functools
import json
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_support as cs
import strategies

KINDS = ["run", "web-index", "recipe", "job-request", "tools", "sources", "capabilities"]
ALLOWED_TAGS = {"loader", "conditional", "post-schema", "cross-file"}
# data-model 8.2, transcribed by hand: hostile class -> document kinds that must have at least one invalid fixture
MATRIX = {
    "non-finite": ["run", "web-index", "recipe", "sources", "capabilities"],
    "wrong-type": KINDS,
    "wrong-shape": KINDS,
    "empty": KINDS,
    "oversized": KINDS,
    "malformed-syntax": KINDS,
    "unknown-field": KINDS,
    "unknown-enum": KINDS,
    "path-traversal": KINDS,
    "injection": ["recipe", "job-request", "sources"],
    "duplicate": KINDS,
    "out-of-range": ["run", "web-index", "recipe", "sources"],
    "inconsistent-counts": ["run"],
    "device-name": ["run", "web-index", "recipe", "tools", "sources"],
    "control-char": KINDS,
    "yaml-specific": ["recipe", "tools", "sources"],
    "licence-honesty": ["run", "web-index", "tools", "sources", "capabilities"],
}
SCHEMA_STEM_TARGET = {
    "run": ("manifest", "#/$defs/run"),
    "web-index": ("manifest", "#/$defs/web_index"),
    "recipe": ("recipe", "#"),
    "job-request": ("recipe", "#/$defs/job_request"),
    "tools": ("tools", "#"),
    "sources": ("sources", "#"),
    "capabilities": ("capabilities", "#"),
}
SLOW = settings(
    max_examples=200,  # thresholds.yaml property_tests.ci_examples_per_test
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much],
)


@functools.cache
def _validator(stem: str, target: str):
    return cs.validator_for(stem, target)


def _errors(kind: str, doc: object, entry: dict | None = None) -> set[tuple[str, str]]:
    stem, target = (entry["schema"], entry["target"]) if entry else SCHEMA_STEM_TARGET[kind]
    out = []
    for e in _validator(stem, target).iter_errors(doc):
        stack = [e]
        while stack:
            cur = stack.pop()
            out.append((cs.pointer_of(cur), str(cur.validator)))
            stack.extend(cur.context or [])
    return set(out)


# ----------------------------------------------------------------------------------------------------------------
# the corpus itself
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("DC-001-08")
def test_dc_001_08_index_lists_existing_files_with_complete_records() -> None:
    entries = cs.load_index()
    assert len(entries) >= 150
    files = [e["file"] for e in entries]
    assert len(files) == len(set(files)), "a fixture is listed twice"
    for e in entries:
        assert set(e) >= {"file", "schema", "target", "kind", "valid", "class", "rule", "pointer", "keyword", "tags"}, e
        assert cs.fixture_file(e).is_file(), e["file"]
        assert e["schema"] in cs.SCHEMA_STEMS
        assert e["kind"] in KINDS
        assert e["file"].startswith(f"{e['schema']}/{'valid' if e['valid'] else 'invalid'}/"), e["file"]
        assert set(e["tags"]) <= ALLOWED_TAGS, e
        if e["valid"]:
            assert e["rule"] is None
            assert e["tags"] == []
        else:
            assert e["rule"], e
            assert e["rule"].split("-")[0] in {"FR", "NFR"}, e
            assert e["pointer"] is not None
            assert e["keyword"] is not None


@pytest.mark.req("DC-001-08")
def test_dc_001_08_no_unlisted_fixture_and_every_file_is_small() -> None:
    listed = {e["file"] for e in cs.load_index()}
    on_disk = {
        p.relative_to(cs.FIXTURES).as_posix()
        for p in cs.FIXTURES.rglob("*")
        if p.is_file() and p.relative_to(cs.FIXTURES).parts[0] not in ("repo", "index.json")
    }
    assert on_disk == listed
    assert all(p.stat().st_size < 100_000 for p in cs.FIXTURES.rglob("*") if p.is_file())


@pytest.mark.req("NFR-001-03")
def test_nfr_001_03_every_applicable_cell_of_the_hostile_class_matrix_has_an_invalid_fixture() -> None:
    have = {(e["kind"], e["class"]) for e in cs.entries(valid=False)}
    missing = [(c, k) for c, kinds in MATRIX.items() for k in kinds if (k, c) not in have]
    assert missing == []


@pytest.mark.req("NFR-001-03")
def test_nfr_001_03_one_valid_example_per_document_kind_and_yaml_twins_for_yaml_kinds() -> None:
    valid = cs.entries(valid=True)
    assert {e["kind"] for e in valid} == set(KINDS)
    yaml_valid = {e["schema"] for e in valid if e["file"].endswith(".yaml")}
    assert yaml_valid == {"recipe", "tools", "sources"}
    for e in valid:
        if e["file"].endswith(".yaml"):
            assert (cs.FIXTURES / e["json_twin"]).is_file()


@pytest.mark.req("NFR-001-03")
def test_nfr_001_03_every_hostile_class_names_a_known_rule() -> None:
    classes = {e["class"] for e in cs.entries(valid=False)}
    assert set(MATRIX) <= classes


@pytest.mark.req("DC-001-08")
def test_dc_001_08_valid_fixtures_are_accepted_by_the_reference_validator() -> None:
    checked = 0
    for e in cs.entries(valid=True):
        if not e["file"].endswith(".json"):
            continue
        assert _errors(e["kind"], cs.fixture_json(e), e) == set(), e["file"]
        checked += 1
    assert checked >= 11


@pytest.mark.req("DC-001-08")
def test_dc_001_08_schema_level_hostile_fixtures_fail_at_the_indexed_pointer_and_keyword() -> None:
    checked = 0
    for e in cs.schema_level():
        if e["valid"]:
            continue
        pairs = _errors(e["kind"], cs.fixture_json(e), e)
        assert (e["pointer"], e["keyword"]) in pairs, (e["file"], e["pointer"], e["keyword"], sorted(pairs)[:5])
        checked += 1
    assert checked >= 120


@pytest.mark.req("DC-001-08")
def test_dc_001_08_post_schema_and_cross_file_fixtures_pass_the_schema_alone() -> None:
    """The classes only `validate` or the checker can catch are, by construction, valid JSON Schema documents."""
    checked = 0
    for e in cs.entries(tag_in=("post-schema", "cross-file")):
        if not e["file"].endswith(".json"):
            continue
        errs = _errors(e["kind"], cs.fixture_json(e), e)
        assert (e["pointer"], e["keyword"]) not in errs, e["file"]
        assert errs == set(), (e["file"], sorted(errs)[:3])
        checked += 1
    assert checked >= 20


@pytest.mark.req("DC-001-08")
def test_dc_001_08_loader_fixtures_are_listed_with_the_error_they_expect() -> None:
    loader = cs.entries(tag_in=("loader",))
    assert len(loader) >= 40
    kinds_by_error = {e["loader_error"] for e in loader}
    assert kinds_by_error >= {
        "non-finite",
        "duplicate-key",
        "bom",
        "invalid-utf8",
        "depth",
        "syntax",
        "empty",
        "alias",
        "tag",
        "multi-document",
        "non-string-key",
    }


@pytest.mark.req("DC-001-08")
def test_dc_001_08_clean_repository_fixture_exists_with_every_document_kind() -> None:
    for rel in (
        "studio/tools.yaml",
        "data/sources.yaml",
        "studio/recipes/cases/a2-haulage.yaml",
        "studio/recipes/_bench/bench-smoke.yaml",
        "studio/capabilities.json",
        "web/public/assets/manifest.json",
    ):
        assert (cs.CLEAN_REPO / rel).is_file(), rel
    assert list((cs.CLEAN_REPO / "web/public/assets/runs").glob("*/manifest.json"))
    index = json.loads((cs.CLEAN_REPO / "web/public/assets/manifest.json").read_text(encoding="utf-8"))
    for a in index["artefacts"]:
        data = (cs.CLEAN_REPO / "web/public" / a["path"]).read_bytes()
        assert (a["bytes"], a["sha256"]) == (len(data), cs.sha256_hex(data)), a["id"]  # hashlib is the oracle


# ----------------------------------------------------------------------------------------------------------------
# the shared strategies
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("DC-001-08")
@SLOW
@given(doc=strategies.recipes())
def test_strategy_recipes_validate(doc: dict) -> None:
    assert _errors("recipe", doc) == set()


@pytest.mark.req("DC-001-08")
@SLOW
@given(doc=strategies.job_requests())
def test_strategy_job_requests_validate(doc: dict) -> None:
    assert _errors("job-request", doc) == set()


@pytest.mark.req("DC-001-08")
@SLOW
@given(doc=strategies.tools_registries())
def test_strategy_tools_registries_validate(doc: dict) -> None:
    assert _errors("tools", doc) == set()


@pytest.mark.req("DC-001-08")
@SLOW
@given(doc=strategies.sources_registries())
def test_strategy_sources_registries_validate(doc: dict) -> None:
    assert _errors("sources", doc) == set()


@pytest.mark.req("DC-001-08")
@SLOW
@given(doc=strategies.capabilities())
def test_strategy_capabilities_validate(doc: dict) -> None:
    assert _errors("capabilities", doc) == set()


@pytest.mark.req("DC-001-08")
@SLOW
@given(doc=strategies.run_manifests())
def test_strategy_run_manifests_validate(doc: dict) -> None:
    assert _errors("run", doc) == set()


@pytest.mark.req("DC-001-08")
@SLOW
@given(doc=strategies.web_indexes())
def test_strategy_web_indexes_validate(doc: dict) -> None:
    assert _errors("web-index", doc) == set()


_SEED_DOCS = {
    "recipe": ("recipe", strategies.recipes()),
    "job_request": ("job-request", strategies.job_requests()),
    "tools": ("tools", strategies.tools_registries()),
    "sources": ("sources", strategies.sources_registries().filter(lambda d: d["sources"])),
    "capabilities": ("capabilities", strategies.capabilities()),
    "run": ("run", strategies.run_manifests().filter(lambda d: d["stages"])),
    "web_index": ("web-index", strategies.web_indexes()),
}


@pytest.mark.req("DC-001-08")
@pytest.mark.parametrize("family", sorted(_SEED_DOCS))
def test_each_mutation_breaks_exactly_the_rule_it_names(family: str) -> None:
    kind, strategy = _SEED_DOCS[family]

    @SLOW
    @given(doc=strategy)
    def check(doc: dict) -> None:
        assert _errors(kind, doc) == set()
        for name, mutate, pointer, keyword in strategies.MUTATIONS[family]:
            pairs = _errors(kind, mutate(doc))
            assert (pointer, keyword) in pairs, (name, pointer, keyword, sorted(pairs)[:4])

    check()


@pytest.mark.req("DC-001-08")
def test_strategies_cover_the_yaml_renderings_used_by_the_syntax_invariance_property() -> None:
    import yaml

    doc = {"id": "a-b", "n": [1, 2.5, None], "nested": {"k": "v w", "t": True}}
    variants = strategies.render_yaml_variants(doc)
    assert set(variants) == {"block", "flow", "quoted", "reversed", "commented"}
    for name, text in variants.items():
        assert yaml.safe_load(text) == doc, name  # PyYAML is the reference parser here
    assert "# trailing comment" in variants["commented"]
