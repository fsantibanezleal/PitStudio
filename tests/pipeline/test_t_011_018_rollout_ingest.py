"""T-011-018 - FR-011-14: hostile rollout files are rejected by `s10_preprocess` with the reason and never coerced.

Oracles (independent of the code under test; plan 011 test strategy FR-011-14: "one invalid file per class, built
    by the test"):
- rollout files built here from the DC-011-01 example (`granular-rollout.valid.json`): the payload is a Parquet
    table with one
  row per particle and frame, columns `frame` (int32), `particle` (int32), `type` (int32 index into
      `particle_types`), `x` and `y`
  (float32), rows ordered by frame then particle; the store digest is the SHA-256 of the Parquet file (spec section 8);
- one invalid file per class listed in FR-011-14: missing frame interval, diameter or radius, a non-finite value,
    non-increasing
  frame times, a particle count that changes between frames, an unknown geometry family, an absolute store path, a
      store path
  containing `..`; plus the checker classes of the corpus index (digest, connectivity radius != 2.5 d, payload
      particle count,
  frame count, unknown particle type) and unreadable files;
- "never coerces": a number given as a string, a float given where an integer is required.

Expected public API (module `pitstudio_pipeline.surrogates.gns.data`, package under `pipeline/src/`; errors in
`pitstudio_pipeline.surrogates.errors`):

    s10_preprocess(meta_path, *, root) -> PreprocessedRollout
        meta_path: the metadata JSON (DC-011-01); root: the directory the store path is relative to.
        PreprocessedRollout attributes: meta (dict), positions (float32 [T, N, 2]), particle_types (int64 [N]).
        Raises `RolloutFileError` (attribute `.reason`, naming the offending key or class) for every invalid file;
            it never
        coerces a value and never reads the payload before the metadata and the store path are valid.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.errors import RolloutFileError  # noqa: E402
from pitstudio_pipeline.surrogates.gns import data  # noqa: E402

EX = ROOT / "specs" / "011-surrogates" / "contracts" / "examples"
VALID = json.loads((EX / "granular-rollout.valid.json").read_text(encoding="utf-8"))
N, T = 6, 5


def base_meta() -> dict:
    meta = copy.deepcopy(VALID)
    meta["particle_count"] = N
    meta["frame_times_s"] = [round(0.01 * k, 6) for k in range(T)]
    meta["rest_time_s"] = 0.04
    return meta


def base_table() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(0)
    pos = rng.uniform(0.1, 0.9, (T, N, 2)).astype(np.float32)
    return {
        "frame": np.repeat(np.arange(T), N).astype(np.int32),
        "particle": np.tile(np.arange(N), T).astype(np.int32),
        "type": np.zeros(T * N, dtype=np.int32),
        "x": pos[:, :, 0].reshape(-1),
        "y": pos[:, :, 1].reshape(-1),
    }


def write_rollout(root: Path, *, meta=None, table=None, name="rollout") -> Path:
    import pyarrow as pa
    import pyarrow.parquet as pq

    meta = base_meta() if meta is None else meta
    table = base_table() if table is None else table
    pq.write_table(pa.table(table), root / f"{name}.parquet")
    meta["store"] = {
        "format": "parquet",
        "path": f"{name}.parquet",
        "sha256": hashlib.sha256((root / f"{name}.parquet").read_bytes()).hexdigest(),
    }
    path = root / f"{name}.json"
    path.write_text(json.dumps(meta), encoding="utf-8")
    return path


def rewrite_meta(path: Path, fn) -> None:
    meta = json.loads(path.read_text(encoding="utf-8"))
    fn(meta)
    path.write_text(json.dumps(meta), encoding="utf-8")


@pytest.mark.req("FR-011-14")
def test_a_valid_rollout_loads_with_positions_and_types(tmp_path: Path) -> None:
    out = data.s10_preprocess(write_rollout(tmp_path), root=tmp_path)
    table = base_table()
    assert out.positions.shape == (T, N, 2)
    assert out.positions.dtype == np.float32
    assert np.array_equal(out.positions[:, :, 0].reshape(-1), table["x"])
    assert np.array_equal(out.positions[:, :, 1].reshape(-1), table["y"])
    assert out.particle_types.shape == (N,)
    assert out.meta["geometry_id"] == "g017"


@pytest.mark.req("FR-011-14")
@pytest.mark.parametrize("key", ["frame_interval_s", "particle_diameter_m", "connectivity_radius_m"])
def test_a_missing_frame_interval_diameter_or_radius_is_rejected_naming_the_key(tmp_path: Path, key: str) -> None:
    path = write_rollout(tmp_path)
    rewrite_meta(path, lambda m: m.pop(key))
    with pytest.raises(RolloutFileError, match=key) as info:
        data.s10_preprocess(path, root=tmp_path)
    assert info.value.reason


@pytest.mark.req("FR-011-14")
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("frame_interval_s", float("nan")),
        ("frame_interval_s", float("inf")),
        ("particle_diameter_m", float("nan")),
        ("connectivity_radius_m", float("-inf")),
        ("rest_time_s", float("nan")),
    ],
)
def test_a_non_finite_metadata_value_is_rejected(tmp_path: Path, key: str, value: float) -> None:
    path = write_rollout(tmp_path)
    rewrite_meta(path, lambda m: m.__setitem__(key, value))  # json.dumps writes NaN / Infinity
    with pytest.raises(RolloutFileError, match=key):
        data.s10_preprocess(path, root=tmp_path)


@pytest.mark.req("FR-011-14")
@pytest.mark.parametrize("column", ["x", "y"])
@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_a_non_finite_payload_value_is_rejected(tmp_path: Path, column: str, value: float) -> None:
    table = base_table()
    table[column][7] = value
    with pytest.raises(RolloutFileError, match="non-finite"):
        data.s10_preprocess(write_rollout(tmp_path, table=table), root=tmp_path)


@pytest.mark.req("FR-011-14")
@pytest.mark.parametrize(
    "times",
    [
        [0.0, 0.01, 0.01, 0.03, 0.04],
        [0.0, 0.02, 0.01, 0.03, 0.04],
        [0.04, 0.03, 0.02, 0.01, 0.0],
        [0.0, 0.01, 0.02, 0.03, 0.03],
    ],
    ids=["equal", "swap", "reversed", "equal-last"],
)
def test_frame_times_that_do_not_strictly_increase_are_rejected(tmp_path: Path, times: list[float]) -> None:
    meta = base_meta()
    meta["frame_times_s"] = times
    with pytest.raises(RolloutFileError, match="frame_times_s"):
        data.s10_preprocess(write_rollout(tmp_path, meta=meta), root=tmp_path)


@pytest.mark.req("FR-011-14")
def test_a_particle_count_that_changes_between_frames_is_rejected(tmp_path: Path) -> None:
    table = base_table()
    keep = ~((table["frame"] == 2) & (table["particle"] == 5))  # frame 2 has 5 particles, the others 6
    table = {k: v[keep] for k, v in table.items()}
    with pytest.raises(RolloutFileError, match=r"particle count|particle_count"):
        data.s10_preprocess(write_rollout(tmp_path, table=table), root=tmp_path)


@pytest.mark.req("FR-011-14")
def test_a_payload_whose_particle_count_differs_from_the_metadata_is_rejected(tmp_path: Path) -> None:
    meta = base_meta()
    meta["particle_count"] = N + 1
    with pytest.raises(RolloutFileError, match="particle_count"):
        data.s10_preprocess(write_rollout(tmp_path, meta=meta), root=tmp_path)


@pytest.mark.req("FR-011-14")
def test_a_frame_count_that_differs_from_the_frame_times_is_rejected(tmp_path: Path) -> None:
    meta = base_meta()
    meta["frame_times_s"] = [0.0, 0.01, 0.02, 0.03]  # 4 times, 5 frames in the payload
    meta["rest_time_s"] = 0.03
    with pytest.raises(RolloutFileError, match="frame"):
        data.s10_preprocess(write_rollout(tmp_path, meta=meta), root=tmp_path)


@pytest.mark.req("FR-011-14")
@pytest.mark.parametrize("family", ["landslide", "", "Column-Collapse", "column collapse", None])
def test_an_unknown_geometry_family_is_rejected(tmp_path: Path, family) -> None:
    path = write_rollout(tmp_path)
    rewrite_meta(path, lambda m: m.__setitem__("family", family))
    with pytest.raises(RolloutFileError, match="family"):
        data.s10_preprocess(path, root=tmp_path)


@pytest.mark.req("FR-011-14")
@pytest.mark.parametrize(
    "store_path",
    [
        "/etc/passwd",
        "C:/data/rollout.parquet",
        "C:\\data\\rollout.parquet",
        "\\\\server\\share\\r.parquet",
        "../outside.parquet",
        "a/../../b.parquet",
        "a/./b/../../../c.parquet",
        "dir\x00/r.parquet",
        "",
    ],
    ids=[
        "posix-abs",
        "win-abs",
        "win-backslash",
        "unc",
        "parent",
        "nested-parent",
        "dot-segments",
        "null-byte",
        "empty",
    ],
)
def test_an_absolute_or_dotdot_store_path_is_rejected_before_anything_is_read(tmp_path: Path, store_path: str) -> None:
    path = write_rollout(tmp_path)
    rewrite_meta(path, lambda m: m["store"].__setitem__("path", store_path))
    with pytest.raises(RolloutFileError, match="path"):
        data.s10_preprocess(path, root=tmp_path)


@pytest.mark.req("FR-011-14")
def test_a_digest_that_differs_from_the_payload_is_rejected(tmp_path: Path) -> None:
    path = write_rollout(tmp_path)
    parquet = tmp_path / "rollout.parquet"
    parquet.write_bytes(parquet.read_bytes() + b"\x00")
    with pytest.raises(RolloutFileError, match="sha256"):
        data.s10_preprocess(path, root=tmp_path)


@pytest.mark.req("FR-011-14")
@pytest.mark.parametrize("radius_factor", [2.0, 3.0, 2.4999, 2.5001])
def test_a_connectivity_radius_that_is_not_2_5_d_is_rejected(tmp_path: Path, radius_factor: float) -> None:
    meta = base_meta()
    meta["connectivity_radius_m"] = radius_factor * meta["particle_diameter_m"]
    with pytest.raises(RolloutFileError, match="connectivity_radius_m"):
        data.s10_preprocess(write_rollout(tmp_path, meta=meta), root=tmp_path)


@pytest.mark.req("FR-011-14")
def test_a_particle_type_index_beyond_the_declared_types_is_rejected(tmp_path: Path) -> None:
    table = base_table()
    table["type"][:] = 3  # `particle_types` declares one type, "grain"
    with pytest.raises(RolloutFileError, match="type"):
        data.s10_preprocess(write_rollout(tmp_path, table=table), root=tmp_path)


@pytest.mark.req("FR-011-14")
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("frame_interval_s", "0.01"),
        ("particle_diameter_m", "0.004"),
        ("particle_count", "6"),
        ("particle_count", 6.5),
        ("packing_seed", "3"),
        ("bounds_m", "0,0,1.6,0.8"),
        ("rest_time_s", True),
    ],
)
def test_values_of_the_wrong_type_are_rejected_not_coerced(tmp_path: Path, key: str, value) -> None:
    path = write_rollout(tmp_path)
    rewrite_meta(path, lambda m: m.__setitem__(key, value))
    with pytest.raises(RolloutFileError, match=key):
        data.s10_preprocess(path, root=tmp_path)


@pytest.mark.req("FR-011-14")
@pytest.mark.parametrize("geometry_id", ["gé-017", "G17", "g 17", "", "g" * 65])
def test_a_malformed_geometry_id_is_rejected(tmp_path: Path, geometry_id: str) -> None:
    path = write_rollout(tmp_path)
    rewrite_meta(path, lambda m: m.__setitem__("geometry_id", geometry_id))
    with pytest.raises(RolloutFileError, match="geometry_id"):
        data.s10_preprocess(path, root=tmp_path)


@pytest.mark.req("FR-011-14")
@pytest.mark.parametrize("payload", [b"", b"not parquet", b"PAR1" + b"\x00" * 64], ids=["empty", "text", "truncated"])
def test_an_unreadable_payload_is_a_rollout_file_error_not_a_crash(tmp_path: Path, payload: bytes) -> None:
    path = write_rollout(tmp_path)
    (tmp_path / "rollout.parquet").write_bytes(payload)
    rewrite_meta(path, lambda m: m["store"].__setitem__("sha256", hashlib.sha256(payload).hexdigest()))
    with pytest.raises(RolloutFileError):
        data.s10_preprocess(path, root=tmp_path)


@pytest.mark.req("FR-011-14")
@pytest.mark.parametrize(
    "text",
    ["", "{", '{"family": "column-collapse"', "[]", "null", "\x00\x01"],
    ids=["empty", "open", "truncated", "list", "null", "binary"],
)
def test_a_malformed_metadata_file_is_a_rollout_file_error(tmp_path: Path, text: str) -> None:
    path = tmp_path / "meta.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(RolloutFileError):
        data.s10_preprocess(path, root=tmp_path)


@pytest.mark.req("FR-011-14")
def test_a_missing_metadata_or_payload_file_is_a_rollout_file_error(tmp_path: Path) -> None:
    with pytest.raises(RolloutFileError):
        data.s10_preprocess(tmp_path / "absent.json", root=tmp_path)
    path = write_rollout(tmp_path)
    (tmp_path / "rollout.parquet").unlink()
    with pytest.raises(RolloutFileError):
        data.s10_preprocess(path, root=tmp_path)


@pytest.mark.req("FR-011-14")
def test_a_rejected_file_leaves_the_directory_unchanged(tmp_path: Path) -> None:
    path = write_rollout(tmp_path)
    rewrite_meta(path, lambda m: m.pop("frame_interval_s"))
    before = sorted(p.name for p in tmp_path.iterdir())
    with pytest.raises(RolloutFileError):
        data.s10_preprocess(path, root=tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == before
