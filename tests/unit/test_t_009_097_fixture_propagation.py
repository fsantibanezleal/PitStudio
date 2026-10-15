# ruff: noqa: E501
"""T-009-097 - FR-009-51: fixture propagation through the detector stages.

Oracles (independent of the code under test; plan 009 test strategy row FR-009-51, a fake trainer): a fixture index (the spec's contract example records, provenance "fixture") run through
`s30_train` (fake trainer), `s40_infer` (fake predictor) and `s50_evaluate` gives a checkpoint record, a prediction file and a report that all carry `fixture: true`, and the publish step passes on
NO metric computed from it; the same run on a real-provenance index carries `fixture: false` and publishes the full report unchanged. Hand lists: the metric keys of DC-009-05 that may not survive
publishing a fixture report (typed out below from the schema's field names); the fake trainer returns the bytes b"fake-checkpoint:<n>" for n selected records, so the checkpoint digest is
`hashlib.sha256` of that text, computed here.

Expected public API (package `pitstudio_pipeline.perception`, under `pipeline/src/`):

module `stages`
    PROVENANCES: tuple[str, ...]          ("fixture", "real")
    TrainStageResult                      frozen dataclass: record: dict, checkpoint_path: pathlib.Path
    s30_train(*, records: Sequence[Mapping], provenance: str, config: TrainConfig, trainer: Callable[[list[dict], TrainConfig], bytes], out_dir: pathlib.Path) -> TrainStageResult
        Runs check_training_inputs (each record as {"id": record_id, "licence_class": licence.licence_class, "source": "synthetic"}) and select_training_records(records, arm="S") of T-009-030, calls
        `trainer(selected, config)`, writes the returned bytes to out_dir / "checkpoint.bin" and the record to out_dir / "checkpoint.json" (UTF-8 JSON). The record is
        training_record(config, checkpoint_sha256=<digest of the bytes>, training_set_sha256=<digest of the selected records>) plus "fixture": True when provenance == "fixture", else False.
        ValueError (message contains "provenance") for a provenance outside PROVENANCES.
    s40_infer(*, checkpoint: Mapping, checkpoint_path: pathlib.Path, records: Sequence[Mapping], provenance: str, predictor: Callable[[bytes, list[dict]], list[dict]], out_path: pathlib.Path) -> dict
        Verifies the checkpoint file against checkpoint["checkpoint_sha256"] (TrainError "checkpoint-digest" otherwise), calls `predictor(checkpoint bytes, records)` -> detections, writes
        out_path (UTF-8 JSON) and returns the prediction file {"model", "precision", "arm" ("S"), "image_ids" (the coco_image_id of each record), "detections", "fixture": bool}; fixture is True when
        provenance == "fixture" or checkpoint["fixture"] is true.

module `s50_evaluate` (see tests/unit/test_t_009_033_support_determinism.py): spec["fixture"] (bool, default False) and any prediction set with "fixture": True make report["fixture"] True and
    S50Result.fixture True; otherwise report["fixture"] is absent or False and S50Result.fixture False.

module `publish`
    METRIC_KEYS: frozenset[str]           {"ap50", "ap50_95", "ap50_interval", "ap50_95_interval", "value", "interval", "delta_rel_pct", "m_clean", "m_corrupted", "difference", "labeller_b_map50", "box_f1"}
    publish_report(report: Mapping) -> dict
        A report with report["fixture"] true is returned WITHOUT any metric: every key of METRIC_KEYS is removed at every depth (rows and blocks stay, so statuses, supports, labels, verdict
        strings and "fixture": true remain); the verdicts of the acceptance rows are replaced by "not run" with reason "fixture index: no metric published" and their `value` removed; a real report is
        returned as an equal deep copy. The input is not modified.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
import _p009_s50_kit as k50  # noqa: E402
from pitstudio_pipeline.perception import publish, s50_evaluate, stages, train  # noqa: E402

PINS = {"d-fine-s": {"id": "dfine-s-coco", "sha256": "b" * 64}}
METRIC_KEYS = {
    "ap50",
    "ap50_95",
    "ap50_interval",
    "ap50_95_interval",
    "value",
    "interval",
    "delta_rel_pct",
    "m_clean",
    "m_corrupted",
    "difference",
    "labeller_b_map50",
    "box_f1",
}


def _records(n: int = 3) -> list[dict]:
    out = []
    for i in range(n):
        r = kit.index_record("valid")
        r["record_id"] = f"fixture-pit-{i:03d}"
        r["split"] = "train"
        r["coco_image_id"] = i + 1
        out.append(r)
    return out


def _config() -> train.TrainConfig:
    return train.build_training_config("d-fine-s", seed=1, epochs=1, pins=PINS)


def _fake_trainer(records: list[dict], cfg: train.TrainConfig) -> bytes:
    return b"fake-checkpoint:" + str(len(records)).encode()


def _fake_predictor(blob: bytes, records: list[dict]) -> list[dict]:
    return [
        {"image_id": r["coco_image_id"], "category_id": 1, "bbox": [1.0, 2.0, 3.0, 4.0], "score": 0.9} for r in records
    ]


def _walk_keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_keys(v)


# ---------------------------------------------------------------- s30_train


@pytest.mark.req("FR-009-51")
def test_a_fixture_index_gives_a_checkpoint_record_marked_fixture(tmp_path: Path) -> None:
    res = stages.s30_train(
        records=_records(), provenance="fixture", config=_config(), trainer=_fake_trainer, out_dir=tmp_path
    )
    blob = b"fake-checkpoint:3"
    assert res.record["fixture"] is True
    assert res.record["checkpoint_sha256"] == hashlib.sha256(blob).hexdigest()
    assert res.record["training_set_sha256"] == train.training_set_digest(_records())
    assert res.record["model"] == "d-fine-s"
    assert res.checkpoint_path == tmp_path / "checkpoint.bin"
    assert res.checkpoint_path.read_bytes() == blob
    assert json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8")) == res.record


@pytest.mark.req("FR-009-51")
def test_a_real_index_gives_fixture_false(tmp_path: Path) -> None:
    res = stages.s30_train(
        records=_records(), provenance="real", config=_config(), trainer=_fake_trainer, out_dir=tmp_path
    )
    assert res.record["fixture"] is False
    assert json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))["fixture"] is False


@pytest.mark.req("FR-009-51")
@pytest.mark.parametrize("provenance", ["", "Fixture", "synthetic", None, True, 1])
def test_an_unknown_provenance_is_refused(tmp_path: Path, provenance: object) -> None:
    with pytest.raises(ValueError, match="provenance"):
        stages.s30_train(
            records=_records(), provenance=provenance, config=_config(), trainer=_fake_trainer, out_dir=tmp_path
        )  # type: ignore[arg-type]
    assert not (tmp_path / "checkpoint.bin").exists()


@pytest.mark.req("FR-009-51")
def test_the_provenances_are_fixture_and_real() -> None:
    assert tuple(stages.PROVENANCES) == ("fixture", "real")


# ---------------------------------------------------------------- s40_infer


def _trained(tmp_path: Path, provenance: str = "fixture"):
    return stages.s30_train(
        records=_records(), provenance=provenance, config=_config(), trainer=_fake_trainer, out_dir=tmp_path / "train"
    )


@pytest.mark.req("FR-009-51")
def test_the_prediction_file_of_a_fixture_run_carries_fixture_true(tmp_path: Path) -> None:
    tr = _trained(tmp_path)
    out = tmp_path / "pred.json"
    pred = stages.s40_infer(
        checkpoint=tr.record,
        checkpoint_path=tr.checkpoint_path,
        records=_records(),
        provenance="fixture",
        predictor=_fake_predictor,
        out_path=out,
    )
    assert pred["fixture"] is True
    assert pred["model"] == "d-fine-s"
    assert pred["image_ids"] == [1, 2, 3]
    assert len(pred["detections"]) == 3
    assert json.loads(out.read_text(encoding="utf-8")) == pred


@pytest.mark.req("FR-009-51")
def test_a_fixture_checkpoint_makes_its_predictions_fixture_even_on_a_real_index(tmp_path: Path) -> None:
    tr = _trained(tmp_path, "fixture")
    pred = stages.s40_infer(
        checkpoint=tr.record,
        checkpoint_path=tr.checkpoint_path,
        records=_records(),
        provenance="real",
        predictor=_fake_predictor,
        out_path=tmp_path / "p.json",
    )
    assert pred["fixture"] is True


@pytest.mark.req("FR-009-51")
def test_a_real_checkpoint_on_a_real_index_gives_fixture_false(tmp_path: Path) -> None:
    tr = _trained(tmp_path, "real")
    pred = stages.s40_infer(
        checkpoint=tr.record,
        checkpoint_path=tr.checkpoint_path,
        records=_records(),
        provenance="real",
        predictor=_fake_predictor,
        out_path=tmp_path / "p.json",
    )
    assert pred["fixture"] is False


@pytest.mark.req("FR-009-51")
def test_a_checkpoint_file_that_does_not_match_its_record_is_refused_before_prediction(tmp_path: Path) -> None:
    tr = _trained(tmp_path)
    tr.checkpoint_path.write_bytes(b"tampered")
    called: list[int] = []

    def predictor(blob: bytes, records: list[dict]) -> list[dict]:
        called.append(1)
        return []

    with pytest.raises(train.TrainError) as exc:
        stages.s40_infer(
            checkpoint=tr.record,
            checkpoint_path=tr.checkpoint_path,
            records=_records(),
            provenance="fixture",
            predictor=predictor,
            out_path=tmp_path / "p.json",
        )
    assert exc.value.code == "checkpoint-digest"
    assert called == []
    assert not (tmp_path / "p.json").exists()


# ---------------------------------------------------------------- s50_evaluate


def _spec(**over) -> dict:
    gt, family, cluster = k50.fraction_gt(100, 100)
    dets = k50.perfect_detections(gt, set(range(1, 181)))
    pred = k50.prediction("d-fine-s", "fp32", "S", dets, gt)
    return k50.spec(gt, family, cluster, [pred], **over)


@pytest.mark.req("FR-009-51")
def test_the_report_of_a_fixture_run_carries_fixture_true() -> None:
    res = s50_evaluate.run_s50_evaluate(_spec(fixture=True))
    assert res.fixture is True
    assert res.report["fixture"] is True


@pytest.mark.req("FR-009-51")
def test_a_fixture_prediction_set_alone_makes_the_report_fixture() -> None:
    spec = _spec()
    spec["predictions"][0]["fixture"] = True
    res = s50_evaluate.run_s50_evaluate(spec)
    assert res.fixture is True
    assert res.report["fixture"] is True


@pytest.mark.req("FR-009-51")
def test_a_real_run_is_not_marked_fixture() -> None:
    res = s50_evaluate.run_s50_evaluate(_spec())
    assert res.fixture is False
    assert not res.report.get("fixture", False)


# ---------------------------------------------------------------- publish


@pytest.mark.req("FR-009-51")
def test_publishing_a_fixture_report_passes_on_no_metric() -> None:
    rep = s50_evaluate.run_s50_evaluate(_spec(fixture=True)).report
    assert set(publish.METRIC_KEYS) == METRIC_KEYS
    before = copy.deepcopy(rep)
    out = publish.publish_report(rep)
    assert rep == before
    assert out["fixture"] is True
    assert not (set(_walk_keys(out)) & METRIC_KEYS)
    assert out["per_class"]
    assert all("support" in r for r in out["per_class"])  # rows and supports stay, metrics go
    assert out["honesty_label"] == kit.HONESTY_LABEL
    for row in out["acceptance"]:
        assert row["verdict"] == "not run"
        assert "value" not in row
        assert row["reason"]


@pytest.mark.req("FR-009-51")
def test_publishing_a_real_report_returns_it_unchanged() -> None:
    rep = s50_evaluate.run_s50_evaluate(_spec()).report
    assert publish.publish_report(rep) == rep


@pytest.mark.req("FR-009-51")
@pytest.mark.parametrize("report", [None, [], "r", 7])
def test_publishing_something_that_is_not_a_report_is_refused(report: object) -> None:
    with pytest.raises(ValueError, match="report"):
        publish.publish_report(report)  # type: ignore[arg-type]
