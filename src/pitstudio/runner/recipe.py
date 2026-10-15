"""Strict loading and validation of recipes, profiles and device files, the stage DAG and the plan (FR-002-01..06)."""

from __future__ import annotations

import heapq
import importlib.util
import itertools
import json
import math
import os
import re
import sys
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from pitstudio.contracts.io import load_yaml as contract_yaml
from pitstudio.contracts.io import parse_json_text
from pitstudio.runner.cache import Store, cache_key, code_digest, derive_seed, lock_digest

ROOT = Path(__file__).resolve().parents[3]
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
RUN_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}")
VALIDATOR = re.compile(r"file|json|jsonl|contract-[a-z0-9-]+|stage-[a-z0-9-]{1,42}")
MAX_SHARDS = 10000
BASE_ID = "https://fsantibanezleal.github.io/PitStudio/contracts/"


class Usage(Exception):
    """A usage or validation error: one line, exit code 2."""


def one_line(text: object, limit: int = 300) -> str:
    return " ".join(str(text).split())[:limit]


strict_json = parse_json_text  # the strict loader of spec 001: no NaN, no Infinity, no duplicate keys


def load_yaml(path: Path, what: str = "file") -> Any:
    try:
        return contract_yaml(path)
    except (ValueError, yaml.YAMLError) as e:  # ContractError; a NUL byte escapes it as a reader error
        raise Usage(f"{path.name}: cannot read {what}: {one_line(e)}") from None


@cache
def _schemas() -> tuple[Registry, dict[str, dict]]:
    reg = Registry()
    docs: dict[str, dict] = {}
    for d in (
        ROOT / "contracts",
        *(ROOT / "specs" / s / "contracts" for s in ("001-contracts", "002-runner", "003-console")),
    ):
        for p in sorted(d.glob("*.schema.json")):  # promoted schemas first: a draft never replaces a promoted file
            doc = docs.setdefault(p.name.removesuffix(".schema.json"), json.loads(p.read_text(encoding="utf-8")))
            reg = reg.with_resource(doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012))
    return reg, docs


@cache
def validator(stem: str, target: str = "#") -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"{BASE_ID}{stem}.schema.json{'' if target == '#' else target}"}, registry=_schemas()[0]
    )


def _pointer(e: Any) -> str:
    """JSON pointer of the offending value; a missing or unexpected property is named in it."""
    path = [*map(str, e.absolute_path)]
    if e.validator == "required":
        path += [p for p in e.validator_value if p not in e.instance][:1]
    elif e.validator == "additionalProperties" and isinstance(e.instance, dict):
        path += [k for k in e.instance if k not in e.schema.get("properties", {})][:1]
    return "/" + "/".join(path)


def first_errors(stem: str, doc: Any, target: str = "#", n: int = 3) -> list[str]:
    errs = sorted((_pointer(e), e.message) for e in validator(stem, target).iter_errors(doc))
    return [f"{ptr}: {one_line(msg, 160)}" for ptr, msg in errs[:n]]


def repo_root() -> Path:
    return Path(os.environ.get("PITSTUDIO_REPO") or ROOT).resolve()


def store_root(prof: dict | None = None) -> Path:
    raw = os.environ.get("PITSTUDIO_STORE") or (prof or {}).get("store_default")
    if not raw:
        raise Usage("PITSTUDIO_STORE is not set")
    p, bad, anc = Path(raw), None, Path(raw)
    while not anc.exists() and anc.parent != anc:
        anc = anc.parent
    here, repo = os.path.normcase(str(p.resolve())), os.path.normcase(str(repo_root()))
    if not p.is_absolute():
        bad = "must be an absolute path"
    elif sys.platform == "win32" and len(str(p)) > 64:
        bad = "is longer than 64 characters"
    elif here == repo or here.startswith(repo + os.sep):
        bad = "must not be inside the repository"
    elif not anc.is_dir() or not os.access(anc, os.W_OK) or (p.exists() and not p.is_dir()):
        bad = "is not a writable directory"
    if bad:
        raise Usage(f"PITSTUDIO_STORE {bad}")
    return p


