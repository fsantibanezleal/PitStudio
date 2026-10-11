"""T-011-097 - FR-011-51: a rollout file or field dataset whose digest changed fails `input-stale` before any step.

Oracles (independent of the code under test; plan 011 test strategy FR-011-51): hand calculation with
    `hashlib.sha256` computed in
the test: a manifest records the digest of each input file at training time; one altered byte (or one altered
    frame) changes the
digest, so `s30_train` and `s50_evaluate` must fail with error class `input-stale` naming the file, with the
    expected and the actual
digest, before the work function (the training or the scoring) is called; an unchanged set passes and the work runs
    once.
Error class and fields follow FR-002-69 (`input-stale`, naming the input, the expected and the actual digest).

Expected public API (module `pitstudio.surrogate_inputs`, under `src/pitstudio/`):

    InputStaleError(Exception): attributes error_class == "input-stale", file (the manifest id of the stale input),
        expected,
        actual (64-hex digests); the message names the file and both digests.
    verify_inputs(inputs, *, root) -> None
        inputs: list of {"id": str, "path": str (relative to root), "sha256": str}; raises InputStaleError for the
            first input whose file
        digest differs from the recorded one; reads every file in manifest order and stops at the first mismatch.
    run_stage(stage, manifest, *, root, work) -> object
        stage in {"s30_train", "s50_evaluate"}; verifies manifest["inputs"] with verify_inputs, then returns
            work(); never calls
        `work` when an input is stale. Raises ValueError for any other stage name.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio.surrogate_inputs import InputStaleError, run_stage, verify_inputs  # noqa: E402


def make_inputs(root: Path) -> list[dict]:
    files = {
        "rollout_a.parquet": b"frame-0|frame-1|frame-2",
        "rollout_b.parquet": b"B" * 4096,
        "field.json": b'{"patch":"p07"}',
    }
    entries = []
    for name, data in files.items():
        (root / name).write_bytes(data)
        entries.append({"id": name.split(".")[0], "path": name, "sha256": hashlib.sha256(data).hexdigest()})
    return entries


def tamper(path: Path, how: str) -> None:
    raw = bytearray(path.read_bytes())
    if how == "flip":
        raw[len(raw) // 2] ^= 0x01
    elif how == "append":
        raw += b"\x00"
    elif how == "truncate":
        raw = raw[:-1]
    path.write_bytes(bytes(raw))


@pytest.mark.req("FR-011-51")
@pytest.mark.parametrize("stage", ["s30_train", "s50_evaluate"])
def test_unchanged_inputs_pass_and_the_work_runs_exactly_once(tmp_path: Path, stage: str) -> None:
    manifest = {"inputs": make_inputs(tmp_path)}
    calls: list[str] = []
    result = run_stage(stage, manifest, root=tmp_path, work=lambda: calls.append(stage) or "trained")
    assert result == "trained"
    assert calls == [stage]
    verify_inputs(manifest["inputs"], root=tmp_path)  # does not raise


@pytest.mark.req("FR-011-51")
@pytest.mark.parametrize("stage", ["s30_train", "s50_evaluate"])
@pytest.mark.parametrize("how", ["flip", "append", "truncate"])
def test_one_altered_input_fails_input_stale_naming_the_file_before_any_step(
    tmp_path: Path, stage: str, how: str
) -> None:
    manifest = {"inputs": make_inputs(tmp_path)}
    old = manifest["inputs"][1]["sha256"]
    tamper(tmp_path / "rollout_b.parquet", how)
    new = hashlib.sha256((tmp_path / "rollout_b.parquet").read_bytes()).hexdigest()
    calls: list[int] = []
    with pytest.raises(InputStaleError, match="rollout_b") as info:
        run_stage(stage, manifest, root=tmp_path, work=lambda: calls.append(1))
    err = info.value
    assert err.error_class == "input-stale"
    assert err.file == "rollout_b"
    assert err.expected == old
    assert err.actual == new
    assert old in str(err)
    assert new in str(err)
    assert calls == []  # no surrogate was trained or scored


@pytest.mark.req("FR-011-51")
def test_the_first_stale_input_in_manifest_order_is_the_one_named(tmp_path: Path) -> None:
    manifest = {"inputs": make_inputs(tmp_path)}
    tamper(tmp_path / "field.json", "append")
    tamper(tmp_path / "rollout_a.parquet", "flip")
    with pytest.raises(InputStaleError) as info:
        verify_inputs(manifest["inputs"], root=tmp_path)
    assert info.value.file == "rollout_a"


@pytest.mark.req("FR-011-51")
def test_a_stale_field_metadata_file_is_detected_like_a_rollout(tmp_path: Path) -> None:
    manifest = {"inputs": make_inputs(tmp_path)}
    (tmp_path / "field.json").write_bytes(b'{"patch":"p08"}')
    with pytest.raises(InputStaleError, match="field"):
        run_stage("s50_evaluate", manifest, root=tmp_path, work=lambda: None)


@pytest.mark.req("FR-011-51")
def test_the_check_writes_nothing_and_leaves_the_files_untouched(tmp_path: Path) -> None:
    manifest = {"inputs": make_inputs(tmp_path)}
    tamper(tmp_path / "rollout_b.parquet", "flip")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(InputStaleError):
        run_stage("s30_train", manifest, root=tmp_path, work=lambda: None)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.req("FR-011-51")
@pytest.mark.parametrize("stage", ["s10_preprocess", "s40_infer", "", "S30_TRAIN"])
def test_only_the_training_and_evaluation_stages_are_guarded_by_this_helper(tmp_path: Path, stage: str) -> None:
    with pytest.raises(ValueError, match="stage"):
        run_stage(stage, {"inputs": make_inputs(tmp_path)}, root=tmp_path, work=lambda: None)


@pytest.mark.req("FR-011-51")
def test_an_empty_input_list_passes_trivially_and_runs_the_work(tmp_path: Path) -> None:
    assert run_stage("s30_train", {"inputs": []}, root=tmp_path, work=lambda: 7) == 7
