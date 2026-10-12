"""In-run GPU guard shared by every GPU job on this machine: pause when hot, stop when too hot or on a hardware error.

Standard library only (NVML is used when `pynvml` is importable, else `nvidia-smi`), so any environment can import it:
    from gpu_guard import Guard, GuardStop
    guard = Guard()
    for step in ...:
        if guard.check() == "cooldown":   # a GPU block of BLOCK_MIN minutes is over
            save_checkpoint(); release_lock(); guard.cool_down(); reacquire_lock()
        train_step()
`check()` pauses in place (the GPU idles and cools) at PAUSE_C until RESUME_C, and raises GuardStop at STOP_C or when a
new WHEA hardware-error event appears (the laptop's GPU link logs PCIe errors before it crashes).
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable

START_MAX_C = 80  # FR-002-19: never start a GPU job hotter than this
PAUSE_C = 83  # pause the job at the next step boundary
RESUME_C = 75  # resume only once cooled to this
STOP_C = 87  # stop (after a checkpoint) at the GPU's throttle point
BLOCK_MIN = 45  # continuous GPU time per block
COOLDOWN_MIN = 10  # idle time between blocks


class GuardStop(RuntimeError):
    """Raised when the job must stop: `reason` is "thermal" or "hw-error"."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def whea_count(since: str | None = None) -> int | None:
    """WHEA-Logger events (PCIe/hardware errors) in the Windows System log created after `since` (UTC ISO time; all
    events when None). None off Windows or when the query fails, so a failed query is never read as "0 new errors"
    and a wrapped log cannot hide a new event (the time filter does not depend on the log's size)."""
    if sys.platform != "win32":
        return None
    when = f" and TimeCreated[@SystemTime>='{since}']" if since else ""
    q = f"*[System[Provider[@Name='Microsoft-Windows-WHEA-Logger']{when}]]"
    try:
        p = subprocess.run(
            ["wevtutil", "qe", "System", f"/q:{q}", "/f:text", "/c:100000"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    if p.returncode != 0:
        return None
    return p.stdout.count("Event[")


def gpu_temp_reader() -> Callable[[], int]:
    """A function returning the GPU 0 core temperature (C): NVML when available, else nvidia-smi."""
    try:
        import pynvml

        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        return lambda: int(pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU))
    except Exception:

        def smi() -> int:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits", "-i", "0"],
                capture_output=True,
                text=True,
            ).stdout
            return int(out.strip().splitlines()[0])

        return smi


class Guard:
    """Call `check()` between steps; it pauses, signals a block end ("cooldown") or raises GuardStop."""

    def __init__(
        self,
        read_temp: Callable[[], int] | None = None,
        whea: Callable[[str | None], int | None] = whea_count,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        log: Callable[[str], None] = lambda m: print(m, flush=True),
        temp_every_s: float = 2.0,
        whea_every_s: float = 30.0,
        block_s: float = BLOCK_MIN * 60,
        cooldown_s: float = COOLDOWN_MIN * 60,
    ) -> None:
        self.read_temp = read_temp or gpu_temp_reader()
        self.whea, self.clock, self.sleep, self.log = whea, clock, sleep, log
        self.temp_every_s, self.whea_every_s = temp_every_s, whea_every_s
        self.block_s, self.cooldown_s = block_s, cooldown_s
        self.since = utc_now_iso()  # hardware errors are counted from the guard's start, by time, not by log size
        self.whea_unavailable_logged = False
        now = clock()
        self._t_temp = self._t_whea = -1e18
        self._block_start = now
        self.paused_s = 0.0
        self.max_temp = -1

    def _temp(self) -> int:
        t = self.read_temp()
        self.max_temp = max(self.max_temp, t)
        if t >= STOP_C:
            raise GuardStop("thermal", f"GPU at {t} C (stop at {STOP_C} C)")
        return t

    def _check_whea(self) -> None:
        w = self.whea(self.since)
        if w is None:
            if sys.platform == "win32" and not self.whea_unavailable_logged:
                self.log("[guard] WARNING: WHEA query failed; hardware-error detection unavailable (watch the log)")
                self.whea_unavailable_logged = True
            return
        if w > 0:
            raise GuardStop("hw-error", f"{w} new WHEA hardware-error event(s) since the job started")

    def check(self) -> str:
        now = self.clock()
        if now - self._t_whea >= self.whea_every_s:
            self._t_whea = now
            self._check_whea()
        if now - self._t_temp >= self.temp_every_s:
            self._t_temp = now
            t = self._temp()
            if t >= PAUSE_C:
                self.log(f"[guard] GPU at {t} C: pausing until {RESUME_C} C")
                p0 = self.clock()
                while t > RESUME_C:
                    self.sleep(5)
                    t = self._temp()
                    if self.clock() - self._t_whea >= self.whea_every_s:
                        self._t_whea = self.clock()
                        self._check_whea()
                paused = self.clock() - p0
                self.paused_s += paused
                self._block_start += paused  # paused time is not GPU time
                self.log(f"[guard] resumed at {t} C after {paused:.0f} s")
        if self.clock() - self._block_start >= self.block_s:
            return "cooldown"
        return "ok"

    def cool_down(self) -> None:
        """Idle for the cool-down period (the caller has saved a checkpoint and released the GPU lock)."""
        self.log(f"[guard] block of {self.block_s / 60:.0f} min done: cooling down {self.cooldown_s / 60:.0f} min")
        self.sleep(self.cooldown_s)
        self._check_whea()
        self._block_start = self.clock()
