# ruff: noqa: E501
"""T-009-019 - FR-009-14, FR-009-15, FR-009-42: dataset-index and COCO validation; hostile COCO files and handoff frames.

Oracles (independent of the code under test):
- the spec's own contract examples (`specs/009-perception/contracts/examples/`) with the JSON pointer each hostile example
  is listed under in `index.json` (produced by the reference validator `jsonschema`, Draft 2020-12);
- hand calculation for what a schema cannot say (plan 009 test strategy row FR-009-15): a COCO file is built from the
  valid example (two images 1280 x 720, annotations 1, 2 on image 123 and 3 on image 124) and ONE thing is damaged per
  test: NaN, width 0, negative height, a box 0.6 px past the right edge (allowed: 0.5 px), a duplicated id, an annotation
  pointing to image 999, an absolute / `..` / drive-letter / backslash / empty / unicode `file_name`;
- hand-built frames (PNG written with Pillow, bytes hashed with `hashlib`) for FR-009-42: a wrong SHA-256, a `../` path, a
  mask one pixel narrower than its RGB image (31 x 24 against 32 x 24), a class value 6 (and 255) in the semantic mask.

Expected public API (module `pitstudio_pipeline.perception.loader`, package under `pipeline/src/`):

    IndexRecordError(ValueError)     .line: int (1-based line of the JSON Lines file), .record_id: str | None,
                                     .pointer: str (RFC 6901 pointer of the first schema error; "" for the root or for a
                                     line that is not JSON), .reason: str
    IndexReadResult                  frozen dataclass: records: tuple[dict, ...] (valid records, file order, each equal to
                                     its parsed line: nothing coerced), rejected: tuple[IndexRecordError, ...]
    validate_index_record(record: object) -> None
        Validates one DC-009-01 record against perception-dataset.schema.json (Draft 2020-12, no format coercion, no type
        coercion: "123" is not 123, True is not 1). Raises IndexRecordError (line 0) for the first error.
    read_index(path: pathlib.Path) -> IndexReadResult
        Reads a JSON Lines file (one DC-009-01 record per non-empty line, UTF-8). A line that is not valid UTF-8 / JSON / an
        object, or that fails validate_index_record, is rejected (never coerced, never repaired) and the other lines are
        still read. A missing file raises FileNotFoundError.
    CocoError(ValueError)            .record_id: str ("image:<id>", "annotation:<id>", "category:<id>", "file"),
                                     .pointer: str, .reason: str; str(error) contains record_id and reason
    load_coco(path: pathlib.Path) -> dict
        Reads a DC-009-02 COCO file and returns the parsed document unchanged. Rejects the WHOLE file (raises CocoError, returns
        nothing) for: any schema violation (reason = the schema message; pointer = the schema error's absolute path), a
        non-finite number (reason contains "non-finite"; also the JSON tokens NaN/Infinity), a box with width or height <= 0
        (reason contains "box size"), a box extending beyond its image by more than 0.5 px on any side (reason contains
        "beyond image"), an unknown category id, a duplicated annotation id or image id (reason contains "duplicate"), an
        annotation whose image_id is not an image of the file (reason contains "missing image"), an image file_name that is
        absolute, contains "..", a drive letter or a backslash (reason contains "file_name"). An empty, truncated, non-JSON or
        non-UTF-8 file raises CocoError with record_id "file" and pointer "". Order of checks: JSON parse, non-finite
        numbers, schema, then the semantic checks (box size, margin, duplicates, dangling image, file_name).
    FrameRejected(ValueError)        .record_id: str, .code: one of "path-unsafe", "schema", "file-missing", "sha256-mismatch",
                                     "mask-size", "class-value"; .reason: str
    check_frame(record: Mapping, root: pathlib.Path) -> None
        Checks one handed-off frame whose files live under `root`, in this order and raising FrameRejected for the first
        failure: (1) every file reference of the record (any object with a "path" key) must be relative, free of "..",
        drive letters and backslashes ("path-unsafe"); (2) the record validates against DC-009-01 ("schema"); (3) every
        referenced file exists ("file-missing"); (4) the SHA-256 of every referenced file equals the record's
        ("sha256-mismatch"); (5) the semantic mask and the instance mask (if any) have the pixel size of the RGB image
        read from the PNG files ("mask-size"); (6) every semantic-mask value is in {0, 1, 2, 3, 4, 5} ("class-value").
    FrameFilterResult                frozen dataclass: accepted: tuple[dict, ...], rejected: tuple[FrameRejected, ...]
    filter_frames(records: Sequence[Mapping], root: pathlib.Path) -> FrameFilterResult
        check_frame on each record; the rejected frames are kept out of `accepted` (hence out of every split); input order.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_pipeline.perception import loader  # noqa: E402

INDEX = json.loads((kit.EXAMPLES / "index.json").read_text(encoding="utf-8"))["examples"]
COCO_HOSTILE = [
    (e["file"], e["pointer"]) for e in INDEX if e["schema"] == "coco-instances.schema.json" and not e["valid"]
]
RECORD_HOSTILE = [
    (e["file"], e["pointer"]) for e in INDEX if e["schema"] == "perception-dataset.schema.json" and not e["valid"]
]


def _write(path: Path, doc: object) -> Path:
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _coco_with(tmp_path: Path, mutate) -> Path:
    doc = kit.coco_doc()
    mutate(doc)
    return _write(tmp_path / "coco.json", doc)


def _reject(path: Path) -> loader.CocoError:
    with pytest.raises(loader.CocoError) as exc:
        loader.load_coco(path)
    assert isinstance(exc.value, ValueError)
    assert exc.value.record_id in str(exc.value)
    return exc.value


# ---------------------------------------------------------------- FR-009-14: dataset-index records


@pytest.mark.req("FR-009-14")
@pytest.mark.parametrize("kind", ["valid", "valid-unstructured", "valid-crusher"])
def test_the_three_valid_contract_records_are_accepted(kind: str) -> None:
    assert loader.validate_index_record(kit.index_record(kind)) is None


@pytest.mark.req("FR-009-14")
@pytest.mark.parametrize(("name", "pointer"), RECORD_HOSTILE, ids=[n for n, _ in RECORD_HOSTILE])
def test_every_hostile_contract_record_is_rejected_at_its_pointer(name: str, pointer: str) -> None:
    with pytest.raises(loader.IndexRecordError) as exc:
        loader.validate_index_record(kit.example(name))
    assert exc.value.pointer == pointer
    assert isinstance(exc.value, ValueError)


@pytest.mark.req("FR-009-14")
@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("coco_image_id",), "123"),  # a string is not coerced to an integer
        (("coco_image_id",), True),
        (("scenario_seed",), 4211.0 + 0.5),
        (("synthetic",), 1),
        (("image", "sha256"), "8796A5B4C3D2E1F092A3B4C5D6E7F80928394A5B6C7D8E9F8796A5B4C3D2E1F0"),
        (("image", "width_px"), "1280"),
        (("intrinsics", "fx_px"), "1108.5"),
    ],
)
def test_a_value_of_the_wrong_type_or_form_is_rejected_never_coerced(path: tuple[str, ...], value: object) -> None:
    rec = kit.index_record("valid")
    node = rec
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    before = copy.deepcopy(rec)
    with pytest.raises(loader.IndexRecordError) as exc:
        loader.validate_index_record(rec)
    assert exc.value.pointer == "/" + "/".join(path)
    assert rec == before  # the record was not repaired in place


@pytest.mark.req("FR-009-14")
@pytest.mark.parametrize("record", [None, [], "record", 7, {}, [kit.index_record("valid")]])
def test_a_value_that_is_not_a_record_object_is_rejected(record: object) -> None:
    with pytest.raises(loader.IndexRecordError):
        loader.validate_index_record(record)


@pytest.mark.req("FR-009-14")
def test_read_index_keeps_valid_lines_and_rejects_bad_ones_with_their_line_numbers(tmp_path: Path) -> None:
    good1, good2 = kit.index_record("valid"), kit.index_record("valid-crusher")
    bad = kit.index_record("valid")
    bad["record_id"] = "pit-s-000124"
    bad["synthetic"] = False
    lines = [
        json.dumps(good1),
        json.dumps(bad),
        "{not json",
        json.dumps(good2),
        json.dumps([1, 2]),
        json.dumps({**kit.index_record("valid"), "throughput_img_s": 12.0, "record_id": "pit-s-000125"}),
    ]
    p = tmp_path / "index.jsonl"
    p.write_bytes(("\n".join(lines) + "\n").encode("utf-8") + b"\xff\xfe\n")
    res = loader.read_index(p)
    assert res.records == (good1, good2)
    assert [e.line for e in res.rejected] == [2, 3, 5, 6, 7]
    assert res.rejected[0].record_id == "pit-s-000124"
    assert res.rejected[0].pointer == "/synthetic"
    assert res.rejected[1].pointer == ""
    assert res.rejected[3].pointer == ""  # unknown key: the schema error sits on the root object


@pytest.mark.req("FR-009-14")
def test_read_index_of_a_valid_file_returns_the_records_unchanged(tmp_path: Path) -> None:
    recs = [kit.index_record("valid"), kit.index_record("valid-unstructured"), kit.index_record("valid-crusher")]
    p = tmp_path / "index.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    res = loader.read_index(p)
    assert res.records == tuple(recs)
    assert res.rejected == ()


@pytest.mark.req("FR-009-14")
def test_read_index_of_a_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        loader.read_index(tmp_path / "absent.jsonl")


# ---------------------------------------------------------------- FR-009-14 / FR-009-15: COCO files


@pytest.mark.req("FR-009-14")
@pytest.mark.req("FR-009-15")
def test_the_valid_contract_coco_file_loads_unchanged(tmp_path: Path) -> None:
    p = _write(tmp_path / "coco.json", kit.coco_doc())
    assert loader.load_coco(p) == kit.coco_doc()


@pytest.mark.req("FR-009-14")
@pytest.mark.parametrize(("name", "pointer"), COCO_HOSTILE, ids=[n for n, _ in COCO_HOSTILE])
def test_every_hostile_contract_coco_example_is_rejected_whole_at_its_pointer(
    tmp_path: Path, name: str, pointer: str
) -> None:
    err = _reject(_write(tmp_path / "coco.json", kit.example(name)))
    assert err.pointer == pointer
    assert err.reason


@pytest.mark.req("FR-009-15")
@pytest.mark.parametrize(
    ("name", "ann_index", "record"),
    [
        ("coco-instances.hostile-iscrowd.json", 0, "annotation"),
        ("coco-instances.hostile-unknown-category.json", 1, "annotation"),
        ("coco-instances.hostile-box-left-edge.json", 0, "annotation"),
        ("coco-instances.hostile-wrong-shape.json", 0, "annotation"),
    ],
)
def test_an_annotation_error_names_the_annotation_by_its_id(
    tmp_path: Path, name: str, ann_index: int, record: str
) -> None:
    doc = kit.example(name)
    want = f"{record}:{doc['annotations'][ann_index]['id']}"
    assert _reject(_write(tmp_path / "coco.json", doc)).record_id == want


@pytest.mark.req("FR-009-15")
@pytest.mark.parametrize(
    ("name", "image_index"),
    [
        ("coco-instances.hostile-path-traversal.json", 0),
        ("coco-instances.hostile-absolute-path.json", 0),
        ("coco-instances.hostile-drive-letter.json", 1),
    ],
)
def test_a_file_name_error_names_the_image_by_its_id(tmp_path: Path, name: str, image_index: int) -> None:
    doc = kit.example(name)
    err = _reject(_write(tmp_path / "coco.json", doc))
    assert err.record_id == f"image:{doc['images'][image_index]['id']}"
    assert "file_name" in err.reason


@pytest.mark.req("FR-009-15")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("slot", [0, 1, 2, 3])
def test_a_non_finite_box_coordinate_rejects_the_file_naming_the_annotation(
    tmp_path: Path, bad: float, slot: int
) -> None:
    def damage(doc: dict) -> None:
        doc["annotations"][1]["bbox"][slot] = bad

    err = _reject(_coco_with(tmp_path, damage))
    assert err.record_id == "annotation:2"
    assert "non-finite" in err.reason


@pytest.mark.req("FR-009-15")
def test_a_non_finite_polygon_vertex_and_image_size_are_rejected(tmp_path: Path) -> None:
    def vertex(doc: dict) -> None:
        doc["annotations"][2]["segmentation"][0][1] = float("nan")

    assert _reject(_coco_with(tmp_path, vertex)).record_id == "annotation:3"
    p = tmp_path / "tokens.json"
    p.write_text(json.dumps(kit.coco_doc()).replace('"area": 408.0', '"area": NaN'), encoding="utf-8")
    err = _reject(p)
    assert err.record_id == "annotation:2"
    assert "non-finite" in err.reason


def _ann(ann_id: int, image_id: int, category_id: int, bbox: list[float], width: int, height: int) -> dict:
    """An annotation whose box is `bbox` and whose polygon is the box clipped to the image (vertices inside the image)."""
    x, y, w, h = bbox
    x0, y0, x1, y1 = max(x, 0.0), max(y, 0.0), min(x + w, float(width)), min(y + h, float(height))
    return {
        "id": ann_id,
        "image_id": image_id,
        "category_id": category_id,
        "bbox": bbox,
        "segmentation": [[x0, y0, x1, y0, x1, y1, x0, y1]],
        "area": (x1 - x0) * (y1 - y0),
        "iscrowd": 0,
    }


@pytest.mark.req("FR-009-15")
@pytest.mark.parametrize(("w", "h"), [(0.0, 96.0), (180.0, 0.0), (-5.0, 96.0), (180.0, -1.0)])
def test_a_box_with_width_or_height_not_positive_rejects_the_file(tmp_path: Path, w: float, h: float) -> None:
    def damage(doc: dict) -> None:
        ann = _ann(1, 123, 1, [412.0, 230.0, 180.0, 96.0], 1280, 720)
        ann["bbox"][2], ann["bbox"][3] = w, h
        doc["annotations"][0] = ann

    assert _reject(_coco_with(tmp_path, damage)).record_id == "annotation:1"


@pytest.mark.req("FR-009-15")
@pytest.mark.parametrize(
    ("bbox", "ok"),
    [
        ([1100.0, 100.0, 180.5, 50.0], True),  # right edge at 1280.5 = 1280 + 0.5: allowed
        ([1100.0, 100.0, 180.6, 50.0], False),  # 0.6 px past the right edge
        ([100.0, 670.0, 50.0, 50.5], True),  # bottom edge at 720.5: allowed
        ([100.0, 670.0, 50.0, 50.6], False),  # 0.6 px past the bottom edge
        ([-0.5, 10.0, 20.5, 20.0], True),  # left edge at -0.5: allowed
        ([10.0, -0.5, 20.0, 20.5], True),  # top edge at -0.5: allowed
    ],
)
def test_a_box_may_extend_at_most_half_a_pixel_beyond_its_image(tmp_path: Path, bbox: list[float], ok: bool) -> None:
    def damage(doc: dict) -> None:
        doc["annotations"][0] = _ann(1, 123, 1, bbox, 1280, 720)

    p = _coco_with(tmp_path, damage)
    if ok:
        assert loader.load_coco(p)["annotations"][0]["bbox"] == bbox
    else:
        err = _reject(p)
        assert err.record_id == "annotation:1"
        assert "beyond image" in err.reason


@pytest.mark.req("FR-009-15")
def test_the_half_pixel_margin_is_measured_against_the_size_of_the_annotations_own_image(tmp_path: Path) -> None:
    def damage(doc: dict) -> None:
        doc["images"][1]["width"] = 640  # image 124 is narrower
        doc["annotations"][2] = _ann(3, 124, 5, [600.0, 400.0, 41.0, 20.0], 640, 720)  # right edge 641 > 640.5

    assert _reject(_coco_with(tmp_path, damage)).record_id == "annotation:3"


@pytest.mark.req("FR-009-15")
def test_a_duplicated_annotation_id_rejects_the_file(tmp_path: Path) -> None:
    def damage(doc: dict) -> None:
        doc["annotations"][2]["id"] = 2

    err = _reject(_coco_with(tmp_path, damage))
    assert err.record_id == "annotation:2"
    assert "duplicate" in err.reason


@pytest.mark.req("FR-009-15")
def test_a_duplicated_image_id_rejects_the_file(tmp_path: Path) -> None:
    def damage(doc: dict) -> None:
        doc["images"][1]["id"] = 123
        doc["annotations"][2]["image_id"] = 123

    err = _reject(_coco_with(tmp_path, damage))
    assert err.record_id == "image:123"
    assert "duplicate" in err.reason


@pytest.mark.req("FR-009-15")
def test_an_annotation_pointing_to_a_missing_image_rejects_the_file(tmp_path: Path) -> None:
    def damage(doc: dict) -> None:
        doc["annotations"][1]["image_id"] = 999

    err = _reject(_coco_with(tmp_path, damage))
    assert err.record_id == "annotation:2"
    assert "missing image" in err.reason


@pytest.mark.req("FR-009-15")
@pytest.mark.parametrize(
    "name",
    [
        "/abs/x.png",
        "..",
        "a/../b.png",
        "C:/x.png",
        "c:x.png",
        "a\\b.png",
        "",
        "rgb/\u00fcnic\u00f6de.png",
        "//server/share/x.png",
    ],
)
def test_an_unsafe_or_malformed_file_name_rejects_the_file(tmp_path: Path, name: str) -> None:
    def damage(doc: dict) -> None:
        doc["images"][0]["file_name"] = name

    err = _reject(_coco_with(tmp_path, damage))
    assert err.record_id == "image:123"
    assert "file_name" in err.reason


@pytest.mark.req("FR-009-15")
@pytest.mark.parametrize(
    "content", [b"", b"   ", b"{", b"[]", b"null", b"\xff\xfe\x00{}", b"\x89PNG\r\n\x1a\n", b"[1, 2]"]
)
def test_an_empty_truncated_or_malformed_file_is_rejected_at_the_root(tmp_path: Path, content: bytes) -> None:
    p = tmp_path / "bad.json"
    p.write_bytes(content)
    err = _reject(p)
    assert err.record_id == "file"
    assert err.pointer == ""


@pytest.mark.req("FR-009-15")
def test_a_file_without_images_or_categories_is_rejected_whole(tmp_path: Path) -> None:
    p = _write(tmp_path / "coco.json", {"images": [], "annotations": [], "categories": []})
    err = _reject(p)
    assert err.record_id == "file"
    assert err.pointer in {"/images", "/categories"}  # two schema errors; either is "the first" (ambiguity reported)


@pytest.mark.req("FR-009-15")
def test_a_missing_coco_file_raises_a_file_error_not_a_coco_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        loader.load_coco(tmp_path / "absent.json")


@pytest.mark.req("FR-009-14")
@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("annotations", 0, "bbox"), ["412", "230", "180", "96"]),
        (("annotations", 0, "id"), "1"),
        (("annotations", 0, "area"), "17280"),
        (("annotations", 0, "iscrowd"), False),
        (("images", 0, "id"), 123.5),
        (("images", 0, "width"), "1280"),
    ],
)
def test_coco_values_of_the_wrong_type_are_rejected_never_coerced(tmp_path: Path, path: tuple, value: object) -> None:
    doc = kit.coco_doc()
    node = doc
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    err = _reject(_write(tmp_path / "coco.json", doc))
    assert err.pointer.startswith("/" + "/".join(str(k) for k in path))


# ---------------------------------------------------------------- FR-009-42: handed-off frames


def _png(path: Path, array: np.ndarray) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array).save(path, format="PNG")


def _file_entry(root: Path, rel: str, extra: dict | None = None) -> dict:
    data = (root / rel).read_bytes()
    return {"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), **(extra or {})}


def _crusher_frame(
    root: Path,
    *,
    shard: str = "shard-0001",
    record_id: str = "crusher-s-000001",
    w: int = 32,
    h: int = 24,
    sem_w: int | None = None,
    sem_value: int = 5,
) -> dict:
    """A valid crusher-family record whose files exist under `root` (32 x 24 px by default); the semantic mask holds
    background 0 and one rectangle of class value `sem_value`."""
    rng = np.random.default_rng(1)
    base = f"sensors/s3-crusher/{shard}"
    _png(root / f"{base}/rgb/000001.png", rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8))
    sw = sem_w or w
    sem = np.zeros((h, sw), dtype=np.uint8)
    sem[2:6, 3:9] = sem_value
    _png(root / f"{base}/semantic/000001.png", sem)
    (root / f"{base}/depth").mkdir(parents=True, exist_ok=True)
    np.save(root / f"{base}/depth/000001.npy", np.full((h, w), 12.5, dtype=np.float32))
    (root / f"{base}/coco_instances.json").write_text(json.dumps(kit.coco_doc()), encoding="utf-8")
    rec = kit.index_record("valid-crusher")
    rec["record_id"] = record_id
    rec["image"] = _file_entry(
        root, f"{base}/rgb/000001.png", {"width_px": w, "height_px": h, "format": "png", "colour_space": "srgb"}
    )
    rec["semantic_mask"] = _file_entry(
        root, f"{base}/semantic/000001.png", {"width_px": sw, "height_px": h, "format": "png"}
    )
    depth_extra = {"width_px": w, "height_px": h, "format": "npy", "dtype": "float32", "unit": "m"}
    rec["depth"] = _file_entry(root, f"{base}/depth/000001.npy", {**depth_extra, "quantity": "distance-to-camera"})
    rec["coco"] = _file_entry(root, f"{base}/coco_instances.json")
    return rec


@pytest.mark.req("FR-009-42")
def test_a_consistent_crusher_frame_is_accepted(tmp_path: Path) -> None:
    assert loader.check_frame(_crusher_frame(tmp_path), tmp_path) is None


@pytest.mark.req("FR-009-42")
def test_a_changed_file_is_rejected_with_the_record_id_and_a_digest_code(tmp_path: Path) -> None:
    rec = _crusher_frame(tmp_path)
    path = tmp_path / rec["image"]["path"]
    data = bytearray(path.read_bytes())
    data[-5] ^= 0x01  # one flipped bit at the end of the PNG
    path.write_bytes(bytes(data))
    with pytest.raises(loader.FrameRejected) as exc:
        loader.check_frame(rec, tmp_path)
    assert exc.value.record_id == "crusher-s-000001"
    assert exc.value.code == "sha256-mismatch"
    assert "image" in exc.value.reason
    assert isinstance(exc.value, ValueError)


@pytest.mark.req("FR-009-42")
@pytest.mark.parametrize("key", ["image", "semantic_mask", "depth", "coco"])
def test_every_referenced_file_is_digest_checked(tmp_path: Path, key: str) -> None:
    rec = _crusher_frame(tmp_path)
    rec[key]["sha256"] = "0" * 64
    with pytest.raises(loader.FrameRejected) as exc:
        loader.check_frame(rec, tmp_path)
    assert exc.value.code == "sha256-mismatch"
    assert key in exc.value.reason


@pytest.mark.req("FR-009-42")
@pytest.mark.parametrize(
    "bad_path",
    [
        "../escape/000001.png",
        "/abs/000001.png",
        "C:/rgb/000001.png",
        "sensors\\s3\\000001.png",
        "a/../../b.png",
        "c:rgb.png",
    ],
)
def test_an_unsafe_path_in_the_record_is_rejected_before_any_file_is_read(tmp_path: Path, bad_path: str) -> None:
    rec = _crusher_frame(tmp_path)
    rec["image"]["path"] = bad_path
    with pytest.raises(loader.FrameRejected) as exc:
        loader.check_frame(rec, tmp_path)
    assert exc.value.code == "path-unsafe"
    assert exc.value.record_id == "crusher-s-000001"


@pytest.mark.req("FR-009-42")
def test_an_unsafe_path_is_reported_before_a_schema_error(tmp_path: Path) -> None:
    rec = _crusher_frame(tmp_path)
    rec["depth"]["path"] = "../depth.npy"
    rec["synthetic"] = False
    with pytest.raises(loader.FrameRejected) as exc:
        loader.check_frame(rec, tmp_path)
    assert exc.value.code == "path-unsafe"


@pytest.mark.req("FR-009-42")
def test_a_schema_error_is_reported_as_a_schema_rejection(tmp_path: Path) -> None:
    rec = _crusher_frame(tmp_path)
    rec["synthetic"] = False
    with pytest.raises(loader.FrameRejected) as exc:
        loader.check_frame(rec, tmp_path)
    assert exc.value.code == "schema"
    assert "/synthetic" in exc.value.reason


@pytest.mark.req("FR-009-42")
def test_a_missing_file_is_rejected(tmp_path: Path) -> None:
    rec = _crusher_frame(tmp_path)
    (tmp_path / rec["semantic_mask"]["path"]).unlink()
    with pytest.raises(loader.FrameRejected) as exc:
        loader.check_frame(rec, tmp_path)
    assert exc.value.code == "file-missing"


@pytest.mark.req("FR-009-42")
def test_a_semantic_mask_one_pixel_narrower_than_its_rgb_image_is_rejected(tmp_path: Path) -> None:
    rec = _crusher_frame(
        tmp_path, w=32, h=24, sem_w=31
    )  # digests and record sizes are consistent: only the size differs
    with pytest.raises(loader.FrameRejected) as exc:
        loader.check_frame(rec, tmp_path)
    assert exc.value.code == "mask-size"
    assert exc.value.record_id == "crusher-s-000001"


@pytest.mark.req("FR-009-42")
@pytest.mark.parametrize("bad_value", [6, 7, 255])
def test_a_class_value_outside_zero_to_five_in_the_semantic_mask_is_rejected(tmp_path: Path, bad_value: int) -> None:
    rec = _crusher_frame(tmp_path, sem_value=bad_value)
    with pytest.raises(loader.FrameRejected) as exc:
        loader.check_frame(rec, tmp_path)
    assert exc.value.code == "class-value"


@pytest.mark.req("FR-009-42")
@pytest.mark.parametrize("value", [0, 1, 2, 3, 4, 5])
def test_every_class_value_of_the_contract_is_accepted(tmp_path: Path, value: int) -> None:
    assert loader.check_frame(_crusher_frame(tmp_path, sem_value=value), tmp_path) is None


def _pit_frame(root: Path, *, inst_w: int = 1280) -> dict:
    rng = np.random.default_rng(2)
    base = "sdg/pit-structured/shard-0003"
    _png(root / f"{base}/rgb/000123.png", rng.integers(0, 256, size=(720, 1280, 3), dtype=np.uint8))
    _png(root / f"{base}/semantic/000123.png", np.zeros((720, 1280), dtype=np.uint8))
    _png(root / f"{base}/instance/000123.png", np.zeros((720, inst_w), dtype=np.uint16))
    (root / f"{base}/depth").mkdir(parents=True, exist_ok=True)
    np.save(root / f"{base}/depth/000123.npy", np.full((720, 1280), 10.0, dtype=np.float32))
    (root / f"{base}/coco_instances.json").write_text(json.dumps(kit.coco_doc()), encoding="utf-8")
    (root / f"{base}/frame_state").mkdir(parents=True, exist_ok=True)
    (root / f"{base}/frame_state/000123.json").write_text("{}", encoding="utf-8")
    rec = kit.index_record("valid")
    rec["image"] = _file_entry(
        root, f"{base}/rgb/000123.png", {"width_px": 1280, "height_px": 720, "format": "png", "colour_space": "srgb"}
    )
    rec["semantic_mask"] = _file_entry(
        root, f"{base}/semantic/000123.png", {"width_px": 1280, "height_px": 720, "format": "png"}
    )
    rec["instance_mask"] = _file_entry(
        root, f"{base}/instance/000123.png", {"width_px": inst_w, "height_px": 720, "format": "png"}
    )
    depth_extra = {"width_px": 1280, "height_px": 720, "format": "npy", "dtype": "float32", "unit": "m"}
    rec["depth"] = _file_entry(root, f"{base}/depth/000123.npy", {**depth_extra, "quantity": "distance-to-image-plane"})
    rec["coco"] = _file_entry(root, f"{base}/coco_instances.json")
    rec["frame_state"] = _file_entry(root, f"{base}/frame_state/000123.json")
    return rec


@pytest.mark.req("FR-009-42")
def test_a_consistent_pit_frame_with_an_instance_mask_is_accepted(tmp_path: Path) -> None:
    assert loader.check_frame(_pit_frame(tmp_path), tmp_path) is None


@pytest.mark.req("FR-009-42")
def test_an_instance_mask_of_another_size_than_the_rgb_image_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(loader.FrameRejected) as exc:
        loader.check_frame(_pit_frame(tmp_path, inst_w=1279), tmp_path)
    assert exc.value.code == "mask-size"
    assert exc.value.record_id == "pit-s-000123"


@pytest.mark.req("FR-009-42")
def test_rejected_frames_are_kept_out_of_the_accepted_set_and_listed_in_input_order(tmp_path: Path) -> None:
    good = _crusher_frame(tmp_path, shard="shard-0001", record_id="crusher-s-000001")
    stale = _crusher_frame(tmp_path, shard="shard-0002", record_id="crusher-s-000002")
    stale["image"]["sha256"] = "1" * 64  # the record no longer matches its file
    bad_class = _crusher_frame(tmp_path, shard="shard-0003", record_id="crusher-s-000003", sem_value=6)
    last = _crusher_frame(tmp_path, shard="shard-0004", record_id="crusher-s-000004")
    res = loader.filter_frames([good, stale, bad_class, last], tmp_path)
    assert res.accepted == (good, last)
    assert [(r.record_id, r.code) for r in res.rejected] == [
        ("crusher-s-000002", "sha256-mismatch"),
        ("crusher-s-000003", "class-value"),
    ]
    assert loader.filter_frames([], tmp_path) == loader.FrameFilterResult(accepted=(), rejected=())
