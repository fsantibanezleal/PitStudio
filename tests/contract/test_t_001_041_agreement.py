"""T-001-041 · generated Pydantic models agree with the JSON Schema validator; every trust boundary validates:
P-001-06, FR-001-45.

Oracles: python ``jsonschema`` (a third-party JSON Schema 2020-12 implementation) is the reference acceptor over the
conformance corpus; the boundary list of data-model 7.3 is inspected with a call spy around ``validate``.

Expected API: the committed generated modules ``pitstudio.contracts._generated.<stem>`` (one per contract). The model of
``#/$defs/<name>`` is the class named like the CamelCase of ``<name>``; the model of ``#`` is the class named ``Model``
or the title of the schema with each word capitalised and the spaces removed (``"PitStudio manifest"`` ->
``PitstudioManifest``). Agreement is checked in strict mode (``model_validate(doc, strict=True)``: no string-to-number
coercion), over every JSON fixture not tagged ``conditional``, ``cross-file``, ``post-schema`` or ``loader`` (rules a
generated model cannot express: ``if/then``, ``uniqueItems``, field pairings, cross-file and post-schema rules).
``tools/check_contracts.py`` exposes ``main(argv: list[str] | None = None) -> int`` and calls
``pitstudio.contracts.validate`` for every document it checks.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_support as cs

SKIPPED_TAGS = ("conditional", "cross-file", "post-schema", "loader")


def camel(name: str) -> str:
    return "".join(w.capitalize() for w in name.split("_"))


def generated(stem: str) -> Any:
    return importlib.import_module(f"pitstudio.contracts._generated.{stem}")


def model_for(stem: str, target: str) -> Any:
    module = generated(stem)
    if target != "#":
        return getattr(module, camel(target.rsplit("/", 1)[1]))
    title = cs.load_schema(stem)["title"]
    for name in ("Model", title.title().replace(" ", "")):
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(f"no root model in pitstudio.contracts._generated.{stem}")


def pydantic_accepts(model: Any, doc: Any) -> bool:
    from pydantic import ValidationError

    try:
        model.model_validate(doc, strict=True)
    except ValidationError:
        return False
    return True


@pytest.mark.req("P-001-06")
def test_p_001_06_every_contract_has_a_generated_module() -> None:
    for stem in cs.SCHEMA_STEMS:
        assert generated(stem) is not None


@pytest.mark.req("P-001-06")
def test_p_001_06_the_generated_model_accepts_a_fixture_if_and_only_if_the_schema_validator_does() -> None:
    disagreements = []
    checked = 0
    for e in cs.entries(tag_not_in=SKIPPED_TAGS):
        if not e["file"].endswith(".json"):
            continue
        doc = cs.fixture_json(e)
        expected = cs.accepts(e["schema"], e["target"], doc)  # the reference acceptor
        actual = pydantic_accepts(model_for(e["schema"], e["target"]), doc)
        checked += 1
        if expected != actual:
            disagreements.append((e["file"], expected, actual))
    assert checked >= 110
    assert disagreements == []


@pytest.mark.req("P-001-06")
def test_p_001_06_every_valid_fixture_is_accepted_by_its_generated_model() -> None:
    for e in cs.entries(valid=True):
        if e["file"].endswith(".json"):
            assert pydantic_accepts(model_for(e["schema"], e["target"]), cs.fixture_json(e)), e["file"]


@pytest.mark.req("P-001-06")
def test_p_001_06_models_are_closed_unknown_fields_are_rejected() -> None:
    from pydantic import ValidationError

    run = cs.fixture_json(
        next(e for e in cs.entries(valid=True, kind="run") if e["file"].endswith("manifest.valid.json"))
    )
    model = model_for("manifest", "#/$defs/run")
    model.model_validate(run, strict=True)
    with pytest.raises(ValidationError):
        model.model_validate({**run, "hostname": "box"}, strict=True)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-45 · trust boundaries validate with the schema, never with the generated types alone
# ----------------------------------------------------------------------------------------------------------------
BOUNDARIES = {  # data-model 7.3: (boundary, owning spec)
    "runner loading a recipe or a profile": "002-runner",
    "runner reading a stage result.json": "002-runner",
    "console accepting POST /jobs": "003-console",
    "tools/check_contracts.py on every committed document": "001-contracts",
    "pages.yml reading the web index and the release assets before upload": "001-contracts",
    "studio publish writing a published manifest": "002-runner",
}


@pytest.mark.req("FR-001-45")
def test_fr_001_45_the_boundary_list_of_data_model_7_3_is_six_entries_two_of_them_in_this_spec() -> None:
    assert len(BOUNDARIES) == 6
    assert [b for b, spec in BOUNDARIES.items() if spec == "001-contracts"] == [
        "tools/check_contracts.py on every committed document",
        "pages.yml reading the web index and the release assets before upload",
    ]


@pytest.mark.req("FR-001-45")
def test_fr_001_45_the_checker_calls_validate_for_every_document_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import pitstudio.contracts as contracts

    calls: list[str] = []
    real = contracts.validate

    def spy(document: Any, schema_name: str, *args: Any, **kwargs: Any) -> Any:
        calls.append(schema_name)
        return real(document, schema_name, *args, **kwargs)

    monkeypatch.setattr(contracts, "validate", spy)
    submodule = sys.modules.get("pitstudio.contracts.validate")
    if submodule is not None and hasattr(submodule, "validate"):
        monkeypatch.setattr(submodule, "validate", spy)
    spec = importlib.util.spec_from_file_location("check_contracts_under_spy", cs.CHECKER)
    assert spec is not None, "tools/check_contracts.py is missing"
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    root = cs.clean_repo(tmp_path)
    assert module.main(["--root", str(root), "--json"]) == 0
    capsys.readouterr()
    stems = {re.split(r"[#]", c)[0] for c in calls}
    assert {"manifest", "recipe", "tools", "sources", "capabilities"} <= stems, calls
    assert len(calls) >= 7  # tools, sources, 2 recipes, capabilities, web index, published run manifest
    assert sum(1 for c in calls if c.startswith("manifest")) >= 2


@pytest.mark.req("FR-001-45")
def test_fr_001_45_no_module_uses_the_generated_types_without_validating() -> None:
    offenders = []
    for base in (
        cs.ROOT / "src" / "pitstudio",
        cs.ROOT / "tools",
        cs.ROOT / "pipeline",
        cs.ROOT / "api",
        cs.ROOT / "studio",
    ):
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            parts = path.relative_to(cs.ROOT).parts
            if "_generated" in parts or ".venv" in parts or "tests" in parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            imports_generated = re.search(r"^\s*(?:from|import)\b[^\n]*_generated", text, re.M)
            if imports_generated and "validate" not in text:
                offenders.append(path.relative_to(cs.ROOT).as_posix())
    assert offenders == []


@pytest.mark.req("FR-001-45")
def test_fr_001_45_the_pages_workflow_is_a_boundary_that_runs_the_checker() -> None:
    text = (cs.ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert "check_contracts.py" in text


@pytest.mark.req("FR-001-45")
def test_fr_001_45_rules_the_generated_types_cannot_express_are_enforced_by_validate_not_by_the_models() -> None:
    from pitstudio.contracts import validate

    inexpressible = [e for e in cs.entries(tag_in=("conditional", "post-schema")) if e["file"].endswith(".json")]
    assert len(inexpressible) >= 30
    caught = 0
    for e in inexpressible:
        name = f"{e['schema']}{e['target']}" if e["target"] != "#" else e["schema"]
        doc = json.loads(cs.fixture_file(e).read_text(encoding="utf-8"))
        errors = validate(doc, name)
        assert errors, e["file"]  # validate catches every one of them
        caught += 1
    assert caught == len(inexpressible)
