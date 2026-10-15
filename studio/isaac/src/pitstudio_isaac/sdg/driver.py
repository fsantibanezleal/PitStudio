"""Shard driver of `st55_sdg`: renders the parameter-table rows, resumable frame by frame (FR-009-02, NFR-009-03).

The driver reads `pit-structured.jsonl` then `pit-unstructured.jsonl` of the table folder, renders every row that has no
valid sidecar yet below `<root>/frames/<record_id>/` and writes the sidecar `frame.json` (the DC-009-01 record with its
paths relative to the root, and the measurements the frame state needs) last and atomically, so a killed run resumes at
the first frame without a sidecar. GPU work runs under the machine lock `gpu0.compute` in blocks: the guard's
`check()` runs after every frame (at most seconds apart), pauses when hot, stops at the throttle point and ends a block
after `BLOCK_MIN` minutes; the renderer is closed and the lock released for the cool-down, then both are taken again.

The renderer is a factory, so the CPU renderer of the dry run goes through exactly this code.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

ARMS = ("pit-structured.jsonl", "pit-unstructured.jsonl")
BYTES_PER_FRAME = 6_000_000  # RGB PNG, float32 depth, mask, COCO (measured on the first frames; a planning figure)
FREE_MARGIN_BYTES = 20 * 1024**3
PROBE_FRAMES = 3
_UNREADABLE = (OSError, ValueError, KeyError)  # an unreadable or incomplete sidecar means the frame is not done
SIDECAR = "frame.json"
RUN_FILE = "run.json"


class Renderer(Protocol):
    def render_row(self, row: Mapping[str, Any], out_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]: ...

    def close(self) -> None: ...


class ProbeFailed(RuntimeError):
    """The first frames are not usable (empty depth, flat image or no annotation at all): the run stops early."""


def read_rows(table_dir: Path) -> list[dict[str, Any]]:
    """Every row of the table in render order (structured arm, then unstructured arm)."""
    rows: list[dict[str, Any]] = []
    for name in ARMS:
        path = Path(table_dir) / name
        if path.is_file():
            rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    if not rows:
        raise FileNotFoundError(f"no parameter table rows under {table_dir}")
    return rows


def frame_dir(root: Path, record_id: str) -> Path:
    return Path(root) / "frames" / record_id


def _prefixed(record: Mapping[str, Any], record_id: str) -> dict[str, Any]:
    """The record with every file path made relative to the dataset root."""
    out = json.loads(json.dumps(record))
    for key in ("image", "coco", "semantic_mask", "depth"):
        out[key]["path"] = f"frames/{record_id}/{out[key]['path']}"
    return out


def is_done(root: Path, row: Mapping[str, Any]) -> bool:
    """True when the frame's sidecar exists and every file it names exists with the recorded size."""
    sidecar = frame_dir(root, row["record_id"]) / SIDECAR
    if not sidecar.is_file():
        return False
    try:
        record = json.loads(sidecar.read_text(encoding="utf-8"))["record"]
        return all(
            (Path(root) / record[k]["path"]).is_file()
            and (Path(root) / record[k]["path"]).stat().st_size == record[k]["size_bytes"]
            for k in ("image", "coco", "semantic_mask", "depth")
        )
    except _UNREADABLE:  # a tuple name: the formatter writes tuples of exceptions without parentheses, a 3.14 syntax
        return False


def write_sidecar(root: Path, row: Mapping[str, Any], record: Mapping[str, Any], measured: Mapping[str, Any]) -> None:
    target = frame_dir(root, row["record_id"]) / SIDECAR
    doc = {"record": _prefixed(record, row["record_id"]), "measured": dict(measured)}
    tmp = target.with_name(SIDECAR + ".tmp")
    tmp.write_text(json.dumps(doc, allow_nan=False), encoding="utf-8")
    os.replace(tmp, target)


def check_probe(measured: Sequence[Mapping[str, Any]]) -> None:
    """Refuse a run whose first frames are empty: depth mostly non-finite, a flat image or no annotation at all."""
    for m in measured:
        if m["depth_finite_fraction"] < 0.5:
            raise ProbeFailed(f"only {m['depth_finite_fraction']:.2f} of the depth pixels are finite")
        if m["rgb_std"] < 1.0:
            raise ProbeFailed(f"the image is flat (standard deviation {m['rgb_std']:.2f})")
    if sum(int(m["annotations"]) for m in measured) == 0:
        raise ProbeFailed(f"no annotation in the first {len(measured)} frames: the labelled objects are not visible")


