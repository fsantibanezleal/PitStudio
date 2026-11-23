# ruff: noqa: E501, PT018
"""T-009-016 (fix): the SDG texture pool is arid rock without vegetation tint, each texture registered (FR-009-08, FR-004-26).

Requirements: FR-009-08 (the unstructured arm draws textures from the whole pool), FR-004-26 (CC0 materials with their
source), FR-009-02.

Oracles: the definition of the vegetation tint (the share of pixels with HSV hue from 60 to 150 degrees and saturation
above 0.25, below 2 percent), checked on synthetic images whose colours are written in HSV here (a solid colour is 0 or
100 percent, a half-and-half image 50 percent, the hue limits 59, 61, 149 and 151 degrees fall on the stated side), and
the registry schema (`contracts/sources.schema.json`) for the registration of each texture.

Expected API (`tools/sdg_inputs.py`, studio environment with Pillow and NumPy): `vegetation_tint_pct(image: bytes) -> float`,
`TINT_LIMIT_PCT == 2.0`, `_checked_tint(texture_id, image) -> float` (exits naming the texture at or above the limit),
the pool lists `AMBIENTCG` and `POLYHAVEN`, `LITHOLOGIES`, `MATERIALS`.
"""

from __future__ import annotations

import colorsys
import importlib.util
import io
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "src"))
_spec = importlib.util.spec_from_file_location("sdg_inputs_tool_textures", ROOT / "tools" / "sdg_inputs.py")
assert _spec is not None and _spec.loader is not None
tool = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tool
_spec.loader.exec_module(tool)

REMOVED = ("rock063", "rock064", "ground068", "aerial-rocks-01", "aerial-rocks-02", "rocky-terrain")


def _png(
    colour_hsv: tuple[float, float, float], size: int = 64, second: tuple[float, float, float] | None = None
) -> bytes:
    from PIL import Image

    def rgb(c):
        return tuple(round(v * 255) for v in colorsys.hsv_to_rgb(c[0] / 360.0, c[1], c[2]))

    image = Image.new("RGB", (size, size), rgb(colour_hsv))
    if second is not None:
        half = Image.new("RGB", (size // 2, size), rgb(second))
        image.paste(half, (0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.req("FR-009-08")
def test_the_tint_is_the_share_of_green_yellow_green_pixels() -> None:
    assert tool.TINT_LIMIT_PCT == 2.0
    assert tool.vegetation_tint_pct(_png((120.0, 0.8, 0.6))) == pytest.approx(100.0)
    assert tool.vegetation_tint_pct(_png((30.0, 0.5, 0.6))) == pytest.approx(0.0)  # brown rock
    assert tool.vegetation_tint_pct(_png((0.0, 0.0, 0.5))) == pytest.approx(0.0)  # grey
    assert tool.vegetation_tint_pct(_png((120.0, 0.8, 0.6), second=(30.0, 0.5, 0.6))) == pytest.approx(50.0, abs=1.0)


@pytest.mark.req("FR-009-08")
@pytest.mark.parametrize(("hue", "inside"), [(55.0, False), (64.0, True), (146.0, True), (156.0, False)])
def test_the_hue_limits_are_sixty_and_one_hundred_fifty_degrees(hue: float, inside: bool) -> None:
    assert tool.vegetation_tint_pct(_png((hue, 0.9, 0.7))) == pytest.approx(100.0 if inside else 0.0)


@pytest.mark.req("FR-009-08")
def test_a_pale_green_below_the_saturation_limit_is_not_vegetation() -> None:
    assert tool.vegetation_tint_pct(_png((100.0, 0.2, 0.7))) == pytest.approx(0.0)
    assert tool.vegetation_tint_pct(_png((100.0, 0.3, 0.7))) == pytest.approx(100.0)


@pytest.mark.req("FR-009-08")
def test_a_texture_at_or_above_the_limit_stops_the_download_naming_it() -> None:
    with pytest.raises(SystemExit, match="ambientcg-test-moss"):
        tool._checked_tint("ambientcg-test-moss", _png((120.0, 0.8, 0.6)))
    assert tool._checked_tint("ambientcg-test-rock", _png((30.0, 0.5, 0.6))) == 0.0


@pytest.mark.req("FR-009-08")
def test_the_mossy_sets_are_out_of_the_pool_and_every_lithology_keeps_three_textures() -> None:
    pool = {f"ambientcg-{tool.slug(a)}" for a in tool.AMBIENTCG} | {f"polyhaven-{tool.slug(p)}" for p in tool.POLYHAVEN}
    for bad in REMOVED:
        assert not any(i.endswith(bad) for i in pool), bad
    for name, ids in tool.LITHOLOGIES.items():
        assert len(ids) >= 3 and set(ids) <= pool, name
    assert len(pool) >= 12
    for _, texture in tool.MATERIALS.values():
        assert texture in pool and not any(texture.endswith(bad) for bad in REMOVED)


@pytest.mark.req("FR-004-26")
def test_every_pool_texture_is_registered_with_its_digest_licence_and_a_card() -> None:
    import jsonschema
    import yaml

    registry = yaml.safe_load((ROOT / "data" / "sources.yaml").read_text(encoding="utf-8"))
    import json

    jsonschema.validate(registry, json.loads((ROOT / "contracts" / "sources.schema.json").read_text(encoding="utf-8")))
    entries = {e["id"]: e for e in registry["sources"]}
    pool = [f"ambientcg-{tool.slug(a)}" for a in tool.AMBIENTCG] + [f"polyhaven-{tool.slug(p)}" for p in tool.POLYHAVEN]
    for texture in pool:
        entry = entries[texture]
        assert entry["spdx"] == "CC0-1.0" and entry["licence_class"] == "open-no-attribution"
        assert all(re.fullmatch(r"[0-9a-f]{64}", f["sha256"]) for f in entry["files"])
        assert (ROOT / entry["card"]).is_file()
    card = (ROOT / "data" / "cards" / "sdg-cc0-textures.md").read_text(encoding="utf-8")
    for texture in pool:
        assert f"`{texture}`" in card
