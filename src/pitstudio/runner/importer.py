"""`studio import-run`: a finished job of the scratch GPU queue recorded as a run of the store (decision of the main
session, 2026-11-22).

GPU work of P5 ran through a queue of job scripts outside the runner, so the store has no record of it and
`studio publish` had nothing to publish. This module writes the run record such a job would have left, with honest
provenance: the producing job name, the sha256 of its script and log, start and end times, GPU-hours, the digest of
every input and output file, and the label "produced by the GPU queue, outside the runner". Nothing is filled by
guess: a missing script, log, time, GPU-hour figure or output field is named in the notes and the run is labelled
partial. A digest that differs from the one the import spec pins is refused before the first write.

The import spec of a job is `imports/<job>.json` next to this module (or `--spec FILE`): the case, the recipe path,
the stages with their tool and outputs, and per output the file inside the `--from` folder, the artefact facts the
published manifest needs, `local_only` (kept in the store, never published) and `required_fields`.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pitstudio.runner import __version__, import_summaries
from pitstudio.runner.cache import Store, file_sha, jcs, sha, write_atomic
from pitstudio.runner.recipe import SLUG, Usage, first_errors, load_yaml, one_line
from pitstudio.runner.worker import git_state

LABEL = "produced by the GPU queue, outside the runner"
SPEC_DIR = Path(__file__).parent / "imports"
ZERO = "0" * 64
QUEUE_LINE = re.compile(r"\[queue (\d\d):(\d\d):(\d\d)\] (start|done|FAILED) (\S+)")


def _stamp(t: datetime, ms: bool = False) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S") + (f".{t.microsecond // 1000:03d}" if ms else "") + "Z"


def load_spec(job: str, spec: str | None) -> dict:
    path = Path(spec) if spec else SPEC_DIR / f"{job}.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        raise Usage(f"no import spec for job {one_line(job, 60)}") from None
    if doc.get("job") != job or not isinstance(doc.get("stages"), list) or not doc["stages"]:
        raise Usage(f"{path.name}: the import spec must name job {one_line(job, 60)} and at least one stage")
    return doc


def queue_facts(job: str) -> tuple[dict[str, Any], list[str]]:
    """Script, log, times and the missing pieces of a queue job; the queue folder is PITSTUDIO_GPU_QUEUE."""
    qdir = Path(os.environ["PITSTUDIO_GPU_QUEUE"]) if os.environ.get("PITSTUDIO_GPU_QUEUE") else None
    facts: dict[str, Any] = {"script": None, "log": None, "end": None, "duration_s": None}
    missing: list[str] = []
    if qdir is None or not qdir.is_dir():
        return facts, ["queue folder not given (PITSTUDIO_GPU_QUEUE): script, log and times missing"]
    script = next((p for d in ("done", "failed", "jobs") if (p := qdir / d / f"{job}.sh").is_file()), None)
    log = qdir / f"{job}.log"
    if script is None:
        missing.append("script missing")
    else:
        facts["script"] = file_sha(script)
    if not log.is_file():
        missing.append("log missing")
    else:
        facts["log"], facts["log_text"] = file_sha(log), log.read_text(encoding="utf-8", errors="replace")
        facts["end"] = datetime.fromtimestamp(log.stat().st_mtime, UTC).replace(microsecond=0)
    try:
        rows = [QUEUE_LINE.fullmatch(x.strip()) for x in (qdir / "queue.log").read_text(encoding="utf-8").splitlines()]
        secs = [(int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]), m[4]) for m in rows if m and m[5] == job]
        ends = [i for i, (_, kind) in enumerate(secs) if kind != "start"]
        starts = [s for s, kind in secs[: ends[-1]] if kind == "start"] if ends else []
        if starts:
            facts["duration_s"] = (secs[ends[-1]][0] - starts[-1]) % 86400
    except OSError:
        pass
    if facts["duration_s"] is None:
        missing.append("start time missing")
    return facts, missing


def _dig(doc: Any, path: list[str]) -> Any:
    for k in path:
        doc = doc.get(k) if isinstance(doc, dict) else None
    return doc


def _gpu_hours(g: dict | None, src: Path) -> float | None:
    """GPU-hours from the job's own files: the value at `path` of `file` (or summed over `files`), over `divide`."""
    if not g:
        return None
    try:
        vals = [
            _dig(json.loads((src / f).read_text(encoding="utf-8")), g["path"]) for f in g.get("files", [g.get("file")])
        ]
    except OSError, ValueError, TypeError:
        return None
    if g.get("each"):
        vals = [sum(x[g["each"]] for x in v) if isinstance(v, list) else None for v in vals]
    vals = [v.get("gpu_hours") if isinstance(v, dict) else v for v in vals]
    if not vals or not all(isinstance(v, int | float) for v in vals):
        return None
    return round(sum(vals) / g.get("divide", 1), 4)


