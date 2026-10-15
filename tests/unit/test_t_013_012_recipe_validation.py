# ruff: noqa: E501, PT018, PERF401
"""T-013-012: sensor-recipe validation with exit code 2 and a JSON pointer; hostile recipe corpus.

Requirements: FR-013-04, NFR-013-05.

Oracle: the hostile recipe corpus of the spec's own example index (`specs/013-sensors/contracts/examples/index.json`: each
case violates exactly one rule and lists the JSON pointer where it is rejected), plus hand-written hostile cases for the
"checker rules" the schema leaves to the lane (`e_min < e_max`, `a_min < a_max`, `min_range < max_range`, unique sensor ids,
paths outside the declared inputs, non-finite numbers); the limits of NFR-013-05 (<= 2 cameras, <= 1920 x 1080 px) at and
just beyond the boundary.

Expected API of the lane (package `pitstudio_rtx.lane`, first-party code importable from `studio/rtx/src`):
- `lane.validate_recipe(stage, params, declared_inputs)`: `stage` is `"st53_sensors"` or `"st57_rain_lidar"`; `params` the
  recipe block (DC-013-01); `declared_inputs` the iterable of declared stage input relpaths. Returns None when valid.
  Otherwise raises `lane.RecipeError` (a `ValueError`) with `.pointer` (the RFC 6901 JSON pointer of the first offending
  value, for a schema violation the pointer of the schema validator) and `.message`. Checked: the contract schema
  (`contracts/sensor-recipe.schema.json`); the checker rules (`elevation_fan_deg[0] < [1]`, `azimuth_fan_deg[0] < [1]`,
  `min_range_m < max_range_m`, unique sensor ids within the block); `poses`, `dust.extinction_fields[*]` and
  `haze.extinction_field` are members of `declared_inputs`; the scenario belongs to the stage (`rain` to `st57_rain_lidar`,
  S1 to S4a to `st53_sensors`); non-finite numbers anywhere.
- `lane.run_stage(stage, params, *, out_dir, inputs, envelope_path=None, backend=None, capabilities=None,
  run_id="20261011T120000Z-test", fixture=False, seed=0) -> lane.StageOutcome`: runs the stage with the given backend
  instance (default: `create_backend(params["backend"])`). `StageOutcome` has `status` (`"succeeded"`, `"failed"`,
  `"not_run"`), `exit_code` (0 on success or "not run", 2 on a refusal before rendering, 1 on a runtime failure),
  `error_class` (None, or a lane class such as `lidar-zero-points`), `message`, `pointer`, `reason`, `index` (the DC-013-03
  shard index of a successful run), `outputs` (relpaths under `out_dir`) and `manifest_fields` (test_t_013_017). Any
  recipe violation gives `exit_code` 2 with `pointer` set, opens no backend (`backend.open_calls == 0`) and leaves `out_dir`
  empty.
"""

from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "rtx" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import sensor_kit as kit  # noqa: E402
from pitstudio_rtx import lane  # noqa: E402
from pitstudio_rtx.backends import fake  # noqa: E402

CORPUS = kit.hostile_recipes()


def _declared(rec: dict) -> list[str]:
    out = []
    for value in (rec.get("poses"), (rec.get("haze") or {}).get("extinction_field")):
        if isinstance(value, str):
            out.append(value)
    out += [v for v in (rec.get("dust") or {}).get("extinction_fields", []) if isinstance(v, str)]
    return out


def _stage_for(rec: dict) -> str:
    return "st57_rain_lidar" if rec.get("scenario") == "rain" else "st53_sensors"


def _pointer_of(rec: dict, stage: str | None = None) -> str:
    with pytest.raises(lane.RecipeError) as exc:
        lane.validate_recipe(stage or _stage_for(rec), rec, _declared(rec))
    assert isinstance(exc.value, ValueError)
    return exc.value.pointer


@pytest.mark.req("FR-013-04")
@pytest.mark.parametrize("name", ["valid", "valid-s2", "valid-s3", "valid-s4a"])
def test_valid_recipes_pass(name: str) -> None:
    rec = kit.recipe(name)
    assert lane.validate_recipe("st53_sensors", rec, _declared(rec)) is None


@pytest.mark.req("FR-013-04")
def test_the_valid_rain_recipe_passes_on_the_rain_stage() -> None:
    rec = kit.recipe("valid-rain")
    assert lane.validate_recipe("st57_rain_lidar", rec, _declared(rec)) is None


@pytest.mark.req("FR-013-04")
@pytest.mark.parametrize(
    "case", CORPUS, ids=[c["file"].replace("sensor-recipe.hostile-", "").removesuffix(".json") for c in CORPUS]
)
def test_every_hostile_example_is_rejected_at_its_documented_json_pointer(case: dict) -> None:
    assert len(CORPUS) >= 20
    assert _pointer_of(case["recipe"]) == case["pointer"], case["class"]


@pytest.mark.req("FR-013-04")
@pytest.mark.parametrize(
    "case", CORPUS, ids=[c["file"].replace("sensor-recipe.hostile-", "").removesuffix(".json") for c in CORPUS]
)
def test_a_hostile_recipe_exits_2_before_opening_a_backend_and_promotes_nothing(case: dict, tmp_path: Path) -> None:
    rec = case["recipe"]
    be = fake.FakeBackend(versions=kit.OVRTX_VERSIONS)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    outcome = lane.run_stage(
        _stage_for(rec), rec, out_dir=out_dir, inputs={p: tmp_path / "x" for p in _declared(rec)}, backend=be
    )
    assert outcome.exit_code == 2 and outcome.status == "failed"
    assert outcome.pointer == case["pointer"], outcome.message
    assert be.open_calls == 0 and be.step_calls == 0
    assert list(out_dir.rglob("*")) == []


