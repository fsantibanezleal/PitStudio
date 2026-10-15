# ruff: noqa: E501, PT018
"""T-007-010: Philox4x64-10 and FNV-1a-64 stream keys in Python; checked against the Random123 known-answer vectors, `numpy.random.Philox`
(counter offset by -1) and the variate-source invariants.

Requirements: FR-007-05, P-007-01, P-007-02.

Spec: specs/007-haulage-dispatch/spec.md FR-007-05 (every random number comes from Philox4x64-10 as defined by Random123; the key is (seed, FNV-1a-64 of the
UTF-8 stream purpose name); the counter is (block index, 0, 0, 0), starting at block 0 for each stream; the four 64-bit words of each block are consumed in
order), FR-007-06 (uniform from integer operations: (x >> 11) * 2^-53, plan.md "Variate source"), P-007-01 (known answers: block for counter 0 and key 0 is
`16554d9eca36314c db20fe9d672d0fdc d7e772cee186176b 7e68b68aec7ba23b`; for every word 2^64-1 it is `87b092c3013fe90b 438c3c67be8d0224 9cc7d7c69cd777b6
a09caebf594f0ba0`; for any key and counter the block equals `numpy.random.Philox` with the counter offset by -1; FNV-1a-64("") = `cbf29ce484222325`,
("a") = `af63dc4c8601ec8c`, ("foobar") = `85944171f73967e8`; 10^4 random (key, counter) pairs), P-007-02 (stream independence; counter addressability;
affine exactness for power-of-two scales, j in [-8, 8]).

Oracle: the published Random123 `kat_vectors` and FNV test vectors quoted in the spec; `numpy.random.Philox` called directly (reference implementation, with the
256-bit counter decremented by one because NumPy increments before each block); the definitions written out in the test.

Expected API (module `pitstudio_pipeline.haulage.variates`):
    philox4x64_10(counter: tuple[int, int, int, int], key: tuple[int, int]) -> tuple[int, int, int, int]     one block; words are 0 <= w < 2^64 else ValueError
    fnv1a_64(data: bytes | str) -> int                      str is encoded as UTF-8; offset basis 0xcbf29ce484222325, prime 0x100000001b3
    stream_key(seed: int, purpose: str) -> tuple[int, int]  (seed, fnv1a_64(purpose))
    u01_from_u64(x: int) -> float                           (x >> 11) * 2^-53, in [0, 1)
    PhiloxStream(seed: int, purpose: str)
        .block_index -> int          number of blocks consumed so far (0 for a fresh stream); the current block is counter (block_index, 0, 0, 0)
        .next_u64() -> int           the next word: the four words of block b in order, then block b + 1
        .jump(block: int) -> None    continue from the start of block `block` (counter addressability)
    VariateSource(seed: int, *, profile: str = "engine", tables=None)
        .stream(purpose) -> PhiloxStream                  the same object for the same purpose; each purpose has its own counter starting at block 0
        .uniform(purpose, lo, hi) -> float                lo + (hi - lo) * ((x >> 11) * 2^-53) with x = next_u64 of the purpose's stream
        .normal(purpose, loc, scale) -> float             loc + scale * (standard-normal quantile-table draw, test_t_007_011)
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit  # noqa: F401
from pitstudio_pipeline.haulage.variates import (
    PhiloxStream,
    VariateSource,
    fnv1a_64,
    philox4x64_10,
    stream_key,
    u01_from_u64,
)

M64 = (1 << 64) - 1


def numpy_block(key: tuple[int, int], counter: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Reference: numpy.random.Philox increments its counter before each block, so start one below (mod 2^256)."""
    v = sum(w << (64 * i) for i, w in enumerate(counter))
    v = (v - 1) % (1 << 256)
    start = np.array([(v >> (64 * i)) & M64 for i in range(4)], dtype=np.uint64)
    bg = np.random.Philox(key=np.array(key, dtype=np.uint64), counter=start)
    return tuple(int(x) for x in bg.random_raw(4))


def words(s: str) -> tuple[int, ...]:
    return tuple(int(w, 16) for w in s.split())


# ---------------------------------------------------------------------------------------------------------------------
# known answers (P-007-01)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("P-007-01")
@pytest.mark.req("FR-007-05")
def test_random123_known_answer_zero_counter_and_zero_key():
    assert philox4x64_10((0, 0, 0, 0), (0, 0)) == words(
        "16554d9eca36314c db20fe9d672d0fdc d7e772cee186176b 7e68b68aec7ba23b"
    )


