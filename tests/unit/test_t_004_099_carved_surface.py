# ruff: noqa: E501, PT018
"""T-004-099: the carved design surface of `st20_pit_design` as a terrain grid and a tiled USD layer.

Requirements: FR-004-50.

Oracles (written here, never the code under test): a flat terrain at a known height and a pit whose levels follow from
the design block (rim 0 m, bench height 12 m, floor -36 m, so the pit centre is at -36 m); the outline step of a flat
terrain at the rim height is at most the drop of one 70 degree face over one cell (tan 70 = 2.747 m per metre); the
terrain-grid contract schema; central differences of the carved array computed with NumPy at the vertex; the planar
`st` rule of FR-004-45 (position / 50 m); the tiling of the source grid from `terrain.tiles.build_tiles`.

Expected API (package `pitstudio_studio.scene.design`, studio environment):
- `design.carved.carve(z_design, windrow_mask, windrow_height_m, terrain, inside) -> float32 array`: the design surface
  inside the outline (plus the windrow height on windrow cells, the top of the design meshes), the terrain outside it
  (nodata stays nodata); a cell inside the outline whose design height is not finite raises `SceneStageError` with
  error class `design-hole` that names the cell count, and nothing is filled.
- `design.carved.outline_step(carved, inside) -> {"pairs", "median_abs_m", "max_abs_m", "mean_signed_m"}` over every pair
  of 4-neighbour cells with one inside and one outside the outline (inside minus outside).
- `build_design` returns a `DesignResult` with `z_carved`, `inside` and `road_mask` arrays of the grid shape and the
  report member `carved_surface {grid_sha256, cells_inside, outline_step_m}` (schema pit-design-report 1.2).
- `design.run(job)` (the stage) writes `design/carved-grid.zarr` (the terrain-grid contract, the source's CRS, extent and
  cell size) and `layers/design-carved.usdc` (variant set `lod` under `/World/Carved`, tile prims named as the source
  tiles, class label `terrain`, normals from the central-difference gradient of the carved grid, planar `primvars:st`
  with a 50 m period, a `road` GeomSubset of the faces whose centroid lies on a road); two runs are bitwise identical.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import design  # noqa: E402
from pitstudio_studio.scene.common import SceneStageError  # noqa: E402
from pitstudio_studio.scene.terrain import tiles as tiles_mod  # noqa: E402

CELL = 1.0
HALF = 130.0  # 260 x 260 cells: 2 x 2 tiles of 257 samples (stride 256)
FLOOR = -36.0
TAN70 = math.tan(math.radians(70.0))
PERIOD_M = 50.0


def _spec():
    return kit.design_spec(h=12.0, alpha=70.0, b=10.0, g=8.0, w=20.0, windrow=2.5, floor_z=FLOOR)


def _outline():
    return kit.regular_polygon(180, 100.0)


@pytest.fixture(scope="module")
def flat_zero():
    """The design of a pit cut into a terrain that is flat at the rim height (0 m)."""
    grid = kit.flat_grid(HALF, CELL, 0.0)
    return grid, design.build_design(grid, _spec(), outline_xy=_outline())


@pytest.fixture(scope="module")
def flat_deep():
    """The same pit in a terrain flat at -100 m, below the pit floor: the carved surface is the design, not min(terrain, design)."""
    grid = kit.flat_grid(HALF, CELL, -100.0)
    return grid, design.build_design(grid, _spec(), outline_xy=_outline())


@pytest.mark.req("FR-004-50")
def test_outside_the_outline_the_carved_surface_is_the_terrain(flat_deep) -> None:
    grid, res = flat_deep
    assert res.z_carved.shape == grid.elevation.shape and res.z_carved.dtype == np.float32
    outside = ~res.inside
    assert outside.sum() > 10_000
    assert np.all(res.z_carved[outside] == -100.0)


@pytest.mark.req("FR-004-50")
def test_inside_the_outline_the_carved_surface_is_the_design_not_the_lower_of_terrain_and_design(flat_deep) -> None:
    _, res = flat_deep
    n = res.z_carved.shape[0]
    centre = res.z_carved[n // 2, n // 2]  # the pit centre sits on the floor bench
    assert centre == pytest.approx(FLOOR, abs=1e-6)
    inside = res.inside
    assert inside.sum() > 25_000
    # every cell inside is within the design levels: the floor below, the rim plus the windrow above
    assert res.z_carved[inside].min() == pytest.approx(FLOOR, abs=1e-6)
    assert res.z_carved[inside].max() <= 0.0 + 2.5 + 1e-6
    assert res.z_carved[inside].max() > -1.0  # the first crest is at the rim, far above the -100 m terrain
    # the old `z_final` (lower of terrain and design) is flat -100 m here; the carved surface must not be it
    assert np.all(res.z_final[inside] <= -100.0 + 2.5 + 1e-6)
    assert np.count_nonzero(res.z_carved[inside] > -99.0) == inside.sum()


@pytest.mark.req("FR-004-50")
def test_the_windrow_cells_stand_the_windrow_height_above_the_design_surface(flat_zero) -> None:
    _, res = flat_zero
    wr = res.windrow_mask & res.inside
    assert wr.sum() > 100
    assert np.allclose(res.z_carved[wr] - res.z_design[wr], 2.5, atol=1e-5)
    plain = res.inside & (res.windrow_raise == 0.0)
    assert np.allclose(res.z_carved[plain], res.z_design[plain], atol=1e-6)


@pytest.mark.req("FR-004-50")
def test_the_outline_step_over_a_terrain_at_the_rim_height_is_at_most_one_cell_of_face(flat_zero) -> None:
    _, res = flat_zero
    step = res.report["carved_surface"]["outline_step_m"]
    perimeter = res.report["outline"]["perimeter_m"]
    assert step["pairs"] >= perimeter  # every metre of outline has at least one inside and one outside neighbour
    # one cell of 70 degree face below the crest, plus the windrow height where a windrow stands at the rim
    assert 0.0 <= step["median_abs_m"] <= step["max_abs_m"] <= TAN70 * CELL + 2.5 + 1e-3
    assert step["median_abs_m"] <= TAN70 * CELL
    assert step["mean_signed_m"] <= 0.0  # the pit is below the terrain: inside minus outside is negative


@pytest.mark.req("FR-004-50")
def test_the_outline_step_over_a_terrain_far_above_the_pit_is_reported_as_the_large_step_it_is(flat_deep) -> None:
    _, res = flat_deep
    step = res.report["carved_surface"]["outline_step_m"]
    # the crest at 0 m against a terrain at -100 m: a step of about +100 m (inside is higher than outside)
    assert 95.0 <= step["median_abs_m"] <= 101.0 and step["max_abs_m"] <= 101.0
    assert step["mean_signed_m"] > 90.0


@pytest.mark.req("FR-004-50")
def test_the_report_carries_the_digest_of_the_carved_array_and_validates_against_the_contract(flat_zero) -> None:
    _, res = flat_zero
    block = res.report["carved_surface"]
    expected = hashlib.sha256(np.ascontiguousarray(res.z_carved, dtype="<f4").tobytes()).hexdigest()
    assert block["grid_sha256"] == expected
    assert block["cells_inside"] == int(res.inside.sum())
    assert kit.schema_errors("pit-design-report.schema.json", res.report) == []


@pytest.mark.req("FR-004-50")
def test_a_cell_inside_the_outline_that_no_design_mesh_covers_fails_with_design_hole_and_is_not_filled() -> None:
    terrain = np.full((6, 6), 5.0, dtype=np.float32)
    inside = np.zeros((6, 6), dtype=bool)
    inside[1:5, 1:5] = True
    z_design = np.full((6, 6), -3.0)
    z_design[~inside] = np.nan
    z_design[2, 3] = np.nan  # one design hole
    z_design[4, 4] = np.nan  # a second one
    with pytest.raises(SceneStageError) as caught:
        design.carved.carve(z_design, np.zeros((6, 6), dtype=bool), 2.5, terrain, inside)
    assert caught.value.error_class == "design-hole"
    assert "2 cell" in str(caught.value)


@pytest.mark.req("FR-004-50")
def test_carve_keeps_terrain_nodata_outside_and_takes_the_design_inside() -> None:
    terrain = np.full((4, 4), 7.0, dtype=np.float32)
    terrain[0, 0] = np.nan
    inside = np.zeros((4, 4), dtype=bool)
    inside[1:3, 1:3] = True
    z_design = np.full((4, 4), np.nan)
    z_design[inside] = [-1.0, -2.0, -3.0, -4.0]
    windrow = np.zeros((4, 4), dtype=bool)
    windrow[1, 1] = True
    out = design.carved.carve(z_design, windrow, 2.5, terrain, inside)
    assert np.isnan(out[0, 0]) and out[0, 1] == 7.0
    assert out[1, 1] == pytest.approx(1.5) and out[1, 2] == -2.0 and out[2, 1] == -3.0 and out[2, 2] == -4.0


@pytest.mark.req("FR-004-50")
def test_the_outline_step_of_a_hand_made_pair_set() -> None:
    carved = np.array([[0.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float32)
    inside = np.zeros((3, 3), dtype=bool)
    inside[1, 1] = True
    step = design.carved.outline_step(carved, inside)
    assert step == {"pairs": 4, "median_abs_m": 10.0, "max_abs_m": 10.0, "mean_signed_m": 10.0}


# ----------------------------------------------------------------------------------------------------------------
# the stage
# ----------------------------------------------------------------------------------------------------------------
def _source_grid(root: Path, elevation: np.ndarray) -> Path:
    import zarr

    folder = root / "terrain" / "grid.zarr"
    attrs = json.loads((kit.EXAMPLES / "terrain-grid.valid.json").read_text(encoding="utf-8"))
    rows, cols = elevation.shape
    attrs.update(rows=rows, cols=cols, x_min_m=-HALF, y_max_m=HALF, cell_size_m=CELL)
    group = zarr.open_group(str(folder), mode="w", zarr_format=3, attributes=attrs)
    for name, array, fill in (
        ("elevation", elevation.astype(np.float32), float("nan")),
        ("valid_mask", np.isfinite(elevation), False),
        ("fill_mask", np.zeros(elevation.shape, dtype=bool), False),
    ):
        arr = group.create_array(name, shape=array.shape, chunks=(128, 128), dtype=array.dtype, fill_value=fill)
        arr[:] = array
    return folder / "zarr.json"


@pytest.fixture(scope="module")
def stage(tmp_path_factory: pytest.TempPathFactory):
    """The stage run twice on a terrain that falls 0.05 m per metre towards +x, with a road-bearing pit."""
    mp = pytest.MonkeyPatch()
    store = tmp_path_factory.mktemp("store")
    mp.setenv("PITSTUDIO_STORE", str(store))
    n = int(2 * HALF)
    xs = -HALF + np.arange(n) * CELL
    elevation = np.tile((-0.05 * xs + 4.0)[None, :], (n, 1))
    zarr_json = _source_grid(store, elevation)
    outline = store / "outline.json"
    outline.write_text(json.dumps(_outline()), encoding="utf-8")
    runs = []
    for k in range(2):
        job = kit.make_job(
            store / f"s{k}",
            "st20_pit_design",
            _spec(),
            [("terrain-grid", zarr_json), ("outline", outline)],
            run_id=f"20261122T0000{k}0Z-carved",
        )
        runs.append((job, design.run(job)))
    yield elevation, runs
    mp.undo()


def _out(job) -> Path:
    return Path(job["output_dir"])


@pytest.mark.req("FR-004-50")
def test_the_stage_succeeds_and_lists_the_carved_outputs(stage) -> None:
    _, runs = stage
    _, run = runs[0]
    assert run.result["status"] == "succeeded", run.result
    names = {o["path"] for o in run.result["outputs"]}
    assert "layers/design-carved.usdc" in names and "design/carved-grid.zarr/zarr.json" in names
    assert "design/carved-grid.zarr/elevation/zarr.json" in names or any(
        n.startswith("design/carved-grid.zarr/elevation") for n in names
    )
    assert "layers/design.usda" in names and "design/pit-design-report.json" in names  # the existing outputs stay


@pytest.mark.req("FR-004-50")
def test_the_carved_grid_keeps_the_crs_extent_and_cell_size_of_the_source_and_validates(stage) -> None:
    elevation, runs = stage
    job, _ = runs[0]
    import zarr

    folder = _out(job) / "design" / "carved-grid.zarr"
    attrs = json.loads((folder / "zarr.json").read_text(encoding="utf-8"))["attributes"]
    source = json.loads((kit.EXAMPLES / "terrain-grid.valid.json").read_text(encoding="utf-8"))
    for key in ("crs", "origin", "frame", "layout", "horizontal_unit", "vertical_unit", "up_axis"):
        assert attrs[key] == source[key], key
    assert (attrs["rows"], attrs["cols"]) == elevation.shape
    assert (attrs["x_min_m"], attrs["y_max_m"], attrs["cell_size_m"]) == (-HALF, HALF, CELL)
    assert kit.schema_errors("terrain-grid.schema.json", attrs) == []
    carved = np.asarray(zarr.open_group(str(folder), mode="r")["elevation"][:], dtype=np.float32)
    digest = hashlib.sha256(np.ascontiguousarray(carved, dtype="<f4").tobytes()).hexdigest()
    assert attrs["arrays"]["elevation"]["sha256"] == digest
    report = json.loads((_out(job) / "design" / "pit-design-report.json").read_text(encoding="utf-8"))
    assert report["carved_surface"]["grid_sha256"] == digest
    # outside the pit the grid is the source terrain; at the pit centre it is the floor
    far = (slice(0, 20), slice(0, 20))
    assert np.array_equal(carved[far], elevation[far].astype(np.float32))
    assert carved[carved.shape[0] // 2, carved.shape[1] // 2] == pytest.approx(FLOOR, abs=1e-6)


def _read_layer(job):
    from pxr import Usd

    return Usd.Stage.Open(str(_out(job) / "layers" / "design-carved.usdc"))


def _tiles(stage_, lod: int):
    from pxr import Usd, UsdGeom

    root = stage_.GetPrimAtPath(f"/World/Carved/Lod{lod}")
    return [p for p in Usd.PrimRange(root) if p.IsA(UsdGeom.Mesh)]


def _select_lod(prim_stage, lod: int) -> None:
    prim_stage.GetPrimAtPath("/World/Carved").GetVariantSet("lod").SetVariantSelection(f"lod{lod}")


@pytest.mark.req("FR-004-50")
def test_the_layer_has_the_source_tiling_in_every_lod_variant(stage) -> None:
    elevation, runs = stage
    job, _ = runs[0]
    lods = _spec()["terrain"]["lods"]
    layer = _read_layer(job)
    prim = layer.GetPrimAtPath("/World/Carved")
    assert prim.IsValid() and layer.GetDefaultPrim().GetName() == "World"
    vset = prim.GetVariantSet("lod")
    assert sorted(vset.GetVariantNames()) == [f"lod{lod['lod']}" for lod in lods]
    source = tiles_mod.build_tiles(
        elevation.astype(np.float64),
        cell_size_m=CELL,
        x_min_m=-HALF,
        y_max_m=HALF,
        lods=lods,
    )
    for lod in lods:
        _select_lod(layer, lod["lod"])
        got = sorted(p.GetName() for p in _tiles(layer, lod["lod"]))
        want = sorted(t.prim.rsplit("/", 1)[1] for t in source.tiles if t.lod == lod["lod"])
        assert got == want and len(got) == 4


@pytest.mark.req("FR-004-50")
def test_every_vertex_of_the_layer_is_on_the_carved_grid_or_on_its_skirt(stage) -> None:
    import zarr
    from pxr import UsdSemantics

    _, runs = stage
    job, _ = runs[0]
    carved = np.asarray(
        zarr.open_group(str(_out(job) / "design" / "carved-grid.zarr"), mode="r")["elevation"][:], dtype=np.float64
    )
    layer = _read_layer(job)
    lod0 = _spec()["terrain"]["lods"][0]
    _select_lod(layer, lod0["lod"])
    meshes = _tiles(layer, lod0["lod"])
    assert meshes
    for prim in meshes:
        pts = np.asarray(prim.GetAttribute("points").Get(), dtype=np.float64)
        col = np.rint((pts[:, 0] + HALF) / CELL).astype(int)
        row = np.rint((HALF - pts[:, 1]) / CELL).astype(int)
        assert np.allclose(pts[:, 0], -HALF + col * CELL) and np.allclose(pts[:, 1], HALF - row * CELL)
        z = carved[row, col]
        on_surface = np.abs(pts[:, 2] - z) < 1e-3
        on_skirt = np.abs(pts[:, 2] - (z - lod0["skirt_depth_m"])) < 1e-3
        assert np.all(on_surface | on_skirt), prim.GetPath()
        assert on_surface.sum() > 4
        assert list(UsdSemantics.LabelsAPI(prim, "class").GetLabelsAttr().Get()) == ["terrain"]


@pytest.mark.req("FR-004-50")
def test_vertex_normals_are_the_central_difference_gradient_of_the_carved_grid_and_st_is_planar(stage) -> None:
    import zarr

    _, runs = stage
    job, _ = runs[0]
    carved = np.asarray(
        zarr.open_group(str(_out(job) / "design" / "carved-grid.zarr"), mode="r")["elevation"][:], dtype=np.float64
    )
    layer = _read_layer(job)
    lod0 = _spec()["terrain"]["lods"][0]["lod"]
    _select_lod(layer, lod0)
    checked = 0
    for prim in _tiles(layer, lod0):
        pts = np.asarray(prim.GetAttribute("points").Get(), dtype=np.float64)
        normals = np.asarray(prim.GetAttribute("normals").Get(), dtype=np.float64)
        st = prim.GetAttribute("primvars:st")
        assert st.IsValid() and st.GetMetadata("interpolation") == "vertex"
        st_values = np.asarray(st.Get(), dtype=np.float64)
        assert np.allclose(st_values, pts[:, :2] / PERIOD_M, atol=1e-5)
        col = np.rint((pts[:, 0] + HALF) / CELL).astype(int)
        row = np.rint((HALF - pts[:, 1]) / CELL).astype(int)
        inner = (col > 1) & (col < carved.shape[1] - 2) & (row > 1) & (row < carved.shape[0] - 2)
        dzdx = (carved[row[inner], col[inner] + 1] - carved[row[inner], col[inner] - 1]) / (2 * CELL)
        dzdy = (carved[row[inner] - 1, col[inner]] - carved[row[inner] + 1, col[inner]]) / (2 * CELL)  # row 0 is north
        want = np.stack([-dzdx, -dzdy, np.ones_like(dzdx)], axis=1)
        want /= np.linalg.norm(want, axis=1, keepdims=True)
        assert np.allclose(normals[inner], want, atol=2e-5)
        checked += int(inner.sum())
    assert checked > 5_000


@pytest.mark.req("FR-004-50")
def test_faces_whose_centroid_lies_on_a_road_form_a_road_subset(stage) -> None:
    from pxr import UsdGeom

    _, runs = stage
    job, _ = runs[0]
    layer = _read_layer(job)
    lod0 = _spec()["terrain"]["lods"][0]["lod"]
    _select_lod(layer, lod0)
    total = 0
    for prim in _tiles(layer, lod0):
        subsets = UsdGeom.Subset.GetGeomSubsets(UsdGeom.Imageable(prim), "face", "materialBind")
        for subset in subsets:
            assert subset.GetPrim().GetName() == "road"
            idx = np.asarray(subset.GetIndicesAttr().Get(), dtype=np.int64)
            counts = np.asarray(UsdGeom.Mesh(prim).GetFaceVertexCountsAttr().Get())
            assert idx.size and idx.max() < counts.size and np.all(np.diff(idx) > 0)
            total += idx.size
    assert total > 500  # the pit has a ramp 20 m wide and a road on every berm


@pytest.mark.req("FR-004-50")
def test_two_runs_write_identical_bytes(stage) -> None:
    _, runs = stage
    (_, first), (_, second) = runs
    assert first.digests == second.digests
    assert "layers/design-carved.usdc" in first.digests


@pytest.mark.req("FR-004-50")
def test_the_road_mask_covers_the_ramp_centreline_and_not_a_far_corner(flat_zero) -> None:
    _, res = flat_zero
    assert res.road_mask.shape == res.z_carved.shape and res.road_mask.dtype == bool
    xs = -HALF + (np.arange(res.road_mask.shape[1]) + 0.5) * CELL
    ys = HALF - (np.arange(res.road_mask.shape[0]) + 0.5) * CELL
    for x, y, _ in res.ramp.centreline[::25]:
        c, r = int(np.argmin(np.abs(xs - x))), int(np.argmin(np.abs(ys - y)))
        assert res.road_mask[r, c], (x, y)
    assert not res.road_mask[:10, :10].any()
