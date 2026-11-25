# ruff: noqa: E501
"""Shared fixtures and hand-built oracles of the spec 008 acceptance tests (pipeline lane, package `pitstudio_pipeline`).

This module holds no test. It is imported by `tests/pipeline/test_t_008_*.py` and `tests/contract/test_t_008_*.py`
(which put `tests/pipeline` on `sys.path`) and is locked with the first of them. Everything here is built from the
standard library, numpy, Pillow, PyYAML, httpx and jsonschema; none of it calls the code under test.

What it provides:
- a mocked HTTP transport (`Net`) with Range, redirects, cut streams, oversize bodies and failure sequences, so no test
  opens a network connection (plan 008, test strategy);
- registry builders (`entry`, `file_rec`, `write_registry`) that follow spec 001 data-model section 5;
- a schema-validation helper that resolves the draft contracts of specs 001 and 008 by `$id` (`schema_errors`);
- hand-written binary fixtures: a GeoTIFF (TIFF tags written through Pillow), a LAS 1.2 file (ASPRS LAS 1.2 header,
  227 bytes, point format 0), a GeoPackage (OGC 12-128r18 tables and geometry blob) and JPEG / indexed PNG pairs;
- the hand calculation of the Mendeley groups (spec 008 FR-008-28, P-008-06), written out in `mendeley_*`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import struct
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC008 = ROOT / "specs" / "008-data-pipeline"
SPEC001 = ROOT / "specs" / "001-contracts"

HEX64 = "0123456789abcdef" * 4
LABEL = "calibrated synthetic — not validated against real data"  # FR-008-36 exact label (U+2014 em dash)


def NOW() -> dt.datetime:
    return dt.datetime(2026, 10, 11, 12, 0, 0, tzinfo=dt.UTC)


NOW_TEXT = "2026-10-11T12:00:00Z"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def payload(n: int, seed: int = 0) -> bytes:
    """Deterministic pseudo-random bytes (numpy PCG64), the fixture 'file' served by the mocked transport."""
    return np.random.default_rng(seed).integers(0, 256, size=n, dtype=np.uint8).tobytes()


# --------------------------------------------------------------------------------------------------- schemas
def _schema_path(name: str) -> Path:
    for base in (ROOT / "contracts", SPEC008 / "contracts", SPEC001 / "contracts"):
        if (base / name).is_file():
            return base / name
    raise FileNotFoundError(name)


def _schema_registry() -> Any:
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    reg: Any = Registry()
    for base in (SPEC001 / "contracts", SPEC008 / "contracts", ROOT / "contracts"):  # later = promoted wins
        for p in sorted(base.glob("*.schema.json")):
            doc = json.loads(p.read_text(encoding="utf-8"))
            reg = reg.with_resource(doc["$id"], Resource.from_contents(doc, DRAFT202012))
    return reg


def schema_errors(schema_file: str, doc: Any) -> list[str]:
    """Every violation of `doc` against the contract `schema_file` (reference implementation: jsonschema)."""
    from jsonschema import Draft202012Validator

    schema = json.loads(_schema_path(schema_file).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, registry=_schema_registry())
    return [f"/{'/'.join(map(str, e.absolute_path))}: {e.message[:160]}" for e in validator.iter_errors(doc)]


def draft_schema_path(name: str) -> Path:
    return _schema_path(name)


# --------------------------------------------------------------------------------------------------- registry
def file_rec(
    url: str,
    data: bytes | None = None,
    *,
    kind: str = "table",
    pinned: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "url": url,
        "sha256": sha256_hex(data) if (data is not None and pinned) else None,
        "bytes": len(data) if (data is not None and pinned) else None,
        "kind": kind,
    }
    rec.update(extra)
    return rec


def entry(
    sid: str,
    files: list[dict[str, Any]],
    *,
    access: str = "direct",
    spdx: str = "CC0-1.0",
    licence_class: str = "open-no-attribution",
    redistribution: str = "redistributable",
    account: dict[str, Any] | None = None,
    fallback: dict[str, Any] | None = None,
    attribution: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """A registry entry valid against spec 001 data-model section 5.1."""
    e: dict[str, Any] = {
        "id": sid,
        "kind": "real",
        "title": f"Fixture source {sid}",
        "landing_url": "https://example.org/data/" + sid,
        "access": access,
        "files": files,
        "spdx": spdx,
        "licence_url": "https://example.org/licence/" + sid,
        "licence_class": licence_class,
        "redistribution": redistribution,
        "citation": f"Example publisher (2026). Fixture {sid}.",
        "card": f"data/cards/{sid}.md",
        "account": account if account is not None else {"needed": False},
    }
    if attribution is not None:
        e["attribution"] = attribution
    if fallback is not None:
        e["fallback"] = fallback
    e.update(extra)
    return e


def write_registry(directory: Path, entries: list[dict[str, Any]], name: str = "sources.yaml") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_text(yaml.safe_dump({"sources": entries}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p


def make_repo(tmp: Path, name: str = "repo") -> Path:
    """A fake repository working tree: a directory with a `.git` folder and the data folders of the layout."""
    repo = tmp / name
    (repo / ".git").mkdir(parents=True)
    for sub in ("raw", "external", "interim", "processed", "synthetic", "samples", "splits", "pins", "cards"):
        (repo / "data" / sub).mkdir(parents=True)
    return repo


def files_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


def tree_digest(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256_hex(p.read_bytes()) for p in files_under(root)}


# --------------------------------------------------------------------------------------------------- mocked network
class CutStream(httpx.SyncByteStream):
    """A response body that yields `data` in chunks and then raises `error` (a connection cut) when given."""

    def __init__(self, data: bytes, error: Exception | None = None, chunk: int = 1024) -> None:
        self.data, self.error, self.chunk = data, error, chunk
        self.yielded = 0

    def __iter__(self):
        for i in range(0, len(self.data), self.chunk):
            piece = self.data[i : i + self.chunk]
            self.yielded += len(piece)
            yield piece
        if self.error is not None:
            raise self.error


def range_server(data: bytes, *, honour_range: bool = True) -> Callable[[httpx.Request], httpx.Response]:
    """Serves `data`; with `honour_range` answers `Range: bytes=N-` with 206 and Content-Range, else always 200."""

    def respond(request: httpx.Request) -> httpx.Response:
        rng = request.headers.get("range")
        if honour_range and rng and rng.startswith("bytes=") and rng.endswith("-"):
            start = int(rng[len("bytes=") : -1])
            return httpx.Response(
                206,
                content=data[start:],
                headers={"Content-Range": f"bytes {start}-{len(data) - 1}/{len(data)}"},
            )
        return httpx.Response(200, content=data)

    return respond


class Seq:
    """Responders used in order, one per request; the last one repeats."""

    def __init__(self, *items: Any) -> None:
        self.items = list(items)
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        item = self.items[min(self.calls, len(self.items) - 1)]
        self.calls += 1
        return Net.respond(item, request)


class Net:
    """A mocked transport. `routes` maps a full URL to bytes, a responder callable, an exception or a `Seq`."""

    def __init__(self, routes: dict[str, Any] | None = None, *, forbid: bool = False) -> None:
        self.routes: dict[str, Any] = dict(routes or {})
        self.requests: list[httpx.Request] = []
        self.forbid = forbid
        self.transport = httpx.MockTransport(self._handle)

    @staticmethod
    def respond(item: Any, request: httpx.Request) -> httpx.Response:
        if isinstance(item, Exception):
            raise item
        if isinstance(item, bytes):
            return httpx.Response(200, content=item)
        return item(request)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.forbid:
            raise AssertionError(f"network request made while forbidden: {request.url}")
        key = str(request.url)
        if key not in self.routes:
            return httpx.Response(404, content=b"not found")
        return self.respond(self.routes[key], request)

    @property
    def urls(self) -> list[str]:
        return [str(r.url) for r in self.requests]


class Sleeps(list):
    """Records the back-off delays instead of sleeping (the injected `sleep`)."""

    def __call__(self, seconds: float) -> None:
        self.append(seconds)

    def __bool__(self) -> bool:  # always truthy: an implementation doing `sleep or time.sleep` must still use this one
        return True


# --------------------------------------------------------------------------------------------------- GeoTIFF
def write_geotiff(
    path: Path,
    array: np.ndarray,
    *,
    epsg: int | None = 32612,
    cell: tuple[float, float] | None = (1.0, 1.0),
    origin: tuple[float, float] = (400000.0, 4500000.0),
    nodata: float | None = None,
) -> Path:
    """A single-band GeoTIFF written with Pillow tags (GeoTIFF 1.0: ModelPixelScale 33550, ModelTiepoint 33922,
    GeoKeyDirectory 34735, GDAL_NODATA 42113). `epsg=None` writes no GeoKeyDirectory (no CRS); `cell=None` writes no
    pixel scale."""
    from PIL import Image, TiffImagePlugin

    ifd = TiffImagePlugin.ImageFileDirectory_v2()
    if cell is not None:
        ifd[33550] = (float(cell[0]), float(cell[1]), 0.0)
        ifd.tagtype[33550] = 12  # DOUBLE
        ifd[33922] = (0.0, 0.0, 0.0, float(origin[0]), float(origin[1]), 0.0)
        ifd.tagtype[33922] = 12
    if epsg is not None:
        ifd[34735] = (1, 1, 0, 3, 1024, 0, 1, 1, 1025, 0, 1, 1, 3072, 0, 1, int(epsg))
        ifd.tagtype[34735] = 3  # SHORT
    if nodata is not None:
        ifd[42113] = f"{nodata:g}"
        ifd.tagtype[42113] = 2  # ASCII
    Image.fromarray(array).save(path, format="TIFF", tiffinfo=ifd)
    return path


# --------------------------------------------------------------------------------------------------- LAS 1.2
def write_las(
    path: Path,
    xyz: np.ndarray,
    classification: Sequence[int],
    *,
    epsg: int | None = 32612,
    scale: float = 0.01,
) -> Path:
    """LAS 1.2, point data record format 0 (20 bytes per point), one GeoKeyDirectory VLR when `epsg` is given.
    Layout from the ASPRS LAS 1.2 specification: 227-byte public header block, VLRs, then point records."""
    xyz = np.asarray(xyz, dtype=np.float64).reshape(-1, 3)
    n = len(xyz)
    vlr = b""
    if epsg is not None:
        keys = struct.pack("<8H", 1, 1, 0, 1, 3072, 0, 1, int(epsg))  # header + one key: ProjectedCSTypeGeoKey
        vlr = (
            struct.pack(
                "<H16sHH32s",
                0,
                b"LASF_Projection".ljust(16, b"\0"),
                34735,
                len(keys),
                b"GeoKeyDirectory".ljust(32, b"\0"),
            )
            + keys
        )
    offset_to_points = 227 + len(vlr)
    mins = xyz.min(axis=0) if n else np.zeros(3)
    maxs = xyz.max(axis=0) if n else np.zeros(3)
    header = struct.pack(
        "<4sHH16sBB32s32sHHHIIBHI5I3d3d6d",
        b"LASF",
        0,
        0,
        b"\0" * 16,
        1,
        2,
        b"fixture".ljust(32, b"\0"),
        b"pitstudio-tests".ljust(32, b"\0"),
        1,
        2026,
        227,
        offset_to_points,
        1 if vlr else 0,
        0,
        20,
        n,
        n,
        0,
        0,
        0,
        0,
        scale,
        scale,
        scale,
        0.0,
        0.0,
        0.0,
        maxs[0],
        mins[0],
        maxs[1],
        mins[1],
        maxs[2],
        mins[2],
    )
    assert len(header) == 227, len(header)
    body = b"".join(
        struct.pack(
            "<iiiHBBbBH",
            round(x / scale),
            round(y / scale),
            round(z / scale),
            100,
            0x11,
            int(c),
            0,
            0,
            1,
        )
        for (x, y, z), c in zip(xyz, classification, strict=True)
    )
    path.write_bytes(header + vlr + body)
    return path


# --------------------------------------------------------------------------------------------------- GeoPackage
def _wkb_polygon(ring: Sequence[tuple[float, float]]) -> bytes:
    pts = b"".join(struct.pack("<dd", x, y) for x, y in ring)
    return struct.pack("<BIII", 1, 3, 1, len(ring)) + pts


def write_gpkg(
    path: Path,
    polygons: Sequence[Sequence[tuple[float, float]]],
    *,
    srs_id: int | None = 32612,
    attributes: Sequence[str] = ("name",),
    names: Sequence[str] | None = None,
) -> Path:
    """OGC GeoPackage 1.3 with one feature table `pits` of polygons. `srs_id=None` stores the undefined Cartesian
    system (-1), i.e. no CRS. `attributes` are the text columns besides `fid` and `geom`."""
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA application_id = 1196444487")
        con.execute("PRAGMA user_version = 10300")
        con.execute(
            "CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY, organization TEXT NOT NULL, "
            "organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT)"
        )
        con.executemany(
            "INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)",
            [
                ("Undefined Cartesian SRS", -1, "NONE", -1, "undefined", None),
                ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
                ("WGS 84 / UTM zone 12N", 32612, "EPSG", 32612, 'PROJCS["WGS 84 / UTM zone 12N"]', None),
            ],
        )
        con.execute(
            "CREATE TABLE gpkg_contents (table_name TEXT PRIMARY KEY, data_type TEXT NOT NULL, identifier TEXT, description TEXT, "
            "last_change TEXT NOT NULL, min_x REAL, min_y REAL, max_x REAL, max_y REAL, srs_id INTEGER)"
        )
        con.execute(
            "CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL, column_name TEXT NOT NULL, geometry_type_name TEXT NOT NULL, "
            "srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL)"
        )
        sid = -1 if srs_id is None else srs_id
        con.execute(
            "INSERT INTO gpkg_contents VALUES ('pits','features','pits','',?,0,0,0,0,?)",
            ("2026-10-11T12:00:00.000Z", sid),
        )
        con.execute("INSERT INTO gpkg_geometry_columns VALUES ('pits','geom','POLYGON',?,0,0)", (sid,))
        cols = "".join(f", {a} TEXT" for a in attributes)
        con.execute(f"CREATE TABLE pits (fid INTEGER PRIMARY KEY AUTOINCREMENT, geom BLOB{cols})")
        for i, ring in enumerate(polygons):
            blob = b"GP" + struct.pack("<BBi", 0, 1, sid) + _wkb_polygon(ring)
            vals = [(names[i] if names else f"pit-{i}") for _ in attributes]
            con.execute(
                f"INSERT INTO pits (geom{''.join(', ' + a for a in attributes)}) VALUES (?{', ?' * len(attributes)})",
                (blob, *vals),
            )
        con.commit()
    finally:
        con.close()
    return path


SQUARE = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
BOWTIE = ((0.0, 0.0), (10.0, 10.0), (10.0, 0.0), (0.0, 10.0), (0.0, 0.0))  # self-intersecting: invalid (OGC SFA)
UNCLOSED = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))  # first point != last point


# --------------------------------------------------------------------------------------------------- images and masks
def write_rgb_jpeg(path: Path, size: tuple[int, int] = (512, 512), mode: str = "RGB") -> Path:
    from PIL import Image

    colour: Any = (120, 90, 60) if mode == "RGB" else 120
    Image.new(mode, size, colour).save(path, format="JPEG")
    return path


def write_indexed_mask(path: Path, labels: np.ndarray, *, mode: str = "P") -> Path:
    """An indexed PNG: palette index = label (0 background, k = instance k)."""
    from PIL import Image

    arr = np.ascontiguousarray(labels, dtype=np.uint8)
    if mode == "P":
        img = Image.frombytes("P", (arr.shape[1], arr.shape[0]), arr.tobytes())
        img.putpalette([c for i in range(256) for c in (i, (i * 7) % 256, (i * 13) % 256)])
    else:
        img = Image.fromarray(arr)  # 8-bit grayscale, mode "L"
    img.save(path, format="PNG")
    return path


# --------------------------------------------------------------------------------------------------- Mendeley hand calculation
# Spec 008 FR-008-28. File k (1..960): original o(k) = ((k-1) mod 240) + 1; scene s(k) = ((k-1) mod 80) + 1.
# The 9 conservative links, as original file numbers:
MENDELEY_LINKS: tuple[tuple[int, int], ...] = (
    (29, 39),
    (34, 41),
    (36, 37),
    (41, 49),
    (59, 60),
    (189, 199),
    (192, 196),
    (196, 198),
    (196, 201),
)


def mendeley_scene(k: int) -> int:
    return ((k - 1) % 80) + 1


def mendeley_original(k: int) -> int:
    return ((k - 1) % 240) + 1


# Hand calculation of the scene components (by hand, from the links mapped to scenes):
#   (29,39) -> s(29)=29, s(39)=39;  (34,41), (36,37), (41,49), (59,60) map to themselves (all <= 80);
#   (189,199): 189 = 2*80+29 -> 29, 199 = 2*80+39 -> 39;  (192,196): 32, 36;  (196,198): 36, 38;  (196,201): 36, 41.
# Components: {29,39}; {32,34,36,37,38,41,49} (34-41-49, 36-37, 32-36, 36-38, 36-41); {59,60}; every other scene alone.
MENDELEY_COMPONENTS: tuple[frozenset[int], ...] = (
    frozenset({29, 39}),
    frozenset({32, 34, 36, 37, 38, 41, 49}),
    frozenset({59, 60}),
)


def mendeley_group_of(k: int) -> int:
    """Group id of file k: the smallest original of its component = the smallest scene number of the component
    (scene s has the originals s, s+80, s+160, so the smallest original of a scene is s itself)."""
    s = mendeley_scene(k)
    for comp in MENDELEY_COMPONENTS:
        if s in comp:
            return min(comp)
    return s


def mendeley_groups() -> dict[int, list[int]]:
    """group id -> files (1..960) of the group, by hand calculation."""
    out: dict[int, list[int]] = {}
    for k in range(1, 961):
        out.setdefault(mendeley_group_of(k), []).append(k)
    return out


def components_by_union_find(
    links: Iterable[tuple[int, int]], scenes: Iterable[int] = range(1, 81)
) -> list[frozenset[int]]:
    """A second, independent derivation of the scene components (plain union-find written here), used to cross-check
    the hand table above and to build the metamorphic variants of P-008-08."""
    parent = {s: s for s in scenes}

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in links:
        ra, rb = find(mendeley_scene(a)), find(mendeley_scene(b))
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    comps: dict[int, set[int]] = {}
    for s in parent:
        comps.setdefault(find(s), set()).add(s)
    return [frozenset(c) for c in comps.values()]


def canonical_membership_sha(groups: Any, folds: Any) -> str:
    """SHA-256 of the RFC 8785 canonical JSON of {groups, folds}. The documents hold only strings and integers, for
    which `json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False)` is the JCS serialisation."""
    text = json.dumps({"groups": groups, "folds": folds}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def env_with(**kwargs: str) -> dict[str, str]:
    """A minimal environment mapping injected as `env` (never the real `os.environ`)."""
    base = {"PATH": os.environ.get("PATH", "")}
    base.update(kwargs)
    return base


def run(tmp: Path, entries: list[dict[str, Any]], net: Net, *, data_root: Path | None = None, **kw: Any) -> Any:
    """`run_download` over a registry written from `entries`, with the injected clock, sleep, env and schema.

    The stage under test is imported here, inside the function, so that this module itself imports nothing first-party."""
    from pitstudio_pipeline.download import run_download

    reg = write_registry(tmp / "cfg", entries)
    kw.setdefault("env", env_with())
    kw.setdefault("now", NOW)
    kw.setdefault("sleep", Sleeps())
    kw.setdefault("schema_path", _schema_path("sources.schema.json"))
    return run_download(reg, data_root if data_root is not None else tmp / "data", transport=net.transport, **kw)
