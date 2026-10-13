# ruff: noqa: PT018
"""T-002-090 (mutation run, `guards.py`): the thermal thresholds read from the repository.

Requirement: NFR-002-05. Added after a real mutation run (specs/002-runner/mutation.json): `guards.thresholds` was
reached only through the command line, so the path of the file and the key mapping survived every mutant.

Oracle: the `runner.*` keys of specs/000-foundation/thresholds.yaml, written out again below.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitstudio.runner import guards


def _repo(tmp_path: Path, text: str | None) -> Path:
    if text is not None:
        f = tmp_path / "specs" / "000-foundation" / "thresholds.yaml"
        f.parent.mkdir(parents=True)
        f.write_bytes(text.encode())
    return tmp_path


@pytest.mark.req("NFR-002-05")
def test_thresholds_maps_the_runner_thermal_keys_to_the_guard_arguments(tmp_path: Path) -> None:
    text = (
        "runner:\n  run_pause_temp_c: 81\n  run_resume_temp_c: 70\n  run_stop_temp_c: 90\n"
        "  gpu_block_minutes: 30\n  gpu_cooldown_minutes: 5\n  loc_max: 1500\n"
    )
    assert guards.thresholds(_repo(tmp_path, text)) == {
        "pause_c": 81,
        "resume_c": 70,
        "stop_c": 90,
        "block_minutes": 30,
        "cooldown_minutes": 5,
    }


@pytest.mark.req("NFR-002-05")
def test_thresholds_keeps_only_the_keys_the_file_has(tmp_path: Path) -> None:
    got = guards.thresholds(_repo(tmp_path, "runner:\n  run_stop_temp_c: 88\n  gpu_cooldown_minutes: 12\n"))
    assert got == {"stop_c": 88, "cooldown_minutes": 12}


@pytest.mark.req("NFR-002-05")
@pytest.mark.parametrize("text", [None, "", "other: 1\n", "runner:\n  loc_max: 1\n"])
def test_thresholds_is_empty_without_a_runner_section_or_file(tmp_path: Path, text: str | None) -> None:
    assert guards.thresholds(_repo(tmp_path, text)) == {}


@pytest.mark.req("NFR-002-05")
def test_the_thermal_guard_takes_these_values_as_its_arguments(tmp_path: Path) -> None:
    text = (
        "runner:\n  run_pause_temp_c: 60\n  run_resume_temp_c: 50\n  run_stop_temp_c: 70\n"
        "  gpu_block_minutes: 1\n  gpu_cooldown_minutes: 2\n"
    )
    g = guards.ThermalGuard(**guards.thresholds(_repo(tmp_path, text)))
    assert (g.pause_c, g.resume_c, g.stop_c, g.block_minutes, g.cooldown_minutes) == (60, 50, 70, 1, 2)
    assert g.observe(0.0, 59.0).action == "run" and g.observe(1.0, 60.0).action == "pause"
    assert g.observe(2.0, 51.0).action == "pause" and g.observe(3.0, 50.0).action == "run"
    decision = g.observe(70.0, 50.0)  # 70 s after the block started: past the one-minute block
    assert decision.action == "cooldown" and decision.resume_at_s == 70.0 + 120
    assert g.observe(189.0, 50.0).action == "cooldown" and g.observe(190.0, 50.0).action == "run"
    assert g.observe(191.0, 70.0).action == "stop"
