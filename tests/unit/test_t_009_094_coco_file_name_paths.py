# ruff: noqa: E501
"""T-009-094 - FR-009-48: COCO `file_name` device names and case-folded duplicates (`coco-path-invalid`).

Oracles (independent of the code under test):
- the reserved DOS device names of Windows, from Microsoft's "Naming Files, Paths, and Namespaces" (learn.microsoft.com, file-system/naming-a-file): CON, PRN, AUX, NUL, COM1 .. COM9, LPT1 .. LPT9, reserved
  with or without an extension ("nul.png" is the device) and in any letter case; COM10 / LPT10, "console", "null" and "aux1" are ordinary names. The page was not re-read during this phase (UNVERIFIED against the
  primary source; the list is the well-known one);
- hand calculation of plan 009 (test strategy row FR-009-48): `nul.png` is rejected; `A.png` together with `a.png` is rejected, both entries named; the check applies to every path segment, not only the last;
- case folding is Python's str.casefold (the two file names are equal after folding), so `Rgb/A.PNG` and `rgb/a.png` collide.

Expected public API (module `pitstudio_pipeline.perception.loader`, see tests/unit/test_t_009_019_coco_loader.py and test_t_009_093_coco_polygon_consistency.py): `load_coco` raises CocoError with
`.code == "coco-path-invalid"`, `.record_id` ("image:<id>" of the offending image; of the SECOND image of a colliding pair) and `.entries: tuple[str, ...]` (the offending file name for a device name; BOTH file names of a
collision, first occurrence first); str(error) contains the code and every entry. Device names are tested on every "/"-separated segment: the part before the first "." compared case-insensitively with the reserved names.
`CocoError.entries` is () for every other code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_pipeline.perception import loader  # noqa: E402


def _file(tmp_path: Path, names: list[str]) -> Path:
    doc = {
        "images": [{"id": i + 1, "file_name": n, "width": 1280, "height": 720} for i, n in enumerate(names)],
        "annotations": [],
        "categories": kit.coco_doc()["categories"],
    }
    p = tmp_path / "coco.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def _bad(path: Path) -> loader.CocoError:
    with pytest.raises(loader.CocoError) as exc:
        loader.load_coco(path)
    assert exc.value.code == "coco-path-invalid"
    assert "coco-path-invalid" in str(exc.value)
    return exc.value


RESERVED = ["con", "prn", "aux", "nul", *[f"com{i}" for i in range(1, 10)], *[f"lpt{i}" for i in range(1, 10)]]


@pytest.mark.req("FR-009-48")
def test_nul_png_is_rejected_naming_the_entry(tmp_path: Path) -> None:
    err = _bad(_file(tmp_path, ["rgb/000001.png", "nul.png"]))
    assert err.entries == ("nul.png",)
    assert err.record_id == "image:2"
    assert "nul.png" in str(err)


@pytest.mark.req("FR-009-48")
@pytest.mark.parametrize("device", RESERVED)
@pytest.mark.parametrize("form", ["{d}.png", "{D}.png", "{d}", "{d}.tar.gz", "rgb/{d}/000001.png", "rgb/{D}.PNG"])
def test_every_reserved_device_name_is_rejected_in_any_case_with_or_without_extension_and_in_any_segment(
    tmp_path: Path, device: str, form: str
) -> None:
    name = form.format(d=device, D=device.upper())
    err = _bad(_file(tmp_path, [name]))
    assert err.entries == (name,)


@pytest.mark.req("FR-009-48")
@pytest.mark.parametrize(
    "name",
    [
        "console.png",
        "null.png",
        "aux1.png",
        "com10.png",
        "lpt10.png",
        "com.png",
        "rgb/prn_1.png",
        "conn.png",
        "xcon.png",
        "rgb/nu.png",
        "a.con.png",
    ],
)
def test_names_that_merely_resemble_devices_are_accepted(tmp_path: Path, name: str) -> None:
    assert loader.load_coco(_file(tmp_path, [name]))["images"][0]["file_name"] == name


@pytest.mark.req("FR-009-48")
def test_two_file_names_equal_after_case_folding_are_rejected_naming_both(tmp_path: Path) -> None:
    err = _bad(_file(tmp_path, ["rgb/x.png", "A.png", "rgb/y.png", "a.png"]))
    assert err.entries == ("A.png", "a.png")
    assert err.record_id == "image:4"
    assert "A.png" in str(err)
    assert "a.png" in str(err)


@pytest.mark.req("FR-009-48")
@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Rgb/A.PNG", "rgb/a.png"),
        ("a/b/C.png", "A/B/c.PNG"),
        ("same.png", "same.png"),
        ("Frame_001.Png", "frame_001.png"),
    ],
)
def test_collisions_inside_a_folder_tree_and_exact_repeats_are_rejected(tmp_path: Path, a: str, b: str) -> None:
    assert _bad(_file(tmp_path, [a, b])).entries == (a, b)


@pytest.mark.req("FR-009-48")
def test_distinct_names_that_differ_by_more_than_case_are_accepted(tmp_path: Path) -> None:
    names = ["a.png", "b.png", "A1.png", "rgb/a.png", "rgb/A_.png"]
    assert [i["file_name"] for i in loader.load_coco(_file(tmp_path, names))["images"]] == names


@pytest.mark.req("FR-009-48")
def test_the_first_problem_in_image_order_is_reported(tmp_path: Path) -> None:
    err = _bad(_file(tmp_path, ["A.png", "a.png", "nul.png"]))
    assert err.entries == ("A.png", "a.png")  # the collision (image 2) comes before the device name (image 3)
    err2 = _bad(_file(tmp_path, ["con.png", "A.png", "a.png"]))
    assert err2.entries == ("con.png",)


@pytest.mark.req("FR-009-48")
def test_other_coco_errors_carry_no_entries(tmp_path: Path) -> None:
    p = _file(tmp_path, ["rgb/000001.png"])
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["images"][0]["file_name"] = "../x.png"
    p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(loader.CocoError) as exc:
        loader.load_coco(p)
    assert exc.value.entries == ()
    assert exc.value.code != "coco-path-invalid" or "file_name" in exc.value.reason
