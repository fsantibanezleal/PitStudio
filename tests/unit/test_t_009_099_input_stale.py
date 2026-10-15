# ruff: noqa: E501
"""T-009-099 - FR-009-53: stale SDG images fail `input-stale` before training.

Oracles (independent of the code under test; plan 009 test strategy row FR-009-53): `hashlib.sha256` of fixture image files written here; the index records carry those digests. One altered byte (an
"altered pixel": the files are opaque bytes, which is all the digest sees) in one image gives `input-stale` naming that record, raised BEFORE any step (the trainer is never called, nothing is written);
an untouched index passes. The error class name `input-stale` is the one of FR-002-69 (spec 002) for a stage whose input digest differs from the artefact now present.

Expected public API (module `pitstudio_pipeline.perception.stages`, see tests/unit/test_t_009_097_fixture_propagation.py):

    InputStaleError(Exception)       .code == "input-stale"; .record_id: str (the first stale record in index order); .record_ids: tuple[str, ...] (all stale records, index order); .expected: str and
                                     .actual: str (SHA-256 of the first one); str(error) contains the code and every stale record id
    check_index_fresh(records: Sequence[Mapping], root: pathlib.Path) -> None
        For every record, the SHA-256 of root / record["image"]["path"] must equal record["image"]["sha256"]; otherwise InputStaleError listing all stale records. FileNotFoundError for an absent image
        file; ValueError (message contains "path") for an image path that is absolute, contains "..", a drive letter or a backslash.
    s30_train(..., root: pathlib.Path | None = None)       with `root` given, check_index_fresh(records, root) runs FIRST: on InputStaleError the trainer is not called and nothing is written to out_dir.
    (module `s50_evaluate`) run_s50_evaluate(spec) with spec["index_records"] and spec["root"] runs check_index_fresh before any evaluation; InputStaleError propagates and no report is produced.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
import _p009_s50_kit as k50  # noqa: E402
from pitstudio_pipeline.perception import s50_evaluate, stages, train  # noqa: E402

PINS = {"d-fine-s": {"id": "dfine-s-coco", "sha256": "b" * 64}}


def _index(root: Path, n: int = 4) -> list[dict]:
    recs = []
    for i in range(n):
        rel = f"sdg/pit-structured/shard-0001/rgb/{i:06d}.png"
        data = kit.payload(500, i)
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
        r = kit.index_record("valid")
        r["record_id"] = f"pit-s-{i:06d}"
        r["split"] = "train"
        r["coco_image_id"] = i + 1
        r["image"]["path"] = rel
        r["image"]["sha256"] = hashlib.sha256(data).hexdigest()
        recs.append(r)
    return recs


def _flip_one_byte(root: Path, rec: dict) -> None:
    p = root / rec["image"]["path"]
    data = bytearray(p.read_bytes())
    data[250] ^= 0x01
    p.write_bytes(bytes(data))


class _Trainer:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, records: list[dict], cfg: train.TrainConfig) -> bytes:
        self.calls += 1
        return b"ckpt"


def _cfg() -> train.TrainConfig:
    return train.build_training_config("d-fine-s", seed=1, epochs=1, pins=PINS)


@pytest.mark.req("FR-009-53")
def test_an_untouched_index_is_fresh(tmp_path: Path) -> None:
    recs = _index(tmp_path)
    assert stages.check_index_fresh(recs, tmp_path) is None
    assert stages.check_index_fresh([], tmp_path) is None


@pytest.mark.req("FR-009-53")
def test_one_altered_image_is_input_stale_naming_the_record(tmp_path: Path) -> None:
    recs = _index(tmp_path)
    _flip_one_byte(tmp_path, recs[2])
    with pytest.raises(stages.InputStaleError) as exc:
        stages.check_index_fresh(recs, tmp_path)
    assert exc.value.code == "input-stale"
    assert exc.value.record_id == "pit-s-000002"
    assert exc.value.record_ids == ("pit-s-000002",)
    assert exc.value.expected == recs[2]["image"]["sha256"]
    assert exc.value.actual == hashlib.sha256((tmp_path / recs[2]["image"]["path"]).read_bytes()).hexdigest()
    assert exc.value.actual != exc.value.expected
    assert "input-stale" in str(exc.value)
    assert "pit-s-000002" in str(exc.value)


@pytest.mark.req("FR-009-53")
def test_every_stale_record_is_listed_in_index_order(tmp_path: Path) -> None:
    recs = _index(tmp_path, 6)
    for i in (1, 4):
        _flip_one_byte(tmp_path, recs[i])
    with pytest.raises(stages.InputStaleError) as exc:
        stages.check_index_fresh(recs, tmp_path)
    assert exc.value.record_ids == ("pit-s-000001", "pit-s-000004")
    assert exc.value.record_id == "pit-s-000001"


@pytest.mark.req("FR-009-53")
@pytest.mark.parametrize("change", ["append", "truncate", "empty", "replace"])
def test_every_kind_of_change_to_an_image_is_stale(tmp_path: Path, change: str) -> None:
    recs = _index(tmp_path, 2)
    p = tmp_path / recs[0]["image"]["path"]
    data = p.read_bytes()
    p.write_bytes(
        {"append": data + b"\0", "truncate": data[:-1], "empty": b"", "replace": kit.payload(500, 99)}[change]
    )
    with pytest.raises(stages.InputStaleError) as exc:
        stages.check_index_fresh(recs, tmp_path)
    assert exc.value.record_id == "pit-s-000000"


@pytest.mark.req("FR-009-53")
def test_an_absent_image_file_is_a_file_error_and_an_unsafe_path_is_refused(tmp_path: Path) -> None:
    recs = _index(tmp_path, 2)
    (tmp_path / recs[1]["image"]["path"]).unlink()
    with pytest.raises(FileNotFoundError):
        stages.check_index_fresh(recs, tmp_path)
    for bad in ("../x.png", "/abs/x.png", "C:/x.png", "a\\b.png"):
        recs2 = _index(tmp_path / "ok", 1)
        recs2[0]["image"]["path"] = bad
        with pytest.raises(ValueError, match="path"):
            stages.check_index_fresh(recs2, tmp_path / "ok")


@pytest.mark.req("FR-009-53")
def test_the_training_stage_fails_before_any_step_and_trains_nothing_on_a_stale_image(tmp_path: Path) -> None:
    recs = _index(tmp_path / "data")
    _flip_one_byte(tmp_path / "data", recs[1])
    trainer = _Trainer()
    out = tmp_path / "out"
    with pytest.raises(stages.InputStaleError) as exc:
        stages.s30_train(
            records=recs, provenance="real", config=_cfg(), trainer=trainer, out_dir=out, root=tmp_path / "data"
        )
    assert exc.value.record_id == "pit-s-000001"
    assert trainer.calls == 0  # before any step
    assert not out.exists() or list(out.iterdir()) == []  # no checkpoint


@pytest.mark.req("FR-009-53")
def test_the_training_stage_runs_on_a_fresh_index(tmp_path: Path) -> None:
    recs = _index(tmp_path / "data")
    trainer = _Trainer()
    res = stages.s30_train(
        records=recs,
        provenance="real",
        config=_cfg(),
        trainer=trainer,
        out_dir=tmp_path / "out",
        root=tmp_path / "data",
    )
    assert trainer.calls == 1
    assert res.checkpoint_path.is_file()


@pytest.mark.req("FR-009-53")
def test_the_evaluation_fails_on_a_stale_image_and_produces_no_report(tmp_path: Path) -> None:
    recs = _index(tmp_path / "data")
    _flip_one_byte(tmp_path / "data", recs[3])
    gt, family, cluster = k50.fraction_gt(10, 10)
    pred = k50.prediction("d-fine-s", "fp32", "S", k50.perfect_detections(gt, set(range(1, 21))), gt)
    spec = k50.spec(gt, family, cluster, [pred], index_records=recs, root=tmp_path / "data")
    with pytest.raises(stages.InputStaleError) as exc:
        s50_evaluate.run_s50_evaluate(spec)
    assert exc.value.record_id == "pit-s-000003"


@pytest.mark.req("FR-009-53")
def test_the_evaluation_runs_when_the_index_is_fresh(tmp_path: Path) -> None:
    recs = _index(tmp_path / "data")
    gt, family, cluster = k50.fraction_gt(10, 10)
    pred = k50.prediction("d-fine-s", "fp32", "S", k50.perfect_detections(gt, set(range(1, 21))), gt)
    res = s50_evaluate.run_s50_evaluate(
        k50.spec(gt, family, cluster, [pred], index_records=recs, root=tmp_path / "data")
    )
    assert res.report["run_id"] == "20261012T100000Z-s50"
