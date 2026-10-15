# ruff: noqa: E501, PT018, PT011
"""T-013-026: web cloud-shard quantiser and its hostile inputs.

Requirements: FR-013-35, FR-013-42, P-013-11.

Oracle: the analytical error bound of 16-bit quantisation over the shard's bounding box (each dequantised coordinate within
extent / (2 x 65,535) of the original, P-013-11 MR1), the metamorphic relations MR2 (translating the cloud leaves the errors
unchanged) and MR3 (permuting the points permutes the shard identically), hand-computed layouts (8 bytes per point: three
uint16 planes, a uint8 intensity plane and a uint8 class plane, little-endian, planar), `hashlib` for the digests, and the DC-013-04
draft schema for the header.

Expected API (package `pitstudio.sensors.quantise`, root environment; NumPy and the standard library only):
- `quantise.encode_web_shard(positions, intensity, classes, *, source, class_labels, payload_path,
  intensity_map=("lidar-intensity", 0.0, 1.0)) -> WebShard` with `.header` (a DC-013-04 dict) and `.payload` (bytes).
  `positions` (n, 3) float64 sensor-frame metres, `intensity` (n,) float, `classes` (n,) integer codes, `source` =
  `{"run_id", "scenario", "sensor", "frame"}`, `class_labels` maps each code to a slug (the header `classes` maps the decimal
  string of the code to it), `intensity_map = (quantity, low, high)`: code = round(clip((I - low) / (high - low), 0, 1) x 255).
  Per axis the offset is the minimum, the scale `extent / 65535` (1 for an axis of zero extent, the offset then being the common
  value); a coordinate code is `round((v - offset) / scale)`. The payload is planar little-endian: x[], y[], z[] (uint16),
  intensity[] (uint8), class[] (uint8): 8 bytes per point; the header holds `points`, `quantisation`, `encoding` (position
  `uint16`, intensity `uint8`, class `uint8`, little, planar), `intensity_map`, `classes` and `payload` (path, bytes, SHA-256).
- `quantise.shard_cloud(positions, intensity, classes, *, source, class_labels, payload_prefix, intensity_map=..., max_bytes=
  10_000_000) -> list[WebShard]`: splits a cloud of more than `max_bytes / 8` points into consecutive shards, each over its own
  bounding box (payload paths `<payload_prefix>-0000.bin`, `-0001.bin`, ...).
- Hostile input (a non-finite coordinate or intensity, a different length of `positions`, `intensity` and `classes`, a class code not
  in `class_labels`, an `intensity_map` with high <= low, a payload path that is not a relpath, more than 1,250,000 points in one
  `encode_web_shard`, positions that are not (n, 3)) raises `ValueError` naming the input, and no shard is produced.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import sensor_kit as kit  # noqa: E402
from pitstudio.sensors import quantise  # noqa: E402

SOURCE = {"run_id": "20261011T120000Z-quant", "scenario": "S1", "sensor": "rotary-64", "frame": 3}
CLASSES = {0: "diffuse", 1: "retro", 2: "dust"}


def _encode(pos: np.ndarray, inten: np.ndarray | None = None, cls: np.ndarray | None = None, **kw):
    n = len(pos)
    return quantise.encode_web_shard(
        pos,
        np.full(n, 0.5) if inten is None else inten,
        np.zeros(n, dtype=np.uint8) if cls is None else cls,
        source=SOURCE,
        class_labels=CLASSES,
        payload_path="shards/s1-rotary-64-0003.bin",
        **kw,
    )


def decode(shard) -> dict:
    """Decode a shard with the layout of the contract (independent of the encoder): positions, intensity codes, classes."""
    h, p = shard.header, shard.payload
    n = h["points"]
    assert len(p) == 8 * n
    q = np.frombuffer(p, dtype="<u2", count=3 * n).reshape(3, n)
    inten = np.frombuffer(p, dtype=np.uint8, count=n, offset=6 * n)
    cls = np.frombuffer(p, dtype=np.uint8, count=n, offset=7 * n)
    off, sc = np.array(h["quantisation"]["offset_m"]), np.array(h["quantisation"]["scale_m"])
    return {"codes": q, "positions": (off[:, None] + sc[:, None] * q).T, "intensity": inten, "classes": cls}


def _cloud(seed: int, n: int, extent: float) -> np.ndarray:
    return np.random.default_rng(seed).uniform(-0.5, 0.5, (n, 3)) * extent + np.random.default_rng(seed + 1).uniform(
        -50, 50, 3
    )


@pytest.mark.req("FR-013-35")
def test_the_header_is_valid_and_describes_the_payload() -> None:
    pos = _cloud(1, 1000, 120.0)
    shard = _encode(pos)
    h = shard.header
    assert kit.schema_errors("web-cloud-shard.schema.json", h) == []
    assert h["points"] == 1000 and len(shard.payload) == 8000 <= 10_000_000
    assert h["encoding"] == {
        "position": "uint16",
        "intensity": "uint8",
        "class": "uint8",
        "byte_order": "little",
        "layout": "planar",
    }
    assert h["payload"] == {
        "path": "shards/s1-rotary-64-0003.bin",
        "bytes": 8000,
        "sha256": hashlib.sha256(shard.payload).hexdigest(),
    }
    assert h["source"] == SOURCE and h["classes"] == {"0": "diffuse", "1": "retro", "2": "dust"}
    assert h["intensity_map"] == {"quantity": "lidar-intensity", "low": 0.0, "high": 1.0}


@pytest.mark.req("FR-013-35")
def test_offset_and_scale_follow_the_bounding_box_by_hand() -> None:
    pos = np.array([[10.0, -4.0, 0.0], [10.0 + 65.535, 6.0, 131.07], [30.0, 1.0, 50.0]])
    h = _encode(pos).header["quantisation"]
    assert h["offset_m"] == [10.0, -4.0, 0.0]
    np.testing.assert_allclose(h["scale_m"], [65.535 / 65535, 10.0 / 65535, 131.07 / 65535], rtol=1e-12)
    d = decode(_encode(pos))
    assert d["codes"][:, 0].tolist() == [0, 0, 0] and d["codes"][:, 1].tolist() == [
        65535,
        65535,
        65535,
    ]  # the box corners


@pytest.mark.req("FR-013-35")
def test_intensity_and_class_planes_by_hand() -> None:
    pos = _cloud(2, 5, 10.0)
    inten = np.array([0.0, 1.0, 0.5, 0.2, 1.7])  # 0.5 -> round(127.5) = 128 (half to even gives 128), 1.7 clips to 255
    d = decode(_encode(pos, inten, np.array([0, 1, 2, 1, 0], dtype=np.uint8)))
    assert d["intensity"].tolist()[:2] == [0, 255] and d["intensity"][3] == 51 and d["intensity"][4] == 255
    assert d["intensity"][2] in (127, 128)
    assert d["classes"].tolist() == [0, 1, 2, 1, 0]
    mapped = decode(
        _encode(
            pos, np.array([-20.0, 20.0, 0.0, 10.0, 30.0]), intensity_map=("radar-radial-velocity-m-per-s", -20.0, 20.0)
        )
    )
    assert mapped["intensity"][:3].tolist() == [0, 255, 128] or mapped["intensity"][:3].tolist() == [0, 255, 127]
    assert quantise.encode_web_shard(
        pos,
        inten,
        np.zeros(5, np.uint8),
        source=SOURCE,
        class_labels=CLASSES,
        payload_path="a.bin",
        intensity_map=("radar-rcs-dbsm", -10.0, 30.0),
    ).header["intensity_map"] == {"quantity": "radar-rcs-dbsm", "low": -10.0, "high": 30.0}


@pytest.mark.req("FR-013-35")
def test_an_axis_of_zero_extent_has_scale_one_and_the_offset_at_the_common_value() -> None:
    pos = np.array([[1.0, 5.0, 7.5], [2.0, 5.0, 7.5], [3.0, 5.0, 7.5]])
    shard = _encode(pos)
    q = shard.header["quantisation"]
    assert q["offset_m"][1:] == [5.0, 7.5] and q["scale_m"][1:] == [1.0, 1.0]
    assert kit.schema_errors("web-cloud-shard.schema.json", shard.header) == []
    d = decode(shard)
    np.testing.assert_array_equal(d["codes"][1:], 0)
    np.testing.assert_array_equal(d["positions"][:, 1:], pos[:, 1:])
    single = decode(_encode(np.array([[4.0, -2.0, 9.0]])))  # one point: all three axes have zero extent
    np.testing.assert_array_equal(single["positions"], [[4.0, -2.0, 9.0]])


@pytest.mark.req("P-013-11")
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1), n=st.integers(2, 3000), extent=st.floats(1.0, 2000.0))
def test_every_dequantised_coordinate_is_within_half_a_step_of_the_original(seed: int, n: int, extent: float) -> None:
    pos = _cloud(seed, n, extent)
    box = pos.max(axis=0) - pos.min(axis=0)
    got = decode(_encode(pos))["positions"]
    bound = box / (2.0 * 65535) + 1e-9 * box  # MR1
    assert np.all(np.abs(got - pos) <= bound[None, :] + 1e-12)


@pytest.mark.req("P-013-11")
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(0, 2**31 - 1), shift=st.tuples(st.floats(-1e5, 1e5), st.floats(-1e5, 1e5), st.floats(-1e5, 1e5))
)
def test_translating_the_cloud_leaves_the_quantisation_errors_unchanged(
    seed: int, shift: tuple[float, float, float]
) -> None:
    pos = _cloud(seed, 800, 500.0)
    moved = pos + np.array(shift)
    e1 = decode(_encode(pos))["positions"] - pos
    e2 = decode(_encode(moved))["positions"] - moved
    box = pos.max(axis=0) - pos.min(axis=0)
    assert np.all(np.abs(e2 - e1) <= 1e-9 * box[None, :] + 1e-9)  # MR2


@pytest.mark.req("P-013-11")
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 2**31 - 1))
def test_permuting_the_points_permutes_the_shard_identically(seed: int) -> None:
    rng = np.random.default_rng(seed)
    pos = _cloud(seed, 600, 300.0)
    inten, cls = rng.uniform(0, 1, 600), rng.integers(0, 3, 600).astype(np.uint8)
    perm = rng.permutation(600)
    a, b = _encode(pos, inten, cls), _encode(pos[perm], inten[perm], cls[perm])
    assert a.header["quantisation"] == b.header["quantisation"]  # the bounding box is the same set of points
    da, db = decode(a), decode(b)
    np.testing.assert_array_equal(db["codes"], da["codes"][:, perm])  # MR3
    np.testing.assert_array_equal(db["intensity"], da["intensity"][perm])
    np.testing.assert_array_equal(db["classes"], da["classes"][perm])


@pytest.mark.req("FR-013-35")
def test_a_cloud_over_ten_megabytes_is_split_into_shards_each_over_its_own_box() -> None:
    n = 1_250_001
    pos = _cloud(7, n, 400.0)
    shards = quantise.shard_cloud(
        pos, np.full(n, 0.5), np.zeros(n, np.uint8), source=SOURCE, class_labels=CLASSES, payload_prefix="shards/s1-big"
    )
    assert len(shards) == 2 and [s.header["points"] for s in shards] == [1_250_000, 1]
    assert [s.header["payload"]["path"] for s in shards] == ["shards/s1-big-0000.bin", "shards/s1-big-0001.bin"]
    for s in shards:
        assert len(s.payload) <= 10_000_000 and s.header["payload"]["bytes"] == len(s.payload)
        assert s.header["payload"]["sha256"] == hashlib.sha256(s.payload).hexdigest()
        assert kit.schema_errors("web-cloud-shard.schema.json", s.header) == []
    first = decode(shards[0])["positions"]
    assert np.all(
        np.abs(first - pos[:1_250_000])
        <= (pos[:1_250_000].max(axis=0) - pos[:1_250_000].min(axis=0)) / 65535 / 2 * 1.0001
    )


@pytest.mark.req("FR-013-35")
def test_a_small_cloud_is_one_shard_and_the_limit_is_exactly_1_250_000_points() -> None:
    pos = _cloud(3, 100, 10.0)
    (only,) = quantise.shard_cloud(
        pos, np.full(100, 0.5), np.zeros(100, np.uint8), source=SOURCE, class_labels=CLASSES, payload_prefix="shards/x"
    )
    assert only.header["points"] == 100
    n = 1_250_000
    big = _cloud(4, n, 50.0)
    shard = _encode(big)  # exactly at the limit: allowed, 10,000,000 bytes
    assert len(shard.payload) == 10_000_000
    with pytest.raises(ValueError):
        _encode(_cloud(4, n + 1, 50.0))


def _bad(**override):
    pos = _cloud(5, 50, 20.0)
    args = {"positions": pos, "intensity": np.full(50, 0.5), "classes": np.zeros(50, np.uint8)}
    args.update(override)
    return lambda: quantise.encode_web_shard(
        args["positions"],
        args["intensity"],
        args["classes"],
        source=SOURCE,
        class_labels=CLASSES,
        payload_path=override.get("payload_path", "a.bin"),
        intensity_map=override.get("intensity_map", ("lidar-intensity", 0.0, 1.0)),
    )


@pytest.mark.req("FR-013-42")
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("axis", [0, 1, 2])
def test_a_non_finite_coordinate_is_rejected_and_named(bad: float, axis: int) -> None:
    pos = _cloud(5, 50, 20.0)
    pos[17, axis] = bad
    with pytest.raises(ValueError) as exc:
        _bad(positions=pos)()
    assert "positions" in str(exc.value)


@pytest.mark.req("FR-013-42")
@pytest.mark.parametrize(
    ("override", "needle"),
    [
        ({"intensity": np.full(49, 0.5)}, "intensity"),
        ({"classes": np.zeros(51, np.uint8)}, "classes"),
        ({"positions": np.zeros((50, 2))}, "positions"),
        ({"positions": np.zeros(150)}, "positions"),
        ({"intensity": np.array([0.5] * 49 + [np.nan])}, "intensity"),
        ({"classes": np.full(50, 9, dtype=np.uint8)}, "class"),
        ({"intensity_map": ("lidar-intensity", 1.0, 1.0)}, "intensity_map"),
        ({"intensity_map": ("lidar-intensity", 2.0, 1.0)}, "intensity_map"),
        ({"payload_path": "../escape.bin"}, "payload"),
        ({"payload_path": "/abs.bin"}, "payload"),
        ({"payload_path": "a b.bin"}, "payload"),
    ],
)
def test_other_hostile_inputs_raise_value_error_naming_the_input(override: dict, needle: str) -> None:
    with pytest.raises(ValueError) as exc:
        _bad(**override)()
    assert needle in str(exc.value)
