# ruff: noqa: E501, PT018, RUF046
"""Shared test fixtures and independent oracles for the sensor-lane red tests (spec 013).

Test-only helper, locked together with the tests that use it. Third-party libraries other than numpy (pyarrow, zarr,
referencing, jsonschema) are imported inside the functions that need them.

Nothing here calls the code under test. Expected values come from the spec text (the dust rule of FR-013-11 to FR-013-14),
published test vectors (MurmurHash3), closed forms, or the contract example corpus.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "specs" / "013-sensors"
EXAMPLES = SPEC / "contracts" / "examples"

# Detection-rule constants of spec 013 section 3.2 (Phillips, Guenther and McAree 2017, abstract, spec section 7 A1).
TAU_ON = 0.3216  # T1 = 0.725
TAU_FLOOR = {"retro": 3.9120, "diffuse": 2.8134}  # -ln 0.02 and -ln 0.06
EDGE_BETA = 1.0e-6  # m^-1: the dust cloud starts at the first sample above this extinction
OVRTX_VERSIONS = {"ovrtx": "0.5.0.377615", "ovstage": "0.2.0.377349"}


# ----------------------------------------------------------------------------------------------------- recipes, schemas
def recipe(name: str = "valid") -> dict[str, Any]:
    """A deep copy of a valid contract example recipe: valid (S1), valid-s2, valid-s3, valid-s4a, valid-rain."""
    return copy.deepcopy(json.loads((EXAMPLES / f"sensor-recipe.{name}.json").read_text(encoding="utf-8")))


def hostile_recipes() -> list[dict[str, Any]]:
    """The hostile recipe corpus: [{file, class, rule, pointer, keyword, recipe}] from the example index."""
    index = json.loads((EXAMPLES / "index.json").read_text(encoding="utf-8"))["examples"]
    out = []
    for ex in index:
        if ex["schema"] == "sensor-recipe.schema.json" and not ex["valid"]:
            ex = dict(ex)
            ex["recipe"] = json.loads((EXAMPLES / ex["file"]).read_text(encoding="utf-8"))
            out.append(ex)
    return out


def validator(schema_name: str):
    import jsonschema
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    resources = []
    for p in (SPEC / "contracts").glob("*.schema.json"):
        doc = json.loads(p.read_text(encoding="utf-8"))
        resources.append((doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012)))
    schema = json.loads((SPEC / "contracts" / schema_name).read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema, registry=Registry().with_resources(resources))


def without_fixture_flag(node: Any) -> Any:
    """A copy of `node` without any boolean `fixture` member (the draft schemas have no such member; FR-013-43 adds it)."""
    if isinstance(node, dict):
        return {k: without_fixture_flag(v) for k, v in node.items() if not (k == "fixture" and isinstance(v, bool))}
    if isinstance(node, list):
        return [without_fixture_flag(v) for v in node]
    return node


def schema_errors(schema_name: str, instance: Any) -> list[str]:
    instance = without_fixture_flag(instance)
    v = validator(schema_name)
    return sorted(f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in v.iter_errors(instance))


def def_errors(schema_name: str, def_name: str, instance: Any) -> list[str]:
    """Errors of `instance` against `$defs/<def_name>` of a draft schema of spec 013 (all sibling schemas resolvable)."""
    import jsonschema
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    resources, base = [], None
    for p in (SPEC / "contracts").glob("*.schema.json"):
        doc = json.loads(p.read_text(encoding="utf-8"))
        resources.append((doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012)))
        if p.name == schema_name:
            base = doc["$id"]
    v = jsonschema.Draft202012Validator(
        {"$ref": f"{base}#/$defs/{def_name}"}, registry=Registry().with_resources(resources)
    )
    return sorted(f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in v.iter_errors(instance))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lidar_configs(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """The probed-configuration key of every lidar of a recipe (scan type, fans, mount rotation)."""
    return [
        {
            "scan_type": s["scan_type"],
            "elevation_fan_deg": s["elevation_fan_deg"],
            "azimuth_fan_deg": s["azimuth_fan_deg"],
            "mount_rotation_deg": s["mount_rotation_deg"],
        }
        for s in rec["sensors"]
        if s["kind"] == "lidar"
    ]


def envelope_for(
    rec: dict[str, Any], *, status: str = "pass", versions: dict[str, str] | None = None
) -> dict[str, Any]:
    """A DC-013-02 envelope listing every lidar configuration of `rec` with `status`."""
    return {
        "schema_version": "1.0",
        "generated": "2026-10-07T10:15:00Z",
        "versions": dict(versions or OVRTX_VERSIONS),
        "probe_scene": {"cube_edge_m": 2, "cube_range_m": 20},
        "configurations": [
            {**c, "status": status, "valid_points": 1000 if status == "pass" else 0} for c in lidar_configs(rec)
        ],
    }


# ------------------------------------------------------------------------------------------------- backend frame outputs
def lidar_output(
    n: int = 300,
    n_valid: int = 240,
    seed: int = 0,
    *,
    beams_emitted: int | None = None,
    rng_range: tuple[float, float] = (5.0, 80.0),
) -> dict[str, Any]:
    """One clean lidar frame as a backend returns it: `n` slots, the first `n_valid` flagged valid (0x40)."""
    rng = np.random.default_rng(seed)
    r = rng.uniform(*rng_range, n).astype(np.float32)
    az = rng.uniform(-math.pi, math.pi, n)
    el = rng.uniform(-0.3, 0.3, n)
    flags = np.zeros(n, dtype=np.uint8)
    flags[:n_valid] = 0x40
    out = {
        "kind": "lidar",
        "beams_emitted": n if beams_emitted is None else beams_emitted,
        "valid_count": int(n_valid),
        "x": (r * np.cos(el) * np.cos(az)).astype(np.float32),
        "y": (r * np.cos(el) * np.sin(az)).astype(np.float32),
        "z": (r * np.sin(el)).astype(np.float32),
        "range_m": r,
        "intensity": rng.uniform(0.0, 1.0, n).astype(np.float32),
        "flags": flags,
        "material_class": (rng.uniform(size=n) < 0.2).astype(np.uint8),  # 0 diffuse, 1 retro
        "object_id": rng.integers(0, 6, n).astype(np.uint32),
        "beam": np.arange(n, dtype=np.uint32),
        "echo": np.zeros(n, dtype=np.uint8),
    }
    return out


def camera_output(
    width: int = 64,
    height: int = 48,
    seed: int = 0,
    outputs: tuple[str, ...] = ("HdrColor", "DistanceToCameraSD", "SemanticSegmentation", "LdrColor"),
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    out: dict[str, Any] = {"kind": "camera"}
    if "HdrColor" in outputs:
        out["hdr"] = rng.uniform(0, 4, (height, width, 3)).astype(np.float16)
    if "DistanceToCameraSD" in outputs:
        out["distance"] = rng.uniform(5, 100, (height, width)).astype(np.float32)
    if "SemanticSegmentation" in outputs:
        out["semantic"] = rng.integers(1, 4, (height, width)).astype(np.uint32)
    if "LdrColor" in outputs:
        out["ldr"] = rng.integers(0, 256, (height, width, 3)).astype(np.uint8)
    return out


def radar_output(n: int = 40, seed: int = 0, native_sign: str = "approaching-positive") -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    return {
        "kind": "radar",
        "x": rng.uniform(15, 80, n).astype(np.float32),
        "y": rng.uniform(-3, 3, n).astype(np.float32),
        "z": rng.uniform(0, 2, n).astype(np.float32),
        "rcs_dbsm": rng.uniform(-10, 20, n).astype(np.float32),
        "radial_velocity_native": rng.uniform(-15, 15, n).astype(np.float32),
        "native_sign": native_sign,
        "object_id": rng.integers(0, 4, n).astype(np.uint32),
    }


def write_poses(path: Path, n: int) -> Path:
    """A pose trace of `n` frames: Parquet with `frame`, `t_s` and `world_from_platform` (16 floats, row-major)."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    eye = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
    table = pa.table(
        {
            "frame": pa.array(range(n), pa.uint32()),
            "t_s": pa.array([0.1 * i for i in range(n)], pa.float64()),
            "world_from_platform": pa.array(
                [[*eye[:12], 0.5 * i, 0.0, 0.0, 1.0] for i in range(n)], pa.list_(pa.float64())
            ),
        }
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)
    return Path(path)


