"""T-001-040 · serialisation round trip, YAML/JSON syntax invariance with RFC 8785 bytes, validation determinism:
P-001-05, P-001-07, P-001-08.

Oracles:
* RFC 8785 (JSON Canonicalization Scheme): the section 3.2.4 example, the section 3.2.3 key-order example (UTF-16 code
  unit order) and the Appendix B IEEE-754 number samples are fixed vectors; the expected strings were cross-checked
  with Node's ``JSON.stringify`` (ECMAScript Number::toString, the algorithm RFC 8785 mandates) when this file was
  written. They are not produced by the code under test.
* PyYAML as the reference producer of the YAML renderings (block, flow, all-quoted, reversed key order, comments).
* Hypothesis strategies of ``tests/contract/strategies.py`` (values inside the patterns and bounds of data-model 1-6).

Expected API: ``pitstudio.contracts.{load_json, load_yaml, dump_json, validate}``,
``pitstudio.contracts.jcs.canonicalize(value) -> bytes`` (RFC 8785, UTF-8; NaN and infinity raise ``ValueError``).
"""

from __future__ import annotations

import json
import os
import random
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contract"))
import contract_support as cs
import strategies

PROP = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much],
)


def pc() -> Any:
    import pitstudio.contracts as c

    return c


def canonicalize(value: Any) -> bytes:
    from pitstudio.contracts.jcs import canonicalize as impl

    return impl(value)


def tmpdir() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(dir=os.environ.get("PITSTUDIO_TMP") or None)


def write_load(loader: str, data: bytes | str, suffix: str) -> Any:
    with tmpdir() as d:
        p = Path(d) / f"doc{suffix}"
        p.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        return getattr(pc(), loader)(p)


# ----------------------------------------------------------------------------------------------------------------
# P-001-05 · serialisation round trip
# ----------------------------------------------------------------------------------------------------------------
FAMILIES = {
    "recipe": strategies.recipes(),
    "job_request": strategies.job_requests(),
    "tools": strategies.tools_registries(),
    "sources": strategies.sources_registries(),
    "capabilities": strategies.capabilities(),
    "run": strategies.run_manifests(),
    "web_index": strategies.web_indexes(),
}


@pytest.mark.req("P-001-05")
@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_p_001_05_load_json_of_dump_json_is_the_identity_and_the_bytes_are_stable(family: str) -> None:
    @PROP
    @given(doc=FAMILIES[family])
    def check(doc: dict) -> None:
        first = pc().dump_json(doc)
        loaded = write_load("load_json", first, ".json")
        assert loaded == doc
        assert pc().dump_json(loaded) == first  # dump(load(dump(d))) is byte-identical to dump(d)
        assert first.endswith(b"\n")
        assert b"\r" not in first
        assert not first.startswith(b"\xef\xbb\xbf")

    check()


@pytest.mark.req("P-001-05")
@PROP
@given(
    value=st.recursive(
        st.one_of(
            st.none(),
            st.booleans(),
            st.integers(-(2**63), 2**63 - 1),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(max_size=12),
        ),
        lambda children: st.one_of(
            st.lists(children, max_size=4), st.dictionaries(st.text(max_size=6), children, max_size=4)
        ),
        max_leaves=20,
    )
)
def test_p_001_05_arbitrary_json_values_round_trip(value: Any) -> None:
    try:
        first = pc().dump_json(value)
    except ValueError, UnicodeError:
        return  # a lone surrogate in a string cannot be written as UTF-8: allowed to refuse, never to corrupt
    assert write_load("load_json", first, ".json") == value
    assert pc().dump_json(write_load("load_json", first, ".json")) == first


# ----------------------------------------------------------------------------------------------------------------
# RFC 8785 fixed vectors
# ----------------------------------------------------------------------------------------------------------------
RFC_3_2_4_JSON = (
    '{\n  "numbers": [333333333.33333329, 1E30, 4.50, 2e-3, 0.000000000000000000000000001],\n'
    '  "string": "\\u20ac$\\u000F\\u000aA\'\\u0042\\u0022\\u005c\\\\\\"/",\n  "literals": [null, true, false]\n}\n'
)
RFC_3_2_4_CANONICAL = (
    '{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
    '"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
).encode()
# the same data in YAML 1.1 spelling (floats need a dot and a signed exponent there)
RFC_3_2_4_YAML = (
    "numbers: [333333333.33333329, 1.0e+30, 4.50, 2.0e-3, 0.000000000000000000000000001]\n"
    'string: "\\u20ac$\\x0F\\nA\'B\\"\\\\\\\\\\"/"\n'
    "literals: [null, true, false]\n"
)

