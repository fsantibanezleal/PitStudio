"""FNO data (s10_preprocess; FR-011-34, FR-011-41): terrain patches, scenarios, the split and the field files.

- 64 terrain patches of 64 x 64 cells (default cell 8 m, block-mean resampled from the 1 m Bingham 3DEP DEM) split by patch into
  48 training, 6 validation and 10 test patches; 40 tailings and 20 dust scenarios per patch drawn from the recipe ranges (the
  training envelope of DC-011-02) by a seeded generator;
- `load_field_file` validates one field dataset (DC-011-03 metadata plus a Zarr payload with one float32 array `data`
  [C, ny, nx] in metadata channel order) and never coerces: grids other than 64 x 64 (128 x 128 only for a resolution-transfer run),
  missing units or cell size, non-finite values, a depth below -1e-9 m, an absolute or `..` store path, a digest or a payload shape
  that differs, output times that are not k T_end / 8 all raise `FieldFileError` naming the key or the class.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator

from pitstudio_pipeline.surrogates.digest import load_schema, zarr_digest
from pitstudio_pipeline.surrogates.errors import DatasetError, FieldFileError
from pitstudio_pipeline.surrogates.gns.data import check_store_path, read_metadata  # shared strict readers
from pitstudio_pipeline.surrogates.errors import RolloutFileError

__all__ = [
    "PatchSplit",
    "block_mean",
    "draw_dust_scenarios",
    "draw_tailings_scenarios",
    "load_field_file",
    "scenarios_for_patches",
    "split_patches",
    "zarr_digest",
]

N_PATCHES, N_TRAIN, N_VAL, N_TEST = 64, 48, 6, 10
TAILINGS_PER_PATCH, DUST_PER_PATCH = 40, 20
GRID = 64
DEPTH_FLOOR_M = -1e-9
# the training envelope of the DC-011-02 FNO example (recipe ranges)
YIELD_STRESS_PA = (10.0, 200.0)
PLASTIC_VISCOSITY_PA_S = (0.05, 1.0)
RELEASE_VOLUME_M3 = (1.0e4, 2.0e5)
DENSITY_KG_M3 = (1600.0, 2000.0)
SOURCE_STRENGTH = (0.01, 1.0)
WIND_SPEED_M_S = (1.0, 20.0)


@dataclass(frozen=True)
class PatchSplit:
    train: list[str]
    val: list[str]
    test: list[str]


def split_patches(patch_ids: Sequence[str], *, seed: int) -> PatchSplit:
    """Split exactly 64 distinct patch ids into 48 training, 6 validation and 10 test patches (reproducible by seed)."""
    ids = list(patch_ids)
    if len(ids) != N_PATCHES:
        raise DatasetError(f"exactly {N_PATCHES} patches are required, got {len(ids)}")
    if len(set(ids)) != len(ids):
        raise DatasetError("patch ids must be distinct: duplicate patch id found")
    order = np.random.default_rng(seed).permutation(len(ids))
    shuffled = [ids[i] for i in order]
    return PatchSplit(
        train=sorted(shuffled[:N_TRAIN]),
        val=sorted(shuffled[N_TRAIN : N_TRAIN + N_VAL]),
        test=sorted(shuffled[N_TRAIN + N_VAL :]),
    )


def _rng(seed: int, patch_id: str | None, stream: int) -> np.random.Generator:
    key = [int(seed) & 0xFFFFFFFF, stream] + ([zlib.crc32(patch_id.encode("utf-8"))] if patch_id is not None else [])
    return np.random.default_rng(key)


def draw_tailings_scenarios(n: int, *, seed: int, patch_id: str | None = None) -> list[dict[str, Any]]:
    """`n` breach scenarios drawn in the training envelope: uniform, except the plastic viscosity (log-uniform over a decade)."""
    rng = _rng(seed, patch_id, 1)
    out = []
    for _ in range(n):
        out.append(
            {
                "breach_row": int(rng.integers(0, GRID)),
                "breach_col": int(rng.integers(0, GRID)),
                "release_volume_m3": float(rng.uniform(*RELEASE_VOLUME_M3)),
                "yield_stress_pa": float(rng.uniform(*YIELD_STRESS_PA)),
                "plastic_viscosity_pa_s": float(math.exp(rng.uniform(math.log(PLASTIC_VISCOSITY_PA_S[0]), math.log(PLASTIC_VISCOSITY_PA_S[1])))),
                "density_kg_per_m3": float(rng.uniform(*DENSITY_KG_M3)),
            }
        )
    return out


def draw_dust_scenarios(n: int, *, seed: int, patch_id: str | None = None) -> list[dict[str, Any]]:
    """`n` dust scenarios: a source line on the grid, a source strength and a wind (speed and direction)."""
    rng = _rng(seed, patch_id, 2)
    out = []
    for _ in range(n):
        out.append(
            {
                "source_row_start": int(rng.integers(0, GRID)),
                "source_col_start": int(rng.integers(0, GRID)),
                "source_row_end": int(rng.integers(0, GRID)),
                "source_col_end": int(rng.integers(0, GRID)),
                "source_strength_kg_per_m2_s": float(rng.uniform(*SOURCE_STRENGTH)),
                "wind_speed_m_per_s": float(rng.uniform(*WIND_SPEED_M_S)),
                "wind_direction_deg": float(rng.uniform(0.0, 360.0)),
            }
        )
    return out


def scenarios_for_patches(patch_ids: Sequence[str], *, seed: int) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """40 tailings and 20 dust scenarios per patch, independent streams per patch."""
    return {
        pid: {
            "tailings": draw_tailings_scenarios(TAILINGS_PER_PATCH, seed=seed, patch_id=pid),
            "dust": draw_dust_scenarios(DUST_PER_PATCH, seed=seed, patch_id=pid),
        }
        for pid in patch_ids
    }


def block_mean(dem: np.ndarray, factor: int) -> np.ndarray:
    """Mean of `factor` x `factor` blocks (1 m DEM to the 8 m cells of the patch)."""
    arr = np.asarray(dem, dtype=np.float64)
    if not isinstance(factor, int | np.integer) or factor < 1:
        raise ValueError(f"factor must be an integer >= 1, got {factor!r}")
    if arr.ndim != 2 or arr.shape[0] % factor or arr.shape[1] % factor:
        raise ValueError(f"a {list(arr.shape)} array is not divisible into {factor} x {factor} blocks")
    if not np.isfinite(arr).all():
        raise ValueError("the DEM contains a non-finite value")
    h, w = arr.shape
    return arr.reshape(h // factor, factor, w // factor, factor).mean(axis=(1, 3))


# ------------------------------------------------------------------ field files (FR-011-41)


@dataclass
class FieldRecord:
    meta: dict[str, Any]
    channels: list[str]
    data: np.ndarray  # float32 [C, ny, nx]


def _reason(error: Any) -> str:
    where = "/".join(str(p) for p in error.path) or "<root>"
    return f"{where}: {error.message}"


def load_field_file(meta_path: str | Path, *, root: str | Path, expected_channels: Sequence[str] | None = None) -> FieldRecord:
    """Validate one field file and return its channels; the payload is read only after the metadata and its digest are valid."""
    try:
        meta = read_metadata(meta_path)
    except RolloutFileError as exc:
        raise FieldFileError(exc.reason) from None
    store = meta.get("store")
    if isinstance(store, dict):
        try:
            check_store_path(store.get("path"))
        except RolloutFileError as exc:
            raise FieldFileError(exc.reason) from None
    errors = sorted(Draft202012Validator(load_schema("field-dataset")).iter_errors(meta), key=lambda e: [str(p) for p in e.path])
    if errors:
        raise FieldFileError(_reason(errors[0]))
    _check_semantics(meta)
    ny, nx = meta["grid"]["ny"], meta["grid"]["nx"]
    if (ny, nx) != (GRID, GRID) and not meta["resolution_transfer"]:
        raise FieldFileError(f"grid: {nx} x {ny} is only admitted when resolution_transfer is true")
    channels = [c["name"] for c in meta["channels"]]
    if expected_channels is not None and tuple(channels) != tuple(expected_channels):
        raise FieldFileError(f"channels: the file holds {channels}, the model expects {list(expected_channels)}")
    payload = Path(root) / meta["store"]["path"]
    if not payload.is_dir():
        raise FieldFileError(f"store/path: payload {meta['store']['path']} does not exist or is not a Zarr directory")
    actual = zarr_digest(payload)
    if actual != meta["store"]["sha256"]:
        raise FieldFileError(f"store/sha256: recorded {meta['store']['sha256']} but the payload digest is {actual}")
    arr = _read_zarr(payload)
    if arr.shape != (len(channels), ny, nx):
        raise FieldFileError(f"payload shape {list(arr.shape)} differs from [channels, ny, nx] = {[len(channels), ny, nx]}")
    if not np.isfinite(arr).all():
        raise FieldFileError("payload holds a non-finite value")
    for i, name in enumerate(channels):
        if name.startswith("depth") and float(arr[i].min()) < DEPTH_FLOOR_M:
            raise FieldFileError(f"channel {name}: a depth below {DEPTH_FLOOR_M} m ({float(arr[i].min())})")
    return FieldRecord(meta=meta, channels=channels, data=arr.astype(np.float32))


def _check_semantics(meta: Mapping[str, Any]) -> None:
    ny, nx = meta["grid"]["ny"], meta["grid"]["nx"]
    scenario = meta["scenario"]
    for key in ("breach_row", "source_row_start", "source_row_end"):
        if key in scenario and not 0 <= scenario[key] < ny:
            raise FieldFileError(f"scenario/{key}: {scenario[key]} lies outside the grid (0 ... {ny - 1}); breach cell")
    for key in ("breach_col", "source_col_start", "source_col_end"):
        if key in scenario and not 0 <= scenario[key] < nx:
            raise FieldFileError(f"scenario/{key}: {scenario[key]} lies outside the grid (0 ... {nx - 1}); breach cell")
    if meta["model"] == "tailings":
        times = meta["output_times_s"]
        expected = [k * meta["t_end_s"] / 8.0 for k in range(1, 9)]
        if len(times) != 8 or not all(math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9) for a, b in zip(times, expected, strict=False)):
            raise FieldFileError(f"output_times_s: must be k T_end / 8 for k = 1 ... 8 ({expected}), got {times}")


def _read_zarr(payload: Path) -> np.ndarray:
    import zarr

    try:
        group = zarr.open_group(str(payload), mode="r")
        return np.asarray(group["data"][:], dtype=np.float32)
    except Exception as exc:
        raise FieldFileError(f"payload unreadable as Zarr: {exc}") from None
