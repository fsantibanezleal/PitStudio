# ruff: noqa: E501
"""T-009-014 - FR-009-09: hostile randomisation configs are rejected before any rendering, with a JSON pointer.

Oracles (independent of the code under test):
- the spec's own contract examples: `specs/009-perception/contracts/examples/index.json` lists, for every hostile
  `sdg-randomisation.*` example, the expected JSON pointer of the (single) schema error; the reference validator
  `jsonschema` (Draft 2020-12) reports exactly one error pointer per file (one file has two errors at the same pointer ""),
  checked while writing this test, so "the first error" is unambiguous for them;
- hand-written hostile documents for the cases the schema cannot express: non-finite numbers (JSON Schema has no NaN),
  an unknown texture id (a lithology list naming an id absent from `texture_pool`), a huge image count, a boolean count;
- the unknown-key and wrong-unit examples report the pointer of the object that holds the unknown key (here the root,
  pointer ""), as the examples' index does.

Expected public API (module `pitstudio_studio.sdg.config`, package under `studio/src/`):

    SdgConfigError(ValueError)     attributes `pointer: str` (RFC 6901 pointer of the first error, "" for the root) and
                                   `reason: str`; str(error) contains the pointer (or the text "<root>" when it is "")
                                   and the reason.
    validate_config(doc: object) -> None
        Raises SdgConfigError for the first error of: a non-finite number anywhere (pointer to that number), any
        violation of sdg-randomisation.schema.json (pointer = absolute path of the schema error), a texture id listed in
        `structured.rock_textures.lithologies` that is not an `id` of `texture_pool` (pointer to that list entry, e.g.
        /structured/rock_textures/lithologies/quartz_monzonite/1). Order of checks: non-finite numbers, then schema
        errors, then the texture cross-reference (so a malformed texture_pool entry is reported before a dangling id).
        Returns None for a valid document.
    load_config(path: pathlib.Path) -> dict
        Reads the JSON file and validates it; SdgConfigError with pointer "" for an unreadable, non-UTF-8, empty or
        non-JSON file, for a JSON document that is not an object, and for the JSON tokens NaN / Infinity / -Infinity
        (pointer = the location of the number).
    run_guarded(config_path: pathlib.Path, render: Callable[[dict], object]) -> int
        The stage entry point: load_config, then `render(config)` and return 0; on SdgConfigError write one line with the
        pointer and the reason to stderr, never call `render`, and return a non-zero status (2).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_studio.sdg import config  # noqa: E402

INDEX = json.loads((kit.EXAMPLES / "index.json").read_text(encoding="utf-8"))["examples"]
HOSTILE = [
    (e["file"], e["pointer"]) for e in INDEX if e["schema"] == "sdg-randomisation.schema.json" and not e["valid"]
]


def _valid() -> dict:
    return kit.example("sdg-randomisation.valid.json")


@pytest.mark.req("FR-009-09")
def test_the_spec_lists_eighteen_hostile_sdg_configs() -> None:
    assert len(HOSTILE) == 18  # the oracle table itself is not silently empty


@pytest.mark.req("FR-009-09")
def test_a_valid_config_is_accepted() -> None:
    assert config.validate_config(_valid()) is None


@pytest.mark.req("FR-009-09")
@pytest.mark.parametrize(("name", "pointer"), HOSTILE, ids=[n for n, _ in HOSTILE])
def test_every_hostile_contract_example_is_rejected_with_the_pointer_of_its_error(name: str, pointer: str) -> None:
    with pytest.raises(config.SdgConfigError) as exc:
        config.validate_config(kit.example(name))
    assert exc.value.pointer == pointer
    assert isinstance(exc.value, ValueError)
    assert exc.value.reason


@pytest.mark.req("FR-009-09")
@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("x_os_m",), float("nan")),
        (("x_os_m",), float("inf")),
        (("drying_time_min",), float("-inf")),
        (("unstructured", "light_intensity_factor", "max"), float("nan")),
        (("unstructured", "colour_temperature_k", "min"), float("inf")),
        (("structured", "sun", "min_elevation_deg"), float("nan")),
        (("structured", "placement", "max_base_offset_m"), float("nan")),
        (("seed",), float("nan")),
    ],
)
def test_a_non_finite_number_is_rejected_at_its_own_pointer(path: tuple[str, ...], value: float) -> None:
    doc = _valid()
    node = doc
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(config.SdgConfigError) as exc:
        config.validate_config(doc)
    assert exc.value.pointer == "/" + "/".join(path)


@pytest.mark.req("FR-009-09")
def test_a_non_finite_image_count_is_rejected_at_its_own_pointer() -> None:
    doc = _valid()
    doc["arms"][1]["image_count"] = float("nan")
    with pytest.raises(config.SdgConfigError) as exc:
        config.validate_config(doc)
    assert exc.value.pointer == "/arms/1/image_count"


@pytest.mark.req("FR-009-09")
def test_an_unknown_texture_id_is_rejected_at_its_list_entry() -> None:
    doc = _valid()
    doc["structured"]["rock_textures"]["lithologies"]["quartz_monzonite"][1] = "rock-does-not-exist"
    with pytest.raises(config.SdgConfigError) as exc:
        config.validate_config(doc)
    assert exc.value.pointer == "/structured/rock_textures/lithologies/quartz_monzonite/1"


@pytest.mark.req("FR-009-09")
@pytest.mark.parametrize("count", [10**30, True, -(10**30), 1.5, None, "10000"])
def test_hostile_image_counts_are_rejected_at_the_count_pointer(count: object) -> None:
    doc = _valid()
    doc["arms"][0]["image_count"] = count
    with pytest.raises(config.SdgConfigError) as exc:
        config.validate_config(doc)
    assert exc.value.pointer == "/arms/0/image_count"


@pytest.mark.req("FR-009-09")
@pytest.mark.parametrize("doc", [None, [], "text", 7, [_valid()], {}])
def test_a_document_that_is_not_a_config_object_is_rejected(doc: object) -> None:
    with pytest.raises(config.SdgConfigError):
        config.validate_config(doc)


@pytest.mark.req("FR-009-09")
def test_a_unicode_texture_id_is_rejected() -> None:
    doc = _valid()
    doc["texture_pool"][0]["id"] = "rock-éñ"
    with pytest.raises(config.SdgConfigError) as exc:
        config.validate_config(doc)
    assert exc.value.pointer.startswith("/texture_pool/0")


@pytest.mark.req("FR-009-09")
def test_validation_does_not_modify_the_document() -> None:
    doc = _valid()
    before = copy.deepcopy(doc)
    config.validate_config(doc)
    assert doc == before


@pytest.mark.req("FR-009-09")
def test_load_config_reads_a_valid_file(tmp_path: Path) -> None:
    p = tmp_path / "recipe.json"
    p.write_text(json.dumps(_valid()), encoding="utf-8")
    assert config.load_config(p) == _valid()


@pytest.mark.req("FR-009-09")
@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"   \n",
        b"{",
        b"\xff\xfe\x00garbage",
        b"[1, 2, 3]",
        b"null",
        b"\x89PNG\r\n\x1a\n",
    ],
)
def test_malformed_files_are_rejected_with_the_root_pointer(tmp_path: Path, content: bytes) -> None:
    p = tmp_path / "bad.json"
    p.write_bytes(content)
    with pytest.raises(config.SdgConfigError) as exc:
        config.load_config(p)
    assert exc.value.pointer == ""


@pytest.mark.req("FR-009-09")
def test_a_missing_file_is_rejected_with_the_root_pointer(tmp_path: Path) -> None:
    with pytest.raises(config.SdgConfigError) as exc:
        config.load_config(tmp_path / "absent.json")
    assert exc.value.pointer == ""


@pytest.mark.req("FR-009-09")
@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_json_non_finite_tokens_in_a_file_are_rejected_at_their_pointer(tmp_path: Path, token: str) -> None:
    text = json.dumps(_valid()).replace('"x_os_m": 1.0', f'"x_os_m": {token}')
    assert token in text
    p = tmp_path / "nan.json"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(config.SdgConfigError) as exc:
        config.load_config(p)
    assert exc.value.pointer == "/x_os_m"


@pytest.mark.req("FR-009-09")
def test_the_stage_entry_renders_a_valid_config_and_returns_zero(tmp_path: Path) -> None:
    p = tmp_path / "recipe.json"
    p.write_text(json.dumps(_valid()), encoding="utf-8")
    calls: list[dict] = []
    assert config.run_guarded(p, calls.append) == 0
    assert calls == [_valid()]


@pytest.mark.req("FR-009-09")
@pytest.mark.parametrize(("name", "pointer"), HOSTILE[:6] + HOSTILE[-3:], ids=lambda v: str(v))
def test_the_stage_entry_never_renders_a_bad_config_and_reports_the_pointer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, pointer: str
) -> None:
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(kit.example(name)), encoding="utf-8")
    calls: list[dict] = []
    status = config.run_guarded(p, calls.append)
    assert status != 0
    assert calls == []  # rejected before any rendering
    err = capsys.readouterr().err
    assert (pointer if pointer else "<root>") in err
