"""T-012-016 - FR-012-22, FR-012-23, NFR-012-03: TSTR and TRTR arms with identical budgets; U-Net inference guards.

Oracles (independent of the code under test):
- hand calculation of the arm contract (FR-012-22): one TSTR arm on synthetic training tiles and five TRTR arms, one
  per fold, whose configurations are equal field by field except the fields that name the arm and its data;
  optimiser "AdamW", 8 dihedral maps plus colour jitter, the same step count and seed in every arm; steps per epoch
  = training tiles / batch size, hand-calculated (5,000 / 8 = 625; 768 / 8 = 96);
- NFR-012-03 thresholds: resume segment <= 8 h = 28,800 s; at least one checkpoint per epoch;
- hand-built hostile tensors for FR-012-23 (wrong dtype, wrong shape, wrong channel count, NaN, +-Inf): each raises
  ValueError before the model runs (a stub model records its calls); softmax of zero logits = 1/3 per class.
The watershed half of FR-012-23 (H x W x 3 uint8, H, W >= 16) is tested with the watershed in T-012-031.
No GPU and no real model are used.

Expected public API

module `pitstudio_pipeline.fragmentation.training`:
    ARM_SPECIFIC_KEYS = frozenset({"arm", "fold", "train_data", "validation_data", "steps_per_epoch",
                                   "checkpoint_every_steps"})
    build_arm_configs(*, steps: int, seed: int, batch_size: int, train_tiles: Mapping[str, int]) -> list[dict]
        train_tiles has the keys "tstr", "trtr-0", ..., "trtr-4" (training tiles of each arm). Returns six dicts,
        in the order tstr, trtr-0 ... trtr-4, with at least the keys
        arm ("tstr" | "trtr"), fold (None | 0..4), train_data ("synthetic/train" | "real/fold-<f>/train"),
        validation_data ("synthetic/validation" | "real/fold-<f>/validation"; model selection uses only this),
        steps_per_epoch (= ceil(train_tiles / batch_size)), checkpoint_every_steps (1 .. steps_per_epoch),
        architecture ("Unet"), encoder ("resnet18.a1_in1k"), classes (3), optimizer ("AdamW"), lr_schedule,
        steps, batch_size, augmentation ({"dihedral_maps": 8, "colour_jitter": <non-empty>}), seed,
        max_segment_seconds (<= 28,800).
        Every key outside ARM_SPECIFIC_KEYS has the same value in all six dicts.

module `pitstudio_pipeline.fragmentation.unet`:
    infer(model: torch.nn.Module, x: torch.Tensor) -> torch.Tensor
        Raises ValueError (and never calls the model) unless x is a float32 tensor of shape [N, 3, 512, 512],
        with only finite values. Otherwise returns softmax(model(x), dim=1), float32 [N, 3, 512, 512].
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.fragmentation import training, unet  # noqa: E402

STEPS, SEED, BATCH = 20000, 20261004, 8
TILES = {"tstr": 5000, **{f"trtr-{f}": 768 for f in range(5)}}  # 768 = 192 originals x 4 dihedral files
SHARED_REQUIRED = {
    "architecture": "Unet",
    "encoder": "resnet18.a1_in1k",
    "classes": 3,
    "optimizer": "AdamW",
    "steps": STEPS,
    "batch_size": BATCH,
    "seed": SEED,
}
SEGMENT_MAX_S = 8 * 3600  # NFR-012-03


def _configs() -> list[dict]:
    return training.build_arm_configs(steps=STEPS, seed=SEED, batch_size=BATCH, train_tiles=TILES)


# ---------------------------------------------------------------- FR-012-22 identical budgets


@pytest.mark.req("FR-012-22")
def test_one_tstr_arm_and_one_trtr_arm_per_fold() -> None:
    cfgs = _configs()
    assert [(c["arm"], c["fold"]) for c in cfgs] == [("tstr", None)] + [("trtr", f) for f in range(5)]


@pytest.mark.req("FR-012-22")
def test_arm_specific_keys_are_exactly_the_data_and_epoch_fields() -> None:
    assert frozenset(training.ARM_SPECIFIC_KEYS) == frozenset(
        {"arm", "fold", "train_data", "validation_data", "steps_per_epoch", "checkpoint_every_steps"}
    )


@pytest.mark.req("FR-012-22")
def test_every_shared_field_is_identical_across_the_six_arms() -> None:
    cfgs = _configs()
    keys = set(cfgs[0])
    assert all(set(c) == keys for c in cfgs), "same configuration fields in every arm"
    shared = keys - set(training.ARM_SPECIFIC_KEYS)
    assert set(SHARED_REQUIRED) | {"lr_schedule", "augmentation", "max_segment_seconds"} <= shared
    for c in cfgs[1:]:
        for k in sorted(shared):
            assert c[k] == cfgs[0][k], k


@pytest.mark.req("FR-012-22")
def test_architecture_optimiser_steps_seed_and_augmentation_are_the_pinned_values() -> None:
    for c in _configs():
        for k, v in SHARED_REQUIRED.items():
            assert c[k] == v, k
        assert c["augmentation"]["dihedral_maps"] == 8
        assert c["augmentation"]["colour_jitter"]
        assert c["lr_schedule"]


@pytest.mark.req("FR-012-22")
def test_each_arm_trains_and_selects_on_its_own_data_only() -> None:
    tstr, *trtr = _configs()
    assert tstr["train_data"] == "synthetic/train"
    assert tstr["validation_data"] == "synthetic/validation"
    for f, c in enumerate(trtr):
        assert c["train_data"] == f"real/fold-{f}/train"
        assert c["validation_data"] == f"real/fold-{f}/validation"
    assert "real" not in tstr["train_data"]
    assert "real" not in tstr["validation_data"]


@pytest.mark.req("FR-012-22")
def test_changing_the_budget_changes_it_for_every_arm_at_once() -> None:
    a = training.build_arm_configs(steps=STEPS, seed=SEED, batch_size=BATCH, train_tiles=TILES)
    b = training.build_arm_configs(steps=2 * STEPS, seed=SEED + 1, batch_size=BATCH, train_tiles=TILES)
    assert {c["steps"] for c in b} == {2 * STEPS}
    assert {c["seed"] for c in b} == {SEED + 1}
    assert [c["train_data"] for c in a] == [c["train_data"] for c in b]


# ---------------------------------------------------------------- NFR-012-03 resume segments and checkpoints


@pytest.mark.req("NFR-012-03")
def test_steps_per_epoch_follow_the_training_tiles() -> None:
    cfgs = _configs()
    assert cfgs[0]["steps_per_epoch"] == 5000 // 8 == 625
    assert all(c["steps_per_epoch"] == 768 // 8 == 96 for c in cfgs[1:])
    odd = training.build_arm_configs(steps=STEPS, seed=SEED, batch_size=BATCH, train_tiles={**TILES, "tstr": 5001})
    assert odd[0]["steps_per_epoch"] == math.ceil(5001 / 8) == 626


@pytest.mark.req("NFR-012-03")
def test_at_least_one_checkpoint_per_epoch_and_segments_within_8_hours() -> None:
    for c in _configs():
        assert 1 <= c["checkpoint_every_steps"] <= c["steps_per_epoch"]
        assert 0 < c["max_segment_seconds"] <= SEGMENT_MAX_S


# ---------------------------------------------------------------- FR-012-23 U-Net inference guards (hostile)


def _stub_model():
    """A torch module standing in for the U-Net: records calls and returns zero logits of the input's batch size."""
    import torch

    class _Stub(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def forward(self, x):
            self.calls += 1
            return torch.zeros(x.shape[0], 3, 512, 512, dtype=torch.float32)

    return _Stub()


def _hostile(case: str):
    import torch

    good = torch.zeros(1, 3, 512, 512, dtype=torch.float32)
    if case == "float64":
        return good.double()
    if case == "float16":
        return good.half()
    if case == "bfloat16":
        return good.bfloat16()
    if case == "int64":
        return good.long()
    if case == "uint8":
        return good.to(torch.uint8)
    if case == "no-batch-axis":
        return torch.zeros(3, 512, 512)
    if case == "one-channel":
        return torch.zeros(1, 1, 512, 512)
    if case == "four-channels":
        return torch.zeros(1, 4, 512, 512)
    if case == "256-tile":
        return torch.zeros(1, 3, 256, 256)
    if case == "511-wide":
        return torch.zeros(1, 3, 512, 511)
    if case == "channels-last-layout":
        return torch.zeros(1, 512, 512, 3)
    if case == "five-dims":
        return torch.zeros(1, 3, 512, 512, 1)
    x = good.clone()
    x[0, 1, 100, 200] = {"nan": math.nan, "pos-inf": math.inf, "neg-inf": -math.inf}[case]
    return x


HOSTILE = [
    "float64", "float16", "bfloat16", "int64", "uint8", "no-batch-axis", "one-channel", "four-channels",
    "256-tile", "511-wide", "channels-last-layout", "five-dims", "nan", "pos-inf", "neg-inf",
]  # fmt: skip


@pytest.mark.req("FR-012-23")
@pytest.mark.parametrize("case", HOSTILE)
def test_hostile_inference_input_raises_before_the_model_runs(case: str) -> None:
    model = _stub_model()
    with pytest.raises(ValueError):  # noqa: PT011 - FR-012-23 fixes the type, not the message
        unet.infer(model, _hostile(case))
    assert model.calls == 0, "no mask is produced for a rejected input"


@pytest.mark.req("FR-012-23")
def test_valid_input_runs_the_model_once_and_returns_class_probabilities() -> None:
    import torch

    model = _stub_model()
    out = unet.infer(model, torch.zeros(2, 3, 512, 512, dtype=torch.float32))
    assert model.calls == 1
    assert out.dtype == torch.float32
    assert tuple(out.shape) == (2, 3, 512, 512)
    torch.testing.assert_close(out, torch.full((2, 3, 512, 512), 1 / 3), rtol=0, atol=1e-6)
