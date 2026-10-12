"""GNS training as a GPU job: machine lock, hold file, in-run guard, resumable atomic checkpoints (FR-011-44,
NFR-011-04).

    python -m pitstudio_pipeline.surrogates.gns.run_train --data <rollouts> --out <run dir> [--config cfg.json]
    [--device cuda]

What the job does around `stages.s30_train`:
- takes the machine lock `gpu0.compute` (a `filelock` file in the lock directory, waiting up to `--lock-wait-h`),
refuses to run while
  `gpu0.hold` exists, refuses to start hotter than 80 C, and tells the stage which locks it holds
  (`PITSTUDIO_HELD_LOCKS`);
- calls the in-run guard (`studio/bench/gpu_guard.py`) after every optimiser step: it pauses in place when hot, stops
(after a
  checkpoint) at 87 C or on a new WHEA hardware error, and after a 45 minute block the job saves, releases the lock,
  cools down for
  10 minutes and takes the lock again;
- writes `state.pt` atomically (temporary file, then `os.replace`) every `--save-every-steps` optimiser steps, after
every epoch and
  before any stop or cool-down; running the same command again resumes from it when the recorded inputs and
  configuration are
  unchanged (a changed input digest fails `input-stale`; a changed configuration refuses to resume);
- records the GPU time of every segment in the manifest (NFR-011-04).
Exit codes: 0 done, 2 usage or refused (lock, hold, heat, stale input), 5 stopped by the guard (state saved; run again
to resume).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import torch

from pitstudio_pipeline.surrogates.gns import stages, train

DEFAULT_LOCK_DIR = Path(r"C:\Users\felipe.santibanez\Data\_Temp\_locks")
LOCK_NAME = "gpu0.compute"
HOLD_NAME = "gpu0.hold"
EXIT_REFUSED, EXIT_STOPPED = 2, 5


def find_guard_module() -> Any:
    """Import `gpu_guard` from `studio/bench` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        bench = parent / "studio" / "bench"
        if (bench / "gpu_guard.py").is_file():
            sys.path.insert(0, str(bench))
            import gpu_guard

            return gpu_guard
    raise FileNotFoundError("studio/bench/gpu_guard.py not found above this module")


