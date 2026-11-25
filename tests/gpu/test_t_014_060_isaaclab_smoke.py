# ruff: noqa: E501
"""T-014-060 (GPU, local): kit-less smoke of the stock Cartpole task on `newton_mjwarp`.

Requirements: FR-014-02.

Spec: specs/014-robot-learning/spec.md FR-014-02: the probe "shall train Isaac Lab's stock Cartpole direct task kit-less on the `newton_mjwarp` physics backend for >= 10 PPO iterations with Isaac Sim absent, and record
`pass` only if training finishes with finite losses, plus the versions read from the lock." Marked `gpu`: runs only on the reference machine under the `gpu0.compute` lock, never in CI, not run in the red phase.

Oracle: the pass rule of the requirement evaluated on the raw loss list the entry point returns (every value finite, at least 10 iterations); the pinned lock (`tomllib` read of studio/isaaclab/uv.lock) for the versions;
the module list of the child process for "Isaac Sim absent" (no isaacsim, omni, carb, ovrtx, ovstage or ovphysx module imported); `torch.cuda` availability asserted in the child.

Expected API of the implementation (module `pitstudio_isaaclab.smoke` of the studio/isaaclab project, run with `python -m pitstudio_isaaclab.smoke --iterations N --num-envs M`): prints a last JSON line
{"status": "pass" | "fail", "task": "Isaac-Cartpole-Direct", "physics": "newton_mjwarp", "iterations_completed": int, "losses": [{name: float}, ...] (one dict per PPO iteration),
"kit_modules": [names of imported Isaac Sim / Kit modules], "versions": {isaaclab, torch, warp_lang, newton, mujoco, mujoco_warp, rsl_rl_lib, cuda}, "device": str} and exits 0 on pass.
"""

from __future__ import annotations

import math
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "support"))
import il_gpu_kit as kit  # noqa: E402

LOCK = {
    p["name"]: p["version"]
    for p in tomllib.loads((ROOT / "studio" / "isaaclab" / "uv.lock").read_text("utf-8"))["package"]
}


@pytest.fixture(scope="module")
def result():
    return kit.run_module("smoke", "--iterations", "10", "--num-envs", "64", timeout=1800)


@pytest.mark.gpu
@pytest.mark.req("FR-014-02")
def test_the_stock_cartpole_trains_ten_ppo_iterations_with_finite_losses(result) -> None:
    assert result["_returncode"] == 0
    assert result["status"] == "pass"
    assert result["task"] == "Isaac-Cartpole-Direct"
    assert result["physics"] == "newton_mjwarp"
    assert result["iterations_completed"] >= 10
    assert len(result["losses"]) >= 10
    for i, d in enumerate(result["losses"]):
        assert d, f"empty loss record at iteration {i}"
        assert all(math.isfinite(v) for v in d.values()), f"non-finite loss at iteration {i}: {d}"


@pytest.mark.gpu
@pytest.mark.req("FR-014-02")
def test_isaac_sim_is_absent_and_no_kit_module_was_imported(result) -> None:
    assert result["kit_modules"] == []
    assert not any(k.lower().startswith("isaacsim") for k in LOCK)


@pytest.mark.gpu
@pytest.mark.req("FR-014-02")
def test_the_recorded_versions_are_those_of_the_lock(result) -> None:
    v = result["versions"]
    assert v["torch"] == LOCK["torch"] == "2.11.0+cu128"
    assert v["warp_lang"] == LOCK["warp-lang"]
    assert v["newton"] == LOCK["newton"]
    assert v["mujoco"] == LOCK["mujoco"]
    assert v["mujoco_warp"] == LOCK["mujoco-warp"]
    assert v["rsl_rl_lib"] == LOCK["rsl-rl-lib"]
    assert v["isaaclab"] == LOCK["isaaclab"]
    assert v["cuda"] != "none"
    assert result["device"]


@pytest.mark.gpu
@pytest.mark.req("FR-014-02")
def test_fewer_than_ten_iterations_cannot_pass() -> None:
    short = kit.run_module("smoke", "--iterations", "3", "--num-envs", "16", timeout=900)
    assert short["status"] == "fail"
    assert short["_returncode"] != 0
