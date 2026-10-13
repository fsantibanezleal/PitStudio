"""Produce the real inputs of the perception SDG job (spec 009 `st55_sdg`) under the data root.

Steps (each is a sub-command; every one is idempotent and writes only below `PITSTUDIO_DATA`):

- `dem`      download the public USGS 3DEP 1 m DEM tile of the Bingham scene and write the copy whose GeoTIFF tags carry
             the vertical CRS (NAVD88, which the publisher states for every 1 m DEM but does not tag), with a manifest.
- `textures` download the CC0 texture pool (colour maps, Poly Haven and ambientCG), SHA-256 each, write the manifest.
- `scene`    run the five stages of spec 004 (`st10_terrain` .. `st45_validate`) through their entry points into
             `processed/scene/<scene id>/`; the pit outline is the smoothed rim contour passed as `upstream-shell`.
- `recipe`   write `processed/perception/recipe.json` (DC-009-03) from the texture pool manifest and validate it.

`dem` and `textures` need `httpx` (run them with `uv run --no-project --with httpx --with truststore`); `scene` and
`recipe` run in the studio environment (`uv run --project studio`). Never use curl.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCENE_ID = "a1-bingham"
DEM_URL = (
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/UT_Central_QL2_2018/TIFF/"
    "USGS_one_meter_x40y449_UT_Central_QL2_2018.tif"
)
DEM_FILE = "ut-central-ql2-2018-dem.tif"
DEM_VERTICAL_EVIDENCE = (
    "The National Map product text of 'USGS one meter x40y449 UT Central QL2 2018': UTM metres in NAD83, all bare "
    "earth elevation values in metres referenced to NAVD88 (TNM Access API record, ScienceBase item "
    "5eacf22382cefae35a24ce71)"
)
AMBIENTCG = ("Rock064", "Rock063", "Rock058", "Ground068")
POLYHAVEN = ("rock_boulder_cracked", "aerial_rocks_01", "aerial_rocks_02", "gravel_ground_01")
LITHOLOGIES = {
    "quartz_monzonite": ["ambientcg-rock064", "ambientcg-rock063", "polyhaven-aerial-rocks-01"],
    "limestone": ["ambientcg-rock058", "polyhaven-rock-boulder-cracked", "polyhaven-aerial-rocks-02"],
}
MATERIALS = {
    "gravel-road": ("polyhaven", "polyhaven-gravel-ground-01"),
    "bench-rock": ("ambientcg", "ambientcg-rock064"),
}
ORIGIN = {"easting_m": 402500.0, "northing_m": 4486500.0, "z0_m": 1800.0}  # the pit centre in the 2018 DEM (EPSG:26912)
AOI = [[-1500.0, -1400.0], [1400.0, -1400.0], [1400.0, 1400.0], [-1500.0, 1400.0]]
FLOOR_Z_M = -540.0
WAIVERS = (
    {
        "rule": "UsdAsciiPerformanceChecker",
        "reason": "the design layer is .usda by contract (NFR-004-05: small layers up to 10 MB, diffable); at 3.9 MB "
        "it is inside the limit and the checker only advises crate storage for large arrays",
    },
)  # the one waived rule of the reference scene, recorded in the validation report (FR-004-37)
OPENING_RADII_M = (100.0, 150.0, 200.0, 300.0, 400.0)  # tried in order until the design stage accepts the outline


def data_root() -> Path:
    value = os.environ.get("PITSTUDIO_DATA")
    if not value:
        sys.exit("PITSTUDIO_DATA is not set: it names the data root (the folder that holds raw/, interim/, processed/)")
    return Path(value)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def slug(text: str) -> str:
    return text.lower().replace("_", "-")


def _client() -> Any:
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:  # the plain certificate store is used
        pass
    import httpx

    return httpx.Client(timeout=180, follow_redirects=True)


# ----------------------------------------------------------------------------------------------------------------
# dem
# ----------------------------------------------------------------------------------------------------------------
def cmd_dem(data: Path) -> None:
    raw = data / "raw" / "usgs-3dep-bingham"
    raw.mkdir(parents=True, exist_ok=True)
    target = raw / DEM_FILE
    if not target.is_file():
        digest = hashlib.sha256()
        with _client().stream("GET", DEM_URL) as response:
            response.raise_for_status()
            with (target.with_suffix(".part")).open("wb") as handle:
                for block in response.iter_bytes(1 << 20):
                    handle.write(block)
                    digest.update(block)
        target.with_suffix(".part").replace(target)
    record = {
        "id": "usgs-3dep-bingham",
        "url": DEM_URL,
        "file": DEM_FILE,
        "sha256": sha256_file(target),
        "bytes": target.stat().st_size,
        "spdx": "LicenseRef-USGov-PD",
        "project": "UT Central QL2 2018",
        "epoch": 2018,
    }
    (raw / "manifest.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    import shutil

    import pyproj
    import rasterio
    from rasterio.crs import CRS

    interim = data / "interim" / "usgs-3dep-bingham"
    interim.mkdir(parents=True, exist_ok=True)
    derived = interim / "ut-central-ql2-2018-dem-navd88.tif"
    shutil.copyfile(target, derived)
    with rasterio.open(derived, "r+", IGNORE_COG_LAYOUT_BREAK="YES") as dataset:
        dataset.crs = CRS.from_wkt(pyproj.CRS.from_user_input("EPSG:26912+5703").to_wkt())
    (interim / "manifest.json").write_text(
        json.dumps(
            {
                "derived_from": f"raw/usgs-3dep-bingham/{DEM_FILE}",
                "derived_from_sha256": record["sha256"],
                "file": derived.name,
                "sha256": sha256_file(derived),
                "change": "GeoTIFF CRS tag only: EPSG:26912 completed with the vertical CRS EPSG:5703 (NAVD88 height, "
                "metres); pixel data untouched",
                "evidence": DEM_VERTICAL_EVIDENCE,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("dem", record["sha256"][:12], "->", derived.name)


# ----------------------------------------------------------------------------------------------------------------
# textures
# ----------------------------------------------------------------------------------------------------------------
def cmd_textures(data: Path) -> None:
    import datetime
    import hashlib as hl

    root = data / "raw" / "textures"
    client = _client()
    today = datetime.date.today().isoformat()
    licence: dict[str, Any] = {}
    for key, url in (
        ("ambientcg", "https://docs.ambientcg.com/license/"),
        ("polyhaven", "https://polyhaven.com/license"),
    ):
        page = client.get(url)
        page.raise_for_status()
        (root / key).mkdir(parents=True, exist_ok=True)
        (root / key / "LICENSE-page.html").write_bytes(page.content)
        licence[key] = {
            "url": url,
            "page_sha256": sha256_bytes(page.content),
            "mentions_cc0": "cc0" in page.text.lower(),
        }
        if not licence[key]["mentions_cc0"]:
            sys.exit(f"{url} does not mention CC0: refusing to download from {key}")
    entries: list[dict[str, Any]] = []
    for asset in AMBIENTCG:
        info = client.get(
            "https://ambientcg.com/api/v2/full_json", params={"id": asset, "include": "downloadData,tagData"}
        ).json()["foundAssets"][0]
        downloads = info["downloadFolders"]["default"]["downloadFiletypeCategories"]["zip"]["downloads"]
        chosen = next(d for d in downloads if d["attribute"] == "1K-JPG")
        archive = client.get(chosen["downloadLink"])
        archive.raise_for_status()
        members = zipfile.ZipFile(io.BytesIO(archive.content))
        name = next(n for n in members.namelist() if n.endswith("_Color.jpg"))
        data_bytes = members.read(name)
        folder = root / "ambientcg" / asset
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{asset}_1K-JPG.zip").write_bytes(archive.content)
        (folder / name).write_bytes(data_bytes)
        entries.append(
            {
                "id": f"ambientcg-{slug(asset)}",
                "source_id": "ambientcg",
                "asset": asset,
                "url": chosen["downloadLink"],
                "file": f"ambientcg/{asset}/{name}",
                "sha256": sha256_bytes(data_bytes),
                "bytes": len(data_bytes),
                "archive": f"ambientcg/{asset}/{asset}_1K-JPG.zip",
                "archive_sha256": sha256_bytes(archive.content),
                "map": "colour",
                "resolution": "1K",
                "spdx": "CC0-1.0",
                "asset_page": f"https://ambientcg.com/view?id={asset}",
                "downloaded": today,
            }
        )
    for asset in POLYHAVEN:
        info = client.get(f"https://api.polyhaven.com/info/{asset}").json()
        published = client.get(f"https://api.polyhaven.com/files/{asset}").json()["Diffuse"]["1k"]["jpg"]
        image = client.get(published["url"])
        image.raise_for_status()
        if hl.md5(image.content).hexdigest() != published["md5"]:
            sys.exit(f"{asset}: the download does not match the md5 the publisher lists")
        folder = root / "polyhaven" / asset
        folder.mkdir(parents=True, exist_ok=True)
        filename = published["url"].rsplit("/", 1)[1]
        (folder / filename).write_bytes(image.content)
        entries.append(
            {
                "id": f"polyhaven-{slug(asset)}",
                "source_id": "polyhaven",
                "asset": asset,
                "url": published["url"],
                "file": f"polyhaven/{asset}/{filename}",
                "sha256": sha256_bytes(image.content),
                "bytes": len(image.content),
                "md5_published": published["md5"],
                "map": "colour",
                "resolution": "1K",
                "spdx": "CC0-1.0",
                "asset_page": f"https://polyhaven.com/a/{asset}",
                "downloaded": today,
                "authors": info.get("authors"),
            }
        )
    manifest = {
        "schema_version": "1.0",
        "kind": "texture-pool",
        "licence": "CC0-1.0",
        "licence_evidence": licence,
        "note": "Colour maps only, 1K JPEG; generic CC0 surfaces, not site-true. "
        "Courtesy credit: Textures: Poly Haven and ambientCG, CC0.",
        "textures": entries,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("textures", len(entries))


# ----------------------------------------------------------------------------------------------------------------
# scene
# ----------------------------------------------------------------------------------------------------------------
def scene_spec(textures: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The scene specification (DC-004-01): the contract example of case A1 centred on the Bingham pit."""
    spec = json.loads(
        (ROOT / "specs" / "004-scene-pipeline" / "contracts" / "examples" / "scene-spec.valid.json").read_text("utf-8")
    )
    spec["site"]["origin"].update(ORIGIN)
    spec["terrain"]["aoi_xy_m"] = [list(p) for p in AOI]
    spec["design"]["floor_z_m"] = FLOOR_Z_M
    spec["design"]["outline_source"] = "upstream-shell"
    spec["materials"] = [
        {"id": name, "source": source, "spdx": textures[texture]["spdx"]}
        for name, (source, texture) in MATERIALS.items()
    ]
    spec["validation"] = {"waivers": [dict(w) for w in WAIVERS]}
    return spec


