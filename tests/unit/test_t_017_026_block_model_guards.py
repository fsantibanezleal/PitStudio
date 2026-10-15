"""T-017-026: hostile block-model and MineLib files (unit, hostile).

Requirements: FR-017-27.

Spec: specs/017-planning-survey/spec.md FR-017-27: if a block model or MineLib file has a non-finite value, a
duplicate
block id, a precedence that names an unknown block, a negative tonnage, a grade outside [0, 1], an unknown
destination,
a sum of |v| in cents >= 2^62 (>= 2^53 for the web engine), or a file path that is absolute or contains `..`, then the
loader rejects it with the reason and produces no shell. plan.md test strategy row FR-017-27: invalid files and
configurations built by the test.

Oracles: the spec's valid example `contracts/examples/block-model.valid.json` (four blocks; block 0 requires 1, 2, 3;
values per destination, `mill` 5.0 / `waste` -1.0 for block 0) as the base document, modified one field at a time by
hand; the bounds 2^62 = 4,611,686,018,427,387,904 and 2^53 = 9,007,199,254,740,992 cents (hand arithmetic: two
blocks of
2.3e16 USD sum to 4.6e18 cents < 2^62 but two blocks of 2.5e16 USD sum to 5e18 >= 2^62; two blocks of 4.6e13 USD
sum to
9.2e15 cents >= 2^53 and are accepted by the Python loader); MineLib text files written by hand in the test in the
published formats (`.blocks`: `id x y z <free columns>`; `.prec`: `b n p_1 ... p_n`; `.upit`: a keyword header, then
`b value`).

Expected public API (module `pitstudio.planning.loader`, root environment):
    class BlockModelError(ValueError)       # `.reason: str`; the message contains the keyword listed per case below
    @dataclass LoadedModel                  # ids: list[int], values_cents: np.ndarray[int64] (best destination
    value per
                                            # block, in cents), arcs: np.ndarray[int64] (m, 2) of index pairs "i
                                            # requires
                                            # j", tonnage: np.ndarray[float64]
    load_block_model(doc: Mapping, *, engine: str = "python") -> LoadedModel
        DC-017-02 document; engine "python" (sum of |v| in cents < 2^62) or "web" (< 2^53). Keywords: "finite",
        "duplicate", "unknown block", "tonnage", "grade", "destination", "sum" (the bound), "blocks" (an empty or
        malformed block list).
    load_minelib(root: Path, blocks: str, prec: str, upit: str) -> LoadedModel
        reads `<root>/<blocks>`, `<root>/<prec>`, `<root>/<upit>`; keywords: "path" (absolute, drive letter,
        backslash or `..`), "finite", "duplicate", "unknown block", "parse", "blocks" (row count differs from
        NBLOCKS).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from pitstudio.planning.loader import BlockModelError, LoadedModel, load_block_model, load_minelib

ROOT = Path(__file__).resolve().parents[2]
BASE = json.loads((ROOT / "specs/017-planning-survey/contracts/examples/block-model.valid.json").read_text("utf-8"))


def _doc() -> dict:
    return copy.deepcopy(BASE)


def _refuse(doc: dict, word: str, engine: str = "python") -> None:
    with pytest.raises(BlockModelError) as info:
        load_block_model(doc, engine=engine)
    assert word in info.value.reason


# ----------------------------------------------------------------------------------------------------------------------
# the valid example
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-27")
def test_the_valid_example_loads_with_the_best_destination_value_in_cents() -> None:
    model = load_block_model(_doc())
    assert isinstance(model, LoadedModel)
    assert model.ids == [0, 1, 2, 3]
    assert model.values_cents.dtype == np.int64
    assert model.values_cents.tolist() == [500, -100, -100, -100]  # max over destinations: 5.0, -1.0, -1.0, -1.0
    assert sorted(map(tuple, model.arcs.tolist())) == [(0, 1), (0, 2), (0, 3)]
    assert model.tonnage.tolist() == [1000.0] * 4


# ----------------------------------------------------------------------------------------------------------------------
# hostile block models
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-27")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_value_is_rejected(bad: float) -> None:
    doc = _doc()
    doc["blocks"][2]["values_usd"]["mill"] = bad
    _refuse(doc, "finite")


@pytest.mark.req("FR-017-27")
def test_non_numeric_values_and_coordinates_are_rejected() -> None:
    doc = _doc()
    doc["blocks"][1]["values_usd"]["waste"] = "-1.0"
    with pytest.raises(BlockModelError):
        load_block_model(doc)
    doc = _doc()
    doc["blocks"][1]["tonnage_t"] = None
    with pytest.raises(BlockModelError):
        load_block_model(doc)


@pytest.mark.req("FR-017-27")
def test_a_duplicate_block_id_is_rejected() -> None:
    doc = _doc()
    doc["blocks"][3]["id"] = 1
    _refuse(doc, "duplicate")


@pytest.mark.req("FR-017-27")
@pytest.mark.parametrize("unknown", [4, 99, -1])
def test_a_precedence_naming_an_unknown_block_is_rejected(unknown: int) -> None:
    doc = _doc()
    doc["blocks"][0]["prec"] = [1, 2, unknown]
    _refuse(doc, "unknown block")


@pytest.mark.req("FR-017-27")
@pytest.mark.parametrize("tonnage", [-1.0, -0.001, float("-inf")])
def test_a_negative_tonnage_is_rejected(tonnage: float) -> None:
    doc = _doc()
    doc["blocks"][1]["tonnage_t"] = tonnage
    with pytest.raises(BlockModelError) as info:
        load_block_model(doc)
    assert "tonnage" in info.value.reason or "finite" in info.value.reason


@pytest.mark.req("FR-017-27")
def test_zero_tonnage_is_accepted() -> None:
    doc = _doc()
    doc["blocks"][1]["tonnage_t"] = 0.0
    assert load_block_model(doc).tonnage[1] == 0.0


@pytest.mark.req("FR-017-27")
@pytest.mark.parametrize(
    ("grade", "ok"), [(0.0, True), (1.0, True), (0.5, True), (-0.001, False), (1.001, False), (5.0, False)]
)
def test_a_grade_must_lie_in_0_1(grade: float, ok: bool) -> None:
    doc = _doc()
    doc["blocks"][0]["grade"] = grade
    if ok:
        assert load_block_model(doc).ids == [0, 1, 2, 3]
    else:
        _refuse(doc, "grade")


@pytest.mark.req("FR-017-27")
@pytest.mark.parametrize("destination", ["ore", "dump", "", "MILL"])
def test_an_unknown_destination_is_rejected(destination: str) -> None:
    doc = _doc()
    doc["blocks"][1]["values_usd"][destination] = 1.0
    _refuse(doc, "destination")


@pytest.mark.req("FR-017-27")
@pytest.mark.parametrize("destination", ["mill", "waste", "leach", "stockpile"])
def test_the_four_known_destinations_are_accepted(destination: str) -> None:
    doc = _doc()
    doc["blocks"][1]["values_usd"] = {destination: 2.5}
    assert load_block_model(doc).values_cents[1] == 250


@pytest.mark.req("FR-017-27")
def test_the_python_bound_on_the_sum_of_absolute_values_is_2_pow_62_cents() -> None:
    ok = _doc()
    ok["blocks"][1]["values_usd"] = {"mill": 2.3e16}
    ok["blocks"][2]["values_usd"] = {"mill": -2.3e16}
    assert load_block_model(ok).values_cents.tolist()[1:3] == [2_300_000_000_000_000_000, -2_300_000_000_000_000_000]
    bad = _doc()
    bad["blocks"][1]["values_usd"] = {"mill": 2.5e16}
    bad["blocks"][2]["values_usd"] = {"mill": -2.5e16}
    _refuse(bad, "sum")


@pytest.mark.req("FR-017-27")
def test_the_web_bound_is_2_pow_53_cents_and_the_python_loader_accepts_what_the_web_engine_refuses() -> None:
    doc = _doc()
    doc["blocks"][1]["values_usd"] = {"mill": 4.6e13}
    doc["blocks"][2]["values_usd"] = {"mill": -4.6e13}  # sum |v| = 9.2e15 cents >= 2^53 = 9.007e15
    assert load_block_model(doc, engine="python").ids == [0, 1, 2, 3]
    _refuse(doc, "sum", engine="web")
    small = _doc()
    assert load_block_model(small, engine="web").ids == [0, 1, 2, 3]


@pytest.mark.req("FR-017-27")
@pytest.mark.parametrize("blocks", [[], None, "x", [1, 2], [{"id": 0}]])
def test_an_empty_or_malformed_block_list_is_rejected(blocks) -> None:
    doc = _doc()
    doc["blocks"] = blocks
    with pytest.raises(BlockModelError):
        load_block_model(doc)


@pytest.mark.req("FR-017-27")
def test_a_rejected_model_produces_nothing_to_solve() -> None:
    doc = _doc()
    doc["blocks"][0]["prec"] = [77]
    with pytest.raises(BlockModelError):
        load_block_model(doc)  # the exception is the only outcome: no LoadedModel is returned


# ----------------------------------------------------------------------------------------------------------------------
# hostile MineLib files
# ----------------------------------------------------------------------------------------------------------------------

BLOCKS = "0 0 0 0 0.01 1000 2.7\n1 1 0 0 0.00 1000 2.7\n2 0 0 1 0.00 1000 2.7\n"
PREC = "0 2 1 2\n1 0 \n2 0 \n"
UPIT = "NAME: tiny\nTYPE: UPIT\nNBLOCKS: 3\nOBJECTIVE_FUNCTION:\n0 5\n1 -1\n2 -1\n"


def _write(tmp_path: Path, blocks: str = BLOCKS, prec: str = PREC, upit: str = UPIT) -> Path:
    (tmp_path / "tiny.blocks").write_text(blocks, encoding="ascii")
    (tmp_path / "tiny.prec").write_text(prec, encoding="ascii")
    (tmp_path / "tiny.upit").write_text(upit, encoding="ascii")
    return tmp_path


@pytest.mark.req("FR-017-27")
def test_a_valid_minelib_instance_loads(tmp_path: Path) -> None:
    model = load_minelib(_write(tmp_path), "tiny.blocks", "tiny.prec", "tiny.upit")
    assert model.ids == [0, 1, 2]
    assert model.values_cents.tolist() == [500, -100, -100]
    assert sorted(map(tuple, model.arcs.tolist())) == [(0, 1), (0, 2)]


@pytest.mark.req("FR-017-27")
@pytest.mark.parametrize(
    "bad_path",
    [
        "/etc/tiny.blocks",
        "../tiny.blocks",
        "sub/../../tiny.blocks",
        "C:/tiny.blocks",
        "C:tiny.blocks",
        "..\\tiny.blocks",
        "\\\\host\\s\\x",
    ],
)
def test_an_absolute_or_parent_relative_file_path_is_rejected_in_any_of_the_three_slots(
    tmp_path: Path, bad_path: str
) -> None:
    root = _write(tmp_path)
    for args in (
        (bad_path, "tiny.prec", "tiny.upit"),
        ("tiny.blocks", bad_path, "tiny.upit"),
        ("tiny.blocks", "tiny.prec", bad_path),
    ):
        with pytest.raises(BlockModelError) as info:
            load_minelib(root, *args)
        assert "path" in info.value.reason


@pytest.mark.req("FR-017-27")
@pytest.mark.parametrize("token", ["nan", "inf", "-inf", "NaN", "Infinity"])
def test_a_non_finite_value_in_the_upit_file_is_rejected(tmp_path: Path, token: str) -> None:
    root = _write(tmp_path, upit=UPIT.replace("1 -1", f"1 {token}"))
    with pytest.raises(BlockModelError) as info:
        load_minelib(root, "tiny.blocks", "tiny.prec", "tiny.upit")
    assert "finite" in info.value.reason or "parse" in info.value.reason


@pytest.mark.req("FR-017-27")
def test_a_duplicate_block_id_in_the_blocks_file_is_rejected(tmp_path: Path) -> None:
    root = _write(tmp_path, blocks=BLOCKS.replace("2 0 0 1", "1 0 0 1"))
    with pytest.raises(BlockModelError) as info:
        load_minelib(root, "tiny.blocks", "tiny.prec", "tiny.upit")
    assert "duplicate" in info.value.reason


@pytest.mark.req("FR-017-27")
def test_a_precedence_row_naming_an_unknown_block_is_rejected(tmp_path: Path) -> None:
    root = _write(tmp_path, prec="0 2 1 9\n1 0 \n2 0 \n")
    with pytest.raises(BlockModelError) as info:
        load_minelib(root, "tiny.blocks", "tiny.prec", "tiny.upit")
    assert "unknown block" in info.value.reason


@pytest.mark.req("FR-017-27")
@pytest.mark.parametrize(
    ("which", "text"),
    [("blocks", "0 a b c\n"), ("prec", "0 two 1 2\n"), ("upit", "NAME: x\nNBLOCKS: 3\nOBJECTIVE_FUNCTION:\n0 five\n")],
)
def test_malformed_files_are_rejected_with_a_parse_reason(tmp_path: Path, which: str, text: str) -> None:
    kwargs = {"blocks": BLOCKS, "prec": PREC, "upit": UPIT, which: text}
    root = _write(tmp_path, **kwargs)
    with pytest.raises(BlockModelError) as info:
        load_minelib(root, "tiny.blocks", "tiny.prec", "tiny.upit")
    assert "parse" in info.value.reason


@pytest.mark.req("FR-017-27")
def test_a_row_count_that_differs_from_nblocks_is_rejected(tmp_path: Path) -> None:
    root = _write(tmp_path, upit=UPIT.replace("NBLOCKS: 3", "NBLOCKS: 4"))
    with pytest.raises(BlockModelError) as info:
        load_minelib(root, "tiny.blocks", "tiny.prec", "tiny.upit")
    assert "blocks" in info.value.reason


@pytest.mark.req("FR-017-27")
def test_a_missing_file_is_rejected_with_the_reason(tmp_path: Path) -> None:
    root = _write(tmp_path)
    (root / "tiny.prec").unlink()
    with pytest.raises(BlockModelError):
        load_minelib(root, "tiny.blocks", "tiny.prec", "tiny.upit")
