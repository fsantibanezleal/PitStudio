"""T-017-046 (GPU): smoke run of the real COLMAP and Brush binaries on a tiny synthetic scene (gpu).

Requirements: FR-017-37, FR-017-38.

Spec: specs/017-planning-survey/spec.md FR-017-37 (COLMAP 4.2.1 sparse reconstruction, Umeyama alignment to the
true camera
centres, dense stereo and fusion, per-cell median surface at 0.25 m) and FR-017-38 (Brush v0.3.0 splat; opaque
Gaussian
means gridded by per-cell median). plan.md: "unit (fake tools) + gpu" for FR-017-37 / FR-017-38.

Marked `gpu`: it needs a CUDA device and the pinned binaries, so it is not run in CI and not run by the red author
(the GPU
belongs to the scheduled jobs and to the runner's locks, FR-017-50). The two binaries are located through the
environment
variables `PITSTUDIO_COLMAP` and `PITSTUDIO_BRUSH` (paths of the portable executables whose SHA-256 the recipe pins).

Oracle: a procedurally textured horizontal plane (z = 0) rendered by the test with the pinhole equations from 8 nadir
cameras at 10 m altitude on a 2 x 4 grid with ~70 % overlap; the true camera centres are the render positions; the
plane
has the known height 0, so the reconstructed photogrammetric surface must have a per-cell median within 0.05 m of 0
(the
alignment to the true centres fixes scale, so a metric height is meaningful) on the cells it covers, with at least
half of
the cells of the central area covered. The tool versions are read from the binaries (`--version`).

Expected public API (module `pitstudio_studio.survey.colmap` and `.brush`, `studio/` environment; see
tests/unit/test_t_017_046_reconstruction.py for `reconstruct` and `train_splat`):
    colmap_version(colmap: Sequence[str]) -> str       # "4.2.1"
    brush_version(brush: Sequence[str]) -> str         # "0.3.0"
"""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
from pitstudio_studio.survey.brush import brush_version, train_splat
from pitstudio_studio.survey.colmap import colmap_version, reconstruct

pytestmark = pytest.mark.gpu

W, H, F = 640, 480, 600.0
ALTITUDE = 10.0
CELL = 0.25


def _png(path: Path, gray: np.ndarray) -> None:
    raw = b"".join(b"\x00" + gray[r].astype(np.uint8).tobytes() for r in range(gray.shape[0]))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", gray.shape[1], gray.shape[0], 8, 0, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


def _texture(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """A deterministic multi-scale value-noise texture of the plane coordinates (metres), values in 0 .. 255."""
    out = np.zeros_like(x)
    for scale, weight, seed in ((0.05, 0.5, 1), (0.13, 0.3, 2), (0.4, 0.2, 3)):
        lattice = np.random.default_rng(seed).random((512, 512))
        u, v = (x / scale) % 510, (y / scale) % 510
        i, j = u.astype(int), v.astype(int)
        fu, fv = u - i, v - j
        top = lattice[j, i] * (1 - fu) + lattice[j, i + 1] * fu
        bottom = lattice[j + 1, i] * (1 - fu) + lattice[j + 1, i + 1] * fu
        out += weight * (top * (1 - fv) + bottom * fv)
    return 255 * out


def _render_scene(folder: Path) -> dict[str, list[float]]:
    folder.mkdir(parents=True, exist_ok=True)
    centres: dict[str, list[float]] = {}
    u, v = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    k = 0
    for iy in range(2):
        for ix in range(4):
            cx, cy = 8.0 + ix * 4.5, 8.0 + iy * 5.5
            x = cx + (u - W / 2) / F * ALTITUDE
            y = cy - (v - H / 2) / F * ALTITUDE
            name = f"img_{k:04d}.png"
            _png(folder / name, _texture(x, y))
            centres[name] = [cx, cy, ALTITUDE]
            k += 1
    return centres


def _launcher(env_name: str) -> list[str]:
    path = os.environ.get(env_name)
    if not path:
        pytest.fail(f"{env_name} must name the pinned executable (set it in the GPU job environment)")
    return [path]


@pytest.mark.req("FR-017-37")
def test_the_pinned_tool_versions_are_read_from_the_binaries() -> None:
    assert colmap_version(_launcher("PITSTUDIO_COLMAP")).startswith("4.2.1")
    assert brush_version(_launcher("PITSTUDIO_BRUSH")).lstrip("v").startswith("0.3.0")


@pytest.mark.req("FR-017-37")
def test_colmap_reconstructs_a_textured_plane_to_height_zero_within_5_cm(tmp_path: Path) -> None:
    centres = _render_scene(tmp_path / "images")
    rec = reconstruct(
        tmp_path / "images", tmp_path / "work", colmap=_launcher("PITSTUDIO_COLMAP"), true_centres=centres,
        origin_xy=(10.0, 8.0), cell_m=CELL, shape=(32, 40),
    )  # fmt: skip
    assert rec.n_images_registered >= 6
    centre = rec.surface[8:24, 10:30]  # the central part of the 10 m x 8 m area, well inside the overlap of all cameras
    covered = np.isfinite(centre)
    assert covered.mean() >= 0.5
    assert abs(float(np.median(centre[covered]))) <= 0.05  # the plane has height 0


@pytest.mark.req("FR-017-38")
def test_brush_trains_a_splat_from_the_colmap_output_and_its_surface_is_close_to_the_plane(tmp_path: Path) -> None:
    centres = _render_scene(tmp_path / "images")
    rec = reconstruct(
        tmp_path / "images", tmp_path / "work", colmap=_launcher("PITSTUDIO_COLMAP"), true_centres=centres,
        origin_xy=(10.0, 8.0), cell_m=CELL, shape=(32, 40),
    )  # fmt: skip
    splat = train_splat(
        tmp_path / "work", tmp_path / "splat", brush=_launcher("PITSTUDIO_BRUSH"), alignment=rec.alignment,
        origin_xy=(10.0, 8.0), cell_m=CELL, shape=(32, 40),
    )  # fmt: skip
    assert splat.n_opaque > 0
    covered = np.isfinite(splat.surface[8:24, 10:30])
    assert covered.mean() >= 0.25
    assert (
        abs(float(np.median(splat.surface[8:24, 10:30][covered]))) <= 0.25
    )  # a splat surface is coarser than COLMAP's
