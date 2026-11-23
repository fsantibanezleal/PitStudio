"""Builders and checks of chart-series documents (DC-020-05, contracts/chart-series.schema.json).

A chart-series file is the only way a computed number reaches the Charts tab: one JSON file per chart with its series,
axes, units and the producer (tool, method, version, label) of the run. The builders below only shape numbers that the
caller computed; `validate` refuses a document that the contract or its size cap refuses.
"""
# ruff: noqa: E501, PERF401

from __future__ import annotations

import json
import math
from itertools import pairwise
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

MAX_BYTES = 524288
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "chart-series.schema.json"


def bi(en: str, es: str) -> dict[str, str]:
    return {"en": en, "es": es}


def producer(tool: str, method: str, version: str, label: str) -> dict[str, str]:
    return {"tool": tool, "method": method, "version": version, "label": label}


def axis(en: str, es: str, unit: str, scale: str | None = None) -> dict[str, Any]:
    return {"label": bi(en, es), "unit": unit, **({"scale": scale} if scale else {})}


def _clean(values: Any) -> list[float | None]:
    out: list[float | None] = []
    for v in values:
        f = None if v is None else float(v)
        out.append(None if f is not None and not math.isfinite(f) else f)
    return out


def series(
    sid: str,
    label: dict[str, str],
    x: Any,
    y: Any,
    *,
    draw: str | None = None,
    n: int | None = None,
    lo: Any = None,
    hi: Any = None,
    band_label: dict[str, str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"id": sid, "label": label, "y": _clean(y)}
    if x is not None:
        out["x"] = [float(v) for v in x]
    if draw:
        out["draw"] = draw
    if n is not None:
        out["n"] = int(n)
    if lo is not None:
        out["lo"], out["hi"] = _clean(lo), _clean(hi)
        if band_label:
            out["band_label"] = band_label
    return out


def chart(
    cid: str,
    case: str,
    chart_type: str,
    title: dict[str, str],
    prod: dict[str, str],
    serves: list[str],
    *,
    caption: dict[str, str] | None = None,
    **parts: Any,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": "1.0",
        "kind": "chart-series",
        "id": cid,
        "case": case,
        "chart_type": chart_type,
        "status": "ok",
        "title": title,
        "producer": prod,
        "serves": serves,
    }
    if caption:
        doc["caption"] = caption
    doc.update({k: v for k, v in parts.items() if v is not None})
    return doc


def not_run(
    cid: str,
    case: str,
    chart_type: str,
    title: dict[str, str],
    prod: dict[str, str],
    serves: list[str],
    reason: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "chart-series",
        "id": cid,
        "case": case,
        "chart_type": chart_type,
        "status": "not-run",
        "title": title,
        "producer": prod,
        "serves": serves,
        "not_run_reason": reason,
    }


def problems(doc: dict[str, Any]) -> list[str]:
    """Schema errors, the byte cap, array lengths and the order of x of one document; empty means it may be published."""
    out = [
        f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"[:200]
        for e in Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))).iter_errors(doc)
    ]
    size = len(json.dumps(doc, indent=1, sort_keys=True, allow_nan=False).encode("utf-8"))
    if size > MAX_BYTES:
        out.append(f"{size} bytes exceed the cap of {MAX_BYTES}")
    if doc.get("status") == "ok":
        for s in doc.get("series", []):
            n = len(s["y"])
            for key in ("x", "lo", "hi"):
                if key in s and len(s[key]) != n:
                    out.append(f"series {s['id']}: {key} has {len(s[key])} values, y has {n}")
            if doc["chart_type"] in ("line", "ecdf") and "x" in s and any(b < a for a, b in pairwise(s["x"])):
                out.append(f"series {s['id']}: x goes backwards")
        if doc["chart_type"] == "bar":
            out += [
                f"series {s['id']}: {len(s['y'])} values for {len(doc['categories'])} categories"
                for s in doc["series"]
                if len(s["y"]) != len(doc["categories"])
            ]
    return out


def write(doc: dict[str, Any], folder: Path) -> Path:
    """Validate and write `<id>.json` into `folder`; raises ValueError listing the problems."""
    found = problems(doc)
    if found:
        raise ValueError(f"chart {doc.get('id')!r} is refused: " + "; ".join(found[:6]))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{doc['id']}.json"
    path.write_text(json.dumps(doc, indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return path
