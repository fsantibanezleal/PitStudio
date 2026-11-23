"""`tools/bake_web_terrain.py`: the import spec of a bake report (web-terrain-3d-2026-11-23, T-016-033).

Oracles: the manifest contract (artefact id pattern, stage output limit, licence classes), the report layout of
`pitstudio_pipeline.export.web_terrain`, hand-written reports.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import bake_web_terrain as tool

EXCHANGE = {
    "input_digests": {
        "usgs-3dep-bingham": "a" * 64,
        "usda-naip-bingham": "b" * 64,
        "polyhaven-rock-boulder-dry": "c" * 64,
    },
    "producer": {"tool": "openusd", "version": "0.25.8"},
    "scene": {"manifest_id": "a1-scene-test"},
}


def report(n_tiles: int = 3, errors: int = 0) -> dict:
    files = [
        {"path": "tiles/lod0/tileset.json", "role": "tileset", "level": "lod0", "bytes": 240, "sha256": "1" * 64},
        {"path": "tiles/lod0/lod0.glb", "role": "tile", "level": "lod0", "bytes": 4000, "sha256": "2" * 64},
        {"path": "tiles/detail/tileset.json", "role": "tileset", "level": "detail", "bytes": 900, "sha256": "3" * 64},
        *[
            {
                "path": f"tiles/detail/lod1/l1-{i}-0.glb",
                "role": "tile",
                "level": "lod1",
                "bytes": 5000,
                "sha256": "4" * 64,
            }
            for i in range(n_tiles)
        ],
        {
            "path": "tiles/textures/rock-normal.jpg",
            "role": "texture",
            "level": "shared",
            "bytes": 900,
            "sha256": "5" * 64,
        },
    ]
    return {"files": files, "totals": {"validator_errors": errors}}


def test_every_file_of_the_report_becomes_one_published_output_with_its_licence_and_inputs() -> None:
    spec = tool.build_import_spec(report(), EXCHANGE)
    assert spec["kind"] == "bake"
    assert spec["all_cases"] is True
    assert spec["stages"][0]["id"] == "s60_export"
    assert spec["stages"][0]["tool"] == "openusd"
    outs = {o["name"]: o for o in spec["stages"][0]["outputs"]}
    assert set(outs) == {f["path"] for f in report()["files"]} | {"tiles/bake-report.json"}
    tileset, tile, texture = (
        outs["tiles/lod0/tileset.json"],
        outs["tiles/lod0/lod0.glb"],
        outs["tiles/textures/rock-normal.jpg"],
    )
    assert (tileset["kind"], tileset["media_type"], tileset["id"]) == (
        "tiles",
        "application/json",
        "bingham-lod0-tileset",
    )
    assert (tile["kind"], tile["media_type"]) == ("tiles", "model/gltf-binary")
    assert [i["id"] for i in tileset["inputs"]] == ["usgs-3dep-bingham", "usda-naip-bingham"]
    assert tileset["spdx"] == "LicenseRef-USGov-PD"
    assert tileset["licence_class"] == "public-domain"
    assert (texture["kind"], texture["spdx"], texture["licence_class"]) == ("image", "CC0-1.0", "open-no-attribution")
    assert texture["inputs"] == [{"id": "polyhaven-rock-boulder-dry", "sha256": "c" * 64, "kind": "source"}]
    assert all(o["publish"] and o["budget_class"] == "tiles-glb" for o in outs.values())


def test_artefact_ids_follow_the_contract_pattern_and_are_unique() -> None:
    spec = tool.build_import_spec(report(8), EXCHANGE)
    ids = [o["id"] for o in spec["stages"][0]["outputs"]]
    assert len(set(ids)) == len(ids)
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", i) for i in ids)


def test_a_report_with_a_validator_error_publishes_nothing() -> None:
    with pytest.raises(tool.BakeToolError, match="validator errors"):
        tool.build_import_spec(report(errors=1), EXCHANGE)


def test_more_outputs_than_a_stage_record_holds_are_refused() -> None:
    assert len(tool.build_import_spec(report(40), EXCHANGE)["stages"][0]["outputs"]) <= tool.MAX_STAGE_OUTPUTS
    with pytest.raises(tool.BakeToolError, match="exceed"):
        tool.build_import_spec(report(60), EXCHANGE)
