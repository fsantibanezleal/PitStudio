# ruff: noqa: PT018
"""T-004-018: optional McKinley and Hambach terrain sources; "not run (<reason>)" without key or data.

Requirements: FR-004-09.

Oracle: hand-written expected records (plan.md "FR-004-09": the expected "not run" record when the key is absent, a
fixture for the enabled case); metamorphic relation: enabling an optional source that does not run leaves the Bingham
grid bit-identical.

Expected API (package `pitstudio_studio.scene.terrain`, studio environment):
- `terrain.sources.resolve_sources(spec, *, env, available) -> list[SourceStatus]`: one entry per source listed in
  `spec["terrain"]["sources"]`, in that order; `available` maps a source id to the list of fetched data files present;
  `env` is the environment mapping. `SourceStatus` has `id`, `status` (`"used"` or `"not_run"`, the DC-004-02
  `sources[].status` values) and `reason` (None when used). A source with `optional: true` is used only when its data is
  present and, for `ot-mckinley-2023`, the environment variable `OPENTOPOGRAPHY_API_KEY` holds a non-empty value;
  `nrw-hambach-dgm1` needs no key. Otherwise it is `not_run` with a one-line reason that names the missing key
  (McKinley) or the missing data; the reason never contains the key's value.
- `terrain.build_terrain(spec, inputs, *, env=None) -> TerrainBuild` with `.sources` (the list above) and `.grids`
  (source id -> `TerrainGrid`, for the sources that ran, by the same rules as `build_terrain_grid`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import terrain  # noqa: E402

BINGHAM, MCKINLEY, HAMBACH = "usgs-3dep-bingham", "ot-mckinley-2023", "nrw-hambach-dgm1"
KEY = "s3cr3t-key-0123456789"


def _spec(*optional: str) -> dict:
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 9.0, 9.0)
    for sid, kind in ((MCKINLEY, "laz"), (HAMBACH, "dem")):
        if sid in optional:
            spec["terrain"]["sources"].append(
                {"id": sid, "kind": kind, "project": f"{sid} project", "epoch": 2023, "optional": True}
            )
    return spec


def _dem(tmp: Path, name: str) -> Path:
    z = kit.Z0 + np.arange(81, dtype=np.float64).reshape(9, 9)
    return kit.write_dem(tmp / name, z, x_min=kit.E0, y_max=kit.N0 + 9, cell=1.0, wkt=kit.crs_wkt("utm12-m"))


def _laz(tmp: Path, name: str) -> Path:
    rng = np.random.default_rng(3)
    n = 3000
    return kit.write_laz(
        tmp / name,
        kit.E0 + rng.uniform(0, 9, n),
        kit.N0 + rng.uniform(0, 9, n),
        kit.Z0 + rng.uniform(0, 5, n),
        np.full(n, 2, np.uint8),
    )


@pytest.mark.req("FR-004-09")
def test_only_sources_listed_in_the_spec_are_resolved(tmp_path: Path) -> None:
    out = terrain.sources.resolve_sources(_spec(), env={}, available={BINGHAM: [_dem(tmp_path, "b.tif")]})
    assert [(s.id, s.status, s.reason) for s in out] == [(BINGHAM, "used", None)]


@pytest.mark.req("FR-004-09")
def test_mckinley_without_a_key_is_not_run_and_the_reason_names_the_key(tmp_path: Path) -> None:
    out = terrain.sources.resolve_sources(
        _spec(MCKINLEY), env={}, available={BINGHAM: [_dem(tmp_path, "b.tif")], MCKINLEY: [_laz(tmp_path, "m.laz")]}
    )
    by_id = {s.id: s for s in out}
    assert by_id[BINGHAM].status == "used"
    assert by_id[MCKINLEY].status == "not_run"
    assert "key" in by_id[MCKINLEY].reason.lower() and "opentopography" in by_id[MCKINLEY].reason.lower()
    assert 0 < len(by_id[MCKINLEY].reason) <= 256 and "\n" not in by_id[MCKINLEY].reason  # DC-004-02 reason bounds


@pytest.mark.req("FR-004-09")
@pytest.mark.parametrize("env", [{"OPENTOPOGRAPHY_API_KEY": ""}, {"OPENTOPOGRAPHY_API_KEY": "   "}, {"OTHER": KEY}])
def test_an_empty_or_misnamed_key_does_not_count(tmp_path: Path, env: dict[str, str]) -> None:
    out = terrain.sources.resolve_sources(
        _spec(MCKINLEY), env=env, available={BINGHAM: [_dem(tmp_path, "b.tif")], MCKINLEY: [_laz(tmp_path, "m.laz")]}
    )
    assert {s.id: s.status for s in out}[MCKINLEY] == "not_run"


@pytest.mark.req("FR-004-09")
def test_mckinley_with_key_and_data_is_used_and_the_key_is_never_recorded(tmp_path: Path) -> None:
    avail = {BINGHAM: [_dem(tmp_path, "b.tif")], MCKINLEY: [_laz(tmp_path, "m.laz")]}
    out = terrain.sources.resolve_sources(_spec(MCKINLEY), env={"OPENTOPOGRAPHY_API_KEY": KEY}, available=avail)
    assert {s.id: s.status for s in out} == {BINGHAM: "used", MCKINLEY: "used"}
    assert KEY not in repr(out)
    # key present, data absent: still not run, and the reason now says the data is missing
    out = terrain.sources.resolve_sources(
        _spec(MCKINLEY), env={"OPENTOPOGRAPHY_API_KEY": KEY}, available={BINGHAM: avail[BINGHAM]}
    )
    miss = {s.id: s for s in out}[MCKINLEY]
    assert miss.status == "not_run" and "data" in miss.reason.lower() and KEY not in miss.reason


@pytest.mark.req("FR-004-09")
def test_hambach_needs_no_key_only_data(tmp_path: Path) -> None:
    spec = _spec(HAMBACH)
    with_data = terrain.sources.resolve_sources(
        spec, env={}, available={BINGHAM: [_dem(tmp_path, "b.tif")], HAMBACH: [_dem(tmp_path, "h.tif")]}
    )
    assert {s.id: s.status for s in with_data} == {BINGHAM: "used", HAMBACH: "used"}
    without = terrain.sources.resolve_sources(spec, env={}, available={BINGHAM: [_dem(tmp_path, "b.tif")]})
    h = {s.id: s for s in without}[HAMBACH]
    assert h.status == "not_run" and "data" in h.reason.lower()


@pytest.mark.req("FR-004-09")
def test_unavailable_optional_source_still_completes_the_bingham_terrain(tmp_path: Path) -> None:
    dem = _dem(tmp_path, "b.tif")
    plain = terrain.build_terrain(_spec(), {BINGHAM: [dem]}, env={})
    with_optional = terrain.build_terrain(_spec(MCKINLEY, HAMBACH), {BINGHAM: [dem]}, env={})
    assert sorted(with_optional.grids) == [BINGHAM]
    assert {s.id: s.status for s in with_optional.sources} == {BINGHAM: "used", MCKINLEY: "not_run", HAMBACH: "not_run"}
    assert all(s.reason for s in with_optional.sources if s.status == "not_run")
    assert with_optional.grids[BINGHAM].elevation.tobytes() == plain.grids[BINGHAM].elevation.tobytes()


@pytest.mark.req("FR-004-09")
def test_enabled_optional_sources_are_processed_with_the_same_rules(tmp_path: Path) -> None:
    spec = _spec(MCKINLEY, HAMBACH)
    inputs = {
        BINGHAM: [_dem(tmp_path, "b.tif")],
        MCKINLEY: [_laz(tmp_path, "m.laz")],
        HAMBACH: [_dem(tmp_path, "h.tif")],
    }
    build = terrain.build_terrain(spec, inputs, env={"OPENTOPOGRAPHY_API_KEY": KEY})
    assert sorted(build.grids) == sorted([BINGHAM, MCKINLEY, HAMBACH])
    np.testing.assert_array_equal(
        build.grids[HAMBACH].elevation, build.grids[BINGHAM].elevation
    )  # same DEM, same rules
    assert build.grids[MCKINLEY].elevation.shape == (9, 9)
    assert build.grids[MCKINLEY].counts["valid_cells"] > 0
