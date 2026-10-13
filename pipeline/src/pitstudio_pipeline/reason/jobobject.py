"""A Windows job object for the stage's child processes (FR-015-11).

Every process of the stage (the llama-server) is assigned to one job; closing or terminating the job kills them all,
so no child outlives the stage even if the stage crashes (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`). On other platforms
the class is a no-op: the driver's own `stop()` still kills the process it started."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_KILL_ON_CLOSE = 0x2000
_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA_TERMINATE = 0x0100 | 0x0001


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ("a", "b", "c", "d", "e", "f")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class JobObject:
    """`assign(pid)` puts a process in the job, `terminate()` kills every process in it, `close()` releases it."""

    def __init__(self) -> None:
        self._handle = None
        if sys.platform != "win32":
            return
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        self._k32 = k32
        handle = k32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        info = _ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = _KILL_ON_CLOSE
        if not k32.SetInformationJobObject(
            handle, _EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)
        ):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
        self._handle = handle

    def assign(self, pid: int) -> None:
        if self._handle is None:
            return
        k32 = self._k32
        k32.OpenProcess.restype = wintypes.HANDLE
        proc = k32.OpenProcess(_PROCESS_SET_QUOTA_TERMINATE, False, pid)
        if not proc:
            raise OSError(ctypes.get_last_error(), f"OpenProcess({pid}) failed")
        try:
            if not k32.AssignProcessToJobObject(self._handle, proc):
                raise OSError(ctypes.get_last_error(), f"AssignProcessToJobObject({pid}) failed")
        finally:
            k32.CloseHandle(proc)

    def terminate(self) -> None:
        if self._handle is not None:
            self._k32.TerminateJobObject(self._handle, 1)

    def close(self) -> None:
        if self._handle is not None:
            self._k32.CloseHandle(self._handle)
            self._handle = None
