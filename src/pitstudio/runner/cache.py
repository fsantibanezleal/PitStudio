"""Cache key, derived seed, code and lock digests, and the content-addressed store (FR-002-08..14)."""

# ruff: noqa: E501

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import time
import uuid
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

PROJECT = {"studio": "studio", "isaac": "studio/isaac", "rtx": "studio/rtx", "isaaclab": "studio/isaaclab", "pipeline": "pipeline",
           "accel": "pipeline/accel", "kit": "studio", "reason": "studio", "external": "studio"}  # fmt: skip
CODE = {"studio": ["studio/src"], "isaac": ["studio/isaac/src"], "rtx": ["studio/rtx/src"], "isaaclab": ["studio/isaaclab/src"],
        "pipeline": ["pipeline/src"], "accel": ["pipeline/accel/src"], "kit": ["studio/src", "studio/kit"],
        "reason": ["studio/src", "studio/reason"], "external": ["studio/src"]}  # fmt: skip
SKIP_DIRS = {"__pycache__", ".venv", ".pytest_cache", "node_modules"}
HEX64 = re.compile(r"[0-9a-f]{64}")


def _num(x: float) -> str:
    """ECMAScript Number::toString for the finite floats of a recipe."""
    if x == int(x) and abs(x) < 1e21:
        return str(int(x))
    return format(Decimal(repr(x)), "f") if 1e-6 <= abs(x) < 1e-4 else re.sub(r"e([+-])0*(\d)", r"e\1\2", repr(x))


def jcs(o: Any) -> bytes:
    """RFC 8785 canonical JSON: sorted keys, no white space, ECMAScript numbers."""
    if isinstance(o, float):
        return _num(o).encode()
    if isinstance(o, list | tuple):
        return b"[" + b",".join(map(jcs, o)) + b"]"
    if isinstance(o, dict):
        items = sorted(o.items(), key=lambda kv: kv[0].encode("utf-16-be"))
        return b"{" + b",".join(jcs(k) + b":" + jcs(v) for k, v in items) + b"}"
    return json.dumps(o, ensure_ascii=False).encode("utf-8")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def file_sha(p: Path) -> str:
    with open(p, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def cache_key(
    *, stage: dict, code: str, lock: str, params: dict, seed: int, inputs: dict, binaries: dict, shard: dict | None
) -> str:
    doc = {
        "stage": stage,
        "code": code,
        "lock": lock,
        "params": params,
        "seed": seed,
        "inputs": inputs,
        "binaries": binaries,
    }
    return sha(jcs({**doc, "shard": shard}))


def derive_seed(seed0: int, key: str, index: int) -> int:
    return int.from_bytes(hashlib.sha256(jcs([seed0, key, index])).digest()[:8], "big") & (2**63 - 1)


def code_digest(repo: Path, env: str) -> str:
    items = []
    for root in [*CODE[env], "src/pitstudio/runner/stagekit"]:
        for dp, dirs, files in os.walk(repo / root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith(".egg-info")]
            items += [
                [Path(dp, f).relative_to(repo).as_posix(), file_sha(Path(dp, f))]
                for f in files
                if not f.endswith(".pyc")
            ]
    return sha(jcs(sorted(items)))


def lock_digest(repo: Path, env: str) -> str:
    return sha((repo / PROJECT[env] / "uv.lock").read_bytes())


def write_atomic(path: Path, data: str) -> None:
    """Write beside the target, then rename over it: a reader sees the old or the new file, never a partial one."""
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(data, encoding="utf-8", newline="\n")
    for attempt in range(50):  # Windows refuses the rename while a reader holds the target open
        try:
            return os.replace(tmp, path)
        except PermissionError:
            if attempt == 49:
                raise
            time.sleep(0.01)


def link_or_copy(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


class Store:
    """`cas/sha256/<aa>/<digest>` objects, `index/<aa>/<key>.json` entries, `views/`, `quarantine/` (plan.md D3)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def obj(self, digest: str) -> Path:
        return self.root / "cas" / "sha256" / digest[:2] / digest

    def entry_path(self, key: str) -> Path:
        return self.root / "index" / key[:2] / f"{key}.json"

    def quarantine(self, p: Path) -> None:
        (self.root / "quarantine").mkdir(parents=True, exist_ok=True)
        os.replace(p, self.root / "quarantine" / f"{p.name}.{uuid.uuid4().hex[:8]}")

    def verify(self, o: dict, repair: bool = True, on_corrupt: Callable[[str], None] | None = None) -> bool:
        """The object exists with its recorded size and (up to 256 MiB) SHA-256; a damaged one is quarantined."""
        try:
            d, n = o["sha256"], o["bytes"]
            f = self.obj(d)
            if not HEX64.fullmatch(d) or not f.is_file():
                return False
            if f.stat().st_size == n and (n > 256 * 2**20 or file_sha(f) == d):
                return True
            if repair:
                self.quarantine(f)
                on_corrupt and on_corrupt(d)
        except KeyError, TypeError, OSError:
            pass
        return False

    def lookup(self, key: str, repair: bool = True, on_corrupt: Callable[[str], None] | None = None) -> dict | None:
        try:
            e = json.loads(self.entry_path(key).read_text(encoding="utf-8"))
            outs = e["outputs"]
        except OSError, ValueError, KeyError, TypeError:
            return None
        return e if isinstance(outs, list) and all(self.verify(o, repair, on_corrupt) for o in outs) else None

    def promote(self, key: str, doc: dict, files: dict[str, Path]) -> list[dict]:
        """Objects first (renamed into place by digest), the index entry last (FR-002-12)."""
        outs, tmp = [], self.root / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        for name, src in files.items():
            d = file_sha(src)
            self.obj(d).parent.mkdir(parents=True, exist_ok=True)
            if not self.obj(d).exists():
                link_or_copy(src, tmp / d)
                os.replace(tmp / d, self.obj(d))
            outs.append({"name": name, "sha256": d, "bytes": src.stat().st_size})
        self.entry_path(key).parent.mkdir(parents=True, exist_ok=True)
        write_atomic(self.entry_path(key), json.dumps({**doc, "outputs": outs}, sort_keys=True))
        return outs

    def stage_bytes(self, stage_id: str) -> int:
        """Bytes recorded in the index entries of one stage id (the quota of FR-002-20)."""
        total = 0
        for p in (self.root / "index").rglob("*.json"):
            with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
                e = json.loads(p.read_text(encoding="utf-8"))
                total += sum(o["bytes"] for o in e["outputs"]) if e["stage"]["id"] == stage_id else 0
        return total

    def view(self, recipe: str, stage: str, outs: list[dict]) -> None:
        """The current outputs of a stage as `views/<recipe>/<stage key>/<name>`."""
        for o in outs:
            dst = self.root / "views" / recipe / stage / o["name"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.unlink(missing_ok=True)
            link_or_copy(self.obj(o["sha256"]), dst)
