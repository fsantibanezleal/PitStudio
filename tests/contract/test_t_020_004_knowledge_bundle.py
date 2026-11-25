"""T-020-004: knowledge bundle schema, generated types and tools/build_knowledge.py.

Requirements: DC-020-03, FR-020-39, FR-020-40, P-020-31.

Spec: specs/020-web-knowledge/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/knowledge-bundle.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/knowledge-bundle.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import json
from pathlib import Path

import _contract_kit as kit
import pytest
import yaml

SPEC = "020-web-knowledge"


@pytest.mark.req("DC-020-03")
def test_knowledge_bundle_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("knowledge-bundle.schema.json")


@pytest.mark.req("DC-020-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["knowledge-bundle.schema.json"], valid=True))
def test_knowledge_bundle_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-020-03")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["knowledge-bundle.schema.json"], valid=False))
def test_knowledge_bundle_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-020-03")
def test_knowledge_bundle_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["knowledge-bundle.schema.json"])


@pytest.mark.req("DC-020-03")
def test_knowledge_bundle_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["knowledge-bundle.schema.json"])


REPO = kit.ROOT


def _valid_bundle() -> dict:
    ex = next(e for e in kit.load_examples(SPEC, ["knowledge-bundle.schema.json"]) if e["valid"])
    return kit.read_json(ex["path"])


def _tables(tmp_path: Path, bundle: dict) -> Path:
    """Write the bundle's rows as input tables: <dir>/{parameters,equations,glossary}.yaml and references.bib.

    Test-defined fixture layout for `--tables` (the spec leaves it to minephys): one YAML list per file under the keys
    `parameters`, `equations`, `glossary`; each row has exactly the fields of the bundle row. references.bib holds one
    entry per bibliography row (`doi`, `url`, `access` as BibTeX fields)."""
    d = tmp_path / "tables"
    d.mkdir(parents=True, exist_ok=True)
    for key in ("parameters", "equations", "glossary"):
        rows = list(bundle[key])
        (d / f"{key}.yaml").write_text(
            yaml.safe_dump({key: rows}, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    bib = []
    for e in bundle["bibliography"]:
        fields = {k: v for k, v in e.items() if k not in {"key", "entry_type", "cited_by"}}
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items())
        bib.append(f"@{e['entry_type']}{{{e['key']},\n{body}\n}}\n")
    (d / "references.bib").write_text("\n".join(bib), encoding="utf-8")
    return d


def _build(tmp_path: Path, tables: Path, out_name: str = "bundle.json") -> tuple[int, str, Path]:
    # Expected CLI: `python tools/build_knowledge.py [--tables DIR] [--out FILE] [--check]`. Without --tables the
    # pinned minephys tables are read; with it, DIR holds the fixture layout of `_tables`. Exit 0 clean, 1 on
    # findings (file and row id named), 2 on usage error; never a traceback. The bundle is written with sorted
    # rows, LF and a final newline.
    out = tmp_path / out_name
    code, text = kit.run_tool("build_knowledge.py", "--tables", str(tables), "--out", str(out))
    return code, text, out


@pytest.mark.req("DC-020-03")
def test_build_knowledge_from_fixture_tables_writes_a_schema_valid_bundle(tmp_path) -> None:
    code, text, out = _build(tmp_path, _tables(tmp_path, _valid_bundle()))
    assert code == 0, text
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert kit.validation_errors("knowledge-bundle.schema.json", "#", doc) == []


@pytest.mark.req("FR-020-40")
def test_build_knowledge_is_byte_identical_across_two_generations_and_sorted_by_id(tmp_path) -> None:
    tables = _tables(tmp_path, _valid_bundle())
    c1, t1, o1 = _build(tmp_path, tables, "a.json")
    c2, t2, o2 = _build(tmp_path, tables, "b.json")
    assert c1 == 0, t1
    assert c2 == 0, t2
    assert o1.read_bytes() == o2.read_bytes()
    doc = json.loads(o1.read_text(encoding="utf-8"))
    for key in ("parameters", "equations", "glossary", "datasets", "frameworks"):
        ids = [r["id"] for r in doc[key]]
        assert ids == sorted(ids), f"{key} rows must be sorted by id"
    keys = [r["key"] for r in doc["bibliography"]]
    assert keys == sorted(keys)


@pytest.mark.req("P-020-31")
def test_build_knowledge_ignores_the_row_order_of_the_input_tables(tmp_path_factory) -> None:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st

    base = _valid_bundle()
    reference_dir = tmp_path_factory.mktemp("ref")
    code, text, ref = _build(reference_dir, _tables(reference_dir, base))
    assert code == 0, text
    want = ref.read_bytes()
    n = max(len(base["parameters"]), len(base["glossary"]), len(base["equations"]), 1)

    @settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(st.permutations(list(range(n))))
    def run(perm: list[int]) -> None:
        d = tmp_path_factory.mktemp("perm")
        shuffled = dict(base)
        for key in ("parameters", "equations", "glossary"):
            rows = base[key]
            shuffled[key] = [rows[i] for i in perm if i < len(rows)]
        c, t, out = _build(d, _tables(d, shuffled))
        assert c == 0, t
        assert out.read_bytes() == want

    run()


def _no_citation(b: dict) -> None:
    del b["parameters"][0]["citation"]


def _no_units(b: dict) -> None:
    del b["parameters"][0]["units"]


def _no_page(b: dict) -> None:
    del b["parameters"][0]["page"]


def _no_verification(b: dict) -> None:
    del b["parameters"][0]["verification"]


def _bad_verification(b: dict) -> None:
    b["parameters"][0]["verification"] = "probably"


def _citation_not_in_bib(b: dict) -> None:
    b["parameters"][0]["citation"] = "nosuchkey2099"


def _bib_without_doi_or_url(b: dict) -> None:
    e = b["bibliography"][0]
    e.pop("doi", None)
    e.pop("url", None)


def _glossary_without_es(b: dict) -> None:
    b["glossary"][0]["term_es"] = ""
    b["glossary"][0]["definition_es"] = ""


def _duplicate_parameter(b: dict) -> None:
    b["parameters"].append(dict(b["parameters"][0]))


@pytest.mark.req("FR-020-39")
@pytest.mark.parametrize(
    ("mutate", "file", "token"),
    [
        pytest.param(_no_citation, "parameters.yaml", lambda b: b["parameters"][0]["id"], id="row-without-citation"),
        pytest.param(_no_units, "parameters.yaml", lambda b: b["parameters"][0]["id"], id="row-without-units"),
        pytest.param(_no_page, "parameters.yaml", lambda b: b["parameters"][0]["id"], id="row-without-page"),
        pytest.param(
            _no_verification, "parameters.yaml", lambda b: b["parameters"][0]["id"], id="row-without-verification"
        ),
        pytest.param(
            _bad_verification,
            "parameters.yaml",
            lambda b: b["parameters"][0]["id"],
            id="verification-not-verified-or-UNVERIFIED",
        ),
        pytest.param(
            _citation_not_in_bib, "parameters.yaml", lambda b: "nosuchkey2099", id="citation-key-missing-from-bib"
        ),
        pytest.param(
            _bib_without_doi_or_url,
            "references.bib",
            lambda b: b["bibliography"][0]["key"],
            id="bib-entry-without-doi-or-url",
        ),
        pytest.param(
            _glossary_without_es, "glossary.yaml", lambda b: b["glossary"][0]["id"], id="glossary-entry-without-es-text"
        ),
        pytest.param(_duplicate_parameter, "parameters.yaml", lambda b: b["parameters"][0]["id"], id="duplicate-id"),
    ],
)
def test_build_knowledge_rejects_each_failure_class_naming_the_file_and_row(tmp_path, mutate, file: str, token) -> None:
    bundle = _valid_bundle()
    mutate(bundle)
    code, text, _ = _build(tmp_path, _tables(tmp_path, bundle))
    assert code == 1, text
    assert file in text, f"the finding must name the file {file}: {text[:400]}"
    assert token(bundle) in text, f"the finding must name the row {token(bundle)!r}: {text[:400]}"
    assert "Traceback" not in text


@pytest.mark.req("FR-020-40")
def test_committed_generated_pages_match_a_fresh_generation_and_an_edit_is_reported(tmp_path) -> None:
    # `--check` regenerates in memory and compares the committed bundle and docs/knowledge/*.md with it.
    code, text = kit.run_tool("build_knowledge.py", "--check")
    assert code == 0, text
    pages = sorted((REPO / "docs" / "knowledge").glob("*.md"))
    generated = [p for p in pages if p.name != "README.md"]
    assert generated, "docs/knowledge/ must hold at least one generated page besides README.md"
    root = tmp_path / "repo"
    kit.copy_tree(REPO / "docs" / "knowledge", root / "docs" / "knowledge")
    bundle = REPO / "web" / "public" / "knowledge" / "bundle.json"
    (root / "web" / "public" / "knowledge").mkdir(parents=True)
    (root / "web" / "public" / "knowledge" / "bundle.json").write_bytes(bundle.read_bytes())
    victim = root / "docs" / "knowledge" / generated[0].name
    victim.write_text(victim.read_text(encoding="utf-8") + "\nedited by hand\n", encoding="utf-8")
    code, text = kit.run_tool("build_knowledge.py", "--check", "--root", str(root))
    assert code == 1, text
    assert generated[0].name in text
