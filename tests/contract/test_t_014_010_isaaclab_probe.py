# ruff: noqa: E501
"""T-014-010: `isaaclab` probe writer: schema, versions from the lock, pass rule.

Requirements: FR-014-02, DC-014-07.

Spec: specs/014-robot-learning/spec.md FR-014-02: "When the `isaaclab` capability probe runs, it shall train Isaac Lab's stock Cartpole direct task kit-less on the `newton_mjwarp` physics backend for >= 10 PPO iterations
with Isaac Sim absent, and record `pass` only if training finishes with finite losses, plus the versions read from the lock." DC-014-07: the `isaaclab` entry of `studio/capabilities.json` is valid against
`contracts/capabilities.schema.json` (DC-000-02). Verification: contract + gpu (local): this file is the contract half; the training run itself is the GPU task T-014-060.

Oracle: the lock read with `tomllib` (the reference parser) for the versions; the JSON Schema 2020-12 validator (`jsonschema`, reference implementation) for the capability entry; the pass rule written out by hand
(a run passes only with at least 10 completed PPO iterations whose every recorded loss is finite); the kit-module rule as a prefix list written out by hand.

Expected API of the implementation (the existing script `studio/bench/probe_isaaclab.py`, imported with `studio/bench` on sys.path; its module level imports only the standard library and `_common`, third-party
packages stay inside `body`):
    TASK == "Isaac-Cartpole-Direct" ; PHYSICS == "newton_mjwarp" ; ITERATIONS >= 10
    lock_versions() -> dict[str, str]
        the versions of the DISTS of the probe read from studio/isaaclab/uv.lock (not from the installed distributions): keys isaaclab, isaaclab_newton, isaaclab_tasks, isaaclab_rl, torch, torchvision, warp_lang,
        newton, mujoco, mujoco_warp, rsl_rl_lib
    evaluate_losses(losses, iterations_requested) -> tuple[str, str | None]
        (status, error): ("pass", None) when len(losses) >= iterations_requested and every value of every loss dict is finite; otherwise ("fail", message) where the message names "only N of M" for too few iterations
        and the iteration index and the key for the first non-finite value; a loss list of empty dicts, or iterations_requested < 10, is ("fail", message)
    kit_modules(module_names) -> list[str]
        the sorted names among module_names whose first dotted component is isaacsim, omni, carb, ovrtx, ovstage or ovphysx
    publish_marker() -> "public" | "local-only"          "local-only" when studio/isaaclab/uv.lock holds a package covered by SLA 8.9 (isaacsim*, omni*, ovrtx, ovstage, ovphysx), else "public"
"""

from __future__ import annotations

import json
import math
import sys
import tomllib
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "bench"))
import probe_isaaclab as probe  # noqa: E402

LOCK = tomllib.loads((ROOT / "studio" / "isaaclab" / "uv.lock").read_text("utf-8"))
BY_NAME = {p["name"]: p["version"] for p in LOCK["package"]}


def losses(n: int, **over: float) -> list[dict[str, float]]:
    return [{"value": 0.5 / (i + 1), "surrogate": -0.01, "entropy": 1.2, **over} for i in range(n)]


# ------------------------------------------------------------------------------------------------ constants
@pytest.mark.req("FR-014-02")
def test_the_probe_trains_the_stock_cartpole_direct_task_on_newton_mjwarp_for_at_least_10_iterations() -> None:
    assert probe.TASK == "Isaac-Cartpole-Direct"
    assert probe.PHYSICS == "newton_mjwarp"
    assert probe.ITERATIONS >= 10


# ------------------------------------------------------------------------------------------------ versions
@pytest.mark.req("FR-014-02")
def test_the_probe_versions_are_read_from_the_lock() -> None:
    v = probe.lock_versions()
    want = {d.replace("-", "_"): BY_NAME[d] for d in probe.DISTS}
    assert v == want
    assert v["torch"] == "2.11.0+cu128"
    assert v["rsl_rl_lib"] == "5.4.1"
    assert v["isaaclab"] == BY_NAME["isaaclab"]
    assert set(v) == {
        "isaaclab",
        "isaaclab_newton",
        "isaaclab_tasks",
        "isaaclab_rl",
        "torch",
        "torchvision",
        "warp_lang",
        "newton",
        "mujoco",
        "mujoco_warp",
        "rsl_rl_lib",
    }


