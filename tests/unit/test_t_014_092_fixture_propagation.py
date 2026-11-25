# ruff: noqa: E501
"""T-014-092 (root half): fixture propagation through the IL training stage.

Requirements: FR-014-48.

Spec: specs/014-robot-learning/spec.md FR-014-48: "While an IL task file, a machine parameter file or a policy handoff (DC-014-01 to DC-014-03) is a contract fixture, the IL stages, the twin runner and `s50_evaluate` shall
run against it, shall write `fixture: true` on every policy, episode table and report, and shall publish no sim-to-sim gap computed from it." FR-000-23: a contract fixture (`fixture: true`) is never presented as a
result and is excluded from release builds. Module map, availability state `fixture`: "built and tested against it; never shown as a result".

This half covers the training stage (the policy artefacts) and the helpers that decide fixture status; the evaluation, gap and export halves are in tests/pipeline/test_t_014_092_fixture_propagation_pipeline.py.

Oracle: hand construction (the example files of the spec are the contract fixtures; a path under `runs/` is not); the stage must still train exactly as for a real input (the closed-form state of the fake trainer of
tests/support/il_fake_trainer.py), so that "run against it" is checked, and the marks are literal `true` / absent values in the JSON files and the manifest.

Expected API of the implementation (module `pitstudio.robots.fixture` and `pitstudio.robots.training`):
    is_fixture(path=None, *, flag=None) -> bool
        flag True / False decides (an explicit flag overrides the location); otherwise True when `path` has the consecutive directory names `contracts`, `examples` or `data`, `samples` among its parts (a file under a
        `contracts/examples/` or a `data/samples/` folder), else False; path None and flag None give False. TypeError or ValueError naming `flag` for a flag that is neither a bool nor None.
    is_publishable(artefact) -> bool                           False when artefact.get("fixture") is True, else True (FR-000-23: a fixture is not a result)
    run_stage(params, make_trainer, out_dir, *, resume=None, fixture=None, params_path=None) -> StageResult
        fixture = is_fixture(params_path, flag=fixture); the stage trains as usual; the manifest gets "fixture": <bool>; when True every sidecar `model_<i>.json` also holds "fixture": true (and no sidecar of a real run
        holds the key set to true).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from pitstudio.robots.fixture import is_fixture, is_publishable
from pitstudio.robots.training import run_stage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import il_fake_trainer as fk

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "specs" / "014-robot-learning" / "contracts" / "examples"
IL1 = json.loads((EXAMPLES / "il-task.valid.json").read_text("utf-8"))


def small(n: int = 250) -> dict:
    d = copy.deepcopy(IL1)
    d["training"]["iterations"] = n
    d["training"]["num_envs"] = 512
    return d


# ------------------------------------------------------------------------------------------------ is_fixture
@pytest.mark.req("FR-014-48")
@pytest.mark.parametrize(
    "name",
    [
        "il-task.valid.json",
        "machine-params.valid.json",
        "machine-params.valid-excavator.json",
        "il-policy-handoff.valid.json",
        "il-twin.valid.json",
    ],
)
def test_the_spec_example_files_are_contract_fixtures_by_location(name) -> None:
    assert is_fixture(EXAMPLES / name) is True
    assert is_fixture(str(EXAMPLES / name)) is True


@pytest.mark.req("FR-014-48")
@pytest.mark.parametrize(
    "path",
    [
        "data/samples/il-task.json",
        "C:/repo/data/samples/x/machine.json",
        "/home/u/repo/specs/014-robot-learning/contracts/examples/il-task.valid.json",
    ],
)
def test_files_under_contracts_examples_or_data_samples_are_fixtures_whatever_the_prefix(path) -> None:
    assert is_fixture(path) is True


@pytest.mark.req("FR-014-48")
@pytest.mark.parametrize(
    "path",
    [
        "runs/r1/params.json",
        "studio/recipes/cases/a2.yaml",
        "contracts/il-task.schema.json",
        "data/raw/x.json",
        "examples/il-task.json",
        "samples/x.json",
        "contracts/examples.json",
    ],
)
def test_other_files_are_not_fixtures(path) -> None:
    assert is_fixture(path) is False


@pytest.mark.req("FR-014-48")
def test_no_path_and_no_flag_is_not_a_fixture_and_the_flag_overrides_the_location() -> None:
    assert is_fixture() is False
    assert is_fixture(flag=True) is True
    assert is_fixture("runs/r1/params.json", flag=True) is True
    assert is_fixture(EXAMPLES / "il-task.valid.json", flag=False) is False


@pytest.mark.req("FR-014-48")
@pytest.mark.parametrize("flag", [1, 0, "yes", "true", [], 1.0])
def test_a_flag_that_is_not_a_bool_is_rejected_naming_it(flag) -> None:
    with pytest.raises((TypeError, ValueError), match=r"\bflag\b"):
        is_fixture("runs/r1/params.json", flag=flag)


@pytest.mark.req("FR-014-48")
def test_a_fixture_is_not_publishable_and_a_real_artefact_is() -> None:
    assert is_publishable({"fixture": True, "status": "complete"}) is False
    assert is_publishable({"fixture": False}) is True
    assert is_publishable({"status": "complete"}) is True
    assert (
        is_publishable({"fixture": "true"}) is True
    )  # only the boolean True marks a fixture (the contract field is a boolean)


# ------------------------------------------------------------------------------------------------ training stage
@pytest.mark.req("FR-014-48")
def test_a_stage_run_on_a_fixture_task_file_trains_as_usual_and_marks_the_manifest_and_every_checkpoint(
    tmp_path: Path,
) -> None:
    f = fk.Factory()
    res = run_stage(small(250), f, tmp_path, params_path=EXAMPLES / "il-task.valid.json")
    assert res.exit_code == 0
    assert f.trainers[0].state == fk.expected_state(
        250
    )  # the stage ran against the fixture exactly as it would on a real input
    assert res.manifest["fixture"] is True
    sidecars = sorted((tmp_path / "checkpoints").glob("model_*.json"))
    assert [p.name for p in sidecars] == ["model_100.json", "model_200.json", "model_250.json"]
    for p in sidecars:
        assert json.loads(p.read_text("utf-8"))["fixture"] is True
    assert is_publishable(res.manifest) is False


@pytest.mark.req("FR-014-48")
def test_an_explicit_fixture_flag_marks_a_run_whose_files_are_not_in_a_fixture_folder(tmp_path: Path) -> None:
    f = fk.Factory()
    res = run_stage(small(120), f, tmp_path, fixture=True, params_path=tmp_path / "params.json")
    assert res.manifest["fixture"] is True
    for p in (tmp_path / "checkpoints").glob("model_*.json"):
        assert json.loads(p.read_text("utf-8"))["fixture"] is True


@pytest.mark.req("FR-014-48")
def test_a_real_run_is_not_marked(tmp_path: Path) -> None:
    f = fk.Factory()
    res = run_stage(small(120), f, tmp_path, params_path=tmp_path / "runs" / "params.json")
    assert res.manifest["fixture"] is False
    for p in (tmp_path / "checkpoints").glob("model_*.json"):
        assert json.loads(p.read_text("utf-8")).get("fixture") is not True
    assert is_publishable(res.manifest) is True


@pytest.mark.req("FR-014-48")
def test_fixture_false_overrides_the_fixture_location_and_a_missing_path_means_not_a_fixture(tmp_path: Path) -> None:
    res = run_stage(small(60), fk.Factory(), tmp_path / "a", fixture=False, params_path=EXAMPLES / "il-task.valid.json")
    assert res.manifest["fixture"] is False
    res = run_stage(small(60), fk.Factory(), tmp_path / "b")
    assert res.manifest["fixture"] is False


@pytest.mark.req("FR-014-48")
def test_a_fixture_run_that_hits_the_oom_fallback_stays_marked(tmp_path: Path) -> None:
    f = fk.Factory(fail_at=lambda i, n: fk.OutOfMemoryError("CUDA out of memory") if (i == 150 and n >= 512) else None)
    res = run_stage(small(250), f, tmp_path, fixture=True)
    assert res.exit_code == 0
    assert res.manifest["oom_fallback"]["to"] == 256
    assert res.manifest["fixture"] is True
    for p in (tmp_path / "checkpoints").glob("model_*.json"):
        assert json.loads(p.read_text("utf-8"))["fixture"] is True


@pytest.mark.req("FR-014-48")
@pytest.mark.parametrize("bad", [1, "yes", []])
def test_a_non_boolean_fixture_argument_of_the_stage_is_rejected_naming_it(bad, tmp_path: Path) -> None:
    f = fk.Factory()
    with pytest.raises((TypeError, ValueError), match=r"\bfixture\b|\bflag\b"):
        run_stage(small(10), f, tmp_path, fixture=bad)
    assert f.trainers == []
