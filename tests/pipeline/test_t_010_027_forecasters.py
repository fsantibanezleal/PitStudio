"""T-010-027: the TCN, PatchTST and Chronos-Bolt arms: inputs, outputs, splits, pinball loss.

Requirement: FR-010-21.
Spec: specs/010-slope/spec.md section 3.3 (FR-010-21), DC-010-05 (the forecaster IO description of spec 011:
`specs/011-surrogates/contracts/examples/surrogate-io.valid-forecaster.json`: input `context` float32 [1, 2, 128],
output
`quantiles` float32 [1, 9, 64]); plan.md row FR-010-21 ("contract checks (split membership by seed, input and output
shapes from
DC-010-05); pinball loss by hand on two values") and the dependency note (Chronos-Bolt arms reported "not run" when
`chronos-forecasting` does not resolve). Runs in the `pipeline/` environment (PyTorch); the context and the forecast
loop are
tested without PyTorch in tests/unit/test_t_010_027_context_forecast.py.

Expected API (package `pitstudio_pipeline.slope`):
- `models.build_model(arm, *, seed=0) -> torch.nn.Module` for arm "tcn" (stacked dilated causal 1-D convolutions with
  residual
  blocks) or "patchtst" (a Transformer over patches of 16 with stride 8, channel-independent): `forward(context)` maps
  float32
  (B, 2, 128) to float32 (B, 9, 64) (quantile axis 1), in the units of the scaled context. `PatchTST` instances expose
  `patch_length == 16`, `stride == 8` and `n_patches == 15`. Each model has fewer than 900,000 parameters (the ONNX
  file stays
  below 4 x 10^6 bytes in fp32, NFR-010-04). The same seed gives identical weights; another seed differs. ValueError
  for an
  unknown arm.
- `train.QUANTILES` = (0.1, 0.2, ..., 0.9); `train.pinball_loss(pred, target, quantiles=QUANTILES) -> torch scalar`:
  the mean over
  batch, quantile and step of max(tau (y - q), (tau - 1) (y - q)); pred (B, 9, 64), target (B, 64).
- `train.check_split_membership(events, config) -> None`: `events` = {"train": [...], "validation": [...], "test":
  [...]} of documents with
  `seed` and `event_id`; `config` = the `splits` mapping of the recipe (train {start, count}, validation {start,
  count}, test
  {start, count_per_stratum}); raises `SplitLeakError(ValueError)` (attribute `event_id`) for an event whose seed lies
  outside
  the range of the split it is listed in, or that is listed in two splits.
- `train.select_hyperparameters(candidates, *, fit, score, train, validation) -> Selection(best, scores)`: for each
  candidate
  `model = fit(candidate, train)` then `score(model, validation)` (lower is better); `fit` only ever receives the
  training events
  and `score` only the validation events; the first minimum wins ties.
- `train.train_arm(arm, contexts, targets, *, config, seed, device="cpu") -> TrainResult` with `.model`, `.history`
  (the training
  pinball loss per epoch) and `.manifest` ({"arm", "seed", "device", "epochs", "gpu_hours": record of tests/unit
  budget helper
  shape with 0.0 on the CPU}); `contexts` float32 (N, 2, 128), `targets` float32 (N, 64) in scaled units; config
  {"epochs", "batch_size", "learning_rate"}. Training on the CPU records that.
- `chronos` (module): constants MODEL_ID "amazon/chronos-bolt-tiny", CONTEXT_LENGTH 128, PREDICTION_LENGTH 64,
  QUANTILES (0.1 ..
  0.9), ARMS ("zero-shot", "fine-tuned"); `availability() -> {"available": bool, "reason": str | None}` (False with a
  reason
  when `chronos-forecasting` does not resolve); `build_arm(mode, *, weights_dir=None)` raises `ChronosUnavailableError`
  (ValueError subclass with the reason) when it is not available and ValueError for an unknown mode;
  `not_run_reason(mode,
  availability)` the sentence stored in the acceptance row ("chronos-bolt zero-shot not run: <reason>").

Oracles: shapes and sizes from DC-010-05 and the spec text; the pinball loss by hand (y = 1: q = (0.5, 1.5, 2.5) at
tau =
(0.1, 0.5, 0.9) gives (0.05 + 0.25 + 0.15) / 3 = 0.15) and the kit `pinball`; planted split leaks; spies on the
selection callbacks;
a learnable target (a constant median of 1, the scale of a mean-|y|-normalised context) for the loss decrease.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

import _slope_ttf_ref as k  # noqa: E402
from pitstudio_pipeline.slope import chronos, models, train  # noqa: E402

torch = pytest.importorskip(
    "torch"
)  # the pipeline environment owns PyTorch (FR-000-17); first-party imports come first

QS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
SPLITS = {
    "train": {"start": 0, "count": 20000},
    "validation": {"start": 20000, "count": 1000},
    "test": {"start": 21000, "count_per_stratum": 500},
}


@pytest.mark.req("FR-010-21")
@pytest.mark.parametrize("arm", ["tcn", "patchtst"])
def test_the_models_map_a_2_by_128_context_to_9_quantiles_of_64_steps(arm) -> None:
    m = models.build_model(arm, seed=1).eval()
    x = torch.randn(3, 2, 128)
    with torch.no_grad():
        y = m(x)
    assert y.shape == (3, 9, 64)
    assert y.dtype == torch.float32
    assert torch.isfinite(y).all()
    with torch.no_grad():  # batch independence
        assert torch.allclose(m(x[:1]), y[:1], atol=1e-5)
    assert sum(p.numel() for p in m.parameters()) < 900_000


@pytest.mark.req("FR-010-21")
def test_patchtst_uses_patches_of_16_with_stride_8() -> None:
    m = models.build_model("patchtst")
    assert (m.patch_length, m.stride, m.n_patches) == (16, 8, 15)  # (128 - 16) / 8 + 1


@pytest.mark.req("FR-010-21")
@pytest.mark.parametrize("arm", ["tcn", "patchtst"])
def test_the_same_seed_gives_the_same_weights_and_another_seed_differs(arm) -> None:
    a, b, c = models.build_model(arm, seed=5), models.build_model(arm, seed=5), models.build_model(arm, seed=6)
    pa, pb, pc = (torch.cat([p.detach().flatten() for p in m.parameters()]) for m in (a, b, c))
    assert torch.equal(pa, pb)
    assert not torch.equal(pa, pc)


@pytest.mark.req("FR-010-21")
def test_an_unknown_arm_is_rejected() -> None:
    for bad in ("lstm", "", "TCN", "chronos"):
        with pytest.raises(ValueError, match=r"."):
            models.build_model(bad)


@pytest.mark.req("FR-010-21")
def test_the_pinball_loss_by_hand_on_two_values_and_against_the_kit() -> None:
    pred = torch.tensor([[[0.5], [1.5], [2.5]]])  # (B = 1, 3 quantiles, 1 step)
    target = torch.tensor([[1.0]])
    loss = train.pinball_loss(pred, target, (0.1, 0.5, 0.9))
    # y - q = (0.5, -0.5, -1.5): losses (0.1 x 0.5, 0.5 x 0.5, 0.1 x 1.5) = (0.05, 0.25, 0.15), mean 0.15
    assert float(loss) == pytest.approx(0.15, rel=1e-6)
    two = train.pinball_loss(torch.tensor([[[2.0], [2.0], [2.0]]]), torch.tensor([[1.0]]), (0.1, 0.5, 0.9))
    # y - q = -1 for every quantile: (0.9, 0.5, 0.1) -> mean 0.5
    assert float(two) == pytest.approx(0.5, rel=1e-6)
    rng = np.random.default_rng(1)
    p, t = rng.normal(size=(4, 9, 64)), rng.normal(size=(4, 64))
    assert float(train.pinball_loss(torch.tensor(p), torch.tensor(t))) == pytest.approx(
        k.pinball(t, np.transpose(p, (0, 2, 1)), QS), rel=1e-6
    )
    assert train.QUANTILES == QS


@pytest.mark.req("FR-010-21")
def test_the_pinball_loss_is_zero_at_the_target_and_has_the_gradient_of_the_quantile_loss() -> None:
    pred = torch.full((1, 9, 4), 2.0, requires_grad=True)
    target = torch.full((1, 4), 2.0)
    assert float(train.pinball_loss(pred, target)) == 0.0
    pred2 = torch.full((1, 9, 4), 3.0, requires_grad=True)  # y - q = -1 < 0: d loss / d q = (1 - tau) / (9 x 4)
    train.pinball_loss(pred2, target).backward()
    expected = (1.0 - torch.tensor(QS)).reshape(1, 9, 1).expand(1, 9, 4) / (9 * 4)
    assert torch.allclose(pred2.grad, expected, atol=1e-7)


def _events(split: str, seeds, prefix="e"):
    return [{"seed": s, "event_id": f"{prefix}-{s:06d}", "split": split} for s in seeds]


@pytest.mark.req("FR-010-21")
def test_split_membership_accepts_events_inside_their_seed_ranges() -> None:
    ev = {
        "train": _events("train", [0, 19999, 100]),
        "validation": _events("validation", [20000, 20999]),
        "test": _events("test", [21000, 21499, 22000, 22999]),  # 4 strata x 500: 21000 .. 22999
    }
    train.check_split_membership(ev, SPLITS)


@pytest.mark.req("FR-010-21")
@pytest.mark.parametrize(
    ("split", "seed"),
    [("train", 20000), ("train", -1), ("validation", 19999), ("validation", 21000), ("test", 20999), ("test", 23000)],
)
def test_an_event_outside_its_split_range_is_a_leak(split, seed) -> None:
    ev = {"train": [], "validation": [], "test": []}
    ev[split] = _events(split, [seed], "bad")
    with pytest.raises(train.SplitLeakError) as exc:
        train.check_split_membership(ev, SPLITS)
    assert exc.value.event_id == f"bad-{seed:06d}"


@pytest.mark.req("FR-010-21")
def test_an_event_listed_in_two_splits_is_a_leak() -> None:
    shared = _events("train", [5])[0]
    with pytest.raises(train.SplitLeakError):
        train.check_split_membership({"train": [shared], "validation": [], "test": [shared]}, SPLITS)


@pytest.mark.req("FR-010-21")
def test_hyperparameters_are_chosen_on_the_validation_split_only() -> None:
    train_events, val_events = _events("train", range(10)), _events("validation", range(20000, 20005))
    seen_fit, seen_score = [], []

    def fit(candidate, events):
        seen_fit.append(events)
        return {"c": candidate}

    def score(model, events):
        seen_score.append(events)
        return abs(model["c"] - 3)  # the best candidate is 3

    sel = train.select_hyperparameters([1, 3, 5, 3], fit=fit, score=score, train=train_events, validation=val_events)
    assert sel.best == 3
    assert list(sel.scores) == [2, 0, 2, 0]
    assert all(e is train_events for e in seen_fit)
    assert all(e is val_events for e in seen_score)
    assert len(seen_fit) == len(seen_score) == 4


@pytest.mark.req("FR-010-21")
@pytest.mark.parametrize("arm", ["tcn", "patchtst"])
def test_training_on_a_learnable_target_lowers_the_pinball_loss_and_records_the_cpu(arm) -> None:
    rng = np.random.default_rng(3)
    n = 192
    ctx = rng.normal(size=(n, 2, 128)).astype(np.float32)
    ctx[:, 1] = 1.0
    target = np.repeat(ctx[:, :1, -1], 64, axis=1).astype(np.float32)  # the median equals the last context value
    res = train.train_arm(
        arm, ctx, target, config={"epochs": 8, "batch_size": 32, "learning_rate": 1e-2}, seed=2, device="cpu"
    )
    assert len(res.history) == 8
    assert res.history[-1] < 0.8 * res.history[0]
    assert res.manifest["arm"] == arm
    assert res.manifest["device"] == "cpu"
    assert res.manifest["gpu_hours"]["gpu_hours"] == 0.0
    assert res.manifest["epochs"] == 8
    again = train.train_arm(
        arm, ctx, target, config={"epochs": 8, "batch_size": 32, "learning_rate": 1e-2}, seed=2, device="cpu"
    )
    assert again.history == pytest.approx(res.history, rel=1e-5)  # seeded


# ---------------------------------------------------------------------------------------------------------------------
# Chronos-Bolt


@pytest.mark.req("FR-010-21")
def test_the_chronos_bolt_configuration_constants_follow_the_spec() -> None:
    assert chronos.MODEL_ID == "amazon/chronos-bolt-tiny"
    assert (chronos.CONTEXT_LENGTH, chronos.PREDICTION_LENGTH) == (128, 64)
    assert tuple(chronos.QUANTILES) == pytest.approx(QS)
    assert tuple(chronos.ARMS) == ("zero-shot", "fine-tuned")


@pytest.mark.req("FR-010-21")
def test_when_chronos_forecasting_is_missing_the_arms_are_reported_not_run_with_the_reason() -> None:
    av = chronos.availability()
    assert isinstance(av["available"], bool)
    if av["available"]:
        assert av["reason"] is None
        return
    assert av["reason"]
    for mode in chronos.ARMS:
        with pytest.raises(chronos.ChronosUnavailableError) as exc:
            chronos.build_arm(mode)
        assert av["reason"] in str(exc.value)
        assert isinstance(exc.value, ValueError)
        sentence = chronos.not_run_reason(mode, av)
        assert sentence.startswith(f"chronos-bolt {mode} not run: ")
        assert av["reason"] in sentence


@pytest.mark.req("FR-010-21")
def test_an_unknown_chronos_mode_is_rejected() -> None:
    for bad in ("few-shot", "", "zero_shot"):
        with pytest.raises(ValueError, match=r"."):
            chronos.build_arm(bad)
