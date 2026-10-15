# ruff: noqa: E501
"""Shared fake training run of the spec 014 export-availability tests (T-014-092, T-014-093; pipeline environment).

This module holds no test. It is imported by `tests/pipeline/test_t_014_092_*.py` and `tests/unit/test_t_014_093_input_stale.py` and is locked with the first of
them. It writes a fake training run on disk (a torch checkpoint with an rsl_rl-style actor, an observation file of goldens and a valid policy handoff) with
torch, numpy, hashlib and json only; nothing here calls the code under test. The layout is the one documented in tests/pipeline/test_t_014_041_policy_export.py.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "014-robot-learning" / "contracts" / "examples"


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_run(tmp_path: Path, *, n_golden: int = 256, seed: int = 0):
    """Write a fake IL-1 run under tmp_path / "run"; return (handoff dict, run root)."""
    import torch

    base = json.loads((EX / "il-policy-handoff.valid.json").read_text("utf-8"))
    n_obs, n_act = 63, 2
    g = torch.Generator().manual_seed(seed)
    layers = {}
    sizes = [n_obs, 256, 256, n_act]
    for i, (a, b) in enumerate(itertools.pairwise(sizes)):
        layers[f"actor.{2 * i}.weight"] = torch.randn(b, a, generator=g) * (1.0 / math.sqrt(a))
        layers[f"actor.{2 * i}.bias"] = torch.randn(b, generator=g) * 0.1
    root = tmp_path / "run"
    (root / "checkpoints").mkdir(parents=True)
    (root / "goldens").mkdir()
    ckpt = root / "checkpoints" / "model_1500.pt"
    torch.save({"model_state_dict": layers, "iter": 1500}, ckpt)
    rng = np.random.default_rng(seed + 1)
    mean = rng.normal(0.0, 1.0, n_obs)
    var = rng.uniform(0.5, 4.0, n_obs)
    obs = (mean + rng.normal(0.0, 1.0, (n_golden, n_obs)) * np.sqrt(var)).astype(np.float32)
    npz = root / "goldens" / "observations.npz"
    np.savez(npz, observations=obs)
    handoff = copy.deepcopy(base)
    handoff["checkpoint"] = {
        "id": "ckpt-1500",
        "path": "checkpoints/model_1500.pt",
        "sha256": sha(ckpt),
        "iteration": 1500,
    }
    handoff["normaliser"] = {"mean": mean.tolist(), "var": var.tolist()}
    handoff["actor"] = {"hidden_units": [256, 256], "activation": "elu"}
    handoff["goldens"] = {"path": "goldens/observations.npz", "sha256": sha(npz), "count": n_golden}
    return handoff, root


def out_files(out: Path) -> list[Path]:
    return sorted(out.rglob("*")) if out.exists() else []
