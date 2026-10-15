"""GNS training (s30_train; FR-011-04): one-step normalised-acceleration MSE with random-walk velocity noise.

Everything that is chosen is chosen on the validation geometries only: the noise scale (a short pilot per candidate, in
the order of `noise_scales`), the checkpoint epoch (the argmin of the logged per-epoch validation loss). The test split
is
never read. Normalisation statistics (velocities, accelerations by finite differences) come from the training split
alone.

Sample (rollout r, frame t): inputs are the velocities (x_k - x_{k-1}) / dt for the five frames ending at t and the
positions
at t; the target acceleration is a = ((x_{t+1} - x_t) / dt - v_t) / dt, so that the semi-implicit Euler update
reproduces
x_{t+1} (FR-011-01). With noise, v_t carries the noise and the target is corrected by it (the noise-correcting target of
Sanchez-Gonzalez et al. 2020). Noise scales are fractions of the training velocity standard deviation.
"""

from __future__ import annotations

import copy
import math
import queue
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch

from pitstudio.granular.graph import K_MAX, build_radius_graph
from pitstudio_pipeline.surrogates.errors import DatasetError
from pitstudio_pipeline.surrogates.fixture import is_fixture, stamp
from pitstudio_pipeline.surrogates.gns.graph_torch import build_radius_graph_torch
from pitstudio_pipeline.surrogates.gns.model import HISTORY, GnsStep

STD_FLOOR = 1e-8
DEVICE_GRAPH = True  # build the radius graph with torch on the training device (run_train self-checks it)


@dataclass
class TrainResult:
    checkpoint: dict[str, Any]
    log: dict[str, Any]
    model: GnsStep | None = None


# ------------------------------------------------------------------ pieces (each tested alone)


def random_walk_noise(n_particles: int, history: int, scale: float, *, seed: int) -> np.ndarray:
    """Random-walk noise [n, history, 2]: the cumulative sum of independent Gaussian increments of std scale /
    sqrt(history).

    The variance grows with the history index, it is zero for scale 0, linear in `scale` and reproducible by `seed`.
    """
    if not (isinstance(n_particles, int | np.integer) and n_particles >= 1):
        raise ValueError(f"n_particles must be a positive integer, got {n_particles!r}")
    if not (isinstance(history, int | np.integer) and history >= 1):
        raise ValueError(f"history must be a positive integer, got {history!r}")
    if not (isinstance(scale, int | float | np.floating) and math.isfinite(scale) and scale >= 0):
        raise ValueError(f"scale must be a finite non-negative number, got {scale!r}")
    increments = np.random.default_rng(seed).standard_normal((n_particles, history, 2))
    return (scale / math.sqrt(history)) * np.cumsum(increments, axis=1)


def one_step_loss(
    model: GnsStep, batch: Mapping[str, torch.Tensor], *, stats: Mapping[str, Mapping[str, Sequence[float]]]
) -> torch.Tensor:
    """Mean squared error of the normalised accelerations; `stats["acceleration"]` holds the mean and std
    (FR-011-04)."""
    pred = model.acceleration_unchecked(
        batch["positions"],
        batch["velocities"],
        batch["particle_type"],
        batch["bounds"],
        batch["neighbour_index"],
        batch["neighbour_mask"],
    )
    mean = torch.as_tensor(stats["acceleration"]["mean"], dtype=pred.dtype, device=pred.device)
    std = torch.as_tensor(stats["acceleration"]["std"], dtype=pred.dtype, device=pred.device)
    target = batch["target_acceleration"].to(pred.dtype)
    return torch.mean(((pred - mean) / std - (target - mean) / std) ** 2)