def atomic_save(obj: Any, path: Path) -> None:
    """Write `obj` to a temporary file beside `path`, then replace `path` (atomic on one volume)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    torch.save(obj, tmp)
    os.replace(tmp, path)


def config_digest(cfg: Mapping[str, Any], seed: int) -> str:
    keep = {k: v for k, v in cfg.items() if k not in ("device",)}
    return hashlib.sha256(json.dumps([keep, seed], sort_keys=True, default=str).encode()).hexdigest()


class GpuSession:
    """The machine lock and the guard of one job; `cuda` False (a CPU run) makes every method a no-op."""

    def __init__(
        self,
        lock_dir: Path,
        *,
        cuda: bool,
        lock_wait_h: float = 6.0,
        guard_module: Any = None,
        lock_factory: Callable[[str], Any] | None = None,
        log: Callable[[str], None] = lambda m: print(m, flush=True),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.lock_dir, self.cuda, self.lock_wait_h, self.log, self.sleep = lock_dir, cuda, lock_wait_h, log, sleep
        self.gpu_guard = guard_module
        self._lock_factory = lock_factory
        self._lock: Any = None
        self.guard: Any = None
        self.gpu_s = 0.0
        self._since = 0.0

    def hold_present(self) -> bool:
        return (self.lock_dir / HOLD_NAME).exists()

    def acquire(self) -> None:
        if not self.cuda:
            return
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        if self.hold_present():
            raise SystemExit(f"GPU hold file present in {self.lock_dir}: not starting")
        if self._lock_factory:
            self._lock = self._lock_factory(str(self.lock_dir / LOCK_NAME))
        else:
            from filelock import FileLock

            self._lock = FileLock(str(self.lock_dir / LOCK_NAME))
        deadline = time.time() + self.lock_wait_h * 3600
        while True:
            try:
                self._lock.acquire(timeout=30)
                break
            except Exception:
                if time.time() > deadline:
                    raise SystemExit("the GPU lock stayed busy for the whole wait: giving up") from None
                self.log("[lock] GPU busy; waiting")
        if self.hold_present():
            self._lock.release()
            raise SystemExit("GPU hold file appeared while waiting for the lock")
        os.environ["PITSTUDIO_HELD_LOCKS"] = LOCK_NAME
        os.environ["GPU_LOCK_DIR"] = str(self.lock_dir)
        g = self.gpu_guard
        if self.guard is None:
            self.guard = g.Guard()
        temp = self.guard.read_temp()
        if temp > g.START_MAX_C:
            self.release()
            raise SystemExit(f"GPU at {temp} C, above the start limit {g.START_MAX_C} C")
        self._since = time.time()

    def release(self) -> None:
        if self._lock is not None:
            self.gpu_s += time.time() - self._since
            self._lock.release()
            self._lock = None
        os.environ.pop("PITSTUDIO_HELD_LOCKS", None)

    def step(self) -> str:
        """Guard check between steps: "ok", or "cooldown" after a block (the caller saves, then `cool_down`)."""
        return self.guard.check() if (self.cuda and self.guard is not None) else "ok"

    def cool_down(self) -> None:
        self.release()
        self.guard.cool_down()
        self.acquire()


class JobHooks(train.TrainHooks):
    """Saves `state.pt` atomically on a schedule, before stops and cool-downs; resumes from it."""

    def __init__(
        self, out: Path, session: GpuSession, *, digest: str, inputs: Sequence[Mapping[str, str]], save_every: int
    ) -> None:
        self.out, self.session, self.digest, self.save_every = out, session, digest, save_every
        self.inputs = [dict(i) for i in inputs]
        self.steps = 0
        self.elapsed_before_s = 0.0
        self.resume = None
        state_path = out / "state.pt"
        if state_path.is_file():
            saved = torch.load(state_path, map_location="cpu", weights_only=False)
            if saved["digest"] != digest:
                raise SystemExit("state.pt was written for another configuration or seed: use a new --out or delete it")
            self.resume = saved["train"]
            self.elapsed_before_s = float(saved.get("elapsed_s", 0.0))
        self._t0 = time.time()

    def _save(self, snapshot: Callable[[], dict[str, Any]]) -> None:
        elapsed = self.elapsed_before_s + (time.time() - self._t0)
        atomic_save(
            {"digest": self.digest, "inputs": self.inputs, "elapsed_s": elapsed, "train": snapshot()},
            self.out / "state.pt",
        )

    def on_step(self, snapshot: Callable[[], dict[str, Any]]) -> None:
        self.steps += 1
        try:
            verdict = self.session.step()
        except Exception:  # GuardStop: save first, then let it propagate
            self._save(snapshot)
            raise
        if verdict == "cooldown":
            self._save(snapshot)
            self.session.cool_down()
        elif self.save_every and self.steps % self.save_every == 0:
            self._save(snapshot)

    def on_epoch(self, snapshot: Callable[[], dict[str, Any]]) -> None:
        self._save(snapshot)


def run_job(
    data_dir: Path,
    out: Path,
    config: Mapping[str, Any],
    *,
    seed: int,
    device: str,
    lock_dir: Path = DEFAULT_LOCK_DIR,
    save_every: int = 200,
    lock_wait_h: float = 6.0,
    session: GpuSession | None = None,
) -> int:
    """Run (or resume) the training under the lock and the guard; returns the process exit code."""
    out.mkdir(parents=True, exist_ok=True)
    cuda = device.startswith("cuda")
    if session is None:
        session = GpuSession(
            lock_dir, cuda=cuda, lock_wait_h=lock_wait_h, guard_module=find_guard_module() if cuda else None
        )
    dataset = stages.Dataset(data_dir)
    cfg = {**stages.DEFAULT_CONFIG, **config}
    inputs = dataset.inputs(["train", "val"])
    hooks = JobHooks(out, session, digest=config_digest(cfg, seed), inputs=inputs, save_every=save_every)
    if hooks.resume is not None:
        from pitstudio.surrogate_inputs import verify_inputs

        saved = torch.load(out / "state.pt", map_location="cpu", weights_only=False)["inputs"]
        if saved != hooks.inputs:
            raise SystemExit("state.pt was made from other rollout files: refusing to resume")
        verify_inputs(inputs, root=dataset.root)
    session.acquire()
    try:
        stages.s30_train(dataset, out, config, seed=seed, device=device, env=os.environ, hooks=hooks)
        session.release()
        manifest = json.loads((out / "train_manifest.json").read_text(encoding="utf-8"))
        manifest["gpu_segments_s"] = session.gpu_s
        (out / "train_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
        (out / "DONE").write_text("done\n", encoding="utf-8")
        return 0
    except BaseException as exc:
        name = type(exc).__name__
        if name == "GuardStop":
            (out / "STOPPED").write_text(f"{exc}\n", encoding="utf-8")
            print(f"[job] stopped by the guard ({exc}); state saved, run the same command to resume", flush=True)
            return EXIT_STOPPED
        raise
    finally:
        session.release()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pitstudio_pipeline.surrogates.gns.run_train", description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--lock-dir", type=Path, default=DEFAULT_LOCK_DIR)
    parser.add_argument("--lock-wait-h", type=float, default=6.0)
    parser.add_argument("--save-every-steps", type=int, default=200)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
    try:
        return run_job(
            args.data,
            args.out,
            config,
            seed=args.seed,
            device=args.device,
            lock_dir=args.lock_dir,
            save_every=args.save_every_steps,
            lock_wait_h=args.lock_wait_h,
        )
    except SystemExit as exc:
        print(f"[job] refused: {exc}", flush=True)
        return EXIT_REFUSED


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