def smoothed_outline(ring: list[list[float]], radius_m: float, simplify_m: float = 8.0) -> list[list[float]]:
    """The rim ring opened by `radius_m` (narrow lobes removed) and simplified, counter-clockwise, as vertices."""
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient

    polygon = Polygon(ring)
    opened = polygon.buffer(-radius_m, join_style=1).buffer(radius_m, join_style=1) if radius_m > 0 else polygon
    if opened.geom_type != "Polygon":
        opened = max(opened.geoms, key=lambda p: p.area)
    shell = orient(opened.simplify(simplify_m), 1.0)
    return [[float(x), float(y)] for x, y in list(shell.exterior.coords)[:-1]]


def cmd_scene(data: Path, scratch: Path) -> None:
    os.environ["PITSTUDIO_DATA"] = str(data)
    sys.path.insert(0, str(ROOT / "studio" / "src"))
    sys.path.insert(0, str(ROOT / "src"))
    import numpy as np
    import zarr
    from pitstudio_studio.scene import assets, compose, design, terrain, validate
    from pitstudio_studio.scene.design import outline as outline_mod

    base = data / "processed" / "scene" / SCENE_ID
    textures = {t["id"]: t for t in json.loads((data / "raw/textures/manifest.json").read_text("utf-8"))["textures"]}
    spec = scene_spec(textures)
    base.mkdir(parents=True, exist_ok=True)
    (base / "scene-spec.json").write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def job(stage: str, entry: str, inputs: list[tuple[str, Path]]) -> dict[str, Any]:
        out, work = base / stage, scratch / stage
        out.mkdir(parents=True, exist_ok=True)
        work.mkdir(parents=True, exist_ok=True)
        return {
            "schema_version": "1.0",
            "run_id": "sdg-inputs",
            "stage": stage,
            "entry": f"pitstudio_studio.scene.{entry}",
            "params": spec,
            "seed": spec["seed"],
            "shard": None,
            "inputs": [{"name": n, "path": p.as_posix(), "sha256": sha256_file(p)} for n, p in inputs],
            "output_dir": out.as_posix(),
            "scratch_dir": work.as_posix(),
            "resume": False,
            "rerun": False,
            "profiling": False,
            "profile": {"id": "laptop", "cpu_slots": 2},
            "vram_fraction": None,
            "nvtx_range": stage,
        }

    def run(module: Any, entry: str, stage: str, inputs: list[tuple[str, Path]], fatal: bool = True) -> Path | None:
        started = time.perf_counter()
        outcome = module.run(job(stage, entry, inputs))
        print(
            stage,
            outcome.result["status"],
            outcome.result.get("message"),
            f"{time.perf_counter() - started:.0f}s",
            flush=True,
        )
        if outcome.result["status"] != "succeeded":
            if fatal:
                sys.exit(json.dumps(outcome.result, indent=1))
            return None
        return base / stage / "result.json"

    dem = data / "interim" / "usgs-3dep-bingham" / "ut-central-ql2-2018-dem-navd88.tif"
    r10 = run(terrain, "terrain", "st10_terrain", [("usgs-3dep-bingham", dem)])
    group = zarr.open_group(str(base / "st10_terrain" / "terrain" / "grid.zarr"), mode="r")
    attrs = group.attrs
    ring = outline_mod.rim_contour(
        np.asarray(group["elevation"][:]),
        x_min_m=float(attrs["x_min_m"]),
        y_max_m=float(attrs["y_max_m"]),
        cell_size_m=float(attrs["cell_size_m"]),
        rim_z_m=float(spec["design"].get("rim_z_m", 0.0)),
    )
    r20 = None
    for radius in OPENING_RADII_M:
        shell = smoothed_outline(ring, radius)
        (base / "inputs").mkdir(exist_ok=True)
        outline_file = base / "inputs" / "pit-outline.geojson"
        outline_file.write_text(json.dumps({"type": "Polygon", "coordinates": [[*shell, shell[0]]]}, indent=1), "utf-8")
        print(f"outline: opening radius {radius:.0f} m, {len(shell)} vertices", flush=True)
        r20 = run(
            design,
            "design",
            "st20_pit_design",
            [
                ("terrain-grid", base / "st10_terrain" / "terrain" / "grid.zarr" / "zarr.json"),
                ("outline", outline_file),
            ],
            fatal=False,
        )
        if r20 is not None:
            params = {
                "opening_radius_m": radius,
                "simplify_m": 8.0,
                "rim_z_m": float(spec["design"].get("rim_z_m", 0.0)),
            }
            (base / "inputs" / "outline-params.json").write_text(json.dumps(params), encoding="utf-8")
            break
    if r20 is None:
        sys.exit("st20_pit_design rejected every outline; see the messages above")
    material_files = [
        (name, data / "raw" / "textures" / textures[texture]["file"]) for name, (_, texture) in MATERIALS.items()
    ]
    r30 = run(assets, "assets", "st30_assets", material_files)
    upstream = [("terrain", r10), ("design", r20), ("assets", r30)]
    run(compose, "compose", "st40_compose", upstream)
    run(validate, "validate", "st45_validate", upstream)


