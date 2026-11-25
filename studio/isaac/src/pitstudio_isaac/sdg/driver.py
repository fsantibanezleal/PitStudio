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
import traceback
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

ARMS = ("pit-structured.jsonl", "pit-unstructured.jsonl")
BYTES_PER_FRAME = 6_000_000  # RGB PNG, float32 depth, mask, COCO (measured on the first frames; a planning figure)
FREE_MARGIN_BYTES = 20 * 1024**3
PROBE_FRAMES = 3
WINDOW_FRAMES = 50  # rolling quality window: frames rendered by this process
WINDOW_MAX_FLAT = 5  # more flat frames than this in a window stop the run
FLAT_STD = 1.0  # a frame is flat below this rgb standard deviation (8-bit levels over all pixels and channels)
_UNREADABLE = (OSError, ValueError, KeyError)  # an unreadable or incomplete sidecar means the frame is not done
SIDECAR = "frame.json"
RUN_FILE = "run.json"
RESULT_FILE = "run_result.json"  # written before the renderer closes: the Isaac fast shutdown ends the process with 0
EXIT_BLOCK_OVER = 75  # the guard ended the block with frames left: the job runs the driver again after the cool-down


class Renderer(Protocol):
    def render_row(self, row: Mapping[str, Any], out_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]: ...

    def close(self) -> None: ...


class ProbeFailed(RuntimeError):
    """The first frames are not usable (empty depth, flat image or no annotation at all): the run stops early."""


class QualityDrift(RuntimeError):
    """Too many flat frames in a rolling window: the renderer has regressed, the run stops (the frames stay on disk)."""


