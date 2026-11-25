# ruff: noqa: E501, PT018, RUF059
"""T-013-060: the `isaac` sensor backend behind the protocol (fake), guards reused, "not run" paths, rain refused on `ovrtx`.

Requirements: FR-013-29, FR-013-30.

Oracle: the committed `studio/capabilities.json` (its `isaacsim` probe passes) and edited copies of it for the not-pass states; the rain-rate
schedule written from the spec (default {0, 2, 10, 50} mm/h); step counts of the fake backend (a re-warm-up of 40 frames after every rain-rate
change); the spec's literal message "rain is available only on the isaac backend".

Expected API (see test_t_013_012, test_t_013_014): `lane.run_stage("st57_rain_lidar", params, *, out_dir, inputs, envelope_path, backend,
capabilities)` with `capabilities` the parsed `studio/capabilities.json` (a mapping with `probes`).
- The stage applies the recipe validation, the envelope guard, the point-count guard and the output validation of st53, and writes shards of the
  same contract (scenario `rain`, stage `st57_rain_lidar`); the pose trace is rendered once per rain rate of `rain_rates_mm_h`, in the listed
  order, re-warming the backend (`warmup_frames` steps, discarded) before each rate; recorded frames are numbered consecutively over all
  rates (0 ... rates x poses - 1) and each index frame record carries `rain_rate_mm_h` (the rate it was rendered at).
- For each rain rate the lane closes the session and opens a new one: `open(stage, sensors)` with `rain_rate_mm_h` in every sensor dict
  (`open_calls == close_calls ==` number of rates). The backend reports the rain rate it applied in each lidar frame output
  (`applied_rain_rate_mm_h`).
- The rain arm is `not_run` (`status` "not_run", `exit_code` 0, a `reason` naming `isaacsim`, no output, no backend opened) when
  `capabilities["probes"]["isaacsim"]["status"]` is not `"pass"` or the probe is absent; it is `not_run` with a reason naming both rates,
  and publishes nothing (an empty `out_dir`, `publishable` false), when a frame reports an applied rate different from the requested one.
- `lane.run_stage("st53_sensors", ...)` with a non-zero rain rate (backend `ovrtx`) exits 2 with the message "rain is available only on the
  isaac backend".
- `pitstudio_isaac.sensor_backend` imports without `isaacsim` and defines an `IsaacSensorBackend` class with the four protocol operations.
"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "rtx" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import sensor_kit as kit  # noqa: E402
from pitstudio_rtx import lane  # noqa: E402
from pitstudio_rtx.backends import fake  # noqa: E402

CAPS = json.loads((ROOT / "studio" / "capabilities.json").read_text(encoding="utf-8"))
ISAAC_VERSIONS = {**kit.OVRTX_VERSIONS, "isaacsim": "6.1.0.0"}


def _rec(rates: list[float] | None = None) -> dict:
    rec = kit.recipe("valid-rain")
    if rates is not None:
        rec["rain_rates_mm_h"] = rates
    return rec


def _setup(tmp: Path, rec: dict, *, applied=None, warmup: int = 0, poses: int = 2, caps=None):
    def script(sensor: dict, i: int) -> dict:
        requested = sensor["rain_rate_mm_h"]  # the lane passes the rate as a sensor setting of `open`
        frame = kit.lidar_output(n=80, n_valid=60, seed=i)
        frame["applied_rain_rate_mm_h"] = applied(requested, i) if applied else requested
        return frame

    be = fake.FakeBackend(script, versions=ISAAC_VERSIONS, warmup_frames=warmup, name="fake")
    inputs = {rec["poses"]: kit.write_poses(tmp / "poses.parquet", poses)}
    env = tmp / "env.json"
    env.write_text(json.dumps(kit.envelope_for(rec, versions=kit.OVRTX_VERSIONS)), encoding="utf-8")
    out = tmp / "out"
    out.mkdir()
    return be, inputs, env, out, CAPS if caps is None else caps


def _run(tmp: Path, rec: dict, **kw):
    be, inputs, env, out, caps = _setup(tmp, rec, **kw)
    outcome = lane.run_stage(
        "st57_rain_lidar", rec, out_dir=out, inputs=inputs, envelope_path=env, backend=be, capabilities=caps
    )
    return outcome, be, out


@pytest.mark.req("FR-013-29")
def test_the_committed_capabilities_file_says_the_isaacsim_probe_passes() -> None:
    assert CAPS["probes"]["isaacsim"]["status"] == "pass"


@pytest.mark.req("FR-013-29")
def test_every_rain_rate_is_rendered_in_order_and_tagged_in_the_shard_contract(tmp_path: Path) -> None:
    outcome, be, out = _run(tmp_path, _rec(), poses=2)
    assert outcome.exit_code == 0 and outcome.status == "succeeded", outcome.message
    index = outcome.index
    assert kit.schema_errors("sensor-shard.schema.json", index) == []
    assert (index["stage"], index["scenario"]) == ("st57_rain_lidar", "rain")
    frames = index["frames"]
    assert [f["frame"] for f in frames] == list(range(8))  # 4 rates x 2 poses, numbered consecutively
    assert [f["rain_rate_mm_h"] for f in frames] == [0, 0, 2, 2, 10, 10, 50, 50]
    assert be.step_calls == 8 and be.open_calls == 4 and be.close_calls == 4  # one session per rain rate
    assert outcome.manifest_fields["performance"] == "local-only"


@pytest.mark.req("FR-013-29")
def test_the_backend_is_re_warmed_after_every_rain_rate_change(tmp_path: Path) -> None:
    outcome, be, _ = _run(tmp_path, _rec([0, 50]), warmup=40, poses=2)
    assert outcome.exit_code == 0, outcome.message
    assert be.step_calls == 2 * (40 + 2)  # 40 discarded + 2 recorded, for each of the two rates
    assert [f["frame"] for f in outcome.index["frames"]] == [0, 1, 2, 3]


@pytest.mark.req("FR-013-29")
def test_the_stage_guards_are_applied_to_the_rain_arm(tmp_path: Path) -> None:
    # point-count guard (FR-013-08)
    be, inputs, env, out, caps = _setup(tmp_path / "a", _rec([0, 2]), poses=3)
    be.script = lambda sensor, i: {
        **kit.lidar_output(n=80, n_valid=0 if i == 4 else 60, seed=i),
        "applied_rain_rate_mm_h": sensor["rain_rate_mm_h"],
    }
    outcome = lane.run_stage(
        "st57_rain_lidar", _rec([0, 2]), out_dir=out, inputs=inputs, envelope_path=env, backend=be, capabilities=caps
    )
    assert outcome.error_class == "lidar-zero-points" and be.step_calls == 5 and list(out.rglob("*")) == []
    # output validation (FR-013-09)
    be, inputs, env, out, caps = _setup(tmp_path / "b", _rec([0]), poses=2)
    be.script = lambda sensor, i: {
        **kit.lidar_output(n=80, n_valid=60, seed=i),
        "x": np.zeros(80, np.float64),
        "applied_rain_rate_mm_h": sensor["rain_rate_mm_h"],
    }
    outcome = lane.run_stage(
        "st57_rain_lidar", _rec([0]), out_dir=out, inputs=inputs, envelope_path=env, backend=be, capabilities=caps
    )
    assert outcome.error_class == "backend-output-invalid" and list(out.rglob("*")) == []
    # recipe validation (FR-013-04)
    bad = _rec([0])
    bad["sensors"][0]["elevation_fan_deg"] = [-22.5, 46.0]
    be, inputs, env, out, caps = _setup(tmp_path / "c", bad)
    outcome = lane.run_stage(
        "st57_rain_lidar", bad, out_dir=out, inputs=inputs, envelope_path=env, backend=be, capabilities=caps
    )
    assert outcome.exit_code == 2 and outcome.pointer == "/sensors/0/elevation_fan_deg/1" and be.open_calls == 0
    # envelope guard (FR-013-05)
    rec = _rec([0])
    be, inputs, env, out, caps = _setup(tmp_path / "d", rec)
    env.write_text(json.dumps(kit.envelope_for(rec, status="fail", versions=kit.OVRTX_VERSIONS)), encoding="utf-8")
    outcome = lane.run_stage(
        "st57_rain_lidar", rec, out_dir=out, inputs=inputs, envelope_path=env, backend=be, capabilities=caps
    )
    assert outcome.exit_code == 2 and be.open_calls == 0


@pytest.mark.req("FR-013-30")
@pytest.mark.parametrize("state", ["fail", "skip", "absent"])
def test_without_a_passing_isaacsim_probe_the_arm_is_recorded_not_run(tmp_path: Path, state: str) -> None:
    caps = copy.deepcopy(CAPS)
    if state == "absent":
        del caps["probes"]["isaacsim"]
    else:
        caps["probes"]["isaacsim"]["status"] = state
    outcome, be, out = _run(tmp_path, _rec(), caps=caps)
    assert outcome.status == "not_run" and outcome.exit_code == 0 and "isaacsim" in outcome.reason
    assert be.open_calls == 0 and list(out.rglob("*")) == [] and outcome.publishable is False


@pytest.mark.req("FR-013-30")
def test_a_different_applied_rain_rate_makes_the_arm_not_run_and_publishes_nothing(tmp_path: Path) -> None:
    outcome, _, out = _run(
        tmp_path, _rec([0, 10]), applied=lambda requested, i: 0.0 if requested == 0 else 7.0, poses=2
    )
    assert outcome.status == "not_run" and outcome.exit_code == 0 and outcome.publishable is False
    assert "10" in outcome.reason and "7" in outcome.reason  # both the requested and the applied rate
    assert list(out.rglob("*")) == [] and outcome.index is None  # not even the 0 mm/h frames that matched


@pytest.mark.req("FR-013-30")
def test_a_non_zero_rain_rate_on_the_ovrtx_backend_exits_2_with_the_spec_message(tmp_path: Path) -> None:
    rec = kit.recipe("valid")
    rec["rain_rates_mm_h"] = [0, 10]
    be = fake.FakeBackend(versions=kit.OVRTX_VERSIONS)
    out = tmp_path / "out"
    out.mkdir()
    inputs = {rec["poses"]: kit.write_poses(tmp_path / "poses.parquet", 2)}
    for f in rec["dust"]["extinction_fields"]:
        inputs[f] = tmp_path
    outcome = lane.run_stage("st53_sensors", rec, out_dir=out, inputs=inputs, backend=be)
    assert outcome.exit_code == 2 and "rain is available only on the isaac backend" in outcome.message
    assert outcome.pointer == "/rain_rates_mm_h/1" and be.open_calls == 0 and list(out.rglob("*")) == []
    zero_only = copy.deepcopy(rec)
    zero_only["rain_rates_mm_h"] = [0]  # a zero rate is the clear-air default and is allowed on ovrtx
    (tmp_path / "z").mkdir()
    env = tmp_path / "z" / "env.json"
    env.write_text(json.dumps(kit.envelope_for(zero_only)), encoding="utf-8")
    out2 = tmp_path / "z" / "out"
    out2.mkdir()
    outcome = lane.run_stage(
        "st53_sensors",
        zero_only,
        out_dir=out2,
        inputs=inputs,
        envelope_path=env,
        backend=fake.FakeBackend(versions=kit.OVRTX_VERSIONS),
    )
    assert outcome.exit_code == 0, outcome.message


@pytest.mark.req("FR-013-29")
def test_the_isaac_backend_module_imports_without_isaac_sim_and_has_the_four_operations() -> None:
    mod = importlib.import_module("pitstudio_isaac.sensor_backend")
    assert "isaacsim" not in sys.modules  # a lazy runtime import: importing the module never loads Isaac Sim
    cls = mod.IsaacSensorBackend
    assert all(callable(getattr(cls, name, None)) for name in ("describe", "open", "step", "close"))
