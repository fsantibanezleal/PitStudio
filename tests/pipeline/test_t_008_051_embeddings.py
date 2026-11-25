# ruff: noqa: E501, PT018
"""T-008-051 (CPU half): DINOv2 ViT-S/14 pin (model id, revision, weights SHA-256, licence), one shared preprocessing function,
bitwise CPU re-run, `ModelPinMismatch`, hostile images rejected.

Requirements: FR-008-40, FR-008-41, FR-008-48.

Spec: specs/008-data-pipeline/spec.md FR-008-40 (frozen DINOv2 ViT-S/14 embeddings with the model id, revision and weights
SHA-256 pinned; one preprocessing function with its parameters recorded in the manifest for real and synthetic images alike;
on CPU the same code path runs and gives bitwise-identical embeddings across runs), FR-008-41 (a weights SHA-256, revision or
licence (Apache-2.0) that differs from the pin makes `s20_feature_extraction` refuse to embed with `ModelPinMismatch`),
FR-008-48 (an image that is not decodable, has a channel count other than 3, or a side < 14 px is rejected with a report
naming the image). The CPU-versus-GPU cosine >= 0.999 half is `tests/gpu/test_t_008_051_embeddings_gpu.py`.

Oracle: no network and no real weights are needed: a tiny deterministic torch module stands in for the backbone (the code
path under test is the pin check, the preprocessing and the batching, not the transformer), a fake weights file whose SHA-256
is computed with `hashlib`, and hand-built images (PNG written with Pillow; the 14 px boundary is the ViT-S/14 patch size).

Expected API of the implementation (module `pitstudio_pipeline.features`):
- `verify_model_pin(weights_path, *, pin, revision, licence) -> None`: `pin` is `{"model_id", "revision", "weights_sha256",
  "licence"}`; `revision` and `licence` are the values observed on the loaded model; raises
  `pitstudio_pipeline.errors.ModelPinMismatch` when the file's SHA-256, `revision` or `licence` differs from the pin.
- `preprocess_image(image) -> numpy.ndarray`: the single preprocessing function (uint8 H x W x 3 -> float32 C x H' x W');
  `PREPROCESS_PARAMS`: the dict of its parameters (JSON-serialisable, non-empty).
- `check_image(image, *, name) -> numpy.ndarray`: `image` is an array (H, W, C) or encoded image bytes; returns the decoded
  uint8 H x W x 3 array or raises `IngestionRejected` (violation `file` = `name`, `field` `image`, `field_kind` `property`).
- `embed_images(images, *, model, weights_path, pin, revision, licence, device="cpu") -> EmbeddingResult` with `.embeddings`
  (float32 array, one row per image), `.manifest` (dict with `preprocess` = `PREPROCESS_PARAMS` and `pin` = the pin) and
  `.device`; it verifies the pin and checks every image BEFORE calling the model and calls `preprocess_image` once per image.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path

import _p008_kit as kit
import numpy as np
import pytest
from pitstudio_pipeline import features
from pitstudio_pipeline.errors import IngestionRejected, ModelPinMismatch
from pitstudio_pipeline.features import check_image, embed_images, verify_model_pin

REVISION = "0123456789abcdef0123456789abcdef01234567"


def tiny_model():
    import torch

    class Tiny(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            g = torch.Generator().manual_seed(0)
            self.w = torch.randn(3, 8, generator=g)
            self.calls = 0

        def forward(self, x):
            self.calls += 1
            return x.mean(dim=(2, 3)) @ self.w

    return Tiny().eval()


@pytest.fixture
def pinned(tmp_path: Path):
    weights = tmp_path / "model.safetensors"
    weights.write_bytes(kit.payload(4096, 77))
    pin = {
        "model_id": "facebook/dinov2-small",
        "revision": REVISION,
        "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
        "licence": "Apache-2.0",
    }
    return weights, pin


def rgb(h: int = 28, w: int = 28, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, size=(h, w, 3), dtype=np.uint8)


def png_bytes(arr: np.ndarray, mode: str | None = None) -> bytes:  # `mode` documents the expected Pillow mode of `arr`
    from PIL import Image

    buf = io.BytesIO()
    img = Image.fromarray(arr)
    assert mode is None or img.mode == mode
    img.save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------------------------------------------ FR-008-41
@pytest.mark.req("FR-008-41")
def test_matching_pin_is_accepted(pinned) -> None:
    weights, pin = pinned
    assert verify_model_pin(weights, pin=pin, revision=REVISION, licence="Apache-2.0") is None


@pytest.mark.req("FR-008-41")
def test_tampered_weights_digest_is_refused(pinned) -> None:
    weights, pin = pinned
    data = bytearray(weights.read_bytes())
    data[100] ^= 0x01
    weights.write_bytes(bytes(data))
    with pytest.raises(ModelPinMismatch):
        verify_model_pin(weights, pin=pin, revision=REVISION, licence="Apache-2.0")


@pytest.mark.req("FR-008-41")
@pytest.mark.parametrize("revision", ["f" * 40, "", REVISION[:-1], REVISION.upper()])
def test_a_different_revision_is_refused(revision: str, pinned) -> None:
    weights, pin = pinned
    with pytest.raises(ModelPinMismatch):
        verify_model_pin(weights, pin=pin, revision=revision, licence="Apache-2.0")


@pytest.mark.req("FR-008-41")
@pytest.mark.parametrize("licence", ["MIT", "CC-BY-NC-4.0", "", "apache-2.0", "Apache-2.0 "])
def test_a_different_licence_is_refused(licence: str, pinned) -> None:
    weights, pin = pinned
    with pytest.raises(ModelPinMismatch):
        verify_model_pin(weights, pin=pin, revision=REVISION, licence=licence)


@pytest.mark.req("FR-008-41")
def test_a_missing_or_empty_weights_file_is_refused(tmp_path: Path, pinned) -> None:
    _, pin = pinned
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    with pytest.raises((ModelPinMismatch, FileNotFoundError)):
        verify_model_pin(tmp_path / "missing.bin", pin=pin, revision=REVISION, licence="Apache-2.0")
    with pytest.raises(ModelPinMismatch):
        verify_model_pin(empty, pin=pin, revision=REVISION, licence="Apache-2.0")


@pytest.mark.req("FR-008-41")
def test_embedding_refuses_before_running_the_model_when_the_pin_differs(pinned) -> None:
    weights, pin = pinned
    model = tiny_model()
    bad = copy.deepcopy(pin)
    bad["weights_sha256"] = "0" * 64
    with pytest.raises(ModelPinMismatch):
        embed_images([rgb()], model=model, weights_path=weights, pin=bad, revision=REVISION, licence="Apache-2.0")
    assert model.calls == 0


# ------------------------------------------------------------------------------------------------ FR-008-40
@pytest.mark.req("FR-008-40")
def test_cpu_embeddings_are_bitwise_identical_across_runs(pinned) -> None:
    weights, pin = pinned
    imgs = [rgb(28, 28, s) for s in range(4)] + [rgb(40, 56, 9)]
    a = embed_images(
        imgs, model=tiny_model(), weights_path=weights, pin=pin, revision=REVISION, licence="Apache-2.0", device="cpu"
    )
    b = embed_images(
        imgs, model=tiny_model(), weights_path=weights, pin=pin, revision=REVISION, licence="Apache-2.0", device="cpu"
    )
    assert a.embeddings.dtype == np.float32 and a.embeddings.shape[0] == 5
    assert a.embeddings.tobytes() == b.embeddings.tobytes()
    assert a.device == "cpu"


@pytest.mark.req("FR-008-40")
def test_embedding_of_an_image_does_not_depend_on_its_batch_companions(pinned) -> None:
    weights, pin = pinned
    kw = dict(model=tiny_model(), weights_path=weights, pin=pin, revision=REVISION, licence="Apache-2.0", device="cpu")
    alone = embed_images([rgb(28, 28, 1)], **kw).embeddings
    together = embed_images([rgb(28, 28, 0), rgb(28, 28, 1), rgb(28, 28, 2)], **kw).embeddings
    np.testing.assert_allclose(alone[0], together[1], rtol=1e-5, atol=1e-6)


@pytest.mark.req("FR-008-40")
def test_one_preprocessing_function_is_used_for_every_image_and_its_parameters_are_recorded(
    pinned, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights, pin = pinned
    seen: list[tuple[int, ...]] = []
    original = features.preprocess_image

    def spy(image):
        seen.append(tuple(image.shape))
        return original(image)

    monkeypatch.setattr(features, "preprocess_image", spy)
    real_like, synthetic_like = rgb(28, 28, 1), rgb(42, 28, 2)
    res = embed_images(
        [real_like, synthetic_like],
        model=tiny_model(),
        weights_path=weights,
        pin=pin,
        revision=REVISION,
        licence="Apache-2.0",
        device="cpu",
    )
    assert seen == [real_like.shape, synthetic_like.shape]
    assert res.manifest["preprocess"] == features.PREPROCESS_PARAMS and res.manifest["pin"] == pin
    assert (
        features.PREPROCESS_PARAMS and json.loads(json.dumps(features.PREPROCESS_PARAMS)) == features.PREPROCESS_PARAMS
    )


@pytest.mark.req("FR-008-40")
def test_preprocessing_returns_float32_channels_first() -> None:
    out = features.preprocess_image(rgb(28, 42, 3))
    assert out.dtype == np.float32 and out.ndim == 3 and out.shape[0] == 3
    assert np.isfinite(out).all()
    assert np.array_equal(out, features.preprocess_image(rgb(28, 42, 3))), "deterministic"


# ------------------------------------------------------------------------------------------------ FR-008-48
@pytest.mark.req("FR-008-48")
def test_valid_images_are_decoded_including_the_14_px_boundary() -> None:
    assert check_image(rgb(14, 14), name="raw/t/a.png").shape == (14, 14, 3)
    assert check_image(png_bytes(rgb(14, 20)), name="raw/t/b.png").shape == (14, 20, 3)


@pytest.mark.req("FR-008-48")
@pytest.mark.parametrize(
    "make",
    [
        lambda: b"",
        lambda: kit.payload(512, 4),
        lambda: png_bytes(rgb(28, 28))[:40],  # truncated PNG
        lambda: png_bytes(np.zeros((28, 28), dtype=np.uint8), "L"),  # 1 channel
        lambda: png_bytes(np.zeros((28, 28, 4), dtype=np.uint8), "RGBA"),  # 4 channels
        lambda: rgb(8, 8),  # side < 14
        lambda: rgb(13, 28),
        lambda: rgb(28, 13),
        lambda: np.zeros((28, 28), dtype=np.uint8),  # 2-D array: no channel axis
        lambda: np.zeros((28, 28, 1), dtype=np.uint8),
        lambda: np.zeros((28, 28, 4), dtype=np.uint8),
        lambda: np.zeros((0, 0, 3), dtype=np.uint8),
    ],
    ids=[
        "empty",
        "garbage",
        "truncated-png",
        "one-channel",
        "four-channels",
        "8px",
        "13x28",
        "28x13",
        "2d",
        "1ch-array",
        "4ch-array",
        "zero-size",
    ],
)
def test_hostile_images_are_rejected_naming_the_image(make) -> None:
    with pytest.raises(IngestionRejected) as info:
        check_image(make(), name="raw/t/bad.png")
    v = info.value.violations[0]
    assert v["file"] == "raw/t/bad.png" and v["field_kind"] == "property" and v["field"] == "image"


@pytest.mark.req("FR-008-48")
def test_one_bad_image_stops_the_batch_before_the_model_runs(pinned) -> None:
    weights, pin = pinned
    model = tiny_model()
    with pytest.raises(IngestionRejected):
        embed_images(
            [rgb(28, 28), rgb(8, 8), rgb(28, 28)],
            model=model,
            weights_path=weights,
            pin=pin,
            revision=REVISION,
            licence="Apache-2.0",
            device="cpu",
        )
    assert model.calls == 0
