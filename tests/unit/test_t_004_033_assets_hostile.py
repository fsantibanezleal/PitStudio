# ruff: noqa: E501
"""T-004-033: hostile asset specifications.

Requirements: FR-004-27.

Oracle: malformed asset specifications with one known defect each (plan.md "FR-004-27": negative mass, NaN size,
unknown label, cyclic joints, a non-CC0 texture), written here; the expected message names the offending part, asset or
material (the spec says "naming the prim path"; prim names are identifiers, so a slug such as `dump-body` may appear
as `dump_body`).

Expected API (package `pitstudio_studio.scene.assets`, studio environment): `assets.build_assets(spec, out_dir,
textures=None)` raises `common.SceneStageError("asset-invalid")` with a message starting `"asset-invalid: "` and naming the
offending prim, before writing any file under `out_dir`, for: a non-positive or non-finite dimension or mass (asset or
part); a class label or part label outside `spec["labels"]` (closed vocabulary); a joint graph with a cycle, with more
than one root, or with a parent that is not a part of the asset; a texture whose licence is not CC0-1.0 (from a CC0
source) or our own (`source` null, CC-BY-4.0).
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import assets, common  # noqa: E402


def _part(spec: dict, pid: str) -> dict:
    return next(p for p in spec["parts"] if p["id"] == pid)


def _truck() -> dict:
    return kit.machine_spec(("haul_truck",))


def _mut_asset(key: str, value: float):
    def apply(spec: dict) -> None:
        spec["assets"][0][key] = value

    return apply


def _mut_part(pid: str, key: str, value: float):
    def apply(spec: dict) -> None:
        _part(spec, pid)[key] = value

    return apply


def _cycle(spec: dict) -> None:
    _part(spec, "chassis")["parent"] = "dump-body"  # chassis <-> dump-body: a cycle with no root
    _part(spec, "chassis").update(joint="revolute", axis="Y", lower_deg=0.0, upper_deg=10.0)


def _two_roots(spec: dict) -> None:
    dump = _part(spec, "dump-body")
    dump["parent"] = None
    for k in ("joint", "axis", "lower_deg", "upper_deg"):
        dump.pop(k, None)


def _dangling(spec: dict) -> None:
    _part(spec, "dump-body")["parent"] = "no-such-part"


def _bad_class(spec: dict) -> None:
    spec["labels"]["classes"] = [c for c in spec["labels"]["classes"] if c != "haul_truck"]


def _bad_part_label(spec: dict) -> None:
    spec["labels"]["parts"] = [p for p in spec["labels"]["parts"] if p != "dump_body"]


def _licence(spdx: str, source: str | None):
    def apply(spec: dict) -> None:
        spec["materials"] = [{"id": "bad-material", "source": source, "spdx": spdx}]

    return apply


CASES = [
    ("asset-mass-zero", _mut_asset("mass_kg", 0.0), r"haul[-_]truck[-_]220t"),
    ("asset-mass-negative", _mut_asset("mass_kg", -1.0), r"haul[-_]truck[-_]220t"),
    ("asset-mass-nan", _mut_asset("mass_kg", float("nan")), r"haul[-_]truck[-_]220t"),
    ("asset-length-inf", _mut_asset("length_m", float("inf")), r"haul[-_]truck[-_]220t"),
    ("asset-width-zero", _mut_asset("width_m", 0.0), r"haul[-_]truck[-_]220t"),
    ("asset-height-negative", _mut_asset("height_m", -6.6), r"haul[-_]truck[-_]220t"),
    ("part-mass-negative", _mut_part("dump-body", "mass_kg", -50000.0), r"dump[-_]body"),
    ("part-length-nan", _mut_part("dump-body", "length_m", float("nan")), r"dump[-_]body"),
    ("part-height-zero", _mut_part("chassis", "height_m", 0.0), r"chassis"),
    ("class-outside-vocabulary", _bad_class, r"haul[-_]truck"),
    ("part-label-outside-vocabulary", _bad_part_label, r"dump[-_]body"),
    ("joint-cycle", _cycle, r"chassis|dump[-_]body"),
    ("two-roots", _two_roots, r"chassis|dump[-_]body"),
    ("dangling-parent", _dangling, r"dump[-_]body"),
    ("licence-cc-by-sa", _licence("CC-BY-SA-4.0", "polyhaven"), r"bad[-_]material"),
    ("licence-mit", _licence("MIT", "ambientcg"), r"bad[-_]material"),
    ("licence-gpl", _licence("GPL-3.0-only", None), r"bad[-_]material"),
    ("ccby-from-a-cc0-source", _licence("CC-BY-4.0", "polyhaven"), r"bad[-_]material"),
]


@pytest.mark.req("FR-004-27")
@pytest.mark.parametrize(("mutate", "names"), [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_malformed_asset_specification_is_asset_invalid_and_writes_nothing(tmp_path: Path, mutate, names: str) -> None:
    spec = copy.deepcopy(_truck())
    mutate(spec)
    textures = {m["id"]: kit.tiny_png(tmp_path / f"{m['id']}.png") for m in spec["materials"]}
    out = tmp_path / "out"
    with pytest.raises(common.SceneStageError) as exc:
        assets.build_assets(spec, out, textures=textures)
    assert exc.value.error_class == "asset-invalid"
    assert str(exc.value).startswith("asset-invalid: ")
    assert re.search(names, str(exc.value)), str(exc.value)  # names the offending prim
    assert not out.exists() or list(out.rglob("*")) == []  # all or nothing


@pytest.mark.req("FR-004-27")
def test_the_unmodified_specification_builds(tmp_path: Path) -> None:
    spec = _truck()
    textures = {m["id"]: kit.tiny_png(tmp_path / f"{m['id']}.png") for m in spec["materials"]}
    build = assets.build_assets(spec, tmp_path / "out", textures=textures)
    assert list(build.machines) == ["haul-truck-220t"]


@pytest.mark.req("FR-004-27")
def test_a_valid_loop_closer_does_not_make_the_graph_cyclic(tmp_path: Path) -> None:
    spec = kit.machine_spec(("wheel_loader",))
    next(p for p in spec["parts"] if p["id"] == "lift-arm")["exclude_from_articulation"] = True
    textures = {m["id"]: kit.tiny_png(tmp_path / f"{m['id']}.png") for m in spec["materials"]}
    assets.build_assets(spec, tmp_path / "out", textures=textures)
