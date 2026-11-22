"""The baked acceleration table, DC-016-05 (FR-016-34, FR-016-32, NFR-016-01)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

CAPTION_TEMPLATE = (
    "measured on one RTX 5000 Ada Laptop GPU (power-limited), Windows 11, {date}, {sha} — not a general benchmark"
)
TABLE_MAX_BYTES = 200_000

_ROW_FIELDS = (
    "model",
    "backend",
    "precision",
    "tensorrt_version",
    "status",
    "reason",
    "performance",
    "latency",
    "throughput",
    "joules_per_inference",
    "vram_peak_bytes",
    "thermal_slowdown",
    "camera_streams",
    "parity",
)


class NotComparable(ValueError):
    """Two records cannot be compared (different enforced power limit or source, or no latency numbers)."""


class TableTooLarge(ValueError):
    def __init__(self, nbytes: int, max_bytes: int) -> None:
        super().__init__(f"table of {nbytes} bytes exceeds {max_bytes}")
        self.nbytes = nbytes


def rows_from_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One table row per record, in input order: the record fields plus power limit, source and licence hash."""
    rows = []
    for record in records:
        row = {k: record[k] for k in _ROW_FIELDS if k in record}
        fp = record.get("fingerprint", {})
        row["power_limit_enforced_w"] = fp.get("power_limit_enforced_w")
        row["power_source"] = fp.get("power_source")
        # the licence hash only travels with a record in which a TensorRT library took part
        row["tensorrt_licence_sha256"] = fp.get("tensorrt_licence_sha256") if record.get("tensorrt_version") else None
        if record.get("fixture") is True:
            row["fixture"] = True
        rows.append(row)
    return rows


def publishable(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The `performance == "public"` records that are not contract fixtures, in input order."""
    return [dict(r) for r in records if r.get("performance") == "public" and r.get("fixture") is not True]


def _single(records: Sequence[Mapping[str, Any]], name: str, get: Any) -> Any:
    values = {get(r) for r in records}
    if len(values) != 1:
        raise ValueError(f"records disagree on {name}: {sorted(map(str, values))}")
    return values.pop()


def bake_table(records: Sequence[Mapping[str, Any]], *, generated: str) -> dict[str, Any]:
    """The DC-016-05 document from public records of one run; refuses local-only, mixed or empty input."""
    if not records:
        raise ValueError("no records to bake")
    for r in records:
        if r.get("fixture") is True:
            raise ValueError(f"record {r.get('model')}/{r.get('backend')} is a contract fixture and is never baked")
        if r.get("performance") != "public":
            raise ValueError(f"record {r.get('model')}/{r.get('backend')} is {r.get('performance')}, not public")
    date = _single(records, "date", lambda r: r["date"])
    sha = _single(records, "git_sha", lambda r: r["git_sha"])
    gpu = _single(records, "gpu_name", lambda r: r["fingerprint"]["gpu_name"])
    driver = _single(records, "driver", lambda r: r["fingerprint"]["driver"])
    return {
        "schema_version": "1.0",
        "generated": generated,
        "git_sha": sha,
        "caption": CAPTION_TEMPLATE.format(date=date, sha=sha),
        "conditions": {"gpu_name": gpu, "driver": driver},
        "rows": rows_from_records(records),
    }


def speedup(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    regime: str = "sustained",
    scope: str = "gpu-compute",
    quantile: str = "p50",
) -> float:
    """Baseline latency over candidate latency; only between records with the same power limit and power source."""
    for key in ("power_limit_enforced_w", "power_source"):
        if baseline["fingerprint"].get(key) != candidate["fingerprint"].get(key):
            raise NotComparable(f"records differ in {key}: not comparable (power conditions)")

    def value(record: Mapping[str, Any]) -> float:
        latency = record.get("latency")
        if not isinstance(latency, list):
            raise NotComparable("record has no latency numbers")
        for entry in latency:
            if entry["regime"] == regime and entry["scope"] == scope:
                return float(entry[quantile]["value_ms"])
        raise NotComparable(f"record has no {regime}/{scope} latency")

    return value(baseline) / value(candidate)


def serialise_table(doc: Mapping[str, Any]) -> bytes:
    """Deterministic UTF-8 JSON as written to the web data folder."""
    return json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def check_table_size(doc: Mapping[str, Any], *, max_bytes: int = TABLE_MAX_BYTES) -> int:
    """The serialised size; TableTooLarge above `max_bytes`."""
    size = len(serialise_table(doc))
    if size > max_bytes:
        raise TableTooLarge(size, max_bytes)
    return size