def png_decode(path: Path) -> np.ndarray:
    """Decode an 8-bit non-interlaced RGB or grey PNG with the standard library only (all five row filters, CRC checked)."""
    import zlib

    data = Path(path).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, ihdr = 8, b"", None
    while pos < len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        tag = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack_from(">I", data, pos + 8 + length)
        assert crc == zlib.crc32(tag + body) & 0xFFFFFFFF, f"bad CRC in chunk {tag!r}"
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + length
    assert ihdr is not None
    w, h, depth, ctype, _, _, interlace = ihdr
    assert depth == 8 and interlace == 0 and ctype in (0, 2), ihdr
    bpp = 3 if ctype == 2 else 1
    raw = zlib.decompress(idat)
    stride = w * bpp
    assert len(raw) == h * (stride + 1)
    out = np.zeros((h, stride), dtype=np.uint8)
    prev = np.zeros(stride, dtype=np.int32)
    for y in range(h):
        ft = raw[y * (stride + 1)]
        line = np.frombuffer(raw, dtype=np.uint8, count=stride, offset=y * (stride + 1) + 1).astype(np.int32)
        cur = np.zeros(stride, dtype=np.int32)
        if ft == 0:
            cur = line
        elif ft == 2:
            cur = (line + prev) & 255
        else:
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                if ft == 1:
                    pred = a
                elif ft == 3:
                    pred = (a + b) >> 1
                else:  # Paeth
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                cur[i] = (line[i] + pred) & 255
        out[y] = cur
        prev = cur
    return out.reshape(h, w, bpp) if bpp == 3 else out.reshape(h, w)


