# ruff: noqa: E501
"""Test support: independent reference implementations of the runner's pure formulas (spec 002) and a store seeder.

These are the ORACLES: written from the requirement text (FR-002-08, FR-002-09, plan.md D3 and D7), with `hashlib`
and sorted-compact `json.dumps` (equal to RFC 8785 for integers, ASCII strings, booleans, null and nested
containers, which is all they are fed). They never import first-party runner code.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import runner_world as rw


def jcs(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def ref_key(
    stage_key: dict, code: str, lock: str, params: dict, seed: int, inputs: dict, binaries: dict, shard: dict | None
) -> str:
    return sha(
        jcs(
            {
                "stage": stage_key,
                "code": code,
                "lock": lock,
                "params": params,
                "seed": seed,
                "inputs": inputs,
                "binaries": binaries,
                "shard": shard,
            }
        )
    )


def ref_seed(seed0: int, key: str, i: int) -> int:
    return int.from_bytes(hashlib.sha256(jcs([seed0, key, i])).digest()[:8], "big") & (2**63 - 1)


def ref_code_digest(repo: Path, env: str) -> str:
    roots = [*rw.ENV_CODE_ROOTS[env], "src/pitstudio/runner/stagekit"]
    entries = []
    for r in roots:
        base = repo / r
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            rel = p.relative_to(repo).as_posix()
            parts = set(rel.split("/"))
            if (
                not p.is_file()
                or parts & {"__pycache__", ".venv", ".pytest_cache", "node_modules"}
                or any(x.endswith(".egg-info") for x in parts)
                or rel.endswith(".pyc")
            ):
                continue
            entries.append([rel, sha(p.read_bytes())])
    entries.sort(key=lambda e: e[0])
    return sha(jcs(entries))


def ref_lock_digest(repo: Path, env: str) -> str:
    return sha((repo / rw.ENV_LOCK_ROOT[env] / "uv.lock").read_bytes())


def key_str(s: dict[str, Any]) -> str:
    return s["id"] + (f"@{s['variant']}" if s.get("variant") else "")


def output_bytes(stage_key: str, path: str) -> bytes:
    """Content of the pseudo output the seeder stores for (stage key, output path)."""
    return f"seeded object of {stage_key}/{path}\n".encode()


def reference_keys(repo: Path, doc: dict[str, Any], hit: set[str] | None = None) -> dict[str, str | None]:
    """Cache key of every stage when all stages in `hit` (default: all) are cached; None for a stage whose key cannot
    be computed because an upstream stage is not cached. Every stage of `doc` must carry a variant (see the red report)."""
    by = {key_str(s): s for s in doc["stages"]}
    hit = set(by) if hit is None else hit
    order: list[str] = []
    seen: set[str] = set()

    def visit(k: str) -> None:
        if k in seen:
            return
        seen.add(k)
        for i in by[k]["inputs"]:
            if "stage" in i:
                visit(i["stage"] + (f"@{i['variant']}" if i.get("variant") else ""))
        order.append(k)

    for k in sorted(by):
        visit(k)
    keys: dict[str, str | None] = {}
    for k in order:
        s = by[k]
        inputs: dict[str, str] = {}
        ok = True
        for i in s["inputs"]:
            if "stage" in i:
                uk = i["stage"] + (f"@{i['variant']}" if i.get("variant") else "")
                if keys.get(uk) is None or uk not in hit:
                    ok = False
                    break
                inputs[f"{uk}/{i['output']}"] = sha(output_bytes(uk, i["output"]))
            else:
                inputs[i["id"]] = i["sha256"]
        if not ok:
            keys[k] = None
            continue
        keys[k] = ref_key(
            {"id": s["id"], "variant": s["variant"]},
            ref_code_digest(repo, s["env"]),
            ref_lock_digest(repo, s["env"]),
            s.get("params", {}),
            ref_seed(doc["seed"], k, 0),
            inputs,
            {b["id"]: b["sha256"] for b in s.get("binaries", [])},
            None,
        )
    return keys


def seed_store(store: Path, repo: Path, doc: dict[str, Any]) -> dict[str, str]:
    """Write the objects and index entries of a fully cached run of `doc` (plan.md D3 layout); returns stage key -> cache key."""
    keys = reference_keys(repo, doc)
    for s in doc["stages"]:
        k = key_str(s)
        outs = []
        for o in s["outputs"]:
            data = output_bytes(k, o["path"])
            d = sha(data)
            p = store / "cas" / "sha256" / d[:2] / d
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            outs.append({"name": o["path"], "sha256": d, "bytes": len(data)})
        ck = keys[k]
        assert ck is not None
        entry = {
            "stage": {"id": s["id"], "variant": s["variant"]},
            "outputs": outs,
            "run_id": "20261004T120000Z-seeded",
            "created": "2026-10-04T12:00:00Z",
        }
        ip = store / "index" / ck[:2] / f"{ck}.json"
        ip.parent.mkdir(parents=True, exist_ok=True)
        ip.write_text(json.dumps(entry, sort_keys=True), encoding="utf-8")
    return {k: v for k, v in keys.items() if v is not None}