# RFC 8785 Appendix B (IEEE-754 bits -> expected serialisation); NaN and Infinity must be refused
APPENDIX_B = [
    ("0000000000000000", "0"),
    ("8000000000000000", "0"),
    ("0000000000000001", "5e-324"),
    ("8000000000000001", "-5e-324"),
    ("7fefffffffffffff", "1.7976931348623157e+308"),
    ("ffefffffffffffff", "-1.7976931348623157e+308"),
    ("4340000000000000", "9007199254740992"),
    ("c340000000000000", "-9007199254740992"),
    ("4430000000000000", "295147905179352830000"),
    ("44b52d02c7e14af5", "9.999999999999997e+22"),
    ("44b52d02c7e14af6", "1e+23"),
    ("44b52d02c7e14af7", "1.0000000000000001e+23"),
    ("444b1ae4d6e2ef4e", "999999999999999700000"),
    ("444b1ae4d6e2ef4f", "999999999999999900000"),
    ("444b1ae4d6e2ef50", "1e+21"),
    ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7"),
    ("3eb0c6f7a0b5ed8d", "0.000001"),
    ("41b3de4355555553", "333333333.3333332"),
    ("41b3de4355555554", "333333333.33333325"),
    ("41b3de4355555555", "333333333.3333333"),
    ("41b3de4355555556", "333333333.3333334"),
    ("41b3de4355555557", "333333333.33333343"),
    ("becbf647612f3696", "-0.0000033333333333333333"),
    ("43143ff3c1cb0959", "1424953923781206.2"),
]


@pytest.mark.req("P-001-07")
@pytest.mark.parametrize(("bits", "expected"), APPENDIX_B, ids=[b for b, _ in APPENDIX_B])
def test_p_001_07_rfc_8785_appendix_b_number_samples(bits: str, expected: str) -> None:
    value = struct.unpack(">d", bytes.fromhex(bits))[0]
    assert canonicalize(value) == expected.encode("ascii")
    assert canonicalize([value]) == b"[" + expected.encode("ascii") + b"]"


@pytest.mark.req("P-001-07")
@pytest.mark.parametrize("bits", ["7fffffffffffffff", "ffffffffffffffff", "7ff0000000000000", "fff0000000000000"])
def test_p_001_07_nan_and_infinity_cannot_be_canonicalised(bits: str) -> None:
    value = struct.unpack(">d", bytes.fromhex(bits))[0]
    with pytest.raises((ValueError, TypeError)):
        canonicalize(value)
    with pytest.raises((ValueError, TypeError)):
        canonicalize({"a": [1, value]})


@pytest.mark.req("P-001-07")
def test_p_001_07_rfc_8785_section_3_2_4_example_from_json_and_from_yaml() -> None:
    loaded = write_load("load_json", RFC_3_2_4_JSON, ".json")
    assert canonicalize(loaded) == RFC_3_2_4_CANONICAL
    from_yaml = write_load("load_yaml", RFC_3_2_4_YAML, ".yaml")
    assert canonicalize(from_yaml) == RFC_3_2_4_CANONICAL
    assert from_yaml == loaded


@pytest.mark.req("P-001-07")
def test_p_001_07_rfc_8785_section_3_2_3_keys_are_sorted_by_utf16_code_units() -> None:
    keys = [
        "€ Euro Sign",
        "\r Carriage Return",
        "דּ Hebrew Letter Dalet With Dagesh",
        "1 One",
        "\U0001f600 Emoji: Grinning Face",
        "\u0080 Control",
        "ö Latin Small Letter O With Diaeresis",
    ]
    expected_order = [
        "\r Carriage Return",
        "1 One",
        "\u0080 Control",
        "ö Latin Small Letter O With Diaeresis",
        "€ Euro Sign",
        "\U0001f600 Emoji: Grinning Face",
        "דּ Hebrew Letter Dalet With Dagesh",
    ]
    out = canonicalize({k: 1 for k in keys}).decode("utf-8")
    positions = [out.index(json.dumps(k, ensure_ascii=False)[1:-1].replace("\r", "\\r")) for k in expected_order]
    assert positions == sorted(positions)
    # code point order would put U+E000 before the emoji; UTF-16 code unit order (D83D DE00 < E000) does not
    assert canonicalize({"": 2, "\U0001f600": 1}) == '{"\U0001f600":1,"":2}'.encode("utf-8")