def kstr(d: dict) -> str:
    """The stage key `id` or `id@variant` of a stage, a stage key object or an upstream input."""
    return (d.get("id") or d["stage"]) + (f"@{d['variant']}" if d.get("variant") else "")


def skey(st: dict) -> dict:
    return {"id": st["id"], **({"variant": st["variant"]} if st.get("variant") else {})}


def load_profile(repo: Path, pid: str) -> dict:
    if not SLUG.fullmatch(pid or ""):
        raise Usage(f"profile id {one_line(pid, 40)!r} is not valid")
    p = repo / "studio" / "recipes" / "_profiles" / f"{pid}.yaml"
    if not p.is_file():
        raise Usage(f"unknown profile {pid}")
    doc = load_yaml(p, "profile")
    errs = first_errors("profile", doc) if isinstance(doc, dict) else ["/: not a mapping"]
    idx = [g["index"] for g in doc["gpus"]] if not errs else []
    if not errs and (dup := sorted({i for i in idx if idx.count(i) > 1})):
        errs = [f"repeated GPU index {', '.join(map(str, dup))}"]
    if errs or doc["id"] != pid:
        raise Usage(f"{p.name}: profile-invalid: {'; '.join(errs) or '/id: must equal the file name'}")
    return doc


def _nonfinite(o: Any, ptr: str = "") -> str | None:
    if isinstance(o, float) and not math.isfinite(o):
        return ptr or "/"
    kids = o.items() if isinstance(o, dict) else enumerate(o) if isinstance(o, list) else ()
    return next((r for k, v in kids if (r := _nonfinite(v, f"{ptr}/{k}"))), None)


def load_device(path: Path) -> dict:
    """A fake GPU device file (FR-002-57): schema, finite values, ascending steps, no field scripted and unsupported."""
    doc = load_yaml(path, "device file")
    errs = (
        [f"{bad}: non-finite value"]
        if (bad := _nonfinite(doc))
        else first_errors("profile", doc, "#/$defs/fake_device")
    )
    for f, v in ({} if errs else doc["series"]).items():
        one = Draft202012Validator(_schemas()[1]["profile"]["$defs"]["fake_series"]["properties"][f]["anyOf"][0])
        if isinstance(v, list) and (
            any(b[0] <= a[0] for a, b in itertools.pairwise(v)) or not all(one.is_valid(x[1]) for x in v)
        ):
            errs = [f"/series/{f}: steps must ascend in time and hold values in range"]
    if not errs and (both := [f for f in doc.get("unsupported", []) if f in doc["series"]]):
        errs = [f"/unsupported: {both[0]} is both scripted and unsupported"]
    if errs:
        raise Usage(f"{path.name}: {errs[0]}")
    return doc


def load_module(f: Path, name: str):
    """Import a repository file by path (its folder is importable while it loads)."""
    spec = importlib.util.spec_from_file_location(name, f)
    if spec is None or spec.loader is None:
        raise ImportError(f"{f} cannot be imported")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(f.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(f.parent))
    return mod


def find_recipe(repo: Path, rid: str) -> Path:
    for folder in ("cases", "_bench"):
        if (p := repo / "studio" / "recipes" / folder / f"{rid}.yaml").is_file():
            return p
    raise Usage(f"unknown recipe {rid}")


def recipe_path(repo: Path, raw: str) -> Path:
    """A `.yaml` file inside `studio/recipes/` once links are resolved (FR-002-42)."""
    try:
        p = Path(raw).resolve()
        ok = p.suffix == ".yaml" and p.is_file() and (repo / "studio" / "recipes").resolve() in p.parents
    except OSError, ValueError:
        ok = False
    if not ok:
        raise Usage(f"recipe {one_line(raw, 60)!r} is not a .yaml file inside studio/recipes/")
    return p


def deps_of(doc: dict) -> dict[str, set[str]]:
    return {kstr(s): {kstr(i) for i in s["inputs"] if "stage" in i} for s in doc["stages"]}