@pytest.mark.req("P-007-01")
@pytest.mark.req("FR-007-05")
def test_random123_known_answer_all_ones():
    assert philox4x64_10((M64,) * 4, (M64, M64)) == words(
        "87b092c3013fe90b 438c3c67be8d0224 9cc7d7c69cd777b6 a09caebf594f0ba0"
    )


@pytest.mark.req("P-007-01")
@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"", 0xCBF29CE484222325),
        (b"a", 0xAF63DC4C8601EC8C),
        (b"foobar", 0x85944171F73967E8),
        ("", 0xCBF29CE484222325),
        ("foobar", 0x85944171F73967E8),
    ],
)
def test_fnv1a_64_published_vectors(data, expected):
    assert fnv1a_64(data) == expected


@pytest.mark.req("P-007-01")
def test_fnv1a_64_of_non_ascii_names_is_over_utf8_bytes_and_matches_the_definition():
    def ref(b: bytes) -> int:
        h = 0xCBF29CE484222325
        for byte in b:
            h = ((h ^ byte) * 0x100000001B3) & M64
        return h

    for name in ("loadtime", "dumptime", "payload", "init", "fail.truck", "policy", "café", "ランダム", "a\x00b"):
        assert fnv1a_64(name) == ref(name.encode("utf-8")) == fnv1a_64(name.encode("utf-8"))


@pytest.mark.req("FR-007-05")
@pytest.mark.parametrize("seed", [0, 1, 42, 2**63 - 1])
def test_stream_key_is_the_seed_and_the_hash_of_the_purpose(seed):
    assert stream_key(seed, "loadtime") == (seed, fnv1a_64(b"loadtime"))


# ---------------------------------------------------------------------------------------------------------------------
# against numpy.random.Philox
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("P-007-01")
def test_ten_thousand_random_key_counter_pairs_equal_numpy_philox():
    rng = random.Random(20261012)
    for _ in range(10_000):
        key = (rng.getrandbits(64), rng.getrandbits(64))
        ctr = tuple(rng.getrandbits(64) for _ in range(4))
        assert philox4x64_10(ctr, key) == numpy_block(key, ctr)


@pytest.mark.req("P-007-01")
@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    st.tuples(*[st.sampled_from([0, 1, M64, M64 - 1, 1 << 63, (1 << 32) - 1]) | st.integers(0, M64)] * 2),
    st.tuples(*[st.sampled_from([0, 1, M64, M64 - 1, 1 << 63]) | st.integers(0, M64)] * 4),
)
def test_edge_counters_and_keys_equal_numpy_philox(key, ctr):
    assert philox4x64_10(ctr, key) == numpy_block(key, ctr)


@pytest.mark.req("P-007-01")
@pytest.mark.parametrize("bad", [(-1, 0, 0, 0), (0, 0, 0, 1 << 64), (0, 0, 0)])
def test_counter_words_outside_64_bits_or_a_wrong_length_are_rejected(bad):
    with pytest.raises((ValueError, TypeError)):
        philox4x64_10(bad, (0, 0))


@pytest.mark.req("P-007-01")
@pytest.mark.parametrize("bad", [(-1, 0), (0, 1 << 64), (0,), (0, 0, 0)])
def test_key_words_outside_64_bits_or_a_wrong_length_are_rejected(bad):
    with pytest.raises((ValueError, TypeError)):
        philox4x64_10((0, 0, 0, 0), bad)


# ---------------------------------------------------------------------------------------------------------------------
# the stream: counter (block, 0, 0, 0), words in order (FR-007-05)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-05")
@pytest.mark.parametrize("seed", [0, 7, 2**62 + 12345])
def test_a_stream_yields_the_words_of_blocks_0_1_2_in_order(seed):
    key = stream_key(seed, "loadtime")
    expected = [w for b in range(3) for w in numpy_block(key, (b, 0, 0, 0))]  # numpy is the reference for each block
    s = PhiloxStream(seed, "loadtime")
    assert s.block_index == 0
    got = [s.next_u64() for _ in range(12)]
    assert got == expected
    assert s.block_index == 3


@pytest.mark.req("FR-007-05")
def test_the_block_index_counts_started_blocks():
    s = PhiloxStream(1, "payload")
    s.next_u64()
    assert s.block_index == 1  # one word consumed: block 0 started
    for _ in range(3):
        s.next_u64()
    assert s.block_index == 1  # the fourth word of block 0
    s.next_u64()
    assert s.block_index == 2


