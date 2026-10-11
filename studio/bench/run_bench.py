"""Run capability probes one at a time under the machine-wide GPU lock, with NVML telemetry, and write the results.

Usage (root project, extra `runner`):
    uv run --extra runner python studio/bench/run_bench.py                 # every probe whose env is installed
    uv run --extra runner python studio/bench/run_bench.py warp_newton     # selected probes
Outputs:
    studio/capabilities.json                     committed: versions, pass/fail, publishable metrics only
    $PITSTUDIO_TMP/bench/bench-<UTC time>.json   local: everything, incl. licence-restricted metrics and telemetry
Environment: GPU_LOCK_DIR (machine-wide lock directory shared by every project), PITSTUDIO_TMP (local outputs).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BENCH = Path(__file__).resolve().parent
# probe name → (uv project dir relative to the repo root, extra uv args)
PROBES: dict[str, tuple[str, list[str]]] = {
    "warp_newton": ("studio", []),
    "torch_ort": ("pipeline", ["--extra", "cu130"]),
    "tensorrt": ("pipeline/accel", []),
    "nvenc": ("studio", []),
    "ovrtx": ("studio/rtx", []),
    "isaacsim": ("studio/isaac", []),
    "isaaclab": ("studio/isaaclab", []),
    "stress": ("studio", []),
}
OPT_IN = {"stress"}  # long or disruptive: run only when named explicitly
MIN_FREE_VRAM_MB = 4096  # refuse to start when another job is holding the GPU
MAX_START_TEMP_C = 88  # laptop GPUs idle near their 87 C throttle target under CPU load (shared cooling)
COOLDOWN_WAIT_S = 600  # wait this long for the GPU to cool below MAX_START_TEMP_C before skipping a probe


def local_dir() -> Path:
    base = os.environ.get("PITSTUDIO_TMP") or str(ROOT / ".tmp")
    d = Path(base) / "bench"
    d.mkdir(parents=True, exist_ok=True)
    return d


def lock_dir() -> Path:
    # machine-wide on purpose: every project on the machine shares one GPU
    d = Path(os.environ.get("GPU_LOCK_DIR") or Path(tempfile.gettempdir()) / "gpu-locks")
    d.mkdir(parents=True, exist_ok=True)
    return d


def hold_reason() -> str | None:
    """A `gpu0.hold` file in the lock directory stops all GPU work on the machine; its text says why."""
    hold = lock_dir() / "gpu0.hold"
    if not hold.exists():
        return None
    return hold.read_text(encoding="utf-8", errors="replace").strip() or "no reason given"


class Telemetry:
    """Samples NVML at 2 Hz while a probe runs; keeps maxima and the PCIe replay-counter delta."""

    def __init__(self) -> None:
        import pynvml

        self.nv = pynvml
        pynvml.nvmlInit()
        self.h = pynvml.nvmlDeviceGetHandleByIndex(0)
        self.samples: list[dict[str, float]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, float]:
        nv, h = self.nv, self.h
        mem = nv.nvmlDeviceGetMemoryInfo(h)
        s = {
            "t": time.time(),
            "temp_c": nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU),
            "power_w": nv.nvmlDeviceGetPowerUsage(h) / 1000.0,
            "power_limit_w": nv.nvmlDeviceGetEnforcedPowerLimit(h) / 1000.0,
            "util_pct": nv.nvmlDeviceGetUtilizationRates(h).gpu,
            "mem_used_mb": mem.used / 2**20,
            "mem_total_mb": mem.total / 2**20,
            "sm_clock_mhz": nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM),
            "throttle_reasons": nv.nvmlDeviceGetCurrentClocksEventReasons(h),
        }
        try:
            s["pcie_replays"] = nv.nvmlDeviceGetPcieReplayCounter(h)
        except nv.NVMLError:
            s["pcie_replays"] = -1
        return s

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.samples.append(self.snapshot())
            self._stop.wait(0.5)

    def __enter__(self) -> Telemetry:
        self.samples = []
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()

    def summary(self) -> dict[str, float]:
        if not self.samples:
            return {}
        key = lambda k: max(s[k] for s in self.samples)  # noqa: E731
        return {
            "samples": len(self.samples),
            "max_temp_c": key("temp_c"),
            "max_power_w": round(key("power_w"), 1),
            "power_limit_w": round(self.samples[-1]["power_limit_w"], 1),
            "max_mem_used_mb": round(key("mem_used_mb")),
            "max_util_pct": key("util_pct"),
            "pcie_replays_delta": self.samples[-1]["pcie_replays"] - self.samples[0]["pcie_replays"],
        }


def whea_count() -> int | None:
    """Number of WHEA-Logger events in the Windows System log (PCIe/hardware errors); None off Windows."""
    if sys.platform != "win32":
        return None
    q = "*[System[Provider[@Name='Microsoft-Windows-WHEA-Logger']]]"
    out = subprocess.run(
        ["wevtutil", "qe", "System", f"/q:{q}", "/f:text", "/c:100000"],
        capture_output=True,
        text=True,
        errors="replace",
    ).stdout
    return out.count("Event[")


def run_one(name: str, tele: Telemetry, timeout_s: int) -> dict[str, Any]:
    project, extra = PROBES[name]
    pdir = ROOT / project
    if not (BENCH / f"probe_{name}.py").exists():
        return {"probe": name, "status": "skip", "notes": ["probe script not written yet"]}
    if not (pdir / ".venv").exists():
        return {"probe": name, "status": "skip", "notes": [f"environment {project} is not installed (uv sync)"]}
    before = tele.snapshot()
    free_mb = before["mem_total_mb"] - before["mem_used_mb"]
    if free_mb < MIN_FREE_VRAM_MB:
        return {"probe": name, "status": "skip", "notes": [f"only {free_mb:.0f} MB VRAM free; another job uses it"]}
    deadline = time.monotonic() + COOLDOWN_WAIT_S  # a hot GPU (e.g. right after the previous probe) cools down first
    while before["temp_c"] > MAX_START_TEMP_C and time.monotonic() < deadline:
        time.sleep(5)
        before = tele.snapshot()
    if before["temp_c"] > MAX_START_TEMP_C:
        return {"probe": name, "status": "skip", "notes": [f"GPU at {before['temp_c']} C before start"]}
    w0 = whea_count()
    cmd = ["uv", "run", "--locked", "--project", str(pdir), *extra, "python", str(BENCH / f"probe_{name}.py")]
    t0 = time.perf_counter()
    with tele:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, cwd=BENCH, errors="replace")
            lines = [ln for ln in p.stdout.splitlines() if ln.startswith("{")]
            res = (
                json.loads(lines[-1])
                if lines
                else {"probe": name, "status": "fail", "error": (p.stderr or p.stdout)[-800:]}
            )
        except subprocess.TimeoutExpired:
            res = {"probe": name, "status": "fail", "error": f"timeout after {timeout_s} s"}
    res["wall_s"] = round(time.perf_counter() - t0, 1)
    res["telemetry"] = tele.summary()
    w1 = whea_count()
    if w0 is not None and w1 is not None:
        res["telemetry"]["whea_events_delta"] = w1 - w0
    return res


LOCAL_ONLY = "measured locally, not published (licence)"


def scrub(text: str) -> str:
    """Local paths never reach the committed file: the repo root becomes <repo>, the home directory ~."""
    for path, token in ((ROOT, "<repo>"), (Path.home(), "~")):
        for form in {str(path), str(path).replace("\\", "/"), str(path).replace("\\", "\\\\")}:
            text = text.replace(form, token)
    return text


def public_view(results: list[dict[str, Any]], driver: str, gpu: str) -> dict[str, Any]:
    """The committed capabilities: performance figures and telemetry only for probes whose licence allows it."""
    probes = {}
    for r in results:
        versions = {k: str(v) for k, v in r.get("versions", {}).items()}
        if py := r.get("env", {}).get("python"):
            versions = {"python": py, **versions}
        entry: dict[str, Any] = {"status": r["status"], "versions": versions}
        public = r.get("publish") == "public"
        if r.get("metrics"):
            entry["metrics"] = r["metrics"] if public else LOCAL_ONLY
        if public and r.get("telemetry"):
            entry["telemetry"] = r["telemetry"]
        if r.get("notes"):
            entry["notes"] = [scrub(n) for n in r["notes"]]
        if r.get("error"):
            entry["error"] = scrub(r["error"])[:300]
        probes[r["probe"]] = entry
    return {
        "$schema": "../contracts/capabilities.schema.json",
        "generated": dt.date.today().isoformat(),
        "gpu": gpu,
        "driver": driver,
        "probes": probes,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    default = f"default: all but {', '.join(sorted(OPT_IN))}"
    ap.add_argument("probes", nargs="*", help=f"subset of: {', '.join(PROBES)} ({default})")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--no-write", action="store_true", help="do not update studio/capabilities.json")
    a = ap.parse_args(argv[1:])
    if unknown := sorted(set(a.probes) - set(PROBES)):
        ap.error(f"unknown probe(s): {', '.join(unknown)}")
    if reason := hold_reason():
        print(f"GPU hold in {lock_dir() / 'gpu0.hold'}: {reason} -- not starting")
        return 4
    # imported only after the hold check: the hold must stop a run even where the `runner` extra is missing
    from filelock import FileLock, Timeout

    names = a.probes or [p for p in PROBES if p not in OPT_IN]
    lock = FileLock(lock_dir() / "gpu0.compute")
    try:
        lock.acquire(timeout=5)
    except Timeout:
        print(f"GPU lock {lock.lock_file} is held by another job -- not starting")
        return 3
    results = []
    try:
        tele = Telemetry()
        gpu = tele.nv.nvmlDeviceGetName(tele.h)
        driver = tele.nv.nvmlSystemGetDriverVersion()
        for n in names:
            print(f"[bench] {n} ...", flush=True)
            r = run_one(n, tele, a.timeout)
            print(f"[bench] {n}: {r['status']} ({r.get('wall_s', 0)} s) {r.get('error', '')}", flush=True)
            results.append(r)
    finally:
        lock.release()
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    local = local_dir() / f"bench-{stamp}.json"
    local.write_text(json.dumps({"gpu": gpu, "driver": driver, "results": results}, indent=2), encoding="utf-8")
    print(f"[bench] local report: {local}")
    if not a.no_write:
        cap = ROOT / "studio" / "capabilities.json"
        old = json.loads(cap.read_text(encoding="utf-8")) if cap.exists() else {"probes": {}}
        new = public_view(results, driver, gpu)
        new["probes"] = {**old.get("probes", {}), **new["probes"]}
        cap.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"[bench] updated {cap.relative_to(ROOT)}")
    return 0 if all(r["status"] != "fail" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
