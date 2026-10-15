"""T-010-097: a displacement series or slope section whose digest changed fails `input-stale` before any step.

Requirement: FR-010-48 ("If the digest of a displacement series or slope section recorded in a training or evaluation
manifest
differs from the digest of the file now present, then the stage shall fail with error class `input-stale` (FR-002-69)
naming
the series, and shall produce no checkpoint or result from it").
Spec: specs/010-slope/spec.md section 3.4 (FR-010-48); plan.md row FR-010-48 ("one altered sample gives `input-stale`
naming
the series; an unaltered series passes").

Expected API (module `pitstudio.slope.inputs`, standard library only; the same shape as spec 011's helper, which the
implementation may share):
- `InputStaleError(Exception)`: `error_class == "input-stale"`, `series` (the manifest id of the stale input),
  `expected` and
  `actual` (64-hex digests); the message names the series and both digests.
- `verify_inputs(inputs, *, root) -> None`: `inputs` is a list of {"id", "path" (relative to root), "sha256"}; raises
  InputStaleError for the first input, in manifest order, whose file digest differs from the recorded one; a missing
  file
  raises InputStaleError too (actual = None).
- `run_stage(stage, manifest, *, root, work) -> object`: stage in {"s30_train", "s40_infer", "s50_evaluate"}; verifies
  `manifest["inputs"], then returns `work()`; never calls `work` when an input is stale (so no checkpoint, prediction or
  result exists); ValueError for any other stage name.

Oracle: hand calculation with `hashlib.sha256` computed in the test; one altered sample (one digit of one displacement
value)
changes the digest.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pitstudio.slope.inputs import InputStaleError, run_stage, verify_inputs

STAGES = ["s30_train", "s40_infer", "s50_evaluate"]


def _write(root: Path) -> list[dict]:
    series = {
        "kind": "synthetic-event",
        "event_id": "voight-test-snr-obs-000123",
        "t_h": [0.0, 3.75, 7.5, 11.25],
        "los_displacement_mm": [0.0, 0.315, 0.635, 0.9602],
    }
    section = {"section_id": "c1-planar-20m-45deg", "ground": [[0.0, 20.0], [20.0, 20.0], [40.0, 0.0]]}
    files = {
        "voight-test-snr-obs-000123.json": json.dumps(series).encode(),
        "c1-planar-20m-45deg.json": json.dumps(section).encode(),
        "voight-test-snr-obs-000124.json": json.dumps({**series, "event_id": "voight-test-snr-obs-000124"}).encode(),
    }
    entries = []
    for name, data in files.items():
        (root / name).write_bytes(data)
        entries.append({"id": name.removesuffix(".json"), "path": name, "sha256": hashlib.sha256(data).hexdigest()})
    return entries


def _alter_one_sample(path: Path) -> str:
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["los_displacement_mm"][2] = 0.636  # one digit of one sample
    path.write_text(json.dumps(doc), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.req("FR-010-48")
@pytest.mark.parametrize("stage", STAGES)
def test_unchanged_inputs_pass_and_the_work_runs_exactly_once(tmp_path: Path, stage: str) -> None:
    manifest = {"inputs": _write(tmp_path)}
    calls: list[str] = []
    assert run_stage(stage, manifest, root=tmp_path, work=lambda: calls.append(stage) or "done") == "done"
    assert calls == [stage]
    verify_inputs(manifest["inputs"], root=tmp_path)


@pytest.mark.req("FR-010-48")
@pytest.mark.parametrize("stage", STAGES)
def test_one_altered_sample_fails_input_stale_naming_the_series_before_any_work(tmp_path: Path, stage: str) -> None:
    manifest = {"inputs": _write(tmp_path)}
    old = manifest["inputs"][0]["sha256"]
    new = _alter_one_sample(tmp_path / "voight-test-snr-obs-000123.json")
    assert new != old
    calls: list[int] = []
    with pytest.raises(InputStaleError, match="voight-test-snr-obs-000123") as info:
        run_stage(stage, manifest, root=tmp_path, work=lambda: calls.append(1))
    err = info.value
    assert err.error_class == "input-stale"
    assert err.series == "voight-test-snr-obs-000123"
    assert (err.expected, err.actual) == (old, new)
    assert old in str(err)
    assert new in str(err)
    assert calls == []  # no checkpoint, prediction file or result was produced


@pytest.mark.req("FR-010-48")
def test_a_slope_section_is_checked_like_a_series(tmp_path: Path) -> None:
    manifest = {"inputs": _write(tmp_path)}
    path = tmp_path / "c1-planar-20m-45deg.json"
    path.write_bytes(path.read_bytes().replace(b"40.0", b"41.0"))
    with pytest.raises(InputStaleError, match="c1-planar-20m-45deg") as info:
        run_stage("s50_evaluate", manifest, root=tmp_path, work=lambda: None)
    assert info.value.series == "c1-planar-20m-45deg"


@pytest.mark.req("FR-010-48")
def test_the_first_stale_input_in_manifest_order_is_named_and_the_files_are_untouched(tmp_path: Path) -> None:
    manifest = {"inputs": _write(tmp_path)}
    _alter_one_sample(tmp_path / "voight-test-snr-obs-000124.json")
    _alter_one_sample(tmp_path / "voight-test-snr-obs-000123.json")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(InputStaleError) as info:
        verify_inputs(manifest["inputs"], root=tmp_path)
    assert info.value.series == "voight-test-snr-obs-000123"
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.req("FR-010-48")
def test_a_missing_file_is_stale_too(tmp_path: Path) -> None:
    manifest = {"inputs": _write(tmp_path)}
    (tmp_path / "voight-test-snr-obs-000124.json").unlink()
    with pytest.raises(InputStaleError, match="voight-test-snr-obs-000124") as info:
        verify_inputs(manifest["inputs"], root=tmp_path)
    assert info.value.actual is None


@pytest.mark.req("FR-010-48")
@pytest.mark.parametrize("stage", ["s10_preprocess", "s05_synthesize", "", "S30_TRAIN", "s60_export"])
def test_only_training_inference_and_evaluation_are_guarded(tmp_path: Path, stage: str) -> None:
    with pytest.raises(ValueError, match="stage"):
        run_stage(stage, {"inputs": _write(tmp_path)}, root=tmp_path, work=lambda: None)


@pytest.mark.req("FR-010-48")
def test_an_empty_input_list_passes_and_hostile_digests_are_stale(tmp_path: Path) -> None:
    assert run_stage("s30_train", {"inputs": []}, root=tmp_path, work=lambda: 7) == 7
    entries = _write(tmp_path)
    for bad in ("", "0" * 63, "g" * 64, "A" * 64):
        with pytest.raises(InputStaleError):
            verify_inputs([{**entries[0], "sha256": bad}], root=tmp_path)
