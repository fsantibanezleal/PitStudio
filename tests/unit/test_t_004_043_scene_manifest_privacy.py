# ruff: noqa: PT018
"""T-004-043: recipe declarations, output digests in the stage result, privacy scan; stage-level params validation.

Requirements: FR-004-41, FR-004-40 (stage behaviour: `params-invalid` before any file is opened).

Oracle: the recipe stages are read with PyYAML and compared with the values written in the spec (`determinism: bitwise`,
`resources.gpu: none`); output digests recomputed with hashlib; a scan of every output file and every message for the
test machine's home path, user name and host name read at test time (plan.md "FR-004-41"); malformed parameter documents
with three known defects, whose JSON pointers are written here.

Expected API (studio environment):
- A recipe under `studio/recipes/` (any `*.yaml`, any depth) declares the five stages `st10_terrain`, `st20_pit_design`,
  `st30_assets`, `st40_compose` and `st45_validate` with `determinism: bitwise` (or `{class: bitwise}`),
  `resources: {gpu: none}` and `entry: pitstudio_studio.scene.<terrain|design|assets|compose|validate>`.
- `pitstudio_studio.scene.<package>.run(job) -> StageRun` for the five packages (`terrain`, `design`, `assets`,
  `compose`, `validate`): `job` is a DC-002-02 job spec (`kit.make_job`); `StageRun.result` is a DC-002-02 stage result
  dict (also written to `<output_dir>/result.json`), `StageRun.digests` maps every output path (relative to
  `output_dir`, as listed in `result["outputs"]`) to its SHA-256. A failure has `status: "failed"`,
  `error_class: "unknown"` and `message` = `"<class>: <detail>"`. Before any file is opened, the job's `params` are
  validated against DC-004-01; a violation gives `params-invalid` with one line per violation holding its JSON pointer
  and the reason.
- No output file, result or message holds a host name, user name or absolute path.
"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import terrain  # noqa: E402

PACKAGES = {
    "st10_terrain": "terrain",
    "st20_pit_design": "design",
    "st30_assets": "assets",
    "st40_compose": "compose",
    "st45_validate": "validate",
}
SRC = "usgs-3dep-bingham"


def _recipe_stages() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for path in sorted((ROOT / "studio" / "recipes").rglob("*.yaml")) if (ROOT / "studio" / "recipes").is_dir() else []:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for stage in doc.get("stages", []) if isinstance(doc, dict) else []:
            if isinstance(stage, dict) and stage.get("id") in PACKAGES:
                found[stage["id"]] = stage
    return found


@pytest.mark.req("FR-004-41")
def test_all_five_scene_stages_are_declared_bitwise_and_cpu_only() -> None:
    stages = _recipe_stages()
    assert sorted(stages) == sorted(PACKAGES), f"stages declared in studio/recipes: {sorted(stages)}"
    for key, stage in stages.items():
        assert stage["determinism"] in ("bitwise", {"class": "bitwise"}), key
        assert stage["resources"]["gpu"] == "none", key
        assert stage["entry"] == f"pitstudio_studio.scene.{PACKAGES[key]}", key


def _terrain_job(tmp: Path, monkeypatch: pytest.MonkeyPatch, wkt: str | None = None) -> dict:
    store, data = tmp / "store", tmp / "data"
    store.mkdir()
    data.mkdir()
    monkeypatch.setenv("PITSTUDIO_STORE", str(store))
    monkeypatch.setenv("PITSTUDIO_DATA", str(data))
    z = kit.Z0 + np.arange(144, dtype=np.float64).reshape(12, 12)
    dem = kit.write_dem(
        data / "dem.tif", z, x_min=kit.E0, y_max=kit.N0 + 12, cell=1.0, wkt=wkt or kit.crs_wkt("utm12-m")
    )
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 12.0, 12.0)
    return kit.make_job(store, "st10_terrain", spec, [(SRC, dem)])


def _files(out: Path) -> list[Path]:
    return sorted(p for p in out.rglob("*") if p.is_file())


@pytest.mark.req("FR-004-41")
def test_terrain_stage_lists_each_output_with_its_sha256(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    job = _terrain_job(tmp_path, monkeypatch)
    run = terrain.run(job)
    out = Path(job["output_dir"])
    assert run.result["status"] == "succeeded" and run.result["error_class"] is None
    assert kit.schema_errors("job.schema.json", run.result, ROOT / "specs" / "002-runner" / "contracts") == []
    listed = [o["path"] for o in run.result["outputs"]]
    assert listed and sorted(run.digests) == sorted(listed)
    import hashlib

    for rel in listed:
        assert (out / rel).is_file()
        assert run.digests[rel] == hashlib.sha256((out / rel).read_bytes()).hexdigest()
    result_file = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert result_file == run.result


@pytest.mark.req("FR-004-41")
def test_no_output_or_message_holds_a_host_user_or_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _terrain_job(tmp_path, monkeypatch)
    run = terrain.run(job)
    out = Path(job["output_dir"])
    needles = [n.encode("utf-8") for n in kit.machine_identifiers()]
    needles += [str(tmp_path).encode(), tmp_path.as_posix().encode(), out.as_posix().encode()]
    for path in [*_files(out)]:
        data = path.read_bytes()
        for needle in needles:
            assert needle not in data, (path.name, needle)
        if path.suffix in {".json", ".usda", ".geojson", ".txt"}:
            assert not kit.has_absolute_path_text(data.decode("utf-8", "replace")), path.name
    message = json.dumps(run.result)
    assert not kit.has_absolute_path_text(message) and not any(n.decode() in message for n in needles)


@pytest.mark.req("FR-004-41")
def test_a_failing_stage_message_names_no_absolute_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    job = _terrain_job(tmp_path, monkeypatch)
    bad = Path(job["inputs"][0]["path"])
    bad.write_bytes(b"not a tiff " * 50)
    job["inputs"][0]["sha256"] = kit.sha256_file(bad)
    run = terrain.run(job)
    assert run.result["status"] == "failed" and run.result["message"].startswith("input-corrupt: ")
    text = json.dumps(run.result)
    assert not kit.has_absolute_path_text(text)
    for needle in [*kit.machine_identifiers(), str(tmp_path), tmp_path.as_posix()]:
        assert needle not in text


@pytest.mark.req("FR-004-41")
def test_assets_stage_runs_from_params_alone_and_lists_digests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib

    assets_stage = importlib.import_module("pitstudio_studio.scene.assets")
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("PITSTUDIO_STORE", str(store))
    spec = kit.machine_spec(("haul_truck", "shovel"))
    spec["people_count"] = 2
    job = kit.make_job(store, "st30_assets", spec, [])
    run = assets_stage.run(job)
    out = Path(job["output_dir"])
    assert run.result["status"] == "succeeded"
    assert any(o["path"].endswith("fleet.usda") for o in run.result["outputs"])
    for rel, digest in run.digests.items():
        assert hashlib.sha256((out / rel).read_bytes()).hexdigest() == digest
    for path in _files(out):
        for needle in kit.machine_identifiers():
            assert needle.encode() not in path.read_bytes(), path.name


# ------------------------------------------------------------------------------------------------------- FR-004-40
def _bad_params() -> tuple[dict, list[str]]:
    spec = copy.deepcopy(kit.scene_spec())
    spec["terrain"]["cell_size_m"] = float("nan")  # NaN in a number
    spec["variants"]["weather"] = ["clear", "hail"]  # unknown enumeration value
    spec["surprise"] = 1  # extra field
    spec["site"]["name"] = "x" * 300  # string longer than 256 characters
    del spec["seed"]  # missing field
    return spec, ["/terrain/cell_size_m", "/variants/weather/1", "surprise", "/site/name", "seed"]


@pytest.mark.req("FR-004-40")
@pytest.mark.parametrize("package", sorted(PACKAGES.values()))
def test_every_stage_rejects_invalid_params_listing_every_violation_before_opening_any_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, package: str
) -> None:
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("PITSTUDIO_STORE", str(store))
    monkeypatch.setenv("PITSTUDIO_DATA", str(tmp_path / "data"))
    stage = next(k for k, v in PACKAGES.items() if v == package)
    params, pointers = _bad_params()
    job = kit.make_job(store, stage, params, [])
    job["inputs"] = [{"name": SRC, "path": (tmp_path / "data" / "never-opened.tif").as_posix(), "sha256": "0" * 64}]
    module = importlib.import_module(f"pitstudio_studio.scene.{package}")
    run = module.run(job)
    assert run.result["status"] == "failed" and run.result["error_class"] == "unknown"
    message = run.result["message"]
    assert message.startswith("params-invalid: ")
    for pointer in pointers:
        assert pointer in message, (pointer, message)
    assert list(Path(job["output_dir"]).rglob("*.json")) in ([], [Path(job["output_dir"]) / "result.json"])