@pytest.mark.req("P-007-02")
@settings(max_examples=100, deadline=None)
@given(
    st.integers(0, 2**63 - 1),
    st.sampled_from(["loadtime", "dumptime", "payload", "init", "policy", "fail.truck"]),
    st.integers(0, 40),
)
def test_jumping_to_block_k_equals_k_sequential_blocks(seed, purpose, k):
    a = PhiloxStream(seed, purpose)
    for _ in range(4 * k):
        a.next_u64()
    b = PhiloxStream(seed, purpose)
    b.jump(k)
    assert [a.next_u64() for _ in range(9)] == [b.next_u64() for _ in range(9)]
    key = stream_key(seed, purpose)
    c = PhiloxStream(seed, purpose)
    c.jump(k)
    assert tuple(c.next_u64() for _ in range(4)) == numpy_block(key, (k, 0, 0, 0))


@pytest.mark.req("P-007-02")
@settings(max_examples=100, deadline=None)
@given(st.integers(0, 2**63 - 1), st.integers(1, 30), st.lists(st.sampled_from(["A", "B"]), min_size=1, max_size=60))
def test_the_nth_draw_of_one_stream_does_not_depend_on_other_streams(seed, n, order):
    alone = VariateSource(seed)
    ref = [alone.uniform("loadtime", 0.0, 1.0) for _ in range(n)]
    mixed = VariateSource(seed)
    got, i = [], 0
    for who in order:
        if who == "A" and i < n:
            got.append(mixed.uniform("loadtime", 0.0, 1.0))
            i += 1
        else:
            mixed.uniform("payload", 0.0, 1.0)  # draws from another stream in between
    while i < n:
        got.append(mixed.uniform("loadtime", 0.0, 1.0))
        i += 1
    assert got == ref


@pytest.mark.req("FR-007-05")
def test_two_sources_with_the_same_seed_agree_and_other_seeds_differ():
    a = [VariateSource(5).uniform("init", 0, 1) for _ in range(1)]
    b = [VariateSource(5).uniform("init", 0, 1) for _ in range(1)]
    c = [VariateSource(6).uniform("init", 0, 1) for _ in range(1)]
    assert a == b and a != c


# ---------------------------------------------------------------------------------------------------------------------
# uniform from integer operations, and affine exactness (FR-007-06, P-007-02)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-06")
@pytest.mark.parametrize("seed", [0, 3, 99])
def test_uniform_is_the_top_53_bits_times_2_to_the_minus_53(seed):
    key = stream_key(seed, "init")
    block = numpy_block(key, (0, 0, 0, 0))
    src = VariateSource(seed)
    for x in block:  # four consecutive draws consume the four words of block 0
        assert src.uniform("init", 0.0, 1.0) == (x >> 11) * 2.0**-53


@pytest.mark.req("FR-007-06")
def test_uniform_maps_the_extreme_words_into_the_half_open_unit_interval():
    assert u01_from_u64(M64) == (2**53 - 1) * 2.0**-53 < 1.0
    assert u01_from_u64(0) == 0.0
    assert u01_from_u64(2**11 - 1) == 0.0  # the low 11 bits are dropped
    assert u01_from_u64(2**11) == 2.0**-53
    assert u01_from_u64(1 << 63) == 0.5


def one_ulp(x: float) -> float:
    return math.ulp(x)


@pytest.mark.req("P-007-02")
@settings(max_examples=150, deadline=None)
@given(
    st.integers(0, 2**63 - 1),
    st.sampled_from(["loadtime", "payload", "init"]),
    st.integers(-8, 8),
    st.sampled_from([0.0, 1.0, -2.0, 0.5, 100.0, 1024.0]),
)
def test_uniform_scales_affinely_for_power_of_two_widths(seed, purpose, j, lo):
    base = VariateSource(seed).uniform(purpose, 0.0, 1.0)
    scaled = VariateSource(seed).uniform(purpose, lo, lo + 2.0**j)
    # exact for lo = 0 (multiplying by 2^j is exact); within one ulp of the larger operand otherwise (the addition of `lo` rounds)
    if lo == 0.0:
        assert scaled - lo == 2.0**j * base
    else:
        assert abs((scaled - lo) - 2.0**j * base) <= one_ulp(max(abs(scaled), abs(lo)))


@pytest.mark.req("P-007-02")
@settings(max_examples=150, deadline=None)
@given(st.integers(0, 2**63 - 1), st.integers(-8, 8), st.sampled_from([0.0, 1.0, -2.0, 0.5, 100.0]))
def test_normal_scales_affinely_for_power_of_two_scales(seed, j, loc):
    z = VariateSource(seed).normal("loadtime", 0.0, 1.0)
    x = VariateSource(seed).normal("loadtime", loc, 2.0**j)
    if loc == 0.0:
        assert x == 2.0**j * z
    else:
        assert abs((x - loc) - 2.0**j * z) <= one_ulp(max(abs(x), abs(loc)))
