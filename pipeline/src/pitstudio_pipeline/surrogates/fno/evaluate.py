"""FNO held-out evaluation (s50_evaluate; FR-011-35, FR-011-42, SC-011-03, FR-011-49, FR-011-50).

Per held-out scenario and per output field the relative L2 error ||u_hat - u||_2 / ||u||_2 on the grid in physical
units, its mean over
the scenarios and its 90th percentile (an empty solver field, norm below 1e-9, is excluded and counted), the tailings
KPI errors
(inundated area at h_thr, arrival time at the checkpoint cells, maximum depth, relative volume error of each h(t_k)),
the dust
receptor concentration errors, and the resolution-transfer evaluation at 128 x 128 (labelled "not claimed"). SC-011-03
is the mean
relative L2 of h_max (tailings) or of the time-averaged concentration (dust) against `models.fno_rel_l2_mean_max`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from pitstudio_pipeline.surrogates.errors import EvaluationError
from pitstudio_pipeline.surrogates.fixture import is_fixture, stamp
from pitstudio_pipeline.surrogates.thresholds import model_threshold

EMPTY_NORM = 1e-9
NOT_RUN = "not run (absent)"
TRANSFER_LABEL = "resolution transfer — not claimed"
SC_FIELD = {"tailings": "depth_max", "dust": "concentration_mean"}
N_SNAPSHOTS = 8


def relative_l2(pred: np.ndarray, truth: np.ndarray) -> float:
    """||pred - truth||_2 / ||truth||_2; an empty truth (norm below 1e-9) has no relative error and is refused."""
    p, t = np.asarray(pred, dtype=np.float64), np.asarray(truth, dtype=np.float64)
    if p.shape != t.shape:
        raise EvaluationError(f"prediction and truth must have the same shape, got {list(p.shape)} and {list(t.shape)}")
    norm = float(np.linalg.norm(t))
    if norm < EMPTY_NORM:
        raise EvaluationError(f"the solver field is empty (norm {norm:.3g} below {EMPTY_NORM}): no relative L2")
    return float(np.linalg.norm(p - t) / norm)


def _check_sets(preds: np.ndarray, truths: np.ndarray, names: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    p, t = np.asarray(preds, dtype=np.float64), np.asarray(truths, dtype=np.float64)
    if p.ndim != 4 or p.shape != t.shape:
        raise EvaluationError(
            f"preds and truths must be [S, C, H, W] arrays of one shape, got {list(p.shape)} and {list(t.shape)}"
        )
    if p.shape[0] < 1:
        raise EvaluationError("no scenario to evaluate")
    if p.shape[1] != len(names):
        raise EvaluationError(f"{p.shape[1]} channels but {len(names)} field names")
    if not (np.isfinite(p).all() and np.isfinite(t).all()):
        raise EvaluationError("predictions or truths contain a non-finite value")
    return p, t


def _field_stats(p: np.ndarray, t: np.ndarray) -> dict[str, Any]:
    per: list[float | None] = []
    for s in range(p.shape[0]):
        if float(np.linalg.norm(t[s])) < EMPTY_NORM:
            per.append(None)
        else:
            per.append(relative_l2(p[s], t[s]))
    included = [v for v in per if v is not None]
    return {
        "per_scenario": per,
        "mean": float(np.mean(included)) if included else None,
        "p90": float(np.percentile(included, 90)) if included else None,
        "n_included": len(included),
        "n_excluded_empty": len(per) - len(included),
    }


def evaluate_fno(
    preds: np.ndarray,
    truths: np.ndarray,
    field_names: Sequence[str],
    *,
    model: str,
    patch_ids: Sequence[str] | None = None,
    expected_patches: Sequence[str] | None = None,
    dataset_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Relative L2 per field over the held-out scenarios and the SC-011-03 verdict (None for a partial set)."""
    fixture = is_fixture(dataset_manifest)
    if model not in SC_FIELD:
        raise EvaluationError(f"model must be 'tailings' or 'dust', got {model!r}")
    p, t = _check_sets(preds, truths, field_names)
    missing: list[dict[str, str]] = []
    if patch_ids is not None:
        if len(patch_ids) != p.shape[0]:
            raise EvaluationError(f"{len(patch_ids)} patch ids for {p.shape[0]} scenarios")
        if expected_patches is not None:
            unexpected = [i for i in patch_ids if i not in set(expected_patches)]
            if unexpected:
                raise EvaluationError(f"patch {unexpected[0]!r} is not among the expected held-out patches")
            present = set(patch_ids)
            missing = [{"patch_id": i, "status": NOT_RUN} for i in expected_patches if i not in present]
    elif expected_patches is not None:
        raise EvaluationError("expected_patches needs the patch id of every scenario (patch_ids)")
    fields = {name: _field_stats(p[:, c], t[:, c]) for c, name in enumerate(field_names)}
    sc_field = SC_FIELD[model]
    if sc_field not in fields:
        raise EvaluationError(f"the field {sc_field!r} that decides SC-011-03 is not among the evaluated fields")
    limit = float(model_threshold("fno_rel_l2_mean_max"))
    mean = fields[sc_field]["mean"]
    complete = not missing
    verdict = None if (not complete or mean is None) else ("pass" if mean <= limit else "fail")
    report: dict[str, Any] = {
        "model": model,
        "n_scenarios": int(p.shape[0]),
        "fields": fields,
        "sc_field": sc_field,
        "threshold": limit,
        "sc_011_03": verdict,
        "status": "complete" if complete else "partial",
        "missing_patches": missing,
    }
    return stamp(report, dataset_manifest) if fixture else report


