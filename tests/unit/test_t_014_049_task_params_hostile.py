# ruff: noqa: E501
"""T-014-049: hostile task parameters and resume with a mismatched configuration hash.

Requirements: FR-014-46.

Spec: specs/014-robot-learning/spec.md FR-014-46: "If the IL task parameters are invalid against `contracts/il-task.schema.json` - an unknown key,
a randomisation range with lower > upper bound or outside the FR-014-13 / FR-014-19 limits, a non-finite reward weight, an observation layout that
does not sum to 63 (IL-1) or 46 (IL-2), or evaluation seeds overlapping training seeds - or `--resume` names a checkpoint whose task-configuration
hash differs from the current one, then the IL stage shall exit with code 2 before any GPU work and name the field."

Oracle: the spec's hostile example corpus (`index.json`, entries of `il-task.schema.json` with `valid: false`, each with its JSON pointer and keyword,
built by the spec author); hand-built mutations of the valid examples for the rules the JSON Schema cannot express (a layout whose sizes sum to 64,
lower > upper, overlapping seed ranges, non-finite weights); the SHA-256 of the canonical JSON text of the parameters computed with `hashlib` over
`json.dumps(sort_keys=True, separators=(",", ":"))` (equal to RFC 8785 for these ASCII keys and plain numbers). "Before any GPU work" is checked with a
spy trainer factory that must never be called, and "name the field" by the JSON pointer in the message.

Expected API of the implementation:
    module `pitstudio.robots.config`
        TaskParamsError(ValueError): attributes `pointer` (str, the JSON pointer of the first offending member) and `exit_code` (int, 2);
            str(error) contains the pointer; for a root-level unknown key or missing member the pointer is "/<key>"
        validate_task_params(params) -> None                      raises TaskParamsError; accepts every valid example of the spec corpus
        config_hash(params) -> str                                SHA-256 hex of the canonical JSON of the whole parameter document
    module `pitstudio.robots.training` (see T-014-040)
        run_stage(params, make_trainer, out_dir, *, resume=None) -> StageResult
            an invalid document ends with StageResult.exit_code == 2 and a message naming the pointer, before `make_trainer` is called and before anything
            is written under out_dir; a `resume` checkpoint whose sidecar `task_config_sha256` differs from config_hash(params) ends the same way with the
            message naming `task_config_sha256`; a resume checkpoint without a readable sidecar ends with exit code 2 naming `checkpoint`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from pathlib import Path

import pytest
from pitstudio.robots.config import TaskParamsError, config_hash, validate_task_params
from pitstudio.robots.training import run_stage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import il_fake_trainer as fk

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "014-robot-learning" / "contracts" / "examples"
IL1 = json.loads((EX / "il-task.valid.json").read_text("utf-8"))
IL2 = json.loads((EX / "il-task.valid-il2.json").read_text("utf-8"))
MPM = json.loads((EX / "il-task.valid-mpm.json").read_text("utf-8"))


def digest(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def mutate(base: dict, path: list, value) -> dict:
    doc = copy.deepcopy(base)
    node = doc
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return doc


# --------------------------------------------------------------------------------------------- valid documents
@pytest.mark.req("FR-014-46")
@pytest.mark.parametrize("doc", [IL1, IL2, MPM], ids=["il1", "il2", "mpm"])
def test_the_valid_spec_examples_are_accepted(doc) -> None:
    validate_task_params(doc)


@pytest.mark.req("FR-014-46")
def test_the_configuration_hash_is_the_sha256_of_the_canonical_json() -> None:
    assert config_hash(IL1) == digest(IL1)
    assert config_hash(IL2) == digest(IL2)
    assert config_hash(copy.deepcopy(IL1)) == config_hash(IL1)
    reordered = dict(reversed(list(IL1.items())))
    assert config_hash(reordered) == config_hash(IL1)  # key order does not matter
    assert config_hash(mutate(IL1, ["reward_weights", "jerk"], 0.02)) != config_hash(IL1)
    assert config_hash(mutate(IL1, ["seeds", "train", "count"], 4097)) != config_hash(IL1)


# ------------------------------------------------------------------------------------------ spec hostile corpus
def corpus() -> list:
    index = json.loads((EX / "index.json").read_text("utf-8"))["examples"]
    out = []
    for e in index:
        if e["schema"] == "il-task.schema.json" and not e["valid"]:
            doc = json.loads((EX / e["file"]).read_text("utf-8"))
            out.append(pytest.param(e["file"], e["pointer"], doc, id=e["file"]))
    return out


def pattern_for(pointer: str, doc: dict) -> str:
    """The pointer, or for a root-level problem the unknown key when there is one, else any non-empty message."""
    if pointer:
        return pointer
    known = set(IL1) | set(IL2) | set(MPM)
    unknown = {k for k in doc if k not in known} if isinstance(doc, dict) else set()
    return "|".join(sorted(unknown)) if unknown else r".+"


@pytest.mark.req("FR-014-46")
@pytest.mark.parametrize(("file", "pointer", "doc"), corpus())
def test_every_hostile_example_of_the_spec_is_rejected_naming_its_pointer(file, pointer, doc) -> None:
    with pytest.raises(TaskParamsError, match=pattern_for(pointer, doc)) as info:
        validate_task_params(doc)
    assert info.value.exit_code == 2
    assert isinstance(info.value, ValueError)
    if pointer:
        assert info.value.pointer.startswith(pointer)  # a nested unknown key may extend the schema pointer


@pytest.mark.req("FR-014-46")
@pytest.mark.parametrize(("file", "pointer", "doc"), corpus())
def test_the_stage_exits_2_before_any_trainer_is_built_and_writes_nothing(file, pointer, doc, tmp_path: Path) -> None:
    f = fk.Factory()
    out = tmp_path / "run"
    res = run_stage(doc, f, out)
    assert res.exit_code == 2
    assert f.trainers == []  # no GPU work: the trainer factory was never called
    assert not out.exists() or list(out.rglob("*")) == []
    assert (pointer or "").split("/")[-1] in res.message or pointer == ""


# ----------------------------------------------------------------------------- rules beyond the JSON Schema
CHECKER = [
    # (base, path, value, pointer-regex)
    (IL1, ["randomisation", "payload_fraction"], [0.8, 0.2], "/randomisation/payload_fraction"),
    (IL1, ["randomisation", "rolling_resistance_pct"], [8, 2], "/randomisation/rolling_resistance_pct"),
    (IL1, ["randomisation", "friction_dry"], [0.75, 0.55], "/randomisation/friction_dry"),
    (IL1, ["randomisation", "friction_wet"], [0.45, 0.25], "/randomisation/friction_wet"),
    (IL1, ["randomisation", "actuator_delay_steps"], [3, 0], "/randomisation/actuator_delay_steps"),
    (IL2, ["randomisation", "bulk_density_kg_m3"], [2100, 1500], "/randomisation/bulk_density_kg_m3"),
    (IL2, ["randomisation", "cohesion_kpa"], [20, 0], "/randomisation/cohesion_kpa"),
    (IL2, ["randomisation", "friction_angle_deg"], [40, 25], "/randomisation/friction_angle_deg"),
    (IL2, ["randomisation", "soil_tool_friction_deg"], [25, 10], "/randomisation/soil_tool_friction_deg"),
    (
        IL1,
        ["randomisation", "rolling_resistance_pct"],
        [2, 9],
        "/randomisation/rolling_resistance_pct",
    ),  # beyond the FR-014-13 limit
    (
        IL2,
        ["randomisation", "friction_angle_deg"],
        [20, 40],
        "/randomisation/friction_angle_deg",
    ),  # below the FR-014-19 limit
    (IL1, ["reward_weights", "jerk"], math.nan, "/reward_weights/jerk"),
    (IL1, ["reward_weights", "progress"], math.inf, "/reward_weights/progress"),
    (IL1, ["reward_weights", "energy"], -math.inf, "/reward_weights/energy"),
    (IL1, ["reward_weights", "collision"], "100", "/reward_weights/collision"),
    (IL2, ["reward_weights", "stall"], math.nan, "/reward_weights/stall"),
    (IL1, ["observation_layout", 2, "size"], 21, "/observation_layout"),  # sizes sum to 64
    (IL1, ["observation_layout", 4, "size"], 31, "/observation_layout"),  # sizes sum to 62
    (IL2, ["observation_layout", 4, "size"], 29, "/observation_layout"),  # sum 45
    (IL2, ["observation_layout", 4, "size"], 31, "/observation_layout"),  # sum 47
    (IL1, ["seeds", "eval", "start"], 100, "/seeds"),  # eval 100..199 inside train 0..4095
    (IL1, ["seeds", "train", "start"], 999_950, "/seeds"),  # train starts 50 before the eval range and overlaps it
    (IL2, ["seeds", "eval", "start"], 4000, "/seeds"),
    (IL2, ["seeds", "tune", "start"], 1_000_050, "/seeds"),  # tune inside eval
    (IL1, ["training", "iterations"], "100", "/training/iterations"),
    (IL1, ["training", "num_envs"], 0, "/training/num_envs"),
    (IL1, ["training", "num_envs"], 1.5, "/training/num_envs"),
    (IL1, ["control_hz"], 10, "/control_hz"),
    (IL1, ["zz_unknown_key"], 1, "zz_unknown_key"),
    (IL2, ["zz_unknown_key"], {"a": 1}, "zz_unknown_key"),
    (IL1, ["randomisation", "zz_extra"], 1, "zz_extra"),
    (IL1, ["reward_weights", "bonus"], 1.0, "reward_weights"),
]


@pytest.mark.req("FR-014-46")
@pytest.mark.parametrize(
    ("base", "path", "value", "pointer"),
    CHECKER,
    ids=[f"{b['policy']}:{'/'.join(map(str, p))}={v}" for b, p, v, _ in CHECKER],
)
def test_rules_beyond_the_schema_are_rejected_naming_the_field(base, path, value, pointer) -> None:
    doc = mutate(base, path, value)
    with pytest.raises(TaskParamsError, match=pointer) as info:
        validate_task_params(doc)
    assert info.value.exit_code == 2


@pytest.mark.req("FR-014-46")
@pytest.mark.parametrize("bad", [None, [], "IL-1", 7, [IL1]])
def test_a_document_that_is_not_an_object_is_rejected(bad) -> None:
    with pytest.raises(TaskParamsError, match=r".+") as info:
        validate_task_params(bad)
    assert info.value.exit_code == 2


@pytest.mark.req("FR-014-46")
def test_adjacent_seed_ranges_are_not_an_overlap() -> None:
    doc = copy.deepcopy(IL1)
    doc["seeds"]["train"] = {"start": 999_900, "count": 100}  # ends exactly where eval starts (1,000,000)
    validate_task_params(doc)
    doc["seeds"]["train"] = {"start": 999_901, "count": 100}  # one shared seed
    with pytest.raises(TaskParamsError, match="/seeds"):
        validate_task_params(doc)


@pytest.mark.req("FR-014-46")
def test_a_narrower_randomisation_range_is_accepted() -> None:
    doc = mutate(IL1, ["randomisation", "payload_fraction"], [0.2, 0.8])
    validate_task_params(doc)
    doc = mutate(IL1, ["randomisation", "friction_dry"], [0.6, 0.6])  # a degenerate range lower == upper is allowed
    validate_task_params(doc)


@pytest.mark.req("FR-014-46")
@pytest.mark.parametrize(("base", "path", "value", "pointer"), CHECKER[:12] + CHECKER[16:24], ids=lambda v: str(v)[:24])
def test_the_stage_exits_2_for_rule_violations_without_calling_the_trainer(
    base, path, value, pointer, tmp_path: Path
) -> None:
    f = fk.Factory()
    res = run_stage(mutate(base, path, value), f, tmp_path / "run")
    assert res.exit_code == 2
    assert f.trainers == []
    assert not (tmp_path / "run").exists() or list((tmp_path / "run").rglob("*")) == []
    assert pointer.split("|")[0] in res.message


# ---------------------------------------------------------------------------------------- resume hash mismatch
def small(doc: dict) -> dict:
    d = copy.deepcopy(doc)
    d["training"]["iterations"] = 150
    d["training"]["num_envs"] = 512
    return d


@pytest.mark.req("FR-014-46")
def test_resume_with_a_checkpoint_of_a_different_configuration_exits_2_before_building_a_trainer(
    tmp_path: Path,
) -> None:
    base = small(IL1)
    run_stage(base, fk.Factory(), tmp_path)  # writes checkpoints 100 and 150 with the hash of `base`
    ckpt = tmp_path / "checkpoints" / "model_100.pt"
    side = json.loads(ckpt.with_suffix(".json").read_text("utf-8"))
    assert side["task_config_sha256"] == digest(
        base
    )  # the hash recorded next to the checkpoint is the canonical-JSON hash

    changed = mutate(base, ["reward_weights", "jerk"], 0.02)  # a different configuration, still valid
    f = fk.Factory()
    res = run_stage(changed, f, tmp_path, resume=ckpt)
    assert res.exit_code == 2
    assert f.trainers == []
    assert "task_config_sha256" in res.message


@pytest.mark.req("FR-014-46")
def test_resume_with_the_same_configuration_is_accepted(tmp_path: Path) -> None:
    base = small(IL1)
    run_stage(base, fk.Factory(), tmp_path)
    f = fk.Factory()
    res = run_stage(base, f, tmp_path, resume=tmp_path / "checkpoints" / "model_100.pt")
    assert res.exit_code == 0
    assert f.trainers[0].state == fk.expected_state(150)


@pytest.mark.req("FR-014-46")
@pytest.mark.parametrize("field", [("training", "iterations"), ("seeds", "eval", "start"), ("control_hz",)])
def test_any_change_of_the_parameters_changes_the_hash_and_blocks_a_resume(field, tmp_path: Path) -> None:
    base = small(IL1)
    run_stage(base, fk.Factory(), tmp_path)
    new = copy.deepcopy(base)
    node = new
    for key in field[:-1]:
        node = node[key]
    node[field[-1]] = node[field[-1]] + 1 if field != ("control_hz",) else node[field[-1]]
    if field == ("control_hz",):
        new["seeds"]["eval"]["start"] += 7
    f = fk.Factory()
    res = run_stage(new, f, tmp_path, resume=tmp_path / "checkpoints" / "model_100.pt")
    assert res.exit_code == 2
    assert f.trainers == []


@pytest.mark.req("FR-014-46")
def test_resume_with_a_missing_or_unreadable_sidecar_exits_2_naming_the_checkpoint(tmp_path: Path) -> None:
    base = small(IL1)
    run_stage(base, fk.Factory(), tmp_path)
    ckpt = tmp_path / "checkpoints" / "model_100.pt"
    ckpt.with_suffix(".json").unlink()
    f = fk.Factory()
    res = run_stage(base, f, tmp_path, resume=ckpt)
    assert res.exit_code == 2
    assert f.trainers == []
    assert "checkpoint" in res.message
    nowhere = run_stage(base, f, tmp_path, resume=tmp_path / "checkpoints" / "model_999.pt")
    assert nowhere.exit_code == 2
    assert f.trainers == []
    ckpt.with_suffix(".json").write_text("{not json", encoding="utf-8")
    broken = run_stage(base, f, tmp_path, resume=ckpt)
    assert broken.exit_code == 2
    assert f.trainers == []


@pytest.mark.req("FR-014-46")
def test_a_hash_mismatch_does_not_touch_the_existing_checkpoints(tmp_path: Path) -> None:
    base = small(IL1)
    run_stage(base, fk.Factory(), tmp_path)
    before = {p.name: p.read_bytes() for p in (tmp_path / "checkpoints").iterdir()}
    run_stage(
        mutate(base, ["reward_weights", "jerk"], 0.03),
        fk.Factory(),
        tmp_path,
        resume=tmp_path / "checkpoints" / "model_100.pt",
    )
    after = {p.name: p.read_bytes() for p in (tmp_path / "checkpoints").iterdir()}
    assert after == before
