# ruff: noqa: PT018
"""T-002-022: a parameter change propagates exactly through the DAG (US-002-3).

Requirement: P-002-04. Also exercises FR-002-08 end to end (plan keys equal the reference formula on a seeded store).

Expected API: `studio plan --json` (see tests/unit/test_t_002_010_plan.py for the shape); a stage whose key has an index
entry with all objects present is `hit` and shows its `cache_key`; after one parameter of stage s changes, s is `miss`,
every descendant of s is `pending` (its inputs' digests are unknown while s is not cached; `miss` is also allowed by the
property) and every other stage keeps its previous `cache_key` and `hit` status.
Oracles: the reference key formula of tests/support/refimpl.py (hashlib over sorted compact JSON), descendants computed
by a breadth-first search over the generated DAG (the plan names networkx as the reference; a hand-written BFS is the
same oracle without a third-party import in a red test), and the store seeded by hand in the layout of plan.md D3.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import refimpl
import runner_world as rw
from runner_world import recipe, stage, up

POOL_IDS = [
    "s00_download",
    "s05_synthesize",
    "s10_preprocess",
    "s20_feature_extraction",
    "s30_train",
    "s40_infer",
    "s50_evaluate",
    "s60_export",
    "st10_terrain",
    "st20_pit_design",
    "st30_assets",
    "st40_compose",
    "st45_validate",
]
POOL = [(i, f"v{j}") for i in POOL_IDS for j in range(6)]  # 78 distinct (id, variant) keys


@st.composite
def dags(draw: st.DrawFn) -> dict[str, Any]:
    n = draw(st.integers(2, 64))
    nodes = draw(st.lists(st.sampled_from(POOL), min_size=n, max_size=n, unique=True))
    stages: list[dict[str, Any]] = []
    for i, (sid, var) in enumerate(nodes):
        parents = draw(st.lists(st.integers(0, i - 1), max_size=3, unique=True)) if i else []
        stages.append(
            stage(
                sid,
                variant=var,
                params={"alpha": draw(st.integers(0, 50))},
                inputs=[up(nodes[p][0], "out.bin", nodes[p][1]) for p in parents],
            )
        )
    rng_seed = draw(st.integers(0, 2**62))
    return recipe("dag", stages, seed=rng_seed)


def descendants(doc: dict[str, Any], key: str) -> set[str]:
    kids: dict[str, set[str]] = {refimpl.key_str(s): set() for s in doc["stages"]}
    for s in doc["stages"]:
        for i in s["inputs"]:
            kids[i["stage"] + "@" + i["variant"]].add(refimpl.key_str(s))
    out: set[str] = set()
    frontier = [key]
    while frontier:
        for c in kids[frontier.pop()]:
            if c not in out:
                out.add(c)
                frontier.append(c)
    return out


def statuses(plan: dict[str, Any]) -> dict[str, tuple[str, str | None]]:
    return {s["key"]: (s["status"], s["cache_key"]) for s in plan["stages"]}


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


@pytest.mark.req("P-002-04")
def test_p_002_04_a_changed_parameter_invalidates_exactly_the_stage_and_its_descendants(world) -> None:
    @settings(max_examples=30, deadline=None)
    @given(doc=dags(), pick=st.integers(0, 63))
    def prop(doc: dict[str, Any], pick: int) -> None:
        shutil.rmtree(world.store, ignore_errors=True)
        world.store.mkdir(parents=True)
        world.write_recipe(doc)
        ref_keys = refimpl.seed_store(world.store, world.repo, doc)
        before = statuses(world.plan_json("dag"))
        assert {k: v for k, (s, v) in before.items() if s == "hit"} == ref_keys, (
            "plan keys must follow the FR-002-08 formula"
        )
        assert all(s == "hit" for s, _ in before.values())

        target = refimpl.key_str(doc["stages"][pick % len(doc["stages"])])
        mutated = {
            **doc,
            "stages": [
                {**s, "params": {**s["params"], "alpha": s["params"]["alpha"] + 1000}}
                if refimpl.key_str(s) == target
                else s
                for s in doc["stages"]
            ],
        }
        world.write_recipe(mutated)
        after = statuses(world.plan_json("dag"))
        below = descendants(doc, target)
        assert after[target][0] == "miss" and after[target][1] != before[target][1] and after[target][1] is not None
        for k in below:
            assert after[k][0] in ("pending", "miss"), (k, after[k])
            assert after[k][1] is None or after[k][1] != before[k][1]
        for k in set(after) - below - {target}:
            assert after[k] == before[k], f"{k} is not downstream of {target} but changed: {before[k]} -> {after[k]}"

    prop()


@pytest.mark.req("P-002-04")
def test_p_002_04_hand_checked_diamond(world) -> None:
    """a -> b, a -> c, b+c -> d, plus an unrelated e: changing b invalidates b and d only."""
    doc = recipe(
        "dag",
        [
            stage("s00_download", variant="a", params={"alpha": 1}),
            stage("s05_synthesize", variant="b", params={"alpha": 2}, inputs=[up("s00_download", "out.bin", "a")]),
            stage("s10_preprocess", variant="c", params={"alpha": 3}, inputs=[up("s00_download", "out.bin", "a")]),
            stage(
                "s20_feature_extraction",
                variant="d",
                params={"alpha": 4},
                inputs=[up("s05_synthesize", "out.bin", "b"), up("s10_preprocess", "out.bin", "c")],
            ),
            stage("st10_terrain", variant="e", params={"alpha": 5}),
        ],
        seed=11,
    )
    world.write_recipe(doc)
    refimpl.seed_store(world.store, world.repo, doc)
    before = statuses(world.plan_json("dag"))
    assert {s for s, _ in before.values()} == {"hit"}
    doc["stages"][1]["params"]["alpha"] = 99
    world.write_recipe(doc)
    after = statuses(world.plan_json("dag"))
    assert after["s05_synthesize@b"][0] == "miss"
    assert after["s20_feature_extraction@d"] == ("pending", None)
    for k in ("s00_download@a", "s10_preprocess@c", "st10_terrain@e"):
        assert after[k] == before[k]
