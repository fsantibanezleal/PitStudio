# ruff: noqa: E501
"""T-015-051: the display-only guard: no data, training or curation stage may take an artefact produced by the Cosmos tool as input.

Requirements: FR-015-39.

Spec: specs/015-vlm/spec.md FR-015-39 ("If a manifest of a data, training or curation stage (`s05_synthesize` to `s30_train`) lists an input produced by
the Cosmos tool, then CI shall fail (captions are display-only)"); plan.md test strategy row FR-015-39 ("manifest fixtures with a Cosmos-produced input in
`s30_train`"). Licence: NVIDIA Open Model License notice and the display-only class (spec section 7, constitution principle 11).

Oracle: hand-built run manifests in the shape of `specs/001-contracts/contracts/examples/manifest.valid.json` (`stages[].key.id`, `inputs[]` with `id`,
`sha256`, `kind`, `outputs[]` with `name`, `sha256`, `bytes`); an artefact is produced by the Cosmos tool when it is an output of a stage whose id begins
`st59` (`st59_reason_bench`, `st59a_vqa`, `st59b_plausibility`, `st59c_captions`); an input is that artefact when its `sha256` equals the output's or its `id` equals the
output's `name`. The checked stage ids are those `sNN_*` with 5 <= NN <= 30 (the range named by the spec); everything else (physics stages, the `st59`
stages themselves, the web publish step) is out of the rule.

Expected API of the implementation (package `pitstudio`, root environment), `pitstudio.reason.guards`:
- `check_display_only(manifests) -> list[Violation]`: `manifests` is a sequence of run-manifest dicts (the Cosmos stage and its consumer may be in different
  manifests); returns one `Violation(path, rule)` per offending stage input with `path == "<run_id>:<stage id>"` and `rule == "cosmos-output-as-input"`; an empty
  list when the rule holds. ValueError for a manifest whose `stages` is missing or not a list, or a stage without `key.id`.
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pitstudio.reason import guards

CAPTIONS_SHA = "c" * 64
RECORDS_SHA = "d" * 64
OTHER_SHA = "e" * 64


def _stage(stage_id: str, inputs: list[dict] | None = None, outputs: list[dict] | None = None) -> dict:
    return {"key": {"id": stage_id}, "status": "succeeded", "inputs": inputs or [], "outputs": outputs or []}


def _inp(artefact_id: str, sha: str) -> dict:
    return {"id": artefact_id, "sha256": sha, "kind": "artefact"}


def _out(name: str, sha: str) -> dict:
    return {"name": name, "sha256": sha, "bytes": 1024}


def _run(run_id: str, *stages: dict) -> dict:
    return {"kind": "run", "schema_version": "1.0", "run_id": run_id, "stages": list(stages)}


COSMOS_STAGE = _stage(
    "st59c_captions", outputs=[_out("reason/captions.json", CAPTIONS_SHA), _out("reason/records.json", RECORDS_SHA)]
)


@pytest.mark.req("FR-015-39")
def test_a_training_stage_that_takes_a_cosmos_output_by_digest_fails_the_check() -> None:
    m = _run("20261012T010000Z-b2", COSMOS_STAGE, _stage("s30_train", inputs=[_inp("captions", CAPTIONS_SHA)]))
    vs = guards.check_display_only([m])
    assert [(v.path, v.rule) for v in vs] == [("20261012T010000Z-b2:s30_train", "cosmos-output-as-input")]


@pytest.mark.req("FR-015-39")
def test_an_input_that_names_the_cosmos_output_fails_even_with_another_digest() -> None:
    m = _run("20261012T010000Z-b2", COSMOS_STAGE, _stage("s10_label", inputs=[_inp("reason/captions.json", OTHER_SHA)]))
    assert [v.path for v in guards.check_display_only([m])] == ["20261012T010000Z-b2:s10_label"]


@pytest.mark.req("FR-015-39")
def test_the_cosmos_stage_and_its_consumer_may_be_in_different_manifests() -> None:
    producer = _run("20261012T010000Z-b2", COSMOS_STAGE)
    consumer = _run("20261013T020000Z-b2", _stage("s20_curate", inputs=[_inp("x", RECORDS_SHA)]))
    vs = guards.check_display_only([producer, consumer])
    assert [v.path for v in vs] == ["20261013T020000Z-b2:s20_curate"]
    assert guards.check_display_only([consumer]) == []  # without the producing manifest there is nothing to match


@pytest.mark.req("FR-015-39")
@pytest.mark.parametrize(
    ("stage_id", "flagged"),
    [
        ("s04_ingest", False),
        ("s05_synthesize", True),
        ("s12_label", True),
        ("s30_train", True),
        ("s31_evaluate", False),
        ("s99_export", False),
        ("st50_physics", False),
        ("st56_encode", False),
        ("st59a_vqa", False),
        ("publish", False),
    ],
)
def test_only_the_data_training_and_curation_stages_s05_to_s30_are_checked(stage_id: str, flagged: bool) -> None:
    m = _run("20261012T010000Z-b2", COSMOS_STAGE, _stage(stage_id, inputs=[_inp("c", CAPTIONS_SHA)]))
    assert bool(guards.check_display_only([m])) is flagged


@pytest.mark.req("FR-015-39")
def test_every_offending_input_of_every_stage_is_reported() -> None:
    m = _run(
        "20261012T010000Z-b2",
        COSMOS_STAGE,
        _stage("s05_synthesize", inputs=[_inp("a", CAPTIONS_SHA), _inp("b", OTHER_SHA), _inp("c", RECORDS_SHA)]),
        _stage("s30_train", inputs=[_inp("d", CAPTIONS_SHA)]),
    )
    vs = guards.check_display_only([m])
    assert [v.path for v in vs] == [
        "20261012T010000Z-b2:s05_synthesize",
        "20261012T010000Z-b2:s05_synthesize",
        "20261012T010000Z-b2:s30_train",
    ]
    assert {v.rule for v in vs} == {"cosmos-output-as-input"}


@pytest.mark.req("FR-015-39")
def test_a_manifest_without_cosmos_output_in_a_stage_input_is_clean() -> None:
    m = _run(
        "20261012T010000Z-b2",
        _stage("st50_physics", outputs=[_out("physics/pile.npz", OTHER_SHA)]),
        COSMOS_STAGE,
        _stage("s30_train", inputs=[_inp("pile", OTHER_SHA), _inp("images", "a" * 64)]),
    )
    assert guards.check_display_only([m]) == []
    assert guards.check_display_only([]) == []


@pytest.mark.req("FR-015-39")
def test_the_check_does_not_modify_the_manifests() -> None:
    m = _run("20261012T010000Z-b2", COSMOS_STAGE, _stage("s30_train", inputs=[_inp("c", CAPTIONS_SHA)]))
    before = copy.deepcopy(m)
    guards.check_display_only([m])
    assert m == before


@pytest.mark.req("FR-015-39")
@pytest.mark.parametrize(
    "manifest",
    [
        pytest.param({"run_id": "r"}, id="no-stages"),
        pytest.param({"run_id": "r", "stages": "s30_train"}, id="stages-not-a-list"),
        pytest.param({"run_id": "r", "stages": [{"inputs": []}]}, id="stage-without-id"),
        pytest.param({"run_id": "r", "stages": [None]}, id="stage-not-a-mapping"),
        pytest.param(None, id="manifest-none"),
        pytest.param([], id="manifest-list"),
    ],
)
def test_a_malformed_manifest_is_refused(manifest: object) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        guards.check_display_only([manifest])  # type: ignore[list-item]


_IDS = st.sampled_from(
    ["s05_synthesize", "s10_label", "s20_curate", "s30_train", "s31_x", "st50_physics", "st59a_vqa", "s04_x"]
)


@pytest.mark.req("FR-015-39")
@given(st.lists(st.tuples(_IDS, st.booleans()), min_size=1, max_size=8))
def test_property_a_stage_is_flagged_if_and_only_if_it_is_in_range_and_takes_a_cosmos_output(
    stages: list[tuple[str, bool]],
) -> None:
    built = [_stage(sid, inputs=[_inp("x", CAPTIONS_SHA if takes else OTHER_SHA)]) for sid, takes in stages]
    got = [
        v.path.split(":", 1)[1] for v in guards.check_display_only([_run("20261012T010000Z-b2", COSMOS_STAGE, *built)])
    ]
    want = [
        sid
        for sid, takes in stages
        if takes and sid.startswith("s") and not sid.startswith("st") and 5 <= int(sid[1:3]) <= 30
    ]
    assert got == want
