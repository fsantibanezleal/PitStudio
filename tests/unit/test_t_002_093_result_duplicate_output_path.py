# ruff: noqa: E501
"""T-002-093: a stage result that lists two outputs on one path is an invalid result (G5 review).

Requirement: FR-002-65.

Expected behaviour: when `result.json` lists two (or more) outputs with the same `path`, the runner treats the stage as
`invalid-result` (failed, descendants skipped, exit 1), names the path (on the command line output, in an event `detail` or in
the stage's `log_tail`), publishes no output of that stage (nothing enters the store) and does not cache it (a later run
executes it again).
Oracle: the fake stage's `dup_output` mode (writes its files and lists the first one twice), hand-built raw results for the
triple listing and for distinct paths (accepted).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import recipe, stage, up


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


def objects(w: rw.World) -> set[str]:
    d = w.store / "cas" / "sha256"
    return {f.name for f in d.rglob("*") if f.is_file()} if d.is_dir() else set()


def mentions(w: rw.World, r: rw.Result, path: str) -> bool:
    texts = [r.text]
    texts += [e.get("detail", "") for e in w.events()]
    texts += [s.get("log_tail", "") for s in w.manifest()["stages"]]
    return any(path in t for t in texts)


@pytest.mark.req("FR-002-65")
def test_fr_002_65_two_outputs_on_one_path_are_an_invalid_result_naming_the_path(world) -> None:
    world.write_recipe(
        recipe(
            "dup",
            [
                stage("s10_preprocess", files=["a.bin", "b.bin"], params={"mode": "dup_output"}),
                stage("s20_feature_extraction", inputs=[up("s10_preprocess", "b.bin")]),
            ],
        )
    )
    r = world.run("dup")
    assert r.code == 1, r.text
    rec = world.stage_record("s10_preprocess")
    assert (rec["status"], rec["error_class"]) == ("failed", "invalid-result")
    assert rec["outputs"] == []
    assert world.stage_record("s20_feature_extraction")["status"] == "skipped"
    assert mentions(world, r, "a.bin"), "the duplicated path must be named"
    assert objects(world) == set(), "no output of the stage is published"
    idx = world.store / "index"
    assert not idx.exists() or not list(idx.rglob("*.json")), "and the stage is not cached"


@pytest.mark.req("FR-002-65")
def test_fr_002_65_the_stage_is_executed_again_on_the_next_run(world) -> None:
    world.write_recipe(recipe("dup2", [stage("s10_preprocess", params={"mode": "dup_output"})]))
    assert world.run("dup2").code == 1
    time.sleep(1.1)
    assert world.run("dup2").code == 1
    assert len(world.starts()) == 2, "an invalid result is never served from the cache"


@pytest.mark.req("FR-002-65")
@pytest.mark.parametrize(
    "outputs",
    [
        [{"path": "out.bin"}, {"path": "out.bin"}, {"path": "out.bin"}],
        [{"path": "out.bin"}, {"path": "other.bin"}, {"path": "out.bin"}],
        [{"path": "out.bin", "validator": "stage-x", "validated": True}, {"path": "out.bin"}],
    ],
    ids=["triple", "separated", "different-validator-fields"],
)
def test_fr_002_65_any_repetition_of_a_path_is_rejected(world, outputs: list[dict]) -> None:
    raw = json.dumps(
        {"schema_version": "1.0", "status": "succeeded", "error_class": None, "outputs": outputs, "checkpoint": False}
    )
    world.write_recipe(
        recipe(
            "dup3", [stage("s10_preprocess", files=["out.bin", "other.bin"], params={"mode": "raw_result", "raw": raw})]
        )
    )
    r = world.run("dup3")
    assert r.code == 1, r.text
    assert world.stage_record("s10_preprocess")["error_class"] == "invalid-result"
    assert objects(world) == set()


@pytest.mark.req("FR-002-65")
def test_fr_002_65_distinct_paths_are_still_accepted(world) -> None:
    world.write_recipe(recipe("nodup", [stage("s10_preprocess", files=["a.bin", "b.bin", "sub/c.bin"])]))
    assert world.run("nodup").code == 0
    assert [o["name"] for o in world.stage_record("s10_preprocess")["outputs"]] == ["a.bin", "b.bin", "sub/c.bin"]
