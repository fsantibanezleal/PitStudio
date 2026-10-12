"""The `studio` command line (plan.md D1, exit codes D2): usage errors are one line and exit 2."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from pathlib import Path

from pitstudio.runner import gc, locks, publish, queue, worker
from pitstudio.runner.cache import Store, jcs
from pitstudio.runner.gpu import BackendInitError, backend_spec, load_backend
from pitstudio.runner.recipe import (
    RUN_ID,
    Usage,
    capacity,
    find_recipe,
    kstr,
    load_device,
    load_module,
    load_profile,
    load_recipe,
    one_line,  # fmt: skip
    plan,
    recipe_path,
    repo_root,
    select,
    store_root,
)

STAGE_KEY = re.compile(r"[a-z][a-z0-9_]{1,31}(@[a-z0-9][a-z0-9-]{0,31})?")
JOB_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}")
FLAG, GPU = {"action": "store_true"}, ("--gpu-backend", {})
SPEC = {"plan": [("recipe", {}), ("--profile", {"required": True}), ("--json", FLAG), GPU],
        "run": [("recipe", {"nargs": "?"}), ("--profile", {}), ("--stage", {"action": "append", "default": []}), ("--resume", {}),
                ("--force", FLAG), ("--rerun-check", FLAG), ("--detach", FLAG), GPU],
        "worker": [GPU], "status": [("--json", FLAG)], "publish": [("run_id", {}), ("--release-tag", {})],
        "gc": [("--keep-last", {"type": int, "default": 3}), ("--keep-pinned", FLAG), ("--dry-run", FLAG), ("--verify", FLAG)],
        "profile": [("recipe", {}), ("--profile", {"required": True}), ("--stage", {"required": True}), GPU]}  # fmt: skip


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise Usage(message)


def build() -> Parser:
    p = Parser(prog="studio", description="PitStudio job runner", allow_abbrev=False)
    sub = p.add_subparsers(dest="cmd", parser_class=Parser)
    for name, args in SPEC.items():
        c = sub.add_parser(name, allow_abbrev=False)
        for flag, kw in args:
            c.add_argument(flag, **kw)
    q = sub.add_parser("queue", allow_abbrev=False).add_subparsers(dest="qcmd", parser_class=Parser)
    q.add_parser("ls", allow_abbrev=False).add_argument("--json", action="store_true")
    q.add_parser("cancel", allow_abbrev=False).add_argument("job_id")
    return p


def hold_gate() -> int | None:
    """Exit code 4 with the hold reason before any GPU library or lock is touched (FR-002-16)."""
    directory = locks.lock_dir(strict=True)
    if (why := locks.hold_reason(directory)) is None:
        return None
    print(f"GPU hold in {directory / 'gpu0.hold'}: {why} -- not starting", file=sys.stderr)
    return 4


def check_backend(flag: str | None) -> str:
    """The backend named on the command line or in PITSTUDIO_GPU_BACKEND must be `nvml` or a valid fake device file."""
    spec = backend_spec(flag)
    if spec != "nvml" and not (spec.startswith("fake:") and spec[5:]):
        raise Usage(f"--gpu-backend must be nvml or fake:<device file>, got {one_line(spec, 60)!r}")
    if spec.startswith("fake:"):
        load_device(Path(spec[5:]))
    return spec


def do_plan(ns: argparse.Namespace) -> int:
    repo = repo_root()
    path, prof = recipe_path(repo, ns.recipe), load_profile(repo, ns.profile)
    store, spec, backend = Store(store_root(prof)), check_backend(ns.gpu_backend), None
    if spec.startswith("fake:"):  # planning never touches NVML: a real device size comes from the profile
        with contextlib.suppress(BackendInitError):
            backend = load_backend(spec)
    result = plan(repo, load_recipe(repo, path), prof, store, capacity(prof, backend))
    if ns.json:
        print(jcs(result).decode("utf-8"))
        return 0
    print(f"recipe {result['recipe']} profile {result['profile']}")
    for r in result["stages"]:
        print(f"{r['key']:<30} {r['status']:<13} env={r['env']} tool={r['tool']} lock={r['lock'] or '-'} key={(r['cache_key'] or '-')[:12]} "
              f"vram={r['vram_gib_est'] or '-'} disk={r['disk_gib_est'] or '-'} shards={r['shards']}")  # fmt: skip
    return 0


def resume_info(repo: Path, store_dir: Path, run_id: str) -> tuple[Path, str]:
    """The recipe file and profile id of an earlier run: from its manifest, else from the job that started it."""
    if not (store_dir / "runs" / run_id).is_dir():
        raise Usage(f"unknown run {run_id}")
    try:
        m = json.loads((store_dir / "runs" / run_id / "manifest.json").read_text(encoding="utf-8"))
        return repo / "studio" / "recipes" / m["recipe"]["path"], m["profile"]
    except OSError, ValueError, KeyError:
        job = next((j for j in queue.jobs() if j["run_id"] == run_id), None)
        if job is None:
            raise Usage(f"unknown run {run_id}") from None
        return find_recipe(repo, job["recipe"]), queue.request_of(job["job_id"])["profile"]


def submit(ns: argparse.Namespace) -> int:
    """Validate everything, enqueue one job and (unless --detach or another worker runs) work until it ends."""
    repo, profiling = repo_root(), ns.cmd == "profile"
    resume, want = getattr(ns, "resume", None), [ns.stage] if profiling else ns.stage
    if (resume and not RUN_ID.fullmatch(resume)) or not (resume or (ns.recipe and ns.profile)):
        raise Usage("run needs a recipe and --profile, or a valid --resume <run id>")
    if bad := next((k for k in want if not STAGE_KEY.fullmatch(k)), None):
        raise Usage(f"{one_line(bad, 40)!r} is not a stage key")
    prof = load_profile(repo, ns.profile) if ns.profile else None
    store_dir = store_root(prof)
    path, prof_id = resume_info(repo, store_dir, resume) if resume else (recipe_path(repo, ns.recipe), None)
    prof, doc = prof or load_profile(repo, prof_id), load_recipe(repo, path)
    if path.stem != doc["id"]:
        raise Usage(f"{path.name}: the recipe id {doc['id']} must equal the file name")
    chosen = select(doc, want, profiling)
    check_backend(ns.gpu_backend)
    locks.lock_dir(strict=True)
    if (
        any(kstr(s) in chosen and s["resources"]["gpu"] != "none" for s in doc["stages"])
        and (code := hold_gate()) is not None
    ):
        return code
    req = {"recipe": doc["id"], "profile": prof["id"], "stages": want, "force": getattr(ns, "force", False), "profiling": profiling,
           "rerun_check": getattr(ns, "rerun_check", False), "gpu_backend": ns.gpu_backend, "resume": resume}  # fmt: skip
    job_id = queue.enqueue(req)
    if getattr(ns, "detach", False):
        print(f"queued {job_id}")
        return 0
    if (code := worker.drain(until=job_id)) is None:
        print(f"queued {job_id}: another worker owns the store")
        return 0
    if (
        profiling
        and (note := store_dir / "runs" / (queue.job(job_id)["run_id"] or "-") / "profile" / "command.txt").is_file()
    ):
        print(note.read_text(encoding="utf-8").strip())
    return code


def do_worker(ns: argparse.Namespace) -> int:
    store_root()
    check_backend(ns.gpu_backend)
    return hold_gate() or (3 if worker.drain() is None else 0)


def line(j: dict) -> str:
    s, sh = j["stage"], j["shards"]
    done = f"{sh['done']}/{sh['total']}" if sh else "-"
    return f"{j['job_id']} {j['recipe']} {j['state']} {j['run_id'] or '-'} {kstr(s) if s else '-'} {done}"


def active_locks(directory: Path) -> list[str]:
    try:
        from filelock import FileLock, Timeout
    except ImportError:
        return []
    held = []
    for p in sorted(directory.glob("gpu*")) if directory.is_dir() else []:
        if not p.name.endswith((".compute", ".nvenc")):
            continue
        try:
            with FileLock(p, timeout=0):
                pass
        except Timeout:
            held.append(p.name)
    return held


def do_queue(ns: argparse.Namespace) -> int:
    store_root()
    if ns.qcmd == "cancel":
        if not JOB_ID.fullmatch(ns.job_id):
            raise Usage(f"{one_line(ns.job_id, 40)!r} is not a job id")
        print(f"job {ns.job_id}: {queue.cancel(ns.job_id)}")
    elif ns.qcmd == "ls":
        print(json.dumps({"jobs": queue.jobs()}) if ns.json else "\n".join(map(line, queue.jobs())))
    else:
        raise Usage("queue needs ls or cancel")
    return 0


def do_status(ns: argparse.Namespace) -> int:
    store_root()
    directory = locks.lock_dir(strict=True)
    jobs, held, hold = queue.jobs(), active_locks(directory), locks.hold_reason(directory)
    if ns.json:
        print(json.dumps({"jobs": jobs, "locks": held, "hold": hold}))
    else:
        print("\n".join([*map(line, jobs), f"locks: {', '.join(held) or 'none held'}", f"hold: {hold or 'none'}"]))
    return 0


def do_gc(ns: argparse.Namespace) -> int:
    store_dir = store_root()
    if ns.keep_last < 0:
        raise Usage("--keep-last must not be negative")
    if (store_dir / "locks").is_dir():  # a store that never had a worker has no lock to respect
        from filelock import FileLock, Timeout

        try:
            with FileLock(store_dir / "locks" / "worker.lock", timeout=0):
                pass
        except Timeout:
            print("a worker holds locks/worker.lock: gc deletes nothing", file=sys.stderr)
            return 3
    print(
        f"gc: {'would free' if ns.dry_run else 'freed'} {gc.collect(store_dir, repo_root(), ns.keep_last, ns.dry_run, ns.verify)} bytes"
    )
    return 0


def bench(args: list[str]) -> int:
    if args[:1] != ["env"]:
        raise Usage("bench: the only command is `bench env [probe...] [--timeout S] [--no-write]`")
    mod = load_module(repo_root() / "studio" / "bench" / "run_bench.py", "_pitstudio_run_bench")
    try:
        return int(mod.main(["run_bench.py", *args[1:]]))
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2


COMMANDS = {"plan": do_plan, "run": submit, "profile": submit, "worker": do_worker, "queue": do_queue, "status": do_status, "gc": do_gc,
            "publish": lambda ns: print("\n".join(publish.publish(store_root(), repo_root(), ns.run_id, ns.release_tag))) or 0}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args[:1] == ["bench"]:
            return bench(args[1:])
        ns = build().parse_args(args)
        if ns.cmd is None:
            raise Usage("no command given: plan, run, worker, queue, status, gc, publish, bench, profile")
        return COMMANDS[ns.cmd](ns)
    except Usage as e:
        print(f"studio: {one_line(e)}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 6
