"""Profile mode of the Warp-based studio stages (FR-006-20, FR-006-21; DC-006-03).

When the runner profiles a stage (`PITSTUDIO_PROFILE=1`) the stage times Warp kernel activity and writes a Chrome
trace and a table of the 20 kernels with the largest total time into its output folder, labelled "kernel timing,
no admin rights". Nsight tools are never launched by this module: it starts no process.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..media.errors import ProfileInvalid

MAX_TRACE_BYTES = 100_000_000
MAX_TABLE_BYTES = 100_000
LABEL = "kernel timing, no admin rights"
TABLE_ROWS = 20
SCHEMA_VERSION = "1.0"
_BAD_CHARS = re.compile(r"[^A-Za-z0-9_.:-]")


def profile_enabled(env: Mapping[str, str] | None = None) -> bool:
    """`PITSTUDIO_PROFILE`: unset or `0` is off, `1` is on, anything else is `profile-invalid`."""
    value = (os.environ if env is None else env).get("PITSTUDIO_PROFILE")
    if value is None or value == "0":
        return False
    if value == "1":
        return True
    raise ProfileInvalid(f"PITSTUDIO_PROFILE must be 0 or 1, got {value[:20]!r}")


def sanitise_kernel_name(name: str) -> str:
    clean = _BAD_CHARS.sub("_", str(name))
    if not clean or not re.match(r"[A-Za-z_]", clean):
        clean = "_" + clean
    return clean[:200]


class KernelProfile:
    def __init__(
        self,
        output_dir: Path,
        *,
        stage: dict,
        warp: Any,
        env: Mapping[str, str] | None = None,
        device: str = "cuda",
        run_id: str | None = None,
        max_trace_bytes: int = MAX_TRACE_BYTES,
    ) -> None:
        self.enabled = profile_enabled(env)
        if (
            isinstance(max_trace_bytes, bool)
            or not isinstance(max_trace_bytes, int)
            or not 0 < max_trace_bytes <= MAX_TRACE_BYTES
        ):
            raise ValueError(f"max_trace_bytes must be in 1..{MAX_TRACE_BYTES}")
        self.output_dir, self.stage, self.warp, self.device = Path(output_dir), stage, warp, device
        self.run_id, self.max_trace_bytes = run_id, max_trace_bytes
        self.summary: dict | None = None
        self.trace_path: Path | None = None
        self.summary_path: Path | None = None

    def __enter__(self) -> KernelProfile:
        if self.enabled:
            self.warp.timing_begin(cuda_filter=self.warp.TIMING_KERNEL)
        return self

    def __exit__(self, *exc: object) -> bool:
        if self.enabled:
            self._write(self.warp.timing_end())
        return False

    def _write(self, results: list) -> None:
        folder = self.output_dir / "profile"
        folder.mkdir(parents=True, exist_ok=True)
        launches = [(sanitise_kernel_name(r.name), float(r.elapsed)) for r in results]
        head, tail = '{"traceEvents":[', "]}"
        chunks: list[str] = []
        size, ts, truncated = len(head) + len(tail), 0.0, False
        for name, ms in launches:
            event = {"name": name, "cat": "kernel", "ph": "X", "ts": ts, "dur": ms * 1000.0, "pid": 1, "tid": 1}
            text = json.dumps(event, separators=(",", ":"))
            cost = len(text) + (1 if chunks else 0)
            if size + cost > self.max_trace_bytes:
                truncated = True
                break
            chunks.append(text)
            size += cost
            ts += ms * 1000.0
        trace = folder / "trace.json"
        trace.write_text(head + ",".join(chunks) + tail, encoding="utf-8")
        table: dict[str, list[float]] = {}
        for name, ms in launches:
            row = table.setdefault(name, [0, 0.0])
            row[0] += 1
            row[1] += ms
        ranked = sorted(table.items(), key=lambda item: -item[1][1])[:TABLE_ROWS]
        summary: dict = {
            "kind": "profile-summary",
            "schema_version": SCHEMA_VERSION,
            "stage": self.stage,
            "method": "warp-activity-timing",
            "label": LABEL,
            "device": self.device,
            "trace": {"file": "profile/trace.json", "format": "chrome-trace-json", "bytes": trace.stat().st_size},
            "truncated": truncated,
            "kernels_total": len(table),
            "kernels": [
                {"name": name, "calls": int(calls), "total_ms": total, "mean_ms": total / calls}
                for name, (calls, total) in ranked
            ],
        }
        if self.run_id is not None:
            summary["run_id"] = self.run_id
        path = folder / "profile-summary.json"
        path.write_text(json.dumps(summary), encoding="utf-8")
        self.summary, self.trace_path, self.summary_path = summary, trace, path
