"""Beam hash: MurmurHash3_x86_32 of (frame, beam, run seed), the uniform number of the dust keep law (FR-013-14).

The key is the 12-byte little-endian concatenation of three unsigned 32-bit integers; `u = h / 2^32` lies in [0, 1).
Standard library and NumPy only, so that the TypeScript port in the web slider reproduces it bit for bit.
"""

from __future__ import annotations

import struct
from typing import Any

import numpy as np

_C1, _C2, _MASK = 0xCC9E2D51, 0x1B873593, 0xFFFFFFFF
_LIMIT = 2**32


def _u32(value: Any, name: str) -> int:
    """`value` as an integer in [0, 2^32), or ValueError (out of range, not integral) or TypeError (not a number)."""
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise TypeError(f"{name} must be an unsigned 32-bit integer, got {type(value).__name__}")
    number = float(value) if isinstance(value, (float, np.floating)) else int(value)
    if isinstance(number, float):
        if number != number or number in (float("inf"), float("-inf")) or number != int(number):
            raise ValueError(f"{name} must be an integer, got {value!r}")
        number = int(number)
    if not 0 <= number < _LIMIT:
        raise ValueError(f"{name} must satisfy 0 <= {name} < 2^32, got {value!r}")
    return number


def murmur3_x86_32(data: bytes, seed: int = 0) -> int:
    """MurmurHash3_x86_32 (public-domain reference algorithm), unsigned 32-bit result."""
    h = seed & _MASK
    n = len(data)
    for i in range(n // 4):
        k = struct.unpack_from("<I", data, 4 * i)[0]
        k = (k * _C1) & _MASK
        k = ((k << 15) | (k >> 17)) & _MASK
        k = (k * _C2) & _MASK
        h ^= k
        h = ((h << 13) | (h >> 19)) & _MASK
        h = (h * 5 + 0xE6546B64) & _MASK
    tail = data[4 * (n // 4) :]
    k = 0
    if len(tail) >= 3:
        k ^= tail[2] << 16
    if len(tail) >= 2:
        k ^= tail[1] << 8
    if len(tail) >= 1:
        k ^= tail[0]
        k = (k * _C1) & _MASK
        k = ((k << 15) | (k >> 17)) & _MASK
        k = (k * _C2) & _MASK
        h ^= k
    h ^= n
    return _fmix(h)


def _fmix(h: int) -> int:
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & _MASK
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & _MASK
    h ^= h >> 16
    return h


def beam_hash(frame: int, beam: int, seed: int) -> int:
    """The uint32 hash of the key (frame, beam, seed)."""
    return murmur3_x86_32(struct.pack("<III", _u32(frame, "frame"), _u32(beam, "beam"), _u32(seed, "seed")), 0)


def beam_value(frame: int, beam: int, seed: int) -> float:
    """`beam_hash / 2^32`, in [0, 1)."""
    return beam_hash(frame, beam, seed) / 2.0**32


def _rotl(x: np.ndarray, r: int) -> np.ndarray:
    return (x << np.uint32(r)) | (x >> np.uint32(32 - r))


def _round_key(k: np.ndarray) -> np.ndarray:
    return _rotl(k * np.uint32(_C1), 15) * np.uint32(_C2)


def _mix_block(h: np.ndarray, k: np.ndarray) -> np.ndarray:
    h = h ^ _round_key(k)
    return _rotl(h, 13) * np.uint32(5) + np.uint32(0xE6546B64)


def beam_hash_array(frame: int, beams: np.ndarray, seed: int) -> np.ndarray:
    """`beam_hash` over an array of beam indices (uint32), vectorised; identical to the scalar values."""
    frame_i, seed_i = _u32(frame, "frame"), _u32(seed, "seed")
    raw = np.asarray(beams)
    if raw.dtype.kind == "f" and (not np.all(np.isfinite(raw)) or np.any(raw != np.floor(raw))):
        raise ValueError("beams must be integers")
    if raw.dtype.kind not in "iuf" or np.any(raw < 0) or np.any(raw >= _LIMIT):
        raise ValueError("beams must satisfy 0 <= beam < 2^32")
    b = raw.astype(np.uint32)
    with np.errstate(over="ignore"):
        h = np.zeros(b.shape, dtype=np.uint32)
        h = _mix_block(h, np.full(b.shape, frame_i, dtype=np.uint32))
        h = _mix_block(h, b)
        h = _mix_block(h, np.full(b.shape, seed_i, dtype=np.uint32))
        h = h ^ np.uint32(12)
        h = h ^ (h >> np.uint32(16))
        h = h * np.uint32(0x85EBCA6B)
        h = h ^ (h >> np.uint32(13))
        h = h * np.uint32(0xC2B2AE35)
        h = h ^ (h >> np.uint32(16))
    return h


def beam_value_array(frame: int, beams: np.ndarray, seed: int) -> np.ndarray:
    """`beam_value` over an array of beam indices, float64."""
    return beam_hash_array(frame, beams, seed).astype(np.float64) / 2.0**32