def compute_stats(rollouts: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, list[float]]]:
    """Mean and std of the velocities and accelerations (finite differences) over the given rollouts, per component."""
    acc = {"velocities": np.zeros((3, 2)), "acceleration": np.zeros((3, 2))}  # count, sum, sum of squares
    for r in rollouts:
        pos = np.asarray(r["positions"], dtype=np.float64)
        dt = float(r["dt"])
        vel = np.diff(pos, axis=0) / dt
        acceleration = np.diff(vel, axis=0) / dt
        for name, values in (("velocities", vel), ("acceleration", acceleration)):
            flat = values.reshape(-1, 2)
            acc[name][0] += flat.shape[0]
            acc[name][1] += flat.sum(axis=0)
            acc[name][2] += (flat**2).sum(axis=0)
    out: dict[str, dict[str, list[float]]] = {}
    for name, (count, total, squares) in acc.items():
        mean = total / count
        std = np.sqrt(np.maximum(squares / count - mean**2, 0.0))
        out[name] = {"mean": [float(v) for v in mean], "std": [float(max(v, STD_FLOOR)) for v in std]}
    return out


def make_sample(
    rollout: Mapping[str, Any],
    t: int,
    *,
    radius: float | None = None,
    noise_scale: float = 0.0,
    velocity_std: Sequence[float] = (1.0, 1.0),
    seed: int = 0,
    device: torch.device | None = None,
) -> dict[str, Any]:
    """Network inputs and the target acceleration of frame `t` (needs frames t - 5 ... t + 1).

    With `device` the radius graph is built there with torch (`graph_torch`, equal to the CPU oracle) and the graph
    arrays are device tensors; without it the CPU oracle builds them as numpy arrays.
    """
    pos = rollout["positions"]
    dt = float(rollout["dt"])
    window = np.asarray(pos[t - HISTORY : t + 2], dtype=np.float64)
    history = (np.diff(window[: HISTORY + 1], axis=0) / dt).transpose(1, 0, 2)  # [N, 5, 2]
    forward = (window[HISTORY + 1] - window[HISTORY]) / dt
    if noise_scale > 0:
        history = history + random_walk_noise(history.shape[0], HISTORY, noise_scale, seed=seed) * np.asarray(
            velocity_std
        )
    target = (forward - history[:, -1, :]) / dt
    current = np.asarray(pos[t], dtype=np.float32)
    radius = radius if radius is not None else 2.5 * float(rollout["d"])
    if device is not None and DEVICE_GRAPH:
        index, mask, _ = build_radius_graph_torch(torch.as_tensor(current, device=device), radius, K_MAX)
    else:
        graph = build_radius_graph(current, radius, K_MAX)
        index, mask = graph.neighbour_index, graph.neighbour_mask
    return {
        "positions": current,
        "velocities": history.astype(np.float32),
        "particle_type": np.asarray(rollout["particle_types"], dtype=np.int64),
        "bounds": np.asarray(rollout["bounds"], dtype=np.float32),
        "neighbour_index": index,
        "neighbour_mask": mask,
        "target_acceleration": target.astype(np.float32),
    }


def collate(samples: Sequence[Mapping[str, Any]], device: torch.device) -> dict[str, torch.Tensor]:
    """One big graph from several samples: neighbour indices offset, bounds repeated per particle."""
    offset = 0
    keys = ("positions", "velocities", "particle_type", "neighbour_index", "neighbour_mask", "target_acceleration")
    parts: dict[str, list[torch.Tensor]] = {k: [] for k in (*keys, "bounds")}
    for s in samples:
        t = {k: torch.as_tensor(s[k], device=device) for k in (*keys, "bounds")}
        n = t["positions"].shape[0]
        for k in ("positions", "velocities", "particle_type", "neighbour_mask", "target_acceleration"):
            parts[k].append(t[k])
        parts["neighbour_index"].append(t["neighbour_index"] + offset)
        parts["bounds"].append(t["bounds"].expand(n, 4))
        offset += n
    return {k: torch.cat(v, dim=0) for k, v in parts.items()}


