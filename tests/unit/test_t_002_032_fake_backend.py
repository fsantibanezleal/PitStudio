# ruff: noqa: E501, PT018
"""T-002-032: the fake GPU backend (US-002-2).

Requirements: FR-002-55, FR-002-56, FR-002-57.

Expected API (stated for the implementer):
  * `pitstudio.runner.gpu.load_backend(spec: str, clock=None)`: `spec` is `fake:<device file>` (the value of
    PITSTUDIO_GPU_BACKEND or of `--gpu-backend`); returns an object with attributes `name`, `driver`,
    `vram_total_bytes` and `read(field) -> int | float`, `field` in free_bytes, temp_c, power_w, power_limit_w,
    util_pct, sm_clock_mhz, clocks_event_mask, energy_mj, nvenc_util_pct, pcie_replays; a field listed under
    `unsupported` raises an exception from `read`; time is `clock.monotonic()` minus its value when the backend was
    created (seconds since the backend started); a series is a constant or [t_s, value] steps (the value of the last
    step whose t_s <= now); `energy_mj` is the integral of the scripted `energy_mj_per_s` (a counter in mJ);
    `init_error: true` raises `pitstudio.runner.gpu.BackendInitError` from `load_backend`;
  * a missing, invalid or non-finite device file makes the command line exit 2 with a one-line message naming the
    file and the JSON pointer of the first offending value (`/series/temp_c`, `/extra`, ...);
  * with the fake backend selected the runner records `gpu.backend: fake` and `launcher: test` in the manifest of a run
    that used a GPU stage, and runs stages as `[sys.executable, "-m", <entry>, "--job", <job.json>]`.
Oracles: the spec's own example device (specs/002-runner/contracts/examples/profile.valid-fake-device.json) with
values read off its steps by hand; hand integration of the energy counter; hostile files built by hand.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import FakeClock, recipe, stage

EXAMPLE = json.loads(
    (rw.ROOT / "specs" / "002-runner" / "contracts" / "examples" / "profile.valid-fake-device.json").read_text(
        encoding="utf-8"
    )
)
GIB = 2**30


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(
        monkeypatch,
        tmp_path,
        device=EXAMPLE,
        recipes=[
            recipe("gpu-run", [stage("st50_physics", gpu="exclusive", vram=2.0)]),
            recipe("cpu-run", [stage("s10_preprocess")]),
        ],
    )
    yield w
    rw.cleanup_world(w)


def backend(world: rw.World, clock: FakeClock):
    from pitstudio.runner import gpu

    return gpu.load_backend(f"fake:{world.device_file}", clock=clock)


# ---- FR-002-55: every query, from the device file -------------------------------------------------------------------------
@pytest.mark.req("FR-002-55")
def test_fr_002_55_static_facts_come_from_the_device_file(world) -> None:
    b = backend(world, FakeClock())
    assert (b.name, b.driver, b.vram_total_bytes) == ("Fake GPU 48GB", "580.95.05", 51539607552)
    assert b.read("power_limit_w") == 300
    assert b.read("sm_clock_mhz") == 1980
    assert b.read("pcie_replays") == 0


@pytest.mark.req("FR-002-55")
@pytest.mark.parametrize(
    ("t", "free", "temp", "power", "util", "mask"),
    [
        (0.0, 49392123904, 45, 30, 0, 1),
        (9.99, 49392123904, 45, 30, 0, 1),
        (10.0, 30064771072, 45, 210, 97, 0),
        (59.9, 30064771072, 45, 210, 97, 0),
        (60.0, 30064771072, 72, 210, 97, 0),
        (119.0, 30064771072, 72, 210, 97, 4),
        (120.0, 30064771072, 83, 210, 97, 4),
        (100.0, 30064771072, 72, 210, 97, 4),
        (5000.0, 30064771072, 83, 210, 97, 4),
    ],
)
def test_fr_002_55_scripted_steps_hold_from_their_start_time(
    world, t: float, free: int, temp: float, power: float, util: float, mask: int
) -> None:
    clock = FakeClock(1000.0)  # the backend measures time since it started, not absolute time
    b = backend(world, clock)
    clock.t += t
    assert b.read("free_bytes") == free
    assert b.read("temp_c") == temp
    assert b.read("power_w") == power
    assert b.read("util_pct") == util
    assert b.read("clocks_event_mask") == mask


@pytest.mark.req("FR-002-55")
@pytest.mark.parametrize(
    ("t", "energy_mj"),
    [
        (0.0, 0),
        (5.0, 150_000),  # 30,000 mJ/s for 5 s
        (10.0, 300_000),
        (12.0, 720_000),  # + 2 s at 210,000 mJ/s
        (20.5, 300_000 + 10.5 * 210_000),
    ],
)
def test_fr_002_55_energy_counter_integrates_the_scripted_rate(world, t: float, energy_mj: float) -> None:
    clock = FakeClock()
    b = backend(world, clock)
    clock.t = t
    assert b.read("energy_mj") == pytest.approx(energy_mj, abs=1e-6)


@pytest.mark.req("FR-002-55")
def test_fr_002_55_an_unsupported_field_raises_and_the_energy_counter_never_decreases(world) -> None:
    clock = FakeClock()
    b = backend(world, clock)
    with pytest.raises(Exception):  # noqa: B017, PT011  (the requirement says "raises"; the exception type is not specified)
        b.read("nvenc_util_pct")
    last = -1.0
    for i in range(0, 300, 7):
        clock.t = float(i)
        v = b.read("energy_mj")
        assert v >= last
        last = v


@pytest.mark.req("FR-002-55")
def test_fr_002_55_initialisation_failure_is_scripted(world) -> None:
    from pitstudio.runner import gpu

    doc = rw.device_doc()
    doc["init_error"] = True
    world.write_device(doc)
    with pytest.raises(gpu.BackendInitError):
        gpu.load_backend(f"fake:{world.device_file}", clock=FakeClock())


@pytest.mark.req("FR-002-55")
def test_fr_002_55_backend_is_selectable_by_variable_and_by_flag_and_the_flag_wins(world, tmp_path: Path) -> None:
    other = rw.device_doc()
    other["name"] = "Other Fake GPU"
    other["driver"] = "999.99"
    p2 = tmp_path / "other.yaml"
    p2.write_text(yaml.safe_dump(other), encoding="utf-8")
    world.write_recipe(recipe("sel", [stage("st50_physics", gpu="exclusive", vram=2.0)]))
    assert world.run("sel").code == 0
    assert world.manifest()["gpu"]["name"] == "Fake GPU 48GB"
    import time

    time.sleep(1.1)
    world.write_recipe(recipe("sel", [stage("st50_physics", gpu="exclusive", vram=2.0, params={"payload": "second"})]))
    r = world.run("sel", "--gpu-backend", f"fake:{p2}")
    assert r.code == 0, r.text
    assert world.manifest()["gpu"]["name"] == "Other Fake GPU" and world.manifest()["gpu"]["driver"] == "999.99"


# ---- FR-002-56: test launcher is recorded -----------------------------------------------------------------------------------
@pytest.mark.req("FR-002-56")
def test_fr_002_56_fake_backend_runs_record_fake_gpu_and_the_test_launcher(world) -> None:
    spy = rw.PopenSpy(world.monkeypatch)
    r = world.run("gpu-run")
    assert r.code == 0, r.text
    m = world.manifest()
    assert m["launcher"] == "test"
    assert m["published"] is False
    assert m["gpu"]["backend"] == "fake" and m["gpu"]["name"] == "Fake GPU 48GB" and m["gpu"]["driver"] == "580.95.05"
    assert m["gpu"]["vram_total_bytes"] == 51539607552 and m["gpu"]["index"] == 0
    launches = [a for a in spy.argv_lists() if "ps_fake_stages.generic" in " ".join(a)]
    assert len(launches) == 1
    assert (
        launches[0][0] == sys.executable
        and launches[0][1:3] == ["-m", "ps_fake_stages.generic"]
        and launches[0][3] == "--job"
    )


@pytest.mark.req("FR-002-56")
def test_fr_002_56_a_cpu_only_run_has_no_gpu_record_but_still_records_the_launcher(world) -> None:
    assert world.run("cpu-run").code == 0
    m = world.manifest()
    assert m["gpu"] is None and m["launcher"] == "test"


# ---- FR-002-57: hostile device files ------------------------------------------------------------------------------------------
def dev(**over: Any) -> dict[str, Any]:
    d = rw.device_doc()
    d.update(over)
    return d


def with_series(**series: Any) -> dict[str, Any]:
    d = rw.device_doc()
    d["series"] = {**d["series"], **series}
    return d


HOSTILE_DEVICES: list[tuple[str, Any, str]] = [
    ("missing-required-field", {k: v for k, v in rw.device_doc().items() if k != "driver"}, "/driver"),
    ("unknown-top-level-field", dev(extra=1), "/extra"),
    ("wrong-type-vram", dev(vram_total_bytes="48GB"), "/vram_total_bytes"),
    ("bad-driver", dev(driver="five eighty"), "/driver"),
    ("unknown-series-field", with_series(temperature=50), "/series"),
    ("temperature-above-cap", with_series(temp_c=201), "/series/temp_c"),
    ("negative-power", with_series(power_w=-1), "/series/power_w"),
    ("util-above-100", with_series(util_pct=100.5), "/series/util_pct"),
    ("empty-steps", with_series(temp_c=[]), "/series/temp_c"),
    ("step-wrong-shape", with_series(temp_c=[[0, 45, 1]]), "/series/temp_c"),
    ("descending-times", with_series(temp_c=[[0, 45], [10, 50], [5, 60]]), "/series/temp_c"),
    ("duplicate-times", with_series(temp_c=[[0, 45], [10, 50], [10, 60]]), "/series/temp_c"),
    ("step-value-out-of-range", with_series(util_pct=[[0, 10], [5, 150]]), "/series/util_pct"),
    ("scripted-and-unsupported", dev(unsupported=["temp_c"]), "/unsupported"),
    ("unsupported-unknown-field", dev(unsupported=["fan_rpm"]), "/unsupported"),
    ("too-many-steps", with_series(temp_c=[[i, 40] for i in range(10001)]), "/series/temp_c"),
    ("name-with-markup", dev(name="<script>alert(1)</script>"), "/name"),
]


@pytest.mark.req("FR-002-57")
@pytest.mark.parametrize(("label", "doc", "pointer"), HOSTILE_DEVICES, ids=[h[0] for h in HOSTILE_DEVICES])
def test_fr_002_57_hostile_device_file_exits_2_naming_the_file_and_the_pointer(
    world, label: str, doc: Any, pointer: str
) -> None:
    world.device_file.write_text(yaml.safe_dump(doc), encoding="utf-8")
    r = world.cli("plan", str(world.recipes["cpu-run"]), "--profile", "test-profile")
    assert r.code == 2, f"{label}: exit {r.code}\n{r.text}"
    assert world.device_file.name in r.text, r.text
    assert pointer in r.text, f"{label}: message must carry the pointer {pointer}: {r.text!r}"
    assert "Traceback" not in r.text


@pytest.mark.req("FR-002-57")
@pytest.mark.parametrize(
    ("label", "body"),
    [
        ("empty-file", ""),
        ("not-yaml", "name: [unclosed"),
        ("scalar-document", "just text"),
        ("nan", "name: Fake GPU\ndriver: 580.1\nvram_total_bytes: 1000\ninit_error: false\nseries:\n  temp_c: .nan\n"),
        (
            "infinity",
            "name: Fake GPU\ndriver: 580.1\nvram_total_bytes: 1000\ninit_error: false\nseries:\n  power_w: .inf\n",
        ),
        (
            "nan-in-steps",
            "name: Fake GPU\ndriver: 580.1\nvram_total_bytes: 1000\ninit_error: false\nseries:\n  temp_c: [[0, .nan]]\n",
        ),
        (
            "negative-infinity",
            "name: Fake GPU\ndriver: 580.1\nvram_total_bytes: 1000\ninit_error: false\nseries:\n  temp_c: -.inf\n",
        ),
        ("duplicate-key", "name: a\nname: b\ndriver: 580.1\nvram_total_bytes: 1000\ninit_error: false\nseries: {}\n"),
        ("bom-and-nul", "﻿\x00\x00"),
    ],
)
def test_fr_002_57_malformed_or_non_finite_device_files_are_usage_errors(world, label: str, body: str) -> None:
    world.device_file.write_text(body, encoding="utf-8")
    r = world.cli("plan", str(world.recipes["cpu-run"]), "--profile", "test-profile")
    assert r.code == 2, f"{label}: {r.text}"
    assert world.device_file.name in r.text
    assert "Traceback" not in r.text


@pytest.mark.req("FR-002-57")
def test_fr_002_57_a_missing_device_file_and_the_flag_form_exit_2(world, tmp_path: Path) -> None:
    gone = tmp_path / "no-such-device.yaml"
    r = world.cli("plan", str(world.recipes["cpu-run"]), "--profile", "test-profile", "--gpu-backend", f"fake:{gone}")
    assert r.code == 2 and gone.name in r.text, r.text
    r = world.cli("run", str(world.recipes["cpu-run"]), "--profile", "test-profile", "--gpu-backend", "fake:")
    assert r.code == 2, r.text
    r = world.cli("run", str(world.recipes["cpu-run"]), "--profile", "test-profile", "--gpu-backend", "nvidia-magic")
    assert r.code == 2, r.text
    assert world.ledger_rows() == [] and world.run_dirs() == []
