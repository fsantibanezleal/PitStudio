# ruff: noqa: PT018
"""`tools/sdg_inputs.py`: the pure parts of the SDG input builder (scene specification, outline smoothing, helpers).

Oracle: the scene specification is validated with the DC-004-01 schema; the smoothed outline is checked with shapely
(area, orientation, a narrow lobe removed); the digests are hashlib values.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "src"))
_spec = importlib.util.spec_from_file_location("sdg_inputs_tool", ROOT / "tools" / "sdg_inputs.py")
assert _spec is not None and _spec.loader is not None
tool = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tool
_spec.loader.exec_module(tool)

TEXTURES = {
    "polyhaven-gravel-ground-01": {"spdx": "CC0-1.0"},
    "ambientcg-rock064": {"spdx": "CC0-1.0"},
}


def test_the_scene_spec_is_valid_and_centred_on_the_pit() -> None:
    from pitstudio_studio.scene.common import params_violations

    spec = tool.scene_spec(TEXTURES)
    assert params_violations(spec) == []
    assert spec["site"]["origin"]["easting_m"] == 402500.0 and spec["site"]["origin"]["northing_m"] == 4486500.0
    assert spec["design"]["outline_source"] == "upstream-shell"
    assert [m["id"] for m in spec["materials"]] == ["gravel-road", "bench-rock"]
    assert all(m["spdx"] == "CC0-1.0" for m in spec["materials"])


def test_a_texture_pool_licence_other_than_cc0_is_carried_into_the_spec_for_the_stage_to_refuse() -> None:
    spec = tool.scene_spec({**TEXTURES, "ambientcg-rock064": {"spdx": "CC-BY-4.0"}})
    assert spec["materials"][1]["spdx"] == "CC-BY-4.0"  # st30_assets rejects it (FR-004-26), the tool does not hide it


def test_opening_removes_a_narrow_lobe_and_keeps_the_body() -> None:
    from shapely.geometry import Polygon

    body = [(0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)]
    ring = [
        body[0],
        body[1],
        (400.0, 190.0),
        (900.0, 190.0),
        (900.0, 210.0),  # a 20 m wide, 500 m long lobe
        (400.0, 210.0),
        body[2],
        body[3],
    ]
    out = tool.smoothed_outline([list(p) for p in ring], 50.0, simplify_m=1.0)
    poly = Polygon(out)
    assert poly.is_valid and poly.exterior.is_ccw
    assert poly.bounds[2] < 450.0, "the lobe is gone"
    assert poly.area == pytest.approx(400.0 * 400.0, rel=0.02)


def test_the_outline_ring_is_open_and_without_a_repeated_vertex() -> None:
    out = tool.smoothed_outline([[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]], 0.0, simplify_m=1.0)
    assert out[0] != out[-1] and len(out) == 4


def test_digest_helpers_match_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc" * 1000)
    assert tool.sha256_file(path) == hashlib.sha256(b"abc" * 1000).hexdigest()
    assert tool.sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()
    assert tool.slug("aerial_rocks_01") == "aerial-rocks-01"


def test_the_data_root_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PITSTUDIO_DATA", raising=False)
    with pytest.raises(SystemExit):
        tool.data_root()


def test_the_lithologies_only_name_textures_of_the_downloaded_pool() -> None:
    pool = {f"ambientcg-{tool.slug(a)}" for a in tool.AMBIENTCG} | {f"polyhaven-{tool.slug(p)}" for p in tool.POLYHAVEN}
    for ids in tool.LITHOLOGIES.values():
        assert set(ids) <= pool
    for _, texture in tool.MATERIALS.values():
        assert texture in pool
