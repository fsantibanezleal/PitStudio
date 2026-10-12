"""FNO training entry point on a synthetic smoothing task (not a locked test; CPU)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.errors import DatasetError  # noqa: E402
from pitstudio_pipeline.surrogates.fno import train  # noqa: E402
from pitstudio_pipeline.surrogates.gns.train import TrainHooks  # noqa: E402

CONFIG = {"epochs": 6, "batch_size": 4, "lr": 3e-3, "width": 8, "layers": 2, "in_channels": 2, "out_channels": 1}


def sample(seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    base = rng.normal(size=(64, 64))
    smooth = np.real(
        np.fft.ifft2(np.fft.fft2(base) * (np.add.outer(np.fft.fftfreq(64), np.fft.fftfreq(64)) ** 2 < 0.01))
    )
    x = np.stack([smooth, np.full((64, 64), rng.uniform())])
    y = (2.0 * smooth + 5.0)[None]
    return x.astype(np.float32), y.astype(np.float32)


class Splits:
    def __init__(self) -> None:
        self.reads: list[str] = []
        self.data = {"train": [sample(i) for i in range(12)], "val": [sample(100 + i) for i in range(4)]}

    def samples(self, name: str):
        self.reads.append(name)
        if name == "test":
            raise AssertionError("the test split was read")
        return self.data[name]


def test_training_learns_selects_on_validation_and_never_reads_test() -> None:
    splits = Splits()
    res = train.train_fno(splits, CONFIG, seed=0)
    assert set(splits.reads) <= {"train", "val"}
    assert res.checkpoint["selected_on"] == "validation"
    best = min(e["val_rel_l2"] for e in res.log["epochs"])
    assert res.log["best_epoch"] == min(res.log["epochs"], key=lambda e: e["val_rel_l2"])["epoch"]
    assert best < res.log["initial_val_rel_l2"]
    assert res.checkpoint.get("fixture", False) is False


def test_the_model_returns_physical_units_and_is_reproducible_by_seed() -> None:
    a = train.train_fno(Splits(), CONFIG, seed=1)
    b = train.train_fno(Splits(), CONFIG, seed=1)
    assert a.log == b.log
    x, y = Splits().data["val"][0]
    with torch.no_grad():
        out = train.load_model(a.checkpoint)(torch.from_numpy(x)[None]).numpy()[0, 0]
    assert abs(out.mean() - 5.0) < 1.0  # the output scale is physical (target mean 5)


def test_a_fixture_dataset_flags_the_checkpoint_and_a_bad_flag_stops_the_run() -> None:
    res = train.train_fno(Splits(), CONFIG, seed=0, dataset_manifest={"fixture": True})
    assert res.checkpoint["fixture"] is True
    assert res.log["fixture"] is True
    with pytest.raises(ValueError, match="fixture"):
        train.train_fno(Splits(), CONFIG, seed=0, dataset_manifest={"fixture": "yes"})


@pytest.mark.parametrize("change", [{"epochs": 0}, {"lr": 0.0}, {"batch_size": 0}, {"in_channels": 0}])
def test_invalid_configuration_is_refused(change: dict) -> None:
    with pytest.raises(ValueError, match=r"."):
        train.train_fno(Splits(), {**CONFIG, **change}, seed=0)


def test_empty_splits_are_refused() -> None:
    class Empty(Splits):
        def __init__(self) -> None:
            super().__init__()
            self.data["val"] = []

    with pytest.raises(DatasetError):
        train.train_fno(Empty(), CONFIG, seed=0)


def test_resume_from_an_epoch_snapshot_gives_the_same_log() -> None:
    straight = train.train_fno(Splits(), CONFIG, seed=2)
    saved: dict = {}

    class Stop(Exception):
        pass

    class H(TrainHooks):
        def on_epoch(self, snapshot) -> None:
            saved["state"] = snapshot()
            if saved["state"]["epoch_index"] == 3:
                raise Stop

    with pytest.raises(Stop):
        train.train_fno(Splits(), CONFIG, seed=2, hooks=H())

    class R(TrainHooks):
        resume = saved["state"]

    resumed = train.train_fno(Splits(), CONFIG, seed=2, hooks=R())
    for a, b in zip(straight.log["epochs"], resumed.log["epochs"], strict=True):
        assert a["val_rel_l2"] == pytest.approx(b["val_rel_l2"], rel=1e-5)
