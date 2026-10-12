"""FNO training (s30_train for the tailings and dust models; FR-011-33, FR-011-44, FR-011-49).

`train_fno(splits, config, seed=...)` trains a direct map on `splits.samples("train")` and chooses the checkpoint epoch
on
`splits.samples("val")` only (the test split is never read). A sample is (x, y): the model input [C_in, 64, 64] already
built by
`inputs.build_fno_input` (normalised) and the solver output [C_out, 64, 64] in physical units. The network works in
standardised output
units (per-channel mean and standard deviation of the training targets) and the exported graph returns physical units
(the statistics
are stored in the model). The loss is the mean squared error of the standardised outputs; the selection metric is the
mean relative L2
of the validation scenarios. The same `TrainHooks` of the GNS job make the run resumable (epoch granularity).
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch

from pitstudio_pipeline.surrogates.errors import DatasetError
from pitstudio_pipeline.surrogates.fixture import is_fixture, stamp
from pitstudio_pipeline.surrogates.fno.evaluate import relative_l2
from pitstudio_pipeline.surrogates.fno.model import FnoModel
from pitstudio_pipeline.surrogates.gns.train import TrainHooks

STD_FLOOR = 1e-8


@dataclass
class FnoTrainResult:
    checkpoint: dict[str, Any]
    log: dict[str, Any]
    model: FnoModel | None = None


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    cfg = dict(config)
    for key, minimum in (("epochs", 1), ("batch_size", 1), ("width", 1), ("layers", 1)):
        value = cfg.get(key, {"width": 32, "layers": 4}.get(key))
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise ValueError(f"{key} must be an integer >= {minimum}, got {value!r}")
        cfg[key] = value
    lr = cfg.get("lr")
    if not isinstance(lr, int | float) or isinstance(lr, bool) or not math.isfinite(lr) or lr <= 0:
        raise ValueError(f"lr must be a positive finite number, got {lr!r}")
    for key in ("in_channels", "out_channels"):
        if not isinstance(cfg.get(key), int) or cfg[key] < 1:
            raise ValueError(f"{key} must be a positive integer, got {cfg.get(key)!r}")
    cfg.setdefault("device", "cpu")
    cfg.setdefault("lr_final_ratio", 1.0)
    if not (isinstance(cfg["lr_final_ratio"], int | float) and 0 < cfg["lr_final_ratio"] <= 1):
        raise ValueError("lr_final_ratio must be in (0, 1]")
    return cfg


def _stack(samples: Sequence[tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    return np.stack([s[0] for s in samples]).astype(np.float32), np.stack([s[1] for s in samples]).astype(np.float32)


def target_stats(samples: Sequence[tuple[np.ndarray, np.ndarray]]) -> dict[str, list[float]]:
    """Per-channel mean and standard deviation of the training targets (the training split alone)."""
    y = np.stack([s[1] for s in samples]).astype(np.float64)
    mean = y.mean(axis=(0, 2, 3))
    std = np.maximum(y.std(axis=(0, 2, 3)), STD_FLOOR)
    return {"mean": [float(v) for v in mean], "std": [float(v) for v in std]}


def val_metric(model: FnoModel, x: np.ndarray, y: np.ndarray, device: torch.device, batch: int) -> float:
    """Mean over scenarios and channels of the relative L2 error (empty channels excluded)."""
    model.eval()
    errors = []
    with torch.no_grad():
        for lo in range(0, len(x), batch):
            pred = model(torch.from_numpy(x[lo : lo + batch]).to(device)).cpu().numpy()
            for s in range(pred.shape[0]):
                for c in range(pred.shape[1]):
                    truth = y[lo + s, c]
                    if np.linalg.norm(truth) >= 1e-9:
                        errors.append(relative_l2(pred[s, c], truth))
    return float(np.mean(errors)) if errors else math.inf


def train_fno(
    splits: Any,
    config: Mapping[str, Any],
    *,
    seed: int,
    dataset_manifest: Mapping[str, Any] | None = None,
    hooks: TrainHooks | None = None,
) -> FnoTrainResult:
    """Train, select on validation, return the checkpoint, the log and the model (see the module docstring)."""
    cfg = validate_config(config)
    fixture = is_fixture(dataset_manifest)
    train_samples, val_samples = splits.samples("train"), splits.samples("val")
    if len(train_samples) == 0 or len(val_samples) == 0:
        raise DatasetError("the training and validation splits must not be empty")
    xt, yt = _stack(train_samples)
    xv, yv = _stack(val_samples)
    if xt.shape[1] != cfg["in_channels"] or yt.shape[1] != cfg["out_channels"]:
        raise DatasetError("sample channels differ from in_channels / out_channels")
    stats = target_stats(train_samples)
    device = torch.device(cfg["device"])
    torch.manual_seed(seed)
    model = FnoModel(cfg["in_channels"], cfg["out_channels"], width=cfg["width"], layers=cfg["layers"])
    mean = torch.tensor(stats["mean"]).reshape(1, -1, 1, 1)
    std = torch.tensor(stats["std"]).reshape(1, -1, 1, 1)
    model.output_mean.copy_(mean)
    model.output_std.copy_(std)
    model.to(device)
    optimiser = torch.optim.Adam(model.parameters(), lr=cfg["lr"])
    steps_per_epoch = math.ceil(len(xt) / cfg["batch_size"])
    gamma = cfg["lr_final_ratio"] ** (1.0 / max(1, cfg["epochs"] * steps_per_epoch))
    scheduler = torch.optim.lr_scheduler.ExponentialLR(optimiser, gamma=gamma)
    hooks = hooks or TrainHooks()
    epochs_log: list[dict[str, Any]] = []
    best, best_epoch, best_state, start = math.inf, 0, None, 0
    initial = None
    resume = hooks.resume
    if resume:
        model.load_state_dict(resume["model"])
        optimiser.load_state_dict(resume["optimiser"])
        scheduler.load_state_dict(resume["scheduler"])
        epochs_log, best, best_epoch, best_state = (
            list(resume["epochs_log"]),
            resume["best"],
            resume["best_epoch"],
            resume["best_state"],
        )
        start, initial = resume["epoch_index"], resume["initial"]
    else:
        initial = val_metric(model, xv, yv, device, cfg["batch_size"])
    y_std = torch.from_numpy(np.asarray(stats["std"], dtype=np.float32)).reshape(1, -1, 1, 1).to(device)
    y_mean = torch.from_numpy(np.asarray(stats["mean"], dtype=np.float32)).reshape(1, -1, 1, 1).to(device)

    def snapshot(epoch_index: int) -> dict[str, Any]:
        return {
            "model": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
            "optimiser": optimiser.state_dict(),
            "scheduler": scheduler.state_dict(),
            "epochs_log": list(epochs_log),
            "best": best,
            "best_epoch": best_epoch,
            "best_state": best_state,
            "epoch_index": epoch_index,
            "initial": initial,
            "candidates": [],
            "chosen": 0.0,
        }

    for epoch_index in range(start, cfg["epochs"]):
        model.train()
        order = np.random.default_rng([seed + 1, epoch_index]).permutation(len(xt))
        total, count = 0.0, 0
        for lo in range(0, len(order), cfg["batch_size"]):
            idx = order[lo : lo + cfg["batch_size"]]
            x = torch.from_numpy(xt[idx]).to(device)
            y = torch.from_numpy(yt[idx]).to(device)
            optimiser.zero_grad(set_to_none=True)
            pred = model(x)
            loss = torch.mean(((pred - y_mean) / y_std - (y - y_mean) / y_std) ** 2)
            loss.backward()
            optimiser.step()
            scheduler.step()
            total += float(loss.detach()) * len(idx)
            count += len(idx)
            hooks.on_step(lambda e=epoch_index: snapshot(e))
        metric = val_metric(model, xv, yv, device, cfg["batch_size"])
        epochs_log.append({"epoch": epoch_index + 1, "train_loss": total / count, "val_rel_l2": metric})
        if metric < best:
            best, best_epoch = metric, epoch_index + 1
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        hooks.on_epoch(lambda e=epoch_index: snapshot(e + 1))
    assert best_state is not None
    model.load_state_dict(best_state)
    checkpoint = stamp(
        {
            "kind": "fno-checkpoint",
            "model_state": best_state,
            "config": {k: v for k, v in cfg.items() if k != "device"},
            "stats": stats,
            "epoch": best_epoch,
            "selected_on": "validation",
            "seed": seed,
        },
        dataset_manifest,
    )
    log = stamp(
        {
            "epochs": epochs_log,
            "best_epoch": best_epoch,
            "initial_val_rel_l2": initial,
            "selection_split": "validation",
        },
        dataset_manifest,
    )
    if fixture:
        assert checkpoint["fixture"] is True
    return FnoTrainResult(checkpoint=checkpoint, log=log, model=model)


def load_model(checkpoint: Mapping[str, Any]) -> FnoModel:
    cfg = checkpoint["config"]
    model = FnoModel(cfg["in_channels"], cfg["out_channels"], width=cfg["width"], layers=cfg["layers"])
    model.load_state_dict(copy.deepcopy(dict(checkpoint["model_state"])))
    return model.eval()
