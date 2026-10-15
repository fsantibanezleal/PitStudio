"""The C1 recipe end to end on the open lane (FR-010-39, US-010-5).

``run`` executes the CPU stages of ``studio/recipes/cases/c1.yaml`` in order on the committed sample scale: the sample
section
(`s10_preprocess`), seeded Voight events (`s05_synthesize`), FoS and PoF (`s20_feature_extraction`), TCN and PatchTST
training on
the CPU (`s30_train`), all methods on identical windows (`s40_infer`), the TTF results (`s50_evaluate`) and the ONNX
export with
parity (`s60_export`). An optional de Wit archive feeds the real event; without it (or when it is rejected) the real
event is
"not run". No NVIDIA proprietary runtime is imported. Every artefact gets a DC-000-01 record naming its producer,
lane, licence
class and the SHA-256 of its inputs.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from pitstudio.slope import evaluate as ev
from pitstudio.slope import events, exclusion, results
from pitstudio_pipeline.slope import chronos, data, dewit, export, infer, s50, stability, synth, train

SCALES = ("sample",)
EPOCHS = 3
ROOT = Path(__file__).resolve().parents[4]


@dataclass
class C1Run:
    manifest: dict[str, Any]
    out_dir: Path
    stages: list[str]
    results: dict[str, Any]
    lane_profile: str


def _round(obj: Any) -> Any:
    if isinstance(obj, float):
        return float(f"{obj:.9g}")
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_round(v) for v in obj]
    return obj


def _sample_section() -> dict[str, Any]:
    t = 1.0
    return {
        "schema_version": "1.0",
        "section_id": "c1-sample-planar-20m-45deg",
        "source": {"kind": "fixture"},
        "ground": [[-60.0, 20.0], [0.0, 20.0], [20.0, 0.0], [60.0, 0.0]],
        "crest_x_m": 0.0,
        "toe_x_m": 20.0 * t,
        "materials": [
            {
                "id": "fill",
                "model": "mohr-coulomb",
                "unit_weight_kn_per_m3": 20.0,
                "cohesion_kpa": 20.0,
                "friction_angle_deg": 30.0,
            }
        ],
        "pore_pressure_ratio": 0.0,
        "analysis": {
            "mode": "live",
            "methods": ["bishop", "spencer"],
            "slices": 50,
            "search": {"entry_points": 8, "exit_points": 8, "radius_ratios": 3, "rho_min": 1.2, "rho_max": 3.0},
            "pof": {
                "samples": 200,
                "candidates": 8,
                "seed": 7,
                "distributions": [
                    {
                        "material_id": "fill",
                        "parameter": "cohesion_kpa",
                        "distribution": "normal",
                        "mean": 20.0,
                        "sd": 4.0,
                        "truncate_lower": 0.0,
                    },
                    {
                        "material_id": "fill",
                        "parameter": "friction_angle_deg",
                        "distribution": "normal",
                        "mean": 30.0,
                        "sd": 3.0,
                        "truncate_lower": 5.0,
                        "truncate_upper": 60.0,
                    },
                ],
            },
        },
    }


class _Writer:
    def __init__(self, out_dir: Path, run_id: str, git_sha: str) -> None:
        self.out, self.run_id, self.git_sha = out_dir, run_id, git_sha
        self.artefacts: list[dict[str, Any]] = []
        self.by_id: dict[str, dict[str, Any]] = {}

    def table(
        self,
        art_id: str,
        rel: str,
        obj: Any,
        *,
        tool: str,
        stage: str,
        inputs: list[str],
        sources: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        path = self.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((json.dumps(_round(obj), indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        return self._record(art_id, rel, path, "table", tool, stage, inputs, sources, "static", "own-code")

    def onnx(self, art_id: str, rel: str, src: Path, *, tool: str, stage: str, inputs: list[str]) -> dict[str, Any]:
        path = self.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(src.read_bytes())
        return self._record(art_id, rel, path, "onnx", tool, stage, inputs, None, "replay", "onnx")

    def _record(
        self,
        art_id: str,
        rel: str,
        path: Path,
        kind: str,
        tool: str,
        stage: str,
        inputs: list[str],
        sources: list[dict[str, str]] | None,
        lane: str,
        budget: str,
    ) -> dict[str, Any]:
        raw = path.read_bytes()
        refs = [{"id": i, "sha256": self.by_id[i]["sha256"], "kind": "artefact"} for i in inputs]
        refs += [{"id": s["id"], "sha256": s["sha256"], "kind": "source"} for s in sources or []]
        rec: dict[str, Any] = {
            "id": art_id,
            "run_id": self.run_id,
            "git_sha": self.git_sha,
            "path": rel,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "kind": kind,
            "producer": {"tool": tool, "stage": {"id": stage}},
            "inputs": refs,
            "cases": ["C1"],
            "lane": lane,
            "licence_class": "own",
            "spdx": "Apache-2.0",
            "asset_host": "git",
            "budget_class": budget,
        }
        if lane == "replay":
            rec["lane_measurements"] = {
                "web_drivable": False,
                "max_asset_bytes": len(raw),
                "interaction_ms": None,
                "run_ms_t2": None,
                "trace_bytes": None,
                "measured": {"tier": "T2", "date": "2026-10-12", "browser": "none: CPU run, not measured in a browser"},
            }
        self.artefacts.append(rec)
        self.by_id[art_id] = rec
        return rec


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT, timeout=20
        ).stdout.strip()
        return out if len(out) == 40 else "0" * 40
    except OSError, subprocess.SubprocessError:
        return "0" * 40


def run(
    *,
    out_dir: str | Path,
    scale: str = "sample",
    seed: int = 20261007,
    dewit_archive: str | Path | None = None,
    dewit_pins: dict[str, Any] | None = None,
    failure_time: dict[str, Any] | None = None,
) -> C1Run:
    """Run the CPU stages of the C1 recipe (see the module docstring)."""
    if scale not in SCALES:
        raise ValueError(f"scale must be one of {list(SCALES)}, got {scale!r}")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**63:
        raise ValueError(f"seed must be an integer in [0, 2**63), got {seed!r}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        return _run(out, seed, dewit_archive, dewit_pins, failure_time)
    finally:
        torch.set_num_threads(threads)


def _run(
    out: Path, seed: int, dewit_archive: Any, dewit_pins: dict[str, Any] | None, failure_time: dict[str, Any] | None
) -> C1Run:
    run_id = f"20261007T000000Z-c1-s{seed % 10**9}"
    w = _Writer(out, run_id, _git_sha())
    stages: list[str] = []

    # real series (optional)
    real_doc: dict[str, Any] | None = None
    real_reason = "the real series was not ingested"
    snr_obs: float | None = None
    if dewit_archive is not None:
        kw: dict[str, Any] = {}
        if dewit_pins:
            kw = {"expected_bytes": dewit_pins["bytes"], "expected_md5": dewit_pins["md5"]}
        try:
            real = dewit.ingest(dewit_archive, failure_time=failure_time, **kw)
            real_doc, snr_obs = real.document, float(real.document["snr_obs"])
        except dewit.DewitRejected as exc:
            real_reason = exc.reason

    # s10_preprocess: the sample section
    section = _sample_section()
    spec_sha = hashlib.sha256(json.dumps(section, sort_keys=True).encode()).hexdigest()
    stages.append("s10_preprocess")
    w.table(
        "c1-section-sample",
        "c1/sections.json",
        {"sections": [section]},
        tool="pitstudio",
        stage="s10_preprocess",
        inputs=[],
        sources=[{"id": "c1-sample-section", "sha256": spec_sha}],
    )

    # s05_synthesize
    cfg = events.default_config(snr_obs)
    base = seed % 100_000
    cfg["n_samples"] = 64
    cfg["splits"] = {
        "train": {"start": base, "count": 24},
        "validation": {"start": base + 100, "count": 6},
        "test": {"start": base + 200, "count_per_stratum": 5},
    }
    stages.append("s05_synthesize")
    docs = synth.synthesize(cfg)
    cfg_sha = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
    w.table(
        "c1-events",
        "c1/events.json",
        {"events": docs},
        tool="pitstudio",
        stage="s05_synthesize",
        inputs=[],
        sources=[{"id": "c1-synth-config", "sha256": cfg_sha}],
    )

    # s20: FoS and PoF
    stages.append("s20_feature_extraction")
    slope_results = stability.analyse([section])
    results.load_results(slope_results, sections={section["section_id"]: section})
    entry = slope_results["sections"][0]
    w.table(
        "c1-fos-table",
        "c1/fos.json",
        {"mode": slope_results["mode"], "section_id": entry["section_id"], "fos": entry["fos"]},
        tool="minephys",
        stage="s20_feature_extraction",
        inputs=["c1-section-sample"],
    )
    w.table(
        "c1-pof-table",
        "c1/pof.json",
        {"section_id": entry["section_id"], "pof": entry["pof"]},
        tool="minephys",
        stage="s20_feature_extraction",
        inputs=["c1-section-sample"],
    )

    # s30_train (CPU)
    stages.append("s30_train")
    train_events = [d for d in docs if d["split"] == "train"]
    contexts, targets = data.training_pairs(train_events)
    models: dict[str, Any] = {}
    reports = []
    for arm in ("tcn", "patchtst"):
        res = train.train_arm(
            arm,
            contexts,
            targets,
            config={"epochs": EPOCHS, "batch_size": 32, "learning_rate": 3e-3},
            seed=seed % 2**31,
        )
        models[arm] = res.model
        reports.append(
            {
                "arm": arm,
                "history": res.history,
                "gpu_hours": {k: v for k, v in res.manifest["gpu_hours"].items() if k != "seconds"},
                "device": res.manifest["device"],
                "note": "trained on the CPU",
            }
        )
    av = chronos.availability()
    chronos_note = {
        "zero_shot": {
            "run": False,
            "reason": chronos.not_run_reason("zero-shot", av) if not av["available"] else "not run at the sample scale",
        },
        "fine_tuned": {"run": False, "reason": "not run at the sample scale (a GPU job trains it)"},
    }
    w.table(
        "c1-training-report",
        "c1/training-report.json",
        {"arms": reports, "budget": "CPU run: 0 GPU-h"},
        tool="pytorch",
        stage="s30_train",
        inputs=["c1-events"],
    )
    exclusion.assert_excluded({"artefacts": w.artefacts}, [real_doc["archive_sha256"]] if real_doc else [])
    w.table(
        "c1-chronos-bolt-status",
        "c1/chronos-bolt-status.json",
        chronos_note,
        tool="pytorch",
        stage="s30_train",
        inputs=["c1-events"],
    )

    # s40_infer
    stages.append("s40_infer")
    forecasters = {arm: infer.TorchForecaster(m) for arm, m in models.items()}
    test_events = [d for d in docs if d["split"] == "test"]
    predictions = data.predict_events(test_events, forecasters, seed=seed % 2**31)
    w.table(
        "c1-forecasts",
        "c1/forecasts.json",
        {"predictions": predictions},
        tool="pytorch",
        stage="s40_infer",
        inputs=["c1-events", "c1-training-report"],
    )

    # real event forecasts
    real_block = ev.real_event_not_run(dewit.EVENT_ID, real_reason)
    if real_doc is not None:
        real_block = _real_event(real_doc, forecasters, seed % 2**31)

    # s50_evaluate
    stages.append("s50_evaluate")
    basis = "observed" if snr_obs is not None else "nominal"
    evaluated = s50.evaluate(
        run_id=run_id,
        snr_basis=basis,
        snr_obs=snr_obs,
        predictions=predictions,
        seeds={"acceptance": seed % 2**31, "comparison": (seed + 1) % 2**31},
        real_event=real_block if real_doc is not None else None,
        fixture=False,
    )
    document = dict(evaluated.document)
    document["real_event"] = real_block
    w.table(
        "c1-metrics", "c1/ttf-results.json", document, tool="pitstudio", stage="s50_evaluate", inputs=["c1-forecasts"]
    )

    # s60_export
    stages.append("s60_export")
    rng = np.random.default_rng(seed)
    golden = contexts[
        rng.choice(len(contexts), size=200, replace=True)
    ].copy()  # 200 golden contexts (training contexts, jittered)
    golden[:, 0] += rng.normal(0.0, 0.01, size=golden[:, 0].shape).astype(np.float32)
    work = out_dir_tmp = Path(w.out) / "c1" / "_export"
    report = export.export_all(
        {arm: {"model": models[arm], "contexts": golden} for arm in ("tcn", "patchtst")},
        out_dir=out_dir_tmp,
        windows={},
        cutoffs=[0.5, 0.8],
    )
    for arm in ("tcn", "patchtst"):
        info = report.arms[arm]
        w.onnx(
            f"c1-{arm}-onnx",
            f"c1/models/{arm}-c1.onnx",
            Path(info["onnx_path"]),
            tool="onnx-runtime",
            stage="s60_export",
            inputs=["c1-training-report", "c1-metrics"],
        )
    for f in work.glob("*"):
        f.unlink()
    work.rmdir()

    manifest = {"run_id": run_id, "artefacts": w.artefacts}
    return C1Run(manifest, out, stages, document, "open")


def _real_event(doc: dict[str, Any], forecasters: dict[str, Any], seed: int) -> dict[str, Any]:
    forecasts: dict[tuple[str, float], dict[str, Any]] = {}
    series = {**doc, "split": "real", "stratum": "snr_obs"}
    for row in data.predict_events([series], forecasters, seed=seed):
        entry = {"outcome": row["outcome"]}
        if "t_hat_f_h" in row:
            entry["t_hat_f_h"] = row["t_hat_f_h"]
        if "reason" in row:
            entry["reason"] = row["reason"]
        forecasts[(row["method"], row["cutoff"])] = entry
    return ev.real_event_report(
        event_id=doc["event_id"], t_0_h=doc["t_0_h"], t_f_h=doc["t_f_h"], snr_obs=doc["snr_obs"], forecasts=forecasts
    )
