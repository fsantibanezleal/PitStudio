"""Launching a stage process, reading its result, checking its outputs, classifying failures (FR-002-24..34, 60..65)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pitstudio.runner import oswin
from pitstudio.runner.cache import PROJECT
from pitstudio.runner.recipe import first_errors, strict_json

OOM = re.compile(r"CUDA out of memory|OutOfMemoryError|cudaErrorMemoryAllocation|CUDA_ERROR_OUT_OF_MEMORY", re.I)
WARMUP_ENVS = ("isaac", "rtx", "kit")


def build_command(*, launcher: str, repo: Path, env: str, entry: str, job_path: Path) -> list[str]:
    if launcher == "test":
        return [sys.executable, "-m", entry, "--job", str(job_path)]
    return [
        shutil.which("uv") or "uv",
        "run",
        "--project",
        str(repo / PROJECT[env]),
        "--frozen",
        "python",
        "-m",
        entry,
        "--job",
        str(job_path),
    ]


def run_attempt(
    argv: list[str],
    env: dict[str, str],
    cwd: Path,
    log_path: Path,
    timeout: float,
    on_tick: Callable[[Any], str | None] | None = None,
) -> dict[str, Any]:
    """Run one stage process in its own tree; end the tree on timeout or when `on_tick` returns a reason (<= 10 s)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    kind, t0 = None, time.monotonic()
    with open(log_path, "ab") as log:
        tree = oswin.Tree(argv, env, cwd, log)
        started = time.monotonic()  # the timeout runs from the moment the process exists, not from process creation
        try:
            while not kind:
                try:
                    code = tree.proc.wait(0.05)
                    break
                except subprocess.TimeoutExpired:
                    kind = "timeout" if time.monotonic() - started > timeout else on_tick and on_tick(tree)
            if kind:
                tree.freeze(False)
                tree.kill()
                code = tree.proc.returncode
        finally:
            tree.close()
    return {"kind": kind, "code": code, "wall_s": time.monotonic() - t0}


def read_result(out: Path, code: int) -> tuple[dict | None, str | None]:
    """The stage result and None, or None and why it is not acceptable (FR-002-25, 61, 65)."""
    p = out / "result.json"
    if not p.is_file():
        return None, "no result.json"
    try:
        if p.stat().st_size > 65536:
            return None, "result.json is larger than 65536 bytes"
        doc = strict_json(p.read_text(encoding="utf-8"))
    except ValueError, UnicodeError, RecursionError:
        return None, "result.json is not valid JSON"
    if errs := first_errors("job", doc, "#/$defs/stage_result", n=1):
        return None, f"result.json is invalid: {errs[0]}"
    paths = [o["path"] for o in doc["outputs"]]
    if dup := next((x for x in paths if paths.count(x) > 1), None):
        return None, f"two outputs on the path {dup}"
    if (doc["status"] == "failed") == (code == 0):
        return None, f"result status {doc['status']} does not match exit code {code}"
    return doc, None


def check_outputs(declared: list[dict], out: Path, result: dict) -> tuple[dict[str, Path], str | None]:
    """Every declared output is a regular file inside the stage folder and passes its validator (FR-002-12, 13)."""
    files, root = {}, os.path.realpath(out)
    for o in declared:
        p, v = out / o["path"], o["schema"]
        if os.path.islink(p) or not p.is_file() or not os.path.realpath(p).startswith(root + os.sep):
            return {}, f"{o['path']}: missing, not a regular file, or outside the stage folder"
        try:
            if v == "file" and p.stat().st_size == 0:
                return {}, f"{o['path']}: empty file"
            kind = "jsonl" if v == "jsonl" else "json" if v == "json" or v.startswith("contract-") else ""
            text = p.read_text(encoding="utf-8") if kind else ""
            docs = (
                [strict_json(x) for x in text.splitlines() if x.strip()]
                if kind == "jsonl"
                else [strict_json(text)]
                if kind
                else []
            )
            if v.startswith("contract-") and (errs := first_errors(v[9:], docs[0], n=1)):
                return {}, f"{o['path']}: {errs[0]}"
        except (ValueError, UnicodeError, RecursionError) as e:
            return {}, f"{o['path']}: {type(e).__name__}"
        if v.startswith("stage-") and not any(
            r["path"] == o["path"] and r.get("validated") and r.get("validator") == v for r in result["outputs"]
        ):
            return {}, f"{o['path']}: the stage did not validate it with {v}"
        files[o["path"]] = p
    return files, None


def scrub(text: str, repo: Path, store: Path, locks: Path) -> str:
    """Replace machine paths by `<repo>`, `$PITSTUDIO_STORE`, `$GPU_LOCK_DIR` and `~` (FR-002-34)."""
    for path, token in ((repo, "<repo>"), (store, "$PITSTUDIO_STORE"), (locks, "$GPU_LOCK_DIR"), (Path.home(), "~")):
        for form in {str(path), path.as_posix(), str(path).replace("\\", "\\\\")}:
            text = re.sub(re.escape(form), lambda _, t=token: t, text, flags=re.I if sys.platform == "win32" else 0)
    return text


def log_lines(log: Path, n: int) -> list[str]:
    try:
        with open(log, "rb") as fh:
            fh.seek(max(0, log.stat().st_size - 1_000_000))
            return fh.read().decode("utf-8", "replace").splitlines()[-n:]
    except OSError:
        return []
