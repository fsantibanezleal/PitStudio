# ruff: noqa: E501, PERF401
"""Counter-based variate source of the haulage adapter (FR-007-05 to FR-007-07, P-007-01 to P-007-03).

Every random number is a word of Philox4x64-10 (Random123). The key of a stream is (seed, FNV-1a-64 of the UTF-8 purpose
name), its counter is (block, 0, 0, 0) from block 0, and the four words of a block are consumed in order. Variates use only
integer operations, the IEEE-754 basic operations (+, -, *, /) and linear interpolation in quantile tables; the tables are
data, built offline from `statistics.NormalDist` and the stdlib `math` functions, and carried in the scenario bundle. The
TypeScript twin (`web/src/engines/random/`) reproduces every number bit for bit, which is why this module calls no
transcendental function when it draws.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import math
from collections.abc import Mapping
from functools import lru_cache
from statistics import NormalDist

import numpy as np

from .errors import InvalidScenario

M64 = (1 << 64) - 1
TABLE_BINS = 4096
PROFILES = ("engine", "exponential", "deterministic")
_M0, _M1 = 0xD2E7470EE14C6C93, 0xCA5A826395121157
_W0, _W1 = 0x9E3779B97F4A7C15, 0xBB67AE8584CAA73B
_FNV_OFFSET, _FNV_PRIME = 0xCBF29CE484222325, 0x100000001B3
_ND = NormalDist()


def _check_words(name: str, words: tuple, n: int) -> None:
    if not isinstance(words, tuple) or len(words) != n:
        raise TypeError(f"{name} must be a tuple of {n} words")
    for w in words:
        if not isinstance(w, int) or isinstance(w, bool) or not 0 <= w <= M64:
            raise ValueError(f"{name} words must be integers in [0, 2^64): {w!r}")


def philox4x64_10(counter: tuple[int, int, int, int], key: tuple[int, int]) -> tuple[int, int, int, int]:
    """One Philox4x64-10 block (Random123 `philox4x64_R(10)`)."""
    _check_words("counter", counter, 4)
    _check_words("key", key, 2)
    c0, c1, c2, c3 = counter
    k0, k1 = key
    for r in range(10):
        p0, p1 = _M0 * c0, _M1 * c2
        c0, c1, c2, c3 = (p1 >> 64) ^ c1 ^ k0, p1 & M64, (p0 >> 64) ^ c3 ^ k1, p0 & M64
        if r < 9:
            k0, k1 = (k0 + _W0) & M64, (k1 + _W1) & M64
    return c0, c1, c2, c3


def fnv1a_64(data: bytes | str) -> int:
    """FNV-1a, 64 bit, over the UTF-8 bytes of a str."""
    raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    h = _FNV_OFFSET
    for byte in raw:
        h = ((h ^ byte) * _FNV_PRIME) & M64
    return h


def stream_key(seed: int, purpose: str) -> tuple[int, int]:
    return (seed, fnv1a_64(purpose))


def u01_from_u64(x: int) -> float:
    """(x >> 11) * 2^-53 in [0, 1)."""
    return (x >> 11) * 2.0**-53


class PhiloxStream:
    """The words of one (seed, purpose) stream: counter (block, 0, 0, 0), four words per block in order."""

    def __init__(self, seed: int, purpose: str) -> None:
        self._key = stream_key(seed, purpose)
        self._block = 0
        self._buf: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._pos = 4

    @property
    def block_index(self) -> int:
        """Blocks started so far."""
        return self._block

    def next_u64(self) -> int:
        if self._pos == 4:
            self._buf = philox4x64_10((self._block, 0, 0, 0), self._key)
            self._block += 1
            self._pos = 0
        w = self._buf[self._pos]
        self._pos += 1
        return w

    def jump(self, block: int) -> None:
        """Continue from the start of block `block` (counter addressability)."""
        if not isinstance(block, int) or isinstance(block, bool) or not 0 <= block <= M64:
            raise ValueError(f"block must be an integer in [0, 2^64): {block!r}")
        self._block = block
        self._pos = 4


# ---------------------------------------------------------------------------------------------------------------------
# quantile tables
# ---------------------------------------------------------------------------------------------------------------------
def _validate_family(family: str, sigma: float | None) -> None:
    if family not in ("uniform", "normal", "exponential", "lognormal-unit-mean"):
        raise ValueError(f"unknown family {family!r}")
    if family == "lognormal-unit-mean":
        if sigma is None or isinstance(sigma, bool) or not isinstance(sigma, (int, float)) or not math.isfinite(sigma):
            raise ValueError("lognormal-unit-mean needs a finite sigma")
        if not 0.05 <= sigma <= 1.0:
            raise ValueError(f"sigma must be in [0.05, 1]: {sigma!r}")
    elif sigma is not None:
        raise ValueError(f"family {family!r} takes no sigma")


@lru_cache(maxsize=64)
def _build(family: str, sigma: float | None) -> np.ndarray:
    n, h = TABLE_BINS, 1.0 / TABLE_BINS
    probs = [i / n for i in range(1, n)]
    if family == "uniform":
        inner = list(probs)
        lo_mean, hi_mean = h / 2.0, 1.0 - h / 2.0
    elif family == "normal":
        inner = [_ND.inv_cdf(p) for p in probs]
        z = _ND.inv_cdf(h)
        lo_mean = -_ND.pdf(z) / h
        hi_mean = -lo_mean
    elif family == "exponential":
        inner = [-math.log1p(-p) for p in probs]
        lo_mean = (h + (1.0 - h) * math.log1p(-h)) / h
        hi_mean = 1.0 - math.log(h)
    else:
        mu = -(sigma * sigma) / 2.0
        inner = [math.exp(mu + sigma * _ND.inv_cdf(p)) for p in probs]
        z_lo, z_hi = _ND.inv_cdf(h), _ND.inv_cdf(1.0 - h)
        lo_mean = _ND.cdf(z_lo - sigma) / h
        hi_mean = _ND.cdf(-(z_hi - sigma)) / h
    k0 = 2.0 * lo_mean - inner[0]
    kn = 2.0 * hi_mean - inner[-1]
    if family in ("exponential", "lognormal-unit-mean"):
        k0 = max(k0, 0.0)  # the support starts at 0
    knots = np.array([k0, *inner, kn], dtype=np.float64)
    knots.setflags(write=False)
    return knots


def build_table(family: str, sigma: float | None = None) -> np.ndarray:
    """4097 knots of the standard-form quantile function (interior knots F^-1(i/4096); end bins at the conditional tail means)."""
    _validate_family(family, sigma)
    return _build(family, None if sigma is None else float(sigma))


def encode_table(knots, family: str, sigma: float | None = None) -> dict:
    raw = np.asarray(knots, dtype="<f8").tobytes()
    entry: dict = {"family": family}
    if sigma is not None:
        entry["sigma"] = sigma
    entry.update(
        {
            "bins": TABLE_BINS,
            "encoding": "float64-le-base64",
            "knots_f64le_b64": base64.b64encode(raw).decode("ascii"),
            "knots_sha256": hashlib.sha256(raw).hexdigest(),
        }
    )
    return entry


def decode_table(entry: dict) -> np.ndarray:
    """Knots of a bundle table entry, after checking bins, encoding, length, SHA-256, finiteness and monotonicity."""
    bad: list[tuple[str, object, str]] = []
    if not isinstance(entry, dict):
        raise InvalidScenario([("", entry, "a quantile table entry must be an object")])
    for key in ("bins", "encoding", "knots_f64le_b64", "knots_sha256"):
        if key not in entry:
            bad.append((f"/{key}", None, "required field is missing"))
    if bad:
        raise InvalidScenario(bad)
    if entry["bins"] != TABLE_BINS:
        bad.append(("/bins", entry["bins"], "a table has 4096 bins"))
    if entry["encoding"] != "float64-le-base64":
        bad.append(("/encoding", entry["encoding"], "encoding must be float64-le-base64"))
    if bad:
        raise InvalidScenario(bad)
    try:
        raw = base64.b64decode(entry["knots_f64le_b64"], validate=True)
    except binascii.Error, ValueError, TypeError:
        raise InvalidScenario([("/knots_f64le_b64", "<not base64>", "knots are not valid base64")]) from None
    if len(raw) != 8 * (TABLE_BINS + 1):
        raise InvalidScenario([("/knots_f64le_b64", f"{len(raw)} bytes", "a table has 4097 float64 knots")])
    if hashlib.sha256(raw).hexdigest() != entry["knots_sha256"]:
        raise InvalidScenario([("/knots_sha256", entry["knots_sha256"], "digest of the decoded knots differs")])
    knots = np.frombuffer(raw, dtype="<f8").astype(np.float64)
    if not np.all(np.isfinite(knots)):
        raise InvalidScenario([("/knots_f64le_b64", "<non-finite>", "knots must be finite")])
    if np.any(np.diff(knots) < 0.0):
        raise InvalidScenario([("/knots_f64le_b64", "<decreasing>", "knots must be non-decreasing")])
    return knots


def lerp_table(knots, word: int) -> float:
    """knots[i] + t * (knots[i+1] - knots[i]) with i the top 12 bits of the word and t the next 52 bits times 2^-52."""
    i = word >> 52
    t = (word & ((1 << 52) - 1)) * 2.0**-52
    a = float(knots[i])
    return a + t * (float(knots[i + 1]) - a)


# ---------------------------------------------------------------------------------------------------------------------
# the source
# ---------------------------------------------------------------------------------------------------------------------
def _finite(*vals: float) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vals)


class VariateSource:
    """Seeded variates by purpose. `tables` maps (family, sigma-or-None) to knots; None builds the standard tables on demand and
    an empty mapping means the bundle carries none (a request that needs a table raises InvalidScenario)."""

    def __init__(self, seed: int, *, profile: str = "engine", tables: Mapping | None = None) -> None:
        if not isinstance(profile, str) or profile not in PROFILES:
            raise InvalidScenario([("/variate_profile", profile, f"profile must be one of {', '.join(PROFILES)}")])
        self.seed = seed
        self.profile = profile
        self._tables = tables
        self._streams: dict[str, PhiloxStream] = {}

    def stream(self, purpose: str) -> PhiloxStream:
        s = self._streams.get(purpose)
        if s is None:
            s = self._streams[purpose] = PhiloxStream(self.seed, purpose)
        return s

    def _table(self, family: str, sigma: float | None):
        if self._tables is None:
            return build_table(family, sigma)
        knots = self._tables.get((family, sigma))
        if knots is None:
            raise InvalidScenario(
                [
                    (
                        "/quantile_tables",
                        (family, sigma),
                        "the bundle carries no quantile table for this family and sigma",
                    )
                ]
            )
        return knots

    def _word(self, purpose: str) -> int:
        return self.stream(purpose).next_u64()

    def uniform(self, purpose: str, lo: float, hi: float) -> float:
        if not _finite(lo, hi) or lo > hi:
            raise ValueError(f"uniform needs finite lo <= hi: {lo!r}, {hi!r}")
        if self.profile == "deterministic":
            return (lo + hi) / 2
        return lo + (hi - lo) * u01_from_u64(self._word(purpose))

    def normal(self, purpose: str, loc: float, scale: float) -> float:
        if not _finite(loc, scale) or scale <= 0.0:
            raise ValueError(f"normal needs a finite loc and a finite scale > 0: {loc!r}, {scale!r}")
        if self.profile == "deterministic" or (self.profile == "exponential" and purpose == "payload"):
            return loc
        return loc + scale * lerp_table(self._table("normal", None), self._word(purpose))

    def lognormal_unit_mean(self, purpose: str, sigma: float) -> float:
        if not _finite(sigma) or sigma < 0.0:
            raise ValueError(f"lognormal needs a finite sigma >= 0: {sigma!r}")
        if self.profile == "deterministic" or sigma == 0.0:
            return 1.0
        if self.profile == "exponential" and purpose in ("loadtime", "dumptime"):
            return lerp_table(self._table("exponential", None), self._word(purpose))
        return lerp_table(self._table("lognormal-unit-mean", float(sigma)), self._word(purpose))

    def exponential(self, purpose: str, scale: float) -> float:
        if not _finite(scale) or scale <= 0.0:
            raise ValueError(f"exponential needs a finite scale > 0: {scale!r}")
        if self.profile == "deterministic":
            return scale
        return scale * lerp_table(self._table("exponential", None), self._word(purpose))

    def integers(self, purpose: str, lo: int, hi: int) -> int:
        if not isinstance(lo, int) or not isinstance(hi, int) or lo >= hi:
            raise ValueError(f"integers needs integer lo < hi: {lo!r}, {hi!r}")
        if self.profile == "deterministic":
            return lo
        return lo + ((self._word(purpose) * (hi - lo)) >> 64)
