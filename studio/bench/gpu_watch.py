"""Independent GPU watch: prints one line per alert and a heartbeat, for a supervising session to read.

Usage (root project, extra `runner`):  uv run --extra runner python studio/bench/gpu_watch.py --minutes 30
Alerts: temperature >= ALERT_C, any new WHEA hardware-error event, PCIe replay counter increase, power at the limit
for > 60 s. It never touches the GPU's work; it only reads NVML and the Windows System log. Bounded by --minutes.
"""

from __future__ import annotations

import argparse
import sys
import time

from gpu_guard import whea_count

ALERT_C = 85


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--heartbeat-min", type=float, default=10)
    a = ap.parse_args(argv[1:])
    import pynvml

    pynvml.nvmlInit()
    h = pynvml.nvmlDeviceGetHandleByIndex(0)
    w0 = whea_count()
    try:
        r0 = pynvml.nvmlDeviceGetPcieReplayCounter(h)
    except pynvml.NVMLError:
        r0 = None
    end = time.monotonic() + a.minutes * 60
    last_beat = t_whea = time.monotonic()
    hot = at_limit_since = None
    tmax = 0
    while time.monotonic() < end:
        t = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
        p = pynvml.nvmlDeviceGetPowerUsage(h) / 1000
        lim = pynvml.nvmlDeviceGetEnforcedPowerLimit(h) / 1000
        u = pynvml.nvmlDeviceGetUtilizationRates(h).gpu
        tmax = max(tmax, t)
        stamp = time.strftime("%H:%M:%S")
        if t >= ALERT_C and not hot:
            print(f"[watch {stamp}] ALERT temperature {t} C (>= {ALERT_C}), util {u} %, {p:.0f} W", flush=True)
            hot = True
        elif t < ALERT_C - 3:
            hot = False
        if p > 2 * lim:  # NVML on this laptop sometimes reports a bogus ~594 W at idle; ignore impossible readings
            p = float("nan")
        if p >= 0.95 * lim:
            at_limit_since = at_limit_since or time.monotonic()
            if time.monotonic() - at_limit_since > 60:
                print(f"[watch {stamp}] ALERT power at the limit for > 60 s ({p:.0f} / {lim:.0f} W)", flush=True)
                at_limit_since = time.monotonic() + 600  # re-alert at most every 10 min
        else:
            at_limit_since = None
        if r0 is not None:
            r = pynvml.nvmlDeviceGetPcieReplayCounter(h)
            if r > r0:
                print(f"[watch {stamp}] ALERT PCIe replay counter +{r - r0} (now {r})", flush=True)
                r0 = r
        if w0 is not None and time.monotonic() - t_whea >= 30:
            t_whea = time.monotonic()
            w = whea_count()
            if w is not None and w > w0:
                print(f"[watch {stamp}] ALERT {w - w0} new WHEA hardware-error event(s)", flush=True)
                w0 = w
        if time.monotonic() - last_beat >= a.heartbeat_min * 60:
            last_beat = time.monotonic()
            print(f"[watch {stamp}] ok: now {t} C, max {tmax} C, util {u} %, {p:.0f} W", flush=True)
            tmax = 0
        time.sleep(2)
    print(f"[watch {time.strftime('%H:%M:%S')}] watch ended after {a.minutes:.0f} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
