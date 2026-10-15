# ruff: noqa: E501
"""T-009-061 - FR-009-33, FR-009-34: optional real probe: aggregate metrics, inter-annotator agreement, hostile probe inputs.

Oracles (independent of the code under test):
- hand calculation of plan 009 (test strategy rows FR-009-33 / FR-009-34): two labellers with 3 and 3 boxes of which 2 match at IoU >= 0.5 give box F1 = 2 * 2 / (3 + 3) = 2/3;
  F1 = 2 TP / (n_A + n_B) with one-to-one matching; no overlap gives 0, identical sets 1, both empty is undefined (None); IoU exactly 0.5 matches (">= 0.5");
- the 6-image probe fixture below (images 1-4 hold one person each, images 5-6 hold trucks: 2 and 1), with the AP values worked out by hand on the COCO 101-point grid (each checked
  against `pycocotools` while writing; grid points not above the recall, np.linspace(0, 1, 101), over 101):
    * D-FINE-S detects the persons of images 1-3 (scores 0.9, 0.8, 0.7) and the two trucks of image 5 (0.95, 0.94): against labeller A, person recall 3/4 -> 76/101, truck recall 2/3 -> 67/101;
    * against labeller B, whose person of image 3 and second truck of image 5 are shifted so that their IoU with A's is below 0.5, person is TP, TP, FP at recall 2/4 -> 51/101 and truck is TP, FP at
      recall 1/3 -> 34/101, so the labeller-B mAP50 over the two classes is (51/101 + 34/101) / 2 = 85/202;
    * labeller agreement: person matches in images 1, 2, 4 -> F1 = 2 * 3 / (4 + 4) = 0.75; truck matches 2 of 3 and 3 -> F1 = 2/3;
    * D-FINE-N detects nothing: AP50 0 with the degenerate interval [0, 0];
- FR-009-34: the six licences of the spec (CC0-1.0, CC-BY-2.0, CC-BY-2.5, CC-BY-3.0, CC-BY-4.0, public domain) are accepted; CC-BY-NC-4.0, CC-BY-SA-4.0, "All rights reserved", "" and a missing record
  exclude the image with a listed reason; 200 supplied images are accepted and 201 refused (counted before exclusions); a missing labeller-B file refuses the probe;
- "aggregate metrics only": no file name or image id of the probe appears anywhere in the published block (checked on the JSON text).

Expected public API (package `pitstudio_pipeline.perception`, under `pipeline/src/`):

module `probe`
    ALLOWED_LICENCES: frozenset[str]        {"CC0-1.0", "CC-BY-2.0", "CC-BY-2.5", "CC-BY-3.0", "CC-BY-4.0", "public domain"}
    PROBE_CLASSES: tuple[int, ...]          (1, 2, 3, 4)  (haul_truck, shovel, light_vehicle, person; boulder has no probe)
    ProbeError(Exception)                   .code == "probe-invalid"; str(error) contains the code and the reason
    ProbeSelection                          frozen dataclass: included: tuple[dict, ...] (the image dicts, input order), excluded: tuple[tuple[str, str], ...] ((file_name, reason), input order)
    load_probe(images: Sequence[Mapping], licence_records: Mapping[str, Mapping], *, annotations_b: object) -> ProbeSelection
        images: {"id": int, "file_name": str}; licence_records[file_name] = {"spdx": str}. ProbeError("probe-invalid") when more than 200 images are supplied (before exclusions),
        annotations_b is None (the second labeller's file is missing), `images` is not a list of mappings with unique int ids and non-empty str file names. An image whose
        record is missing, or whose spdx is not in ALLOWED_LICENCES (also "", None, non-str), is excluded with a reason that names the licence (or "no licence record").
    agreement_f1(boxes_a: Sequence[Mapping], boxes_b: Sequence[Mapping], *, iou_threshold: float = 0.5) -> dict[int, float | None]
        boxes {"image_id": int, "category_id": int, "bbox": [x, y, w, h]}; per category id present in either list: F1 = 2 TP / (n_A + n_B) with greedy one-to-one matching by descending
        IoU within the same image and category, IoU >= iou_threshold; None when both lists hold no box of the category (never returned for an absent category: absent categories are omitted).
    evaluate_probe(*, images: Sequence[Mapping], annotations_a: Sequence[Mapping], annotations_b: Sequence[Mapping], predictions: Mapping[str, Sequence[Mapping]], seed: int,
                   excluded_images: int = 0, resamples: int = 2000) -> dict
        The `real_probe` block of DC-009-05 (#/$defs/real_probe): "images" (int), "excluded_images", "ground_truth": "labeller-a", "per_class" (per model in sorted order, per probe class in
        ascending id with support > 0: {"model", "class" (name), "support" (labeller-A instances), "ap50", "ap50_interval": {"lower", "upper"}} from the COCO protocol with an image-level
        percentile bootstrap of `resamples` draws), "labeller_b_map50" (per model {"model", "map50"}: mean AP50 over the probe classes with labeller-B instances against labeller B),
        "agreement" (per category with boxes, ascending id: {"class", "box_f1", "iou_threshold": 0.5}, categories whose F1 is None omitted), "bootstrap": {"resamples", "method":
        "image-percentile", "level": 0.95, "seed"}, "aggregate_only": True. Contains no file name and no image id. ValueError (message names the argument) for resamples < 1, a
        non-int seed, a category outside the four probe classes in any annotation or prediction ("category_id").

module `s50_evaluate` (additions): spec["probe"] = {"images", "licence_records", "annotations_a", "annotations_b", "predictions"} (the arguments above; "annotations_b" may be None). When present,
    load_probe (ProbeError propagates, no report), evaluate_probe with the bootstrap seed, and report["real_probe"] = the block; the report's top-level `sim_to_real` becomes "measured"; the
    rows of the class "boulder" stay "not measured" (no probe class).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_ap_kit as apkit  # noqa: E402
import _p009_s50_kit as k50  # noqa: E402
from pitstudio_pipeline.perception import probe, s50_evaluate  # noqa: E402

TOL = 1e-9
PERSON, TRUCK = 4, 1


def _box(image_id: int, cat: int, bbox) -> dict:
    return {"image_id": image_id, "category_id": cat, "bbox": [float(v) for v in bbox]}


def _images(n: int = 6) -> list[dict]:
    return [{"id": i, "file_name": f"probe_private_{i:03d}.jpg"} for i in range(1, n + 1)]


A = [
    *[_box(i, PERSON, (10, 10, 20, 40)) for i in (1, 2, 3, 4)],
    _box(5, TRUCK, (10, 10, 60, 30)),
    _box(5, TRUCK, (100, 10, 60, 30)),
    _box(6, TRUCK, (10, 10, 60, 30)),
]
B = [
    _box(1, PERSON, (10, 10, 20, 40)),
    _box(2, PERSON, (10, 10, 20, 40)),
    _box(3, PERSON, (70, 70, 20, 40)),  # shifted: IoU 0 with A's person of image 3
    _box(4, PERSON, (10, 10, 20, 40)),
    _box(5, TRUCK, (10, 10, 60, 30)),
    _box(5, TRUCK, (300, 200, 60, 30)),  # shifted
    _box(6, TRUCK, (10, 10, 60, 30)),
]
DET_S = [
    apkit.detection(1, PERSON, (10, 10, 20, 40), 0.9),
    apkit.detection(2, PERSON, (10, 10, 20, 40), 0.8),
    apkit.detection(3, PERSON, (10, 10, 20, 40), 0.7),
    apkit.detection(5, TRUCK, (10, 10, 60, 30), 0.95),
    apkit.detection(5, TRUCK, (100, 10, 60, 30), 0.94),
]


def _block(**kw) -> dict:
    args = {
        "images": _images(),
        "annotations_a": A,
        "annotations_b": B,
        "predictions": {"d-fine-s": DET_S, "d-fine-n": []},
        "seed": 90212,
        "resamples": 40,
    }
    args.update(kw)
    return probe.evaluate_probe(**args)


# ---------------------------------------------------------------- agreement F1


@pytest.mark.req("FR-009-33")
def test_two_labellers_with_three_boxes_each_and_two_matches_have_f1_two_thirds() -> None:
    a = [_box(1, 1, (0, 0, 10, 10)), _box(1, 1, (50, 50, 10, 10)), _box(2, 1, (0, 0, 10, 10))]
    b = [_box(1, 1, (0, 0, 10, 10)), _box(1, 1, (200, 200, 10, 10)), _box(2, 1, (0, 0, 10, 10))]
    assert probe.agreement_f1(a, b)[1] == pytest.approx(2.0 / 3.0, abs=TOL)


@pytest.mark.req("FR-009-33")
def test_agreement_edge_cases() -> None:
    same = [_box(1, 4, (0, 0, 10, 10)), _box(2, 4, (5, 5, 10, 10))]
    assert probe.agreement_f1(same, same) == {4: pytest.approx(1.0, abs=TOL)}
    assert probe.agreement_f1([_box(1, 4, (0, 0, 10, 10))], [_box(1, 4, (100, 100, 10, 10))]) == {4: 0.0}
    assert probe.agreement_f1([], []) == {}
    assert probe.agreement_f1([_box(1, 2, (0, 0, 10, 10))], [])[2] == 0.0  # one labeller has a box, the other none
    # IoU exactly 0.5 matches: boxes [0,0,10,10] and [0,0,10,5]
    assert probe.agreement_f1([_box(1, 1, (0, 0, 10, 10))], [_box(1, 1, (0, 0, 10, 5))])[1] == pytest.approx(
        1.0, abs=TOL
    )
    # one-to-one: a single A box cannot match two B boxes: TP 1, F1 = 2 * 1 / (1 + 2) = 2/3
    assert probe.agreement_f1([_box(1, 1, (0, 0, 10, 10))], [_box(1, 1, (0, 0, 10, 10)), _box(1, 1, (0, 0, 10, 9))])[
        1
    ] == pytest.approx(2.0 / 3.0, abs=TOL)
    # same box in another image or another category never matches
    assert probe.agreement_f1([_box(1, 1, (0, 0, 10, 10))], [_box(2, 1, (0, 0, 10, 10))])[1] == 0.0
    assert probe.agreement_f1([_box(1, 1, (0, 0, 10, 10))], [_box(1, 3, (0, 0, 10, 10))]) == {1: 0.0, 3: 0.0}


@pytest.mark.req("FR-009-33")
def test_the_fixture_labellers_agree_with_f1_075_for_persons_and_two_thirds_for_trucks() -> None:
    f1 = probe.agreement_f1(A, B)
    assert f1[PERSON] == pytest.approx(0.75, abs=TOL)
    assert f1[TRUCK] == pytest.approx(2.0 / 3.0, abs=TOL)


# ---------------------------------------------------------------- the real_probe block


@pytest.mark.req("FR-009-33")
def test_the_block_holds_the_hand_computed_per_class_ap_and_the_labeller_b_sensitivity() -> None:
    blk = _block()
    assert blk["ground_truth"] == "labeller-a"
    assert blk["images"] == 6
    assert blk["excluded_images"] == 0
    assert blk["aggregate_only"] is True
    rows = {(r["model"], r["class"]): r for r in blk["per_class"]}
    assert set(rows) == {
        ("d-fine-n", "haul_truck"),
        ("d-fine-n", "person"),
        ("d-fine-s", "haul_truck"),
        ("d-fine-s", "person"),
    }
    assert rows[("d-fine-s", "person")]["support"] == 4
    assert rows[("d-fine-s", "haul_truck")]["support"] == 3
    assert rows[("d-fine-s", "person")]["ap50"] == pytest.approx(76 / 101, abs=TOL)
    assert rows[("d-fine-s", "haul_truck")]["ap50"] == pytest.approx(67 / 101, abs=TOL)
    for key in (("d-fine-n", "person"), ("d-fine-n", "haul_truck")):
        assert rows[key]["ap50"] == 0.0
        assert rows[key]["ap50_interval"] == {"lower": 0.0, "upper": 0.0}
    for r in rows.values():
        assert 0.0 <= r["ap50_interval"]["lower"] <= r["ap50_interval"]["upper"] <= 1.0
    by_model = {r["model"]: r["map50"] for r in blk["labeller_b_map50"]}
    assert by_model["d-fine-s"] == pytest.approx(85 / 202, abs=TOL)
    assert by_model["d-fine-n"] == 0.0
    assert [(r["class"], r["box_f1"], r["iou_threshold"]) for r in blk["agreement"]] == [
        ("haul_truck", pytest.approx(2 / 3, abs=TOL), 0.5),
        ("person", pytest.approx(0.75, abs=TOL), 0.5),
    ]
    assert blk["bootstrap"] == {"resamples": 40, "method": "image-percentile", "level": 0.95, "seed": 90212}


@pytest.mark.req("FR-009-33")
def test_the_block_validates_against_the_real_probe_definition_apart_from_the_test_resample_count() -> None:
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "contracts" / "detection-eval.schema.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator({"$ref": "#/$defs/real_probe", "$defs": schema["$defs"]}).iter_errors(_block()))
    assert [
        e.message for e in errors if list(e.absolute_path) != ["bootstrap", "resamples"]
    ] == []  # B = 40 here, 2000 in the product


@pytest.mark.req("FR-009-33")
def test_only_aggregate_metrics_are_published() -> None:
    text = json.dumps(_block())
    assert "probe_private" not in text
    assert "file_name" not in text
    assert "image_id" not in text


@pytest.mark.req("FR-009-33")
def test_the_block_is_deterministic_for_a_seed() -> None:
    assert _block() == _block()


@pytest.mark.req("FR-009-33")
@pytest.mark.parametrize(
    ("kwargs", "arg"),
    [
        ({"resamples": 0}, "resamples"),
        ({"seed": "1"}, "seed"),
        ({"annotations_a": [*A, _box(1, 5, (0, 0, 5, 5))]}, "category_id"),
        ({"predictions": {"d-fine-s": [apkit.detection(1, 7, (0, 0, 5, 5), 0.5)]}}, "category_id"),
    ],
)
def test_hostile_probe_evaluation_arguments_are_rejected(kwargs: dict, arg: str) -> None:
    with pytest.raises(ValueError, match=arg):
        _block(**kwargs)


# ---------------------------------------------------------------- FR-009-34: hostile probe inputs


def _recs(images: list[dict], spdx: str = "CC-BY-4.0") -> dict:
    return {i["file_name"]: {"spdx": spdx} for i in images}


@pytest.mark.req("FR-009-34")
@pytest.mark.parametrize("spdx", ["CC0-1.0", "CC-BY-2.0", "CC-BY-2.5", "CC-BY-3.0", "CC-BY-4.0", "public domain"])
def test_each_allowed_licence_is_accepted(spdx: str) -> None:
    imgs = _images(2)
    sel = probe.load_probe(imgs, _recs(imgs, spdx), annotations_b=[])
    assert sel.included == tuple(imgs)
    assert sel.excluded == ()
    assert spdx in probe.ALLOWED_LICENCES


@pytest.mark.req("FR-009-34")
def test_the_allowed_licence_set_is_exactly_the_six_of_the_spec() -> None:
    assert set(probe.ALLOWED_LICENCES) == {
        "CC0-1.0",
        "CC-BY-2.0",
        "CC-BY-2.5",
        "CC-BY-3.0",
        "CC-BY-4.0",
        "public domain",
    }
    assert tuple(probe.PROBE_CLASSES) == (1, 2, 3, 4)


@pytest.mark.req("FR-009-34")
@pytest.mark.parametrize(
    "spdx", ["CC-BY-NC-4.0", "CC-BY-SA-4.0", "All rights reserved", "", None, 7, "cc-by-4.0", "CC-BY-4.0 "]
)
def test_an_image_with_a_licence_outside_the_set_is_excluded_and_listed(spdx: object) -> None:
    imgs = _images(3)
    recs = _recs(imgs)
    recs[imgs[1]["file_name"]] = {"spdx": spdx}
    sel = probe.load_probe(imgs, recs, annotations_b=[])
    assert sel.included == (imgs[0], imgs[2])
    ((name, reason),) = sel.excluded
    assert name == imgs[1]["file_name"]
    assert reason


@pytest.mark.req("FR-009-34")
def test_an_image_without_a_licence_record_is_excluded_with_that_reason() -> None:
    imgs = _images(3)
    recs = _recs(imgs)
    del recs[imgs[2]["file_name"]]
    sel = probe.load_probe(imgs, recs, annotations_b=[])
    assert sel.included == (imgs[0], imgs[1])
    assert sel.excluded == ((imgs[2]["file_name"], sel.excluded[0][1]),)
    assert "licence" in sel.excluded[0][1].lower()


@pytest.mark.req("FR-009-34")
def test_every_excluded_image_is_listed_in_input_order() -> None:
    imgs = _images(5)
    recs = _recs(imgs)
    recs[imgs[0]["file_name"]] = {"spdx": "CC-BY-NC-4.0"}
    del recs[imgs[3]["file_name"]]
    sel = probe.load_probe(imgs, recs, annotations_b=[])
    assert [n for n, _ in sel.excluded] == [imgs[0]["file_name"], imgs[3]["file_name"]]
    assert sel.included == (imgs[1], imgs[2], imgs[4])


@pytest.mark.req("FR-009-34")
def test_200_supplied_images_are_accepted_and_201_are_refused_even_if_some_would_be_excluded() -> None:
    imgs = _images(200)
    assert len(probe.load_probe(imgs, _recs(imgs), annotations_b=[]).included) == 200
    many = _images(201)
    recs = _recs(many)
    for img in many[:5]:
        recs[img["file_name"]] = {
            "spdx": "CC-BY-NC-4.0"
        }  # 196 would remain: still refused, the count is of supplied images
    with pytest.raises(probe.ProbeError) as exc:
        probe.load_probe(many, recs, annotations_b=[])
    assert exc.value.code == "probe-invalid"
    assert "probe-invalid" in str(exc.value)


@pytest.mark.req("FR-009-34")
def test_a_missing_second_labeller_file_refuses_the_probe() -> None:
    imgs = _images(3)
    with pytest.raises(probe.ProbeError) as exc:
        probe.load_probe(imgs, _recs(imgs), annotations_b=None)
    assert exc.value.code == "probe-invalid"


@pytest.mark.req("FR-009-34")
@pytest.mark.parametrize(
    "images",
    [
        None,
        "images",
        [None],
        [{"id": 1}],
        [{"file_name": "a.jpg"}],
        [{"id": "1", "file_name": "a.jpg"}],
        [{"id": 1, "file_name": ""}],
        [{"id": 1, "file_name": "a.jpg"}, {"id": 1, "file_name": "b.jpg"}],
    ],
)
def test_malformed_image_lists_refuse_the_probe(images: object) -> None:
    with pytest.raises(probe.ProbeError) as exc:
        probe.load_probe(images, {}, annotations_b=[])  # type: ignore[arg-type]
    assert exc.value.code == "probe-invalid"


# ---------------------------------------------------------------- through s50_evaluate


def _probe_spec(**over) -> dict:
    imgs = _images()
    return {
        "images": imgs,
        "licence_records": _recs(imgs),
        "annotations_a": A,
        "annotations_b": B,
        "predictions": {"d-fine-s": DET_S, "d-fine-n": []},
    } | over


def _spec(**probe_over) -> dict:
    gt, family, cluster = k50.fraction_gt(100, 100)
    dets = k50.perfect_detections(gt, set(range(1, 181)))
    preds = [k50.prediction("d-fine-s", "fp32", "S", dets, gt), k50.prediction("d-fine-n", "fp32", "S", dets, gt)]
    return k50.spec(gt, family, cluster, preds, probe=_probe_spec(**probe_over))


@pytest.mark.req("FR-009-33")
def test_a_labelled_probe_adds_the_block_and_marks_the_probe_classes_measured() -> None:
    rep = s50_evaluate.run_s50_evaluate(_spec()).report
    assert rep["sim_to_real"] == "measured"
    blk = rep["real_probe"]
    assert blk["images"] == 6
    assert blk["aggregate_only"] is True
    assert blk["bootstrap"]["seed"] == rep["bootstrap"]["seed"]
    assert all(r["sim_to_real"] == "not measured" for r in k50.find_rows(rep, **{"class": "boulder"}))
    assert "probe_private" not in json.dumps(rep)


@pytest.mark.req("FR-009-34")
def test_a_refused_probe_gives_no_report() -> None:
    with pytest.raises(probe.ProbeError):
        s50_evaluate.run_s50_evaluate(_spec(annotations_b=None))
    imgs = _images(201)
    with pytest.raises(probe.ProbeError):
        s50_evaluate.run_s50_evaluate(_spec(images=imgs, licence_records=_recs(imgs)))


@pytest.mark.req("FR-009-34")
def test_an_unlicensed_probe_image_is_excluded_and_counted_in_the_block() -> None:
    imgs = _images()
    recs = _recs(imgs)
    recs[imgs[5]["file_name"]] = {"spdx": "CC-BY-NC-4.0"}
    rep = s50_evaluate.run_s50_evaluate(_spec(licence_records=recs)).report
    assert rep["real_probe"]["images"] == 5
    assert rep["real_probe"]["excluded_images"] == 1
    assert imgs[5]["file_name"] not in json.dumps(rep)