# ------------------------------------------------------------------ KPIs (FR-011-35)


def _positive(name: str, value: float) -> float:
    if not isinstance(value, int | float | np.floating) or not math.isfinite(value) or value <= 0:
        raise EvaluationError(f"{name} must be a positive finite number, got {value!r}")
    return float(value)


def _cells(checkpoints: Sequence[tuple[int, int]], shape: tuple[int, int]) -> list[tuple[int, int]]:
    out = []
    for row, col in checkpoints:
        if not (0 <= row < shape[0] and 0 <= col < shape[1]):
            raise EvaluationError(f"checkpoint {(row, col)} lies outside the {shape[0]} x {shape[1]} grid")
        out.append((int(row), int(col)))
    return out


def _first_arrival(series: np.ndarray, h_thr: float, times: Sequence[float]) -> float | None:
    for value, time in zip(series, times, strict=True):
        if value >= h_thr:
            return float(time)
    return None


def _scalar_error(pred: float, truth: float) -> dict[str, float | None]:
    return {
        "pred": float(pred),
        "truth": float(truth),
        "abs_error": float(abs(pred - truth)),
        "rel_error": float(abs(pred - truth) / abs(truth)) if truth != 0 else None,
    }


def tailings_kpi_errors(
    pred: np.ndarray,
    truth: np.ndarray,
    *,
    cell_size_m: float,
    h_thr_m: float,
    checkpoints: Sequence[tuple[int, int]],
    t_end_s: float,
) -> dict[str, Any]:
    """KPI errors of one scenario: pred and truth are [9, H, W] (h(t_1 ... t_8), h_max)."""
    p, t = np.asarray(pred, dtype=np.float64), np.asarray(truth, dtype=np.float64)
    if p.ndim != 3 or p.shape != t.shape or p.shape[0] != N_SNAPSHOTS + 1:
        raise EvaluationError(
            f"pred and truth must be [9, H, W] arrays of one shape, got {list(p.shape)} and {list(t.shape)}"
        )
    if not (np.isfinite(p).all() and np.isfinite(t).all()):
        raise EvaluationError("predictions or truths contain a non-finite value")
    cell = _positive("cell_size_m", cell_size_m)
    thr = _positive("h_thr_m", h_thr_m)
    end = _positive("t_end_s", t_end_s)
    cells = _cells(checkpoints, p.shape[1:])
    times = [k * end / N_SNAPSHOTS for k in range(1, N_SNAPSHOTS + 1)]
    area_p = float((p[N_SNAPSHOTS] >= thr).sum() * cell * cell)
    area_t = float((t[N_SNAPSHOTS] >= thr).sum() * cell * cell)
    arrivals = []
    for r, c in cells:
        a_p, a_t = _first_arrival(p[:N_SNAPSHOTS, r, c], thr, times), _first_arrival(t[:N_SNAPSHOTS, r, c], thr, times)
        arrivals.append(
            {
                "checkpoint": (r, c),
                "pred": a_p,
                "truth": a_t,
                "abs_error": None if a_p is None or a_t is None else float(abs(a_p - a_t)),
            }
        )
    volumes = []
    for k in range(N_SNAPSHOTS):
        v_t = float(t[k].sum() * cell * cell)
        v_p = float(p[k].sum() * cell * cell)
        volumes.append(float(abs(v_p - v_t) / v_t) if v_t > 0 else None)
    return {
        "area_m2": _scalar_error(area_p, area_t),
        "arrival_time_s": arrivals,
        "max_depth_m": _scalar_error(float(p[N_SNAPSHOTS].max()), float(t[N_SNAPSHOTS].max())),
        "volume_rel_error": volumes,
    }


def dust_kpi_errors(pred: np.ndarray, truth: np.ndarray, *, receptors: Sequence[tuple[int, int]]) -> dict[str, Any]:
    """Concentration error at each receptor cell; pred and truth are [1, H, W] (the time-averaged concentration)."""
    p, t = np.asarray(pred, dtype=np.float64), np.asarray(truth, dtype=np.float64)
    if p.ndim != 3 or p.shape != t.shape or p.shape[0] != 1:
        raise EvaluationError(
            f"pred and truth must be [1, H, W] arrays of one shape, got {list(p.shape)} and {list(t.shape)}"
        )
    if not (np.isfinite(p).all() and np.isfinite(t).all()):
        raise EvaluationError("predictions or truths contain a non-finite value")
    out = []
    for r, c in _cells(receptors, p.shape[1:]):
        entry = _scalar_error(float(p[0, r, c]), float(t[0, r, c]))
        out.append({"receptor": (r, c), **entry})
    return {"receptors": out}


# ------------------------------------------------------------------ resolution transfer (FR-011-42)


def evaluate_resolution_transfer(
    predict: Callable[[np.ndarray], np.ndarray], inputs: np.ndarray, truths: np.ndarray, field_names: Sequence[str]
) -> dict[str, Any]:
    """Relative L2 of the model evaluated on refined 128 x 128 inputs against 128 x 128 solver runs; no verdict."""
    t = np.asarray(truths, dtype=np.float64)
    if t.ndim != 4 or t.shape[-2:] != (128, 128):
        raise EvaluationError(f"resolution transfer needs 128 x 128 solver fields, got {list(t.shape)}")
    preds = np.asarray(predict(inputs), dtype=np.float64)
    p, t = _check_sets(preds, t, field_names)
    return {
        "label": TRANSFER_LABEL,
        "fields": {name: {"mean": _field_stats(p[:, c], t[:, c])["mean"]} for c, name in enumerate(field_names)},
    }
