# ruff: noqa: PT018
"""T-002-072: `studio profile` (US-002-6).

Requirement: FR-002-54.

Expected behaviour (stated for the implementer; A = assumption listed in the red report):
  * `studio profile <recipe> --stage <key> --profile <id>` executes that ONE stage once under the normal GPU locks, hold
    check and guards, with `PITSTUDIO_PROFILE=1` in the stage's environment (and `profiling: true` in its job spec),
    uncached (it neither reads nor writes the cache: it runs even when the stage is cached, and leaves no index entry or
    object of its own in the store) and unpublishable (`studio publish` refuses its run);
  * A: the profiler files the stage leaves in its output or scratch folder (the fake stage writes `profiler.txt`) are
    collected into the run folder `runs/<run_id>/` (any sub-folder);
  * it prints a command line starting with `nsys profile --trace=cuda,nvtx` for the maintainer to run, and never spawns
    `nsys` (no argument list of any started process contains `nsys`).
Oracles: the ledger written by the fake stage (executions, environment, locks seen), PopenSpy (the full list of spawned
argument lists), store snapshots, the documented nsys command prefix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import recipe, stage


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    w.write_recipe(
        recipe(
            "prof",
            [
                stage("s10_preprocess"),
                stage("st50_physics", gpu="exclusive", vram=2.0, variant="dem", params={"probe_locks": True}),
            ],
        )
    )
    yield w
    rw.cleanup_world(w)


def objects(w: rw.World) -> set[str]:
    d = w.store / "cas" / "sha256"
    return {f.name for f in d.rglob("*") if f.is_file()} if d.is_dir() else set()


def index_files(w: rw.World) -> set[str]:
    d = w.store / "index"
    return {f.name for f in d.rglob("*.json")} if d.is_dir() else set()


@pytest.mark.req("FR-002-54")
def test_fr_002_54_the_stage_runs_once_with_the_profile_flag_under_the_normal_locks_and_nsys_is_only_printed(
    world,
) -> None:
    spy = rw.PopenSpy(world.monkeypatch)
    r = world.cli("profile", str(world.recipes["prof"]), "--stage", "st50_physics@dem", "--profile", "test-profile")
    assert r.code == 0, r.text
    rows = world.starts()
    assert len(rows) == 1 and rows[0]["stage"] == {"id": "st50_physics", "variant": "dem"}, "only the named stage, once"
    row = rows[0]
    assert row["env"]["PITSTUDIO_PROFILE"] == "1" and row["profiling"] is True and row["job"]["profiling"] is True
    assert row["locks_held"]["gpu0.compute"] is True, "the normal GPU lock is held while profiling"
    lines = [ln.strip() for ln in r.out.splitlines()]
    assert any(ln.startswith("nsys profile --trace=cuda,nvtx") for ln in lines), r.out
    for argv in spy.argv_lists():
        assert not any("nsys" in Path(a).name.lower() for a in argv), f"nsys must never be executed: {argv}"


@pytest.mark.req("FR-002-54")
def test_fr_002_54_a_profiled_run_is_uncached_even_when_the_stage_is_cached_and_stores_nothing(world) -> None:
    assert world.run("prof").code == 0
    n_exec = len(world.starts())
    objs, idx = objects(world), index_files(world)
    import time

    time.sleep(1.1)
    r = world.cli("profile", str(world.recipes["prof"]), "--stage", "st50_physics@dem", "--profile", "test-profile")
    assert r.code == 0, r.text
    assert len(world.starts()) == n_exec + 1, "a hit is not served: the stage runs for the profiler"
    assert objects(world) == objs and index_files(world) == idx, "a profiled run reads and writes no cache"


@pytest.mark.req("FR-002-54")
def test_fr_002_54_profiler_files_are_collected_in_the_run_folder_and_never_promoted(world) -> None:
    assert (
        world.cli(
            "profile", str(world.recipes["prof"]), "--stage", "st50_physics@dem", "--profile", "test-profile"
        ).code
        == 0
    )
    run_dir = world.last_run()
    found = [p for p in run_dir.rglob("*") if p.is_file() and p.read_bytes() == b"profile data\n"]
    assert found, "the profiler output must be collected under runs/<run_id>/"
    import hashlib

    assert hashlib.sha256(b"profile data\n").hexdigest() not in objects(world)
    assert index_files(world) == set(), "nothing of a profiled run enters the cache"


@pytest.mark.req("FR-002-54")
def test_fr_002_54_a_profiled_run_cannot_be_published(world) -> None:
    assert (
        world.cli(
            "profile", str(world.recipes["prof"]), "--stage", "st50_physics@dem", "--profile", "test-profile"
        ).code
        == 0
    )
    run_id = world.last_run().name
    before = world.snapshot_repo()
    r = world.cli("publish", run_id)
    assert r.code == 2, r.text
    assert world.snapshot_repo() == before


@pytest.mark.req("FR-002-54")
def test_fr_002_54_the_hold_and_the_guards_apply_and_nsys_is_not_printed_when_nothing_ran(world) -> None:
    world.hold("profiling must wait")
    r = world.cli("profile", str(world.recipes["prof"]), "--stage", "st50_physics@dem", "--profile", "test-profile")
    assert r.code == 4 and world.ledger_rows() == []
    world.release_hold()
    world.write_recipe(recipe("toobig", [stage("st50_physics", gpu="exclusive", vram=60.0)]))
    spy = rw.PopenSpy(world.monkeypatch)
    r = world.cli("profile", str(world.recipes["toobig"]), "--stage", "st50_physics", "--profile", "test-profile")
    assert r.code == 5, r.text
    assert world.ledger_rows() == []
    assert not any("nsys" in " ".join(a).lower() for a in spy.argv_lists())


@pytest.mark.req("FR-002-54")
def test_fr_002_54_a_failing_profiled_stage_reports_the_failure_and_still_never_runs_nsys(world) -> None:
    world.write_recipe(
        recipe("brokenprof", [stage("st50_physics", gpu="exclusive", vram=2.0, params={"mode": "fail"})])
    )
    spy = rw.PopenSpy(world.monkeypatch)
    r = world.cli("profile", str(world.recipes["brokenprof"]), "--stage", "st50_physics", "--profile", "test-profile")
    assert r.code == 1, r.text
    assert not any("nsys" in " ".join(a).lower() for a in spy.argv_lists())
