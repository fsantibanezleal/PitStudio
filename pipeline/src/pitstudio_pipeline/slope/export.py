"""ONNX export of the C1 forecasters with parity and the Chronos-Bolt fallback (FR-010-30, FR-010-31, SC-010-04,
DC-010-05).

``export_forecaster`` exports the forecasting graph of one 64-step block (input ``context`` float32 [1, 2, 128], output
``quantiles`` float32 [1, 9, 64]) at opset 17 with IR version 10 by the dynamo exporter, then checks ONNX Runtime CPU
fp32
against PyTorch fp32 on the golden contexts (``models.onnx_cpu_fp32`` of thresholds.yaml). ``export_all`` keeps TCN and
PatchTST live; Chronos-Bolt fine-tuned whose export raises or misses parity becomes PRECOMPUTE with its forecasts
baked for
every published event at every cut-off of the grid; the zero-shot arm is published as baked forecasts only.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from torch import nn

from pitstudio.slope import forecast, preprocess
from pitstudio.slope.errors import InvalidWindowError
from pitstudio_pipeline.slope import infer

ARMS = ("tcn", "patchtst", "chronos_bolt_fine_tuned")
_THRESHOLDS = Path(__file__).resolve().parents[4] / "specs" / "000-foundation" / "thresholds.yaml"
MIN_CONTEXTS = 200


class ParityError(ValueError):
    """The exported graph misses ONNX Runtime versus PyTorch parity."""


@dataclass
class ExportResult:
    onnx_path: Path
    size_bytes: int
    io: dict[str, Any]
    parity: dict[str, Any]


@dataclass
class ExportReport:
    arms: dict[str, dict[str, Any]] = field(default_factory=dict)
    model_card_notes: list[str] = field(default_factory=list)


def _thresholds() -> dict[str, float]:
    th = yaml.safe_load(_THRESHOLDS.read_text(encoding="utf-8"))["models"]["onnx_cpu_fp32"]
    return {"rtol": th["rtol"], "atol": th["atol"], "max_abs": th["max_abs"]}


def check_parity(
    torch_fn: Callable[[np.ndarray], np.ndarray], ort_fn: Callable[[np.ndarray], np.ndarray], contexts: np.ndarray
) -> dict[str, Any]:
    """Run both back ends on every context (shape (1, 2, 128) each) and compare them against the thresholds."""
    th = _thresholds()
    max_abs, excess = 0.0, -np.inf
    for i in range(len(contexts)):
        c = np.ascontiguousarray(contexts[i : i + 1])
        want, got = np.asarray(torch_fn(c), dtype=np.float32), np.asarray(ort_fn(c), dtype=np.float32)
        diff = np.abs(got.astype(np.float64) - want.astype(np.float64))
        max_abs = max(max_abs, float(diff.max()))
        excess = max(excess, float((diff - (th["atol"] + th["rtol"] * np.abs(want))).max()))
    return {
        "n_contexts": len(contexts),
        "max_abs": max_abs,
        "max_rel_excess": excess,
        "passed": bool(excess <= 0.0 and max_abs <= th["max_abs"]),
        "thresholds": th,
    }


def _check_contexts(contexts: Any) -> np.ndarray:
    arr = contexts
    if not isinstance(arr, np.ndarray) or arr.dtype != np.float32 or arr.ndim != 3 or arr.shape[1:] != (2, 128):
        raise ValueError("golden contexts must be a float32 array of shape (N, 2, 128)")
    if len(arr) < MIN_CONTEXTS:
        raise ValueError(f"at least {MIN_CONTEXTS} golden contexts are needed, got {len(arr)}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("golden contexts must be finite")
    return arr


def _io_description(arm: str, path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    model_id = f"{arm.replace('_', '-')}-c1"
    return {
        "model_id": model_id,
        "engine": "forecasters",
        "cases": ["C1"],
        "onnx": {
            "path": f"web/public/models/{path.name}",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        },
        "opset": 17,
        "ir_version": 10,
        "precision": "fp32",
        "delivery": "live",
        "constants": {"context_length": 128, "block_mean_width": 4, "horizon_steps": 64, "max_blocks": 4},
        "inputs": [
            {
                "name": "context",
                "dtype": "float32",
                "shape": [1, 2, 128],
                "unit": "per-channel",
                "channel_axis": 1,
                "channels": [
                    {
                        "name": "inverse_velocity",
                        "unit": "h/mm",
                        "normalisation": {"rule": "context-mean-abs", "applied_in_graph": False},
                    },
                    {"name": "mask", "unit": "1"},
                ],
            }
        ],
        "outputs": [
            {
                "name": "quantiles",
                "dtype": "float32",
                "shape": [1, 9, 64],
                "unit": "h/mm",
                "quantile_axis": 1,
                "quantiles": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
                "normalisation": {"rule": "context-mean-abs", "applied_in_graph": False},
            }
        ],
        "training_envelope": {
            "voight_alpha": {"min": 1.7, "max": 2.3, "unit": "1"},
            "terminal_duration": {"min": 24, "max": 720, "unit": "h"},
            "onset_velocity": {"min": 0.004167, "max": 0.4167, "unit": "mm/h"},
        },
    }


def export_forecaster(model: nn.Module, arm: str, out_dir: str | Path, *, golden_contexts: Any) -> ExportResult:
    """Export one forecaster and check its parity (see the module docstring)."""
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {list(ARMS)}, got {arm!r}")
    ctx = _check_contexts(golden_contexts)
    import onnx
    import onnxruntime as ort

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{arm}-c1.onnx"
    model = model.eval().cpu()
    program = torch.onnx.export(
        model, (torch.zeros(1, 2, 128),), None, opset_version=17, input_names=["context"], output_names=["quantiles"],
        dynamo=True, verify=True,
    )  # fmt: skip
    proto = program.model_proto
    proto.ir_version = 10
    onnx.save(proto, str(path))
    onnx.checker.check_model(onnx.load(str(path)))
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])

    def torch_fn(c: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            return model(torch.from_numpy(c)).numpy()

    parity = check_parity(torch_fn, lambda c: session.run(None, {"context": c})[0], ctx)
    if not parity["passed"]:
        raise ParityError(f"parity missed: max abs {parity['max_abs']:.3g}")
    return ExportResult(path, path.stat().st_size, _io_description(arm, path), parity)


def _bake(model: nn.Module, windows: Mapping[str, preprocess.Window], cutoffs: list[float], path: Path) -> Path:
    forecaster = infer.TorchForecaster(model.eval())
    baked: dict[str, dict[str, Any]] = {}
    for event_id, w in windows.items():
        per: dict[str, Any] = {}
        for c in cutoffs:
            t_c = float(w.t[0] + c * (w.t[-1] - w.t[0]))
            try:
                sub = preprocess.preprocess_window(w.t, w.omega, t_c)
                f = forecast.learned_forecast(forecaster, sub)
                per[str(c)] = {
                    "outcome": f.outcome,
                    "t_hat_f_h": f.t_hat_f,
                    "scored_at_cap": f.scored_at_cap,
                    "interval_80_h": {"lower_h": f.interval_80[0], "upper_h": f.interval_80[1]},
                }
            except InvalidWindowError as exc:
                per[str(c)] = {"outcome": "no forecast", "reason": str(exc)}
        baked[event_id] = per
    path.write_text(json.dumps(baked, indent=2), encoding="utf-8")
    return path


def export_all(
    jobs: Mapping[str, Mapping[str, Any]],
    *,
    out_dir: str | Path,
    windows: Mapping[str, preprocess.Window],
    cutoffs: list[float],
) -> ExportReport:
    """Export every arm of ``jobs`` (see the module docstring); the report lists the lane of each and the card notes."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = ExportReport()
    for arm, job in jobs.items():
        model = job.get("model")
        if arm == "chronos_bolt_zero_shot":
            reason = "the zero-shot arm is published as baked forecasts only"
            baked = _bake(model, windows, cutoffs, out / f"{arm}-baked.json") if model is not None else None
            report.arms[arm] = {
                "lane": "PRECOMPUTE",
                "reason": reason,
                "onnx_path": None,
                "baked_path": str(baked) if baked else None,
            }
            report.model_card_notes.append(f"{arm}: {reason}")
            continue
        exporter = job.get("exporter", export_forecaster)
        try:
            res = exporter(model, arm, out, golden_contexts=job["contexts"])
        except Exception as exc:
            if arm != "chronos_bolt_fine_tuned":
                raise
            baked_path = _bake(model, windows, cutoffs, out / f"{arm}-baked.json")
            report.arms[arm] = {
                "lane": "PRECOMPUTE",
                "reason": str(exc),
                "onnx_path": None,
                "baked_path": str(baked_path),
            }
            report.model_card_notes.append(f"{arm}: {exc}")
            continue
        report.arms[arm] = {"lane": "LIVE", "reason": None, "onnx_path": str(res.onnx_path), "baked_path": None}
    return report
