"""Stage `st10_terrain` (spec 004, section 3.1): real DEM and lidar terrain in the site-local frame, RTIN tiles, USD
layer."""

from pitstudio_studio.scene.common import SceneStageError
from pitstudio_studio.scene.terrain import frame, grid, rtin, sources, tiles, usd
from pitstudio_studio.scene.terrain import io as io
from pitstudio_studio.scene.terrain.build import (
    SiteName,
    TerrainBuild,
    TerrainGrid,
    build_terrain,
    build_terrain_grid,
    check_terrain_sources,
    confirm_site_name,
    run,
    write_grid_zarr,
)

__all__ = [
    "SceneStageError",
    "SiteName",
    "TerrainBuild",
    "TerrainGrid",
    "build_terrain",
    "build_terrain_grid",
    "check_terrain_sources",
    "confirm_site_name",
    "frame",
    "grid",
    "io",
    "rtin",
    "run",
    "sources",
    "tiles",
    "usd",
    "write_grid_zarr",
]
