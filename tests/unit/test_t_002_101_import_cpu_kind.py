# ruff: noqa: PT018, F811
"""T-002-101: `studio import-run` records a run made on the CPU with a CPU label (FR-002-72).

Oracles: the run manifest contract, the label the main session fixed (2026-11-23: how it was produced, CPU, on this
machine, with the producer tool), and the observation that no queue fact exists for such a run. The imports of C1, D1,
D2, E1 and E2 name `"kind": "cpu"`.
"""

from __future__ import annotations

import json

import pytest
from test_import_run import World, manifest_of, world  # noqa: F401  (the fixture is used by name)

from pitstudio.runner import publish
from pitstudio.runner.recipe import first_errors


def cpu_spec(w: World) -> dict:
    spec = w.doc()
    spec["kind"] = "cpu"
    spec["producer_paths"] = ["studio/recipes/cases"]
    spec.pop("gpu_hours")
    return spec


@pytest.mark.req("FR-002-72")
def test_a_cpu_run_is_labelled_cpu_on_this_machine_with_its_producer_tool(world: World) -> None:
    code, err = world.run(cpu_spec(world))
    assert code == 0, err
    m = manifest_of(world)
    assert first_errors("manifest", m, "#/$defs/run", n=3) == []
    notes = " | ".join(m["notes"])
    assert "produced on the CPU, on this machine" in notes and "pytorch" in notes
    assert "GPU queue" not in notes
    assert m["gpu"] is None


@pytest.mark.req("FR-002-72")
def test_a_cpu_run_looks_for_no_queue_fact_and_is_not_partial_for_their_absence(world: World) -> None:
    (world.queue / "done" / "33-demo-job.sh").unlink()
    (world.queue / "33-demo-job.log").unlink()
    code, err = world.run(cpu_spec(world))
    assert code == 0, err
    notes = " | ".join(manifest_of(world)["notes"])
    for word in ("script", "log", "GPU-hours", "partial"):
        assert word not in notes, word
    (run,) = world.runs()
    assert json.loads((run / "import.json").read_text(encoding="utf-8"))["partial"] is False


@pytest.mark.req("FR-002-72")
def test_a_cpu_run_records_no_timing_and_publishes(world: World) -> None:
    code, err = world.run(cpu_spec(world))
    assert code == 0, err
    (stage,) = manifest_of(world)["stages"]
    assert stage["wall_s"] == 0 and stage["attempts"][0]["duration_s"] == 0
    (run,) = world.runs()
    publish.publish(world.store, world.repo, run.name, None)
    pub = json.loads((world.repo / "web/public/assets/runs" / run.name / "manifest.json").read_text(encoding="utf-8"))
    assert any("produced on the CPU" in n for n in pub["notes"])


@pytest.mark.req("FR-002-72")
def test_a_cpu_run_may_still_name_partial_reasons_of_its_own(world: World) -> None:
    spec = cpu_spec(world)
    spec["partial_reasons"] = ["the observed signal-to-noise ratio is unavailable"]
    code, err = world.run(spec)
    assert code == 0, err
    assert "partial: the observed signal-to-noise ratio is unavailable" in " | ".join(manifest_of(world)["notes"])
