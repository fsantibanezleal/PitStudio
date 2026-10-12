"""The displacement-series validator shared by real data, synthetic data and feature extraction (FR-008-34, FR-008-48).

A series is two arrays: sample times `t` (strictly increasing, finite) and displacements `x` (finite). The first
offending index of each broken rule is reported; nothing is repaired.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from pitstudio_pipeline.errors import IngestionRejected
from pitstudio_pipeline.ingest.report import safe_relpath, violation


def series_violations(
    t: Sequence[float] | np.ndarray, x: Sequence[float] | np.ndarray, *, series: str, file: str | None = None
) -> list[dict[str, Any]]:
    """Report violations of a series: length mismatch, non-finite values, non-increasing timestamps (first of each).

    `file` is the report path of the series when it lives in a file; by default it is derived from the series name.
    """
    file = file if file is not None else safe_relpath(series)
    found: list[dict[str, Any]] = []
    try:
        times, values = np.asarray(t, dtype=float), np.asarray(x, dtype=float)
    except TypeError, ValueError:
        return [violation(file, "x", "numeric samples", field_kind="column", expected="finite numbers")]
    if times.ndim != 1 or values.ndim != 1:
        return [violation(file, "x", "one-dimensional arrays", field_kind="column", expected="1-D arrays")]
    if times.shape != values.shape:
        found.append(
            violation(
                file,
                "x",
                "same length as t",
                field_kind="column",
                value=int(values.size),
                expected=f"{times.size} samples",
            )
        )
    for name, array in (("t", times), ("x", values)):
        bad = np.flatnonzero(~np.isfinite(array))
        if bad.size:
            i = int(bad[0])
            found.append(
                violation(file, name, "finite value", row=i, value=float(array[i]), expected="a finite number")
            )
    finite = np.isfinite(times)
    steps = np.flatnonzero(finite[1:] & finite[:-1] & (np.diff(times) <= 0))
    if steps.size:
        i = int(steps[0]) + 1
        found.append(
            violation(
                file,
                "t",
                "strictly increasing timestamps",
                row=i,
                value=float(times[i]),
                expected=f"> {float(times[i - 1])!r}",
            )
        )
    found.sort(key=lambda v: (v["row"] is None, v["row"] if v["row"] is not None else -1, v["field"]))
    return found


def validate_series(
    t: Sequence[float] | np.ndarray, x: Sequence[float] | np.ndarray, *, series: str, file: str | None = None
) -> None:
    """Return None for a valid series; raise `IngestionRejected` naming the series and the first offending index."""
    found = series_violations(t, x, series=series, file=file)
    if found:
        raise IngestionRejected(found)