# ----------------------------------------------------------------------------------------------------------------
# recipe
# ----------------------------------------------------------------------------------------------------------------
def cmd_recipe(data: Path) -> None:
    sys.path.insert(0, str(ROOT / "studio" / "src"))
    sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location(
        "sdg_default_recipe", ROOT / "pipeline" / "src" / "pitstudio_pipeline" / "perception" / "recipe.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    from pitstudio_studio.sdg.config import validate_config

    manifest = json.loads((data / "raw" / "textures" / "manifest.json").read_text("utf-8"))
    pool = [{k: t[k] for k in ("id", "source_id", "sha256", "spdx")} for t in manifest["textures"]]
    known = {t["id"] for t in pool}
    for litho, ids in LITHOLOGIES.items():
        missing = sorted(set(ids) - known)
        if missing:
            sys.exit(f"lithology {litho}: textures {missing} are not in the pool manifest")
    recipe = module.default_recipe(texture_pool=pool, lithologies=LITHOLOGIES)
    validate_config(recipe)
    out = data / "processed" / "perception"
    out.mkdir(parents=True, exist_ok=True)
    (out / "recipe.json").write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
    print("recipe valid:", len(pool), "textures,", sum(a["image_count"] for a in recipe["arms"]), "images in 3 arms")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=("dem", "textures", "scene", "recipe"))
    parser.add_argument("--scratch", type=Path, help="scratch folder of the scene stages (default: <data>/../_scratch)")
    args = parser.parse_args(argv)
    data = data_root()
    if args.step == "dem":
        cmd_dem(data)
    elif args.step == "textures":
        cmd_textures(data)
    elif args.step == "scene":
        cmd_scene(data, args.scratch or data.parent / "_scratch" / "sdg-inputs")
    else:
        cmd_recipe(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
