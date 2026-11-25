"""Probe (pipeline env): the pinned llama.cpp b11381 CUDA runtime (spec 015, DC-015-08).

llama.cpp is an external tool (MIT licence; the open-model licence of the lane has no benchmark clause, so the figures
are `public`). The unpacked build is looked up in `PITSTUDIO_LLAMACPP` (the folder holding `llama-server.exe`), else in
`$PITSTUDIO_MODELS/llama.cpp/b11381`. The probe verifies every pinned executable against `studio/reason/pins.json`, runs
`llama-server --version` and records the build; a missing runtime is a skip, never a pass.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from _common import SkipProbe, run_probe

PINS = Path(__file__).resolve().parents[1] / "reason" / "pins.json"


def runtime_dir() -> Path:
    explicit = os.environ.get("PITSTUDIO_LLAMACPP")
    if explicit:
        folder = Path(explicit)
    elif os.environ.get("PITSTUDIO_MODELS"):
        folder = Path(os.environ["PITSTUDIO_MODELS"]) / "llama.cpp" / "b11381"
    else:
        raise SkipProbe("set PITSTUDIO_LLAMACPP (folder with llama-server.exe) or PITSTUDIO_MODELS")
    if not (folder / "llama-server.exe").is_file():
        raise SkipProbe(f"llama.cpp b11381 is not unpacked in {folder}: llama-server.exe is missing")
    return folder


def body(r: dict[str, Any]) -> None:
    folder = runtime_dir()
    pins = json.loads(PINS.read_text(encoding="utf-8"))["llamacpp"]
    for name, digest in pins["executables"].items():
        exe = folder / name
        if not exe.is_file() or hashlib.sha256(exe.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"{name} is missing or differs from the pin in studio/reason/pins.json")
    out = subprocess.run(
        [str(folder / "llama-server.exe"), "--version"], capture_output=True, text=True, timeout=60, check=False
    )
    text = (out.stdout + out.stderr).strip()
    if out.returncode != 0 or not text:
        raise RuntimeError(f"llama-server --version failed with code {out.returncode}")
    r["versions"]["llama.cpp"] = pins["build"]
    r["notes"].append(text.splitlines()[-1][:200])
    r["metrics"]["executables_verified"] = len(pins["executables"])


if __name__ == "__main__":
    run_probe("llamacpp", "public", body)