# ------------------------------------------------------------------------------ MurmurHash3 reference (published vectors)
def murmur3_x86_32(data: bytes, seed: int = 0) -> int:
    """MurmurHash3_x86_32 (Austin Appleby, public domain reference algorithm), unsigned 32-bit result."""
    c1, c2, mask = 0xCC9E2D51, 0x1B873593, 0xFFFFFFFF
    h = seed & mask
    n = len(data)
    for i in range(n // 4):
        k = struct.unpack_from("<I", data, 4 * i)[0]
        k = (k * c1) & mask
        k = ((k << 15) | (k >> 17)) & mask
        k = (k * c2) & mask
        h ^= k
        h = ((h << 13) | (h >> 19)) & mask
        h = (h * 5 + 0xE6546B64) & mask
    tail = data[4 * (n // 4) :]
    k = 0
    if len(tail) >= 3:
        k ^= tail[2] << 16
    if len(tail) >= 2:
        k ^= tail[1] << 8
    if len(tail) >= 1:
        k ^= tail[0]
        k = (k * c1) & mask
        k = ((k << 15) | (k >> 17)) & mask
        k = (k * c2) & mask
        h ^= k
    h ^= n
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & mask
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & mask
    h ^= h >> 16
    return h


# Published test vectors (seed, input, unsigned result): the empty-string vectors of the SMHasher verification suite,
# the Hello/quick-brown-fox vectors used by the Python `mmh3` and Rust `murmur3` test suites, and 1-4 byte tails.
MURMUR_VECTORS = [
    (0, b"", 0x00000000),
    (1, b"", 0x514E28B7),
    (0xFFFFFFFF, b"", 0x81F16F39),
    (0, b"test", 0xBA6BD213),
    (0, b"foo", 0xF6A5C420),
    (0, b"Hello, world!", 0xC0363E43),
    (0, b"The quick brown fox jumps over the lazy dog", 0x2E4FF723),
    (0, b"abc", 0xB3DD93FA),
    (0x9747B28C, b"a", 0x7FA09EA6),
    (0x9747B28C, b"aa", 0x5D211726),
    (0x9747B28C, b"aaa", 0x283E0130),
    (0x9747B28C, b"aaaa", 0x5A97808A),
    (0x9747B28C, b"Hello, world!", 0x24884CBA),
    (0, b"\x00\x00\x00\x00", 0x2362F9DE),
    (0, b"\xff\xff\xff\xff", 0x76293B50),
]


def beam_hash_ref(frame: int, beam: int, seed: int) -> int:
    """h = MurmurHash3_x86_32 (seed 0) of the 12-byte little-endian key (frame index, beam index, run seed), FR-013-14."""
    return murmur3_x86_32(struct.pack("<III", frame, beam, seed), 0)


def beam_u_ref(frame: int, beam: int, seed: int) -> float:
    return beam_hash_ref(frame, beam, seed) / 2.0**32


# ------------------------------------------------------------------------------------------------ dust rule reference
def tau_ref(beta_row: np.ndarray, spacing: float, r: float) -> float:
    """Optical depth to range r: integral of the piecewise-linear extinction through the samples (exact trapezoids)."""
    b = np.asarray(beta_row, dtype=np.float64)
    s = np.arange(len(b)) * spacing
    k = int(np.searchsorted(s, r, side="right")) - 1  # last sample at or before r
    total = float(np.sum((b[:k] + b[1 : k + 1]) * 0.5 * spacing)) if k > 0 else 0.0
    if s[k] < r:
        frac = (r - s[k]) / spacing
        b_r = b[k] + (b[k + 1] - b[k]) * frac
        total += 0.5 * (b[k] + b_r) * (r - s[k])
    return total


def edge_ref(beta_row: np.ndarray, spacing: float, r: float) -> float:
    """Leading edge of the dust cloud: the smallest sample range s < r with beta(s) > 1e-6 (NaN if none)."""
    s = np.arange(len(beta_row)) * spacing
    idx = np.nonzero((np.asarray(beta_row) > EDGE_BETA) & (s < r))[0]
    return float(s[idx[0]]) if len(idx) else float("nan")


def dust_reference(
    beam: np.ndarray,
    rng_m: np.ndarray,
    material: np.ndarray,
    intensity: np.ndarray,
    beta: np.ndarray,
    spacing: float,
    *,
    frame: int,
    seed: int,
    max_returns: int = 1,
) -> dict[str, np.ndarray]:
    """Row-aligned reference of FR-013-11 to FR-013-14, written from the spec text."""
    n = len(rng_m)
    tau = np.array([tau_ref(beta[i], spacing, float(rng_m[i])) for i in range(n)])
    u = np.array([beam_u_ref(frame, int(beam[i]), seed) for i in range(n)])
    floor = np.where(np.asarray(material) == "retro", TAU_FLOOR["retro"], TAU_FLOOR["diffuse"])
    keep = (tau <= TAU_ON) | ((tau <= floor) & (u * (floor - TAU_ON) < floor - tau))
    emit = (tau > TAU_ON) & (~keep | (max_returns >= 2))
    edge = np.array([edge_ref(beta[i], spacing, float(rng_m[i])) if emit[i] else np.nan for i in range(n)])
    return {
        "tau": tau,
        "u": u,
        "kept": keep,
        "intensity": intensity * np.exp(-2.0 * tau),
        "emit_dust": emit,
        "r_edge": edge,
    }


def uniform_beta(n_rows: int, beta: float, extent_m: float, spacing: float) -> np.ndarray:
    """(n_rows, m) extinction samples for a uniform layer, m samples covering at least `extent_m`."""
    m = int(math.ceil(extent_m / spacing)) + 2
    return np.full((n_rows, m), float(beta), dtype=np.float64)


# ------------------------------------------------------------------------------------------------------- statistics
def ks_pvalue(sample: np.ndarray) -> float:
    """Kolmogorov-Smirnov p-value of `sample` against U(0, 1): the asymptotic Kolmogorov series (n large)."""
    x = np.sort(np.asarray(sample, dtype=np.float64))
    n = len(x)
    i = np.arange(1, n + 1)
    d = max(float(np.max(i / n - x)), float(np.max(x - (i - 1) / n)))
    lam = (math.sqrt(n) + 0.12 + 0.11 / math.sqrt(n)) * d
    if lam < 1e-3:
        return 1.0
    return float(
        min(1.0, max(0.0, 2.0 * sum((-1) ** (k - 1) * math.exp(-2.0 * k * k * lam * lam) for k in range(1, 101))))
    )


def chi2_interval(df: int, z: float = 3.2905267314919255) -> tuple[float, float]:
    """Two-sided 99.9 % chi-square interval by the Wilson-Hilferty normal approximation (df large: error < 1e-4)."""

    def q(zz: float) -> float:
        return df * (1.0 - 2.0 / (9.0 * df) + zz * math.sqrt(2.0 / (9.0 * df))) ** 3

    return q(-z), q(z)


def label_components_8(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """8-connected components of a boolean mask by breadth-first search: (x_min, y_min, x_max, y_max, area), sorted."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    for y0 in range(h):
        for x0 in range(w):
            if mask[y0, x0] and not seen[y0, x0]:
                stack = [(y0, x0)]
                seen[y0, x0] = True
                xs, ys = [], []
                while stack:
                    y, x = stack.pop()
                    xs.append(x)
                    ys.append(y)
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            yy, xx = y + dy, x + dx
                            if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not seen[yy, xx]:
                                seen[yy, xx] = True
                                stack.append((yy, xx))
                out.append((min(xs), min(ys), max(xs), max(ys), len(xs)))
    return sorted(out)


def chamfer_ref(a: np.ndarray, b: np.ndarray) -> float:
    """Symmetric mean Chamfer distance (mean of the two mean nearest-neighbour distances), brute force."""

    def one_way(p: np.ndarray, q: np.ndarray) -> float:
        total = 0.0
        for i in range(0, len(p), 512):
            d = np.linalg.norm(p[i : i + 512, None, :] - q[None, :, :], axis=2)
            total += float(d.min(axis=1).sum())
        return total / len(p)

    return 0.5 * (one_way(a, b) + one_way(b, a))
