"""T-001-001 · the five promoted contract schemas: FR-001-01..04, DC-001-01..05.

Oracles (all independent of the code under test):
* FR-001-01: the JSON Schema 2020-12 meta-schema, applied by ``Draft202012Validator.check_schema`` (reference).
* FR-001-02: a schema walker written here from data-model 1.2, itself checked on hand-seeded open/closed schemas.
* FR-001-03: ``re.compile`` and pydantic-core's regex compiler (Rust regex engine) as reference engines; a seeded
  lookahead pattern must be rejected.
* FR-001-04: hand-built hostile digests, timestamps, URLs run through python ``jsonschema`` in a subprocess in which
  the optional format-checker packages cannot be imported (``sys.modules[name] = None`` before jsonschema loads).
* The shared patterns of data-model 1.3 are transcribed in ``contract_support.PATTERNS``.

Expected API: none (data files only): ``contracts/{manifest,recipe,tools,sources,capabilities}.schema.json``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_support as cs

DEFS_REQUIRED = {  # data-model 1.3: shared patterns each schema must define (by the names of the table)
    "manifest": [
        "slug",
        "tool_id",
        "artefact_id",
        "run_id",
        "variant",
        "sha256",
        "git_sha",
        "utc_timestamp",
        "date",
        "release_tag",
        "relpath",
        "semver",
        "package",
        "version",
        "python_version",
        "driver",
        "param_key",
    ],
    "recipe": [
        "slug",
        "tool_id",
        "variant",
        "sha256",
        "relpath",
        "module_path",
        "param_key",
        "probe",
        "binary_id",
        "validator_id",
    ],
    "tools": ["tool_id", "sha256", "package", "version", "binary_id", "https_url"],
    "sources": ["slug", "sha256", "https_url", "relpath", "relglob", "env_var"],
    "capabilities": ["date", "driver"],
}
SCHEMA_KEYS_SINGLE = (
    "additionalProperties",
    "unevaluatedProperties",
    "items",
    "contains",
    "not",
    "if",
    "then",
    "else",
    "propertyNames",
    "unevaluatedItems",
)
SCHEMA_KEYS_LIST = ("allOf", "anyOf", "oneOf", "prefixItems")
SCHEMA_KEYS_MAP = ("properties", "patternProperties", "$defs", "dependentSchemas")


# ----------------------------------------------------------------------------------------------------------------
# helpers written from the data model
# ----------------------------------------------------------------------------------------------------------------
def children(node: dict) -> list[tuple[str, dict, bool]]:
    """(location, subschema, parent composes with unevaluatedProperties:false) for every direct subschema."""
    closed_parent = node.get("unevaluatedProperties") is False
    out: list[tuple[str, dict, bool]] = []
    for key in SCHEMA_KEYS_SINGLE:
        v = node.get(key)
        if isinstance(v, dict):
            out.append((key, v, False))
    for key in SCHEMA_KEYS_LIST:
        for i, v in enumerate(node.get(key, [])):
            if isinstance(v, dict):
                out.append((f"{key}/{i}", v, closed_parent and key in ("allOf", "anyOf", "oneOf")))
    for key in SCHEMA_KEYS_MAP:
        for name, v in (node.get(key) or {}).items():
            if isinstance(v, dict):
                out.append((f"{key}/{name}", v, False))
    return out


def open_objects(node: dict, path: str = "#", composed_closed: bool = False) -> list[str]:
    """Locations of object-typed subschemas that are not closed (data-model 1.2)."""
    problems: list[str] = []
    t = node.get("type")
    is_object = t == "object" or (isinstance(t, list) and "object" in t)
    if is_object:
        record = node.get("additionalProperties") is False
        ap = node.get("additionalProperties")
        names = node.get("propertyNames")
        typed = isinstance(ap, dict) and any(
            k in ap for k in ("type", "$ref", "anyOf", "oneOf", "allOf", "enum", "const")
        )
        tmap = isinstance(names, dict) and "pattern" in names and typed and "maxProperties" in node
        if not (record or tmap or composed_closed):
            problems.append(path)
    for loc, sub, comp in children(node):
        problems += open_objects(sub, f"{path}/{loc}", comp)
    return problems


def all_patterns(node: Any, path: str = "#") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "pattern" and isinstance(v, str):
                found.append((path, v))
            elif k == "patternProperties" and isinstance(v, dict):
                found += [(f"{path}/patternProperties", p) for p in v]
            found += all_patterns(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found += all_patterns(v, f"{path}/{i}")
    return found


def forbidden_constructs(pattern: str) -> list[str]:
    """Lookaround, backreference, possessive quantifier, atomic group (FR-001-03); character classes are skipped."""
    found = []
    if re.search(r"(?<!\\)(?:\\\\)*\\[1-9]", pattern) or re.search(r"\(\?P=|\\k<", pattern):
        found.append("backreference")
    bare = re.sub(r"\\.", "", pattern)  # drop escapes
    bare = re.sub(r"\[\^?\]?[^\]]*\]", "[]", bare)  # drop character classes
    if re.search(r"\(\?<?[=!]", bare):
        found.append("lookaround")
    if "(?>" in bare:
        found.append("atomic group")
    if re.search(r"[*+?}]\+", bare):
        found.append("possessive quantifier")
    return found


def walk(node: Any):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-01 / DC-001-01..05
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-01")
@pytest.mark.req("DC-001-01")
@pytest.mark.req("DC-001-02")
@pytest.mark.req("DC-001-03")
@pytest.mark.req("DC-001-04")
@pytest.mark.req("DC-001-05")
@pytest.mark.parametrize("stem", cs.SCHEMA_STEMS)
def test_fr_001_01_schema_declares_dialect_and_id_and_passes_the_meta_schema(stem: str) -> None:
    schema = cs.load_schema(stem)
    assert schema["$schema"] == cs.META_2020_12
    assert schema["$id"] == f"https://fsantibanezleal.github.io/PitStudio/contracts/{stem}.schema.json"
    Draft202012Validator.check_schema(schema)  # raises SchemaError on any meta-schema violation


@pytest.mark.req("DC-001-02")
def test_dc_001_02_recipe_schema_holds_the_job_request_definition_and_no_profile_or_absolute_path_field() -> None:
    schema = cs.load_schema("recipe")
    assert "job_request" in schema["$defs"]
    assert "recipe" in schema["$defs"]
    names = {k.lower() for n in walk(schema) for k in n.get("properties", {})}
    assert not {"profile_id", "machine", "hostname", "abs_path", "absolute_path", "home"} & names
    job = schema["$defs"]["job_request"]
    assert set(job["properties"]) == {"recipe", "stages", "force", "rerun_check", "profile"}  # data-model 3.5
    assert job["additionalProperties"] is False
    assert set(job["required"]) == {"recipe", "profile"}


@pytest.mark.req("DC-001-01")
def test_dc_001_01_manifest_schema_has_the_two_document_kinds() -> None:
    schema = cs.load_schema("manifest")
    assert {"run", "web_index"} <= set(schema["$defs"])
    assert schema["$defs"]["run"]["properties"]["kind"] == {"const": "run"}
    assert schema["$defs"]["web_index"]["properties"]["kind"] == {"const": "web-index"}
    assert len(schema["oneOf"]) == 2


@pytest.mark.req("FR-001-01")
def test_fr_001_01_no_remote_reference_anywhere() -> None:
    for stem in cs.SCHEMA_STEMS:
        for node in walk(cs.load_schema(stem)):
            ref = node.get("$ref")
            if isinstance(ref, str):
                assert not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", ref), (stem, ref)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-02
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-02")
def test_fr_001_02_walker_flags_seeded_open_objects_and_accepts_closed_ones() -> None:
    open_record = {"type": "object", "properties": {"a": {"type": "string"}}}
    assert open_objects(open_record) == ["#"]
    assert open_objects({"type": "object", "additionalProperties": True}) == ["#"]
    assert open_objects({"type": "object", "additionalProperties": False}) == []
    untyped_map = {
        "type": "object",
        "propertyNames": {"pattern": "^a$"},
        "additionalProperties": {},
        "maxProperties": 3,
    }
    assert open_objects(untyped_map) == ["#"]
    no_cap = {"type": "object", "propertyNames": {"pattern": "^a$"}, "additionalProperties": {"type": "string"}}
    assert open_objects(no_cap) == ["#"]
    good_map = {**no_cap, "maxProperties": 3}
    assert open_objects(good_map) == []
    nested = {"type": "object", "additionalProperties": False, "properties": {"x": open_record}}
    assert open_objects(nested) == ["#/properties/x"]
    composed = {"unevaluatedProperties": False, "allOf": [open_record, {"type": "object", "properties": {"b": {}}}]}
    assert open_objects(composed) == []
    assert open_objects({"allOf": [open_record]}) == ["#/allOf/0"]


@pytest.mark.req("FR-001-02")
@pytest.mark.parametrize("stem", cs.SCHEMA_STEMS)
def test_fr_001_02_every_object_subschema_is_closed(stem: str) -> None:
    assert open_objects(cs.load_schema(stem)) == []


@pytest.mark.req("FR-001-02")
def test_fr_001_02_only_schema_hint_property_is_allowed_beyond_the_fields_and_it_is_bounded() -> None:
    manifest, recipe = cs.load_schema("manifest"), cs.load_schema("recipe")
    roots = [
        manifest["$defs"]["run"],
        manifest["$defs"]["web_index"],
        recipe["$defs"]["recipe"],
        cs.load_schema("tools"),
        cs.load_schema("sources"),
        cs.load_schema("capabilities"),
    ]
    for root in roots:
        hint = root["properties"]["$schema"]
        assert hint["type"] == "string"
        assert hint["maxLength"] <= 200
        assert "$schema" not in root.get("required", [])


# ----------------------------------------------------------------------------------------------------------------
# FR-001-03
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-03")
def test_fr_001_03_lint_and_reference_engines_reject_the_seeded_lookahead() -> None:
    from pydantic_core import SchemaError, SchemaValidator, core_schema

    seeded = {
        "lookahead": r"^(?=a)[a-z]+$",
        "negative lookahead": r"^(?!a)[a-z]+$",
        "lookbehind": r"^(?<=a)b$",
        "backreference": r"^(a)\1$",
        "atomic group": r"^(?>a+)b$",
        "possessive quantifier": r"^a++b$",
    }
    for label, pattern in seeded.items():
        re.compile(pattern)  # Python accepts them (except where noted); the portable subset must not
        assert forbidden_constructs(pattern), label
    with pytest.raises(SchemaError):
        SchemaValidator(core_schema.str_schema(pattern=seeded["lookahead"]))
    assert forbidden_constructs(r"^[a-z0-9][a-z0-9.+_-]{0,63}$") == []  # '+' inside a class is not possessive


@pytest.mark.req("FR-001-03")
@pytest.mark.parametrize("stem", cs.SCHEMA_STEMS)
def test_fr_001_03_every_pattern_compiles_under_python_re_and_pydantic_core_and_is_portable(stem: str) -> None:
    from pydantic_core import SchemaValidator, core_schema

    patterns = all_patterns(cs.load_schema(stem))
    assert patterns, "a contract without a single pattern cannot constrain ids, digests or paths"
    for where, pattern in patterns:
        re.compile(pattern)
        SchemaValidator(core_schema.str_schema(pattern=pattern))  # Rust regex engine, pydantic-core default
        assert forbidden_constructs(pattern) == [], (where, pattern)
        assert pattern.startswith("^"), (where, pattern)
        assert pattern.endswith("$"), (where, pattern)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-04
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-04")
@pytest.mark.parametrize("stem", cs.SCHEMA_STEMS)
def test_fr_001_04_shared_patterns_have_the_data_model_text_and_max_length(stem: str) -> None:
    defs = cs.load_schema(stem)["$defs"]
    for name in DEFS_REQUIRED[stem]:
        assert name in defs, f"{stem}: $defs/{name} missing"
        pattern, max_length = cs.PATTERNS[name]
        assert defs[name]["pattern"] == pattern, (stem, name)
        assert defs[name]["maxLength"] == max_length, (stem, name)
        assert defs[name]["type"] == "string"


@pytest.mark.req("FR-001-04")
@pytest.mark.parametrize("stem", cs.SCHEMA_STEMS)
def test_fr_001_04_format_is_only_ever_an_annotation_next_to_a_pattern(stem: str) -> None:
    for node in walk(cs.load_schema(stem)):
        if "format" in node:
            assert "pattern" in node, (stem, node)


_HOSTILE_SCRIPT = textwrap.dedent(
    """
    import json, sys
    for name in ("rfc3339_validator", "rfc3987", "rfc3986_validator", "fqdn", "idna", "isoduration", "jsonpointer",
                 "uri_template", "webcolors"):
        sys.modules[name] = None  # import raises ImportError: the optional format checkers are absent
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
    payload = json.load(sys.stdin)
    resources = [(s["$id"], Resource.from_contents(s)) for s in payload["schemas"].values()]
    reg = Registry().with_resources(resources)
    out = []
    for case in payload["cases"]:
        s = payload["schemas"][case["stem"]]
        v = Draft202012Validator({"$ref": s["$id"] + case["target"]}, registry=reg, format_checker=FormatChecker())
        errs = []
        stack = list(v.iter_errors(case["doc"]))
        while stack:
            e = stack.pop()
            errs.append(["/" + "/".join(str(p) for p in e.absolute_path), e.validator])
            stack.extend(e.context or [])
        out.append(errs)
    print(json.dumps(out))
    """
)


def _hostile_cases() -> list[dict]:
    def load(rel: str) -> Any:
        return json.loads((cs.FIXTURES / rel).read_text(encoding="utf-8"))

    run = load("manifest/valid/manifest.valid.json")
    web = load("manifest/valid/manifest.valid-web-index.json")
    rec = load("recipe/valid/recipe.valid.json")
    src = load("sources/valid/sources.valid.json")
    cap = load("capabilities/valid/capabilities.valid.json")
    cases: list[dict] = []

    def add(stem: str, target: str, base: Any, pointer: list[Any], value: Any) -> None:
        doc = json.loads(json.dumps(base))
        node = doc
        for p in pointer[:-1]:
            node = node[p]
        node[pointer[-1]] = value
        cases.append({"stem": stem, "target": target, "doc": doc, "pointer": "/" + "/".join(str(p) for p in pointer)})

    for bad in ("A" * 64, "a" * 63, "a" * 65, "sha256:" + "a" * 64, "g" * 64, " " + "a" * 63, "a" * 63 + "é"):
        add("manifest", "#/$defs/run", run, ["recipe", "sha256"], bad)
        add("recipe", "#", rec, ["stages", 0, "inputs", 0, "sha256"], bad)
        add("sources", "#", src, ["sources", 0, "files", 0, "sha256"], bad)
    for bad in ("c" * 39, "c" * 41, "C" * 40, "c" * 39 + "z"):
        add("manifest", "#/$defs/run", run, ["git_sha"], bad)
    for bad in (
        "2026-10-07T12:00:00+00:00",
        "2026-10-07 12:00:00Z",
        "2026-13-07T12:00:00Z",
        "2026-10-32T12:00:00Z",
        "2026-10-07T24:00:00Z",
        "2026-10-07T12:60:00Z",
        "2026-10-07T12:00:00",
        "2026-10-07T12:00:00.1234567Z",
        "26-10-07T12:00:00Z",
        "2026-10-07T12:00:00z",
        "2026-10-07T12:00:00Z" + "0" * 20,
    ):
        add("manifest", "#/$defs/run", run, ["created"], bad)
    for bad in ("2026-10-07T00:00:00Z", "2026-1-07", "20261007", "2026-00-10", "2026-10-00"):
        add("manifest", "#/$defs/web_index", web, ["generated"], bad)
        add("capabilities", "#", cap, ["generated"], bad)
    for bad in (
        "http://example.org/x",
        "ftp://example.org/x",
        "https://user:pw@example.org/x",
        "https:///x",
        "https://exa mple.org",
        "javascript:alert(1)",
        "https://example.org/" + "a" * 2049,
        "//example.org/x",
        "https://example.org/é",
        "https://example.org/x y",
    ):
        add("sources", "#", src, ["sources", 0, "landing_url"], bad)
        add("sources", "#", src, ["sources", 0, "files", 0, "url"], bad)
    for bad in (
        "assets-v1.2.003",
        "assets-v1.002.003",
        "assets-v1.02.3",
        "assets-1.02.003",
        "Assets-v1.02.003",
        "assets-v.02.003",
    ):
        add("manifest", "#/$defs/web_index", web, ["artefacts", 0, "release_tag"], bad)
    for bad in ("20261007T120000Z-A2", "2026100T120000Z-a2", "20261007T120000-a2", "20261007T120000Z-", "x" * 70):
        add("manifest", "#/$defs/run", run, ["run_id"], bad)
    for bad in ("../x", "/abs/x", "a\\b", "a//b", "a/./b", "x.", "a b", ".hidden", "-x", "a" * 256):
        add("manifest", "#/$defs/run", run, ["artefacts", 0, "path"], bad)
    for bad in ("582", "v582.78", "582.78.", "582..78", "5" * 40 + ".1"):
        add("capabilities", "#", cap, ["driver"], bad)
    return cases


@pytest.mark.req("FR-001-04")
def test_fr_001_04_hostile_digests_timestamps_urls_are_rejected_by_pattern_alone() -> None:
    cases = _hostile_cases()
    assert len(cases) >= 90
    schemas = {s: cs.load_schema(s) for s in cs.SCHEMA_STEMS}
    proc = subprocess.run(
        [sys.executable, "-c", _HOSTILE_SCRIPT],
        input=json.dumps({"schemas": schemas, "cases": cases}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=300,
    )
    results = json.loads(proc.stdout)
    for case, errs in zip(cases, results, strict=True):
        hit = {k for p, k in errs if p == case["pointer"]}
        assert hit & {"pattern", "maxLength"}, (case["pointer"], case["doc"], errs[:3])
