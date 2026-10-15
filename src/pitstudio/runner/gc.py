"""`studio gc`: mark what the kept runs reach, sweep the rest of cas/, index/ and runs/ (FR-002-51, FR-002-52)."""

from __future__ import annotations

import collections
import contextlib
import json
import shutil
from pathlib import Path

from pitstudio.runner import queue
from pitstudio.runner.cache import HEX64, Store, file_sha
from pitstudio.runner.recipe import RUN_ID


def _doc(p: Path) -> dict:
    with contextlib.suppress(OSError, ValueError):
        if isinstance(doc := json.loads(p.read_text(encoding="utf-8")), dict):
            return doc
    return {}


def _size(p: Path) -> int:
    return sum(f.stat().st_size for f in ([p] if p.is_file() else p.rglob("*")) if f.is_file())


def kept_runs(runs: Path, repo: Path, ids: list[str], keep_last: int) -> set[str]:
    """Pinned runs, runs of the web index and model cards, runs of queued or running jobs, the newest N per recipe."""
    keep = {r for r in ids if (runs / r / "PINNED").exists()}
    keep |= {
        x["run_id"]
        for x in _doc(repo / "web" / "public" / "assets" / "manifest.json").get("runs", [])
        if isinstance(x, dict) and isinstance(x.get("run_id"), str)
    }
    keep |= {
        doc["run_id"]
        for c in (repo / "models" / "cards").glob("*/manifest.json")
        if isinstance((doc := _doc(c)).get("run_id"), str)
    }
    keep |= {j["run_id"] for j in queue.jobs() if j["state"] in ("queued", "running")}
    seen: collections.Counter[str] = collections.Counter()
    for r in ids:  # newest first, so the first N of each recipe are the newest
        seen[r[17:]] += 1
        if seen[r[17:]] <= keep_last:
            keep.add(r)
    return keep & set(ids)


def collect(store_dir: Path, repo: Path, keep_last: int, dry: bool = False, verify: bool = False) -> int:
    """Delete what no kept run reaches; returns the bytes freed (or that would be freed)."""
    store, runs = Store(store_dir), store_dir / "runs"
    ids = (
        sorted((d.name for d in runs.iterdir() if d.is_dir() and RUN_ID.fullmatch(d.name)), reverse=True)
        if runs.is_dir()
        else []
    )
    keep, keys, objects = kept_runs(runs, repo, ids, keep_last), set(), set()
    for r in keep:
        for s in _doc(runs / r / "manifest.json").get("stages", []):
            keys.add(s.get("cache_key"))
            objects |= {o["sha256"] for o in s.get("outputs", [])}
        for line in (
            (runs / r / "events.jsonl").read_text(encoding="utf-8", errors="replace").splitlines()
            if (runs / r / "events.jsonl").is_file()
            else []
        ):
            with contextlib.suppress(ValueError, AttributeError, TypeError, KeyError):
                keys.add(json.loads(line)["data"]["cache_key"])
    for k in filter(HEX64.fullmatch, (k for k in keys if isinstance(k, str))):
        objects |= {o["sha256"] for o in _doc(store.entry_path(k)).get("outputs", [])}
    doomed = [p for p in (store_dir / "index").rglob("*.json") if p.stem not in keys]
    doomed += [p for p in (store_dir / "cas" / "sha256").rglob("*") if p.is_file() and p.name not in objects]
    doomed += [runs / r for r in ids if r not in keep]
    freed = sum(_size(p) for p in doomed)
    for p in [] if dry else doomed:
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    for d in objects if verify and not dry else ():
        if store.obj(d).is_file() and file_sha(store.obj(d)) != d:
            store.quarantine(store.obj(d))
    return freed
