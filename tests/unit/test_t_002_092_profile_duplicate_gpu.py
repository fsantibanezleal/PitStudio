# ruff: noqa: E501, PT018
"""T-002-092: a machine profile that lists the same GPU index twice is rejected (G5 review).

Requirement: FR-002-64.

Expected behaviour: loading a profile whose `gpus` repeat an `index` fails with error class `profile-invalid`, and the one-line
message (exit code 2 on the command line) names the class and every repeated index; a profile with distinct indices (any
order, including the empty list) loads.
Oracle: hand-built profiles ([0, 0] rejected; [0, 1] accepted; [2, 2, 5, 5] names both 2 and 5).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import GIB, recipe, stage


def gpus(*indices: int) -> list[dict[str, Any]]:
    return [{"index": i, "vram_bytes": 16 * GIB, "power_class": "server"} for i in indices]


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path, recipes=[recipe("one", [stage("s10_preprocess")])])
    yield w
    rw.cleanup_world(w)


def plan(w: rw.World, **over: Any) -> rw.Result:
    w.write_profile(rw.profile_doc(**over))
    return w.cli("plan", str(w.recipes["one"]), "--profile", "test-profile")


@pytest.mark.req("FR-002-64")
@pytest.mark.parametrize(
    ("indices", "repeated"),
    [
        ((0, 0), ["0"]),
        ((0, 3, 3), ["3"]),
        ((2, 2, 5, 5), ["2", "5"]),
        ((7, 1, 7, 1, 7), ["7", "1"]),
        ((15, 15), ["15"]),
    ],
)
def test_fr_002_64_a_repeated_gpu_index_is_profile_invalid_and_named(
    world, indices: tuple[int, ...], repeated: list[str]
) -> None:
    r = plan(world, gpus=gpus(*indices))
    assert r.code == 2, r.text
    assert "profile-invalid" in r.text, r.text
    for idx in repeated:
        assert idx in r.text, f"the message must name the repeated index {idx}: {r.text!r}"
    assert len([ln for ln in r.text.splitlines() if ln.strip()]) == 1
    assert world.ledger_rows() == [] and world.run_dirs() == []


@pytest.mark.req("FR-002-64")
@pytest.mark.parametrize("indices", [(0, 1), (1, 0), (0, 1, 2, 3), (5, 3), (), (15,)])
def test_fr_002_64_distinct_gpu_indices_are_accepted_in_any_order(world, indices: tuple[int, ...]) -> None:
    r = plan(world, gpus=gpus(*indices))
    assert r.code == 0, r.text


@pytest.mark.req("FR-002-64")
def test_fr_002_64_the_check_applies_to_run_as_well_as_to_plan(world) -> None:
    world.write_profile(rw.profile_doc(gpus=gpus(0, 0)))
    r = world.cli("run", str(world.recipes["one"]), "--profile", "test-profile")
    assert r.code == 2 and "profile-invalid" in r.text
    assert world.ledger_rows() == []
