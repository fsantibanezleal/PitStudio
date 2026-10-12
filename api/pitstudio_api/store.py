"""Read-only access to the store, the repository's recipes and the runner's queue records (FR-003-05, 07, 08, 12, 13, 23)."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from functools import cache
from pathlib import Path
from typing import Any

from pitstudio.runner import queue
from pitstudio.runner.recipe import (
    RUN_ID,
    SLUG,
    Usage,
    first_errors,
    load_recipe,
    load_yaml,
    store_root,
    strict_json,  # fmt: skip
    validator,
)

log = logging.getLogger("pitstudio_api")
CASES = {"A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2", "bench"}
MANIFEST_MAX = 8 * 2**20


class StoreUnavailable(Exception):
    """The store folder or the queue file cannot be used right now (503, Retry-After: 5)."""


def store_dir() -> Path:
    try:
        p = store_root()
    except Usage:
        raise StoreUnavailable("the store location is not usable") from None
    if not p.is_dir():
        raise StoreUnavailable("the store folder is missing")
    return p


def ask_queue(call: str, *args: Any) -> Any:
    """Call the runner's queue API by attribute (so it can be replaced); a broken queue file is a 503."""
    store_dir()
    try:
        return getattr(queue, call)(*args)
    except sqlite3.Error, OSError:
        raise StoreUnavailable("the job queue is unavailable") from None


def check_job(rec: dict) -> dict:
    """A record whose shard counter exceeds its total is never served (FR-003-31): the SHA-256 of the record is logged."""
    shards = rec.get("shards")
    if shards and shards["done"] > shards["total"]:
        digest = hashlib.sha256(json.dumps(rec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        log.error("job record %s has done > total; record sha256 %s", rec["job_id"], digest)
        raise ValueError(rec["job_id"])
    return rec


# ---- recipes -----------------------------------------------------------------------------------------------------------
def recipe_files(repo: Path) -> list[Path]:
    return sorted(
        p for d in ("cases", "_bench") for p in (repo / "studio" / "recipes" / d).glob("*.yaml") if p.is_file()
    )


def error_items(errs: list[Any]) -> list[dict]:
    return [
        {
            "pointer": "/" + "/".join(map(str, e.absolute_path)),
            "keyword": str(e.validator),
            "message": " ".join(e.message.split())[:300] or "invalid",
        }
        for e in errs[:20]
    ]


def recipe_view(repo: Path, path: Path) -> tuple[dict | None, list[dict]]:
    """The validated recipe, or None and up to 20 errors (an unreadable, oversized or invalid file is never a 5xx)."""
    try:
        if path.stat().st_size > 262_144:
            return None, [{"pointer": "", "keyword": "size", "message": "the recipe file is larger than 262,144 bytes"}]
        if path.read_bytes().startswith(b"\xef\xbb\xbf"):
            return None, [{"pointer": "", "keyword": "bom", "message": "the recipe file starts with a byte-order mark"}]
        doc = load_yaml(path, "recipe")
    except (Usage, OSError) as e:
        return None, [{"pointer": "", "keyword": "loader", "message": " ".join(str(e).split())[:300]}]
    if not isinstance(doc, dict):
        return None, [{"pointer": "", "keyword": "type", "message": "the recipe must be a mapping"}]
    if errs := list(validator("recipe").iter_errors(doc)):
        return None, error_items(sorted(errs, key=lambda e: [str(p) for p in e.absolute_path]))
    try:
        return load_recipe(repo, path), []
    except Usage as e:
        return None, [{"pointer": "", "keyword": "recipe", "message": " ".join(str(e).split())[:300]}]


def recipe_summary(repo: Path, path: Path) -> dict:
    doc, errors = recipe_view(repo, path)
    raw = path.read_bytes()
    head = {}
    if not doc:
        with_doc = load_yaml_or_none(path)
        head = with_doc if isinstance(with_doc, dict) else {}
    src = doc or head
    rid, case = src.get("id"), src.get("case")
    stages = src.get("stages")
    return {"id": rid if isinstance(rid, str) and SLUG.fullmatch(rid) else None, "case": case if case in CASES else None,
            "path": path.relative_to(repo).as_posix(), "sha256": hashlib.sha256(raw).hexdigest(),
            "stages": min(len(stages), 64) if isinstance(stages, list) else 0, "valid": doc is not None, "errors": errors}  # fmt: skip


def load_yaml_or_none(path: Path) -> Any:
    try:
        return load_yaml(path, "recipe")
    except Usage, OSError:
        return None


def find_recipe_file(repo: Path, rid: str) -> Path | None:
    return next((p for p in recipe_files(repo) if p.stem == rid), None)


# ---- runs --------------------------------------------------------------------------------------------------------------
def run_ids(store: Path) -> list[str]:
    runs = store / "runs"
    return sorted(d.name for d in runs.iterdir() if d.is_dir() and RUN_ID.fullmatch(d.name)) if runs.is_dir() else []


@cache
def _manifest(path: str, mtime: int, size: int) -> tuple[dict | None, str]:
    try:
        doc = strict_json(Path(path).read_text(encoding="utf-8")) if size <= MANIFEST_MAX else None
    except OSError, ValueError, RecursionError:
        doc = None
    if not isinstance(doc, dict):
        return None, "the manifest is not a readable JSON object"
    errs = first_errors("manifest", doc, "#/$defs/run", n=1)
    return (None, f"the manifest is invalid: {errs[0]}") if errs else (doc, "")


def read_manifest(store: Path, run_id: str) -> tuple[dict | None, str]:
    """(manifest, "") for a valid manifest, (None, why) for a damaged one; FileNotFoundError when the run is unknown."""
    p = store / "runs" / run_id / "manifest.json"
    if not (store / "runs" / run_id).is_dir():
        raise FileNotFoundError(run_id)
    try:
        st = p.stat()
    except OSError:
        return None, "the run has no manifest"
    return _manifest(str(p), st.st_mtime_ns, st.st_size)


def artefact_file(store: Path, sha: str) -> Path | None:
    """The stored object of an artefact, or None when it is missing or leads outside `cas/` (for example through a link)."""
    cas = os.path.realpath(store / "cas")
    p = store / "cas" / "sha256" / sha[:2] / sha
    real = os.path.realpath(p)
    return p if re.fullmatch(r"[0-9a-f]{64}", sha) and real.startswith(cas + os.sep) and os.path.isfile(real) else None
