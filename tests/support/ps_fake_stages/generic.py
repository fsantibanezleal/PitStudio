"""One configurable fake stage: its behaviour is chosen by the recipe `params` (so it enters the cache key).

Standard library only; it never imports first-party code, so runner tests exercise real process launching.
Params (all optional):
  mode            ok | fail | crash | oom_result | oom_log | oom_if_big | sleep | grandchild | notrun | raw_result |
                  big_result | no_result | dup_output | missing_output | empty_output | bad_json_output | link_output |
                  escape_output | hold_after | wait_for_file | exit_nonzero_ok_result
  files           list of relative output paths to write (default ["out.bin"])
  payload         text mixed into every file (default "x")
  repeat          repeat count of the file text (default 1)
  sleep_s         seconds to sleep (modes sleep, grandchild)
  particles/limit mode oom_if_big fails with a CUDA OOM result while particles > limit
  reason          mode notrun: the reason text
  raw             mode raw_result: the exact text written to result.json
  exit_code       process exit code (default 0; mode fail/crash default 1/3)
  observables     object name -> number reported in the result (plus `obs_jitter` * (seed % 7) added)
  hold_dir        mode hold_after: directory in which a `gpu0.hold` file is created after the stage's work
  marker          mode wait_for_file: path whose existence ends the wait
Environment: PS_FAKE_LEDGER (a file; one JSON line is appended at start and at end of every execution).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _sha(path: str) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _ledger(event: str, job: dict, extra: dict | None = None) -> None:
    path = os.environ.get("PS_FAKE_LEDGER")
    if not path:
        return
    shard = job.get("shard") or {"index": 0}
    rec = {
        "event": event,
        "stage": job["stage"],
        "shard": shard["index"],
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "t_ns": time.time_ns(),
        "seed": job["seed"],
        "params": job["params"],
        "env": {
            k: v
            for k, v in os.environ.items()
            if k.startswith("PITSTUDIO_") or k in ("CUDA_VISIBLE_DEVICES", "PYTHONPATH")
        },
        "argv": sys.argv,
        "resume": job.get("resume"),
        "rerun": job.get("rerun"),
        "profiling": job.get("profiling"),
        "inputs": [
            {"name": i["name"], "declared": i["sha256"], "actual": _sha(i["path"])} for i in job.get("inputs", [])
        ],
        "job": job if event == "start" else None,
        "cwd": os.getcwd(),
        **(extra or {}),
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def _content(job: dict, name: str) -> bytes:
    p = job["params"]
    if "text" in p:
        return str(p["text"]).encode("utf-8")
    shard = (job.get("shard") or {"index": 0})["index"]
    text = f"{job['stage']['id']}|{job['stage'].get('variant')}|{job['seed']}|{shard}|{name}|{p.get('payload', 'x')}\n"
    if p.get("nondeterministic"):  # a bitwise stage that is not: different bytes on every execution
        text += f"{time.time_ns()}-{os.getpid()}\n"
    return (text * int(p.get("repeat", 1))).encode()


def _probe_locks() -> dict:
    """Try to take each GPU lock without waiting (needs the `filelock` package of the root runner extra)."""
    from filelock import FileLock, Timeout

    held = {}
    d = os.environ.get("GPU_LOCK_DIR", "")
    for name in ("gpu0.compute", "gpu0.nvenc"):
        lock = FileLock(os.path.join(d, name))
        try:
            lock.acquire(timeout=0)
            lock.release()
            held[name] = False
        except Timeout:
            held[name] = True
    return held


def _write_result(out: Path, doc: dict) -> None:
    (out / "result.json").write_text(json.dumps(doc), encoding="utf-8")


def _result(job: dict, files: list[str], **over: object) -> dict:
    p = job["params"]
    obs = {
        k: float(v) + float(p.get("obs_jitter", 0.0)) * (job["seed"] % 7)
        for k, v in dict(p.get("observables", {})).items()
    }
    if job.get("rerun") and "rerun_delta" in p:  # the re-execution of --rerun-check deviates by a controlled amount
        key = p.get("rerun_delta_key")
        obs = {k: v + float(p["rerun_delta"]) if key in (None, k) else v for k, v in obs.items()}
    outputs: list[dict] = [{"path": f} for f in files]
    if "validated" in p:  # stage-side validators: the stage states whether it validated the output
        outputs = [
            {"path": f, "validator": str(p.get("validator_id", "stage-fake")), "validated": bool(p["validated"])}
            for f in files
        ]
    doc: dict = {
        "schema_version": "1.0",
        "status": "succeeded",
        "error_class": None,
        "outputs": outputs,
        "checkpoint": False,
    }
    if obs:
        doc["observables"] = obs
    doc.update(over)
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    a = ap.parse_args(argv)
    job = json.loads(Path(a.job).read_text(encoding="utf-8"))
    out = Path(job["output_dir"])
    p = job["params"]
    mode = p.get("mode", "ok")
    if os.environ.get("PS_FAKE_FAIL"):  # environment is not part of the cache key: lets a test fail a forced re-run
        mode = "fail"
    fail_shard = os.environ.get("PS_FAKE_FAIL_SHARD", "")  # ... or one shard of a sharded stage
    if fail_shard != "" and int(fail_shard) == (job.get("shard") or {"index": 0})["index"]:
        mode = "fail"
    files = list(p.get("files", ["out.bin"]))
    extra_start: dict = {}
    if p.get("probe_locks"):  # is each machine-wide lock held by someone else (the runner) while this stage runs?
        extra_start["locks_held"] = _probe_locks()
    _ledger("start", job, extra_start)
    if (
        os.environ.get("PITSTUDIO_PROFILE") == "1"
    ):  # a profiled run leaves profiler output next to the job (both folders)
        for d in (out, Path(job["scratch_dir"])):
            d.mkdir(parents=True, exist_ok=True)
            (d / "profiler.txt").write_bytes(b"profile data\n")

    def finish(code: int = 0) -> int:
        _ledger("end", job, {"exit_code": code})
        return code

    def write_files() -> None:
        for f in files:
            target = out / f
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_content(job, f))

    if mode in ("sleep", "grandchild"):
        if mode == "grandchild":
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
            _ledger("grandchild", job, {"child_pid": child.pid})
        time.sleep(float(p.get("sleep_s", 0.0)))
        write_files()
        _write_result(out, _result(job, files))
        return finish(int(p.get("exit_code", 0)))
    if mode == "wait_for_file":
        deadline = time.monotonic() + float(p.get("sleep_s", 20.0))
        while not Path(p["marker"]).exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        write_files()
        _write_result(out, _result(job, files))
        return finish()
    for i in range(int(p.get("log_lines", 0))):  # filler so that tests can check the 50-line / 4,000-character log tail
        print(f"line-{i:03d} " + "." * int(p.get("log_width", 0)), file=sys.stderr)
    if mode == "slow_first":  # the first execution (no marker file yet) is slower than the timeout: a warm-up
        marker = Path(p["marker"])
        if not marker.exists():
            marker.write_text("first attempt\n", encoding="utf-8")
            time.sleep(float(p.get("sleep_s", 30)))
        write_files()
        _write_result(out, _result(job, files))
        return finish()
    if mode == "oom_log_if_big":  # CUDA OOM reported only through the log (no result.json), while particles > limit
        if p.get("particles", 0) > p.get("limit", 0):
            print(str(p.get("oom_text", "CUDA out of memory")), file=sys.stderr)
            for i in range(int(p.get("trailing_lines", 0))):
                print(f"trailing-{i:03d}", file=sys.stderr)
            return finish(1)
        write_files()
        _write_result(out, _result(job, files))
        return finish()
    if mode == "fail":
        _write_result(out, _result(job, [], status="failed", error_class="unknown", message="fake failure"))
        print("fake stage failed: see " + str(Path.home() / "secret" / "x.log"), file=sys.stderr)
        print(
            f"repo={os.environ.get('PITSTUDIO_REPO', '')} store={os.environ.get('PITSTUDIO_STORE', '')}",
            file=sys.stderr,
        )
        return finish(int(p.get("exit_code", 1)))
    if mode == "crash":
        print("Traceback (most recent call last): fake crash", file=sys.stderr)
        return finish(int(p.get("exit_code", 3)))
    if mode == "oom_result" or (mode == "oom_if_big" and p.get("particles", 0) > p.get("limit", 0)):
        _write_result(out, _result(job, [], status="failed", error_class="oom", message="CUDA out of memory"))
        return finish(int(p.get("exit_code", 1)))
    if mode == "oom_log":
        print("torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB", file=sys.stderr)
        return finish(1)
    if mode == "notrun":
        _write_result(out, _result(job, [], status="not_run", error_class=None, reason=p.get("reason", "tool missing")))
        return finish(int(p.get("exit_code", 0)))
    if mode == "raw_result":
        (out / "result.json").write_text(str(p["raw"]), encoding="utf-8")
        return finish(int(p.get("exit_code", 0)))
    if mode == "big_result":
        pad = "x" * 70000
        _write_result(out, _result(job, files, message="m", observables={"a": 1.0}) | {"$schema": pad})
        write_files()
        return finish()
    if mode == "no_result":
        write_files()
        return finish()
    if mode == "dup_output":
        write_files()
        _write_result(out, _result(job, files + files[:1]))
        return finish()
    if mode == "missing_output":
        _write_result(out, _result(job, files))
        return finish()
    if mode == "empty_output":
        for f in files:
            (out / f).write_bytes(b"")
        _write_result(out, _result(job, files))
        return finish()
    if mode == "bad_json_output":
        for f in files:
            (out / f).write_text("{not json", encoding="utf-8")
        _write_result(out, _result(job, files))
        return finish()
    if mode in ("link_output", "escape_output"):
        # outputs[0] is a link (or lies behind a directory link) pointing outside the stage folder
        outside = out.parent / "outside_target"
        outside.mkdir(exist_ok=True)
        (outside / "secret.bin").write_bytes(b"outside the stage folder")
        if mode == "link_output":
            try:
                os.symlink(outside / "secret.bin", out / files[0])
            except OSError:  # no symlink privilege (Windows): a directory junction gives the same escape
                _junction(out / "jdir", outside)
                files = ["jdir/secret.bin"]
        else:
            if os.name == "nt":
                _junction(out / "jdir", outside)
            else:
                os.symlink(outside, out / "jdir", target_is_directory=True)
            files = ["jdir/secret.bin"]
        _write_result(out, _result(job, files))
        return finish()
    if mode == "hold_after":
        write_files()
        _write_result(out, _result(job, files))
        if (job.get("shard") or {"index": 0})["index"] == int(p.get("hold_shard", 0)):
            (Path(p["hold_dir"]) / "gpu0.hold").write_text("hold appeared mid-run\n", encoding="utf-8")
        return finish()
    if mode == "exit_nonzero_ok_result":
        write_files()
        _write_result(out, _result(job, files))
        return finish(1)
    write_files()
    _write_result(out, _result(job, files))
    return finish(int(p.get("exit_code", 0)))


def _junction(link: Path, target: Path) -> None:
    if link.exists():
        return
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


if __name__ == "__main__":
    sys.exit(main())
