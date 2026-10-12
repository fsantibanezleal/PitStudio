"""The worker: runs a job's stages in order with guards, locks, retries, shards, resume, manifest and events."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import Any

from pitstudio.runner import __version__, execute, guards, locks, oswin, queue, telemetry
from pitstudio.runner.cache import PROJECT, Store, file_sha, write_atomic
from pitstudio.runner.gpu import BackendInitError, backend_spec, load_backend
from pitstudio.runner.recipe import (
    Keys,
    Usage,
    capacity,
    deps_of,
    find_recipe,
    gpu_index,
    input_map,
    kstr,
    load_module,
    load_profile,
    load_recipe,
    load_yaml,
    lock_name,
    plan,
    refusal,
    repo_root,
    select,
    shard_count,
    skey,
    store_root,
)

KEEP, RELEASE = 0x80000001, 0x80000000
KIT = Path(__file__).resolve().parent / "stagekit"


class Stop(Exception):
    """The job cannot go on: `state` and exit `code` of the job, `status` and `error_class` of the stage."""

    def __init__(self, state: str, code: int, status: str, error_class: str, reason: str) -> None:
        super().__init__(reason)
        self.state, self.code, self.status, self.error_class, self.reason = state, code, status, error_class, reason


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def git_state(repo: Path) -> tuple[str, bool]:
    def git(*a: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, timeout=60).stdout.strip()

    try:
        sha, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    except OSError, subprocess.SubprocessError:
        sha, dirty = "", True
    return (sha, dirty) if re.fullmatch(r"[0-9a-f]{40}", sha) else ("0" * 40, True)


def lock_versions(repo: Path, project: str) -> dict[str, str]:
    try:
        pkgs = tomllib.loads((repo / project / "uv.lock").read_text(encoding="utf-8")).get("package", [])
    except OSError, ValueError:
        return {}
    return {p["name"].lower().replace("_", "-"): p["version"] for p in pkgs if "version" in p}


class Run:
    def __init__(self, job_id: str, req: dict) -> None:
        self.job_id, self.req, self.repo = job_id, req, repo_root()
        self.prof, self.path = load_profile(self.repo, req["profile"]), find_recipe(self.repo, req["recipe"])
        self.doc = load_recipe(self.repo, self.path)
        self.by = {kstr(s): s for s in self.doc["stages"]}
        self.deps = deps_of(self.doc)
        self.keys, self.store, self.lockdir = Keys(self.repo, self.doc), Store(store_root(self.prof)), locks.lock_dir()
        self.force, self.rerun_check, self.profiling = (bool(req.get(k)) for k in ("force", "rerun_check", "profiling"))
        want = [s if isinstance(s, str) else kstr(s) for s in req.get("stages") or []]
        self.order, self.resume = select(self.doc, want, self.profiling), req.get("resume")
        self.run_id = self.resume or self.new_run_id()
        self.dir = self.store.root / "runs" / self.run_id
        self.spec = backend_spec(req.get("gpu_backend"))
        self.launcher = "test" if self.spec.startswith("fake") else "uv"
        self.backend: Any = None
        self.recs, self.done, self.outs, self.tele = [], {}, {}, {}  # stage records, by stage key; outputs; samples
        self.stop: tuple[str, int, str] | None = None
        self.seq, self.whea_at, self.started = 0, 0.0, time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        self.header: dict[str, Any] = {}

    def new_run_id(self) -> str:
        t = time.time()
        while (
            self.store.root / "runs" / (rid := f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(t))}-{self.doc['id']}")
        ).exists():
            t += 1
        return rid

    def ev(
        self, type_: str, st: dict | None = None, shard: int | None = None, detail: str | None = None, **data: Any
    ) -> None:
        self.seq += 1
        doc = {"seq": self.seq, "t": now(), "run_id": self.run_id, "type": type_, **({"stage": skey(st)} if st else {})}
        doc |= ({"shard": shard} if shard is not None else {}) | ({"data": data} if data else {})
        if detail:
            doc["detail"] = execute.scrub(detail, self.repo, self.store.root, self.lockdir)[:300]
        with open(self.dir / "events.jsonl", "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(doc) + "\n")

    def flush(self) -> None:
        write_atomic(
            self.dir / "manifest.json", json.dumps({**self.header, "stages": self.recs, "artefacts": []}, indent=1)
        )

    def go(self) -> tuple[str, int, str | None]:
        self.dir.mkdir(parents=True, exist_ok=True)
        log, mf = self.dir / "events.jsonl", self.dir / "manifest.json"
        self.seq = (
            max((json.loads(x)["seq"] for x in log.read_text(encoding="utf-8").splitlines() if x.strip()), default=0)
            if log.exists()
            else 0
        )
        sha, dirty = git_state(self.repo)
        prev = json.loads(mf.read_text(encoding="utf-8")) if self.resume and mf.exists() else {}
        self.header = {
            "kind": "run",
            "schema_version": "1.0",
            "run_id": self.run_id,
            "git_sha": sha,
            "git_dirty": dirty,
            "runner_version": __version__,
            "recipe": {
                "id": self.doc["id"],
                "path": f"{self.path.parent.name}/{self.path.name}",
                "sha256": file_sha(self.path),
            },
            "created": now()[:19] + "Z",
            "profile": self.prof["id"],
            "seed": self.doc["seed"],
            "published": False,
            "launcher": self.launcher,
            "gpu": None,
            **({"notes": ["profiled run: not publishable"]} if self.profiling else {}),
        }
        self.header |= {k: prev[k] for k in ("created", "git_sha", "git_dirty", "recipe", "seed") if k in prev}
        if any(self.by[k]["resources"]["gpu"] != "none" for k in self.order):
            try:
                b = self.backend = load_backend(self.spec)
                self.header["gpu"] = {
                    "backend": "fake" if self.launcher == "test" else "nvml",
                    "index": gpu_index(self.prof),
                    "name": b.name,
                    "driver": b.driver,
                    "vram_total_bytes": b.vram_total_bytes,
                    "power_limit_enforced_w": telemetry.read_sample(b, "power_limit_w"),
                }
            except BackendInitError:
                self.backend = None
        self.cap = capacity(self.prof, self.backend)
        self.outs = plan(self.repo, self.doc, self.prof, self.store, self.cap, outs_only=True)
        queue.update(self.job_id, run_id=self.run_id)
        self.ev("run-started")
        for k in self.order:
            if self.stop:
                break
            self.do_stage(self.by[k])
        failed = any(r["status"] == "failed" for r in self.recs)
        state, code, reason = self.stop or (("failed", 1, "a stage failed") if failed else ("succeeded", 0, None))
        self.ev("run-finished", state=state, exit_code=code)
        print(f"run {self.run_id}: {state}")
        return state, code, reason

    def record(self, st: dict) -> dict:
        tool, project = self.tools[st["tool"]], PROJECT[st["env"]]
        pkg, py = (
            tool.get("version", {}).get("package", "").lower().replace("_", "-"),
            self.repo / project / ".python-version",
        )
        ver = py.read_text(encoding="utf-8").strip() if py.is_file() else ""
        python = (
            "{}.{}.{}".format(*sys.version_info[:3])
            if self.launcher == "test"
            else ver
            if re.fullmatch(r"3\.\d+(\.\d+)?", ver)
            else None
        )
        found, cls = lock_versions(self.repo, project), st["determinism"]
        cls = cls if isinstance(cls, str) else cls["class"]
        return {
            "key": skey(st),
            "tool": st["tool"],
            "cache_key": self.keys.key(st, st.get("params", {}), 0, {}),
            "cache": "miss",
            "status": "succeeded",
            "env": {
                "name": st["env"],
                "python": python,
                "lock_sha256": self.keys.digests(st["env"])[1],
                "versions": {pkg: found[pkg]} if pkg in found else {},
            },
            "exit_code": None,
            "error_class": None,
            "attempts": [{"n": 1, "error_class": None}],
            "params": st.get("params", {}),
            "seed": self.keys.seed(st, 0),
            "determinism": {"class": cls, "rerun_check": "not-applicable" if cls == "none" else "pending"},
            "performance": tool["performance"],
            "telemetry": None,
            "thermal_flag": False,
            "inputs": [],
            "outputs": [],
        }

    @cached_property
    def tools(self) -> dict[str, dict]:
        return {t["id"]: t for t in load_yaml(self.repo / "studio" / "tools.yaml", "tool registry")["tools"]}

    def do_stage(self, st: dict) -> None:
        k, n, rec = kstr(st), shard_count(st), self.record(st)
        self.recs.append(rec)
        self.done[k] = rec
        self.ev("stage-started", st)
        queue.update(self.job_id, stage=rec["key"], shards={"done": 0, "total": n} if st.get("shardable") else None)
        if st.get("shardable"):
            rec["shards"] = {"total": n, "done": 0}
        dead = next(
            (
                u
                for u in self.deps[k]
                if (self.done[u]["status"] != "succeeded" if u in self.done else self.outs.get(u) is None)
            ),
            None,
        )
        if dead:
            up = self.done.get(dead, {})
            nr = up.get("status") == "not_run" or str(up.get("reason")).startswith("upstream not run")
            rec |= {
                "status": "skipped",
                "reason": f"upstream not run: {dead}" if nr else f"upstream {up.get('status', 'not cached')}: {dead}",
            }
            return self.end(st, rec)
        inputs = input_map(st, self.outs) or {}
        rec["cache_key"] = self.keys.key(st, st.get("params", {}), 0, inputs)
        rec["inputs"] = [
            {
                "id": re.sub(r"[^a-z0-9_-]+", "-", nm.lower()).strip("-")[:96],
                "sha256": d,
                "kind": "artefact" if "/" in nm else "source",
            }
            for nm, d in inputs.items()
        ]
        exs: list[dict] = []
        try:
            for i in range(n):
                exs.append(ex := self.execute(st, i, inputs))
                if "shards" in rec:
                    rec["shards"]["done"] = i + (ex["status"] == "succeeded")
                    queue.update(self.job_id, shards=rec["shards"])
                    self.ev("shard-finished", st, i, cache="hit" if ex["hit"] else "miss", cache_key=ex["key"])
                if ex["status"] != "succeeded":
                    break
            if ex["status"] == "succeeded" and self.rerun_check:
                rec["determinism"] |= self.recheck(st, inputs, exs[0])
        except Stop as s:
            self.stop = (s.state, s.code, s.reason)
            rec |= {
                "status": s.status,
                "error_class": s.error_class,
                "attempts": [{"n": 1, "error_class": s.error_class}],
            }
            print(f"{k}: {s.error_class}: {s.reason}", file=sys.stderr)
            return self.end(st, rec, f"{s.error_class}: {s.reason}")
        first = exs[0]
        rec |= {
            "cache_key": first["key"],
            "params": first["params"],
            "attempts": ex["attempts"],
            "status": ex["status"],
            "exit_code": ex["exit_code"],
            "error_class": ex["error_class"],
            "cache": "hit" if all(e["hit"] for e in exs) and len(exs) == n else "miss",
        }
        rec |= {"outputs": first["outs"]} if ex["status"] == "succeeded" else {}
        rec |= {"wall_s": round(sum(e["wall_s"] for e in exs), 3)} if not ex["hit"] else {}
        rec |= {"throughput": ex["throughput"]} if ex.get("throughput") else {}
        rec |= (
            {"log_tail": ex["tail"]}
            if ex["status"] == "failed"
            else {"reason": ex["reason"]}
            if ex["status"] == "not_run"
            else {}
        )
        if (samples := self.tele.get(k)) and self.backend is not None:
            rec["telemetry"] = telemetry.summarize(samples, sample_hz=self.prof["telemetry_hz"])
            rec["thermal_flag"] = telemetry.thermal_flag(rec["telemetry"])
        self.end(st, rec, ex.get("problem"))

    def end(self, st: dict, rec: dict, detail: str | None = None) -> None:
        k, status = kstr(st), rec["status"]
        self.outs[k] = {o["name"]: o["sha256"] for o in rec["outputs"]} if status == "succeeded" else None
        if status == "not_run":
            self.ev("stage-not-run", st, detail=rec["reason"])
            print(f"not run: {k}: {rec['reason']}")
        self.ev(
            "stage-skipped" if status == "skipped" else "stage-finished",
            st,
            detail=rec.get("reason") if status == "skipped" else detail,
            status=status,
        )
        self.flush()

    # ---- one execution (one shard) -----------------------------------------------------------------------------
    def refuse(self, st: dict, why: str) -> Stop:
        self.ev("guard-refused", st, detail=why, reason=why)
        return Stop("failed", 5, "env-disabled" if why == "env-disabled" else "failed", "guard", why)

    def held(self, st: dict, why: str) -> Stop:
        self.ev("hold-detected", st, detail=why)
        return Stop("held", 4, "held", "hold", why)

    def preflight(self, st: dict) -> None:
        """Hold, profile refusals, capabilities, disk and quota: everything that is decided before a lock is taken."""
        res, g = st["resources"], self.prof["guards"]
        gpu, est = res["gpu"] != "none", res.get("disk_gib_est", 0)
        if gpu and (why := locks.hold_reason(self.lockdir)) is not None:
            raise self.held(st, why)
        caps, quota = self.repo / "studio" / "capabilities.json", self.prof.get("quotas", {}).get(st["id"])
        checks = [
            refusal(st, self.prof, self.cap),
            "no-gpu" if gpu and self.backend is None else None,
            gpu
            and st.get("requires")
            and self.backend
            and guards.capability_refusal(caps, st["requires"], self.backend.driver),
            None if guards.disk_ok(shutil.disk_usage(self.store.root).free, est, g["disk_margin_gib"]) else "disk",
            "quota"
            if quota is not None and not guards.quota_ok(self.store.stage_bytes(st["id"]), est, quota)
            else None,
        ]
        if why := next((c for c in checks if c), None):
            raise self.refuse(st, why)

    def execute(self, st: dict, i: int, inputs: dict[str, str], rerun: bool = False) -> dict:
        g, base = self.prof["guards"], st.get("params", {})
        key0 = self.keys.key(st, base, i, inputs)
        if not (self.force or self.profiling or rerun):

            def corrupt(d: str) -> None:
                self.ev("store-corrupt", st, detail=f"object {d[:12]} failed verification")

            if e := self.store.lookup(key0, on_corrupt=corrupt):
                self.ev("stage-cache-hit", st, i if st.get("shardable") else None)
                return {
                    "hit": True,
                    "key": key0,
                    "params": base,
                    "attempts": [{"n": 1, "error_class": None}],
                    "status": "succeeded",
                    "error_class": None,
                    "exit_code": None,
                    "outs": e["outputs"],
                    "obs": e.get("observables"),
                    "wall_s": 0.0,
                    "tail": "",
                    "reason": None,
                }
        self.preflight(st)
        name = lock_name(st, self.prof)
        try:
            wait = lambda: self.ev("lock-waiting", st, detail=name)  # noqa: E731
            with (
                locks.acquire(name, wait_s=g["lock_wait_s"], lock_dir=self.lockdir, on_wait=wait)
                if name
                else contextlib.nullcontext()
            ):
                if name:
                    self.ev("lock-acquired", st, detail=name)
                    self.device_guards(st)
                return self.attempts(st, i, inputs, key0, rerun, name)
        except locks.GpuHold as h:
            raise self.held(st, h.reason) from None
        except locks.LockTimeout as e:
            raise Stop("blocked", 3, "blocked", "lock-timeout", str(e)) from None

    def device_guards(self, st: dict) -> None:
        g, est = self.prof["guards"], st["resources"].get("vram_gib_est")
        try:
            if est is not None and not guards.vram_ok(int(self.backend.read("free_bytes")), est, g["vram_margin_gib"]):
                raise self.refuse(st, "vram")
            if not guards.wait_for_cooldown(
                lambda: self.backend.read("temp_c"), g["max_start_temp_c"], g["cooldown_wait_s"]
            ):
                raise self.refuse(st, "temp")
        except Stop:
            raise
        except Exception:
            raise self.refuse(st, "no-gpu") from None

    def attempts(self, st: dict, i: int, inputs: dict, key0: str, rerun: bool, name: str | None) -> dict:
        """Run until it works or fails for good: OOM walks the fallbacks, a first warm-up timeout is retried."""
        base, steps, atts, tries, applied = (
            st.get("params", {}),
            list(st.get("retry", {}).get("oom_fallback", [])),
            [],
            1,
            None,
        )
        params = base
        while True:
            a = self.attempt(st, i, inputs, params, rerun, tries, name)
            atts.append(
                {
                    "n": tries,
                    "error_class": a["ec"],
                    "duration_s": round(a["wall_s"], 3),
                    **({"fallback": applied} if applied else {}),
                }
            )
            if (
                a["status"] != "failed"
                or tries >= 5
                or not (a["ec"] == "warmup-timeout" or (a["ec"] == "oom" and steps))
            ):
                break
            applied = steps.pop(0) if a["ec"] == "oom" else None
            params, tries = {**params, **(applied or {})}, tries + 1
            self.ev("stage-retry", st, i if st.get("shardable") else None, detail=f"after {a['ec']}", attempt=tries)
        res = a["result"] or {}
        ex = {
            "hit": False,
            "key": key0 if params == base else self.keys.key(st, params, i, inputs),
            "params": params,
            "attempts": atts,
            "status": a["status"],
            "error_class": a["ec"],
            "exit_code": a["code"],
            "outs": [],
            "obs": res.get("observables"),
            "reason": a["reason"],
            "wall_s": sum(x["duration_s"] for x in atts),
            "tail": a["tail"],
            "problem": a["problem"],
            "throughput": res.get("throughput"),
        }
        if a["status"] == "succeeded" and (rerun or self.profiling):
            ex["outs"] = [
                {"name": nm, "sha256": file_sha(p), "bytes": p.stat().st_size} for nm, p in a["files"].items()
            ]
        elif a["status"] == "succeeded":
            entry = {
                "stage": skey(st),
                "run_id": self.run_id,
                "created": now()[:19] + "Z",
                **({"observables": ex["obs"]} if ex["obs"] else {}),
            }
            ex["outs"] = self.store.promote(ex["key"], entry, a["files"])
            if i == 0:
                self.store.view(self.doc["id"], kstr(st), ex["outs"])
        return ex

    def hw_error(self) -> bool:
        """A new WHEA/PCIe error since the job started (real GPU on Windows only; polled every 30 s)."""
        if self.launcher == "test" or sys.platform != "win32" or time.monotonic() - self.whea_at < 30:
            return False
        self.whea_at = time.monotonic()
        with contextlib.suppress(Exception):
            return bool(
                load_module(self.repo / "studio" / "bench" / "gpu_guard.py", "_pitstudio_gpu_guard").whea_count(
                    self.started
                )
            )
        return False

    def attempt(self, st: dict, i: int, inputs: dict, params: dict, rerun: bool, tries: int, name: str | None) -> dict:
        k, res = kstr(st), st["resources"]
        gpu, sh = res["gpu"] != "none", st.get("shardable")
        out = self.dir / "rerun" / "runs" / self.run_id / "tmp" / k / "0" if rerun else self.dir / "tmp" / k / str(i)
        scratch = out.parent / f"{out.name}.scratch"
        for d in (out, scratch):
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True)
        total, est = self.backend.vram_total_bytes if self.backend else None, res.get("vram_gib_est")
        frac = min(1.0, est * 2**30 / total) if gpu and total and est else None
        nvtx, seed = f"pitstudio:{k}:{i}", self.keys.seed(st, i)
        job = {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "stage": skey(st),
            "entry": st["entry"],
            "params": params,
            "seed": seed,
            "shard": {"index": i, "size": sh["shard_size"], "total": sh["total"]} if sh else None,
            "inputs": [
                {"name": nm, "path": self.store.obj(d).as_posix(), "sha256": d} for nm, d in inputs.items() if "/" in nm
            ],
            "output_dir": out.as_posix(),
            "scratch_dir": scratch.as_posix(),
            "resume": bool(self.resume),
            "rerun": rerun,
            "profiling": self.profiling,
            "profile": {"id": self.prof["id"], "cpu_slots": self.prof["cpu_slots"]},
            "vram_fraction": frac,
            "nvtx_range": nvtx,
        }
        (out / "job.json").write_text(json.dumps(job), encoding="utf-8")
        env = {
            **os.environ,
            "PITSTUDIO_RUN_ID": self.run_id,
            "PITSTUDIO_STAGE": k,
            "PITSTUDIO_SHARD": str(i),
            "PITSTUDIO_SEED": str(seed),
            "PITSTUDIO_NVTX_RANGE": nvtx,
            "PITSTUDIO_CPU_SLOTS": str(min(res.get("cpu", 1), self.prof["cpu_slots"])),
            "PITSTUDIO_HELD_LOCKS": name or "",
            "PYTHONPATH": os.pathsep.join(x for x in (str(KIT), os.environ.get("PYTHONPATH")) if x),
            "GPU_LOCK_DIR": str(self.lockdir),
        }
        env.pop("PITSTUDIO_VRAM_FRACTION", None)
        env |= {"CUDA_VISIBLE_DEVICES": str(gpu_index(self.prof))} if gpu else {}
        env |= {"PITSTUDIO_VRAM_FRACTION": repr(frac)} if frac else {}
        env |= {"PITSTUDIO_PROFILE": "1"} if self.profiling else {}
        argv = execute.build_command(
            launcher=self.launcher, repo=self.repo, env=st["env"], entry=st["entry"], job_path=out / "job.json"
        )
        stop, state, last, frozen, th = threading.Event(), {}, [0.0], [False], None
        if gpu and self.backend is not None:
            tg, samples = guards.ThermalGuard(**guards.thresholds(self.repo)), self.tele.setdefault(k, [])

            def on_sample(row: dict) -> None:
                samples.append(row)
                if row["temp_c"] is not None:
                    state["d"] = tg.observe(row["t_s"], row["temp_c"], self.hw_error())

            kw = {
                "should_stop": stop.is_set,
                "run_id": self.run_id,
                "stage": skey(st),
                "shard": i,
                "gpu": gpu_index(self.prof),
                "on_sample": on_sample,
            }
            th = threading.Thread(
                target=telemetry.sample_loop,
                args=(self.backend, self.dir / "telemetry.jsonl", self.prof["telemetry_hz"]),
                kwargs=kw,
                daemon=True,
            )
            th.start()

        def tick(tree: Any) -> str | None:
            if time.monotonic() - last[0] >= 0.25:
                last[0] = time.monotonic()
                if queue.cancel_requested(self.job_id):
                    return "cancel"
            d = state.get("d")
            if d is not None and d.action == "stop":
                return d.reason
            if (want := d is not None and d.action in ("pause", "cooldown")) != frozen[0]:
                tree.freeze(want)
                frozen[0] = want
            return None

        if self.profiling:
            (self.dir / "profile").mkdir(exist_ok=True)
            (self.dir / "profile" / "command.txt").write_text(
                f"nsys profile --trace=cuda,nvtx -o {self.dir / 'profile' / k} {' '.join(argv)}\n", encoding="utf-8"
            )
        log = self.dir / "logs" / f"{k}-{i}-{tries}.log"
        try:
            r = execute.run_attempt(argv, env, self.repo, log, st["timeout_s"], tick)
        finally:
            stop.set()
            if th:
                th.join(10)
        if r["kind"] == "cancel":
            self.ev("cancelled", st)
            raise Stop("cancelled", 6, "cancelled", "cancelled", "cancelled")
        if r["kind"] in ("thermal", "hw-error"):
            self.ev("guard-refused", st, detail=r["kind"], reason=r["kind"])
            raise Stop("failed", 5, "failed", "guard", r["kind"])
        return self.classify(st, out, log, r, tries)

    def classify(self, st: dict, out: Path, log: Path, r: dict, tries: int) -> dict:
        """Turn the process result into success, `not_run` or a failure with its error class (FR-002-25, 33, 60, 61)."""
        tail = execute.scrub("\n".join(execute.log_lines(log, 50)), self.repo, self.store.root, self.lockdir)[-4000:]
        a = {
            "status": "failed",
            "ec": None,
            "code": r["code"],
            "wall_s": r["wall_s"],
            "result": None,
            "files": {},
            "problem": None,
            "reason": None,
            "tail": tail,
        }
        if r["kind"] == "timeout":
            a["ec"] = "warmup-timeout" if tries == 1 and st["env"] in execute.WARMUP_ENVS else "timeout"
            return a | {"problem": f"no result after {st['timeout_s']} s"}
        res, problem = execute.read_result(out, r["code"])
        a["problem"] = problem
        if problem:
            oom = (
                r["code"] != 0
                and res is None
                and problem == "no result.json"
                and execute.OOM.search("\n".join(execute.log_lines(log, 200)))
            )
            a["ec"] = (
                "oom" if oom else "nonzero-exit" if problem == "no result.json" and r["code"] != 0 else "invalid-result"
            )
        elif res["status"] == "not_run":
            a |= {"status": "not_run", "reason": res["reason"], "result": res}
        elif res["status"] == "failed":
            a |= {"ec": res["error_class"], "problem": res.get("message"), "result": res}
        else:
            files, bad = execute.check_outputs(st["outputs"], out, res)
            a |= {
                "result": res,
                "files": files,
                "problem": bad,
                "status": "failed" if bad else "succeeded",
                "ec": "invalid-output" if bad else None,
            }
        return a

    def recheck(self, st: dict, inputs: dict, first: dict) -> dict:
        """`--rerun-check` (FR-002-38): shard 0 again into a scratch folder; digests or observables must agree."""
        cls = st["determinism"] if isinstance(st["determinism"], str) else st["determinism"]["class"]
        tol = {} if isinstance(st["determinism"], str) else st["determinism"].get("observables", {})
        if cls == "none":
            return {"rerun_check": "not-applicable"}
        again = self.execute(st, 0, inputs, rerun=True)
        if again["status"] != "succeeded":
            return {"rerun_check": "fail", **({"max_deviation": 0.0} if cls == "statistical" else {})}
        if cls == "bitwise":
            return {
                "rerun_check": "pass"
                if {o["name"]: o["sha256"] for o in again["outs"]} == {o["name"]: o["sha256"] for o in first["outs"]}
                else "fail"
            }
        a, b = again.get("obs") or {}, first.get("obs") or {}
        dev = {nm: abs(a[nm] - b[nm]) for nm in tol if nm in a and nm in b}
        ok = len(dev) == len(tol) and all(dev[nm] <= t["atol"] + t["rtol"] * abs(b[nm]) for nm, t in tol.items())
        return {"rerun_check": "pass" if ok else "fail", "max_deviation": max(dev.values(), default=0.0)}


def run_job(job: dict) -> int:
    """Run one claimed job to the end; the state, exit code and reason are written to the queue."""
    job_id = job["job_id"]
    try:
        state, code, reason = Run(job_id, queue.request_of(job_id)).go()
    except Usage as e:
        state, code, reason = "failed", 2, str(e)
    except KeyboardInterrupt:
        state, code, reason = "interrupted", 6, "interrupted"
    except Exception as e:
        state, code, reason = "failed", 1, f"{type(e).__name__}: {e}"
    queue.update(job_id, state=state, exit_code=code, reason=(reason or "")[:300] or None)
    if state != "succeeded":
        print(f"job {job_id}: {state}" + (f": {reason}" if reason else ""), file=sys.stderr)
    return code


def drain(until: str | None = None) -> int | None:
    """Take the worker lock and run queued jobs (until `until` has ended, or until the queue is empty).

    Returns the exit code of job `until` (0 when draining), or None when another worker owns the store."""
    from filelock import FileLock, Timeout

    lock_path = store_root() / "locks" / "worker.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock, awake, code = FileLock(lock_path), False, 0
    try:
        lock.acquire(timeout=0)
    except Timeout:
        return None
    try:
        queue.settle_stale()
        while job := queue.claim():
            keep = False
            with contextlib.suppress(Usage):
                keep = load_profile(repo_root(), queue.request_of(job["job_id"])["profile"]).get("keep_awake")
            if keep and sys.platform == "win32" and not awake:
                oswin.set_thread_execution_state(KEEP)
                awake = True
            rc = run_job(job)
            if job["job_id"] == until:
                code = rc
                break
    finally:
        if awake:
            oswin.set_thread_execution_state(RELEASE)
        lock.release()
    return code
