# ruff: noqa: E501
"""Test support for `studio gc`: seed a store with runs, shared objects and index entries, and compute the reachability
oracle by hand (no networkx, no code under test).

Layout of plan.md D3: cas/sha256/<aa>/<digest>, index/<aa>/<cache key>.json, runs/<run id>/{manifest.json, events.jsonl,
PINNED}. Runs that share a cache key share one index entry (written once, by the earliest run, as a cache hit would).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import runner_world as rw

POOL = [f"object number {i} of the pool\n".encode() * (3 + i) for i in range(10)]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@dataclass
class SeedRun:
    run_id: str
    recipe: str
    objects: tuple[int, ...]  # indices into POOL
    pinned: bool = False
    in_web: bool = False
    in_models: bool = False
    stale_running_job: bool = False
    key: str = field(init=False)

    def __post_init__(self) -> None:
        self.key = sha(("key|" + ",".join(map(str, sorted(self.objects)))).encode())


def manifest_for(run: SeedRun, repo_sha: str, published: bool = False) -> dict[str, Any]:
    ts = run.run_id[:8] + "T" + run.run_id[9:15]
    outs = [{"name": f"o{i}.bin", "sha256": sha(POOL[i]), "bytes": len(POOL[i])} for i in sorted(run.objects)]
    return {
        "kind": "run", "schema_version": "1.0", "run_id": run.run_id,
        "recipe": {"id": run.recipe, "path": f"cases/{run.recipe}.yaml", "sha256": "e" * 64},
        "git_sha": repo_sha, "git_dirty": False, "runner_version": "0.1.0",
        "created": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}T{ts[9:11]}:{ts[11:13]}:{ts[13:15]}Z", "profile": "test-profile", "seed": 1,
        "published": published, "launcher": "uv", "gpu": None,
        "stages": [{
            "key": {"id": "s10_preprocess"}, "tool": "pitstudio",
            "env": {"name": "pipeline", "python": "3.14.4", "lock_sha256": "3" * 64, "versions": {}},
            "cache_key": run.key, "cache": "miss", "status": "succeeded", "exit_code": 0, "error_class": None,
            "attempts": [{"n": 1, "error_class": None}], "params": {}, "seed": 5, "determinism": {"class": "bitwise", "rerun_check": "pending"},
            "performance": "public", "telemetry": None, "thermal_flag": False, "inputs": [], "outputs": outs,
        }],
        "artefacts": [],
    }  # fmt: skip


def seed(world: rw.World, runs: list[SeedRun], repo_sha: str) -> None:
    """Write the store content of `runs` and the pointers (web index, model cards) that keep some of them alive."""
    store = world.store
    written_keys: set[str] = set()
    for run in sorted(runs, key=lambda r: r.run_id):
        d = store / "runs" / run.run_id
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps(manifest_for(run, repo_sha)), encoding="utf-8")
        (d / "events.jsonl").write_text(
            json.dumps({"seq": 1, "t": "2026-10-07T12:00:00Z", "run_id": run.run_id, "type": "run-started"})
            + "\n"
            + json.dumps({"seq": 2, "t": "2026-10-07T12:05:00Z", "run_id": run.run_id, "type": "run-finished"})
            + "\n",
            encoding="utf-8",
        )
        if run.pinned:
            (d / "PINNED").write_text("pinned by studio publish\n", encoding="utf-8")
        for i in run.objects:
            data = POOL[i]
            p = store / "cas" / "sha256" / sha(data)[:2] / sha(data)
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_bytes(data)
        if run.key not in written_keys:
            written_keys.add(run.key)
            entry = {
                "stage": {"id": "s10_preprocess"},
                "outputs": [
                    {"name": f"o{i}.bin", "sha256": sha(POOL[i]), "bytes": len(POOL[i])} for i in sorted(run.objects)
                ],
                "run_id": run.run_id,
                "created": "2026-10-07T12:00:00Z",
            }
            ip = store / "index" / run.key[:2] / f"{run.key}.json"
            ip.parent.mkdir(parents=True, exist_ok=True)
            ip.write_text(json.dumps(entry, sort_keys=True), encoding="utf-8")
    web = world.repo / "web" / "public" / "assets" / "manifest.json"
    idx = json.loads(web.read_text(encoding="utf-8"))
    idx["runs"] = [
        {"run_id": r.run_id, "manifest": f"{r.run_id}/manifest.json", "sha256": "7" * 64} for r in runs if r.in_web
    ]
    web.write_text(json.dumps(idx), encoding="utf-8")
    cards = world.repo / "models" / "cards"
    for r in runs:
        if r.in_models:
            c = cards / f"card-{r.run_id}"
            c.mkdir(parents=True, exist_ok=True)
            (c / "manifest.json").write_text(json.dumps(manifest_for(r, repo_sha, published=True)), encoding="utf-8")


def reference(runs: list[SeedRun], keep_last: int) -> dict[str, Any]:
    """Oracle: which runs, cache keys and objects must survive (written from FR-002-51, independent of the code under test)."""
    kept = {r.run_id for r in runs if r.pinned or r.in_web or r.in_models or r.stale_running_job}
    by_recipe: dict[str, list[SeedRun]] = {}
    for r in runs:
        by_recipe.setdefault(r.recipe, []).append(r)
    for rs in by_recipe.values():
        for r in sorted(rs, key=lambda x: x.run_id, reverse=True)[:keep_last]:
            kept.add(r.run_id)
    kept_runs = [r for r in runs if r.run_id in kept]
    return {
        "runs": kept,
        "keys": {r.key for r in kept_runs},
        "objects": {sha(POOL[i]) for r in kept_runs for i in r.objects},
    }


def present(store: Path) -> dict[str, set[str]]:
    cas = store / "cas" / "sha256"
    idx = store / "index"
    runs = store / "runs"
    return {
        "objects": {f.name for f in cas.rglob("*") if f.is_file()} if cas.is_dir() else set(),
        "keys": {f.stem for f in idx.rglob("*.json")} if idx.is_dir() else set(),
        "runs": {d.name for d in runs.iterdir() if d.is_dir()} if runs.is_dir() else set(),
    }


def total_bytes(store: Path, parts: tuple[str, ...] = ("cas", "index", "runs")) -> int:
    n = 0
    for part in parts:
        base = store / part
        if base.is_dir():
            n += sum(f.stat().st_size for f in base.rglob("*") if f.is_file())
    return n
