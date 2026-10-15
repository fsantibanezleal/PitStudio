# ruff: noqa: E501, PT018
"""T-002-046: `--rerun-check` (determinism verification) (US-002-4).

Requirement: FR-002-38.

Expected behaviour (stated for the implementer):
  * `studio run <recipe> --rerun-check` re-executes shard 0 of each `bitwise` and `statistical` stage into a scratch
    folder, bypassing the cache (even on a hit); that execution's job spec has `rerun: true`; nothing it writes enters the
    store; `none` stages are not re-executed;
  * the manifest stage record's `determinism.rerun_check` is `pass` iff every output SHA-256 of the re-execution equals
    the original (bitwise) or every DECLARED observable satisfies |a - b| <= atol + rtol * |b| (statistical), `fail`
    otherwise, `not-applicable` for `none` stages, `pending` when `--rerun-check` was not given; a statistical stage also
    gets `determinism.max_deviation` (a number >= 0 that grows with the deviation).
Oracles: hand-chosen observable values far from the tolerance boundary (so the choice of the reference value in b does
not matter), a deliberately non-deterministic fake stage, ledger counts of executions, store object sets.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import recipe, stage


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


def objects(world: rw.World) -> set[str]:
    d = world.store / "cas" / "sha256"
    return {f.name for f in d.rglob("*") if f.is_file()} if d.is_dir() else set()


def stat(rtol: float = 0.01, atol: float = 0.1, names: tuple[str, ...] = ("x",)) -> dict[str, Any]:
    return {"class": "statistical", "observables": {n: {"rtol": rtol, "atol": atol} for n in names}}


def rerun_rows(world: rw.World) -> list[dict[str, Any]]:
    return [r for r in world.starts() if r["rerun"]]


@pytest.mark.req("FR-002-38")
def test_fr_002_38_a_deterministic_bitwise_stage_passes_and_only_shard_0_is_re_executed(world) -> None:
    world.write_recipe(recipe("bitwise", [stage("st10_terrain", shardable=(1, 3), determinism="bitwise")]))
    r = world.run("bitwise", "--rerun-check")
    assert r.code == 0, r.text
    rows = world.starts()
    assert len(rows) == 4, "three shards plus one re-execution of shard 0"
    rr = rerun_rows(world)
    assert len(rr) == 1 and rr[0]["shard"] == 0 and rr[0]["job"]["rerun"] is True
    det = world.stage_record("st10_terrain")["determinism"]
    assert det["class"] == "bitwise" and det["rerun_check"] == "pass"


@pytest.mark.req("FR-002-38")
def test_fr_002_38_a_non_deterministic_bitwise_stage_fails_and_the_store_keeps_the_original_outputs(world) -> None:
    world.write_recipe(
        recipe("flaky", [stage("st10_terrain", determinism="bitwise", params={"nondeterministic": True})])
    )
    r = world.run("flaky", "--rerun-check")
    assert r.code in (0, 1), r.text
    assert world.stage_record("st10_terrain")["determinism"]["rerun_check"] == "fail"
    out = world.stage_record("st10_terrain")["outputs"]
    assert objects(world) == {o["sha256"] for o in out}, "the re-execution's different bytes must never enter the store"
    assert len(rerun_rows(world)) == 1


@pytest.mark.req("FR-002-38")
def test_fr_002_38_the_check_bypasses_the_cache_and_compares_with_the_cached_outputs(world) -> None:
    world.write_recipe(recipe("cached", [stage("st10_terrain", determinism="bitwise")]))
    assert world.run("cached").code == 0
    assert len(world.starts()) == 1
    import time

    time.sleep(1.1)
    assert world.run("cached", "--rerun-check").code == 0
    assert len(world.starts()) == 2, "a hit is still re-executed once for the check"
    assert rerun_rows(world)[0]["shard"] == 0
    assert world.stage_record("st10_terrain")["determinism"]["rerun_check"] == "pass"


@pytest.mark.req("FR-002-38")
@pytest.mark.parametrize(
    ("delta", "expected"), [(0.0, "pass"), (0.5, "pass"), (5.0, "fail"), (-5.0, "fail"), (-0.5, "pass")]
)
def test_fr_002_38_statistical_stage_uses_atol_plus_rtol_times_the_reference(
    world, delta: float, expected: str
) -> None:
    # x = 100: tolerance is 0.1 + 0.01 * 100 = 1.1 (1.105 with the other reference); 0.5 is well inside, 5 well outside
    st = stage("st10_terrain", determinism=stat(0.01, 0.1), params={"observables": {"x": 100.0}, "rerun_delta": delta})
    world.write_recipe(recipe("stat", [st]))
    r = world.run("stat", "--rerun-check")
    assert r.code in (0, 1), r.text
    det = world.stage_record("st10_terrain")["determinism"]
    assert det["class"] == "statistical" and det["rerun_check"] == expected
    assert isinstance(det["max_deviation"], (int, float)) and det["max_deviation"] >= 0
    if delta == 0.0:
        assert det["max_deviation"] == 0
    else:
        assert det["max_deviation"] > 0


@pytest.mark.req("FR-002-38")
def test_fr_002_38_max_deviation_grows_with_the_deviation(world) -> None:
    devs = []
    for delta in (0.5, 5.0):
        w_recipe = recipe(
            f"stat-{int(delta * 10)}",
            [
                stage(
                    "st10_terrain",
                    determinism=stat(0.01, 0.1),
                    params={"observables": {"x": 100.0}, "rerun_delta": delta},
                )
            ],
        )
        world.write_recipe(w_recipe)
        world.run(w_recipe["id"], "--rerun-check")
        devs.append(world.stage_record("st10_terrain")["determinism"]["max_deviation"])
    assert devs[0] < devs[1]


@pytest.mark.req("FR-002-38")
def test_fr_002_38_every_declared_observable_must_satisfy_its_own_tolerance(world) -> None:
    det = {"class": "statistical", "observables": {"x": {"rtol": 0.01, "atol": 0.1}, "y": {"rtol": 0.5, "atol": 1.0}}}
    ok = stage(
        "st10_terrain",
        determinism=det,
        params={"observables": {"x": 100.0, "y": 100.0}, "rerun_delta": 5.0, "rerun_delta_key": "y"},
    )
    world.write_recipe(recipe("two-ok", [ok]))
    world.run("two-ok", "--rerun-check")
    assert world.stage_record("st10_terrain")["determinism"]["rerun_check"] == "pass", (
        "y moved 5 (tolerance 51), x did not move"
    )
    bad = stage(
        "st10_terrain",
        determinism=det,
        params={"observables": {"x": 100.0, "y": 100.0}, "rerun_delta": 5.0, "rerun_delta_key": "x"},
    )
    world.write_recipe(recipe("two-bad", [bad]))
    world.run("two-bad", "--rerun-check")
    assert world.stage_record("st10_terrain")["determinism"]["rerun_check"] == "fail", "x moved 5 (tolerance 1.1)"


@pytest.mark.req("FR-002-38")
def test_fr_002_38_a_declared_observable_the_stage_does_not_report_fails_the_check(world) -> None:
    st = stage(
        "st10_terrain", determinism=stat(0.5, 5.0, names=("x", "missing_one")), params={"observables": {"x": 100.0}}
    )
    world.write_recipe(recipe("missing-obs", [st]))
    world.run("missing-obs", "--rerun-check")
    assert world.stage_record("st10_terrain")["determinism"]["rerun_check"] == "fail"


@pytest.mark.req("FR-002-38")
def test_fr_002_38_stages_of_class_none_are_not_applicable_and_not_re_executed(world) -> None:
    st = stage("st10_terrain", determinism={"class": "none", "reason": "hardware encoder output varies"})
    world.write_recipe(recipe("nodet", [st]))
    assert world.run("nodet", "--rerun-check").code == 0
    assert len(world.starts()) == 1 and rerun_rows(world) == []
    assert world.stage_record("st10_terrain")["determinism"]["rerun_check"] == "not-applicable"


@pytest.mark.req("FR-002-38")
def test_fr_002_38_without_the_flag_nothing_is_re_executed_and_the_check_is_pending(world) -> None:
    world.write_recipe(recipe("plain", [stage("st10_terrain", determinism="bitwise")]))
    assert world.run("plain").code == 0
    assert len(world.starts()) == 1
    assert world.stage_record("st10_terrain")["determinism"]["rerun_check"] == "pending"


@pytest.mark.req("FR-002-38")
def test_fr_002_38_a_failed_stage_is_not_re_checked(world) -> None:
    world.write_recipe(recipe("broken", [stage("st10_terrain", determinism="bitwise", params={"mode": "fail"})]))
    assert world.run("broken", "--rerun-check").code == 1
    assert len(world.starts()) == 1