def preflight(root: Path, pending: int) -> None:
    """Refuse to start when the data drive cannot hold the pending frames plus a margin."""
    Path(root).mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(root).free
    need = pending * BYTES_PER_FRAME + FREE_MARGIN_BYTES
    if free < need:
        raise OSError(f"{free / 1e9:.0f} GB free below {root}, need {need / 1e9:.0f} GB for {pending} frames")


def _run_file(root: Path) -> None:
    path = Path(root) / RUN_FILE
    if not path.is_file():
        path.write_text(json.dumps({"started_utc": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")}), encoding="utf-8")


def _pending(root: Path, rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The rows without a valid sidecar, the probe rows first: two structured frames and one unstructured frame, so
    that a defect of either arm stops the job in its first minutes instead of hours in."""
    todo = [r for r in rows if not is_done(root, r)]
    probe: list[Mapping[str, Any]] = []
    for arm, n in (("structured", PROBE_FRAMES - 1), ("unstructured", 1)):
        probe.extend([r for r in todo if r["arm"] == arm][:n])
    chosen = {r["record_id"] for r in probe}
    return probe + [r for r in todo if r["record_id"] not in chosen]


def _discard(root: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Remove the frames of rows that failed the probe, so that a later run renders them again."""
    for row in rows:
        shutil.rmtree(frame_dir(root, row["record_id"]), ignore_errors=True)


def run(
    *,
    rows: Sequence[Mapping[str, Any]],
    root: Path,
    renderer_factory: Callable[[], Renderer],
    session: Callable[[], contextlib.AbstractContextManager[Any]],
    log: Callable[[str], None] = lambda m: print(m, flush=True),
    limit: int | None = None,
) -> dict[str, Any]:
    """Render the pending rows in guarded blocks; returns the counts. `session()` yields the guard under the GPU lock.

    `limit` stops after that many newly rendered frames (a bounded run); a stop by the guard (`GuardStop`) or a failed
    probe propagates after the frames written so far are safe on disk.
    """
    root = Path(root)
    pending = _pending(root, rows)
    preflight(root, len(pending))
    _run_file(root)
    rendered = 0
    probed = False
    probe: list[Mapping[str, Any]] = []
    probe_rows: list[Mapping[str, Any]] = []
    started = time.monotonic()
    log(f"[sdg] {len(rows)} rows, {len(rows) - len(pending)} done, {len(pending)} pending")
    while pending and (limit is None or rendered < limit):
        with session() as guard:
            renderer = renderer_factory()
            try:
                for row in pending:
                    if limit is not None and rendered >= limit:
                        break
                    out = frame_dir(root, row["record_id"])
                    record, measured = renderer.render_row(row, out)
                    write_sidecar(root, row, record, measured)
                    rendered += 1
                    if len(probe) < PROBE_FRAMES and not probed:
                        probe.append(measured)
                        probe_rows.append(row)
                        if len(probe) == PROBE_FRAMES or len(probe) == len(pending):
                            try:
                                check_probe(probe)
                            except ProbeFailed:
                                _discard(root, probe_rows)
                                raise
                            probed = True
                    if rendered % 50 == 0:
                        rate = rendered / max(time.monotonic() - started, 1e-9)
                        log(f"[sdg] {rendered} frames this run, {rate:.2f} frames/s, {len(pending) - rendered} to go")
                    if guard is not None and guard.check() == "cooldown":
                        break
            finally:
                renderer.close()
        pending = _pending(root, rows)
        if pending and (limit is None or rendered < limit) and guard is not None:
            guard.cool_down()
    return {"rendered": rendered, "remaining": len(_pending(root, rows))}


def gpu_session_factory(lock_path: str) -> Callable[[], contextlib.AbstractContextManager[Any]]:
    """The machine lock `gpu0.compute` plus the guard of `studio/bench/gpu_guard.py`; refuses to start above 80 C."""
    import sys

    bench = str(Path(__file__).resolve().parents[4] / "bench")
    if bench not in sys.path:
        sys.path.insert(0, bench)
    import gpu_guard
    from filelock import FileLock

    @contextlib.contextmanager
    def session() -> Iterator[Any]:
        guard = gpu_guard.Guard()
        temp = guard.read_temp()
        if temp > gpu_guard.START_MAX_C:
            raise RuntimeError(f"GPU at {temp} C, above the start limit {gpu_guard.START_MAX_C} C")
        with FileLock(lock_path):
            yield guard

    return session


@contextlib.contextmanager
def no_gpu_session() -> Iterator[None]:
    """Session of the CPU renderer of the dry run: no lock and no guard."""
    yield None
