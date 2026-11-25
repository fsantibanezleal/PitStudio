"""Chart-series outputs of `studio import-run` (FR-002-70, DC-020-05): one JSON file per chart of a published run.

The contract schema (`contracts/chart-series.schema.json`) states shapes, units, labels and caps. This module adds
what a schema cannot state: the byte cap, the case of the import, the agreement of equal-length arrays, the order of
x, the cumulative share of an ECDF, the band around its series, the cells of a raster and the width of a table row.
A problem is a short sentence naming the output; an empty list means the file may be imported.
"""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any

from pitstudio.runner.recipe import first_errors, one_line, strict_json

MAX_BYTES = 524288


def _finite(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


def _series(doc: dict, s: dict, name: str) -> list[str]:
    out: list[str] = []
    sid, n = s["id"], len(s["y"])
    if "x" in s and len(s["x"]) != n:
        out.append(f"{name}: series {sid} has {len(s['x'])} x values and {n} y values")
    out += [
        f"{name}: series {sid}: {k} has {len(s[k])} values, y has {n}"
        for k in ("lo", "hi")
        if k in s and len(s[k]) != n
    ]
    if doc["chart_type"] in ("line", "ecdf") and "x" in s:
        back = next((i for i, (a, b) in enumerate(pairwise(s["x"]), 1) if b < a), None)
        if back is not None:
            out.append(f"{name}: series {sid}: x goes backwards at index {back}")
    if doc["chart_type"] == "ecdf":
        ys = [v for v in s["y"] if v is not None]
        if any(not 0 <= v <= 1 for v in ys) or any(b < a for a, b in pairwise(ys)):
            out.append(f"{name}: series {sid}: an ECDF rises from 0 to 1 and never falls")
    if "lo" in s and "hi" in s and len(s["lo"]) == len(s["hi"]) == n:
        for i, (lo, v, hi) in enumerate(zip(s["lo"], s["y"], s["hi"], strict=True)):
            if None not in (lo, v, hi) and not lo <= v <= hi:
                out.append(f"{name}: series {sid}: lo, y and hi are not ordered at index {i}")
                break
    return out


def semantic_problems(doc: dict, name: str) -> list[str]:
    """Rules of the contract that a JSON schema cannot state (the schema has already accepted the document)."""
    out: list[str] = []
    kind = doc["chart_type"]
    if doc["status"] == "ok":
        for s in doc.get("series", []):
            out += _series(doc, s, name)
        if kind == "bar":
            out += [
                f"{name}: series {s['id']} has {len(s['y'])} values for {len(doc['categories'])} categories"
                for s in doc["series"]
                if len(s["y"]) != len(doc["categories"])
            ]
        if kind == "raster":
            r = doc["raster"]
            if len(r["values"]) != r["nx"] * r["ny"]:
                out.append(f"{name}: the raster has {len(r['values'])} values for {r['nx']} x {r['ny']} cells")
            e, c = r["extent"], r["colour"]
            if not (e["x1"] > e["x0"] and e["y1"] > e["y0"]):
                out.append(f"{name}: the raster extent is empty (x1 must exceed x0 and y1 must exceed y0)")
            if not c["vmax"] > c["vmin"]:
                out.append(f"{name}: the colour scale is empty (vmax must exceed vmin)")
        if kind == "table":
            t = doc["table"]
            for i, row in enumerate(t["rows"]):
                if len(row) != len(t["columns"]):
                    out.append(f"{name}: table row {i} has {len(row)} cells for {len(t['columns'])} columns")
                    continue
                for col, cell in zip(t["columns"], row, strict=True):
                    if cell is not None and (col["type"] == "number") != _finite(cell):
                        out.append(f"{name}: table row {i}, column {col['id']}: a {col['type']} column holds {cell!r}")
                        break
    return out


def check(raw: bytes, case: str, name: str) -> list[str]:
    """Every problem that stops a chart-series file from being imported as an output of `case` (empty when it may)."""
    if len(raw) > MAX_BYTES:
        return [f"{name}: a chart-series file is at most {MAX_BYTES} bytes, this one has {len(raw)}"]
    try:
        doc = strict_json(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, TypeError) as e:
        return [f"{name}: the chart-series file is not strict JSON ({one_line(e, 100)})"]
    if errs := first_errors("chart-series", doc, n=3):
        return [f"{name}: not a valid chart series: {'; '.join(errs)}"]
    if doc["case"] != case:
        return [f"{name}: the chart is of case {doc['case']}, the import is of case {case}"]
    return semantic_problems(doc, name)
