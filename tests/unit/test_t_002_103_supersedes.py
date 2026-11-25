# ruff: noqa: PT018, F811
"""T-002-103: an imported run that supersedes an earlier published run replaces it (FR-002-73).

Oracles: the web index and the files of the published tree, listed by the test before and after; the rule that a
republished run must not leave its predecessor beside it (two cards with the same numbers on one case page).
"""

from __future__ import annotations

import json

import pytest
from test_import_run import World, world  # noqa: F401  (the fixture is used by name)

from pitstudio.runner import publish
from pitstudio.runner.recipe import Usage


def first_run(w: World) -> str:
    assert w.run()[0] == 0
    (run,) = w.runs()
    publish.publish(w.store, w.repo, run.name, None)
    return run.name


def second_run(w: World, old: str, **over: object) -> str:
    spec = w.doc()
    spec["slug"] = "c1-demo-v2"
    spec["supersedes"] = old
    spec.update(over)
    assert w.run(spec)[0] == 0
    return next(r.name for r in w.runs() if r.name != old)


def index(w: World) -> dict:
    return json.loads((w.repo / "web/public/assets/manifest.json").read_text(encoding="utf-8"))


@pytest.mark.req("FR-002-73")
def test_publishing_the_new_run_removes_the_superseded_one(world: World) -> None:
    old = first_run(world)
    assert (world.repo / "web/public/assets" / old).is_dir()
    new = second_run(world, old)
    publish.publish(world.store, world.repo, new, None)
    idx = index(world)
    assert [r["run_id"] for r in idx["runs"]] == [new]
    assert {a["run_id"] for a in idx["artefacts"]} == {new}
    assert not (world.repo / "web/public/assets" / old).exists()
    assert not (world.repo / "web/public/assets/runs" / old).exists()
    assert (world.repo / "web/public/assets/runs" / new / "manifest.json").is_file()


@pytest.mark.req("FR-002-73")
def test_the_new_run_records_what_it_supersedes(world: World) -> None:
    old = first_run(world)
    new = second_run(world, old)
    run = world.store / "runs" / new
    assert json.loads((run / "import.json").read_text(encoding="utf-8"))["supersedes"] == old
    assert any(old in n for n in json.loads((run / "manifest.json").read_text(encoding="utf-8"))["notes"])


@pytest.mark.req("FR-002-73")
def test_a_superseded_run_that_is_not_published_is_not_an_error(world: World) -> None:
    assert world.run()[0] == 0
    (run,) = world.runs()
    spec = world.doc()
    spec["slug"] = "c1-demo-v2"
    spec["supersedes"] = run.name
    assert world.run(spec)[0] == 0
    new = next(r.name for r in world.runs() if r.name != run.name)
    publish.publish(world.store, world.repo, new, None)
    assert [r["run_id"] for r in index(world)["runs"]] == [new]


@pytest.mark.req("FR-002-73")
@pytest.mark.parametrize("bad", ["", "../x", "not-a-run-id", "20261012T061925Z-a/b"])
def test_a_supersedes_that_is_not_a_run_id_is_refused_before_the_first_write(world: World, bad: str) -> None:
    spec = world.doc()
    spec["supersedes"] = bad
    code, err = world.run(spec)
    assert code == 2 and "supersedes" in err
    assert world.runs() == []


@pytest.mark.req("FR-002-73")
def test_a_run_cannot_supersede_itself(world: World) -> None:
    old = first_run(world)
    with pytest.raises(Usage, match="supersede"):
        spec = world.doc()
        spec["supersedes"] = old
        publish_self = world.store / "runs" / old / "import.json"
        data = json.loads(publish_self.read_text(encoding="utf-8"))
        data["supersedes"] = old
        publish_self.write_text(json.dumps(data), encoding="utf-8")
        publish.publish(world.store, world.repo, old, None)
