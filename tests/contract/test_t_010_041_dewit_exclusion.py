"""T-010-041: the real de Wit series never enters training, selection, C2ST or TSTR.

Requirement: FR-010-15 ("The training, validation and model-selection inputs of every C1 forecaster, and every
classifier
two-sample test or TSTR input of the product, shall exclude the de Wit-derived series: no such manifest lists its
SHA-256 among
its inputs").
Spec: specs/010-slope/spec.md section 3.2 (FR-010-15), section 8 (Constitution principle: a single real event is
reported
descriptively, never trained on); plan.md row FR-010-15 ("manifest inputs of the training, validation, C2ST and TSTR
stages
scanned for the de Wit digest").

Expected API (module `pitstudio.slope.exclusion`, standard library only):
- `GUARDED_STAGES`: the producers whose inputs must exclude the real series: stage `s30_train` (training, validation and
  model selection all run inside it) and the tools `c2st`, `tstr`, `model_selection`, `validation` (any stage).
- `leaks(manifest, dewit_sha256) -> list[dict]`: for a run manifest ({"artefacts": [{"id", "producer": {"tool",
  "stage"},
  "inputs": [{"id", "sha256", "kind"}]}]}) the list of {"artefact", "input", "pointer"} for every guarded artefact whose
  inputs list a digest in `dewit_sha256` (an iterable of lower-case hex digests: the derived series' and the archive's);
  `pointer` is the JSON pointer of the offending input ("/artefacts/1/inputs/0"). Digests compare case-insensitively.
  Unguarded producers (`s40_infer`, `s50_evaluate`, ...) may list the real series: evaluation and inference are
  descriptive.
- `assert_excluded(manifest, dewit_sha256) -> None`: raises `DewitLeakError(ValueError)` (attributes `error_class ==
  "dewit-in-training"`, `leaks`) when `leaks` is not empty. ValueError for a manifest that is not a mapping, has no
  `artefacts`
  list, or lists an input without a 64-hex sha256 (a malformed manifest cannot be proven clean).

Oracle: hand-built manifests (the digests are 64-hex literals written in the test); the rule of the spec read literally.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pitstudio.slope import exclusion

DEWIT_SERIES = "a" * 63 + "1"
DEWIT_ARCHIVE = "b" * 63 + "2"
SYNTH = "c" * 63 + "3"
OTHER = "d" * 63 + "4"


def _art(art_id: str, tool: str, stage: str, digests: list[str]) -> dict:
    return {
        "id": art_id,
        "producer": {"tool": tool, "stage": stage},
        "inputs": [{"id": f"in-{i}", "sha256": d, "kind": "artefact"} for i, d in enumerate(digests)],
    }


def _manifest(*artefacts) -> dict:
    return {"run_id": "20261115T101500Z-c1", "artefacts": list(artefacts)}


CLEAN = _manifest(
    _art("tcn-checkpoint", "pitstudio", "s30_train", [SYNTH, OTHER]),
    _art("tcn-predictions", "pitstudio", "s40_infer", [SYNTH, DEWIT_SERIES]),  # inference on the real series: allowed
    _art(
        "ttf-results", "pitstudio", "s50_evaluate", [DEWIT_SERIES, DEWIT_ARCHIVE, SYNTH]
    ),  # descriptive evaluation: allowed
)


@pytest.mark.req("FR-010-15")
def test_a_clean_run_lists_the_real_series_only_in_inference_and_evaluation() -> None:
    assert exclusion.leaks(CLEAN, {DEWIT_SERIES, DEWIT_ARCHIVE}) == []
    exclusion.assert_excluded(CLEAN, {DEWIT_SERIES, DEWIT_ARCHIVE})


@pytest.mark.req("FR-010-15")
@pytest.mark.parametrize("digest", [DEWIT_SERIES, DEWIT_ARCHIVE])
def test_the_training_stage_listing_the_derived_series_or_the_archive_is_a_leak(digest) -> None:
    m = copy.deepcopy(CLEAN)
    m["artefacts"][0]["inputs"].append({"id": "dewit", "sha256": digest, "kind": "artefact"})
    found = exclusion.leaks(m, {DEWIT_SERIES, DEWIT_ARCHIVE})
    assert found == [{"artefact": "tcn-checkpoint", "input": "dewit", "pointer": "/artefacts/0/inputs/2"}]
    with pytest.raises(exclusion.DewitLeakError) as exc:
        exclusion.assert_excluded(m, {DEWIT_SERIES, DEWIT_ARCHIVE})
    assert exc.value.error_class == "dewit-in-training"
    assert exc.value.leaks == found
    assert "tcn-checkpoint" in str(exc.value)


@pytest.mark.req("FR-010-15")
@pytest.mark.parametrize("tool", ["c2st", "tstr", "model_selection", "validation"])
def test_two_sample_tests_tstr_selection_and_validation_inputs_are_guarded_in_any_stage(tool) -> None:
    m = _manifest(_art("report", tool, "s50_evaluate", [SYNTH, DEWIT_SERIES]))
    found = exclusion.leaks(m, {DEWIT_SERIES})
    assert [f["artefact"] for f in found] == ["report"]
    with pytest.raises(exclusion.DewitLeakError):
        exclusion.assert_excluded(m, {DEWIT_SERIES})


@pytest.mark.req("FR-010-15")
def test_every_leak_is_reported_with_its_pointer_and_digests_compare_case_insensitively() -> None:
    m = _manifest(
        _art("a", "pitstudio", "s30_train", [DEWIT_SERIES.upper()]),
        _art("b", "pitstudio", "s40_infer", [DEWIT_SERIES]),
        _art("c", "c2st", "s50_evaluate", [OTHER, DEWIT_ARCHIVE]),
    )
    found = exclusion.leaks(m, {DEWIT_SERIES, DEWIT_ARCHIVE})
    assert found == [
        {"artefact": "a", "input": "in-0", "pointer": "/artefacts/0/inputs/0"},
        {"artefact": "c", "input": "in-1", "pointer": "/artefacts/2/inputs/1"},
    ]


@pytest.mark.req("FR-010-15")
def test_synthetic_inputs_never_match_and_an_empty_digest_set_finds_nothing() -> None:
    m = _manifest(_art("t", "pitstudio", "s30_train", [SYNTH, OTHER]))
    assert exclusion.leaks(m, {DEWIT_SERIES}) == []
    assert exclusion.leaks(CLEAN, set()) == []
    assert exclusion.leaks(_manifest(), {DEWIT_SERIES}) == []


@pytest.mark.req("FR-010-15")
@pytest.mark.parametrize(
    "bad",
    [
        [],
        "manifest",
        {"run_id": "x"},
        {"artefacts": "none"},
        {
            "artefacts": [
                {
                    "id": "t",
                    "producer": {"tool": "pitstudio", "stage": "s30_train"},
                    "inputs": [{"id": "i", "sha256": "xyz", "kind": "artefact"}],
                }
            ]
        },
        {
            "artefacts": [
                {
                    "id": "t",
                    "producer": {"tool": "pitstudio", "stage": "s30_train"},
                    "inputs": [{"id": "i", "kind": "artefact"}],
                }
            ]
        },
        {"artefacts": [{"id": "t", "inputs": []}]},
    ],
)
def test_a_malformed_manifest_cannot_be_proven_clean(bad) -> None:
    with pytest.raises(ValueError, match=r"."):
        exclusion.assert_excluded(bad, {DEWIT_SERIES})


@pytest.mark.req("FR-010-15")
def test_the_guarded_stages_constant_names_training_and_the_statistical_tools() -> None:
    assert "s30_train" in exclusion.GUARDED_STAGES
    assert {"c2st", "tstr"} <= set(exclusion.GUARDED_STAGES)
