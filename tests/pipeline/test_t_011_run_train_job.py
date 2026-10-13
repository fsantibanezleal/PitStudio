"""The GNS training job (`run_train`): resumable atomic checkpoints, the machine lock, the hold file and the in-run
guard, on the CPU
with a fake lock and a fake guard (not a locked test; no CUDA is used).

Oracles: a run interrupted by a guard stop and resumed gives the same per-epoch log as the same run uninterrupted (the
data order and
the noise are fixed by (seed, epoch, step)); `state.pt` is replaced atomically (no temporary file is left); a hold file
refuses the job
before the lock is taken; the lock is released at the end and the stage sees `PITSTUDIO_HELD_LOCKS` while it holds it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("pyarrow")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).parent))

import test_t_011_stages_smoke as smoke  # noqa: E402
from pitstudio_pipeline.surrogates.gns import run_train  # noqa: E402

CONFIG = {
    "noise_scales": [0.0],
    "epochs": 2,
    "batch_size": 1,
    "lr": 1e-3,
    "latent": 8,
    "steps": 1,
    "samples_per_epoch": 5,
    "val_samples": 2,
    "connectivity_radius": 2.5 * smoke.fx.D,
    "checkpoint_steps": False,
}


class FakeGuardStop(RuntimeError):
    pass


FakeGuardStop.__name__ = "GuardStop"


class StopAfter(run_train.GpuSession):
    """A CPU session whose guard raises a GuardStop at the n-th step."""

    def __init__(self, n: int | None) -> None:
        super().__init__(Path("."), cuda=False)
        self.n, self.calls = n, 0

    def step(self) -> str:
        self.calls += 1
        if self.n is not None and self.calls == self.n:
            raise FakeGuardStop("thermal: test stop")
        return "ok"


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("job_rollouts")
    smoke.write_dataset(root)
    (root / "_state.json").write_text(
        json.dumps({"slots": [{"id": g, "split": s} for g, (_, _, s) in smoke.GEOMS.items()]}), encoding="utf-8"
    )
    return root


def log_of(out: Path) -> list[dict]:
    return json.loads((out / "train_log.json").read_text(encoding="utf-8"))["epochs"]


def test_a_stop_saves_the_state_and_a_second_run_resumes_to_the_same_result(data_dir: Path, tmp_path: Path) -> None:
    straight = tmp_path / "straight"
    assert (
        run_train.run_job(data_dir, straight, CONFIG, seed=3, device="cpu", session=StopAfter(None), save_every=2) == 0
    )
    stopped = tmp_path / "stopped"
    assert (
        run_train.run_job(data_dir, stopped, CONFIG, seed=3, device="cpu", session=StopAfter(7), save_every=2)
        == run_train.EXIT_STOPPED
    )
    assert (stopped / "state.pt").is_file()
    assert (stopped / "STOPPED").is_file()
    assert not (stopped / "checkpoint.pt").exists()
    assert not list(stopped.glob("*.tmp"))
    assert (
        run_train.run_job(data_dir, stopped, CONFIG, seed=3, device="cpu", session=StopAfter(None), save_every=2) == 0
    )
    assert (stopped / "DONE").is_file()
    a, b = log_of(straight), log_of(stopped)
    assert [e["epoch"] for e in b] == [1, 2]
    for x, y in zip(a, b, strict=True):
        assert x["train_loss"] == pytest.approx(y["train_loss"], rel=1e-5)
        assert x["val_loss"] == pytest.approx(y["val_loss"], rel=1e-5)


def test_a_state_of_another_configuration_or_seed_is_not_resumed(data_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    assert (
        run_train.run_job(data_dir, out, CONFIG, seed=1, device="cpu", session=StopAfter(3), save_every=1)
        == run_train.EXIT_STOPPED
    )
    with pytest.raises(SystemExit, match="another configuration"):
        run_train.run_job(data_dir, out, CONFIG, seed=2, device="cpu", session=StopAfter(None))


def test_a_changed_rollout_file_fails_the_resume_before_any_step(data_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    run_train.run_job(data_dir, out, CONFIG, seed=1, device="cpu", session=StopAfter(3), save_every=1)
    payload = data_dir / "payload" / "g001-s1000.parquet"
    original = payload.read_bytes()
    payload.write_bytes(original + b"\x00")
    try:
        from pitstudio.surrogate_inputs import InputStaleError

        with pytest.raises(InputStaleError):
            run_train.run_job(data_dir, out, CONFIG, seed=1, device="cpu", session=StopAfter(None))
    finally:
        payload.write_bytes(original)


class FakeLock:
    def __init__(self, path: str) -> None:
        self.path, self.held, self.seen_env = path, False, None

    def acquire(self, timeout: float = 0) -> None:
        self.held = True

    def release(self) -> None:
        self.held = False


def fake_session(lock_dir: Path, temp: int = 60) -> tuple[run_train.GpuSession, FakeLock]:
    lock = FakeLock("x")
    guard_module = SimpleNamespace(
        START_MAX_C=80,
        Guard=lambda: SimpleNamespace(read_temp=lambda: temp, check=lambda: "ok", cool_down=lambda: None),
    )
    session = run_train.GpuSession(lock_dir, cuda=True, guard_module=guard_module, lock_factory=lambda p: lock)
    return session, lock


def test_the_session_takes_and_releases_the_lock_and_exports_the_held_locks(tmp_path: Path) -> None:
    session, lock = fake_session(tmp_path)
    session.acquire()
    try:
        assert lock.held is True
        assert os.environ["PITSTUDIO_HELD_LOCKS"] == "gpu0.compute"
        assert os.environ["GPU_LOCK_DIR"] == str(tmp_path)
    finally:
        session.release()
    assert lock.held is False
    assert "PITSTUDIO_HELD_LOCKS" not in os.environ


def test_a_hold_file_refuses_the_job_before_the_lock_is_taken(tmp_path: Path) -> None:
    (tmp_path / "gpu0.hold").write_text("thermal", encoding="utf-8")
    session, lock = fake_session(tmp_path)
    with pytest.raises(SystemExit, match="hold"):
        session.acquire()
    assert lock.held is False


def test_a_hot_gpu_refuses_to_start_and_releases_the_lock(tmp_path: Path) -> None:
    session, lock = fake_session(tmp_path, temp=85)
    with pytest.raises(SystemExit, match="85 C"):
        session.acquire()
    assert lock.held is False


def test_the_checkpoint_write_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "state.pt"
    run_train.atomic_save({"a": 1}, target)
    run_train.atomic_save({"a": 2}, target)
    assert torch.load(target, weights_only=False) == {"a": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["state.pt"]
