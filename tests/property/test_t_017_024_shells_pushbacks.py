"""T-017-024: shells over the lambda grid and the pushback rule (property).

Requirements: FR-017-16, FR-017-17, P-017-03, P-017-09.

Spec: specs/017-planning-survey/spec.md
- FR-017-16: the shell generator solves the pit at the revenue factors lambda = 0.025, 0.050, ..., 1.000 (40
  values) and
  writes a shell table (DC-017-03) with lambda, block count, ore and waste tonnage, value and strip ratio;
- FR-017-17: the pushback rule walks the distinct shells in increasing lambda and closes a pushback when its
  cumulative
  incremental ore tonnage reaches T_min (default one period of processing capacity), merging a final remainder below
  T_min / 2 into the previous pushback, and reports each pushback's ore and waste tonnage and its incremental strip
  ratio;
- P-017-03: nesting: lambda_1 < lambda_2 implies pit(lambda_1) is a subset of pit(lambda_2) (40-value grid, random
  deposits; exact);
- P-017-09: pushbacks partition the final pit: they are disjoint, their union is the pit, and the union of the first k
  pushbacks is one of the shells (random deposits; exact).
plan.md test strategy rows FR-017-16 / FR-017-17: hand-built 2-D deposits with known shells; the T_min rule by hand.

Oracles:
- the spec's own four-block example `contracts/examples/pit-shells.valid.json`: one ore block (1,000 t) over three
  waste
  blocks (1,000 t each); at lambda 0.5 the pit is empty (`"blocks": "AA=="`), at lambda 1.0 it is all four blocks
  (`"Dw=="`,
  ore 1,000 t, waste 3,000 t, value 200 cents, strip ratio 3.0); its pushback record (shell 1, ore 1,000, waste 3,000,
  incremental and cumulative strip ratio 3.0) is the expected output of the rule with T_min = 1,000 t. The deposit
  that
  reproduces it by hand: tonnage 1,000 t each, grade (0.006, 0, 0, 0), recovery 1, net price 1, processing cost 0,
  mining
  cost 0.001 USD/t, arcs (0, 1), (0, 2), (0, 3): the ore block is worth 1,000 x lambda x 0.006 - 1 = 6 lambda - 1 USD
  (2 at lambda 0.5, 5 at 1) and each waste block -1 USD;
- the bitset encoding `bitset-lsb0-base64` of the contract (bit i = byte i // 8, bit i % 8; standard base64 with
  padding): blocks 0..3 -> byte 0x0F -> "Dw=="; blocks 0 and 9 -> bytes 01 02 -> "AQI=";
- the T_min rule worked by hand on cumulative ore tonnages (see the fixtures below);
- the nesting, partition and prefix-is-a-shell properties on random level-cone deposits.

Expected public API (root environment, numpy only):
module `pitstudio.planning.shells`
    LAMBDA_GRID: tuple[float, ...]         # 0.025, 0.050, ..., 1.000 (40 values)
    encode_bitset(mask) -> str; decode_bitset(text: str, n: int) -> np.ndarray[bool]     # bitset-lsb0-base64
    compute_shells(tonnage, grade, arcs, *, recovery, net_price, processing_cost, mining_cost,
                   lambdas: Sequence[float] = LAMBDA_GRID) -> ShellTable
        ShellTable.rows: one dict per lambda {"lambda", "blocks" (bitset text), "block_count", "ore_t", "waste_t",
        "value_cents", "strip_ratio" (waste / ore, None when ore is 0)}; ShellTable.masks: the boolean masks, same
        order;
        ShellTable.ultimate_pit: {"shell": index of the last lambda, "value_cents", "strip_ratio"}. A block is ore
        in a
        shell when lambda g r (p - s_r) - c_p > 0, else waste; the pit of each lambda is `ultimate_pit` on the
        cents of
        `block_values(..., lam=lambda)`.
module `pitstudio.planning.pushbacks`
    build_pushbacks(shells: Sequence[Mapping], *, t_min_t: float) -> list[dict]
        shells: cumulative records {"lambda", "mask" (bool array), "ore_t", "waste_t"} in increasing lambda; empty
        shells and shells whose mask equals the previous one are skipped (distinct shells only). Returns, per
        pushback, {"shell": index (in `shells`) of the last shell it contains, "mask": the blocks added by it
        (disjoint
        from the others), "ore_t", "waste_t" (increments), "strip_ratio_incremental", "strip_ratio_cumulative" (None
        when the ore is 0)}. ValueError for t_min_t <= 0 or non-finite.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.planning.pushbacks import build_pushbacks
from pitstudio.planning.shells import LAMBDA_GRID, compute_shells, decode_bitset, encode_bitset

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads((ROOT / "specs/017-planning-survey/contracts/examples/pit-shells.valid.json").read_text("utf-8"))
ECON = {"recovery": 1.0, "net_price": 1.0, "processing_cost": 0.0, "mining_cost": 0.001}


def _four_blocks():
    return np.full(4, 1000.0), np.array([0.006, 0.0, 0.0, 0.0]), np.array([[0, 1], [0, 2], [0, 3]], dtype=np.int64)


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-16
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-16")
def test_the_lambda_grid_has_the_40_values_0_025_to_1() -> None:
    assert len(LAMBDA_GRID) == 40
    assert LAMBDA_GRID[0] == 0.025
    assert LAMBDA_GRID[-1] == 1.0
    for k, lam in enumerate(LAMBDA_GRID, start=1):
        assert lam == pytest.approx(0.025 * k, abs=1e-12)
    assert all(b > a for a, b in itertools.pairwise(LAMBDA_GRID))


@pytest.mark.req("FR-017-16")
def test_the_bitset_encoding_is_lsb0_base64_with_padding() -> None:
    assert encode_bitset(np.array([True, True, True, True])) == "Dw=="
    assert encode_bitset(np.array([False] * 4)) == "AA=="
    mask = np.zeros(10, dtype=bool)
    mask[[0, 9]] = True
    assert encode_bitset(mask) == "AQI="
    assert decode_bitset("AQI=", 10).tolist() == mask.tolist()
    assert decode_bitset("Dw==", 4).tolist() == [True] * 4


@pytest.mark.req("FR-017-16")
def test_the_four_block_example_gives_the_spec_shells_and_ultimate_pit() -> None:
    tonnage, grade, arcs = _four_blocks()
    table = compute_shells(tonnage, grade, arcs, lambdas=[0.5, 1.0], **ECON)
    assert table.rows == EXAMPLE["shells"]
    assert table.ultimate_pit == EXAMPLE["ultimate_pit"]
    assert [m.tolist() for m in table.masks] == [[False] * 4, [True] * 4]


@pytest.mark.req("FR-017-16")
def test_the_default_grid_gives_40_rows_in_increasing_lambda_with_consistent_fields() -> None:
    tonnage, grade, arcs = _four_blocks()
    table = compute_shells(tonnage, grade, arcs, **ECON)
    assert len(table.rows) == len(table.masks) == 40
    assert [r["lambda"] for r in table.rows] == list(LAMBDA_GRID)
    for row, mask in zip(table.rows, table.masks, strict=True):
        assert row["block_count"] == int(mask.sum())
        assert row["blocks"] == encode_bitset(mask)
    # the ore block pays off when 6 lambda - 1 > 3, i.e. lambda > 2/3: the first such grid value is 0.675
    full = [r["lambda"] for r in table.rows if r["block_count"] == 4]
    assert full[0] == pytest.approx(0.675)
    assert all(r["block_count"] in (0, 4) for r in table.rows)


@pytest.mark.req("FR-017-16")
def test_ore_and_waste_tonnage_split_by_destination_and_the_strip_ratio_is_waste_over_ore() -> None:
    # a 2-block deposit: ore block 0 (500 t, grade 0.03) requires waste block 1 (700 t, grade 0)
    tonnage, grade = np.array([500.0, 700.0]), np.array([0.03, 0.0])
    arcs = np.array([[0, 1]], dtype=np.int64)
    econ = {"recovery": 1.0, "net_price": 100.0, "processing_cost": 20.0, "mining_cost": 5.0}
    # grade 0.03 x 100 USD/t = 3 USD/t < c_p 20: block 0 is never ore at lambda 1 or 2, so the pit stays empty
    table = compute_shells(tonnage, grade, arcs, lambdas=[1.0, 2.0], **econ)
    assert [r["block_count"] for r in table.rows] == [0, 0]
    rich = compute_shells(tonnage, np.array([0.5, 0.0]), arcs, lambdas=[1.0], **econ)
    # block 0: lambda g r p' - c_p = 50 - 20 = 30 > 0 -> ore; value 500 x 30 - 2,500 = 12,500; waste block -3,500
    row = rich.rows[0]
    assert (row["block_count"], row["ore_t"], row["waste_t"]) == (2, 500.0, 700.0)
    assert row["value_cents"] == (12_500 - 3_500) * 100
    assert row["strip_ratio"] == pytest.approx(700.0 / 500.0)


@pytest.mark.req("FR-017-16")
def test_a_shell_without_ore_has_a_null_strip_ratio() -> None:
    tonnage, grade, arcs = _four_blocks()
    row = compute_shells(tonnage, grade, arcs, lambdas=[0.5], **ECON).rows[0]
    assert (row["block_count"], row["ore_t"], row["waste_t"], row["value_cents"], row["strip_ratio"]) == (
        0,
        0.0,
        0.0,
        0,
        None,
    )


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-17: the pushback rule by hand
# ----------------------------------------------------------------------------------------------------------------------


def _shells(cum_ore: list[float], cum_waste: list[float]) -> list[dict]:
    """Nested shells k = 0 .. n-1 where shell k holds the first k blocks (shell 0 is empty); lambda increases."""
    n = len(cum_ore)
    return [
        {"lambda": 0.1 * (k + 1), "mask": np.arange(n) < k, "ore_t": cum_ore[k], "waste_t": cum_waste[k]}
        for k in range(n)
    ]


@pytest.mark.req("FR-017-17")
def test_the_four_block_example_pushback_is_the_spec_record() -> None:
    tonnage, grade, arcs = _four_blocks()
    table = compute_shells(tonnage, grade, arcs, lambdas=[0.5, 1.0], **ECON)
    shells = [
        {"lambda": r["lambda"], "mask": m, "ore_t": r["ore_t"], "waste_t": r["waste_t"]}
        for r, m in zip(table.rows, table.masks, strict=True)
    ]
    (pb,) = build_pushbacks(shells, t_min_t=1000.0)
    expected = EXAMPLE["pushbacks"][0]
    assert pb["shell"] == expected["shell"]
    assert encode_bitset(pb["mask"]) == expected["blocks"]
    assert (pb["ore_t"], pb["waste_t"]) == (expected["ore_t"], expected["waste_t"])
    assert pb["strip_ratio_incremental"] == expected["strip_ratio_incremental"]
    assert pb["strip_ratio_cumulative"] == expected["strip_ratio_cumulative"]


@pytest.mark.req("FR-017-17")
def test_a_pushback_closes_when_the_incremental_ore_reaches_t_min_and_a_small_final_remainder_merges() -> None:
    # cumulative ore 0, 400, 900, 1500, 1700, 1800: closes at shell 3 (1,500 >= 1,000); the remainder 300 < 500 merges
    shells = _shells([0, 400, 900, 1500, 1700, 1800], [0, 100, 300, 500, 800, 900])
    (pb,) = build_pushbacks(shells, t_min_t=1000.0)
    assert pb["shell"] == 5
    assert (pb["ore_t"], pb["waste_t"]) == (1800.0, 900.0)
    assert pb["strip_ratio_incremental"] == pytest.approx(0.5)
    assert pb["strip_ratio_cumulative"] == pytest.approx(0.5)
    assert pb["mask"].tolist() == [True, True, True, True, True, False]  # shell 5 = the first five blocks


@pytest.mark.req("FR-017-17")
def test_two_pushbacks_with_incremental_and_cumulative_strip_ratios_by_hand() -> None:
    # cumulative ore 0, 400, 900, 1500, 2000, 2600; waste 0, 100, 300, 500, 900, 1300
    shells = _shells([0, 400, 900, 1500, 2000, 2600], [0, 100, 300, 500, 900, 1300])
    a, b = build_pushbacks(shells, t_min_t=1000.0)
    assert a["shell"] == 3
    assert (a["ore_t"], a["waste_t"]) == (1500.0, 500.0)
    assert b["shell"] == 5  # 2,000 - 1,500 = 500 < 1,000; 2,600 - 1,500 = 1,100 >= 1,000
    assert (b["ore_t"], b["waste_t"]) == (1100.0, 800.0)
    assert b["strip_ratio_incremental"] == pytest.approx(800.0 / 1100.0)
    assert b["strip_ratio_cumulative"] == pytest.approx(1300.0 / 2600.0)
    assert a["mask"].tolist() == [True, True, True, False, False, False]
    assert b["mask"].tolist() == [False, False, False, True, True, False]  # blocks 3 and 4 enter between shells 3 and 5


@pytest.mark.req("FR-017-17")
@pytest.mark.parametrize(("last_cum_ore", "n_pushbacks"), [(1799.0, 1), (2000.0, 2), (2100.0, 2), (1500.0, 1)])
def test_a_final_remainder_of_at_least_half_t_min_stays_its_own_pushback(last_cum_ore: float, n_pushbacks: int) -> None:
    # after the first pushback closes at 1,500: remainders 299 (< 500: merged), 500 (not below: own), 600 (own), 0
    # (none)
    shells = _shells([0, 400, 900, 1500, last_cum_ore], [0, 0, 0, 0, 0])
    assert len(build_pushbacks(shells, t_min_t=1000.0)) == n_pushbacks


@pytest.mark.req("FR-017-17")
def test_when_the_total_ore_is_below_t_min_everything_is_one_pushback() -> None:
    shells = _shells([0, 100, 250, 300], [0, 10, 20, 30])
    (pb,) = build_pushbacks(shells, t_min_t=1000.0)
    assert (pb["shell"], pb["ore_t"], pb["waste_t"]) == (3, 300.0, 30.0)


@pytest.mark.req("FR-017-17")
def test_repeated_and_empty_shells_are_skipped() -> None:
    base = _shells([0, 400, 900, 1500], [0, 0, 0, 0])
    repeated = [base[0], base[0], base[1], base[1], base[2], base[3], base[3]]
    pushbacks = build_pushbacks(repeated, t_min_t=1000.0)
    assert len(pushbacks) == 1
    assert pushbacks[0]["shell"] in (5, 6)  # the last distinct shell (either copy of the repeated one)


@pytest.mark.req("FR-017-17")
@pytest.mark.parametrize("bad", [0.0, -5.0, float("nan"), float("inf")])
def test_a_non_positive_or_non_finite_t_min_is_refused(bad: float) -> None:
    with pytest.raises(ValueError, match="t_min_t"):
        build_pushbacks(_shells([0, 400], [0, 0]), t_min_t=bad)


# ----------------------------------------------------------------------------------------------------------------------
# P-017-03 and P-017-09
# ----------------------------------------------------------------------------------------------------------------------


def _deposit(nx: int, ny: int, nz: int, seed: int):
    from pitstudio.planning.precedence import level_cone_precedence

    rng = np.random.default_rng(seed)
    n = nx * ny * nz
    arcs = level_cone_precedence(nx, ny, nz, dx=1.0, dy=1.0, dz=1.0, slope_deg=45.0)
    grade = rng.uniform(0.0, 0.05, n) * (rng.random(n) < 0.35)
    return np.full(n, 1000.0), grade, arcs


ECON_REAL = {"recovery": 0.85, "net_price": 8000.0, "processing_cost": 10.0, "mining_cost": 2.5}


@pytest.mark.req("P-017-03")
@settings(max_examples=200, deadline=None)
@given(dims=st.tuples(st.integers(2, 6), st.integers(2, 6), st.integers(2, 4)), seed=st.integers(0, 2**32 - 1))
def test_shells_are_nested_over_the_40_value_grid(dims, seed):
    tonnage, grade, arcs = _deposit(*dims, seed)
    masks = compute_shells(tonnage, grade, arcs, **ECON_REAL).masks
    assert len(masks) == 40
    for smaller, larger in itertools.pairwise(masks):
        assert not np.any(smaller & ~larger)  # pit(lambda_1) is a subset of pit(lambda_2)


@pytest.mark.req("P-017-09")
@settings(max_examples=200, deadline=None)
@given(
    dims=st.tuples(st.integers(2, 6), st.integers(2, 6), st.integers(2, 4)),
    seed=st.integers(0, 2**32 - 1),
    t_min=st.floats(1_000.0, 200_000.0),
)
def test_pushbacks_partition_the_final_pit_and_every_prefix_union_is_a_shell(dims, seed, t_min):
    tonnage, grade, arcs = _deposit(*dims, seed)
    table = compute_shells(tonnage, grade, arcs, **ECON_REAL)
    shells = [
        {"lambda": r["lambda"], "mask": m, "ore_t": r["ore_t"], "waste_t": r["waste_t"]}
        for r, m in zip(table.rows, table.masks, strict=True)
    ]
    pushbacks = build_pushbacks(shells, t_min_t=t_min)
    final = table.masks[-1]
    if not final.any():
        assert pushbacks == []
        return
    union = np.zeros_like(final)
    for pb in pushbacks:
        assert not np.any(union & pb["mask"])  # disjoint
        union |= pb["mask"]
        assert any(np.array_equal(union, m) for m in table.masks)  # the prefix union is one of the shells
        assert np.array_equal(union, table.masks[pb["shell"]])
    assert np.array_equal(union, final)  # the union is the pit
