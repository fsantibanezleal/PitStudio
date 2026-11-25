# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: PT018  (compound assertions read as one fact in these tests)
"""GPU session: CUDA visibility, start temperature, the machine lock gpu0.compute and the in-run guard."""

from __future__ import annotations

import subprocess

import pytest
from filelock import FileLock, Timeout
from pitstudio_rtx.render.gpu import GpuError, assert_cuda_visible, cuda_devices, gpu_session, load_guard_module

SMI = "0, NVIDIA RTX 5000 Ada Generation Laptop GPU, 582.78, 68\n"


def smi(out: str = SMI, code: int = 0):
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")

    return run


class FakeGuard:
    def __init__(self, temp: int = 60, results: tuple[str, ...] = ()) -> None:
        self.temp, self.results = temp, list(results)
        self.checks = 0
        self.cooled = 0
        self.paused_s = 0.0
        self.lock_free_during_cooldown: bool | None = None
        self.lock_path = None

    def read_temp(self) -> int:
        return self.temp

    def check(self) -> str:
        self.checks += 1
        return self.results.pop(0) if self.results else "ok"

    def cool_down(self) -> None:
        self.cooled += 1
        if self.lock_path is not None:
            probe = FileLock(str(self.lock_path))
            try:
                probe.acquire(timeout=0)
            except Timeout:
                self.lock_free_during_cooldown = False
            else:
                self.lock_free_during_cooldown = True
                probe.release()


def test_cuda_devices_parse():
    (dev,) = cuda_devices(smi())
    assert (
        dev.index == 0 and dev.name.startswith("NVIDIA RTX 5000") and dev.driver == "582.78" and dev.temperature_c == 68
    )


def test_no_cuda_device_is_an_error():
    with pytest.raises(GpuError, match="no CUDA device"):
        assert_cuda_visible(smi(""))
    with pytest.raises(GpuError, match="nvidia-smi"):
        assert_cuda_visible(smi("", 9))


def test_guard_module_is_the_shared_one():
    assert load_guard_module().START_MAX_C == 80


def test_refuses_to_start_above_80_c(tmp_path):
    with (
        pytest.raises(GpuError, match="above the start limit"),
        gpu_session(tmp_path / "gpu0.compute", run=smi(), guard=FakeGuard(temp=81)),
    ):
        pytest.fail("the session must not start")
    # exactly 80 C is allowed
    with gpu_session(tmp_path / "gpu0.compute", run=smi(), guard=FakeGuard(temp=80)):
        pass


def test_holds_the_machine_lock_for_the_session_only(tmp_path):
    lock = tmp_path / "gpu0.compute"
    with gpu_session(lock, run=smi(), guard=FakeGuard()):
        probe = FileLock(str(lock))
        with pytest.raises(Timeout):
            probe.acquire(timeout=0)
    probe.acquire(timeout=0)
    probe.release()


def test_a_held_lock_blocks_the_start(tmp_path):
    lock = tmp_path / "gpu0.compute"
    other = FileLock(str(lock))
    with (
        other,
        pytest.raises(GpuError, match=r"gpu0\.compute"),
        gpu_session(lock, run=smi(), guard=FakeGuard(), lock_timeout_s=0.1),
    ):
        pytest.fail("the lock is held elsewhere")


def test_tick_calls_the_guard_and_counts_gpu_time(tmp_path):
    clock = iter([0.0, 1.0, 5.0, 12.0, 100.0, 200.0, 300.0])
    guard = FakeGuard()
    with gpu_session(tmp_path / "l", run=smi(), guard=guard, clock=lambda: next(clock)) as session:
        session.tick()
        session.tick()
    assert guard.checks == 2
    assert session.gpu_seconds > 0


def test_cooldown_releases_the_lock_then_takes_it_back(tmp_path):
    lock = tmp_path / "gpu0.compute"
    guard = FakeGuard(results=("cooldown",))
    guard.lock_path = lock
    with gpu_session(lock, run=smi(), guard=guard) as session:
        session.tick()
        assert guard.cooled == 1
        assert guard.lock_free_during_cooldown is True
        with pytest.raises(Timeout):
            FileLock(str(lock)).acquire(timeout=0)  # held again after the cool-down
