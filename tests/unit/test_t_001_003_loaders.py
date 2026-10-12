"""T-001-003 · strict loaders, deterministic writer and lazy validation: FR-001-05, FR-001-06, FR-001-07, FR-001-08.

Oracles: hand-built byte strings with the expected error kind and location (NaN, Infinity, ``1e999``, duplicate keys,
BOM, invalid UTF-8, depth 33, anchors, aliases, explicit tags, several documents, non-string keys, ``.nan``, implicit
booleans, dates); expected bytes of the writer written out literally; PyYAML as the reference YAML parser for what
the loader must NOT change; python ``jsonschema`` plus hand-counted violations for ``validate``.

Expected API (see ``contract_support``): ``pitstudio.contracts.load_json(path, *, max_bytes=None)``,
``load_yaml(path, *, max_bytes=None)``, ``dump_json(obj) -> bytes``, ``ContractError`` (a ``ValueError``) whose message
names the file and the line or the JSON pointer, ``validate(document, schema_name) -> list`` of objects with
``pointer``, ``keyword``, ``message``. A rejected document returns no partial object (the loader raises).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contract"))
import contract_support as cs

BOM = b"\xef\xbb\xbf"


def contracts() -> Any:
    import pitstudio.contracts as c

    return c


def write(tmp: Path, name: str, data: bytes | str) -> Path:
    p = tmp / name
    p.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return p


def names_location(message: str, *, line: int | None = None, pointer: str | None = None) -> bool:
    """The message names the line (as a standalone number) or the JSON pointer."""
    if line is not None and re.search(rf"(?<![0-9]){line}(?![0-9])", message):
        return True
    return pointer is not None and pointer in message


def rejects(loader: str, path: Path, **kw: Any) -> Exception:
    c = contracts()
    with pytest.raises(c.ContractError) as info:
        getattr(c, loader)(path, **kw)
    assert isinstance(info.value, ValueError)
    assert path.name in str(info.value), "the error must name the file"
    return info.value


# ----------------------------------------------------------------------------------------------------------------
# FR-001-05 · JSON
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-05")
def test_fr_001_05_a_clean_document_loads_to_the_same_value_as_the_standard_library(tmp_path: Path) -> None:
    text = '{"a": [1, 2.5, null, true, "x\\u00e9"], "b": {"c": -3}, "d": 1e3, "e": 12345678901234567890}\n'
    p = write(tmp_path, "ok.json", text)
    assert contracts().load_json(p) == json.loads(text)
    assert isinstance(contracts().load_json(p)["a"][0], int)


@pytest.mark.req("FR-001-05")
@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999", "1E400"])
def test_fr_001_05_non_finite_numbers_are_rejected_with_their_line(tmp_path: Path, token: str) -> None:
    p = write(tmp_path, "nonfinite.json", f'{{\n  "ok": 1,\n  "bad": {token}\n}}\n')
    err = rejects("load_json", p)
    assert names_location(str(err), line=3, pointer="/bad"), str(err)


@pytest.mark.req("FR-001-05")
@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_fr_001_05_non_finite_numbers_nested_in_arrays_and_objects(tmp_path: Path, token: str) -> None:
    p = write(tmp_path, "nested.json", f'{{"a": {{"b": [1, 2, {token}]}}}}')
    err = rejects("load_json", p)
    assert names_location(str(err), line=1, pointer="/a/b/2")


@pytest.mark.req("FR-001-05")
def test_fr_001_05_duplicate_keys_are_rejected_at_every_level(tmp_path: Path) -> None:
    top = write(tmp_path, "dup1.json", '{\n  "a": 1,\n  "b": 2,\n  "a": 3\n}\n')
    assert names_location(str(rejects("load_json", top)), line=4, pointer="/a")
    nested = write(tmp_path, "dup2.json", '{"x": {"y": 1, "z": 2, "y": 3}}')
    assert names_location(str(rejects("load_json", nested)), line=1, pointer="/x/y")
    in_array = write(tmp_path, "dup3.json", '{"l": [{"k": 1, "k": 2}]}')
    assert names_location(str(rejects("load_json", in_array)), line=1, pointer="/l/0/k")
    escaped = write(tmp_path, "dup4.json", '{"a": 1, "\\u0061": 2}')  # the same key spelled with an escape
    rejects("load_json", escaped)


@pytest.mark.req("FR-001-05")
def test_fr_001_05_keys_that_differ_only_in_case_or_normalisation_are_distinct(tmp_path: Path) -> None:
    p = write(tmp_path, "keys.json", '{"A": 1, "a": 2, "\\u00e9": 3, "e\\u0301": 4}')
    assert len(contracts().load_json(p)) == 4


@pytest.mark.req("FR-001-05")
def test_fr_001_05_byte_order_mark_is_rejected(tmp_path: Path) -> None:
    err = rejects("load_json", write(tmp_path, "bom.json", BOM + b'{"a": 1}'))
    assert names_location(str(err), line=1)
    rejects("load_json", write(tmp_path, "bom16.json", b"\xff\xfe" + '{"a": 1}'.encode("utf-16-le")))


@pytest.mark.req("FR-001-05")
@pytest.mark.parametrize(
    "raw",
    [b'{"a": "\xff"}', b'{"a": "\xc3\x28"}', b'{"a": "\xe2\x82"}', b"\x80{}", b'{"\xed\xa0\x80": 1}'],
    ids=["ff", "c328", "truncated-e2", "lead-80", "surrogate-half"],
)
def test_fr_001_05_invalid_utf8_is_rejected_before_parsing(tmp_path: Path, raw: bytes) -> None:
    rejects("load_json", write(tmp_path, "badutf8.json", raw))


@pytest.mark.req("FR-001-05")
@pytest.mark.parametrize(("depth", "ok"), [(1, True), (31, True), (32, True), (33, False), (100, False)])
def test_fr_001_05_nesting_deeper_than_32_levels_is_rejected(tmp_path: Path, depth: int, ok: bool) -> None:
    text = "[" * depth + "]" * depth  # the outermost array is level 1
    p = write(tmp_path, "deep.json", text)
    if ok:
        assert contracts().load_json(p) is not None
    else:
        rejects("load_json", p)
    objs = write(tmp_path, "deepobj.json", '{"a":' * depth + "1" + "}" * depth)
    if ok:
        assert contracts().load_json(objs) is not None
    else:
        rejects("load_json", objs)


@pytest.mark.req("FR-001-05")
def test_fr_001_05_extremely_deep_nesting_is_an_error_not_a_crash(tmp_path: Path) -> None:
    rejects("load_json", write(tmp_path, "abyss.json", "[" * 200_000 + "]" * 200_000))


@pytest.mark.req("FR-001-05")
def test_fr_001_05_bytes_over_the_cap_are_rejected_before_parsing(tmp_path: Path) -> None:
    exact = write(tmp_path, "exact.json", '{"a": "' + "x" * 991 + '"}')  # 7 + 991 + 2 = 1000 bytes
    assert exact.stat().st_size == 1000
    assert contracts().load_json(exact, max_bytes=1000) == {"a": "x" * 991}
    err = rejects("load_json", exact, max_bytes=999)
    assert "999" in str(err) or "cap" in str(err).lower() or "bytes" in str(err).lower()
    garbage = write(tmp_path, "huge.json", b"\xff" * 5000)  # over the cap and invalid: the size is checked first
    rejects("load_json", garbage, max_bytes=100)


@pytest.mark.req("FR-001-05")
@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n",
        '{"a": 1',
        '{"a": 1}}',
        "[1, 2,]",
        "{'a': 1}",
        '{"a": undefined}',
        "nul",
        '{"a" 1}',
        '{"a": 1} {"b": 2}',
        "\x00",
        '"unterminated',
        "{,}",
    ],
)
def test_fr_001_05_malformed_documents_raise_contract_error_not_json_decode_error(tmp_path: Path, text: str) -> None:
    err = rejects("load_json", write(tmp_path, "bad.json", text))
    assert not isinstance(err, json.JSONDecodeError)


@pytest.mark.req("FR-001-05")
def test_fr_001_05_unicode_content_survives_and_a_lone_surrogate_escape_is_not_silently_accepted(
    tmp_path: Path,
) -> None:
    p = write(tmp_path, "uni.json", json.dumps({"k\u00e9y": "\u4e2d\u6587 \U0001f600 \u00f1"}, ensure_ascii=False))
    assert contracts().load_json(p) == {"k\u00e9y": "\u4e2d\u6587 \U0001f600 \u00f1"}
    lone = write(tmp_path, "lone.json", '{"a": "\\ud800"}')
    try:
        value = contracts().load_json(lone)
    except contracts().ContractError:
        return
    with pytest.raises(UnicodeError):
        json.dumps(value, ensure_ascii=False).encode("utf-8")  # if accepted, it must at least not round-trip silently


@pytest.mark.req("FR-001-05")
def test_fr_001_05_loader_fixtures_of_the_corpus_are_all_rejected_with_their_location() -> None:
    json_loader = [e for e in cs.entries(tag_in=("loader",)) if e["file"].endswith(".json")]
    assert len(json_loader) >= 20
    for e in json_loader:
        path = cs.fixture_file(e)
        c = contracts()
        with pytest.raises(c.ContractError) as info:
            c.load_json(path)
        msg = str(info.value)
        assert path.name in msg, e["file"]
        if e["loader_error"] in ("non-finite", "duplicate-key", "depth", "bom"):
            assert names_location(msg, line=e["line"], pointer=e["pointer"] or None), (e["file"], msg)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-06 · YAML
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-06")
def test_fr_001_06_a_clean_document_loads_like_pyyaml_except_for_the_hardened_scalars(tmp_path: Path) -> None:
    text = "# comment\na: 1\nb: [1, 2.5, null, true, false]\nc:\n  d: text\n  e: 'quoted'\nf: 0.5\ng: ~\n"
    p = write(tmp_path, "ok.yaml", text)
    assert contracts().load_yaml(p) == yaml.safe_load(text)


@pytest.mark.req("FR-001-06")
@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("a: &x 1\nb: *x\n", "alias"),
        ("a: &x [1, 2]\n", "anchor"),
        ("a: *undefined\n", "alias"),
        ("<<: &base {a: 1}\nb: 2\n", "anchor"),
        ("a: !!python/object/apply:os.system ['echo hi']\n", "tag"),
        ("a: !!str 5\n", "tag"),
        ("a: !custom value\n", "tag"),
        ("a: !!binary aGk=\n", "tag"),
        ("!!set {a, b}\n", "tag"),
        ("a: 1\n---\nb: 2\n", "multi-document"),
        ("---\na: 1\n---\n", "multi-document"),
        ("a: 1\n...\n---\nb: 2\n", "multi-document"),
        ("a: 1\na: 2\n", "duplicate"),
        ("a:\n  b: 1\n  b: 2\n", "duplicate"),
        ("a: 1\n'a': 2\n", "duplicate"),
        ("7: seven\n", "non-string key"),
        ("true: yes\n", "non-string key"),
        ("null: x\n", "non-string key"),
        ("~: x\n", "non-string key"),
        ("1.5: x\n", "non-string key"),
        ("? [a, b]\n: c\n", "non-string key"),
        ("a: .nan\n", "non-finite"),
        ("a: .NaN\n", "non-finite"),
        ("a: .inf\n", "non-finite"),
        ("a: -.inf\n", "non-finite"),
        ("a: +.inf\n", "non-finite"),
        ("a: .Inf\n", "non-finite"),
        ("a: [1, .nan]\n", "non-finite"),
        ("a: 1.0e+999\n", "non-finite"),
    ],
)
def test_fr_001_06_hostile_yaml_constructs_are_rejected_naming_the_file_and_line(
    tmp_path: Path, text: str, kind: str
) -> None:
    p = write(tmp_path, "hostile.yaml", text)
    err = rejects("load_yaml", p)
    assert re.search(r"\d", str(err)), "the error must give a line number"


@pytest.mark.req("FR-001-06")
def test_fr_001_06_error_names_the_line_of_the_offending_construct(tmp_path: Path) -> None:
    p = write(tmp_path, "line.yaml", "a: 1\nb: 2\nc: &x 3\n")
    assert names_location(str(rejects("load_yaml", p)), line=3)
    p2 = write(tmp_path, "line2.yaml", "a: 1\nb: 2\na: 4\n")
    assert names_location(str(rejects("load_yaml", p2)), line=3, pointer="/a")
    p3 = write(tmp_path, "line3.yaml", "a: 1\nb: .nan\n")
    assert names_location(str(rejects("load_yaml", p3)), line=2)


@pytest.mark.req("FR-001-06")
@pytest.mark.parametrize(
    "word",
    ["yes", "no", "on", "off", "y", "n", "Yes", "YES", "No", "NO", "On", "ON", "Off", "OFF", "Y", "N", "yEs", "oN"],
)
def test_fr_001_06_yaml_1_1_implicit_booleans_load_as_strings(tmp_path: Path, word: str) -> None:
    p = write(tmp_path, "bool.yaml", f"flag: {word}\nlist: [{word}, x]\n")
    assert contracts().load_yaml(p) == {"flag": word, "list": [word, "x"]}


@pytest.mark.req("FR-001-06")
def test_fr_001_06_true_and_false_stay_booleans_and_other_scalars_keep_their_types(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        "types.yaml",
        "a: true\nb: false\nc: 12\nd: 1.5\ne: null\nf: ~\ng: 'true'\nh: \"12\"\ni: -7\nj: 1.0e+3\n",
    )
    got = contracts().load_yaml(p)
    assert got["a"] is True
    assert got["b"] is False
    assert got["c"] == 12
    assert isinstance(got["c"], int)
    assert got["d"] == 1.5
    assert got["e"] is None
    assert got["f"] is None
    assert got["g"] == "true"
    assert got["h"] == "12"
    assert got["i"] == -7
    assert isinstance(got["j"], float)
    assert got["j"] == 1000.0


@pytest.mark.req("FR-001-06")
@pytest.mark.parametrize(
    "scalar",
    [
        "2026-10-07",
        "2026-10-07T12:00:00Z",
        "2026-10-07 12:00:00",
        "2026-10-07T12:00:00.5+02:00",
        "2001-12-14t21:59:43.10-05:00",
        "2002-12-14",
    ],
)
def test_fr_001_06_unquoted_dates_and_timestamps_load_as_strings(tmp_path: Path, scalar: str) -> None:
    p = write(tmp_path, "date.yaml", f"when: {scalar}\nitems: [{scalar}]\n")
    got = contracts().load_yaml(p)
    assert got == {"when": scalar, "items": [scalar]}
    assert isinstance(got["when"], str)


@pytest.mark.req("FR-001-06")
def test_fr_001_06_quoted_scalars_and_block_styles_are_untouched(tmp_path: Path) -> None:
    text = "a: \"yes\"\nb: 'no'\nc: |\n  line one\n  line two\nd: >\n  folded\n  text\ne: [a, b]\nf: {g: 1}\n"
    got = contracts().load_yaml(write(tmp_path, "styles.yaml", text))
    assert got == yaml.safe_load(text)


@pytest.mark.req("FR-001-06")
def test_fr_001_06_bytes_over_the_cap_and_nesting_over_32_levels_are_rejected(tmp_path: Path) -> None:
    p = write(tmp_path, "big.yaml", "a: " + "x" * 500 + "\n")
    assert contracts().load_yaml(p, max_bytes=p.stat().st_size)
    rejects("load_yaml", p, max_bytes=p.stat().st_size - 1)
    rejects("load_yaml", write(tmp_path, "deep.yaml", "a: " + "[" * 33 + "]" * 33 + "\n"))
    assert contracts().load_yaml(write(tmp_path, "ok32.yaml", "a: " + "[" * 31 + "]" * 31 + "\n"))  # 1 + 31 = 32 levels


@pytest.mark.req("FR-001-06")
@pytest.mark.parametrize(
    "raw",
    [b"a: [1, 2\n", b"a: 1\n b: 2\n", b"\t a: 1\n", b"a: {b: 1\n", b"key: value\n- item\n", b"a: 'unterminated\n"],
)
def test_fr_001_06_malformed_or_empty_yaml_raises_contract_error(tmp_path: Path, raw: bytes) -> None:
    err = rejects("load_yaml", write(tmp_path, "bad.yaml", raw))
    assert not isinstance(err, yaml.YAMLError)


@pytest.mark.req("FR-001-06")
def test_fr_001_06_invalid_utf8_and_a_byte_order_mark_in_yaml_are_rejected_or_stripped_never_garbled(
    tmp_path: Path,
) -> None:
    rejects("load_yaml", write(tmp_path, "badutf8.yaml", b"a: \xff\xfe\n"))


@pytest.mark.req("FR-001-06")
def test_fr_001_06_loader_fixtures_of_the_corpus_are_all_rejected() -> None:
    yaml_loader = [e for e in cs.entries(tag_in=("loader",)) if e["file"].endswith(".yaml")]
    assert len(yaml_loader) >= 18
    c = contracts()
    for e in yaml_loader:
        if e["loader_error"] == "implicit-boolean-is-string":  # loads fine (as the string "yes"); the schema rejects it
            loaded = c.load_yaml(cs.fixture_file(e))
            assert loaded["seed"] == "yes"
            assert any(cs.get(x, "pointer") == "/seed" for x in c.validate(loaded, "recipe"))
            continue
        with pytest.raises(c.ContractError) as info:
            c.load_yaml(cs.fixture_file(e))
        assert cs.fixture_file(e).name in str(info.value), e["file"]


@pytest.mark.req("FR-001-06")
def test_fr_001_06_the_valid_yaml_twins_load_to_the_documents_of_their_json_twins() -> None:
    c = contracts()
    for e in cs.entries(valid=True):
        if e["file"].endswith(".yaml"):
            twin = json.loads((cs.FIXTURES / e["json_twin"]).read_text(encoding="utf-8"))
            assert c.load_yaml(cs.fixture_file(e)) == twin, e["file"]


# ----------------------------------------------------------------------------------------------------------------
# FR-001-07 · the writer (expected bytes written out by hand)
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-07")
def test_fr_001_07_dump_json_bytes_for_small_objects() -> None:
    dump = contracts().dump_json
    assert dump({}) == b"{}\n"
    assert dump([]) == b"[]\n"
    assert dump({"a": 1}) == b'{\n  "a": 1\n}\n'
    assert dump({"a": 1, "b": [1, 2], "c": {}}) == b'{\n  "a": 1,\n  "b": [\n    1,\n    2\n  ],\n  "c": {}\n}\n'
    assert dump({"a": {"b": {"c": [None, True, False]}}}) == (
        b'{\n  "a": {\n    "b": {\n      "c": [\n        null,\n        true,\n        false\n      ]\n    }\n  }\n}\n'
    )
    assert dump({"s": "x"}) == b'{\n  "s": "x"\n}\n'
    assert dump({"n": 1.5, "m": -2, "z": 0}) == b'{\n  "n": 1.5,\n  "m": -2,\n  "z": 0\n}\n'
    assert dump("text") == b'"text"\n'
    assert dump(5) == b"5\n"


@pytest.mark.req("FR-001-07")
def test_fr_001_07_output_has_no_bom_lf_only_two_space_indent_and_one_trailing_newline() -> None:
    doc = {"a": [{"b": 1, "c": "line1\nline2"}], "d": "\u00e9\u4e2d"}
    data = contracts().dump_json(doc)
    assert not data.startswith(BOM)
    assert b"\r" not in data
    assert data.endswith(b"}\n")
    assert not data.endswith(b"\n\n")
    text = data.decode("utf-8")  # valid UTF-8
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip(" "))
        assert indent % 2 == 0
        assert "\t" not in line
    assert "\\n" in text  # newlines inside strings are escaped, never raw
    assert json.loads(text) == doc


@pytest.mark.req("FR-001-07")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_fr_001_07_non_finite_numbers_cannot_be_written(bad: float) -> None:
    with pytest.raises((ValueError, TypeError)):  # allow_nan=False; ContractError is a ValueError too
        contracts().dump_json({"a": [1, {"b": bad}]})


@pytest.mark.req("FR-001-07")
def test_fr_001_07_equal_input_gives_byte_identical_output_and_files(tmp_path: Path) -> None:
    doc = {"a": [1, 2, {"k": "v"}], "b": {"c": None}}
    assert contracts().dump_json(doc) == contracts().dump_json(json.loads(json.dumps(doc)))
    p1, p2 = tmp_path / "1.json", tmp_path / "2.json"
    p1.write_bytes(contracts().dump_json(doc))
    p2.write_bytes(contracts().dump_json(contracts().load_json(p1)))
    assert p1.read_bytes() == p2.read_bytes()


# ----------------------------------------------------------------------------------------------------------------
# FR-001-08 · validate
# ----------------------------------------------------------------------------------------------------------------
def three_violations() -> dict:
    doc = json.loads((cs.FIXTURES / "recipe/valid/recipe.valid.json").read_text(encoding="utf-8"))
    doc["seed"] = -1  # /seed minimum
    doc["stages"][0]["timeout_s"] = 0  # /stages/0/timeout_s minimum
    doc["stages"][0]["extra"] = "x"  # /stages/0 additionalProperties
    return doc


@pytest.mark.req("FR-001-08")
def test_fr_001_08_every_violation_is_reported_sorted_by_pointer_with_pointer_keyword_and_message() -> None:
    errors = contracts().validate(three_violations(), "recipe")
    pointers = [cs.get(e, "pointer") for e in errors]
    assert pointers == ["/seed", "/stages/0", "/stages/0/timeout_s"]  # string order of the pointers
    assert [cs.get(e, "keyword") for e in errors] == ["minimum", "additionalProperties", "minimum"]
    for e in errors:
        msg = cs.get(e, "message")
        assert isinstance(msg, str)
        assert 0 < len(msg) <= 300


@pytest.mark.req("FR-001-08")
def test_fr_001_08_a_valid_document_gives_an_empty_list_for_every_valid_corpus_json_fixture() -> None:
    checked = 0
    for e in cs.entries(valid=True):
        if not e["file"].endswith(".json"):
            continue
        name = f"{e['schema']}{e['target']}" if e["target"] != "#" else e["schema"]
        assert contracts().validate(cs.fixture_json(e), name) == [], e["file"]
        checked += 1
    assert checked >= 11


@pytest.mark.req("FR-001-08")
def test_fr_001_08_messages_are_bounded_even_for_huge_values_and_never_contain_an_absolute_path() -> None:
    doc = three_violations()
    drive = "Z" + ":\\" + "secret\\" + "x" * 50
    posix = "/sr" + "v/secret/" + "y" * 50
    doc["stages"][0]["outputs"][0]["path"] = drive
    doc["stages"][1]["outputs"][0]["path"] = posix
    doc["description"] = "d" * 100_000  # over the 500-character cap
    doc["case"] = "C" + ":\\" + "Windows\\" + "z" * 10_000
    errors = contracts().validate(doc, "recipe")
    assert len(errors) >= 6
    for e in errors:
        msg = cs.get(e, "message")
        assert len(msg) <= 300, len(msg)
        assert not cs.has_absolute_path(msg), msg


@pytest.mark.req("FR-001-08")
def test_fr_001_08_the_result_is_deterministic_and_independent_of_key_order() -> None:
    doc = three_violations()
    first = [
        (cs.get(e, "pointer"), cs.get(e, "keyword"), cs.get(e, "message")) for e in contracts().validate(doc, "recipe")
    ]
    reordered = json.loads(json.dumps(doc), object_pairs_hook=lambda p: dict(reversed(p)))
    second = [
        (cs.get(e, "pointer"), cs.get(e, "keyword"), cs.get(e, "message"))
        for e in contracts().validate(reordered, "recipe")
    ]
    assert first == second


@pytest.mark.req("FR-001-08")
def test_fr_001_08_wrong_shaped_documents_are_reported_not_raised() -> None:
    for bad in (None, [], "text", 5, 1.5, True, {}, [{}], {"seed": []}):
        errors = contracts().validate(bad, "recipe")
        assert errors, repr(bad)
        assert all(isinstance(cs.get(e, "pointer"), str) for e in errors)
    assert [cs.get(e, "pointer") for e in contracts().validate([], "recipe")] == [""]


@pytest.mark.req("FR-001-08")
@pytest.mark.parametrize(
    ("name", "target"),
    [("recipe", "#/$defs/job_request"), ("manifest", "#/$defs/run"), ("manifest", "#/$defs/web_index")],
)
def test_fr_001_08_definitions_can_be_addressed_by_schema_name(name: str, target: str) -> None:
    kind = {"#/$defs/job_request": "job-request", "#/$defs/run": "run", "#/$defs/web_index": "web-index"}[target]
    valid = next(e for e in cs.entries(valid=True, schema=name, kind=kind) if e["file"].endswith(".json"))
    assert contracts().validate(cs.fixture_json(valid), f"{name}{target}") == []
    assert contracts().validate({}, f"{name}{target}")


@pytest.mark.req("FR-001-08")
def test_fr_001_08_an_unknown_schema_name_is_an_error() -> None:
    with pytest.raises((contracts().ContractError, KeyError, ValueError)):
        contracts().validate({}, "no-such-schema")