@pytest.mark.req("P-001-07")
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, b"null"),
        (True, b"true"),
        (False, b"false"),
        (0, b"0"),
        (-0.0, b"0"),
        (1, b"1"),
        (-5, b"-5"),
        (1.5, b"1.5"),
        (0.1 + 0.2, b"0.30000000000000004"),
        (2**53, b"9007199254740992"),
        (10**21, b"1e+21"),
        (1e-7, b"1e-7"),
        (123456789.0, b"123456789"),
        ("", b'""'),
        ("a/b", b'"a/b"'),
        ('q"b\\', b'"q\\"b\\\\"'),
        ("\x00\x08\t\n\x0c\r\x1f", b'"\\u0000\\b\\t\\n\\f\\r\\u001f"'),
        ("\x7f", b'"\x7f"'),
        ("\U0001f600", b'"\xf0\x9f\x98\x80"'),
        ("é", b'"\xc3\xa9"'),
        ([], b"[]"),
        ({}, b"{}"),
        ([3, 1, 2], b"[3,1,2]"),
        ({"b": 1, "a": [True, None]}, b'{"a":[true,null],"b":1}'),
        ({"a": {"d": 1, "c": 2}}, b'{"a":{"c":2,"d":1}}'),
    ],
    ids=lambda v: repr(v)[:30],
)
def test_p_001_07_hand_worked_canonical_forms(value: Any, expected: bytes) -> None:
    assert canonicalize(value) == expected


@pytest.mark.req("P-001-07")
def test_p_001_07_a_lone_surrogate_or_a_non_string_key_cannot_be_canonicalised() -> None:
    with pytest.raises((ValueError, TypeError, UnicodeError)):
        canonicalize("\ud800")
    with pytest.raises((ValueError, TypeError)):
        canonicalize({1: "a"})


# ----------------------------------------------------------------------------------------------------------------
# P-001-07 · syntax invariance
# ----------------------------------------------------------------------------------------------------------------
YAML_FAMILIES = {"recipe": "recipe", "tools": "tools", "sources": "sources"}


def outcome(doc: Any, name: str) -> list[tuple[str, str, str]]:
    return [(cs.get(e, "pointer"), cs.get(e, "keyword"), cs.get(e, "message")) for e in pc().validate(doc, name)]


@pytest.mark.req("P-001-07")
@pytest.mark.parametrize("family", sorted(YAML_FAMILIES))
def test_p_001_07_every_yaml_rendering_gives_the_same_document_outcome_and_canonical_bytes_as_the_json(
    family: str,
) -> None:
    @PROP
    @given(doc=FAMILIES[family])
    def check(doc: dict) -> None:
        canonical = canonicalize(doc)
        json_loaded = write_load("load_json", pc().dump_json(doc), ".json")
        assert canonicalize(json_loaded) == canonical
        base_outcome = outcome(doc, family)
        assert base_outcome == []
        for style, text in strategies.render_yaml_variants(doc).items():
            loaded = write_load("load_yaml", text, ".yaml")
            assert loaded == doc, style
            assert canonicalize(loaded) == canonical, style
            assert outcome(loaded, family) == base_outcome, style

    check()


@pytest.mark.req("P-001-07")
@pytest.mark.parametrize("family", sorted(YAML_FAMILIES))
def test_p_001_07_broken_documents_fail_identically_in_every_syntax(family: str) -> None:
    @PROP
    @given(
        doc=FAMILIES[family].filter(lambda d: d.get("stages") or d.get("tools") or d.get("sources")),
        index=st.integers(0, 10),
    )
    def check(doc: dict, index: int) -> None:
        name, mutate, pointer, _keyword = strategies.MUTATIONS[family][index % len(strategies.MUTATIONS[family])]
        broken = mutate(doc)
        expected = outcome(broken, family)
        # the error sits at the mutated value or at an ancestor (a oneOf/anyOf reports at the object that holds it)
        assert any(pointer == p or pointer.startswith(p + "/") or p == "" for p, _, _ in expected), (name, expected[:3])
        assert outcome(write_load("load_json", pc().dump_json(broken), ".json"), family) == expected
        for style, text in strategies.render_yaml_variants(broken).items():
            assert outcome(write_load("load_yaml", text, ".yaml"), family) == expected, (name, style)

    check()


