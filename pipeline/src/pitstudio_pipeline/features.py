"""s20_feature_extraction (spec 008): causal window features, split-fitted transforms, frozen image embeddings.

Window features are computed per record and causally: the feature stamped at sample i uses only samples 0 ... i. A
normaliser is fitted on the training pool of one fold of a split and stored with that split's id (FR-008-42).
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from pitstudio_pipeline.download.hashing import sha256_file
from pitstudio_pipeline.errors import IngestionRejected
from pitstudio_pipeline.ingest.report import build_report, relative_to_root, violation
from pitstudio_pipeline.ingest.series import series_violations
from pitstudio_pipeline.ingest.tables import write_parquet
from pitstudio_pipeline.paths import check_data_root

STAGE = "s20_feature_extraction"
FEATURE_NAMES = ("displacement", "velocity", "velocity_ratio")


# --------------------------------------------------------------------------------------------- window features
def _window_violations(windows: Sequence[int], n: int, file: str) -> list[dict[str, Any]]:
    found = []
    for index, w in enumerate(windows):
        if isinstance(w, bool) or not isinstance(w, int | np.integer) or w <= 0:
            found.append(
                violation(file, "windows", "window length is a positive integer", row=index, value=w, expected="> 0")
            )
    if not found and windows and n < max(windows):
        found.append(
            violation(
                file,
                "x",
                "at least as many samples as the longest window",
                value=n,
                expected=f">= {max(windows)} samples",
            )
        )
    return found


def window_features(
    t: Sequence[float] | np.ndarray,
    x: Sequence[float] | np.ndarray,
    *,
    windows: Sequence[int],
    step: int = 1,
    features: Sequence[str],
    series: str = "series",
    file: str | None = None,
) -> dict[str, np.ndarray]:
    """Causal window features of a displacement series (FR-008-39).

    Windows are counts of samples; L is the longest. For every stamp index i = L - 1, L - 1 + step, ... and every window
    w, the window is the samples i - w + 1 ... i and `displacement_w<w>` = x[i] - x[i-w+1], `velocity_w<w>` =
    displacement / (t[i] - t[i-w+1]), `velocity_ratio_w<w>` = `velocity_w<w>` / `velocity_w<L>` (NaN where the longest
    velocity is zero); `t` holds the stamps. Only the requested features are returned, all float64. A hostile series
    raises `IngestionRejected` naming the series and the first offending index (FR-008-48).
    """
    if isinstance(step, bool) or not isinstance(step, int | np.integer) or step < 1:
        raise ValueError("step must be a positive integer")
    unknown = [f for f in features if f not in FEATURE_NAMES]
    if unknown:
        raise ValueError(f"unknown feature(s): {', '.join(unknown)}")
    name = file if file is not None else series
    found = series_violations(t, x, series=series, file=name)
    found += _window_violations(list(windows), len(np.atleast_1d(np.asarray(t, dtype=float))), name)
    if not windows:
        found.append(violation(name, "windows", "at least one window", expected="a non-empty list of windows"))
    if found:
        raise IngestionRejected(found)
    times, values = np.asarray(t, dtype=float), np.asarray(x, dtype=float)
    longest = int(max(windows))
    stamps = np.arange(longest - 1, times.size, step)
    out: dict[str, np.ndarray] = {"t": times[stamps].astype(np.float64)}
    displacement, velocity = {}, {}
    for w in windows:
        start = stamps - (int(w) - 1)
        displacement[int(w)] = values[stamps] - values[start]
        velocity[int(w)] = displacement[int(w)] / (times[stamps] - times[start])
    for w in windows:
        w = int(w)
        if "displacement" in features:
            out[f"displacement_w{w}"] = displacement[w].astype(np.float64)
        if "velocity" in features:
            out[f"velocity_w{w}"] = velocity[w].astype(np.float64)
        if "velocity_ratio" in features:
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = velocity[w] / velocity[longest]
            out[f"velocity_ratio_w{w}"] = np.where(velocity[longest] == 0.0, np.nan, ratio).astype(np.float64)
    return out


def run_series_stage(
    path: Path | str,
    *,
    windows: Sequence[int],
    step: int,
    features: Sequence[str],
    source: str,
    data_root: Path | str,
    run_id: str,
    now: Callable[[], dt.datetime],
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Validate one series file (`{"t": [...], "x": [...]}`), compute its window features and report (DC-008-03)."""
    root = check_data_root(data_root, repo_root=repo_root)
    path = Path(path)
    rel = relative_to_root(root, path)
    entry: dict[str, Any] = {
        "path": rel,
        "sha256": sha256_file(path),
        "validator": "series",
        "schema_name": "series_window_features",
        "status": "accepted",
        "records": None,
    }
    outputs: list[dict[str, str]] = []
    try:
        document = json.loads(path.read_bytes().decode("utf-8"))
        t, x = document["t"], document["x"]
        entry["records"] = len(t)
        table = window_features(t, x, windows=windows, step=step, features=features, file=rel)
    except IngestionRejected as exc:
        entry["status"], found = "rejected", exc.violations
    except (OSError, ValueError, KeyError, TypeError) as exc:
        entry["status"] = "rejected"
        found = [
            violation(rel, "file", "a JSON document with `t` and `x`", field_kind="property", value=type(exc).__name__)
        ]
    else:
        found = []
        out = root / "processed" / source / f"{path.stem}.features.parquet"
        outputs.append(write_parquet(pl.DataFrame(table), out, root))
    return build_report(
        source=source, stage=STAGE, run_id=run_id, now=now(), files=[entry], violations=found, outputs=outputs
    )


# ---------------------------------------------------------------------------------- split-fitted transforms
@dataclass(frozen=True)
class Normaliser:
    """A per-column z-score fitted on the training pool of one fold of one split (FR-008-42)."""

    mean: np.ndarray
    std: np.ndarray
    split_id: str
    fold: int

    def transform(self, x: np.ndarray) -> np.ndarray:
        """(X - mean) / std; a constant column (std = 0) is only centred."""
        scale = np.where(self.std == 0.0, 1.0, self.std)
        return (np.asarray(x, dtype=float) - self.mean) / scale


def fit_normaliser(x: np.ndarray, record_ids: Sequence[str], split: Mapping[str, Any], fold: int) -> Normaliser:
    """Fit mean and standard deviation (ddof = 0) on the rows of `x` whose record is in the fold's training pool.

    The rows of the fold's test records are ignored, so nothing is ever fitted on test data. `record_ids` names the
    record of each row and must all belong to the split.
    """
    matrix = np.asarray(x, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != len(record_ids):
        raise ValueError("X must be (n_records, n_features) with one row per record id")
    folds = split["folds"]
    if isinstance(fold, bool) or not isinstance(fold, int) or not 0 <= fold < len(folds):
        raise ValueError(f"fold {fold!r} does not exist in the split")
    known = {m for g in split["groups"] for m in g["members"]}
    unknown = [r for r in record_ids if r not in known]
    if unknown:
        raise ValueError(f"record {unknown[0]!r} is not in the split")
    pool = set(folds[fold]["train_pool"])
    rows = [i for i, r in enumerate(record_ids) if r in pool]
    if not rows:
        raise ValueError("no row belongs to the training pool of this fold")
    train = matrix[rows]
    return Normaliser(train.mean(axis=0), train.std(axis=0, ddof=0), str(split["id"]), fold)
