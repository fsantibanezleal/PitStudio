# ruff: noqa: E501
"""T-009-030 (unit half) - FR-009-18, FR-009-19: training configuration, pinned checkpoints, training-input licence guard.

Oracles (independent of the code under test):
- FR-009-18, published values: RF-DETR 1.11.1 `src/rfdetr/config.py` `SegmentationTrainConfig`: `mask_ce_loss_coef` 5.0,
  `mask_dice_loss_coef` 5.0, `cls_loss_coef` 1.0 (spec 009 section 7, read 2026-10-06 from the primary source; the values are
  the ones the spec pins); D-FINE keeps its upstream loss configuration untouched (no override: the spec pins no D-FINE
  coefficient, so none is asserted); bf16 autocast and no FP8 training are spec statements, typed out;
- the pinned checkpoint digest is checked with `hashlib.sha256` over fixture files written here;
- the training-set digest is defined in this file (the spec names no recipe, reported as an ambiguity) as the SHA-256 of the
  UTF-8 text made of the lines `<record_id> <image sha256>\\n`, sorted by record_id, and computed here with `hashlib`;
- FR-009-19, hand calculation (plan 009 test strategy row): manifests carrying a `display-only` input, a `reference-only` input
  and a real-probe image are each refused with `training-input-licence`, naming every offending input.

Expected public API (module `pitstudio_pipeline.perception.train`, package under `pipeline/src/`):

    MODELS: tuple[str, ...] == ("d-fine-n", "d-fine-s", "rf-detr-seg-n")
    TrainError(Exception)            .code: str ("checkpoint-digest", "training-input-licence"); .inputs: tuple[str, ...]
                                     (offending input ids or file names, input order, no duplicates); str(error) contains
                                     the code and every name in .inputs
    TrainConfig                      frozen dataclass: model, base_checkpoint_id, base_checkpoint_sha256, licence ("Apache-2.0"),
                                     precision ("bf16"), autocast_dtype ("bfloat16"), fp8 (False), loss_coefficients: dict[str,
                                     float], seed: int, epochs: int, split ("train")
    build_training_config(model: str, *, seed: int, epochs: int, pins: Mapping[str, Mapping[str, str]],
                          precision: str = "bf16") -> TrainConfig
        pins[model] = {"id": str, "sha256": 64 lower-case hex}; loss_coefficients is {"mask_ce_loss_coef": 5.0,
        "mask_dice_loss_coef": 5.0, "cls_loss_coef": 1.0} for "rf-detr-seg-n" and {} for the D-FINE models (upstream
        defaults, no override). ValueError (message names the argument: "model", "seed", "epochs", "precision", "pins") for an
        unknown model, a seed outside 0..2**63-1 (bool excluded), epochs < 1 or not an int, any precision other than "bf16"
        (fp8, fp16, fp32 are refused), a missing/malformed pin.
    verify_checkpoint(path: pathlib.Path, expected_sha256: str) -> str
        returns the file's SHA-256; TrainError("checkpoint-digest") (inputs == (path.name,)) when it differs; FileNotFoundError
        when the file is absent.
    training_set_digest(records: Sequence[Mapping]) -> str          as defined above; ValueError for an empty sequence.
    select_training_records(records: Sequence[Mapping], *, arm: str) -> list[dict]
        arm "S": records with split "train" and arm "structured" (pit and crusher); arm "U": split "train" and (arm "unstructured"
        with family "pit", or arm "structured" with family "crusher"); input order kept; validation/test records are never
        returned. ValueError("arm") for any other arm name.
    training_record(cfg: TrainConfig, *, checkpoint_sha256: str, training_set_sha256: str) -> dict
        the manifest record of the run (DC-000-01 `params` shape: keys match ^[a-z][a-z0-9_]{0,63}$, scalar values): exactly
        {"model", "base_checkpoint_id", "base_checkpoint_sha256", "checkpoint_sha256", "training_set_sha256", "seed", "epochs",
        "precision", "fp8", "split"} with the values of the arguments / the config.
    check_training_inputs(inputs: Sequence[Mapping]) -> None
        each input {"id": str, "licence_class": str, "source": str}; allowed licence classes: public-domain, open-no-attribution, own,
        attribution, share-alike; refused: display-only and reference-only, and any input whose source is "real-probe".
        Raises TrainError("training-input-licence") naming ALL offenders. ValueError (message contains "licence_class") for a
        licence class outside the seven of DC-000-01, or a non-mapping input.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_pipeline.perception import train  # noqa: E402

PINS = {
    "d-fine-n": {"id": "dfine-n-coco", "sha256": "a" * 64},
    "d-fine-s": {"id": "dfine-s-coco", "sha256": "b" * 64},
    "rf-detr-seg-n": {"id": "rf-detr-seg-nano", "sha256": "c" * 64},
}
RF_COEF = {"mask_ce_loss_coef": 5.0, "mask_dice_loss_coef": 5.0, "cls_loss_coef": 1.0}  # RF-DETR 1.11.1 config.py


def _cfg(model: str = "d-fine-s", **kw) -> train.TrainConfig:
    return train.build_training_config(
        model, seed=kw.pop("seed", 20261007), epochs=kw.pop("epochs", 30), pins=PINS, **kw
    )


# ---------------------------------------------------------------- FR-009-18


@pytest.mark.req("FR-009-18")
def test_the_three_models_are_listed() -> None:
    assert tuple(train.MODELS) == ("d-fine-n", "d-fine-s", "rf-detr-seg-n")


@pytest.mark.req("FR-009-18")
@pytest.mark.parametrize("model", ["d-fine-n", "d-fine-s", "rf-detr-seg-n"])
def test_each_config_starts_from_its_pinned_apache_checkpoint_in_bf16_without_fp8(model: str) -> None:
    cfg = _cfg(model)
    assert cfg.model == model
    assert cfg.base_checkpoint_id == PINS[model]["id"]
    assert cfg.base_checkpoint_sha256 == PINS[model]["sha256"]
    assert cfg.licence == "Apache-2.0"
    assert cfg.precision == "bf16"
    assert cfg.autocast_dtype == "bfloat16"
    assert cfg.fp8 is False
    assert cfg.split == "train"
    assert (cfg.seed, cfg.epochs) == (20261007, 30)


@pytest.mark.req("FR-009-18")
def test_rf_detr_seg_n_uses_the_upstream_default_loss_coefficients_and_d_fine_has_no_override() -> None:
    assert _cfg("rf-detr-seg-n").loss_coefficients == RF_COEF
    assert _cfg("d-fine-n").loss_coefficients == {}
    assert _cfg("d-fine-s").loss_coefficients == {}


@pytest.mark.req("FR-009-18")
@pytest.mark.parametrize("precision", ["fp8", "fp16", "fp32", "BF16", "", "bfloat16"])
def test_any_precision_other_than_bf16_is_refused(precision: str) -> None:
    with pytest.raises(ValueError, match="precision"):
        _cfg(precision=precision)


@pytest.mark.req("FR-009-18")
@pytest.mark.parametrize(
    ("kwargs", "arg"),
    [
        ({"model": "yolo"}, "model"),
        ({"model": ""}, "model"),
        ({"seed": -1}, "seed"),
        ({"seed": 2**63}, "seed"),
        ({"seed": True}, "seed"),
        ({"seed": 1.5}, "seed"),
        ({"epochs": 0}, "epochs"),
        ({"epochs": -3}, "epochs"),
        ({"epochs": 2.0}, "epochs"),
        ({"epochs": True}, "epochs"),
    ],
)
def test_hostile_configuration_arguments_are_refused(kwargs: dict, arg: str) -> None:
    args = {"model": "d-fine-s", "seed": 1, "epochs": 2} | kwargs
    with pytest.raises(ValueError, match=arg):
        train.build_training_config(args["model"], seed=args["seed"], epochs=args["epochs"], pins=PINS)


@pytest.mark.req("FR-009-18")
@pytest.mark.parametrize(
    "pins",
    [
        {},
        {"d-fine-s": {"id": "x"}},
        {"d-fine-s": {"id": "x", "sha256": "ABC"}},
        {"d-fine-s": {"id": "x", "sha256": "A" * 64}},
        {"d-fine-s": {"id": "", "sha256": "a" * 64}},
        {"d-fine-s": None},
    ],
)
def test_a_missing_or_malformed_pin_is_refused(pins: dict) -> None:
    with pytest.raises(ValueError, match="pins"):
        train.build_training_config("d-fine-s", seed=1, epochs=1, pins=pins)


@pytest.mark.req("FR-009-18")
def test_a_checkpoint_with_the_pinned_digest_is_accepted_and_one_byte_off_is_refused(tmp_path: Path) -> None:
    data = kit.payload(4096, 11)
    good = tmp_path / "dfine_s.pth"
    good.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    assert train.verify_checkpoint(good, digest) == digest
    bad = tmp_path / "dfine_s_tampered.pth"
    bad.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    with pytest.raises(train.TrainError) as exc:
        train.verify_checkpoint(bad, digest)
    assert exc.value.code == "checkpoint-digest"
    assert exc.value.inputs == ("dfine_s_tampered.pth",)
    assert "checkpoint-digest" in str(exc.value)
    with pytest.raises(FileNotFoundError):
        train.verify_checkpoint(tmp_path / "absent.pth", digest)


def _rec(rid: str, split: str, arm: str, family: str, sha: str) -> dict:
    return {"record_id": rid, "split": split, "arm": arm, "family": family, "image": {"sha256": sha}}


RECORDS = [
    _rec("p1", "train", "structured", "pit", "1" * 64),
    _rec("p2", "validation", "structured", "pit", "2" * 64),
    _rec("p3", "test", "structured", "pit", "3" * 64),
    _rec("c1", "train", "structured", "crusher", "4" * 64),
    _rec("c2", "test", "structured", "crusher", "5" * 64),
    _rec("u1", "train", "unstructured", "pit", "6" * 64),
    _rec("p4", "train", "structured", "pit", "7" * 64),
]


@pytest.mark.req("FR-009-18")
def test_training_uses_the_training_split_only_per_arm() -> None:
    assert [r["record_id"] for r in train.select_training_records(RECORDS, arm="S")] == ["p1", "c1", "p4"]
    assert [r["record_id"] for r in train.select_training_records(RECORDS, arm="U")] == ["c1", "u1"]


@pytest.mark.req("FR-009-18")
@pytest.mark.parametrize("arm", ["s", "A", "", "structured", None])
def test_an_unknown_arm_name_is_refused(arm: object) -> None:
    with pytest.raises(ValueError, match="arm"):
        train.select_training_records(RECORDS, arm=arm)  # type: ignore[arg-type]


@pytest.mark.req("FR-009-18")
def test_the_training_set_digest_is_the_sha256_of_the_sorted_record_lines() -> None:
    recs = [RECORDS[3], RECORDS[0], RECORDS[6]]  # c1, p1, p4 in a shuffled order
    text = "c1 " + "4" * 64 + "\n" + "p1 " + "1" * 64 + "\n" + "p4 " + "7" * 64 + "\n"
    assert train.training_set_digest(recs) == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert train.training_set_digest(list(reversed(recs))) == train.training_set_digest(recs)  # order does not matter
    changed = [dict(r) for r in recs]
    changed[0] = _rec("c1", "train", "structured", "crusher", "9" * 64)  # one image changed
    assert train.training_set_digest(changed) != train.training_set_digest(recs)
    with pytest.raises(ValueError, match="records"):
        train.training_set_digest([])


@pytest.mark.req("FR-009-18")
def test_the_manifest_record_holds_digests_seed_epochs_and_the_training_set_digest() -> None:
    cfg = _cfg("d-fine-n", seed=7, epochs=12)
    rec = train.training_record(cfg, checkpoint_sha256="d" * 64, training_set_sha256="e" * 64)
    assert rec == {
        "model": "d-fine-n",
        "base_checkpoint_id": "dfine-n-coco",
        "base_checkpoint_sha256": "a" * 64,
        "checkpoint_sha256": "d" * 64,
        "training_set_sha256": "e" * 64,
        "seed": 7,
        "epochs": 12,
        "precision": "bf16",
        "fp8": False,
        "split": "train",
    }
    for key, value in rec.items():
        assert re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key)
        assert isinstance(value, (str, int, float, bool))  # DC-000-01 param values are scalars


# ---------------------------------------------------------------- FR-009-19


def _inp(iid: str, licence: str = "own", source: str = "synthetic") -> dict:
    return {"id": iid, "licence_class": licence, "source": source}


@pytest.mark.req("FR-009-19")
@pytest.mark.parametrize("licence", ["public-domain", "open-no-attribution", "own", "attribution", "share-alike"])
def test_inputs_of_allowed_licence_classes_pass(licence: str) -> None:
    assert train.check_training_inputs([_inp("a", licence), _inp("b")]) is None
    assert train.check_training_inputs([]) is None


@pytest.mark.req("FR-009-19")
@pytest.mark.parametrize("licence", ["display-only", "reference-only"])
def test_a_display_only_or_reference_only_input_is_refused_by_name(licence: str) -> None:
    with pytest.raises(train.TrainError) as exc:
        train.check_training_inputs([_inp("ok-1"), _inp("bad-1", licence), _inp("ok-2")])
    assert exc.value.code == "training-input-licence"
    assert exc.value.inputs == ("bad-1",)
    assert "training-input-licence" in str(exc.value)
    assert "bad-1" in str(exc.value)


@pytest.mark.req("FR-009-19")
def test_a_real_probe_image_is_refused_whatever_its_licence() -> None:
    with pytest.raises(train.TrainError) as exc:
        train.check_training_inputs([_inp("probe-007", "public-domain", "real-probe"), _inp("ok")])
    assert exc.value.code == "training-input-licence"
    assert exc.value.inputs == ("probe-007",)


@pytest.mark.req("FR-009-19")
def test_every_offender_is_named_in_input_order_once() -> None:
    inputs = [
        _inp("a", "display-only"),
        _inp("b"),
        _inp("c", "reference-only"),
        _inp("d", "own", "real-probe"),
        _inp("a", "display-only"),
    ]
    with pytest.raises(train.TrainError) as exc:
        train.check_training_inputs(inputs)
    assert exc.value.inputs == ("a", "c", "d")
    for name in ("a", "c", "d"):
        assert name in str(exc.value)


@pytest.mark.req("FR-009-19")
@pytest.mark.parametrize(
    "bad", [None, "own", 7, [], {"id": "x"}, {"id": "x", "licence_class": "proprietary", "source": "s"}]
)
def test_malformed_inputs_or_unknown_licence_classes_are_refused(bad: object) -> None:
    with pytest.raises(ValueError, match=r"licence_class|input"):
        train.check_training_inputs([bad])  # type: ignore[list-item]
