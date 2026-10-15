# ruff: noqa: E501, PT018
"""T-013-022: beam hash against the MurmurHash3 reference; uniformity.

Requirements: FR-013-14, P-013-12.

Oracle: the published MurmurHash3_x86_32 test vectors (`sensor_kit.MURMUR_VECTORS`: the SMHasher verification and the
`mmh3`/`murmur3` suite vectors) and a reference implementation of the published algorithm (`sensor_kit.murmur3_x86_32`,
validated against those vectors); the key of FR-013-14 is the 12-byte little-endian (frame, beam, run seed) of three unsigned
32-bit integers, u = h / 2^32; known answers for ten keys were computed with that reference (the same vectors are used by the
TypeScript port, test T-013-031); uniformity by a Kolmogorov-Smirnov test written from the asymptotic Kolmogorov series
(`sensor_kit.ks_pvalue`; p > 0.001 over 10^6 consecutive beams).

Expected API (package `pitstudio.sensors.beamhash`, root environment; standard library and NumPy only):
- `beamhash.murmur3_x86_32(data: bytes, seed: int = 0) -> int`: MurmurHash3_x86_32, unsigned 32-bit.
- `beamhash.beam_hash(frame, beam, seed) -> int` (uint32): `murmur3_x86_32` (seed 0) of `struct.pack("<III", frame, beam, seed)`.
- `beamhash.beam_value(frame, beam, seed) -> float`: `beam_hash / 2**32`, in [0, 1).
- `beamhash.beam_hash_array(frame, beams, seed) -> uint32 array` and `beamhash.beam_value_array(frame, beams, seed) -> float64
  array`: the vectorised forms over a `beams` array (values identical to the scalar ones).
- A frame, beam or seed outside 0 <= x < 2^32, or not an integer, raises `ValueError` (or `TypeError` for a non-number).
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import sensor_kit as kit  # noqa: E402
from pitstudio.sensors import beamhash  # noqa: E402

# (frame, beam, seed, hash, u), computed with the reference implementation; shared with the TypeScript tests.
KNOWN = [
    (0, 0, 0, 0xD941144B, 0.8486492808442563),
    (1, 0, 0, 0xD4657DC3, 0.8296736336778849),
    (0, 1, 0, 0x6F08BAED, 0.43372696195729077),
    (0, 0, 1, 0x5FBBC52A, 0.3739588954485953),
    (1, 2, 3, 0xE9D78AD6, 0.9134451649151742),
    (3, 17, 20261007, 0x641A6166, 0.39102753391489387),
    (7, 199999, 20261007, 0x2A3A2FAA, 0.16495035076513886),
    (100000, 200000, 4294967295, 0x16F9EF31, 0.08975119539536536),
    (4294967295, 4294967295, 4294967295, 0xA9ED186D, 0.6637740388978273),
    (12345, 678, 90, 0xBA88CA14, 0.7286497401073575),
]
U32 = st.integers(0, 2**32 - 1)


@pytest.mark.req("FR-013-14")
@pytest.mark.parametrize(("seed", "data", "expected"), kit.MURMUR_VECTORS)
def test_murmur3_matches_the_published_vectors(seed: int, data: bytes, expected: int) -> None:
    assert beamhash.murmur3_x86_32(data, seed) == expected
    assert kit.murmur3_x86_32(data, seed) == expected  # the reference used below is itself validated here


@pytest.mark.req("FR-013-14")
@pytest.mark.parametrize(("frame", "beam", "seed", "h", "u"), KNOWN)
def test_known_answers_of_the_beam_hash(frame: int, beam: int, seed: int, h: int, u: float) -> None:
    assert beamhash.beam_hash(frame, beam, seed) == h == kit.beam_hash_ref(frame, beam, seed)
    assert beamhash.beam_value(frame, beam, seed) == u
    assert kit.murmur3_x86_32(struct.pack("<III", frame, beam, seed), 0) == h  # 12-byte little-endian key


@pytest.mark.req("FR-013-14")
@given(frame=U32, beam=U32, seed=U32)
def test_beam_hash_equals_the_reference_for_every_key(frame: int, beam: int, seed: int) -> None:
    h = beamhash.beam_hash(frame, beam, seed)
    assert h == kit.beam_hash_ref(frame, beam, seed)
    u = beamhash.beam_value(frame, beam, seed)
    assert u == h / 2.0**32 and 0.0 <= u < 1.0


@pytest.mark.req("FR-013-14")
def test_extreme_keys_stay_in_the_half_open_unit_interval() -> None:
    for key in ((0, 0, 0), (2**32 - 1, 2**32 - 1, 2**32 - 1), (0, 2**32 - 1, 0), (2**32 - 1, 0, 2**32 - 1)):
        assert 0.0 <= beamhash.beam_value(*key) < 1.0


@pytest.mark.req("FR-013-14")
def test_array_forms_agree_with_the_scalar_forms_bit_for_bit() -> None:
    rng = np.random.default_rng(3)
    beams = rng.integers(0, 2**32, 5000, dtype=np.uint64).astype(np.uint32)
    for frame, seed in ((0, 0), (17, 20261007), (2**32 - 1, 2**32 - 1)):
        h = beamhash.beam_hash_array(frame, beams, seed)
        u = beamhash.beam_value_array(frame, beams, seed)
        assert h.dtype == np.uint32 and u.dtype == np.float64
        assert h.tolist() == [kit.beam_hash_ref(frame, int(b), seed) for b in beams]
        assert u.tolist() == [kit.beam_u_ref(frame, int(b), seed) for b in beams]


@pytest.mark.req("P-013-12")
@pytest.mark.parametrize(("frame", "seed"), [(0, 0), (3, 20261007), (99_999, 2**32 - 1)])
def test_a_million_consecutive_beams_are_uniform_by_kolmogorov_smirnov(frame: int, seed: int) -> None:
    u = beamhash.beam_value_array(frame, np.arange(10**6, dtype=np.uint32), seed)
    assert u.min() >= 0.0 and u.max() < 1.0
    assert kit.ks_pvalue(u) > 0.001


@pytest.mark.req("P-013-12")
def test_the_value_depends_on_every_part_of_the_key() -> None:
    beams = np.arange(20_000, dtype=np.uint32)
    base = beamhash.beam_value_array(5, beams, 11)
    for other in (
        beamhash.beam_value_array(6, beams, 11),
        beamhash.beam_value_array(5, beams, 12),
        beamhash.beam_value_array(5, beams + np.uint32(1), 11),
    ):
        assert np.mean(other != base) > 0.999
    assert np.array_equal(base, beamhash.beam_value_array(5, beams, 11))  # and it is a pure function of the key


@pytest.mark.req("FR-013-14")
@pytest.mark.parametrize("bad", [-1, 2**32, 2**64, 1.5, float("nan"), float("inf")])
def test_keys_outside_the_unsigned_32_bit_integers_are_rejected(bad: float) -> None:
    for position in range(3):
        key = [1, 2, 3]
        key[position] = bad
        with pytest.raises((ValueError, TypeError, OverflowError)):
            beamhash.beam_hash(*key)
    with pytest.raises((ValueError, TypeError, OverflowError)):
        beamhash.beam_value_array(0, np.array([bad]), 0)


@pytest.mark.req("FR-013-14")
@pytest.mark.parametrize("bad", ["1", None, b"1", [1]])
def test_non_numbers_are_a_type_error(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        beamhash.beam_hash(bad, 0, 0)
