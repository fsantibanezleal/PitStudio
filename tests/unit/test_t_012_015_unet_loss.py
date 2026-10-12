"""T-012-015 - FR-012-20, FR-012-21, P-012-16: U-Net architecture, pinned encoder, weight map and loss.

Oracles (independent of the code under test):
- published worked equation: Ronneberger, Fischer & Brox 2015, "U-Net", section 3, Eq. (2), p. 5
  (https://arxiv.org/abs/1505.04597): w(x) = w_c(x) + w0 * exp(-(d1(x) + d2(x))^2 / (2 sigma^2)), w0 = 10,
  sigma = 5 px (spec 012 section 7), hand-calculated below at chosen pixels of a three-square fixture with the
  Euclidean distances to the nearest and second-nearest instance written out;
- layer table of the U-Net from plan 012 (test strategy rows FR-012-20/21): encoder feature channels
  3/64/64/128/256/512 at strides 1/2/4/8/16/32 (timm `resnet18.a1_in1k`, model card
  https://huggingface.co/timm/resnet18.a1_in1k), decoder blocks 256/128/64/32/16 channels, 3 output classes;
- published ImageNet normalisation constants mean (0.485, 0.456, 0.406), std (0.229, 0.224, 0.225)
  (timm `IMAGENET_DEFAULT_MEAN` / `IMAGENET_DEFAULT_STD`);
- closed-form loss values: cross-entropy of uniform logits = ln 3; soft Dice of a uniform foreground probability
  2/3 against an all-foreground target = 2 (2/3) / (2/3 + 1) = 0.8, against an all-background target = 0.
No GPU is used: the model is built on the CPU with encoder_weights=None (no download).

Expected public API

module `pitstudio_pipeline.fragmentation.unet`:
    ENCODER_NAME = "resnet18.a1_in1k"
    IMAGENET_MEAN = (0.485, 0.456, 0.406); IMAGENET_STD = (0.229, 0.224, 0.225)
    BACKEND: str, "smp" when segmentation_models_pytorch imports, otherwise "vendored" (FR-012-21)
    build_unet(encoder_weights: str | None = "imagenet") -> torch.nn.Module
        smp backend: segmentation_models_pytorch.Unet("tu-resnet18.a1_in1k", encoder_weights=..., classes=3).
        Both backends create the encoder through `timm.create_model("resnet18.a1_in1k", ..., pretrained=<bool>)`,
        expose `model.encoder(x) -> list[Tensor]` (6 feature maps, the input first) and `model.decoder.blocks`
        (5 blocks), and map float32 [N, 3, 512, 512] to logits [N, 3, 512, 512].
    normalise(image: np.ndarray) -> torch.Tensor
        (H, W, 3) uint8 RGB -> float32 [3, H, W] = (image / 255 - mean) / std per channel.

module `pitstudio_pipeline.fragmentation.loss`:
    W0 = 10.0; SIGMA_PX = 5.0
    class_weight_map(label: np.ndarray) -> np.ndarray
        (H, W) float64 w_c: inverse frequency of the three FR-012-18 classes of the tile, normalised to mean 1.
    weight_map(label: np.ndarray, *, w0: float = W0, sigma: float = SIGMA_PX) -> np.ndarray
        (H, W) float64 w = w_c + w0 exp(-(d1 + d2)^2 / (2 sigma^2)); d_i = Euclidean distance (pixel centres) to
        the i-th nearest instance, 0 inside that instance; border term 0 when the tile has fewer than 2 instances.
    unet_loss(logits: Tensor[N, 3, H, W], target: Tensor[N, H, W] int64, weight: Tensor[N, H, W]) -> Tensor[]
        pixel-weighted cross-entropy + (1 - soft Dice) on the foreground probability p1 + p2 = 1 - p0.
"""

from __future__ import annotations

import importlib
import math
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.fragmentation import loss, unet  # noqa: E402

