# ruff: noqa: E501, PT018
"""T-013-092: fixture sensor inputs: fake backend only, shards marked, none published.

Requirements: FR-013-43.

Oracle: hand calculation (plan.md "FR-013-43"): a fixture envelope on the real backend exits 2; on the fake backend the shards carry `fixture: true` and none
is promoted to a published manifest; a real input gives an explicit `false`. The Parquet marker is read back with `pyarrow`.

Expected API (see test_t_013_012, test_t_013_017): `lane.run_stage(..., fixture=True)` declares that the sensor recipe block or the lidar envelope
is a contract fixture (DC-013-01, DC-013-02 fixtures; the draft schemas have `additionalProperties: false` and no `fixture` member, so the flag
travels in the stage parameters, see the review notes).
- With `fixture=True` and a backend whose `describe().name` is not `"fake"` (a real `ovrtx` or `isaac` backend, here a `FakeBackend(name="ovrtx")`
  standing in for one) the stage exits 2 before opening it, naming "fake backend".
- With `fixture=True` on the `fake` backend the run succeeds, the index has `fixture: true` at the top level and on every file entry, every
  Parquet file carries the file-level metadata key `pitstudio:fixture` = `b"true"`, `outcome.publishable` is false and
  `outcome.manifest_fields["publish"]` is false.
- With `fixture=False` (the default) the index and its file entries carry no `fixture: true` (absent or false), no Parquet file carries the key set to
  `true`, `publishable` is true.
- A fixture rain arm (`st57_rain_lidar`) follows the same rules.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "rtx" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import sensor_kit as kit  # noqa: E402
from pitstudio_rtx import lane  # noqa: E402
from pitstudio_rtx.backends import fake  # noqa: E402


def _run(tmp: Path, *, fixture: bool, backend_name: str = "fake", stage: str = "st53_sensors"):
    rec = kit.recipe("valid-rain" if stage == "st57_rain_lidar" else "valid")
    if stage == "st53_sensors":
        rec["sensors"] = rec["sensors"][:1]
    versions = {**kit.OVRTX_VERSIONS, "isaacsim": "6.1.0.0"}
    script = None
    if stage == "st57_rain_lidar":

        def script(sensor: dict, i: int) -> dict:  # a rain-capable stand-in: the applied rate equals the requested one
            frame = kit.lidar_output(n=80, n_valid=60, seed=i)
            frame["applied_rain_rate_mm_h"] = sensor["rain_rate_mm_h"]
            return frame

    be = fake.FakeBackend(script, versions=versions, name=backend_name)
    inputs = {rec["poses"]: kit.write_poses(tmp / "poses.parquet", 2)}
    for f in (rec.get("dust") or {}).get("extinction_fields", []):
        (tmp / "field").mkdir(exist_ok=True)
        inputs[f] = tmp / "field"
    env = tmp / "env.json"
    env.write_text(json.dumps(kit.envelope_for(rec, versions=kit.OVRTX_VERSIONS)), encoding="utf-8")
    out = tmp / "out"
    out.mkdir()
    kw = (
        {"capabilities": json.loads((ROOT / "studio" / "capabilities.json").read_text(encoding="utf-8"))}
        if stage == "st57_rain_lidar"
        else {}
    )
    outcome = lane.run_stage(
        stage, rec, out_dir=out, inputs=inputs, envelope_path=env, backend=be, fixture=fixture, **kw
    )
    return outcome, be, out


def _marker(path: Path) -> bytes | None:
    import pyarrow.parquet as pq

    return (pq.read_metadata(path).metadata or {}).get(b"pitstudio:fixture")


@pytest.mark.req("FR-013-43")
@pytest.mark.parametrize("name", ["ovrtx", "isaac", "isaac-sim", "ovrtx-0.5"])
def test_a_fixture_on_a_real_backend_exits_2_before_opening_it(tmp_path: Path, name: str) -> None:
    outcome, be, out = _run(tmp_path, fixture=True, backend_name=name)
    assert outcome.exit_code == 2 and outcome.status == "failed" and "fake backend" in outcome.message.lower()
    assert be.open_calls == 0 and be.step_calls == 0 and list(out.rglob("*")) == []
    assert outcome.publishable is False


@pytest.mark.req("FR-013-43")
@pytest.mark.parametrize("stage", ["st53_sensors", "st57_rain_lidar"])
def test_a_fixture_on_the_fake_backend_runs_marks_every_shard_and_publishes_none(tmp_path: Path, stage: str) -> None:
    outcome, be, out = _run(tmp_path, fixture=True, stage=stage)
    assert outcome.exit_code == 0 and outcome.status == "succeeded", outcome.message
    index = outcome.index
    assert index["fixture"] is True and all(e["fixture"] is True for e in index["files"])
    parquet = [e for e in index["files"] if e["format"] == "parquet"]
    assert parquet and all(_marker(out / e["path"]) == b"true" for e in parquet)
    assert outcome.publishable is False and outcome.manifest_fields["publish"] is False
    assert be.open_calls >= 1


@pytest.mark.req("FR-013-43")
def test_a_real_input_is_not_marked_and_is_publishable(tmp_path: Path) -> None:
    outcome, _, out = _run(tmp_path, fixture=False)
    assert outcome.exit_code == 0, outcome.message
    index = outcome.index
    assert index.get("fixture") in (None, False) and all(e.get("fixture") in (None, False) for e in index["files"])
    assert all(_marker(out / e["path"]) in (None, b"false") for e in index["files"] if e["format"] == "parquet")
    assert outcome.publishable is True and outcome.manifest_fields["publish"] is True