@pytest.mark.req("P-001-07")
def test_p_001_07_the_valid_corpus_yaml_files_and_their_json_twins_have_equal_canonical_bytes() -> None:
    twins = [e for e in cs.entries(valid=True) if e["file"].endswith(".yaml")]
    assert len(twins) == 3
    for e in twins:
        from_yaml = pc().load_yaml(cs.fixture_file(e))
        from_json = pc().load_json(cs.FIXTURES / e["json_twin"])
        assert canonicalize(from_yaml) == canonicalize(from_json), e["file"]


@pytest.mark.req("P-001-07")
def test_p_001_07_comments_flow_style_quoting_and_key_order_do_not_change_the_document() -> None:
    plain = "id: a2\nseed: 5\nstages: [x, y]\nnested: {k: v}\n"
    noisy = '# header\nnested:   # trailing\n  "k": "v"\nstages:\n  - "x"\n  - \'y\'   # last\nseed: 5\nid: "a2"\n'
    assert write_load("load_yaml", plain, ".yaml") == write_load("load_yaml", noisy, ".yaml")
    assert canonicalize(write_load("load_yaml", plain, ".yaml")) == canonicalize(
        write_load("load_yaml", noisy, ".yaml")
    )


# ----------------------------------------------------------------------------------------------------------------
# P-001-08 · validation determinism
# ----------------------------------------------------------------------------------------------------------------
def shuffled(value: Any, rng: random.Random) -> Any:
    if isinstance(value, dict):
        items = [(k, shuffled(v, rng)) for k, v in value.items()]
        rng.shuffle(items)
        return dict(items)
    if isinstance(value, list):
        return [shuffled(v, rng) for v in value]
    return value


def validate_name(entry: dict) -> str:
    return f"{entry['schema']}{entry['target']}" if entry["target"] != "#" else entry["schema"]


@pytest.mark.req("P-001-08")
def test_p_001_08_the_error_list_of_every_corpus_fixture_is_identical_across_runs_and_key_orders() -> None:
    checked = 0
    for e in cs.entries(tag_not_in=("loader",)):
        if not e["file"].endswith(".json"):
            continue
        doc = cs.fixture_json(e)
        name = validate_name(e)
        reference = outcome(doc, name)
        assert outcome(doc, name) == reference, e["file"]  # a second run
        assert [t[0] for t in reference] == sorted(t[0] for t in reference)  # sorted by pointer
        rng = random.Random(8128)
        for _ in range(3):
            assert outcome(shuffled(doc, rng), name) == reference, e["file"]
        checked += 1
    assert checked >= 150


@pytest.mark.req("P-001-08")
@pytest.mark.parametrize("family", ["recipe", "tools", "sources", "capabilities", "run", "web_index"])
def test_p_001_08_mutated_generated_documents_validate_deterministically(family: str) -> None:
    kind_name = {"run": "manifest#/$defs/run", "web_index": "manifest#/$defs/web_index"}.get(family, family)
    documents = FAMILIES[family]
    if family == "sources":  # the mutations edit the first entry: an empty registry has none
        documents = documents.filter(lambda d: bool(d["sources"]))
    if family == "run":
        documents = documents.filter(lambda d: bool(d["stages"]))

    @PROP
    @given(doc=documents, seed=st.integers(0, 10**6), index=st.integers(0, 10))
    def check(doc: dict, seed: int, index: int) -> None:
        mutations = strategies.MUTATIONS[family]
        broken = mutations[index % len(mutations)][1](doc)
        reference = outcome(broken, kind_name)
        assert reference, "a mutated document must fail"
        assert outcome(broken, kind_name) == reference
        assert outcome(shuffled(broken, random.Random(seed)), kind_name) == reference
        assert [t[0] for t in reference] == sorted(t[0] for t in reference)

    check()
