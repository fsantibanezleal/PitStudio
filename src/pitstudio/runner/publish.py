"""`studio publish`: a finished run as static web files, and published telemetry (FR-002-48..50)."""

# ruff: noqa: E501

from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

from pitstudio.runner.cache import Store, file_sha, sha, write_atomic
from pitstudio.runner.recipe import RUN_ID, Usage, first_errors, kstr, load_yaml, one_line

LOCAL_ONLY = "measured locally, not published (licence)"
RANK = ["public-domain", "open-no-attribution", "own", "attribution", "share-alike", "display-only", "reference-only"]
TAG = re.compile(r"assets-v[0-9]+\.[0-9]{2}\.[0-9]{3}")
PRIVATE = [re.compile(p) for p in (r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", r"\\\\[A-Za-z0-9._$-]+\\", r"(^|[\s\"'=(,:])/(home|Users|root|tmp|var|mnt|media|opt|srv|private|run)/")]  # fmt: skip


def _bucket(rows: list[dict], start: float) -> dict:
    """One point: mean utilisation, power and clock; maximum temperature and memory; OR of the clock-event masks."""

    def col(f: str) -> list:
        return [r[f] for r in rows if r.get(f) is not None]

    mean = {
        f: round(math.fsum(col(f)) / len(col(f)), 3) if col(f) else None
        for f in ("util_pct", "power_w", "sm_clock_mhz")
    }
    mask = None
    for m in col("clocks_event_mask"):
        mask = (mask or 0) | m
    return {"t_s": start, **mean, "temp_c": max(col("temp_c"), default=None), "mem_used_bytes": max(col("mem_used_bytes"), default=None), "clocks_event_mask": mask}  # fmt: skip


def downsample(samples: list[dict], *, max_points: int = 2000) -> dict:
    """Equal-time buckets over the run (a series that fits is kept sample by sample)."""
    rows = sorted(samples, key=lambda s: s["t_s"])
    if len(rows) <= max_points:
        return {
            "bucket_s": (rows[-1]["t_s"] - rows[0]["t_s"]) / (len(rows) - 1) or 1.0 if len(rows) > 1 else 1.0,
            "points": [_bucket([r], r["t_s"]) for r in rows],
        }
    t0, width = rows[0]["t_s"], (rows[-1]["t_s"] - rows[0]["t_s"]) / max_points or 1.0
    groups: dict[int, list[dict]] = {}
    for r in rows:
        groups.setdefault(min(max_points - 1, int((r["t_s"] - t0) / width)), []).append(r)
    return {"bucket_s": width, "points": [_bucket(g, t0 + k * width) for k, g in sorted(groups.items())]}


def published_telemetry(run_id: str, stages: list[dict], *, max_points: int = 2000, max_bytes: int = 204800) -> dict:
    """At most `max_points` per stage; the bucket count is halved until the JSON text fits `max_bytes`."""
    while True:
        doc = {
            "run_id": run_id,
            "stages": [
                {"key": s["key"], "performance": "public", **downsample(s["samples"], max_points=max_points)}
                for s in stages
            ],
        }
        if len(json.dumps(doc, separators=(",", ":")).encode()) <= max_bytes or max_points <= 1:
            return doc
        max_points //= 2


def _strings(o: Any):
    yield from (
        [o]
        if isinstance(o, str)
        else (s for v in (o.values() if isinstance(o, dict) else o if isinstance(o, list) else ()) for s in _strings(v))
    )


def _licence(kind: str, inputs: list[dict], sources: dict[str, dict]) -> dict:
    """Licence class (the lattice maximum), SPDX id and attribution of an artefact (plan.md D3)."""
    srcs = [sources[i["id"]] for i in inputs if i["kind"] == "source" and i["id"] in sources]
    cls = max(["own", *(s["licence_class"] for s in srcs)], key=RANK.index)
    texts = list(dict.fromkeys(s["attribution"] for s in srcs if s.get("attribution")))
    if cls == "reference-only" or len("; ".join(texts)) > 1000:
        raise Usage("an input is reference-only, or the attribution text exceeds 1,000 characters (licence)")
    if cls == "display-only":
        texts.insert(0, "Built on NVIDIA Cosmos")
    cc = any(s["spdx"] == "LicenseRef-Copernicus-CLMS" for s in srcs)
    spdx = {
        "share-alike": next((s["spdx"] for s in srcs if s["licence_class"] == cls), ""),
        "display-only": "LicenseRef-NVIDIA-Open-Model",
    }.get(cls)
    spdx = spdx or (
        "Apache-2.0" if kind == "onnx" else "LicenseRef-Copernicus-CLMS" if cls == "attribution" and cc else "CC-BY-4.0"
    )
    return {
        "licence_class": cls if RANK.index(cls) > 2 else "own",
        "spdx": spdx,
        **({"attribution": "; ".join(texts)} if texts else {}),
    }


def _lane(kind: str, lm: dict | None) -> str:
    """`live` iff web drivable, small, fast and with a bounded trace (the lane gate); stills are `static`."""
    if kind in ("image", "figure", "table", "text", "model-card", "usd"):
        return "static"
    fast = lm and any(
        lm[k] is not None and lm[k] <= limit for k, limit in (("interaction_ms", 16), ("run_ms_t2", 1000))
    )
    live = (
        fast and lm["web_drivable"] and lm["max_asset_bytes"] <= 25_000_000 and (lm["trace_bytes"] or 0) <= 10_000_000
    )
    return "live" if live else "replay"


def _refuse_unfit(m: dict, events: list[dict]) -> None:
    if not events or events[-1]["type"] != "run-finished":
        raise Usage("run is not finished (no run-finished event)")
    why = {"a dirty tree (uncommitted changes)": m["git_dirty"], "the test launcher": m["launcher"] != "uv", "the fake GPU backend": (m["gpu"] or {}).get("backend") == "fake",
           "profiling": any("profiled" in n for n in m.get("notes", []))}  # fmt: skip
    if bad := [t for t, hit in why.items() if hit]:
        raise Usage(f"run was made with {' and '.join(bad)}: it cannot be published")


def publish(store_dir: Path, repo: Path, run_id: str, tag: str | None) -> list[str]:
    """Write the published files of a run; every refusal is a `Usage` raised before the first write."""
    if not RUN_ID.fullmatch(run_id):
        raise Usage(f"{one_line(run_id, 60)!r} is not a run id")
    run, store = store_dir / "runs" / run_id, Store(store_dir)
    try:
        m = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        events = [json.loads(x) for x in (run / "events.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    except OSError, ValueError:
        raise Usage(f"unknown run {run_id}") from None
    _refuse_unfit(m, events)
    rpath = repo / "studio" / "recipes" / m["recipe"]["path"]
    if not rpath.is_file() or file_sha(rpath) != m["recipe"]["sha256"]:
        raise Usage("the recipe changed since the run (sha256 differs)")
    recipe, sf = load_yaml(rpath, "recipe"), repo / "data" / "sources.yaml"
    sources = {s["id"]: s for s in (load_yaml(sf, "sources") or {}).get("sources", [])} if sf.is_file() else {}
    by, arts, copies = {kstr(s["key"]): s for s in m["stages"]}, [], []
    for st in recipe["stages"]:
        wanted, rec = [o for o in st["outputs"] if o.get("publish")], by.get(kstr(st))
        if not wanted:
            continue
        if rec is None or rec["status"] != "succeeded":
            raise Usage(f"stage {kstr(st)} did not succeed: its output cannot be published")
        if bad := next(
            (
                i["id"]
                for i in rec["inputs"]
                if i["kind"] == "source"
                and any(f.get("sha256") is None for f in sources.get(i["id"], {}).get("files", []))
            ),
            None,
        ):
            raise Usage(f"source {bad} is not pinned (no sha256 digest for every file)")
        try:
            facts = {
                o["path"]: o.get("artefact") or {}
                for o in json.loads((run / "tmp" / kstr(st) / "0" / "result.json").read_text(encoding="utf-8"))[
                    "outputs"
                ]
            }
        except OSError, ValueError, KeyError:
            facts = {}
        for o in wanted:
            done, f = {x["name"]: x for x in rec["outputs"]}[o["path"]], facts.get(o["path"])
            if not f:
                raise Usage(f"no artefact facts reported for {kstr(st)}/{o['path']}")
            host = "release" if done["bytes"] >= 10 * 2**20 else "git"
            path = f"assets/{run_id}/{o['path']}" if host == "git" else f"{run_id}-{o['path'].replace('/', '-')}"
            a = {"id": re.sub(r"[^a-z0-9_-]+", "-", f"{recipe['id']}-{kstr(st)}-{o['path']}".lower())[:96], "run_id": run_id, "git_sha": m["git_sha"], "path": path,
                 "bytes": done["bytes"], "sha256": done["sha256"], "kind": f["kind"], "producer": {"tool": rec["tool"], "stage": rec["key"]}, "inputs": rec["inputs"],
                 "lane": _lane(f["kind"], f.get("lane_measurements")), "asset_host": host, "budget_class": f["budget_class"],
                 **{k: f[k] for k in ("media_type", "cases", "encoder", "lane_measurements") if k in f}, **_licence(f["kind"], rec["inputs"], sources)}  # fmt: skip
            if a["lane"] == "static":
                a.pop("lane_measurements", None)
            if host == "release" and not (tag and TAG.fullmatch(tag)):
                raise Usage("a release asset needs a well-formed --release-tag (assets-vN.NN.NNN)")
            a |= {"release_tag": tag} if host == "release" else {}
            arts.append(a)
            copies.append(
                (
                    store.obj(done["sha256"]),
                    repo / "web" / "public" / path if host == "git" else store_dir / "publish" / str(tag) / path,
                )
            )
    pub = {**m, "published": True, "artefacts": arts, "stages": []}
    for s in m["stages"]:
        s = {k: v for k, v in s.items() if k != "log_tail"}
        if s["performance"] == "local-only":
            s["telemetry"], s["attempts"] = (
                LOCAL_ONLY,
                [{k: v for k, v in a.items() if k != "duration_s"} for a in s["attempts"]],
            )
            s.pop("wall_s", None), s.pop("throughput", None)
        pub["stages"].append(s)
    if errs := first_errors("manifest", pub, "#/$defs/run", n=2):
        raise Usage(f"published manifest is invalid: {'; '.join(errs)}")
    if any(p.search(t) for t in _strings(pub) for p in PRIVATE):
        raise Usage("the published manifest holds an absolute path (privacy rule)")
    idx_path = repo / "web" / "public" / "assets" / "manifest.json"
    idx, body = json.loads(idx_path.read_text(encoding="utf-8")), json.dumps(pub, indent=1) + "\n"
    idx["runs"] = [r for r in idx["runs"] if r["run_id"] != run_id] + [
        {"run_id": run_id, "manifest": f"{run_id}/manifest.json", "sha256": sha(body.encode())}
    ]
    idx["artefacts"] = [a for a in idx["artefacts"] if a["run_id"] != run_id] + arts
    samples: dict[str, list[dict]] = {}
    for line in (
        (run / "telemetry.jsonl").read_text(encoding="utf-8").splitlines()
        if (run / "telemetry.jsonl").is_file()
        else []
    ):
        samples.setdefault(kstr((r := json.loads(line))["stage"]), []).append(r)
    stages = [
        {"key": by[k]["key"], "samples": v} for k, v in samples.items() if k in by and by[k]["performance"] == "public"
    ]
    tele = published_telemetry(run_id, stages)
    if errs := first_errors("manifest", idx, "#/$defs/web_index", n=1) or first_errors(
        "events", tele, "#/$defs/published_telemetry", n=1
    ):
        raise Usage(f"a published file would be invalid: {errs[0]}")
    for src, dst in copies:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    out = repo / "web" / "public" / "assets" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=True)
    write_atomic(out / "manifest.json", body)
    write_atomic(out / "telemetry.json", json.dumps(tele, separators=(",", ":")))
    write_atomic(idx_path, json.dumps(idx, indent=1) + "\n")
    (run / "PINNED").write_text("pinned by studio publish\n", encoding="utf-8")
    return [f"published {run_id}: {len(arts)} artefact(s)"]
