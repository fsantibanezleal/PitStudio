# ruff: noqa: E501
"""The footprints of the B1 traffic recipe are the asset specification's dimensions (studio environment).

Oracle: `pitstudio_studio.scene.assets.catalogue.ENVELOPES`, the bounding boxes of the procedural machines that the asset
specification of the SDG scene places (Cat 793F sheet for the haul truck, Land Cruiser 79 sheet for the light vehicle, FR-004-51),
read independently of the recipe. The lane offset is checked against its derivation (0.875 x the truck width, so that a road of
3.5 x the truck width holds two lanes: Tannant and Regensburg 2001, Eq. 5).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

catalogue = pytest.importorskip("pitstudio_studio.scene.assets.catalogue")

ROOT = Path(__file__).resolve().parents[2]


def traffic_block() -> dict:
    recipe = yaml.safe_load((ROOT / "studio/recipes/cases/b1.yaml").read_text(encoding="utf-8"))
    return recipe["stages"][0]["params"]["traffic"]


def test_the_recipe_footprints_equal_the_asset_specification_envelopes() -> None:
    fp = traffic_block()["footprint_m"]
    truck, lv = catalogue.ENVELOPES["haul_truck"], catalogue.ENVELOPES["light_vehicle"]
    assert fp["haul-truck"] == [truck[0], truck[1]]
    assert fp["light-vehicle"] == [lv[0], lv[1]]


def test_the_lane_offset_is_the_derived_half_lane_of_a_road_of_3_5_truck_widths() -> None:
    width = catalogue.ENVELOPES["haul_truck"][1]
    assert traffic_block()["lane_offset_m"] == pytest.approx(0.875 * width, abs=5e-4)
    # opposing vehicles pass with their sides further apart than a truck width is wide
    assert 2 * traffic_block()["lane_offset_m"] - width > width * 0.7


def test_the_asset_specification_cites_its_dimensions() -> None:
    spec = {a["class_label"]: a for a in catalogue.machine_specification()["assets"]}
    assert "793F" in spec["haul_truck"]["dimensions_citation"]
    assert "Land Cruiser 79" in spec["light_vehicle"]["dimensions_citation"]
