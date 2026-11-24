"""E2 run: the real 2018 to 2023 excavated volume by DEM differencing and the chart-series files of the case page
(FR-017-30, FR-017-31, FR-017-33, FR-017-34, FR-017-51).

Usage: python -m pitstudio_studio.survey.real_run RECIPE.yaml OUT_DIR --data-root DIR

Writes `survey-volume.json` (DC-017-04, one volume per area of interest), `charts/e2-*.json` (DC-020-05 chart-series,
case E2) and `e2-run.json`. A vertical-datum mismatch without a declared transform gives "not run" with its reason in
every file and no number (FR-017-32).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio.survey.difference import InvalidSurfaceError, Surface, _inside_grid
from pitstudio.survey.real_volume import LABEL, clip_polygon, real_volume
from pitstudio_studio.survey.dem_prepare import EM_DASH, DemInfo, prepare_pair

MAX_CHART_BYTES = 524_288
MAP_CELLS = 200
SERVES = ["FR-018-16", "FR-017-34"]
METHOD = "DEM differencing with exactly rounded sums (pitstudio.survey)"


def _en_es(en: str, es: str) -> dict:
    return {"en": en, "es": es}


def _surface(dem: DemInfo) -> Surface:
    """A north-up DEM as a `Surface`: rows ascend in y, so the array is flipped and the origin is the lower left."""
    a, b, c, d, e, f = dem.transform
    if b != 0 or d != 0 or a != -e:
        raise ValueError("the DEM grid is rotated or has non-square cells")
    ny = dem.z.shape[0]
    return Surface(z=dem.z[::-1], origin_xy=(c, f + e * ny), cell_size_m=float(a), nodata=None)


def _crop(s: Surface, x0: float, y0: float, x1: float, y1: float) -> Surface:
    """The cells of `s` that cover the box, one cell of margin kept; cell alignment is preserved."""
    ny, nx = s.z.shape
    c = s.cell_size_m
    i0 = max(0, math.floor((x0 - s.origin_xy[0]) / c) - 1)
    i1 = min(nx, math.ceil((x1 - s.origin_xy[0]) / c) + 1)
    j0 = max(0, math.floor((y0 - s.origin_xy[1]) / c) - 1)
    j1 = min(ny, math.ceil((y1 - s.origin_xy[1]) / c) + 1)
    return Surface(
        z=s.z[j0:j1, i0:i1],
        origin_xy=(s.origin_xy[0] + i0 * c, s.origin_xy[1] + j0 * c),
        cell_size_m=c,
        nodata=s.nodata,
    )


def _footprint(area: Mapping[str, Any], data_root: Path | None) -> tuple[np.ndarray, str | None]:
    """The footprint of an area in CRS coordinates and its digest: inline vertices, or a GeoJSON polygon in local
    scene metres plus the scene origin."""
    if "footprint" in area:
        return np.asarray(area["footprint"], dtype=np.float64).reshape(-1, 2), None
    if "footprint_file" in area:
        path = (data_root or Path()) / area["footprint_file"]
        raw = path.read_bytes()
        ring = np.asarray(json.loads(raw)["coordinates"][0], dtype=np.float64)
        ox, oy = area["origin_m"]
        return ring + np.array([ox, oy]), hashlib.sha256(raw).hexdigest()
    return np.empty((0, 2)), None


def _surface_meta(rec: dict, key: str, epoch: str, path: str) -> dict:
    """Surface record of the `before` (record key 2018) or `after` (record key 2023) DEM of the prepared pair."""
    meta = {
        "path": path,
        "sha256": rec[f"sha256_{key}"],
        "epoch": epoch,
        "project": rec[f"project_{key}"],
        "crs": rec["source_crs_2018"] if key == "2018" else rec["crs"],
        "vertical_datum": rec[f"vertical_datum_{key}"],
        "rmse_z_m": rec[f"rmse_z_{key}_m"],
    }
    missing = [k for k in ("project", "vertical_datum", "rmse_z_m") if meta[k] is None]
    if missing:
        raise ValueError(f"the {epoch} DEM lacks {', '.join(missing)} in its tags and in the recipe dem_metadata")
    return meta


def _transform_meta(declared: dict | None) -> dict:
    if declared is None:
        return {"kind": "none"}
    if declared["kind"] == "constant":
        return {"kind": "constant", "offset_m": float(declared["offset_m"]), "source": declared["source"]}
    raw = Path(declared["path"]).read_bytes()
    return {
        "kind": "grid",
        "grid": {"path": f"data/processed/{Path(declared['path']).name}", "sha256": hashlib.sha256(raw).hexdigest()},
        "source": declared["source"],
    }


def _map_raster(before: Surface, after: Surface, polygon: np.ndarray) -> dict:
    """Block-mean elevation change (after minus before) of the cells inside the polygon, at most 200 x 200 blocks."""
    ny, nx = before.z.shape
    c = before.cell_size_m
    x0, y0 = before.origin_xy
    inside = _inside_grid(polygon, x0, y0, c, nx, ny)
    with np.errstate(invalid="ignore"):
        diff = np.where(inside, after.z.astype(np.float64) - before.z.astype(np.float64), np.nan)
    rows, cols = np.nonzero(np.isfinite(diff))
    r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    diff = diff[r0:r1, c0:c1]
    k = max(1, math.ceil(max(diff.shape) / MAP_CELLS))
    ph, pw = -diff.shape[0] % k, -diff.shape[1] % k
    padded = np.pad(diff, ((0, ph), (0, pw)), constant_values=np.nan)
    blocks = padded.reshape(padded.shape[0] // k, k, padded.shape[1] // k, k)
    cnt = np.isfinite(blocks).sum(axis=(1, 3))
    total = np.where(np.isfinite(blocks), blocks, 0.0).sum(axis=(1, 3))
    mean = np.where(cnt > 0, total / np.maximum(cnt, 1), np.nan)
    flipped = mean[::-1]  # the first row is the top (y1) row
    nyb, nxb = flipped.shape
    x_left = x0 + c0 * c
    y_bottom = y0 + r0 * c
    return {
        "nx": nxb,
        "ny": nyb,
        "extent": {"x0": x_left, "x1": x_left + nxb * k * c, "y0": y_bottom, "y1": y_bottom + nyb * k * c},
        "values": [None if not math.isfinite(v) else round(float(v), 2) for v in flipped.ravel()],
        "block_cells": int(k),
        "cell_m": c,
    }


def _chart(cid: str, ctype: str, title: dict, serves: list[str], producer: dict, **body: Any) -> dict:
    return {
        "schema_version": "1.0",
        "kind": "chart-series",
        "id": cid,
        "case": "E2",
        "chart_type": ctype,
        "status": "ok",
        "title": title,
        "producer": producer,
        "serves": serves,
        **body,
    }


def _not_run_chart(cid: str, ctype: str, title: dict, producer: dict, reason: str) -> dict:
    return {
        "schema_version": "1.0",
        "kind": "chart-series",
        "id": cid,
        "case": "E2",
        "chart_type": ctype,
        "status": "not-run",
        "title": title,
        "producer": producer,
        "serves": SERVES,
        "not_run_reason": _en_es(reason, reason),
    }


def _write(out_dir: Path, name: str, doc: Any) -> None:
    text = json.dumps(doc, indent=1) + "\n"
    if name.startswith("charts/") and len(text.encode()) > MAX_CHART_BYTES:
        raise ValueError(f"{name} is {len(text.encode())} bytes, above the {MAX_CHART_BYTES} byte chart budget")
    (out_dir / name).write_text(text, encoding="utf-8", newline="\n")


def run_e2(
    out_dir: Path,
    *,
    path_2018: Path,
    path_2023: Path,
    recipe: Mapping[str, Any],
    data_root: Path | None = None,
) -> dict:
    """Prepare the pair, difference it over every area and write all outputs; returns the content of `e2-run.json`."""
    out_dir = Path(out_dir)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)
    prep = prepare_pair(
        path_2018,
        path_2023,
        recipe={k: recipe[k] for k in ("dem_metadata", "vertical_transform") if k in recipe},
    )
    producer = {
        "tool": "pitstudio",
        "method": METHOD,
        "version": "pitstudio-survey-1.0",
        "label": LABEL,
    }
    areas = list(recipe["areas"])
    table_title = _en_es("Cut, fill and net volume", "Volumen de corte, relleno y neto")
    epochs = tuple(recipe.get("epochs", ("2018", "2023")))  # the epoch of the older and of the newer DEM
    period = recipe.get("period", f"{epochs[0]} to {epochs[1]}")
    period_es = period.replace(" to ", " a ")
    paths = tuple(
        recipe.get(
            "surface_paths",
            (
                f"data/raw/usgs-3dep-bingham/{Path(path_2018).name}",
                f"data/raw/usgs-3dep-bingham/{Path(path_2023).name}",
            ),
        )
    )
    if recipe.get("run_label"):
        producer["label"] = f"{LABEL}; {recipe['run_label']}"[:200]
    bars_title = _en_es(
        f"Cut, fill and net surface change {period}", f"Corte, relleno y cambio neto de superficie {period_es}"
    )
    map_title = _en_es(f"Elevation change {period}", f"Cambio de elevación {period_es}")
    if prep.status != "ok":
        reason = prep.label or "Not run"
        doc = {
            "schema_version": "1.0",
            "volumes": [
                {
                    "id": recipe["id"],
                    "scope": "real",
                    "method": "dem-differencing",
                    "status": "not_run",
                    "reason": reason,
                    "label": LABEL,
                    "licence": dict(recipe["licence"]),
                }
            ],
        }
        _write(out_dir, "survey-volume.json", doc)
        for cid, ctype, title in (
            ("e2-volume-bars", "bar", bars_title),
            ("e2-difference-map", "raster", map_title),
            ("e2-volume-table", "table", table_title),
        ):
            _write(out_dir, f"charts/{cid}.json", _not_run_chart(cid, ctype, title, producer, reason))
        summary = {"kind": "e2-run", "case": "E2", "status": "not_run", "label": reason, "prepare": None, "volumes": []}
        _write(out_dir, "e2-run.json", summary)
        return summary

    before_full, after_full = _surface(prep.before), _surface(prep.after)  # type: ignore[arg-type]
    ny, nx = after_full.z.shape
    c = after_full.cell_size_m
    bx0, by0 = after_full.origin_xy
    query_box = np.array([[bx0, by0], [bx0 + nx * c, by0], [bx0 + nx * c, by0 + ny * c], [bx0, by0 + ny * c]])
    rec = prep.record
    assert rec is not None
    meta_common = {
        "licence": dict(recipe["licence"]),
        "surfaces": {
            "before": _surface_meta(rec, "2018", epochs[0], paths[0]),
            "after": _surface_meta(rec, "2023", epochs[1], paths[1]),
        },
        "resampling": {"method": "none"}
        if rec["resampling"] == "none"
        else {"method": "bilinear", "source_crs": rec["source_crs_2018"]},
        "vertical_transform": _transform_meta(rec["vertical_transform"]),
    }
    volumes: list[dict] = []
    surfaces_by_area: dict[str, tuple[Surface, Surface, np.ndarray]] = {}
    footprint_digests: dict[str, str] = {}
    for area in areas:
        footprint, digest = _footprint(area, data_root)
        if digest:
            footprint_digests[area["id"]] = digest
        clipped = clip_polygon(footprint, query_box) if len(footprint) else np.empty((0, 2))
        window = clipped if len(clipped) else query_box
        before = _crop(before_full, window[:, 0].min(), window[:, 1].min(), window[:, 0].max(), window[:, 1].max())
        after = _crop(after_full, window[:, 0].min(), window[:, 1].min(), window[:, 0].max(), window[:, 1].max())
        vid = f"{recipe['id']}-{area['id']}"
        try:
            vol = real_volume(
                before,
                after,
                footprint=footprint,
                query_box=query_box,
                meta={"id": vid, **meta_common},
                footprint_label=area.get("footprint_label"),
            )
        except InvalidSurfaceError as exc:  # e.g. one epoch has no valid cell inside the area: never a made-up number
            volumes.append(
                {
                    "id": vid,
                    "scope": "real",
                    "method": "dem-differencing",
                    "status": "not_run",
                    "reason": f"Not run {EM_DASH} {exc.reason}"[:300],
                    "label": LABEL,
                    "licence": dict(recipe["licence"]),
                }
            )
            continue
        volumes.append(vol)
        surfaces_by_area[area["id"]] = (before, after, np.asarray(vol["polygon"]["vertices"]))
    _write(out_dir, "survey-volume.json", {"schema_version": "1.0", "volumes": volumes})

    by_area = {a["id"]: v for a, v in zip(areas, volumes, strict=True)}
    ok_areas = [a for a in areas if by_area[a["id"]]["status"] == "ok"]
    if not ok_areas:
        reason = "; ".join(f"{a['label']}: {by_area[a['id']]['reason']}" for a in areas)[:200]
        for cid, ctype, title in (
            ("e2-volume-bars", "bar", bars_title),
            ("e2-difference-map", "raster", map_title),
            ("e2-volume-table", "table", table_title),
        ):
            _write(out_dir, f"charts/{cid}.json", _not_run_chart(cid, ctype, title, producer, reason))
        summary = {"kind": "e2-run", "case": "E2", "status": "not_run", "label": reason, "volumes": []}
        _write(out_dir, "e2-run.json", summary)
        return summary
    cats = [
        {"id": "cut", "label": _en_es("Cut", "Corte")},
        {"id": "fill", "label": _en_es("Fill", "Relleno")},
        {"id": "net", "label": _en_es("Net (fill minus cut)", "Neto (relleno menos corte)")},
    ]
    bar_series = []
    for a in ok_areas:
        v = by_area[a["id"]]
        y = [v["v_cut_m3"], v["v_fill_m3"], v["v_net_m3"]]
        bound = v["uncertainty_m3"]["correlated"]
        bar_series.append(
            {
                "id": a["id"],
                "label": _en_es(a["label"], a.get("label_es", a["label"])),
                "y": y,
                "lo": [t - bound for t in y],
                "hi": [t + bound for t in y],
                "band_label": _en_es(
                    "Fully correlated vertical-error bound from the RMSEz of both epochs",
                    "Cota de error vertical totalmente correlacionado a partir del RMSEz de ambas épocas",
                ),
            }
        )
    map_area = recipe.get("map_area", areas[0]["id"])
    if map_area not in surfaces_by_area:  # the wanted area was not run: the first area that was
        map_area = ok_areas[0]["id"]
    mb, ma, mpoly = surfaces_by_area[map_area]
    raster = _map_raster(mb, ma, mpoly)
    vals = np.array([v for v in raster["values"] if v is not None])
    q = float(np.percentile(np.abs(vals), 99)) or 1.0
    ext = raster.pop("extent")
    block_cells, cell_m = raster.pop("block_cells"), raster.pop("cell_m")
    raster["extent"] = ext
    raster["colour"] = {
        "colormap": "cividis",
        "vmin": -q,
        "vmax": q,
        "unit": "m",
        "label": _en_es(
            f"Surface change, {epochs[1]} minus {epochs[0]} (negative is cut)",
            f"Cambio de superficie, {epochs[1]} menos {epochs[0]} (negativo es corte)",
        ),
    }
    table_rows = []
    for a in areas:
        v = by_area[a["id"]]
        if v["status"] != "ok":
            table_rows.append([f"{a['label']}: {v['reason']}"[:200], None, None, None, None, None, None, None])
            continue
        table_rows.append(
            [
                a["label"],
                v["v_cut_m3"],
                v["v_fill_m3"],
                v["v_net_m3"],
                v["uncertainty_m3"]["uncorrelated"],
                v["uncertainty_m3"]["correlated"],
                v["cells"]["valid"],
                v["cells"]["nodata_fraction"],
            ]
        )
    charts = [
        _chart(
            "e2-volume-bars",
            "bar",
            bars_title,
            SERVES,
            producer,
            y_axis={"label": _en_es("Volume", "Volumen"), "unit": "m3"},
            categories=cats,
            series=bar_series,
            caption=_en_es(
                "Measurement of the surface change between two lidar epochs, not a validation.",
                "Medición del cambio de superficie entre dos épocas lidar, no una validación.",
            ),
        ),
        _chart(
            "e2-difference-map",
            "raster",
            map_title,
            [*SERVES, "FR-017-30"],
            producer,
            x_axis={"label": _en_es("Easting", "Este"), "unit": "m"},
            y_axis={"label": _en_es("Northing", "Norte"), "unit": "m"},
            raster=raster,
            caption=_en_es(
                f"Mean of {block_cells} x {block_cells} cells of {cell_m:g} m inside the area of interest.",
                f"Media de {block_cells} x {block_cells} celdas de {cell_m:g} m dentro del área de interés.",
            ),
        ),
        _chart(
            "e2-volume-table",
            "table",
            table_title,
            SERVES,
            producer,
            table={
                "columns": [
                    {"id": "area", "label": _en_es("Area of interest", "Área de interés"), "type": "text"},
                    {"id": "cut", "label": _en_es("Cut", "Corte"), "type": "number", "unit": "m3"},
                    {"id": "fill", "label": _en_es("Fill", "Relleno"), "type": "number", "unit": "m3"},
                    {"id": "net", "label": _en_es("Net", "Neto"), "type": "number", "unit": "m3"},
                    {
                        "id": "bound-uncorrelated",
                        "label": _en_es("Bound, uncorrelated error", "Cota, error no correlacionado"),
                        "type": "number",
                        "unit": "m3",
                    },
                    {
                        "id": "bound-correlated",
                        "label": _en_es("Bound, fully correlated error", "Cota, error totalmente correlacionado"),
                        "type": "number",
                        "unit": "m3",
                    },
                    {"id": "cells", "label": _en_es("Valid cells", "Celdas válidas"), "type": "number", "unit": "1"},
                    {
                        "id": "nodata",
                        "label": _en_es("No-data fraction", "Fracción sin dato"),
                        "type": "number",
                        "unit": "1",
                    },
                ],
                "rows": table_rows,
            },
        ),
    ]
    for ch in charts:
        _write(out_dir, f"charts/{ch['id']}.json", ch)

    summary = {
        "kind": "e2-run",
        "case": "E2",
        "status": "ok",
        "label": LABEL,
        "prepare": {k: rec[k] for k in rec if k not in ("metadata_from_recipe",)},
        "metadata_from_recipe": rec["metadata_from_recipe"],
        "dem_metadata_sources": {k: v.get("source") for k, v in (recipe.get("dem_metadata") or {}).items()},
        "footprint_sha256": footprint_digests,
        "volumes": [
            {
                "id": v["id"],
                "v_cut_m3": v["v_cut_m3"],
                "v_fill_m3": v["v_fill_m3"],
                "v_net_m3": v["v_net_m3"],
                "uncertainty_m3": v["uncertainty_m3"],
                "overlap_ratio": v["polygon"]["overlap_ratio"],
                "cells": v["cells"],
            }
            if v["status"] == "ok"
            else {"id": v["id"], "status": v["status"], "reason": v["reason"]}
            for v in volumes
        ],
        "notes": list(recipe.get("notes", [])),
        "versions": {"python": platform.python_version()},
        "charts": [c["id"] for c in charts],
    }
    _write(out_dir, "e2-run.json", summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    import yaml

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("recipe", type=Path, help="a recipe YAML: the params of its first stage are the run parameters")
    p.add_argument("out_dir", type=Path)
    p.add_argument("--data-root", type=Path, required=True)
    a = p.parse_args(argv)
    doc = yaml.safe_load(a.recipe.read_text(encoding="utf-8"))
    recipe = doc["stages"][0]["params"] if "stages" in doc else doc
    summary = run_e2(
        a.out_dir,
        path_2018=a.data_root / recipe["dem_2018"],
        path_2023=a.data_root / recipe["dem_2023"],
        recipe=recipe,
        data_root=a.data_root,
    )
    print(json.dumps({"status": summary["status"], "volumes": summary["volumes"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
