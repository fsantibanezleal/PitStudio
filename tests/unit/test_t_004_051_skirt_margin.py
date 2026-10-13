"""T-004-051 (fix): the terrain range invariant accounts for the skirts that FR-004-07 requires.

Requirements: FR-004-07, FR-004-34.

The first validation of the real Bingham scene failed `terrain_range_excess` (0.05 m at LOD 1, 2.99 m at LOD 2): the
skirts hang `skirt_depth_m` below the boundary vertices (default twice the tile error), so the skirt of a tile that
holds the lowest source cell lies below the source range widened by `max_error_m`. A skirt point may be at most
`max_error_m + skirt_depth_m` below the source minimum; the upper bound is unchanged.

Oracle: a tilted plane whose lowest cells are on the grid border, tiled by the stage code; the expected bounds are the
published ones computed here from the plane's own range and the LOD table.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_studio.scene import terrain  # noqa: E402
from pitstudio_studio.scene.validate import invariants  # noqa: E402

Z0 = 1800.0
LODS = [{"lod": 0, "max_error_m": 0.25, "skirt_depth_m": 0.5}, {"lod": 1, "max_error_m": 1.0, "skirt_depth_m": 2.0}]


def _scene(tmp: Path, *, lo_shift: float = 0.0) -> tuple[Path, dict]:
    """A scene folder with the terrain records of a plane that falls 0.1 m per m towards the west border."""
    x = np.arange(513, dtype=np.float64)
    h = np.tile(0.1 * x, (513, 1))  # site elevations 0 .. 51.2, the minimum on the west border
    ts = terrain.tiles.build_tiles(h, cell_size_m=1.0, x_min_m=-256.0, y_max_m=256.0, lods=LODS)
    (tmp / "layers").mkdir(parents=True)
    (tmp / "terrain" / "grid.zarr").mkdir(parents=True)
    terrain.usd.write_terrain_layer(
        tmp / "layers" / "terrain.usdc", ts, source_id="usgs-3dep-bingham", project="p", epoch=2018, attribution="a"
    )
    (tmp / "terrain" / "tiles.json").write_text(json.dumps(ts.document("0" * 64, "layers/terrain.usdc")), "utf-8")
    source_range = {"min": float(h.min()) + Z0 + lo_shift, "max": float(h.max()) + Z0}
    attrs = {"attributes": {"source_elevation_range_m": source_range}}
    (tmp / "terrain" / "grid.zarr" / "zarr.json").write_text(json.dumps(attrs), "utf-8")
    manifest = {"terrain": {"grid": {"path": "terrain/grid.zarr/zarr.json"}, "tiles": {"path": "terrain/tiles.json"}}}
    return tmp, manifest


@pytest.mark.req("FR-004-07")
def test_skirts_below_the_lowest_cell_are_inside_the_widened_range(tmp_path: Path) -> None:
    scene, manifest = _scene(tmp_path)
    assert invariants._terrain_excess(scene, manifest, Z0) == 0.0


@pytest.mark.req("FR-004-34")
def test_a_surface_point_below_the_range_is_still_reported(tmp_path: Path) -> None:
    scene, manifest = _scene(tmp_path, lo_shift=+10.0)  # the stated minimum is 10 m above the plane's real minimum
    excess = invariants._terrain_excess(scene, manifest, Z0)
    # the skirt hangs below the plane by skirt_depth_m and the allowance is max_error + skirt_depth, so the excess is
    # 10 - max_error at every LOD; the smallest error (LOD 0, 0.25 m) gives the worst case
    assert excess == pytest.approx(9.75, abs=1e-3)
