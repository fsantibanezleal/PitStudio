# ruff: noqa: E501
"""Test support for spec 003 (console): a runner world (repo, store, locks), recipes, a hand-built finished run with artefacts,
queue jobs, and an in-process ASGI client on the console application.

Expected console API (stated in every console test file and in the red report):
  * `pitstudio_api.app.create_app(*, port: int, allow_origins: list[str] | None = None)` returns the ASGI application
    (FastAPI); `port` is the port the console listens on (the Host/Origin rules need it); `allow_origins` None reads
    PITSTUDIO_CONSOLE_ALLOW_ORIGINS (default `https://fsantibanezleal.github.io`);
  * the store is PITSTUDIO_STORE and the repository PITSTUDIO_REPO, read per request (so a test can break them);
  * the console calls the runner only through `pitstudio.runner.queue` (`enqueue`, `cancel`, `jobs`, `job`) by module
    attribute (`from pitstudio.runner import queue; queue.enqueue(...)`), so tests can spy on them;
  * `python -m pitstudio_api` starts the server (see tests/unit/test_t_003_010_startup.py).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import publish_world as pw
import runner_world as rw
import yaml
from asgi_client import Client

PORT = 8765
sys.path.insert(0, str(rw.ROOT / "api"))
sys.path.insert(0, str(rw.SRC))

CLIP = bytes((i * 7 + 3) % 256 for i in range(300_000))
NOTES = b"plain notes without a declared media type\n" * 20
RUN_ID = pw.RUN_ID
BROKEN_RUN_ID = "20261008T090000Z-broken-manifest"
OTHER_RUN_ID = "20261009T090000Z-other"


def good_recipes() -> list[tuple[dict[str, Any], str]]:
    return [
        (rw.recipe("a2-haulage", [rw.stage("s10_preprocess"), rw.stage("st10_terrain")], case="A2"), "cases"),
        (rw.recipe("bench-one", [rw.stage("s64_bench", env="accel")], case="bench"), "_bench"),
    ]


@dataclass
class ConsoleWorld:
    w: rw.World
    client: Client
    app: Any
    run_id: str = RUN_ID

    def post_job(self, body: Any = None, **kw: Any):
        body = body if body is not None else {"recipe": "a2-haulage", "profile": "test-profile"}
        return self.client.post("/jobs", json_body=body, **kw)


def make_artefacts(run_id: str, git_sha: str, clip_sha: str, notes_sha: str) -> list[dict[str, Any]]:
    base = {
        "run_id": run_id,
        "git_sha": git_sha,
        "producer": {"tool": "nvenc-ffmpeg", "stage": {"id": "st56_encode"}},
        "inputs": [],
        "licence_class": "own",
        "spdx": "CC-BY-4.0",
        "asset_host": "git",
    }
    return [
        {**base, "id": "a2-clip", "path": f"assets/{run_id}/clip.mp4", "bytes": len(CLIP), "sha256": clip_sha, "media_type": "video/mp4", "kind": "video", "cases": ["A2"],
         "lane": "replay", "lane_measurements": pw.lane_measurements(max_asset_bytes=len(CLIP)), "budget_class": "videos", "encoder": pw.encoder_record()},
        {**base, "id": "a2-notes", "path": f"assets/{run_id}/notes.txt", "bytes": len(NOTES), "sha256": notes_sha, "kind": "text", "lane": "static", "budget_class": "own-code"},
    ]  # fmt: skip


def seed_run(w: rw.World) -> dict[str, Any]:
    """The hand-built finished run (publish_world.build_run) plus two artefact records backed by cas objects."""
    b = pw.build_run(w, run_id=RUN_ID)
    cas = w.store / "cas" / "sha256"
    shas = {}
    for name, data in (("clip", CLIP), ("notes", NOTES)):
        d = pw.sha(data)
        p = cas / d[:2] / d
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        shas[name] = d
    m = dict(b.manifest)
    m["artefacts"] = make_artefacts(RUN_ID, b.git_sha, shas["clip"], shas["notes"])
    (b.run_dir / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    # a second valid run and one whose manifest is damaged
    broken = w.store / "runs" / BROKEN_RUN_ID
    broken.mkdir(parents=True)
    (broken / "manifest.json").write_text("{this is not json", encoding="utf-8")
    (broken / "events.jsonl").write_text(
        json.dumps({"seq": 1, "t": "2026-10-08T09:00:00Z", "run_id": BROKEN_RUN_ID, "type": "run-started"}) + "\n",
        encoding="utf-8",
    )
    other = dict(m)
    other["run_id"] = OTHER_RUN_ID
    other["artefacts"] = []
    od = w.store / "runs" / OTHER_RUN_ID
    od.mkdir(parents=True)
    (od / "manifest.json").write_text(json.dumps(other), encoding="utf-8")
    (od / "events.jsonl").write_text(
        json.dumps({"seq": 1, "t": "2026-10-09T09:00:00Z", "run_id": OTHER_RUN_ID, "type": "run-started"}) + "\n",
        encoding="utf-8",
    )
    return {"manifest": m, "shas": shas}


def make_console_world(
    monkeypatch: Any, tmp_path: Path, *, recipes: bool = True, runs: bool = True, allow_origins: list[str] | None = None
) -> ConsoleWorld:
    from pitstudio_api.app import (
        create_app,  # first-party; absent until the console exists (fail before building anything)
    )

    w = rw.make_world(monkeypatch, tmp_path)
    if recipes:
        for doc, folder in good_recipes():
            w.write_recipe(doc, folder)
        (w.repo / "studio" / "recipes" / "cases" / "broken-one.yaml").write_text(
            "id: broken-one\ncase: A2\nseed: 1\nstages: nope\n", encoding="utf-8"
        )
        (w.repo / "studio" / "recipes" / "_bench" / "not-yaml.yaml").write_text("id: [unclosed\n", encoding="utf-8")
    if runs:
        seed_run(w)
    w.commit()
    app = create_app(port=PORT, allow_origins=allow_origins)
    return ConsoleWorld(w=w, client=Client(app, PORT), app=app)


def junction_or_symlink(link: Path, target: Path) -> None:
    import os
    import subprocess

    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def recipe_yaml(doc: dict[str, Any]) -> str:
    return yaml.safe_dump(doc, sort_keys=False)
