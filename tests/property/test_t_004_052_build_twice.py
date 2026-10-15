# ruff: noqa: E501, PT018
"""T-004-052: build twice, stage hash, `nondeterministic` failure.

Requirements: FR-004-36, FR-004-39, P-004-11.

Oracle: SHA-256 of the files recomputed with hashlib (exact equality across two builds); the flattened text export of a
`.usdc` layer from OpenUSD (reference implementation); a fake writer that injects a timestamp into one layer of the second
build (plan.md "FR-004-39"); the stage hash is compared across runs (identical inputs give the identical hash, any layer
change gives a different one). The exact byte serialisation of "the sorted list of (layer role, layer SHA-256)" is not fixed by
the spec, so the test accepts the usual encodings of the sorted pair list (see `_stage_hash_candidates`).

Expected API (package `pitstudio_studio.scene.validate`, studio environment): `validate.validate_scene(spec, build_scene,
work_dir, *, runners=None)` as in test_t_004_050. `build_scene(out_dir)` is called twice, with two distinct fresh (empty)
folders under `work_dir`. `report["determinism"]` = `{class: "bitwise", layers: [...], identical, stage_hash}` with one
entry per manifest layer: `{role, path, format, method, first_sha256, second_sha256, equal[, first_difference]}`; for a
`.usda` layer `method` is `"bytes"` and the digests are the SHA-256 of the file; for a `.usdc` layer `method` is
`"flattened-text"` and the digest is that of the layer's text export; `stage_hash` is the SHA-256 of the sorted
(role, SHA-256) list of the first build. When any layer differs, `outcome.error_class == "nondeterministic"`,
`outcome.message` = `"nondeterministic: <differing layer paths> ... first differing line ..."`, the report has
`identical: false`, `passed: false` and `first_difference = {line, first, second}` on each differing layer.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import compose, validate  # noqa: E402

NO_RESULTS = {"usd-validation-nvidia": lambda root, selection: [], "simready-validate": lambda root, selection: []}


def _spec(seed: int = 20261007) -> dict:
    spec = kit.scene_spec()
    spec["seed"] = seed
    spec["variants"] = {
        "pushback": ["pb0"],
        "scenario": ["baseline"],
        "time_of_day": ["noon"],
        "weather": ["clear"],
        "lod": ["lod0", "lod1", "lod2"],
    }
    return spec


def _builder(spec: dict, tmp: Path, mutate_second=None, seen=None):
    counter = itertools.count()

    def build(out_dir: Path):
        n = next(counter)
        if seen is not None:
            seen.append(
                (Path(out_dir), sorted(p.name for p in Path(out_dir).glob("*")) if Path(out_dir).exists() else [])
            )
        result = compose.compose_scene(spec, kit.fixture_upstream(tmp / f"up{n}"), out_dir)
        if n == 1 and mutate_second:
            mutate_second(out_dir)
        return result

    return build


def _stage_hash_candidates(layers: list[dict], key: str = "first_sha256") -> set[str]:
    pairs = sorted((entry["role"], entry[key]) for entry in layers)
    texts = {
        json.dumps([[r, h] for r, h in pairs]),
        json.dumps([[r, h] for r, h in pairs], separators=(",", ":")),
        json.dumps([{"role": r, "sha256": h} for r, h in pairs], separators=(",", ":")),
        json.dumps([{"role": r, "sha256": h} for r, h in pairs], separators=(",", ":"), sort_keys=True),
        "\n".join(f"{r} {h}" for r, h in pairs),
        "\n".join(f"{r} {h}" for r, h in pairs) + "\n",
        "\n".join(f"{r}:{h}" for r, h in pairs),
        "".join(f"{r}{h}" for r, h in pairs),
    }
    return {hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts}


@pytest.mark.req("FR-004-36")
def test_two_builds_in_two_fresh_folders_give_identical_layer_hashes(tmp_path: Path) -> None:
    spec, seen = _spec(), []
    out = validate.validate_scene(spec, _builder(spec, tmp_path, seen=seen), tmp_path / "work", runners=NO_RESULTS)
    (first, listing1), (second, listing2) = seen
    assert first != second and listing1 == [] and listing2 == []  # two distinct, fresh (empty) folders
    assert tmp_path / "work" in first.parents and tmp_path / "work" in second.parents
    det = out.report["determinism"]
    assert det["class"] == "bitwise" and det["identical"] is True and out.error_class is None
    assert kit.schema_errors("scene-validation-report.schema.json", out.report) == []
    manifest_paths = sorted(e["path"] for e in out.manifest["layers"])
    assert sorted(entry["path"] for entry in det["layers"]) == manifest_paths  # every layer is compared
    scene = Path(out.scene_dir)
    for entry in det["layers"]:
        assert (
            entry["equal"] is True
            and entry["first_sha256"] == entry["second_sha256"]
            and "first_difference" not in entry
        )
        if entry["format"] == "usda":
            assert entry["method"] == "bytes"
            assert entry["first_sha256"] == kit.sha256_file(scene / entry["path"])
        else:
            from pxr import Sdf, Usd

            assert entry["method"] == "flattened-text"
            layer_path = str(scene / entry["path"])
            texts = {
                Sdf.Layer.FindOrOpen(layer_path).ExportToString(),
                Usd.Stage.Open(layer_path).ExportToString(addSourceFileComment=False),
                Usd.Stage.Open(layer_path).Flatten().ExportToString(),
            }
            assert entry["first_sha256"] in {hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts}
    assert {e["role"] for e in det["layers"]} >= {
        "root",
        "anim",
        "sensors",
        "weather",
        "lights",
        "fleet",
        "design",
        "terrain",
    }


@pytest.mark.req("FR-004-36")
def test_stage_hash_is_a_hash_of_the_sorted_role_digest_pairs(tmp_path: Path) -> None:
    spec = _spec()
    a = validate.validate_scene(spec, _builder(spec, tmp_path / "a"), tmp_path / "wa", runners=NO_RESULTS).report
    b = validate.validate_scene(spec, _builder(spec, tmp_path / "b"), tmp_path / "wb", runners=NO_RESULTS).report
    h = a["determinism"]["stage_hash"]
    assert h == b["determinism"]["stage_hash"] and len(h) == 64
    assert h in _stage_hash_candidates(a["determinism"]["layers"])
    other = _spec(seed=7)  # another seed changes the params hash in the root layer, hence its digest and the stage hash
    c = validate.validate_scene(other, _builder(other, tmp_path / "c"), tmp_path / "wc", runners=NO_RESULTS).report
    assert c["determinism"]["stage_hash"] != h


def _inject_timestamp(scene: Path) -> None:
    path = scene / "layers" / "anim.usda"
    path.write_text(
        path.read_text(encoding="utf-8").rstrip("\n") + "\n# built at 2026-10-11T12:00:00Z\n", encoding="utf-8"
    )


def _move_a_terrain_point(scene: Path) -> None:
    from pxr import Usd

    stage = Usd.Stage.Open(str(scene / "layers" / "terrain.usdc"))
    vset = stage.GetPrimAtPath("/World/Terrain").GetVariantSet("lod")
    vset.SetVariantSelection("lod0")
    with vset.GetVariantEditContext():
        stage.GetPrimAtPath("/World/Terrain/Lod0/Tile_0_0_0_0").GetAttribute("points").Set(
            [(0.0, 0.0, 0.5), (100.0, 0.0, 0.0), (100.0, 100.0, 0.0), (0.0, 100.0, 0.0)]
        )
    stage.GetRootLayer().Save()


@pytest.mark.req("FR-004-39")
@pytest.mark.parametrize(
    ("mutate", "path", "fmt"),
    [(_inject_timestamp, "layers/anim.usda", "usda"), (_move_a_terrain_point, "layers/terrain.usdc", "usdc")],
)
def test_a_difference_between_the_builds_is_nondeterministic_and_names_the_layer_and_line(
    tmp_path: Path, mutate, path: str, fmt: str
) -> None:
    spec = _spec()
    out = validate.validate_scene(
        spec, _builder(spec, tmp_path, mutate_second=mutate), tmp_path / "work", runners=NO_RESULTS
    )
    assert out.error_class == "nondeterministic" and out.message.startswith("nondeterministic: ")
    assert path in out.message and "line" in out.message.lower()
    det = out.report["determinism"]
    assert det["identical"] is False and out.report["passed"] is False and out.passed is False
    bad = [e for e in det["layers"] if not e["equal"]]
    assert [e["path"] for e in bad] == [path]  # only the injected layer differs
    diff = bad[0]["first_difference"]
    assert diff["line"] >= 1 and diff["first"] != diff["second"]
    if fmt == "usda":
        assert "# built at" in diff["second"]
    assert bad[0]["first_sha256"] != bad[0]["second_sha256"]
    assert kit.schema_errors("scene-validation-report.schema.json", out.report) == []


@pytest.mark.req("P-004-11")
@settings(
    max_examples=8, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
)
@given(seed=st.integers(0, 2**32 - 1), other=st.integers(0, 2**32 - 1))
def test_builds_of_any_seed_are_bitwise_identical_and_seed_dependent(
    tmp_path_factory: pytest.TempPathFactory, seed: int, other: int
) -> None:
    """P-004-11: for any seed two builds give identical layer and stage hashes (and another seed another stage hash)."""
    tmp = tmp_path_factory.mktemp("p11")
    spec = _spec(seed)
    out = validate.validate_scene(spec, _builder(spec, tmp / "a"), tmp / "work_a", runners=NO_RESULTS)
    det = out.report["determinism"]
    assert det["identical"] is True and all(e["first_sha256"] == e["second_sha256"] for e in det["layers"])
    again = validate.validate_scene(spec, _builder(spec, tmp / "b"), tmp / "work_b", runners=NO_RESULTS)
    assert again.report["determinism"]["stage_hash"] == det["stage_hash"]
    if other != seed:
        moved = _spec(other)
        third = validate.validate_scene(moved, _builder(moved, tmp / "c"), tmp / "work_c", runners=NO_RESULTS)
        assert third.report["determinism"]["stage_hash"] != det["stage_hash"]
