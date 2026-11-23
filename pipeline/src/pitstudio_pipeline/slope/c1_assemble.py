"""The four C1 run folders of 2026-11-23: charts, raw data, the "Published results" summary and the import spec.

``assemble`` reads what the ``c1_results`` sub-commands wrote, builds every chart with ``c1_charts``, checks it against
the chart-series contract and writes ``<out>/<slug>/`` for ``studio import-run --from``. The runs are CPU work done
outside the runner: the import spec carries ``"kind": "cpu"`` and says so in its label and notes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from pitstudio_pipeline.slope import c1_charts

RUNS = ("c1-error-results", "c1-event-curves", "c1-real-event", "c1-wall-sections")
SYNTH = "calibrated synthetic, not validated against real data"
PRODUCER_PATHS = ["pipeline/src/pitstudio_pipeline/slope", "studio/recipes/cases/c1.yaml"]
STAGES = {
    "c1-error-results": ("s50_evaluate", "pitstudio"),
    "c1-event-curves": ("s40_infer", "onnx-runtime"),
    "c1-real-event": ("s00_download", "pitstudio"),
    "c1-wall-sections": ("s20_feature_extraction", "minephys"),
}
SEED = 20261007
ATTRIBUTION = (
    "de Wit (2025). Data used for the study of time-lapse velocity variations during an open-pit mine slope failure using "
    "seismic noise interferometry. Zenodo. https://doi.org/10.5281/zenodo.15003054. Licensed under CC BY 4.0."
)


def _hw(name: str, value: float, unit: str, note: str = "", kpi: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "value": round(float(value), 4),
        "unit": unit,
        **({"note": note} if note else {}),
        **({"kpi": kpi} if kpi else {}),
    }


def summary_of(slug: str, data: Mapping[str, Any]) -> dict[str, Any]:
    """The summary read by the case page for the run ``slug`` (see the module docstring of ``import_summaries``)."""
    if slug == "c1-error-results":
        errs = data["errors"]
        comps = errs["comparisons"]
        better = sum(1 for c in comps if c["verdict"] == "better")
        stm = errs["statement"]
        return {
            "methods": ["M14"],
            "title": "C1 forecast error by method and noise stratum, with paired intervals against inverse velocity",
            "label": SYNTH + "; nominal signal-to-noise strata, no observed SNR",
            "verdict": "ok",
            "headline": [
                _hw(
                    "Learned-arm comparisons better than inverse velocity (interval above 0)",
                    better,
                    "1",
                    f"of {stm['comparisons']} comparisons made, 95 % paired percentile bootstrap, no family-wise claim",
                )
            ],
            "rows": [
                {
                    "stratum": c["stratum"],
                    "method": c["method"],
                    "cutoff": c["cutoff"],
                    "mean_difference": round(c["mean_difference"], 4),
                    "lower": round(c["interval"]["lower"], 4),
                    "upper": round(c["interval"]["upper"], 4),
                    "verdict": c["verdict"],
                }
                for c in comps
            ],
        }
    if slug == "c1-event-curves":
        curves = data["curves"]
        worst = curves["consistency_with_scored_rows"]["max_abs_diff_h_by_method"]
        return {
            "methods": ["M14"],
            "title": "C1 seeded event curves with the baselines and the three exported forecasters",
            "label": SYNTH + "; nominal signal-to-noise strata; forecasters run with ONNX Runtime CPU on the exported files",
            "verdict": "ok",
            "headline": [
                _hw("Seeded test events baked", len(curves["events"]), "1", "4 per stratum, chosen by rank of the TCN error"),
                _hw(
                    "Largest gap between a baked and a scored failure time",
                    max(worst.values()),
                    "h",
                    "ONNX Runtime CPU against the scored rows of the GPU job",
                ),
            ],
            "rows": [
                {
                    "event": e["event_id"],
                    "stratum": e["stratum"],
                    "true_failure_h": round(e["t_f_h"], 2),
                    "tcn_at_0_5_h": e["cutoffs"][0]["methods"]["tcn"].get("t_hat_f_h"),
                    "tcn_at_0_8_h": e["cutoffs"][1]["methods"]["tcn"].get("t_hat_f_h"),
                }
                for e in curves["events"]
            ],
        }
    if slug == "c1-real-event":
        real = data["real"]
        return {
            "methods": ["M14"],
            "title": "C1 single real event (de Wit): not run",
            "label": c1_charts.REAL_LABEL + "; not run: the archive states no failure time",
            "verdict": "partial",
            "headline": [_hw("Archive members read", len(real["evidence"]["members"]), "1", "no forecast number is published")],
            "rows": [{"member": m["name"], "bytes": m["bytes"]} for m in real["evidence"]["members"]],
        }
    if slug == "c1-wall-sections":
        walls = data["walls"]
        best = []
        for w in walls:
            bishop = next((r for r in w["fos"] if r["method"] == "bishop" and r.get("status") == "ok"), None)
            best.append((bishop["fos"] if bishop else float("inf"), w))
        lowest_fos, lowest = min(best, key=lambda t: t[0])
        k = int(lowest["section"]["section_id"].rsplit("-s", 1)[1])
        pof = lowest["pof"]
        note = f"lowest of the {len(walls)} sections: section {k}"
        return {
            "methods": ["M13"],
            "title": "C1 wall sections: minimum factor of safety, slip circle and probability of failure",
            "label": c1_charts.WALL_LABEL,
            "verdict": "ok",
            "headline": [
                _hw("Minimum factor of safety, Bishop", lowest_fos, "1", note, kpi="fos"),
                _hw(
                    "Probability of failure",
                    100.0 * pof["pof"],
                    "%",
                    f"{note}; {pof['failures']} of {pof['samples']} samples, the {pof['candidates']} most critical surfaces",
                    kpi="pof",
                ),
            ],
            "rows": [
                {
                    "section": w["section"]["section_id"],
                    "fos_bishop": next((round(r["fos"], 3) for r in w["fos"] if r["method"] == "bishop" and "fos" in r), None),
                    "fos_spencer": next((round(r["fos"], 3) for r in w["fos"] if r["method"] == "spencer" and "fos" in r), None),
                    "pof": w["pof"]["pof"],
                }
                for w in walls
            ],
        }
    raise ValueError(f"unknown C1 run {slug!r}")


def import_spec(
    slug: str,
    charts: Sequence[Mapping[str, Any]],
    extra_outputs: Sequence[tuple[str, str]],
    *,
    inputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """The import spec of a run folder (see the module docstring)."""
    stage, tool = STAGES[slug]
    licence = ("attribution", "CC-BY-4.0") if slug == "c1-real-event" else ("own", "CC-BY-4.0")
    common = {"budget_class": "studio-showcase", "licence_class": licence[0], "spdx": licence[1]}
    outputs: list[dict[str, Any]] = [
        {
            "name": f"charts/{c['id']}.json",
            "from": f"charts/{c['id']}.json",
            "kind": "chart-series",
            "publish": True,
            "id": c["id"],
            "media_type": "application/json",
            "inputs": [dict(i) for i in inputs],
            **common,
        }
        for c in charts
    ]
    outputs += [
        {"name": name, "from": src, "kind": "table", "publish": False, **common} for name, src in extra_outputs
    ]
    outputs.append(
        {
            "name": "results-summary.json",
            "from": "results-summary.json",
            "kind": "table",
            "publish": True,
            "id": f"{slug}-results",
            "media_type": "application/json",
            **common,
        }
    )
    label = (
        c1_charts.REAL_LABEL + "; not run: the archive states no failure time"
        if slug == "c1-real-event"
        else c1_charts.WALL_LABEL
        if slug == "c1-wall-sections"
        else SYNTH + "; nominal signal-to-noise strata, no observed SNR"
    )
    notes = [
        "Produced on the CPU by pitstudio_pipeline.slope.c1_results (not by the GPU queue); no GPU time is used.",
        "The forecasts and errors come from the files of GPU job 33-slope-forecasters (ttf-results.json and the ONNX files).",
    ]
    if slug == "c1-real-event":
        notes.append(ATTRIBUTION)
    return {
        "job": slug,
        "kind": "cpu",
        "case": "C1",
        "recipe": "cases/c1.yaml",
        "slug": slug,
        "seed": SEED,
        "label": label[:300],
        "producer_paths": list(PRODUCER_PATHS),
        "notes": notes,
        "stages": [{"id": stage, "tool": tool, "outputs": outputs}],
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def assemble(
    data_dir: Path, out_dir: Path, specs_dir: Path, *, ttf_results: Path, schema: Path
) -> dict[str, list[str]]:
    """Write the four run folders and their import specs; every chart is validated against ``schema`` first."""
    validator = Draft202012Validator(json.loads(schema.read_text(encoding="utf-8")))
    prod_err = c1_charts.producer(
        "Median with percentile bootstrap, paired percentile bootstrap against inverse velocity, B = 10,000",
        SYNTH + "; nominal signal-to-noise strata, no observed SNR",
    )
    prod_curves = c1_charts.producer(
        "Inverse-velocity fit, Bayesian posterior lines, TCN, PatchTST and Chronos-Bolt fine-tuned (ONNX Runtime CPU)",
        SYNTH + "; nominal signal-to-noise strata",
    )
    prod_real = c1_charts.producer(
        "Archive check of Zenodo record 15003054 (checksum, members, ingestion)",
        c1_charts.REAL_LABEL + "; not run: no failure time stated",
    )
    errors = json.loads((data_dir / "error-results.json").read_text(encoding="utf-8"))
    curves = json.loads((data_dir / "event-curves.json").read_text(encoding="utf-8"))
    real = json.loads((data_dir / "real-event.json").read_text(encoding="utf-8"))
    walls = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((data_dir / "walls").glob("usgs-3dep-bingham-s*.json"))]
    oracles = json.loads((data_dir / "oracle-check.json").read_text(encoding="utf-8"))["checks"]
    dem = json.loads((data_dir / "bingham-2018-west-wall-window.json").read_text(encoding="utf-8"))
    prod_walls = c1_charts.producer(c1_charts.WALL_METHOD, c1_charts.WALL_LABEL)

    event_charts: list[dict[str, Any]] = []
    for e in curves["events"]:
        event_charts += c1_charts.event_charts(e, producer=prod_curves)
    plan = {
        "c1-error-results": c1_charts.error_charts(errors, producer=prod_err),
        "c1-event-curves": event_charts,
        "c1-real-event": c1_charts.real_charts(real, producer=prod_real),
        "c1-wall-sections": c1_charts.wall_charts(walls, oracles, producer=prod_walls),
    }
    src_ttf = {"id": "c1-ttf-results-job33", "sha256": _sha(ttf_results), "kind": "source"}
    inputs = {
        "c1-error-results": [src_ttf],
        "c1-event-curves": [src_ttf]
        + [{"id": f"c1-onnx-{a}", "sha256": curves["onnx_sha256"][a], "kind": "source"} for a in curves["onnx_sha256"]],
        "c1-real-event": [{"id": "dewit-slope-failure", "sha256": real["evidence"]["sha256"], "kind": "source"}],
        "c1-wall-sections": [
            {"id": "usgs-3dep-bingham", "sha256": dem["source_sha256"], "kind": "source"},
            {"id": "usgs-3dep-bingham-window", "sha256": dem["window_sha256"], "kind": "source"},
        ],
    }
    raw = {
        "c1-error-results": [("error-results.json", errors)],
        "c1-event-curves": [("event-curves.json", curves)],
        "c1-real-event": [("real-event.json", real)],
        "c1-wall-sections": [(f"sections/{w['section']['section_id']}.json", w) for w in walls]
        + [("oracle-check.json", {"checks": oracles})],
    }
    written: dict[str, list[str]] = {}
    for slug in RUNS:
        run = out_dir / slug
        for chart in plan[slug]:
            problems = [e.message[:160] for e in validator.iter_errors(chart)]
            if problems:
                raise ValueError(f"{chart['id']}: {problems[:2]}")
            _write(run / "charts" / f"{chart['id']}.json", chart)
        extra = []
        for name, obj in raw[slug]:
            _write(run / name, obj)
            extra.append((name, name))
        if slug == "c1-error-results":
            sdata = {"errors": errors}
        elif slug == "c1-wall-sections":
            sdata = {"walls": walls}
        elif slug == "c1-event-curves":
            sdata = {"curves": curves}
        else:
            sdata = {"real": real}
        _write(run / "results-summary.json", summary_of(slug, sdata))
        _write(specs_dir / f"{slug}.json", import_spec(slug, plan[slug], extra, inputs=inputs[slug]))
        written[slug] = [c["id"] for c in plan[slug]]
    return written