@pytest.mark.req("FR-014-02")
def test_the_committed_probe_entry_is_valid_against_the_capability_schema_and_carries_the_lock_versions() -> None:
    schema = json.loads((ROOT / "contracts" / "capabilities.schema.json").read_text("utf-8"))
    doc = json.loads((ROOT / "studio" / "capabilities.json").read_text("utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(e.absolute_path))
    assert errors == []
    entry = doc["probes"]["isaaclab"]
    assert entry["status"] in {"pass", "fail", "skip"}
    lock = probe.lock_versions()
    for key, value in lock.items():
        assert entry["versions"][key] == value, key
    assert "python" in entry["versions"]
    assert "cuda" in entry["versions"]


# ------------------------------------------------------------------------------------------------ pass rule
@pytest.mark.req("FR-014-02")
@pytest.mark.parametrize("n", [10, 11, 50])
def test_ten_or_more_finite_iterations_pass(n) -> None:
    assert probe.evaluate_losses(losses(n), 10) == ("pass", None)


@pytest.mark.req("FR-014-02")
@pytest.mark.parametrize("n", [0, 1, 9])
def test_fewer_than_the_requested_iterations_fail_naming_the_counts(n) -> None:
    status, error = probe.evaluate_losses(losses(n), 10)
    assert status == "fail"
    assert f"only {n} of 10" in error


@pytest.mark.req("FR-014-02")
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_non_finite_loss_fails_naming_the_iteration_and_the_key(bad) -> None:
    ls = losses(12)
    ls[7]["entropy"] = bad
    status, error = probe.evaluate_losses(ls, 10)
    assert status == "fail"
    assert "7" in error
    assert "entropy" in error


@pytest.mark.req("FR-014-02")
def test_the_first_non_finite_iteration_is_the_one_reported() -> None:
    ls = losses(12)
    ls[9]["value"] = math.nan
    ls[4]["surrogate"] = math.inf
    status, error = probe.evaluate_losses(ls, 10)
    assert status == "fail"
    assert "4" in error
    assert "surrogate" in error


@pytest.mark.req("FR-014-02")
def test_empty_loss_records_and_a_request_below_the_minimum_fail() -> None:
    assert probe.evaluate_losses([{} for _ in range(12)], 10)[0] == "fail"
    assert probe.evaluate_losses(losses(12), 5)[0] == "fail"  # the requirement demands at least 10 iterations
    assert probe.evaluate_losses(losses(12), 0)[0] == "fail"


@pytest.mark.req("FR-014-02")
def test_more_iterations_than_requested_still_pass_when_every_value_is_finite() -> None:
    assert probe.evaluate_losses(losses(25), 10) == ("pass", None)


# ------------------------------------------------------------------------------------------------ Isaac Sim absent
@pytest.mark.req("FR-014-02")
def test_the_kit_module_rule_lists_isaac_sim_and_kit_modules() -> None:
    names = [
        "numpy",
        "torch",
        "isaaclab.app",
        "isaacsim.core.api",
        "omni.kit",
        "carb",
        "ovrtx",
        "ovstage.x",
        "ovphysx",
        "omnibus",
        "isaacsimfake",
        "carbon",
    ]
    assert probe.kit_modules(names) == ["carb", "isaacsim.core.api", "omni.kit", "ovphysx", "ovrtx", "ovstage.x"]
    assert probe.kit_modules([]) == []
    assert probe.kit_modules(["isaaclab", "isaaclab_tasks.direct", "rsl_rl"]) == []


# ------------------------------------------------------------------------------------------------ publish marker
@pytest.mark.req("FR-014-02")
def test_the_probe_publish_marker_follows_the_lock_and_is_local_only_for_the_real_lock() -> None:
    names = {n.lower() for n in BY_NAME}
    restricted = any(n.startswith(("isaacsim", "omni")) or n in {"ovrtx", "ovstage", "ovphysx"} for n in names)
    assert probe.publish_marker() == ("local-only" if restricted else "public")
    assert restricted  # the real lock holds ovstage
    assert probe.publish_marker() == "local-only"