def import_run(store_dir: Path, repo: Path, job: str, src: Path, spec_file: str | None = None) -> list[str]:
    """Write the run of a queue job into the store; every refusal is a `Usage` raised before the first write."""
    spec = load_spec(job, spec_file)
    if not src.is_dir():
        raise Usage(f"--from {one_line(src, 80)} is not a folder")
    if not SLUG.fullmatch(spec.get("slug", "")) or not re.fullmatch(r"C1|[A-E][1-3]", spec.get("case", "")):
        raise Usage("the import spec needs a slug and a case id")
    recipe_path = repo / "studio" / "recipes" / spec["recipe"]
    tools = {t["id"]: t for t in load_yaml(repo / "studio" / "tools.yaml", "tool registry")["tools"]}
    notes: list[str] = []
    partial: list[str] = []
    facts, qmiss = queue_facts(job)
    partial += qmiss
    partial += spec.get("partial_reasons", [])
    hours = _gpu_hours(spec.get("gpu_hours"), src)
    if hours is None and (m := re.search(r"GPU hours ([0-9.]+)", facts.get("log_text", ""))):
        hours = float(m[1])
    if not isinstance(hours, int | float):
        hours = None
        partial.append("GPU-hours missing")
    end = facts["end"] or datetime.now(UTC).replace(microsecond=0)
    dur = facts["duration_s"] or 0
    begin = end - timedelta(seconds=dur)
    git_sha, dirty = git_state(repo)
    rid = f"{end.strftime('%Y%m%dT%H%M%SZ')}-{spec['slug']}"
    if (store_dir / "runs" / rid).exists():
        raise Usage(f"run {rid} is already in the store")
    files: dict[str, Path] = {}
    derived: dict[str, bytes] = {}
    outs: dict[str, dict] = {}
    for st in spec["stages"]:
        if st.get("tool") not in tools:
            raise Usage(f"stage {one_line(st.get('id'), 40)}: unknown tool {one_line(st.get('tool'), 40)}")
        for o in st["outputs"]:
            if o["name"] in outs:
                raise Usage(f"output {one_line(o['name'], 80)} is listed twice")
            if "derive" in o:
                try:
                    derived[o["name"]] = import_summaries.build(o["derive"], src, rid)
                except import_summaries.Missing as e:
                    raise Usage(f"{o['name']}: {one_line(e)}") from None
                data, path = derived[o["name"]], None
            else:
                path = src / o["from"]
                if not path.is_file():
                    raise Usage(
                        f"output {one_line(o['name'], 80)}: {one_line(o['from'], 80)} is not in the --from folder"
                    )
                data = None
            digest = sha(data) if data is not None else file_sha(path)
            if o.get("sha256") and o["sha256"] != digest:
                raise Usage(f"output {one_line(o['name'], 80)}: digest differs from the pinned one (refused)")
            raw = data if data is not None else None
            if o.get("required_fields"):
                try:
                    doc = json.loads(raw if raw is not None else path.read_bytes())
                except ValueError:
                    doc = None
                partial.extend(
                    f"{o['name']} lacks field {f}: marked missing"
                    for f in o["required_fields"]
                    if not isinstance(doc, dict) or f not in doc
                )
            outs[o["name"]] = {**o, "stage": st["id"], "variant": st.get("variant"), "sha256": digest}
            if path is not None:
                files[o["name"]] = path
    bundles = {b["id"]: json.loads(import_summaries.build(b["derive"], src, rid)) for b in spec.get("bundles", [])}
    for bid, doc in bundles.items():
        if errs := first_errors("results", doc, n=2):
            raise Usage(f"bundle {bid} is invalid: {'; '.join(errs)}")

    recipe = {"id": spec["slug"], "path": spec["recipe"], "sha256": ZERO}
    if recipe_path.is_file():
        recipe |= {
            "id": str((load_yaml(recipe_path, "recipe") or {}).get("id", spec["slug"])),
            "sha256": file_sha(recipe_path),
        }
    else:
        partial.append(f"recipe {spec['recipe']} is not written yet: its sha256 is recorded as zeros")

    notes += [
        LABEL,
        f"job {job}; script sha256 {facts['script'] or 'missing'}; log sha256 {facts['log'] or 'missing'}",
        f"started {_stamp(begin)}; ended {_stamp(end)}; GPU-hours {hours if hours is not None else 'missing'}",
        spec["label"],
        "git_sha is the checkout that imported the run, not the code that produced it; launcher uv is recorded for the "
        "contract, the stages were not launched by the runner",
        *spec.get("notes", []),
    ]
    for other in spec.get("also_jobs", []):
        of, om = queue_facts(other)
        notes.append(
            f"also job {other}; script sha256 {of['script'] or 'missing'}; log sha256 {of['log'] or 'missing'}"
        )
        partial += [f"job {other}: {x}" for x in om if "queue folder" not in x]
    if partial:
        notes.append(one_line("partial: " + "; ".join(partial), 300))
    store = Store(store_dir)
    stages = []
    for st in spec["stages"]:
        key = {"id": st["id"], **({"variant": st["variant"]} if st.get("variant") else {})}
        stages.append(
            {
                "key": key,
                "tool": st["tool"],
                "env": {"name": "external", "python": None, "lock_sha256": ZERO, "versions": {}},
                "cache_key": sha(
                    jcs({"import": job, "stage": key, "outputs": {n: outs[n]["sha256"] for n in sorted(outs)}})
                ),
                "cache": "miss",
                "status": "succeeded",
                "exit_code": 0,
                "error_class": None,
                "attempts": [{"n": 1, "error_class": None, "duration_s": float(dur)}],
                "params": {},
                "seed": int(spec.get("seed", 0)),
                "determinism": {"class": "none", "rerun_check": "not-applicable"},
                "performance": tools[st["tool"]]["performance"],
                "wall_s": float(dur),
                "telemetry": None,
                "thermal_flag": False,
                "inputs": [],
                "outputs": [],
            }
        )
    manifest = {
        "kind": "run",
        "schema_version": "1.0",
        "run_id": rid,
        "recipe": recipe,
        "git_sha": git_sha,
        "git_dirty": dirty,
        "runner_version": __version__,
        "created": _stamp(end),
        "profile": "imported",
        "seed": int(spec.get("seed", 0)),
        "published": False,
        "launcher": "uv",
        "gpu": None,
        "stages": stages,
        "artefacts": [],
        "notes": notes[:20],
    }
    # objects first (content-addressed), then the run folder; a failure before this point left nothing behind
    tmp = store_dir / "tmp" / f"import-{rid}"
    tmp.mkdir(parents=True, exist_ok=True)
    for name, data in derived.items():
        files[name] = tmp / sha(data)
        files[name].write_bytes(data)
    promoted = {
        o["name"]: o for o in store.promote(manifest["stages"][0]["cache_key"], {"stage": {"id": "import"}}, files)
    }
    for s, st in zip(stages, spec["stages"], strict=True):
        s["outputs"] = [
            {"name": o["name"], "sha256": promoted[o["name"]]["sha256"], "bytes": promoted[o["name"]]["bytes"]}
            for o in st["outputs"]
        ]
    for n, o in outs.items():
        o["bytes"] = promoted[n]["bytes"]
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    if errs := first_errors("manifest", manifest, "#/$defs/run", n=2):
        raise Usage(f"the imported run is not a valid manifest: {'; '.join(errs)}")
    run = store_dir / "runs" / rid
    run.mkdir(parents=True)
    ev = [
        {"seq": 1, "t": _stamp(begin, True), "run_id": rid, "type": "run-started"},
        {
            "seq": 2,
            "t": _stamp(end, True),
            "run_id": rid,
            "type": "run-finished",
            "data": {"state": "succeeded", "exit_code": 0},
        },
    ]
    write_atomic(run / "events.jsonl", "".join(json.dumps(e) + "\n" for e in ev))
    imp = {
        "job": job,
        "case": spec["case"],
        "label": spec["label"],
        "partial": bool(partial),
        "outputs": list(outs.values()),
        "bundles": bundles,
    }
    write_atomic(run / "import.json", json.dumps(imp, indent=1))
    write_atomic(run / "manifest.json", json.dumps(manifest, indent=1))
    return [f"imported {rid}: {len(outs)} output(s){' (partial)' if partial else ''}"]


def imported(run: Path) -> dict | None:
    """The import record of a run folder, or None for a run the worker made."""
    try:
        return json.loads((run / "import.json").read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None


__all__ = ["LABEL", "import_run", "imported"]
