"""Process trees (Windows job objects, Linux process groups) and keep-awake (FR-002-27, FR-002-29)."""

from __future__ import annotations

import contextlib
import ctypes
import os
import signal
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

WIN = sys.platform == "win32"


def set_thread_execution_state(flags: int) -> int:
    """kernel32 SetThreadExecutionState; a no-op (returns 0) off Windows."""
    return int(ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))) if WIN else 0


class Tree:
    """One stage process and everything it starts: killed together on cancel, timeout, or the runner's death."""

    def __init__(self, argv: list[str], env: dict[str, str], cwd: Path, log: Any) -> None:
        kw: dict[str, Any] = {
            "stdout": log,
            "stderr": subprocess.STDOUT,
            "env": env,
            "cwd": str(cwd),
            "start_new_session": not WIN,
        }
        self.job = None
        if WIN:
            kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        self.proc = subprocess.Popen(argv, **kw)
        if WIN:
            k32, void = ctypes.windll.kernel32, ctypes.c_void_p
            k32.CreateJobObjectW.restype = k32.OpenProcess.restype = void
            self.job = k32.CreateJobObjectW(None, None)
            info = ctypes.create_string_buffer(
                144
            )  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION; LimitFlags sits at offset 16
            struct.pack_into("<I", info, 16, 0x2000)  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            k32.SetInformationJobObject(void(self.job), 9, info, len(info))
            proc = k32.OpenProcess(0x1F0FFF, False, self.proc.pid)
            k32.AssignProcessToJobObject(void(self.job), void(proc))
            k32.CloseHandle(void(proc))

    def kill(self) -> None:
        """End the whole tree; returns once the stage process is reaped (or after 10 s)."""
        self.close(wait=False)
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def freeze(self, on: bool) -> None:
        """Suspend (on) or resume the whole tree: how a thermal pause or a cool-down is enforced."""
        import psutil

        with contextlib.suppress(psutil.Error):
            root = psutil.Process(self.proc.pid)
            for p in [root, *root.children(recursive=True)]:
                p.suspend() if on else p.resume()

    def close(self, wait: bool = True) -> None:
        """Whatever the stage left running goes with it (kill-on-close on Windows, the process group on Linux)."""
        if WIN and self.job:
            if not wait:
                ctypes.windll.kernel32.TerminateJobObject(ctypes.c_void_p(self.job), 1)
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self.job))
            self.job = None
        elif not WIN:
            with contextlib.suppress(OSError):
                os.killpg(self.proc.pid, signal.SIGKILL)