class QualityWindow:
    """Rolling quality guard over the frames rendered by one process (it replaces the first-frames probe on a resume).

    Over each window of `size` consecutive frames more than `max_flat` flat frames (rgb std below `FLAT_STD`) raise
    `QualityDrift` at the frame that completes the window, so a regression stops a run within `size` frames while one
    legitimate flat frame never does. `finish()` applies the same ratio pro rata to the shorter window at the end of a
    GPU block (more than `max_flat / size` of its frames, with a floor of one frame, so a single flat frame never stops
    a run); it then starts the next window. `stats` keeps one entry per closed window for the job log.
    """

    def __init__(self, size: int = WINDOW_FRAMES, max_flat: int = WINDOW_MAX_FLAT) -> None:
        self.size, self.max_flat = size, max_flat
        self._stds: list[float] = []
        self.stats: list[dict[str, Any]] = []

    def allowed(self, frames: int) -> int:
        """Flat frames a window of `frames` frames may hold."""
        return self.max_flat if frames >= self.size else max(1, frames * self.max_flat // self.size)

    def add(self, measured: Mapping[str, Any]) -> dict[str, Any] | None:
        """Count a frame; returns the window's statistics when it closes, raises `QualityDrift` when it is bad."""
        self._stds.append(float(measured["rgb_std"]))
        return self._close() if len(self._stds) >= self.size else None

    def finish(self) -> dict[str, Any] | None:
        """Close the trailing window of a block (pro rata); None when it holds no frame."""
        return self._close() if self._stds else None

    def _close(self) -> dict[str, Any]:
        stds, self._stds = sorted(self._stds), []
        flat = sum(1 for v in stds if v < FLAT_STD)
        entry = {"frames": len(stds), "flat": flat, "std_min": stds[0], "std_median": stds[len(stds) // 2]}
        self.stats.append(entry)
        if flat > self.allowed(len(stds)):
            raise QualityDrift(
                f"{flat} flat frames in the last {len(stds)} (rgb std below {FLAT_STD:g}; at most "
                f"{self.allowed(len(stds))} allowed): the renderer has regressed"
            )
        return entry


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


def write_result(root: Path, status: str, rendered: int, remaining: int, error: str | None = None) -> None:
    """Atomically write the outcome of this run: `complete`, `limited`, `partial` (block over) or `failed`."""
    doc: dict[str, Any] = {"status": status, "rendered": rendered, "remaining": remaining}
    if error is not None:
        doc["error"] = error
    target = Path(root) / RESULT_FILE
    tmp = target.with_name(RESULT_FILE + ".tmp")
    tmp.write_text(json.dumps(doc), encoding="utf-8")
    os.replace(tmp, target)


def result_exit_code(root: Path) -> int:
    """Exit status the job takes from the result file: 0 complete or limited, 75 block over, 1 failed or unreadable.

    A missing or unreadable file means the process ended before it wrote one (a crash), which is a failure; a
    `complete` result that still lists remaining frames contradicts itself and fails too.
    """
    try:
        doc = json.loads((Path(root) / RESULT_FILE).read_text(encoding="utf-8"))
        status, remaining = doc["status"], int(doc["remaining"])
    except _UNREADABLE:
        return 1
    if status == "complete":
        return 0 if remaining == 0 else 1
    if status == "limited":
        return 0
    return EXIT_BLOCK_OVER if status == "partial" else 1


def preflight(root: Path, pending: int) -> None:
    """Refuse to start when the data drive cannot hold the pending frames plus a margin."""
    Path(root).mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(root).free
    need = pending * BYTES_PER_FRAME + FREE_MARGIN_BYTES
    if free < need:
        raise OSError(f"{free / 1e9:.0f} GB free below {root}, need {need / 1e9:.0f} GB for {pending} frames")


def _run_file(root: Path, info: Mapping[str, Any] | None = None) -> None:
    """Create `run.json` on the first run; every run records `info` (the render-settings model) in it."""
    path = Path(root) / RUN_FILE
    doc: dict[str, Any] = {}
    if path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
    else:
        doc = {"started_utc": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")}
    if not path.is_file() or (info and any(doc.get(k) != v for k, v in info.items())):
        doc.update(info or {})
        path.write_text(json.dumps(doc), encoding="utf-8")


def _pending(root: Path, rows: Sequence[Mapping[str, Any]], probe_first: bool = True) -> list[Mapping[str, Any]]:
    """The rows without a valid sidecar. With `probe_first` (an empty dataset) the probe rows come first: two
    structured frames and one unstructured frame, so that a defect of either arm stops the job in its first minutes
    instead of hours in. A resume keeps the table order, starting at the first frame without a valid sidecar."""
    todo = [r for r in rows if not is_done(root, r)]
    if not probe_first:
        return todo
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
    run_info: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Render the pending rows in guarded blocks; returns the counts. `session()` yields the guard under the GPU lock.

    `limit` stops after that many newly rendered frames (a bounded run); a stop by the guard (`GuardStop`) or a failed
    probe propagates after the frames written so far are safe on disk.
    """
    root = Path(root)
    pending = _pending(root, rows, probe_first=False)
    # The first-frames probe runs only when the dataset holds no valid frame yet: on a resume the rolling window guards.
    probed = len(pending) < len(rows)
    if not probed:
        pending = _pending(root, rows)
    window = QualityWindow()
    preflight(root, len(pending))
    _run_file(root, run_info)
    (root / RESULT_FILE).unlink(missing_ok=True)  # a result of an earlier run never stands for this one
    rendered = 0
    probe: list[Mapping[str, Any]] = []
    probe_rows: list[Mapping[str, Any]] = []
    started = time.monotonic()
    log(f"[sdg] {len(rows)} rows, {len(rows) - len(pending)} done, {len(pending)} pending")
    while pending and (limit is None or rendered < limit):
        with session() as guard:
            try:
                renderer = renderer_factory()
            except BaseException as exc:
                log(f"[sdg] the renderer failed to start\n{traceback.format_exc()}")
                write_result(root, "failed", rendered, len(pending), f"{type(exc).__name__}: {exc}")
                raise
            current: str | None = None
            outcome: tuple[str, str | None] = ("failed", "the block ended without an outcome")
            try:
                for row in pending:
                    if limit is not None and rendered >= limit:
                        break
                    current = row["record_id"]
                    out = frame_dir(root, row["record_id"])
                    record, measured = renderer.render_row(row, out)
                    write_sidecar(root, row, record, measured)
                    rendered += 1
                    closed = window.add(measured)
                    if closed is not None:
                        log(
                            f"[sdg] quality window: {closed['flat']} flat of {closed['frames']} frames, rgb std min "
                            f"{closed['std_min']:.1f} median {closed['std_median']:.1f}"
                        )
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
                closed = window.finish()
                if closed is not None:
                    log(
                        f"[sdg] block end window: {closed['flat']} flat of {closed['frames']} frames, rgb std min "
                        f"{closed['std_min']:.1f} median {closed['std_median']:.1f}"
                    )
                left = len(_pending(root, rows, probe_first=False))
                done = limit is not None and rendered >= limit
                outcome = ("complete" if left == 0 else "limited" if done else "partial", None)
            except BaseException as exc:
                # The Isaac renderer closes with a fast shutdown that ends the process: report before closing.
                log(f"[sdg] render block failed at {current} after {rendered} frames\n{traceback.format_exc()}")
                outcome = ("failed", f"{type(exc).__name__}: {exc}")
                raise
            finally:
                write_result(root, outcome[0], rendered, len(_pending(root, rows, probe_first=False)), outcome[1])
                renderer.close()
        pending = _pending(root, rows, probe_first=False)
        if pending and (limit is None or rendered < limit) and guard is not None:
            guard.cool_down()
    return {"rendered": rendered, "remaining": len(_pending(root, rows, probe_first=False))}


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
