"""U-Net factory (spec 012, FR-012-20, FR-012-21): smp Unet with the timm encoder resnet18.a1_in1k, 3 classes."""

from __future__ import annotations

import numpy as np
import timm
import torch
from torch import nn

ENCODER_NAME = "resnet18.a1_in1k"  # Apache-2.0 model card; the smp hub copy of the torchvision weights is not used
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
NUM_CLASSES = 3
DECODER_CHANNELS = (256, 128, 64, 32, 16)

try:  # FR-012-21: fall back to the vendored layout where smp cannot be imported
    import segmentation_models_pytorch as smp

    BACKEND = "smp"
except ImportError:
    smp = None
    BACKEND = "vendored"


def _conv_block(cin: int, cout: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1, bias=False),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
        nn.Conv2d(cout, cout, 3, padding=1, bias=False),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
    )


class _DecoderBlock(nn.Module):
    """Upsample x2, concatenate the skip (if any), two 3 x 3 conv-BN-ReLU."""

    def __init__(self, cin: int, skip: int, cout: int) -> None:
        super().__init__()
        self.conv = _conv_block(cin + skip, cout)

    def forward(self, x: torch.Tensor, skip: torch.Tensor | None) -> torch.Tensor:
        x = nn.functional.interpolate(x, scale_factor=2.0, mode="nearest")
        if skip is not None:
            x = torch.cat([x, skip], dim=1)
        return self.conv(x)


class _Encoder(nn.Module):
    """timm features-only ResNet-18; returns the input followed by the five stage maps (strides 2 to 32)."""

    def __init__(self, pretrained: bool) -> None:
        super().__init__()
        self.model = timm.create_model(ENCODER_NAME, features_only=True, pretrained=pretrained)
        self.out_channels = [3, *self.model.feature_info.channels()]

    def forward(self, x: torch.Tensor) -> list[torch.Tensor]:
        return [x, *self.model(x)]


class _Decoder(nn.Module):
    def __init__(self, encoder_channels: list[int]) -> None:
        super().__init__()
        chans = encoder_channels[1:][::-1]  # deepest first
        skips = [*chans[1:], 0]
        ins = [chans[0], *DECODER_CHANNELS[:-1]]
        self.blocks = nn.ModuleList(
            _DecoderBlock(i, s, o) for i, s, o in zip(ins, skips, DECODER_CHANNELS, strict=True)
        )

    def forward(self, features: list[torch.Tensor]) -> torch.Tensor:
        feats = features[1:][::-1]
        x, skips = feats[0], [*feats[1:], None]
        for block, skip in zip(self.blocks, skips, strict=True):
            x = block(x, skip)
        return x


class VendoredUnet(nn.Module):
    """Minimal U-Net with the smp layer table (encoder 3/64/64/128/256/512, decoder 256/128/64/32/16)."""

    def __init__(self, pretrained: bool = False, classes: int = NUM_CLASSES) -> None:
        super().__init__()
        self.encoder = _Encoder(pretrained)
        self.decoder = _Decoder(self.encoder.out_channels)
        self.segmentation_head = nn.Conv2d(DECODER_CHANNELS[-1], classes, 3, padding=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.segmentation_head(self.decoder(self.encoder(x)))


def build_unet(encoder_weights: str | None = "imagenet") -> nn.Module:
    """Float32 [N, 3, 512, 512] to logits [N, 3, 512, 512]. `encoder_weights=None` never downloads."""
    if BACKEND == "smp":
        return smp.Unet(encoder_name=f"tu-{ENCODER_NAME}", encoder_weights=encoder_weights, classes=NUM_CLASSES)
    return VendoredUnet(pretrained=encoder_weights is not None)


def normalise(image: np.ndarray) -> torch.Tensor:
    """(H, W, 3) uint8 RGB to float32 [3, H, W] = (image / 255 - mean) / std per channel."""
    image = np.asarray(image)
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError(f"image must be H x W x 3 uint8, got {image.shape} {image.dtype}")
    x = torch.from_numpy(np.ascontiguousarray(image)).permute(2, 0, 1).float() / 255.0
    mean = torch.tensor(IMAGENET_MEAN).view(3, 1, 1)
    std = torch.tensor(IMAGENET_STD).view(3, 1, 1)
    return (x - mean) / std


def infer(model: nn.Module, x: torch.Tensor) -> torch.Tensor:
    """FR-012-23: class probabilities softmax(model(x), dim=1) for a float32 [N, 3, 512, 512] tensor with finite values.

    Anything else raises ValueError before the model runs.
    """
    if not isinstance(x, torch.Tensor):
        raise ValueError(f"x must be a torch.Tensor, got {type(x).__name__}")
    if x.dtype != torch.float32:
        raise ValueError(f"x must be float32, got {x.dtype}")
    if x.ndim != 4 or tuple(x.shape[1:]) != (3, 512, 512):
        raise ValueError(f"x must have shape [N, 3, 512, 512], got {tuple(x.shape)}")
    if not bool(torch.isfinite(x).all()):
        raise ValueError("x contains a non-finite value")
    return torch.softmax(model(x), dim=1)
