"""Driver of the C1 results of 2026-11-23: error tables, event curves, the de Wit state and the wall sections.

Sub-commands (every one deterministic for its seeds, CPU only, writes JSON under ``--out``)::

    python -m pitstudio_pipeline.slope.c1_results crop-dem --dem DEM --out TIF      (studio environment: rasterio)
    python -m pitstudio_pipeline.slope.c1_results walls --dem TIF --out DIR [--section K]
    python -m pitstudio_pipeline.slope.c1_results errors --events-from ttf-results.json --out DIR
    python -m pitstudio_pipeline.slope.c1_results curves --events-from ttf-results.json --onnx DIR --out DIR
    python -m pitstudio_pipeline.slope.c1_results real --archive Data.zip --out DIR
    python -m pitstudio_pipeline.slope.c1_results dewit --archive Data.zip --onnx DIR --out DIR

The 1 m 3DEP tile is LZW compressed and ``tifffile`` here has no ``imagecodecs``, so ``crop-dem`` writes an uncompressed
window of it (same georeferencing, no resampling) and ``walls`` reads that window; the SHA-256 of the source tile is
recorded next to the one of the window.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio.slope import lem
from pitstudio_pipeline.slope import c1_errors, c1_walls

SEED = 20261007  # the recipe seed of studio/recipes/cases/c1.yaml
COMPARISON_SEED = SEED + 1  # the "comparison" seed of s50 (seed + 1), as in pitstudio_pipeline.slope.c1
SITE_LABEL = "Bingham Canyon west wall, 3DEP 2018 (provisional)"
SOURCE_ID = "usgs-3dep-bingham"
WINDOW = (401000.0, 4485800.0, 402600.0, 4487600.0)  # x0, y0, x1, y1 (EPSG:26912)
WALL_LINE = ((401700.0, 4486300.0), (401700.0, 4487100.0))
HALF_LENGTH_M = 450.0
DROP_M = 100.0
POF = {"samples": 2000, "candidates": 64, "seed": SEED}
# The inputs of the example section of specs/010-slope/contracts/examples/slope-section.valid-hoek-brown.json.
# No rock-mass
# data of the pit is sourced: every number is illustrative and UNVERIFIED.
MATERIAL = {
    "id": "monzonite",
    "model": "hoek-brown",
    "unit_weight_kn_per_m3": 26.0,
    "gsi": 50,
    "m_i": 10,
    "sigma_ci_mpa": 60.0,
    "disturbance_d": 0.7,
}
DISTRIBUTIONS = [
    {
        "material_id": "monzonite",
        "parameter": "gsi",
        "distribution": "normal",
        "mean": 50,
        "sd": 5,
        "truncate_lower": 10,
        "truncate_upper": 100,
    },
    {"material_id": "monzonite", "parameter": "sigma_ci_mpa", "distribution": "lognormal", "mean": 60.0, "cv": 0.3},
]
# Mohr-Coulomb strength used only for the pySlope comparison (pySlope has no Hoek-Brown): illustrative, UNVERIFIED
ORACLE_MC = {"gamma": 26.0, "c": 150.0, "phi": 38.0}
DEFAULTS = {
    "materials": [MATERIAL],
    "pore_pressure_ratio": 0.2,
    "analysis": {
        "mode": "live",
        "methods": ["bishop", "spencer"],
        "slices": 50,
        "search": dict(c1_walls.SEARCH),
    },
}


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def crop_dem(dem: Path, out: Path) -> dict[str, Any]:
    """Write the uncompressed window ``WINDOW`` of the LZW tile ``dem`` (needs rasterio)."""
    import rasterio
    from rasterio.windows import from_bounds

    with rasterio.open(dem) as ds:
        win = from_bounds(*WINDOW, ds.transform).round_offsets().round_lengths()
        z = ds.read(1, window=win)
        profile = {
            "driver": "GTiff",
            "height": z.shape[0],
            "width": z.shape[1],
            "count": 1,
            "dtype": "float32",
            "crs": ds.crs,
            "transform": ds.window_transform(win),
            "nodata": ds.nodata,
            "compress": None,
            "tiled": False,
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(out, "w", **profile) as o:
            o.write(z, 1)
    record = {"source": dem.name, "source_sha256": _sha(dem), "window": list(WINDOW), "window_sha256": _sha(out)}
    _write(out.with_suffix(".json"), record)
    return record


def walls(dem_window: Path, out: Path, only: int | None) -> None:
    """The three wall sections: FoS (Bishop, Spencer), the critical circle and the PoF with its distribution."""
    from pitstudio_pipeline.slope import sections  # tifffile: pipeline environment only

    extracted = sections.extract_sections(
        dem_window,
        source_id=SOURCE_ID,
        site_label=SITE_LABEL,
        wall_line=WALL_LINE,
        half_length_m=HALF_LENGTH_M,
        defaults=DEFAULTS,
    )
    parent = json.loads(dem_window.with_suffix(".json").read_text(encoding="utf-8"))
    for k, base in enumerate(extracted.sections):
        if only is not None and k != only:
            continue
        doc = c1_walls.wall_section(
            base, drop_m=DROP_M, mode="live", pof_settings=POF, material=MATERIAL, distributions=DISTRIBUTIONS
        )
        t0 = time.monotonic()
        fos = lem.analyse_section(doc)
        t_fos = time.monotonic() - t0
        t0 = time.monotonic()
        pof_result = c1_walls.pof_distribution(doc, n=POF["samples"], k=POF["candidates"], seed=POF["seed"])
        t_pof = time.monotonic() - t0
        mins = np.asarray(pof_result.pop("min_factors"), dtype=float)
        hist = c1_walls.histogram(mins[np.isfinite(mins)], bins=40)
        _write(
            out / f"{doc['section_id']}.json",
            {
                "section": doc,
                "dem": {"parent_source_sha256": parent["source_sha256"], "window_sha256": parent["window_sha256"]},
                "fos": fos["fos"],
                "pof": pof_result,
                "pof_min_factor_histogram": hist,
                "pof_min_factor_summary": {
                    "min": float(np.min(mins)),
                    "median": float(np.median(mins)),
                    "max": float(np.max(mins)),
                },
                "seconds": {"fos": round(t_fos, 1), "pof": round(t_pof, 1)},
            },
        )
        print(
            f"{doc['section_id']}: FoS {[(r['method'], round(r.get('fos', float('nan')), 3)) for r in fos['fos']]}",
            flush=True,
        )


def errors(events_from: Path, out: Path) -> None:
    """Paired intervals, the comparison statement, the error distributions and the summary rows of a results file."""
    doc = json.loads(events_from.read_text(encoding="utf-8"))
    rows = doc["events"]
    comparisons = c1_errors.paired_intervals(rows, seed=COMPARISON_SEED, resamples=10_000)
    _write(
        out / "error-results.json",
        {
            "source_run_id": doc["run_id"],
            "snr_basis": doc["snr_basis"],
            "summary": doc["summary"],
            "median_intervals": c1_errors.median_intervals(rows, seed=SEED, resamples=10_000),
            "comparisons": comparisons,
            "statement": c1_errors.comparison_statement(comparisons),
            "distributions": c1_errors.error_distributions(rows),
            "acceptance": doc["acceptance"],
        },
    )


JOB_SEED = (
    20261012  # the seed of the GPU job that scored the rows (its Bayesian draws), kept so the values can be compared
)


def _job_config() -> dict[str, Any]:
    from pitstudio.slope import events

    cfg = events.default_config(None)
    cfg["n_samples"] = 2000
    cfg["splits"] = {
        "train": {"start": 0, "count": 20_000},
        "validation": {"start": 1_000_000, "count": 1_000},
        "test": {"start": 2_000_000, "count_per_stratum": 500},
    }
    return cfg


def curves(events_from: Path, onnx_dir: Path, out: Path) -> None:
    """Twelve seeded test events (4 per stratum) baked with the on-disk ONNX forecasters at both cut-offs."""
    from pitstudio_pipeline.slope import c1_curves

    doc = json.loads(events_from.read_text(encoding="utf-8"))
    rows = doc["events"]
    stored = {(r["event_id"], r["method"], r["cutoff"]): r for r in rows}
    forecasters = c1_curves.load_onnx_forecasters(onnx_dir)
    cfg = _job_config()
    stratum_of = {r["event_id"]: r["stratum"] for r in rows}
    baked, checks = [], []
    for event_id in c1_curves.select_events(rows):
        event = c1_curves.rebuild_event(event_id, stratum_of[event_id], cfg)
        item = c1_curves.bake_event(event, forecasters, seed=JOB_SEED)
        baked.append(item)
        for c in item["cutoffs"]:
            for method, arm in c["methods"].items():
                ref = stored[(event_id, method, c["cutoff"])]
                if arm.get("status") != "ok" or "t_hat_f_h" not in ref:
                    continue
                checks.append(
                    {
                        "event_id": event_id,
                        "method": method,
                        "cutoff": c["cutoff"],
                        "baked_t_hat_f_h": arm["t_hat_f_h"],
                        "scored_t_hat_f_h": ref["t_hat_f_h"],
                        "abs_diff_h": abs(arm["t_hat_f_h"] - ref["t_hat_f_h"]),
                    }
                )
    by_method: dict[str, float] = {}
    for c in checks:
        by_method[c["method"]] = max(by_method.get(c["method"], 0.0), c["abs_diff_h"])
    _write(
        out / "event-curves.json",
        {
            "source_run_id": doc["run_id"],
            "selection": "per stratum the events at the 10th, 40th, 70th and 95th percentile (by rank) of the TCN "
            "relative error at the cut-off 0.5, so that good and poor cases are both shown",
            "onnx_files": c1_curves.ONNX_FILES,
            "onnx_sha256": {a: _sha(onnx_dir / f) for a, f in c1_curves.ONNX_FILES.items()},
            "zero_shot": "not run: the zero-shot Chronos-Bolt arm has no ONNX file (FR-010-30: baked forecasts only)",
            "events": baked,
            "consistency_with_scored_rows": {"max_abs_diff_h_by_method": by_method, "rows": checks},
        },
    )


def real(archive: Path, out: Path) -> None:
    """The de Wit archive evidence and the not-run real-event state."""
    from pitstudio_pipeline.slope import c1_real, dewit

    evidence = c1_real.archive_evidence(archive, expected_bytes=dewit.EXPECTED_BYTES, expected_md5=dewit.EXPECTED_MD5)
    _write(
        out / "real-event.json",
        {
            "evidence": evidence,
            "state": c1_real.real_event_state(evidence),
            "record_page_check": {
                "zenodo_record_15003054": "read 2026-11-23: no failure date, no description of the radar "
                "files or units",
                "seismica_article_1902": "abstract only: velocity decrease about 12 days before the initiation of the "
                "slope failure; no date (the full PDF was not reachable: UNVERIFIED)",
            },
        },
    )


def dewit(archive: Path, onnx_dir: Path, out: Path) -> None:
    """The de Wit real event: the prism series, the five methods at 0.5 and 0.8, the sensitivity row, chart inputs."""
    import zipfile

    from pitstudio_pipeline.slope import c1_curves, c1_real, c1_real_eval, dewit_prisms
    from pitstudio_pipeline.slope import dewit as dewit_mod

    evidence = c1_real.archive_evidence(
        archive, expected_bytes=dewit_mod.EXPECTED_BYTES, expected_md5=dewit_mod.EXPECTED_MD5
    )
    primary = dewit_prisms.ingest_prisms(archive, failure_time=c1_real_eval.PRIMARY_FAILURE)
    sens = dewit_prisms.ingest_prisms(archive, failure_time=c1_real_eval.SENSITIVITY_FAILURE)
    forecasters = c1_curves.load_onnx_forecasters(onnx_dir)
    pair = c1_real_eval.evaluate_pair(primary.document, sens.document, forecasters, seed=SEED)
    detail = c1_real_eval.bake(primary.document, forecasters, seed=SEED)
    with zipfile.ZipFile(archive) as z:
        events_csv = z.read("seismic-event-data/events-and-blasts.csv").decode("utf-8", "replace")
    blast = c1_real_eval.blast_marker(events_csv, c1_real_eval.BLAST_DATE, utc_offset_h=10.0)
    state = {
        "event_id": dewit_mod.EVENT_ID,
        "status": "run",
        "label": c1_real.LABEL,
        "label_es": c1_real.LABEL_ES,
        "snr_obs": primary.document["snr_obs"],
    }
    _write(
        out / "real-event.json",
        {
            "evidence": evidence,
            "state": state,
            "failure_time": c1_real_eval.PRIMARY_FAILURE,
            "sensitivity_failure_time": c1_real_eval.SENSITIVITY_FAILURE,
            "series": primary.document,
            "sensitivity_series": {
                k: sens.document[k]
                for k in (
                    "t_0_instant",
                    "t_f_instant",
                    "t_f_h",
                    "snr_obs",
                    "prisms",
                    "sampling",
                    "t_h",
                    "los_displacement_mm",
                )
            },
            "pair": pair,
            "detail": detail,
            "blast": blast,
            "onnx_sha256": {a: _sha(onnx_dir / f) for a, f in c1_curves.ONNX_FILES.items()},
            "record_page_check": {
                "zenodo_record_15003054": "read 2026-11-23: no failure date, no description of the radar files "
                "or units",
                "seismica_article_1902": "the failure date is quoted from the article text by the main session; the "
                "article page reachable here shows the abstract only (UNVERIFIED by this run)",
            },
        },
    )
    print(
        f"series {len(primary.document['t_h'])} epochs, t_f_h {primary.document['t_f_h']:.1f}, "
        f"SNR_obs {primary.document['snr_obs']:.2f}, prisms {primary.document['prisms']}",
        flush=True,
    )


def oracle(walls_dir: Path, out: Path) -> None:
    """The pySlope planar-reduction check of every wall section found in walls_dir (root environment: pySlope)."""
    from pitstudio_pipeline.slope import c1_oracle

    checks = []
    for f in sorted(walls_dir.glob("usgs-3dep-bingham-s*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))["section"]
        checks.append(
            c1_oracle.check_planar_reduction(
                doc, gamma=ORACLE_MC["gamma"], cohesion_kpa=ORACLE_MC["c"], friction_deg=ORACLE_MC["phi"]
            )
        )
        print(checks[-1]["section_id"], checks[-1]["fixed_pass"], checks[-1]["search_pass"], flush=True)
    _write(out / "oracle-check.json", {"checks": checks})


def assemble(
    data_dir: Path,
    out_dir: Path,
    specs_dir: Path,
    ttf_results: Path,
    schema: Path,
    only: list[str] | None = None,
) -> None:
    """The four run folders (charts, raw data, summary) and their import specs."""
    from pitstudio_pipeline.slope import c1_assemble

    written = c1_assemble.assemble(data_dir, out_dir, specs_dir, ttf_results=ttf_results, schema=schema, only=only)
    for slug, ids in written.items():
        print(slug, len(ids), "charts")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("crop-dem")
    p.add_argument("--dem", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("walls")
    p.add_argument("--dem", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--section", type=int)
    p = sub.add_parser("errors")
    p.add_argument("--events-from", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("curves")
    p.add_argument("--events-from", required=True)
    p.add_argument("--onnx", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("real")
    p.add_argument("--archive", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("dewit")
    p.add_argument("--archive", required=True)
    p.add_argument("--onnx", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("oracle")
    p.add_argument("--walls", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("assemble")
    p.add_argument("--data", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--specs", required=True)
    p.add_argument("--ttf-results", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--only", nargs="+")
    args = ap.parse_args(argv)
    if args.cmd == "assemble":
        assemble(
            Path(args.data), Path(args.out), Path(args.specs), Path(args.ttf_results), Path(args.schema), args.only
        )
    elif args.cmd == "dewit":
        dewit(Path(args.archive), Path(args.onnx), Path(args.out))
    elif args.cmd == "oracle":
        oracle(Path(args.walls), Path(args.out))
    elif args.cmd == "real":
        real(Path(args.archive), Path(args.out))
    elif args.cmd == "curves":
        curves(Path(args.events_from), Path(args.onnx), Path(args.out))
    elif args.cmd == "crop-dem":
        crop_dem(Path(args.dem), Path(args.out))
    elif args.cmd == "walls":
        walls(Path(args.dem), Path(args.out), args.section)
    elif args.cmd == "errors":
        errors(Path(args.events_from), Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
