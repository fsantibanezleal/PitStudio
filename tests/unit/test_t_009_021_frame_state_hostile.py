# ruff: noqa: E501
"""T-009-021 (hostile half) - FR-009-45: stage data that cannot give a valid frame state keeps the frame out of the index.

Oracles (independent of the code under test):
- hand calculation of plan 009 (test strategy row FR-009-45): a stage without `metersPerUnit`, a stage without `upAxis`, a NaN
  transform, a class label outside the frame-state enumeration (the five perception classes of contracts/frame-state.schema.json),
  and a duplicated prim id each give NO frame-state file, no entry in the report's `written` list (= the dataset index) and one
  counted exclusion with its reason; good frames around them are written normally.

Expected public API (module `pitstudio_studio.sdg.frame_state`, package under `studio/src/`; see
tests/contract/test_t_009_021_frame_state_emission.py for `build_frame_state` and `write_frame_state`):

    FrameStateError(ValueError)      .code: str, .frame_id: str | None, .reason: str; str(error) contains code and reason.
        Codes, in the order they are checked: "stage-units-missing" (no "stage" mapping, or metersPerUnit absent, not a real
        number, not finite, <= 0), "stage-axis-missing" (upAxis absent or not exactly "Y" or "Z"), "prim-id-duplicate" (two
        objects with one prim_id; reason contains the id), "class-unknown" (class outside haul_truck, shovel, light_vehicle, person,
        boulder; reason contains the label and the prim id), "transform-non-finite" (a NaN/inf in any object or camera
        translation, rotation or footprint; reason contains the prim id or "camera"), "file-missing" (an image, depth, dust-field or
        terrain file absent under root), "schema" (any other violation of frame-state.schema.json, e.g. an empty object list).
        write_frame_state / build_frame_state raise it; write_frame_state leaves no file and no folder behind.
    Exclusion                        frozen dataclass: frame_id: str | None, code: str, reason: str
    FrameStateReport                 frozen dataclass: written: tuple[dict, ...] ({"frame_id": str, "frame_state": {"path",
                                     "sha256", "size_bytes"}} per written frame, input order), excluded: tuple[Exclusion, ...]
                                     (input order), counts: dict with "written": int, "excluded": int and "by_code": dict[str, int]
    process_frames(frames: Sequence[Mapping], root: pathlib.Path, *, out_dir: str) -> FrameStateReport
        For each frame: write_frame_state(frame, root, f"{out_dir}/{frame_id}.json"); a FrameStateError becomes an Exclusion
        (nothing written, frame kept out of `written`); a frame that is not a mapping or has no usable frame_id is excluded with
        code "schema" and frame_id None. Never raises for a bad frame.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_studio.sdg import frame_state  # noqa: E402

OUT = "sdg/pit/frame_state"
NAN, INF = float("nan"), float("inf")


def _frame(root: Path, frame_id: str = "b2-pit-s0042-f0007") -> dict:
    for rel, seed in (("sdg/pit/rgb/000007.png", 1), ("sdg/pit/depth/000007.npy", 2), ("scenes/b2/terrain.tif", 3)):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(kit.payload(200, seed))
    return {
        "frame_id": frame_id,
        "run_id": "20261012T013000Z-b2",
        "case": "B2",
        "location": "haul_road",
        "condition": "day",
        "stage": {"metersPerUnit": 0.01, "upAxis": "Z"},
        "image": {"path": "sdg/pit/rgb/000007.png", "width_px": 1280, "height_px": 720},
        "depth": {"path": "sdg/pit/depth/000007.npy"},
        "dust_field": None,
        "terrain": {"path": "scenes/b2/terrain.tif"},
        "camera": {
            "intrinsics": {"fx_px": 1108.5, "fy_px": 1108.5, "cx_px": 640.0, "cy_px": 360.0},
            "translation": [0.0, 0.0, 150.0],
            "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
        },
        "objects": [
            {
                "prim_id": "/World/Cube",
                "class": "boulder",
                "translation": [500.0, 0.0, 0.0],
                "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
                "footprint": {"centre": [500.0, 0.0], "half_extents": [50.0, 50.0], "heading_deg": 0.0},
                "visible_px": 1200,
                "in_frustum": True,
            },
            {
                "prim_id": "/World/Truck",
                "class": "haul_truck",
                "translation": [900.0, 100.0, 0.0],
                "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
                "footprint": {"centre": [900.0, 100.0], "half_extents": [300.0, 200.0], "heading_deg": 30.0},
                "visible_px": 5000,
                "in_frustum": True,
            },
        ],
        "bench_edges": [],
    }


def _rejects(frame: dict, root: Path, code: str) -> frame_state.FrameStateError:
    with pytest.raises(frame_state.FrameStateError) as exc:
        frame_state.write_frame_state(frame, root, f"{OUT}/x.json")
    assert exc.value.code == code
    assert code in str(exc.value)
    assert isinstance(exc.value, ValueError)
    assert not (root / OUT).exists()  # no file and no folder
    return exc.value


@pytest.mark.req("FR-009-45")
def test_a_clean_frame_is_written_so_the_fixture_is_sound(tmp_path: Path) -> None:
    entry = frame_state.write_frame_state(_frame(tmp_path), tmp_path, f"{OUT}/ok.json")
    assert (tmp_path / entry["path"]).is_file()


@pytest.mark.req("FR-009-45")
def test_a_stage_without_meters_per_unit_gives_no_frame_state(tmp_path: Path) -> None:
    f = _frame(tmp_path)
    del f["stage"]["metersPerUnit"]
    _rejects(f, tmp_path, "stage-units-missing")


@pytest.mark.req("FR-009-45")
def test_a_stage_without_up_axis_gives_no_frame_state(tmp_path: Path) -> None:
    f = _frame(tmp_path)
    del f["stage"]["upAxis"]
    _rejects(f, tmp_path, "stage-axis-missing")


@pytest.mark.req("FR-009-45")
@pytest.mark.parametrize("stage", [None, {}, "stage", 7, []])
def test_a_missing_or_malformed_stage_reports_the_units_first(tmp_path: Path, stage: object) -> None:
    f = _frame(tmp_path)
    if stage is None:
        del f["stage"]
    else:
        f["stage"] = stage
    _rejects(f, tmp_path, "stage-units-missing")


@pytest.mark.req("FR-009-45")
@pytest.mark.parametrize("mpu", [0.0, -0.01, NAN, INF, "0.01", None, [0.01], True])
def test_an_unusable_meters_per_unit_is_treated_as_missing(tmp_path: Path, mpu: object) -> None:
    f = _frame(tmp_path)
    f["stage"]["metersPerUnit"] = mpu
    _rejects(f, tmp_path, "stage-units-missing")


@pytest.mark.req("FR-009-45")
@pytest.mark.parametrize("axis", ["X", "z", "y", "", None, 1, "ZY"])
def test_an_unusable_up_axis_is_treated_as_missing(tmp_path: Path, axis: object) -> None:
    f = _frame(tmp_path)
    f["stage"]["upAxis"] = axis
    _rejects(f, tmp_path, "stage-axis-missing")


@pytest.mark.req("FR-009-45")
@pytest.mark.parametrize("bad", [NAN, INF, -INF])
@pytest.mark.parametrize(
    "where",
    [
        ("objects", 0, "translation", 1),
        ("objects", 1, "translation", 0),
        ("objects", 0, "rotation_xyzw", 3),
        ("objects", 0, "footprint", "centre", 0),
        ("objects", 0, "footprint", "half_extents", 1),
        ("objects", 0, "footprint", "heading_deg"),
        ("camera", "translation", 2),
        ("camera", "rotation_xyzw", 0),
    ],
)
def test_a_non_finite_transform_gives_no_frame_state_and_names_the_prim(
    tmp_path: Path, bad: float, where: tuple
) -> None:
    f = _frame(tmp_path)
    node = f
    for key in where[:-1]:
        node = node[key]
    node[where[-1]] = bad
    err = _rejects(f, tmp_path, "transform-non-finite")
    expected = "camera" if where[0] == "camera" else f["objects"][where[1]]["prim_id"]
    assert expected in err.reason


@pytest.mark.req("FR-009-45")
@pytest.mark.parametrize("label", ["tractor", "terrain", "Boulder", "", "haul truck", "トラック", None, 5])
def test_a_class_label_outside_the_enumeration_gives_no_frame_state(tmp_path: Path, label: object) -> None:
    f = _frame(tmp_path)
    f["objects"][1]["class"] = label
    err = _rejects(f, tmp_path, "class-unknown")
    assert "/World/Truck" in err.reason


@pytest.mark.req("FR-009-45")
def test_two_objects_sharing_a_prim_id_give_no_frame_state(tmp_path: Path) -> None:
    f = _frame(tmp_path)
    f["objects"][1]["prim_id"] = f["objects"][0]["prim_id"]
    err = _rejects(f, tmp_path, "prim-id-duplicate")
    assert "/World/Cube" in err.reason


@pytest.mark.req("FR-009-45")
def test_a_missing_image_file_gives_no_frame_state(tmp_path: Path) -> None:
    f = _frame(tmp_path)
    (tmp_path / f["image"]["path"]).unlink()
    _rejects(f, tmp_path, "file-missing")


@pytest.mark.req("FR-009-45")
def test_an_empty_object_list_is_a_schema_rejection(tmp_path: Path) -> None:
    f = _frame(tmp_path)
    f["objects"] = []
    _rejects(f, tmp_path, "schema")


@pytest.mark.req("FR-009-45")
def test_with_two_faults_the_earlier_check_names_the_error(tmp_path: Path) -> None:
    f = _frame(tmp_path)
    del f["stage"]["metersPerUnit"]
    del f["stage"]["upAxis"]
    f["objects"][0]["class"] = "tractor"
    _rejects(f, tmp_path, "stage-units-missing")
    f2 = _frame(tmp_path)
    f2["objects"][0]["class"] = "tractor"
    f2["objects"][1]["translation"][0] = NAN
    _rejects(f2, tmp_path, "class-unknown")


@pytest.mark.req("FR-009-45")
def test_the_stage_report_counts_and_keeps_bad_frames_out_of_the_index(tmp_path: Path) -> None:
    good1 = _frame(tmp_path, "f-good-1")
    bad_units = copy.deepcopy(good1)
    bad_units["frame_id"] = "f-bad-units"
    del bad_units["stage"]["metersPerUnit"]
    good2 = copy.deepcopy(good1)
    good2["frame_id"] = "f-good-2"
    bad_class = copy.deepcopy(good1)
    bad_class["frame_id"] = "f-bad-class"
    bad_class["objects"][0]["class"] = "tractor"
    bad_nan = copy.deepcopy(good1)
    bad_nan["frame_id"] = "f-bad-nan"
    bad_nan["objects"][0]["translation"][0] = NAN
    bad_dup = copy.deepcopy(good1)
    bad_dup["frame_id"] = "f-bad-dup"
    bad_dup["objects"][1]["prim_id"] = "/World/Cube"
    report = frame_state.process_frames([good1, bad_units, good2, bad_class, bad_nan, bad_dup], tmp_path, out_dir=OUT)
    assert [w["frame_id"] for w in report.written] == ["f-good-1", "f-good-2"]
    assert [(e.frame_id, e.code) for e in report.excluded] == [
        ("f-bad-units", "stage-units-missing"),
        ("f-bad-class", "class-unknown"),
        ("f-bad-nan", "transform-non-finite"),
        ("f-bad-dup", "prim-id-duplicate"),
    ]
    assert all(e.reason for e in report.excluded)
    assert report.counts["written"] == 2
    assert report.counts["excluded"] == 4
    assert report.counts["by_code"] == {
        "stage-units-missing": 1,
        "class-unknown": 1,
        "transform-non-finite": 1,
        "prim-id-duplicate": 1,
    }
    assert sorted(p.name for p in (tmp_path / OUT).iterdir()) == ["f-good-1.json", "f-good-2.json"]
    for w in report.written:
        assert (tmp_path / w["frame_state"]["path"]).is_file()


@pytest.mark.req("FR-009-45")
@pytest.mark.parametrize("junk", [None, 7, "frame", [], {}, {"frame_id": 5}])
def test_a_frame_that_is_not_a_frame_is_excluded_without_raising(tmp_path: Path, junk: object) -> None:
    good = _frame(tmp_path)
    report = frame_state.process_frames([junk, good], tmp_path, out_dir=OUT)  # type: ignore[list-item]
    assert report.counts["written"] == 1
    assert report.counts["excluded"] == 1
    assert report.excluded[0].code == "schema"
    assert report.excluded[0].frame_id is None


@pytest.mark.req("FR-009-45")
def test_an_all_good_batch_has_no_exclusions(tmp_path: Path) -> None:
    report = frame_state.process_frames([_frame(tmp_path)], tmp_path, out_dir=OUT)
    assert report.excluded == ()
    assert report.counts == {"written": 1, "excluded": 0, "by_code": {}}
    assert frame_state.process_frames([], tmp_path, out_dir=OUT).counts == {"written": 0, "excluded": 0, "by_code": {}}
