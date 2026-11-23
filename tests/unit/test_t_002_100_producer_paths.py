# ruff: noqa: PT018, F811
"""T-002-100: the clean-tree rule of an imported run counts only the producer paths (FR-002-71).

Oracle: `git status --porcelain` of a scratch repository the test builds (a modified or untracked file under a
producer path is dirty, one elsewhere is not), and the publish rule of FR-002-52 (a run made from a dirty tree is
refused). The producer paths of a run are the paths its import spec names (default: the runner package, the tool
registry and the recipe).
"""

from __future__ import annotations

import json

import pytest
from test_import_run import World, manifest_of, world  # noqa: F401  (the fixture is used by name)

from pitstudio.runner import publish
from pitstudio.runner.recipe import Usage


def spec_with(w: World, paths: list[str] | None) -> dict:
    spec = w.doc()
    if paths is not None:
        spec["producer_paths"] = paths
    return spec


@pytest.mark.req("FR-002-71")
def test_a_dirty_file_outside_the_producer_paths_does_not_block_the_run(world: World) -> None:
    (world.repo / "other").mkdir()
    (world.repo / "other" / "agent-work.txt").write_text("someone else's work in progress", encoding="utf-8")
    (world.repo / "studio" / "tools.yaml").write_bytes((world.repo / "studio" / "tools.yaml").read_bytes())
    code, err = world.run(spec_with(world, ["studio/recipes/cases"]))
    assert code == 0, err
    assert manifest_of(world)["git_dirty"] is False
    (run,) = world.runs()
    publish.publish(world.store, world.repo, run.name, None)


@pytest.mark.req("FR-002-71")
def test_a_modified_file_under_a_producer_path_blocks_the_publication(world: World) -> None:
    (world.repo / "studio" / "recipes" / "cases" / "c1.yaml").write_text("id: c1-slope\n# edited\n", encoding="utf-8")
    code, err = world.run(spec_with(world, ["studio/recipes/cases"]))
    assert code == 0, err
    assert manifest_of(world)["git_dirty"] is True
    (run,) = world.runs()
    with pytest.raises(Usage, match="uncommitted"):
        publish.publish(world.store, world.repo, run.name, None)


@pytest.mark.req("FR-002-71")
def test_an_untracked_file_under_a_producer_path_blocks_the_publication(world: World) -> None:
    (world.repo / "studio" / "recipes" / "cases" / "new.yaml").write_text("id: new\n", encoding="utf-8")
    code, err = world.run(spec_with(world, ["studio/recipes/cases"]))
    assert code == 0, err
    assert manifest_of(world)["git_dirty"] is True


@pytest.mark.req("FR-002-71")
def test_a_committed_producer_path_is_clean(world: World) -> None:
    code, err = world.run(spec_with(world, ["studio/recipes/cases", "studio/tools.yaml"]))
    assert code == 0, err
    assert manifest_of(world)["git_dirty"] is False


@pytest.mark.req("FR-002-71")
def test_the_default_producer_paths_include_the_recipe_and_the_tool_registry(world: World) -> None:
    (world.repo / "studio" / "recipes" / "cases" / "c1.yaml").write_text("id: c1-slope\n# edited\n", encoding="utf-8")
    code, err = world.run(spec_with(world, None))
    assert code == 0, err
    assert manifest_of(world)["git_dirty"] is True


@pytest.mark.req("FR-002-71")
def test_the_producer_paths_and_the_sha_are_recorded_with_the_run(world: World) -> None:
    code, err = world.run(spec_with(world, ["studio/recipes/cases"]))
    assert code == 0, err
    (run,) = world.runs()
    rec = json.loads((run / "import.json").read_text(encoding="utf-8"))
    assert rec["producer_paths"] == ["studio/recipes/cases"]
    m = manifest_of(world)
    assert any("producer paths: studio/recipes/cases" in n and m["git_sha"][:12] in n for n in m["notes"])


@pytest.mark.req("FR-002-71")
@pytest.mark.parametrize("bad", ["../outside", "/etc", "C:/Users/x", "studio/missing-dir", "", "a\\b"])
def test_a_producer_path_that_is_not_a_repository_path_is_refused(world: World, bad: str) -> None:
    code, err = world.run(spec_with(world, [bad]))
    assert code == 2 and "producer path" in err
    assert world.runs() == []
