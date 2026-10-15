# ruff: noqa: E501
"""T-004-051: scene invariants, each violated once by a hand-made fixture.

Requirements: FR-004-35.

Oracle: the composed fixture scene (hand-written upstream layers and the contract-example design report, whose numbers
are the expected measures: bench height deviation 0.2 m, face angle deviation 0.4 deg, ramp 8.06 %, windrow margin
2.5 - 1.6 = 0.9 m, residual 2.3e-16), one hand-made defect per invariant (wrong units, unlabelled prim, steep ramp, low
windrow, ...), expected measures computed by hand in each case (plan.md "FR-004-35"); the invariant records are validated
against the DC-004-07 draft schema, which also fixes their units, limits and comparisons.

Expected API (package `pitstudio_studio.scene.validate`, studio environment): `validate.compute_invariants(scene_dir,
spec) -> dict` for a scene folder written by `compose.compose_scene` (test_t_004_040; the design report at
`design/pit-design-report.json`, the terrain grid attributes at `terrain/grid.zarr/zarr.json` and the tile index at
`terrain/tiles.json` are read from the folder). It returns the 14 invariants of the DC-004-07 `invariants` object, each
`{measured, unit, limit, comparison, passed}`:
- `layer_units_axis`: number of manifest layers whose `upAxis`, `metersPerUnit` or `kilogramsPerUnit` is wrong or unauthored;
- `class_label_coverage`: share of geometry prims (over all lod selections) with exactly one class label;
- `time_sampled_labels`: label attributes with time samples; `articulation_roots`: machine layers (manifest role `asset`)
  without exactly one articulation root; `cyclic_joint_graphs`: machine layers whose joint graph is not a tree;
  `non_positive_masses`: bodies with mass <= 0;
- `bench_height_deviation`: largest |bench `height_m` - H| in the design report (m); `face_angle_deviation`: largest
  |`face_angle_deg` - alpha| (deg); `ramp_grade_max`: `ramp.max_grade_pct` against the limit g + 0.1; `windrow_margin`:
  `windrows.height_m - windrows.mid_axle_height_m` (m, `ge` 0); `cut_fill_identity_residual`: `volumes.identity_residual_rel`;
- `terrain_range_excess`: largest excess (m) of a terrain mesh point's absolute elevation (site z + z0) over the grid's
  `source_elevation_range_m` widened by the tile's `max_error_m`; `forbidden_paths`: forbidden asset paths in any layer;
  `layer_size_max`: size in bytes of the largest small `.usda` layer (limit 10,000,000).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import compose, validate  # noqa: E402

NAMES = [
    "layer_units_axis",
    "class_label_coverage",
    "time_sampled_labels",
    "articulation_roots",
    "cyclic_joint_graphs",
    "non_positive_masses",
    "bench_height_deviation",
    "face_angle_deviation",
    "ramp_grade_max",
    "windrow_margin",
    "terrain_range_excess",
    "cut_fill_identity_residual",
    "forbidden_paths",
    "layer_size_max",
]
EXAMPLE = json.loads((kit.EXAMPLES / "scene-validation-report.valid.json").read_text(encoding="utf-8"))["invariants"]


def _spec() -> dict:
    spec = kit.scene_spec()
    spec["variants"] = {
        "pushback": ["pb0"],
        "scenario": ["baseline"],
        "time_of_day": ["noon"],
        "weather": ["clear"],
        "lod": ["lod0", "lod1", "lod2"],
    }
    return spec


def _scene(tmp: Path) -> tuple[dict, Path]:
    spec = _spec()
    out = tmp / "scene"
    compose.compose_scene(spec, kit.fixture_upstream(tmp / "up"), out)
    return spec, out


def _json_edit(path: Path, edit) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    edit(doc)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _stage_edit(path: Path, edit) -> None:
    from pxr import Usd

    stage = Usd.Stage.Open(str(path))
    edit(stage)
    stage.GetRootLayer().Save()


def _check_shape(inv: dict) -> None:
    assert sorted(inv) == sorted(NAMES)
    report = json.loads((kit.EXAMPLES / "scene-validation-report.valid.json").read_text(encoding="utf-8"))
    report["invariants"] = inv
    assert kit.schema_errors("scene-validation-report.schema.json", report) == []  # also checks measured vs passed
    for name in NAMES:  # units, comparisons and fixed limits are those of the contract
        assert (inv[name]["unit"], inv[name]["comparison"]) == (EXAMPLE[name]["unit"], EXAMPLE[name]["comparison"])
        if name != "ramp_grade_max":
            assert inv[name]["limit"] == EXAMPLE[name]["limit"]
    assert inv["ramp_grade_max"]["limit"] == pytest.approx(8.1)  # g + 0.1 % with g = 8 %


@pytest.mark.req("FR-004-35")
def test_intact_scene_passes_every_invariant_with_the_expected_measures(tmp_path: Path) -> None:
    spec, scene = _scene(tmp_path)
    inv = validate.compute_invariants(scene, spec)
    _check_shape(inv)
    assert all(inv[n]["passed"] is True for n in NAMES), {n: inv[n] for n in NAMES if not inv[n]["passed"]}
    for n in (
        "layer_units_axis",
        "time_sampled_labels",
        "articulation_roots",
        "cyclic_joint_graphs",
        "non_positive_masses",
        "forbidden_paths",
    ):
        assert inv[n]["measured"] == 0
    assert inv["class_label_coverage"]["measured"] == 1.0
    assert inv["bench_height_deviation"]["measured"] == pytest.approx(0.2, abs=1e-9)
    assert inv["face_angle_deviation"]["measured"] == pytest.approx(0.4, abs=1e-9)
    assert inv["ramp_grade_max"]["measured"] == pytest.approx(8.06, abs=1e-9)
    assert inv["windrow_margin"]["measured"] == pytest.approx(0.9, abs=1e-9)
    assert inv["terrain_range_excess"]["measured"] == 0.0
    assert inv["cut_fill_identity_residual"]["measured"] == pytest.approx(2.3e-16, rel=1e-9)
    small = ["root.usda", *(f"layers/{n}.usda" for n in ("anim", "sensors", "weather", "lights", "fleet", "design"))]
    assert inv["layer_size_max"]["measured"] == max((scene / p).stat().st_size for p in small)


def _units(scene: Path) -> None:
    from pxr import Sdf

    layer = Sdf.Layer.FindOrOpen(str(scene / "layers" / "design.usda"))
    layer.pseudoRoot.SetInfo("metersPerUnit", 0.01)
    layer.Save()


def _unlabelled(scene: Path) -> None:
    from pxr import UsdGeom

    def edit(stage) -> None:
        mesh = UsdGeom.Mesh.Define(stage, "/World/Design/Unlabelled")
        mesh.CreatePointsAttr([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
        mesh.CreateFaceVertexCountsAttr([3, 3])
        mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 0, 2, 3])

    _stage_edit(scene / "layers" / "design.usda", edit)


def _two_labels(scene: Path) -> None:
    from pxr import UsdSemantics

    _stage_edit(
        scene / "layers" / "design.usda",
        lambda st: (
            UsdSemantics.LabelsAPI(st.GetPrimAtPath("/World/Design/Bench_00"), "class")
            .GetLabelsAttr()
            .Set(["bench", "berm"])
        ),
    )


def _time_sampled(scene: Path) -> None:
    from pxr import UsdSemantics, Vt

    def edit(stage) -> None:
        attr = UsdSemantics.LabelsAPI(stage.GetPrimAtPath("/World/Design/Bench_00"), "class").GetLabelsAttr()
        attr.Set(Vt.TokenArray(["bench"]), 1.0)
        attr.Set(Vt.TokenArray(["bench"]), 2.0)

    _stage_edit(scene / "layers" / "design.usda", edit)


def _machine(**kw) -> object:
    def apply(scene: Path) -> None:
        path = scene / "assets" / "truck.usda"
        path.unlink()
        kit.write_machine_asset(path, **kw)

    return apply


def _report(edit) -> object:
    return lambda scene: _json_edit(scene / "design" / "pit-design-report.json", edit)


def _terrain_high(scene: Path) -> None:
    def edit(stage) -> None:
        vset = stage.GetPrimAtPath("/World/Terrain").GetVariantSet("lod")
        vset.SetVariantSelection("lod0")
        with vset.GetVariantEditContext():
            stage.GetPrimAtPath("/World/Terrain/Lod0/Tile_0_0_0_0").GetAttribute("points").Set(
                [(0.0, 0.0, 3000.0), (100.0, 0.0, 0.0), (100.0, 100.0, 0.0), (0.0, 100.0, 0.0)]
            )

    _stage_edit(scene / "layers" / "terrain.usdc", edit)


def _forbidden(scene: Path) -> None:
    from pxr import Sdf

    _stage_edit(
        scene / "layers" / "design.usda",
        lambda st: (
            st.GetPrimAtPath("/World/Design/Bench_00")
            .CreateAttribute("pitstudio:testfile", Sdf.ValueTypeNames.Asset)
            .Set(Sdf.AssetPath("http://example.org/x.png"))
        ),
    )


def _oversize(scene: Path) -> None:
    from pxr import Sdf

    layer = Sdf.Layer.FindOrOpen(str(scene / "layers" / "design.usda"))
    layer.documentation = "x" * 10_000_100
    layer.Save()


def _bench(edit) -> object:
    return _report(lambda doc: edit(doc["benches"]))


CASES = [
    ("layer_units_axis", _units, 1, None),
    ("class_label_coverage", _unlabelled, 0.75, None),
    ("class_label_coverage", _two_labels, 2 / 3, None),  # 3 prims per lod, one of them with two labels
    ("time_sampled_labels", _time_sampled, None, None),
    ("articulation_roots", _machine(roots=0), 1, None),
    ("articulation_roots", _machine(roots=2), 1, None),
    ("cyclic_joint_graphs", _machine(cycle=True), 1, None),
    ("non_positive_masses", _machine(masses=(0.0, 50000.0)), 1, None),
    ("non_positive_masses", _machine(masses=(112000.0, -5.0)), 1, None),
    ("bench_height_deviation", _bench(lambda b: b[1].update(height_m=15.8)), 0.8, 1e-9),
    ("face_angle_deviation", _bench(lambda b: b[0].update(face_angle_deg=71.5)), 1.5, 1e-9),
    ("ramp_grade_max", _report(lambda d: d["ramp"].update(max_grade_pct=9.0)), 9.0, 1e-9),
    ("windrow_margin", _report(lambda d: d["windrows"].update(height_m=1.0)), -0.6, 1e-9),
    ("terrain_range_excess", _terrain_high, 2389.5, 1e-3),  # 1800 + 3000 - (2410.25 + 0.25)
    ("cut_fill_identity_residual", _report(lambda d: d["volumes"].update(identity_residual_rel=1e-6)), 1e-6, 1e-12),
    ("forbidden_paths", _forbidden, 1, None),
    ("layer_size_max", _oversize, None, None),
]


@pytest.mark.req("FR-004-35")
@pytest.mark.parametrize(("name", "defect", "measured", "tol"), CASES, ids=[f"{c[0]}-{i}" for i, c in enumerate(CASES)])
def test_each_invariant_fails_when_its_own_defect_is_introduced_and_no_other_does(
    tmp_path: Path, name: str, defect, measured, tol
) -> None:
    spec, scene = _scene(tmp_path)
    defect(scene)
    inv = validate.compute_invariants(scene, spec)
    _check_shape(inv)
    assert inv[name]["passed"] is False, inv[name]
    assert [n for n in NAMES if not inv[n]["passed"]] == [name], {n: inv[n]["passed"] for n in NAMES}
    if measured is not None:
        assert inv[name]["measured"] == pytest.approx(measured, abs=tol or 1e-9)
    if name == "time_sampled_labels":
        assert inv[name]["measured"] >= 1
    if name == "layer_size_max":
        assert inv[name]["measured"] == (scene / "layers" / "design.usda").stat().st_size > 10_000_000
