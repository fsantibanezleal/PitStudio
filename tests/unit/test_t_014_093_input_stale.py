# ruff: noqa: E501
"""T-014-093: a stale policy checkpoint fails `input-stale` at export.

Requirements: FR-014-49.

Spec: specs/014-robot-learning/spec.md FR-014-49: "If the checkpoint SHA-256 in a policy handoff (DC-014-03) differs from the SHA-256 of the checkpoint file now present, then `s60_export` shall fail with
error class `input-stale` (FR-002-69) naming the checkpoint and shall export nothing." FR-002-69 (spec 002): the error names the input, the expected and the actual digest. Plan: "a handoff with one wrong
digest gives `input-stale` with both digests and no ONNX file".

Oracle: hand construction: a fake run whose handoff digest is correct, then the checkpoint file changed afterwards (one byte appended; a different tensor saved); the expected and actual digests computed with `hashlib.sha256` of
the file bytes; "export nothing" is an empty output folder. The control case (an unchanged checkpoint) must still export.

Expected API of the implementation (module `pitstudio_pipeline.export.il`, see T-014-041):
    StaleInput(ExportRejected): attributes `error_class` ("input-stale"), `input` (the checkpoint id of the handoff, for example "ckpt-1500"), `expected` (the digest of the handoff) and `actual` (the digest of the file
        now present), plus ExportRejected.pointer == "/checkpoint/sha256"; str(error) contains "input-stale", the checkpoint id and path, and both digests.
    export_il_policy raises StaleInput, before any model is built, when checkpoint.sha256 differs from the SHA-256 of the file at root / checkpoint.path; nothing is written under out_dir.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
from pitstudio_pipeline.export.il import ExportRejected, StaleInput, export_il_policy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import il_export_kit as kit


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.req("FR-014-49")
def test_an_unchanged_checkpoint_exports(tmp_path: Path) -> None:
    handoff, root = kit.make_run(tmp_path)
    res = export_il_policy(handoff, root=root, out_dir=tmp_path / "out")
    assert res.onnx_path.is_file()


@pytest.mark.req("FR-014-49")
def test_a_checkpoint_changed_after_the_handoff_fails_input_stale_with_both_digests_and_exports_nothing(
    tmp_path: Path,
) -> None:
    handoff, root = kit.make_run(tmp_path)
    ckpt = root / handoff["checkpoint"]["path"]
    expected = handoff["checkpoint"]["sha256"]
    assert expected == digest(ckpt)
    ckpt.write_bytes(ckpt.read_bytes() + b"\x00")  # the file now present differs from the one the handoff describes
    actual = digest(ckpt)
    assert actual != expected
    out = tmp_path / "out"
    with pytest.raises(StaleInput) as info:
        export_il_policy(handoff, root=root, out_dir=out)
    err = info.value
    assert isinstance(err, ExportRejected)
    assert err.error_class == "input-stale"
    assert err.input == "ckpt-1500"
    assert err.expected == expected
    assert err.actual == actual
    assert err.pointer == "/checkpoint/sha256"
    text = str(err)
    for needle in ("input-stale", "ckpt-1500", "model_1500.pt", expected, actual):
        assert needle in text
    assert kit.out_files(out) == []  # no ONNX file, no report, no folder content


@pytest.mark.req("FR-014-49")
def test_a_replaced_checkpoint_of_the_same_size_is_also_stale(tmp_path: Path) -> None:
    import torch

    handoff, root = kit.make_run(tmp_path)
    ckpt = root / handoff["checkpoint"]["path"]
    state = torch.load(ckpt, weights_only=True)
    state["model_state_dict"]["actor.0.bias"] = (
        state["model_state_dict"]["actor.0.bias"] + 1.0
    )  # same shapes, other values
    torch.save(state, ckpt)
    with pytest.raises(StaleInput) as info:
        export_il_policy(handoff, root=root, out_dir=tmp_path / "out")
    assert info.value.actual == digest(ckpt)
    assert info.value.expected == handoff["checkpoint"]["sha256"]
    assert kit.out_files(tmp_path / "out") == []


@pytest.mark.req("FR-014-49")
def test_a_wrong_digest_in_the_handoff_is_stale_too(tmp_path: Path) -> None:
    handoff, root = kit.make_run(tmp_path)
    handoff["checkpoint"]["sha256"] = "a" * 64
    with pytest.raises(StaleInput) as info:
        export_il_policy(handoff, root=root, out_dir=tmp_path / "out")
    assert info.value.expected == "a" * 64
    assert info.value.actual == digest(root / handoff["checkpoint"]["path"])
    assert kit.out_files(tmp_path / "out") == []


@pytest.mark.req("FR-014-49")
def test_the_stale_check_happens_before_the_checkpoint_is_read_as_a_model(tmp_path: Path) -> None:
    handoff, root = kit.make_run(tmp_path)
    ckpt = root / handoff["checkpoint"]["path"]
    ckpt.write_bytes(b"not a torch file at all")  # unreadable AND stale: the stale class wins, it is the first check
    with pytest.raises(StaleInput):
        export_il_policy(handoff, root=root, out_dir=tmp_path / "out")


@pytest.mark.req("FR-014-49")
def test_the_digest_comparison_is_exact_not_a_prefix_or_a_case_fold(tmp_path: Path) -> None:
    handoff, root = kit.make_run(tmp_path)
    good = handoff["checkpoint"]["sha256"]
    for wrong in (good[:-1] + ("0" if good[-1] != "0" else "1"), "0" + good[1:] if good[0] != "0" else "1" + good[1:]):
        h = {**handoff, "checkpoint": {**handoff["checkpoint"], "sha256": wrong}}
        with pytest.raises(StaleInput):
            export_il_policy(h, root=root, out_dir=tmp_path / "out")
    upper = {**handoff, "checkpoint": {**handoff["checkpoint"], "sha256": good.upper()}}
    with pytest.raises(ExportRejected):  # the schema pattern demands lower-case hex: rejected, and nothing exported
        export_il_policy(upper, root=root, out_dir=tmp_path / "out2")
    assert kit.out_files(tmp_path / "out2") == []


@pytest.mark.req("FR-014-49")
def test_the_error_class_is_input_stale_only_for_a_digest_mismatch(tmp_path: Path) -> None:
    handoff, root = kit.make_run(tmp_path)
    bad = {**handoff, "observation_size": 46}
    with pytest.raises(ExportRejected) as info:
        export_il_policy(bad, root=root, out_dir=tmp_path / "out")
    assert not isinstance(info.value, StaleInput)
    assert getattr(info.value, "error_class", None) != "input-stale"