def _with(rec: dict, pointer: str, value: object) -> dict:
    """A deep copy of `rec` with the value at JSON pointer `pointer` replaced."""
    out = copy.deepcopy(rec)
    node = out
    parts = pointer.strip("/").split("/")
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
    return out


@pytest.mark.req("FR-013-04")
@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        ("/sensors/0/elevation_fan_deg", [10.0, -10.0]),  # e_min >= e_max
        ("/sensors/0/elevation_fan_deg", [5.0, 5.0]),
        ("/sensors/0/azimuth_fan_deg", [90.0, -90.0]),  # a_min >= a_max
        ("/sensors/0/max_range_m", 0.4),  # min_range_m (0.5) >= max_range_m
        ("/sensors/1/id", "rotary-64"),  # duplicate sensor id
    ],
)
def test_checker_rules_left_to_the_lane_are_enforced(pointer: str, value: object) -> None:
    assert _pointer_of(_with(kit.recipe("valid"), pointer, value)) == pointer


@pytest.mark.req("FR-013-04")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "pointer",
    [
        "/sensors/0/max_range_m",
        "/sensors/0/range_accuracy_m",
        "/sensors/0/mount_position_m/1",
        "/dust/beta_spacing_m",
        "/dust/dust_return_intensity",
        "/metrics/range_bin_m",
        "/sensors/0/horizontal_resolution_deg",
        "/sensors/0/elevation_fan_deg/0",
    ],
)
def test_non_finite_numbers_are_rejected_where_they_stand(pointer: str, bad: float) -> None:
    assert _pointer_of(_with(kit.recipe("valid"), pointer, bad)) == pointer


@pytest.mark.req("FR-013-04")
def test_non_finite_numbers_in_camera_exposure_and_haze_blocks_are_rejected() -> None:
    assert (
        _pointer_of(_with(kit.recipe("valid-s2"), "/exposure/exposure_time_s", float("nan")))
        == "/exposure/exposure_time_s"
    )
    assert _pointer_of(_with(kit.recipe("valid-s3"), "/haze/airlight_rgb/2", float("inf"))) == "/haze/airlight_rgb/2"


@pytest.mark.req("FR-013-04")
@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        ("/sensors/0/id", "Rotary_64"),  # upper-case: not a sensor id
        ("/sensors/0/id", "gänsemarsch"),  # unicode
        pytest.param("/sensors/0/id", "x" * 10_000, id="10-kB-id"),  # a 10 kB string
        ("/poses", "traces/ünicode.parquet"),
        ("/poses", "traces\\win.parquet"),
        ("/poses", "C:/traces/x.parquet"),
        ("/poses", ""),
        ("/sensors", []),  # no sensor at all
    ],
)
def test_malformed_strings_and_empty_sensor_lists_are_rejected(pointer: str, value: object) -> None:
    assert _pointer_of(_with(kit.recipe("valid"), pointer, value)).startswith(pointer)


@pytest.mark.req("FR-013-04")
def test_a_path_that_is_not_a_declared_stage_input_is_rejected() -> None:
    rec = kit.recipe("valid")
    declared = [p for p in _declared(rec) if p != rec["poses"]]
    with pytest.raises(lane.RecipeError) as exc:
        lane.validate_recipe("st53_sensors", rec, declared)
    assert exc.value.pointer == "/poses"
    declared = [p for p in _declared(rec) if p not in rec["dust"]["extinction_fields"]]
    with pytest.raises(lane.RecipeError) as exc2:
        lane.validate_recipe("st53_sensors", rec, declared)
    assert exc2.value.pointer == "/dust/extinction_fields/0"
    s3 = kit.recipe("valid-s3")
    s3["haze"]["extinction_field"] = "dust/other-field.zarr"
    with pytest.raises(lane.RecipeError) as exc3:
        lane.validate_recipe("st53_sensors", s3, [s3["poses"]])
    assert exc3.value.pointer == "/haze/extinction_field"


@pytest.mark.req("FR-013-04")
def test_the_scenario_must_belong_to_the_stage() -> None:
    rain = kit.recipe("valid-rain")
    assert _pointer_of(rain, "st53_sensors") == "/scenario"
    assert _pointer_of(kit.recipe("valid"), "st57_rain_lidar") == "/scenario"


@pytest.mark.req("NFR-013-05")
def test_camera_resolution_limits_hold_at_the_boundary() -> None:
    ok = kit.recipe("valid-s2")
    ok["sensors"][0]["width_px"], ok["sensors"][0]["height_px"] = 1920, 1080
    assert lane.validate_recipe("st53_sensors", ok, _declared(ok)) is None
    assert _pointer_of(_with(ok, "/sensors/0/width_px", 1921)) == "/sensors/0/width_px"
    assert _pointer_of(_with(ok, "/sensors/0/height_px", 1081)) == "/sensors/0/height_px"
    assert _pointer_of(_with(ok, "/sensors/0/width_px", math.inf)).startswith("/sensors/0/width_px")


@pytest.mark.req("NFR-013-05")
def test_at_most_two_cameras_and_no_camera_with_a_radar_in_one_session() -> None:
    two = kit.recipe("valid-s3")
    cam = copy.deepcopy(two["sensors"][0])
    cam["id"] = "second-camera"
    two["sensors"].append(cam)
    assert lane.validate_recipe("st53_sensors", two, _declared(two)) is None
    three = copy.deepcopy(two)
    third = copy.deepcopy(cam)
    third["id"] = "third-camera"
    three["sensors"].append(third)
    assert _pointer_of(three) == "/sensors"
    radar = kit.recipe("valid-s4a")
    radar["sensors"].append({**copy.deepcopy(cam), "id": "cam-in-radar-session"})
    assert _pointer_of(radar) == "/sensors/1/kind"