def select(doc: dict, want: list[str], profiling: bool = False) -> list[str]:
    """Stage keys of a job in order: all, or the wanted ones plus their ancestors (the wanted ones when profiling)."""
    deps = deps_of(doc)
    if bad := [k for k in want if k not in deps]:
        raise Usage(f"stage {bad[0]} is not in recipe {doc['id']}")
    need = set(want)
    while not profiling and want and (extra := {u for k in need for u in deps[k]} - need):
        need |= extra
    return [k for k in order_or_cycle(deps) if not want or k in need]


def capacity(prof: dict, backend: Any | None) -> int | None:
    """The largest device VRAM known to the plan: the backend (live or fake), else the profile (FR-002-06)."""
    return backend.vram_total_bytes if backend else max((g["vram_bytes"] for g in prof["gpus"]), default=None)


def shard_count(st: dict) -> int:
    sh = st.get("shardable")
    return -(-sh["total"] // sh["shard_size"]) if sh else 1


def load_recipe(repo: Path, path: Path) -> dict:
    doc = load_yaml(path, "recipe")
    if not isinstance(doc, dict) or not isinstance(doc.get("stages"), list):
        raise Usage(f"{path.name}: recipe must be a mapping with a stage list")
    if errs := first_errors("recipe", doc, n=5):
        raise Usage(f"{path.name}: invalid recipe: {'; '.join(errs)}")
    keys, bad = [kstr(s) for s in doc["stages"]], {}
    outputs = {kstr(s): [o["path"] for o in s["outputs"]] for s in doc["stages"]}
    reg = {t["id"] for t in (load_yaml(repo / "studio" / "tools.yaml", "tool registry") or {}).get("tools", [])}
    need = any(s.get("requires") for s in doc["stages"])
    probes = (
        set(load_module(repo / "studio" / "bench" / "run_bench.py", "_pitstudio_run_bench").PROBES) if need else set()
    )
    for s in doc["stages"]:
        why = ["duplicate stage key"] * (keys.count(kstr(s)) > 1)
        why += [
            f"unknown input {kstr(i)}/{i.get('output', '')}"
            for i in s["inputs"]
            if "stage" in i and (kstr(i) not in outputs or i.get("output", outputs[kstr(i)][0]) not in outputs[kstr(i)])
        ]
        why += [
            f"oom fallback key {x!r} not in params"
            for st in s.get("retry", {}).get("oom_fallback", [])
            for x in st
            if x not in s.get("params", {})
        ]
        why += [f"unknown probe {p}" for p in s.get("requires", []) if p not in probes]
        why += [f"tool {s['tool']} is not in studio/tools.yaml"] * (s["tool"] not in reg)
        for v in (o["schema"] for o in s["outputs"]):
            if not VALIDATOR.fullmatch(v) or (v.startswith("contract-") and v[9:] not in _schemas()[1]):
                why.append(f"unknown output validator {v}")
        why += [f"more than {MAX_SHARDS} shards"] * (shard_count(s) > MAX_SHARDS)
        if why:
            bad[kstr(s)] = why
    if not bad:
        order_or_cycle(deps_of(doc), bad)
    if bad:
        raise Usage(f"{path.name}: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(bad.items())))
    return doc


def order_or_cycle(deps: dict[str, set[str]], bad: dict[str, list[str]] | None = None) -> list[str]:
    """Lexicographically smallest topological order; nodes that cannot be ordered are flagged as a cycle in `bad`."""
    left = {k: set(v) for k, v in deps.items()}
    ready = [k for k, v in left.items() if not v]
    heapq.heapify(ready)
    out: list[str] = []
    while ready:
        out.append(k := heapq.heappop(ready))
        for o, v in left.items():
            if k in v:
                v.discard(k)
                if not v and o not in out and o not in ready:
                    heapq.heappush(ready, o)
    stuck = {k for k in left if k not in out}
    while sink := {k for k in stuck if not any(k in left[o] for o in stuck)}:  # drop what only hangs below a cycle
        stuck -= sink
    if bad is not None:
        for k in sorted(stuck):
            bad.setdefault(k, []).append("dependency cycle")
    return out


class Keys:
    """Cache keys of the executions of one recipe (FR-002-08, FR-002-09); digests are read once per environment."""

    def __init__(self, repo: Path, doc: dict) -> None:
        self.repo, self.seed0 = repo, doc["seed"]
        self._d: dict[Any, Any] = {}

    def digests(self, env: str) -> tuple[str, str]:
        if env not in self._d:
            self._d[env] = (code_digest(self.repo, env), lock_digest(self.repo, env))
        return self._d[env]

    def seed(self, st: dict, i: int) -> int:
        return derive_seed(self.seed0, kstr(st), i)

    def key(self, st: dict, params: dict, i: int, inputs: dict[str, str]) -> str:
        sh, (code, lock) = st.get("shardable"), self.digests(st["env"])
        shard = {"index": i, "size": sh["shard_size"], "total": sh["total"]} if sh else None
        bins = {b["id"]: b["sha256"] for b in st.get("binaries", [])}
        return cache_key(
            stage={"id": st["id"], "variant": st.get("variant")},
            code=code,
            lock=lock,
            params=params,
            seed=self.seed(st, i),
            inputs=inputs,
            binaries=bins,
            shard=shard,
        )


def input_map(st: dict, outs: dict[str, dict | None]) -> dict[str, str] | None:
    """Digest of every input by name (FR-002-08), or None while an upstream output is not known."""
    m: dict[str, str] = {}
    for i in st["inputs"]:
        if "stage" not in i:
            m[i["id"]] = i["sha256"]
        elif (up := outs.get(kstr(i))) is None:
            return None
        else:
            m.update({f"{kstr(i)}/{n}": up[n] for n in ([i["output"]] if i.get("output") else sorted(up))})
    return m


def gpu_index(prof: dict) -> int:
    return prof["gpus"][0]["index"] if prof["gpus"] else 0


def lock_name(st: dict, prof: dict) -> str | None:
    kind = {"exclusive": "compute", "nvenc": "nvenc"}.get(st["resources"]["gpu"])
    return f"gpu{gpu_index(prof)}.{kind}" if kind else None


def refusal(st: dict, prof: dict, cap: int | None) -> str | None:
    """`env-disabled` or `does-not-fit` (FR-002-06), decided from the profile alone."""
    if st["env"] not in prof["envs_enabled"]:
        return "env-disabled"
    est = st["resources"].get("vram_gib_est")
    need = math.ceil(est * 2**30) + prof["guards"]["vram_margin_gib"] * 2**30 if est else 0
    return "does-not-fit" if cap is not None and need > cap else None


def plan(repo: Path, doc: dict, prof: dict, store: Store, cap: int | None, outs_only: bool = False) -> dict:
    by, keys, rows = {kstr(s): s for s in doc["stages"]}, Keys(repo, doc), []
    outs: dict[str, dict[str, str] | None] = {}
    for k in order_or_cycle(deps_of(doc)):
        st, res = by[k], by[k]["resources"]
        row = {
            "key": k,
            "env": st["env"],
            "tool": st["tool"],
            "lock": lock_name(st, prof),
            "cache_key": None,
            "status": "pending",
            "vram_gib_est": res.get("vram_gib_est"),
            "disk_gib_est": res.get("disk_gib_est"),
            "shards": shard_count(st),
        }
        outs[k] = None
        if why := refusal(st, prof, cap):
            row["status"] = why
        elif (inputs := input_map(st, outs)) is not None:
            ks = [keys.key(st, st.get("params", {}), i, inputs) for i in range(row["shards"])]
            ents = [store.lookup(x, repair=False) for x in ks]
            row["cache_key"], row["status"] = ks[0], "hit" if all(ents) else "miss"
            first = ents[0]
            outs[k] = {o["name"]: o["sha256"] for o in first["outputs"]} if first and all(ents) else None
        rows.append(row)
    return outs if outs_only else {"recipe": doc["id"], "profile": prof["id"], "stages": rows}