class _Prefetch:
    """Builds the next batches in a worker thread while the current optimiser step runs (queue of `depth`)."""

    def __init__(self, make_batches: Callable[[], Any], depth: int = 2) -> None:
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=depth)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._work, args=(make_batches,), daemon=True)
        self._thread.start()

    def _put(self, item: Any) -> bool:
        while not self._stop.is_set():
            try:
                self._queue.put(item, timeout=0.1)
                return True
            except queue.Full:
                continue
        return False

    def _work(self, make_batches: Callable[[], Any]) -> None:
        try:
            for item in make_batches():
                if not self._put(("item", item)):
                    return
            self._put(("end", None))
        except BaseException as exc:
            self._put(("error", exc))

    def __iter__(self):
        while True:
            kind, payload = self._queue.get()
            if kind == "end":
                return
            if kind == "error":
                raise payload
            yield payload

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=30)


# ------------------------------------------------------------------ configuration


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return the config with defaults filled in; raise ValueError for any invalid value, before any data is read."""
    cfg = dict(config)
    scales = cfg.get("noise_scales")
    if not isinstance(scales, Sequence) or isinstance(scales, str) or len(scales) < 1:
        raise ValueError("noise_scales must list at least one non-negative scale")
    if not all(isinstance(s, int | float) and math.isfinite(s) and s >= 0 for s in scales):
        raise ValueError(f"noise_scales must be finite and non-negative, got {list(scales)}")
    for key, minimum in (("epochs", 1), ("batch_size", 1), ("latent", 1), ("steps", 1)):
        value = cfg.get(key, {"latent": 128, "steps": 10}.get(key))
        if not isinstance(value, int | np.integer) or isinstance(value, bool) or value < minimum:
            raise ValueError(f"{key} must be an integer >= {minimum}, got {value!r}")
        cfg[key] = int(value)
    for key in ("lr", "connectivity_radius"):
        value = cfg.get(key)
        if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be a positive finite number, got {value!r}")
    cfg["noise_scales"] = [float(s) for s in scales]
    cfg.setdefault("device", "cpu")
    cfg.setdefault("checkpoint_steps", False)
    cfg.setdefault("samples_per_epoch", None)
    cfg.setdefault("val_samples", 64)
    cfg.setdefault("lr_final_ratio", 1.0)
    cfg.setdefault("pilot_epochs", None)
    for key in ("samples_per_epoch", "pilot_epochs"):
        if cfg[key] is not None and (not isinstance(cfg[key], int) or cfg[key] < 1):
            raise ValueError(f"{key} must be a positive integer or None, got {cfg[key]!r}")
    if not isinstance(cfg["val_samples"], int) or cfg["val_samples"] < 1:
        raise ValueError(f"val_samples must be a positive integer, got {cfg['val_samples']!r}")
    if not (isinstance(cfg["lr_final_ratio"], int | float) and 0 < cfg["lr_final_ratio"] <= 1):
        raise ValueError("lr_final_ratio must be in (0, 1]")
    return cfg


# ------------------------------------------------------------------ the training run


def _sample_index(rollouts: Sequence[Mapping[str, Any]]) -> list[tuple[int, int]]:
    index = []
    for r, rollout in enumerate(rollouts):
        frames = rollout["positions"].shape[0]
        index.extend((r, t) for t in range(HISTORY, frames - 1))
    return index


class _Run:
    """One training run (model, optimiser, data order) shared by the noise pilots and the final training."""

    def __init__(
        self,
        cfg: Mapping[str, Any],
        train_rollouts: Sequence[Mapping[str, Any]],
        val_rollouts: Sequence[Mapping[str, Any]],
        stats: Mapping[str, Any],
        n_types: int,
        dt: float,
        seed: int,
        total_steps_hint: int,
    ) -> None:
        self.cfg, self.train, self.val, self.stats, self.seed = cfg, train_rollouts, val_rollouts, stats, seed
        self.device = torch.device(cfg["device"])
        torch.manual_seed(seed)
        self.model = GnsStep(
            connectivity_radius=cfg["connectivity_radius"],
            frame_interval=dt,
            n_particle_types=n_types,
            latent=cfg["latent"],
            steps=cfg["steps"],
            checkpoint_steps=cfg["checkpoint_steps"],
        )
        self.model.set_normalisation(
            velocity_mean=stats["velocities"]["mean"],
            velocity_std=stats["velocities"]["std"],
            acceleration_mean=stats["acceleration"]["mean"],
            acceleration_std=stats["acceleration"]["std"],
        )
        self.model.to(self.device)
        self.optimiser = torch.optim.Adam(self.model.parameters(), lr=cfg["lr"])
        gamma = cfg["lr_final_ratio"] ** (1.0 / max(1, total_steps_hint))
        self.scheduler = torch.optim.lr_scheduler.ExponentialLR(self.optimiser, gamma=gamma)
        self.rng = np.random.default_rng(seed + 1)
        self.train_index = _sample_index(train_rollouts)
        self.val_index = _sample_index(val_rollouts)
        if not self.train_index or not self.val_index:
            raise DatasetError("the training and validation rollouts need frames t - 5 ... t + 1: too few frames")
        pick = np.random.default_rng(seed + 2).permutation(len(self.val_index))[: cfg["val_samples"]]
        self.val_pick = [self.val_index[i] for i in sorted(pick)]
        self.noise_counter = 0
        self.on_log: Callable[[int, int, float, int], None] | None = None

    def val_loss(self) -> float:
        self.model.eval()
        total, count = 0.0, 0
        with torch.no_grad():
            for lo in range(0, len(self.val_pick), self.cfg["batch_size"]):
                chunk = self.val_pick[lo : lo + self.cfg["batch_size"]]
                batch = collate(
                    [
                        make_sample(self.val[r], t, radius=self.cfg["connectivity_radius"], device=self.device)
                        for r, t in chunk
                    ],
                    self.device,
                )
                weight = batch["positions"].shape[0]
                total += float(one_step_loss(self.model, batch, stats=self.stats)) * weight
                count += weight
        return total / count

    def epoch(
        self,
        noise_scale: float,
        epoch_index: int = 0,
        start_chunk: int = 0,
        partial: tuple[float, int] = (0.0, 0),
        on_step: Callable[[int, float, int], None] | None = None,
    ) -> float:
        """One epoch in a data order fixed by (seed, epoch_index), resumable from `start_chunk`."""
        self.model.train()
        order = np.random.default_rng([self.seed + 1, epoch_index]).permutation(len(self.train_index))
        limit = self.cfg["samples_per_epoch"] or len(order)
        order = order[:limit]
        size = self.cfg["batch_size"]
        total, count = partial
        radius = self.cfg["connectivity_radius"]

        def batches():
            for chunk_no, lo in enumerate(range(0, len(order), size)):
                if chunk_no < start_chunk:
                    continue
                chunk = [self.train_index[i] for i in order[lo : lo + size]]
                samples = [
                    make_sample(
                        self.train[r],
                        t,
                        radius=radius,
                        noise_scale=noise_scale,
                        velocity_std=self.stats["velocities"]["std"],
                        seed=self.seed * 1_000_003 + epoch_index * 1_000_000 + lo + k,
                        device=self.device,
                    )
                    for k, (r, t) in enumerate(chunk)
                ]
                yield chunk_no, collate(samples, self.device)

        feed = _Prefetch(batches)
        try:
            for chunk_no, batch in feed:
                self.optimiser.zero_grad(set_to_none=True)
                loss = one_step_loss(self.model, batch, stats=self.stats)
                loss.backward()
                self.optimiser.step()
                self.scheduler.step()
                weight = batch["positions"].shape[0]
                step_loss = float(loss.detach())
                total += step_loss * weight
                count += weight
                if on_step:
                    on_step(chunk_no + 1, total, count)
                if self.on_log:
                    self.on_log(epoch_index, chunk_no + 1, step_loss, weight)
        finally:
            feed.close()
        return total / count

    def state(self) -> dict[str, Any]:
        return {
            "model": {k: v.detach().cpu().clone() for k, v in self.model.state_dict().items()},
            "optimiser": self.optimiser.state_dict(),
            "scheduler": self.scheduler.state_dict(),
        }

    def load(self, state: Mapping[str, Any]) -> None:
        self.model.load_state_dict(state["model"])
        self.optimiser.load_state_dict(state["optimiser"])
        self.scheduler.load_state_dict(state["scheduler"])


class TrainHooks:
    """Hooks of a long run: `resume` (a state saved earlier or None) and the two callbacks the runner implements.

    `on_step(snapshot)` is called after every optimiser step of the final training, `on_epoch(snapshot)` after every
    pilot candidate
    and every epoch; `snapshot()` returns the picklable state to resume from. A hook may raise to stop the run.
    """

    resume: dict[str, Any] | None = None

    def on_step(self, snapshot: Callable[[], dict[str, Any]]) -> None:  # pragma: no cover - default does nothing
        return None

    def on_epoch(self, snapshot: Callable[[], dict[str, Any]]) -> None:  # pragma: no cover - default does nothing
        return None

    def on_log(
        self, epoch_index: int, chunk: int, loss: float, batch_size: int
    ) -> None:  # pragma: no cover - default does nothing
        """After every optimiser step of the final training: epoch, step within it, step loss, samples in it."""
        return None


def train_gns(
    splits: Any,
    config: Mapping[str, Any],
    *,
    seed: int,
    dataset_manifest: Mapping[str, Any] | None = None,
    on_epoch: Callable[[dict[str, Any]], None] | None = None,
    hooks: TrainHooks | None = None,
) -> TrainResult:
    """Train the GNS on `splits.rollouts("train")`, select on `splits.rollouts("val")`, never read "test" (FR-011-04).

    `config`: noise_scales (>= 1 non-negative floats), epochs, batch_size, lr, connectivity_radius, latent, steps;
    optional
    device, checkpoint_steps, samples_per_epoch, val_samples, lr_final_ratio, pilot_epochs.
    `dataset_manifest["fixture"]` makes the
    run flag its checkpoint and log `fixture: true` (FR-011-49). Returns the checkpoint, the log and the trained model.
    """
    cfg = validate_config(config)
    fixture = is_fixture(dataset_manifest)  # a non-boolean flag stops the run before any work
    train_rollouts = splits.rollouts("train")
    val_rollouts = splits.rollouts("val")
    if len(train_rollouts) == 0:
        raise DatasetError("the training split is empty")
    if len(val_rollouts) == 0:
        raise DatasetError("the validation split is empty")
    for rollouts in (train_rollouts, val_rollouts):
        if hasattr(rollouts, "preload"):
            rollouts.preload()  # decode each payload once, in parallel, and keep it in memory
    stats = compute_stats(train_rollouts)  # training split alone
    n_types = 1 + max(int(np.max(r["particle_types"])) for r in train_rollouts)
    dt = float(np.mean([r["dt"] for r in train_rollouts]))
    steps_per_epoch = math.ceil(
        min(cfg["samples_per_epoch"] or math.inf, len(_sample_index(train_rollouts))) / cfg["batch_size"]
    )

    hooks = hooks or TrainHooks()
    resume = hooks.resume
    candidates: list[dict[str, Any]] = list(resume["candidates"]) if resume else []
    scales = cfg["noise_scales"]
    if resume and resume.get("chosen") is not None:
        chosen = resume["chosen"]
    elif len(scales) == 1:
        chosen = scales[0]
        candidates = [{"scale": chosen, "val_loss": None}]
    else:
        pilot_epochs = cfg["pilot_epochs"] or max(1, min(cfg["epochs"], cfg["epochs"] // 3 or 1))
        for scale in scales[len(candidates) :]:
            pilot = _Run(cfg, train_rollouts, val_rollouts, stats, n_types, dt, seed, pilot_epochs * steps_per_epoch)
            best = math.inf
            for e in range(pilot_epochs):
                pilot.epoch(scale, e)
                best = min(best, pilot.val_loss())
            candidates.append({"scale": scale, "val_loss": best})
            hooks.on_epoch(lambda: {"candidates": list(candidates), "chosen": None})
        chosen = min(candidates, key=lambda c: c["val_loss"])["scale"]

    run = _Run(cfg, train_rollouts, val_rollouts, stats, n_types, dt, seed, cfg["epochs"] * steps_per_epoch)
    run.on_log = hooks.on_log
    epochs_log: list[dict[str, Any]] = []
    best_loss, best_epoch, best_state = math.inf, 0, None
    start_epoch, start_chunk, partial = 0, 0, (0.0, 0)
    initial = None
    if resume and resume.get("chosen") is not None:
        run.load(resume["run"])
        epochs_log = list(resume["epochs_log"])
        best_loss, best_epoch, best_state = resume["best_loss"], resume["best_epoch"], resume["best_state"]
        start_epoch, start_chunk, partial = resume["epoch_index"], resume["chunk"], tuple(resume["partial"])
        initial = resume["initial_val_loss"]
    else:
        initial = run.val_loss()

    def snapshot(epoch_index: int, chunk: int, part: tuple[float, int]) -> dict[str, Any]:
        return {
            "candidates": list(candidates),
            "chosen": chosen,
            "run": run.state(),
            "epochs_log": list(epochs_log),
            "best_loss": best_loss,
            "best_epoch": best_epoch,
            "best_state": best_state,
            "epoch_index": epoch_index,
            "chunk": chunk,
            "partial": part,
            "initial_val_loss": initial,
        }

    for epoch_index in range(start_epoch, cfg["epochs"]):
        train_loss = run.epoch(
            chosen,
            epoch_index,
            start_chunk if epoch_index == start_epoch else 0,
            partial if epoch_index == start_epoch else (0.0, 0),
            on_step=lambda chunk, tot, cnt, e=epoch_index: hooks.on_step(lambda: snapshot(e, chunk, (tot, cnt))),
        )
        val_loss = run.val_loss()
        entry = {"epoch": epoch_index + 1, "train_loss": train_loss, "val_loss": val_loss}
        epochs_log.append(entry)
        if on_epoch:
            on_epoch(entry)
        if val_loss < best_loss:
            best_loss, best_epoch = val_loss, epoch_index + 1
            best_state = {k: v.detach().cpu().clone() for k, v in run.model.state_dict().items()}
        hooks.on_epoch(lambda e=epoch_index: snapshot(e + 1, 0, (0.0, 0)))
    assert best_state is not None
    run.model.load_state_dict(best_state)
    checkpoint = stamp(
        {
            "kind": "gns-checkpoint",
            "model_state": best_state,
            "config": {k: v for k, v in cfg.items() if k != "device"},
            "stats": stats,
            "epoch": best_epoch,
            "noise_scale": chosen,
            "selected_on": "validation",
            "n_particle_types": n_types,
            "frame_interval": dt,
            "seed": seed,
        },
        dataset_manifest,
    )
    log = stamp(
        {
            "noise_candidates": candidates,
            "chosen_noise_scale": chosen,
            "epochs": epochs_log,
            "best_epoch": best_epoch,
            "initial_val_loss": initial,
            "selection_split": "validation",
        },
        dataset_manifest,
    )
    if fixture:
        assert checkpoint["fixture"] is True
        assert log["fixture"] is True
    return TrainResult(checkpoint=checkpoint, log=log, model=run.model)


def load_model(checkpoint: Mapping[str, Any]) -> GnsStep:
    """Rebuild the `GnsStep` of a checkpoint (statistics included) on the CPU."""
    cfg = checkpoint["config"]
    model = GnsStep(
        connectivity_radius=cfg["connectivity_radius"],
        frame_interval=checkpoint["frame_interval"],
        n_particle_types=checkpoint["n_particle_types"],
        latent=cfg["latent"],
        steps=cfg["steps"],
    )
    model.load_state_dict(copy.deepcopy(dict(checkpoint["model_state"])))
    return model.eval()