EXAMPLES = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "property_tests"
]["ci_examples_per_test"]
ATOL = 1e-12  # P-012-16; float64 sqrt / exp of exact integer squared distances
W0, SIGMA = 10.0, 5.0  # Ronneberger et al. 2015, section 3, p. 5

ENCODER_CHANNELS = [3, 64, 64, 128, 256, 512]  # plan 012, FR-012-21 layer table (input + 5 stages)
ENCODER_STRIDES = [1, 2, 4, 8, 16, 32]
DECODER_CHANNELS = [256, 128, 64, 32, 16]
DECODER_SIZES = [32, 64, 128, 256, 512]


def _dihedral(a: np.ndarray) -> list[np.ndarray]:
    return [np.rot90(a, k) for k in range(4)] + [np.rot90(np.fliplr(a), k) for k in range(4)]


def _ref_encode(label: np.ndarray) -> np.ndarray:
    h, w = label.shape
    p = np.pad(label, 1, constant_values=0)
    differs = np.zeros((h, w), dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                differs |= p[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w] != label
    return np.where(label == 0, 0, np.where(differs, 2, 1))


def _border(d1: float, d2: float) -> float:
    return W0 * math.exp(-((d1 + d2) ** 2) / (2 * SIGMA**2))


# ---------------------------------------------------------------- FR-012-20 pinned encoder and layout


def _layer_table(model) -> tuple[list[tuple[int, int]], list[tuple[int, int]], tuple[int, ...]]:
    import torch

    seen: list[tuple[int, int]] = []
    hooks = [
        b.register_forward_hook(lambda m, i, o: seen.append((o.shape[1], o.shape[-1]))) for b in model.decoder.blocks
    ]
    model.eval()
    with torch.no_grad():
        x = torch.zeros(2, 3, 512, 512, dtype=torch.float32)
        feats = model.encoder(x)
        y = model(x)
    for h in hooks:
        h.remove()
    enc = [(f.shape[1], 512 // f.shape[-1]) for f in feats]
    return enc, seen, (tuple(y.shape), y.dtype)


@pytest.mark.req("FR-012-20")
def test_pinned_encoder_name_and_imagenet_normalisation_constants() -> None:
    assert unet.ENCODER_NAME == "resnet18.a1_in1k"
    assert tuple(unet.IMAGENET_MEAN) == (0.485, 0.456, 0.406)
    assert tuple(unet.IMAGENET_STD) == (0.229, 0.224, 0.225)


@pytest.mark.req("FR-012-20")
def test_default_encoder_weights_are_imagenet() -> None:
    import inspect

    assert inspect.signature(unet.build_unet).parameters["encoder_weights"].default == "imagenet"


@pytest.mark.req("FR-012-20")
def test_normalise_scales_to_unit_range_then_applies_imagenet_mean_and_std() -> None:
    img = np.zeros((2, 3, 3), dtype=np.uint8)
    img[0, 0] = (255, 0, 128)
    img[1, 2] = (10, 200, 255)
    t = unet.normalise(img)
    import torch

    assert t.dtype == torch.float32
    assert tuple(t.shape) == (3, 2, 3)
    mean, std = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)
    for (r, c), rgb in (((0, 0), (255, 0, 128)), ((1, 2), (10, 200, 255)), ((0, 1), (0, 0, 0))):
        expected = [(v / 255 - m) / s for v, m, s in zip(rgb, mean, std, strict=True)]
        np.testing.assert_allclose(t[:, r, c].numpy(), expected, rtol=1e-6, atol=1e-6)


@pytest.mark.req("FR-012-20")
def test_unet_builds_on_cpu_with_the_pinned_timm_encoder_and_the_layer_table(monkeypatch) -> None:
    import timm
    import torch

    calls: list[tuple[tuple, dict]] = []
    real = timm.create_model

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(timm, "create_model", spy)
    torch.manual_seed(0)
    model = unet.build_unet(encoder_weights=None)
    names = [a[0] if a else k.get("model_name") for a, k in calls]
    assert "resnet18.a1_in1k" in names
    assert all(k.get("pretrained", False) is False for _, k in calls), "encoder_weights=None must not download"
    enc, dec, (shape, dtype) = _layer_table(model)
    assert [c for c, _ in enc] == ENCODER_CHANNELS
    assert [s for _, s in enc] == ENCODER_STRIDES
    assert dec == list(zip(DECODER_CHANNELS, DECODER_SIZES, strict=True))
    assert shape == (2, 3, 512, 512)
    assert dtype == torch.float32


# ---------------------------------------------------------------- FR-012-21 vendored fallback


@pytest.mark.req("FR-012-21")
def test_backend_is_smp_when_segmentation_models_pytorch_imports() -> None:
    try:
        import segmentation_models_pytorch as smp
    except ImportError:
        assert unet.BACKEND == "vendored"
        return
    assert unet.BACKEND == "smp"
    assert isinstance(unet.build_unet(encoder_weights=None), smp.Unet)


@pytest.mark.req("FR-012-21")
def test_without_smp_the_vendored_unet_has_the_same_layer_table(monkeypatch) -> None:
    import pitstudio_pipeline.fragmentation as frag
    import torch

    monkeypatch.setattr(frag, "unet", unet)  # restores the package attribute on teardown
    monkeypatch.setitem(sys.modules, "segmentation_models_pytorch", None)  # import now raises ImportError
    monkeypatch.delitem(sys.modules, "pitstudio_pipeline.fragmentation.unet")
    fresh = importlib.import_module("pitstudio_pipeline.fragmentation.unet")
    assert fresh.BACKEND == "vendored"
    assert fresh.ENCODER_NAME == "resnet18.a1_in1k"
    torch.manual_seed(0)
    enc, dec, (shape, dtype) = _layer_table(fresh.build_unet(encoder_weights=None))
    assert [c for c, _ in enc] == ENCODER_CHANNELS
    assert [s for _, s in enc] == ENCODER_STRIDES
    assert dec == list(zip(DECODER_CHANNELS, DECODER_SIZES, strict=True))
    assert shape == (2, 3, 512, 512)
    assert dtype == torch.float32


# ---------------------------------------------------------------- FR-012-20 weight map (Ronneberger Eq. 2)

# 25 x 25 tile: A = rows 10-14, cols 5-9; B = rows 10-14, cols 15-19; C = rows 0-1, cols 23-24.
THREE = np.zeros((25, 25), dtype=np.uint16)
THREE[10:15, 5:10] = 1
THREE[10:15, 15:20] = 2
THREE[0:2, 23:25] = 3

# pixel -> (d1, d2), Euclidean distances to the nearest pixel of the nearest and second-nearest instance:
HAND_D = {
    (12, 12): (3.0, 3.0),  # gap centre: A at (12, 9), B at (12, 15); C at (1, 23) is sqrt(242) away
    (12, 10): (1.0, 5.0),  # A at (12, 9), B at (12, 15)
    (12, 7): (0.0, 8.0),  # inside A; B at (12, 15)
    (8, 12): (math.sqrt(13), math.sqrt(13)),  # A at (10, 9) and B at (10, 15): dy 2, dx 3
    (0, 22): (1.0, math.sqrt(109)),  # C at (0, 23); B at (10, 19): dy 10, dx 3 (A: sqrt(269) is third)
    (0, 24): (0.0, math.sqrt(125)),  # inside C; B at (10, 19): dy 10, dx 5
    (24, 0): (math.sqrt(10**2 + 5**2), math.sqrt(10**2 + 15**2)),  # A at (14, 5), B at (14, 15)
}


@pytest.mark.req("FR-012-20")
def test_pinned_weight_map_parameters() -> None:
    assert loss.W0 == 10.0
    assert loss.SIGMA_PX == 5.0


@pytest.mark.req("FR-012-20")
@pytest.mark.parametrize("pixel", sorted(HAND_D))
def test_border_term_matches_the_hand_calculated_eq_2(pixel: tuple[int, int]) -> None:
    w = loss.weight_map(THREE)
    wc = loss.class_weight_map(THREE)
    assert w.dtype == np.float64
    assert w.shape == THREE.shape
    d1, d2 = HAND_D[pixel]
    np.testing.assert_allclose(w[pixel] - wc[pixel], _border(d1, d2), rtol=1e-12, atol=ATOL)


@pytest.mark.req("FR-012-20")
def test_border_term_values_are_the_published_magnitudes() -> None:
    # Spot values of 10 exp(-(d1 + d2)^2 / 50): gap centre 10 e^-0.72 = 4.8675..., inside A 10 e^-1.28 = 2.7803...
    w = loss.weight_map(THREE) - loss.class_weight_map(THREE)
    assert w[12, 12] == pytest.approx(4.867522559599717, rel=1e-12)
    assert w[12, 7] == pytest.approx(2.780373004531941, rel=1e-12)


@pytest.mark.req("FR-012-20")
def test_class_weights_are_inverse_class_frequencies_with_mean_one() -> None:
    wc = loss.class_weight_map(THREE)
    enc = _ref_encode(THREE)
    freq = {c: float((enc == c).mean()) for c in (0, 1, 2)}
    assert all(f > 0 for f in freq.values())
    products = {c: float(wc[enc == c][0]) * freq[c] for c in (0, 1, 2)}
    for c in (0, 1, 2):
        assert np.ptp(wc[enc == c]) == 0.0, "one weight per class"
        assert products[c] == pytest.approx(products[0], rel=1e-12), "w_c proportional to 1 / frequency"
    pixel_mean = float(wc.mean())
    class_mean = float(np.mean([wc[enc == c][0] for c in (0, 1, 2)]))
    # "inverse frequency, mean 1" (spec 012 section 7) does not say whether the mean is over pixels or over the
    # three classes; either reading is accepted (reported as an ambiguity).
    assert pixel_mean == pytest.approx(1.0, rel=1e-12) or class_mean == pytest.approx(1.0, rel=1e-12)


@pytest.mark.req("FR-012-20")
def test_fewer_than_two_instances_have_no_border_term() -> None:
    empty = np.zeros((20, 20), dtype=np.uint16)
    np.testing.assert_array_equal(loss.weight_map(empty), loss.class_weight_map(empty))
    np.testing.assert_allclose(loss.class_weight_map(empty), 1.0, rtol=0, atol=ATOL)
    one = empty.copy()
    one[5:12, 3:9] = 4
    np.testing.assert_array_equal(loss.weight_map(one), loss.class_weight_map(one))


# ---------------------------------------------------------------- P-012-16 weight-map invariants


@st.composite
def _label_images(draw) -> np.ndarray:
    h, w = draw(st.integers(8, 64)), draw(st.integers(8, 64))
    lab = np.zeros((h, w), dtype=np.uint16)
    ids = draw(st.lists(st.integers(1, 65535), unique=True, max_size=6))
    for i in ids:
        top, left = draw(st.integers(0, h - 1)), draw(st.integers(0, w - 1))
        rh, rw = draw(st.integers(1, 20)), draw(st.integers(1, 20))
        lab[top : top + rh, left : left + rw] = i
    return lab


@pytest.mark.req("P-012-16")
@settings(max_examples=EXAMPLES, deadline=None)
@given(lab=_label_images())
def test_weight_map_is_dihedral_equivariant(lab: np.ndarray) -> None:
    w = loss.weight_map(lab)
    for lab_t, w_t in zip(_dihedral(lab), _dihedral(w), strict=True):
        np.testing.assert_allclose(loss.weight_map(np.ascontiguousarray(lab_t)), w_t, rtol=0, atol=ATOL)


@pytest.mark.req("P-012-16")
@settings(max_examples=EXAMPLES, deadline=None)
@given(lab=_label_images(), data=st.data())
def test_weight_map_is_invariant_under_instance_relabelling(lab: np.ndarray, data) -> None:
    ids = [int(i) for i in np.unique(lab) if i]
    new = data.draw(st.lists(st.integers(1, 65535), unique=True, min_size=len(ids), max_size=len(ids)))
    relabelled = np.zeros_like(lab)
    for old, nw in zip(ids, new, strict=True):
        relabelled[lab == old] = nw
    np.testing.assert_allclose(loss.weight_map(relabelled), loss.weight_map(lab), rtol=0, atol=ATOL)


@pytest.mark.req("P-012-16")
@settings(max_examples=EXAMPLES, deadline=None)
@given(lab=_label_images())
def test_weight_map_is_at_least_the_class_weight_with_equality_below_two_instances(lab: np.ndarray) -> None:
    w, wc = loss.weight_map(lab), loss.class_weight_map(lab)
    assert (w >= wc - ATOL).all()
    assert (w <= wc + W0 + ATOL).all()
    if len([i for i in np.unique(lab) if i]) < 2:
        np.testing.assert_array_equal(w, wc)


# ---------------------------------------------------------------- FR-012-20 loss (weighted CE + soft Dice)


def _targets(kind: str):
    import torch

    t = torch.zeros(2, 64, 64, dtype=torch.int64)
    if kind == "foreground":
        t[:] = 1
        t[:, ::3, :] = 2
    return t


@pytest.mark.req("FR-012-20")
def test_uniform_logits_on_an_all_foreground_target_give_ln3_plus_0_2() -> None:
    import torch

    logits = torch.zeros(2, 3, 64, 64, requires_grad=True)
    value = loss.unet_loss(logits, _targets("foreground"), torch.ones(2, 64, 64))
    assert value.ndim == 0
    # CE = ln 3; foreground probability 2/3 everywhere, target 1: Dice = 2 (2/3) / (2/3 + 1) = 0.8, so 1 - Dice = 0.2.
    # atol 1e-3 covers any Dice smoothing constant <= 1 over 8,192 pixels (shift < 2e-5).
    assert float(value) == pytest.approx(math.log(3) + 0.2, abs=1e-3)
    value.backward()
    assert torch.isfinite(logits.grad).all()


@pytest.mark.req("FR-012-20")
def test_uniform_logits_on_an_all_background_target_give_ln3_plus_1() -> None:
    import torch

    value = loss.unet_loss(torch.zeros(2, 3, 64, 64), _targets("background"), torch.ones(2, 64, 64))
    # Dice of probability 2/3 against an empty target is 0 (up to the smoothing constant: < 4e-4 for 1 over 8,192 px).
    assert float(value) == pytest.approx(math.log(3) + 1.0, abs=1e-3)


@pytest.mark.req("FR-012-20")
def test_confident_correct_logits_give_a_loss_near_zero() -> None:
    import torch

    t = _targets("foreground")
    t[:, :, :20] = 0
    logits = torch.nn.functional.one_hot(t, 3).permute(0, 3, 1, 2).float() * 60.0 - 30.0
    value = loss.unet_loss(logits, t, torch.ones(2, 64, 64))
    assert float(value) == pytest.approx(0.0, abs=1e-4)


@pytest.mark.req("FR-012-20")
def test_cross_entropy_is_pixel_weighted() -> None:
    import torch

    t = _targets("foreground")
    logits = torch.zeros(2, 3, 64, 64)
    logits[:, 1] = 4.0  # predicts interior everywhere: correct on class-1 pixels, wrong on class-2 rows
    base = torch.ones(2, 64, 64)
    heavy_wrong = base.clone()
    heavy_wrong[t == 2] = 10.0
    heavy_right = base.clone()
    heavy_right[t == 1] = 10.0
    l_base = float(loss.unet_loss(logits, t, base))
    assert float(loss.unet_loss(logits, t, heavy_wrong)) > l_base
    assert float(loss.unet_loss(logits, t, heavy_wrong)) > float(loss.unet_loss(logits, t, heavy_right))
