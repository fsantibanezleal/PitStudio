"""FNO of the tailings and dust fields (FR-011-32, FR-011-33).

A direct map from input channels on a 64 x 64 grid to output channels: pointwise lifting to width 32, four Fourier layers (the sum of a
pointwise linear map and the spectral convolution of `spectral`, GELU after every layer but the last) and a pointwise projection.
Every pointwise map is a matrix product over the channel axis (no convolution node), so the exported graph stays inside the operator
whitelist of FR-011-36. The tailings instance maps [bed elevation, release depth, yield stress, plastic viscosity, density] to
[h(t_1) ... h(t_8), h_max]; the dust instance maps [bed elevation, source strength, wind speed, wind direction cos, sin] to the
time-averaged concentration.
"""

from __future__ import annotations

import torch
from torch import nn

from pitstudio_pipeline.surrogates.fno.spectral import MODES, spectral_conv2d

TAILINGS_INPUT_CHANNELS = ("bed_elevation", "release_depth", "yield_stress", "plastic_viscosity", "density")
TAILINGS_OUTPUT_CHANNELS = (*tuple(f"depth_t{k}" for k in range(1, 9)), "depth_max")
DUST_INPUT_CHANNELS = ("bed_elevation", "source_strength", "wind_speed", "wind_dir_cos", "wind_dir_sin")
DUST_OUTPUT_CHANNELS = ("concentration_mean",)


class Pointwise(nn.Module):
    """A per-pixel linear map over the channel axis: [B, C_in, H, W] -> [B, C_out, H, W] with MatMul and Add only."""

    def __init__(self, c_in: int, c_out: int) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.empty(c_out, c_in))
        self.bias = nn.Parameter(torch.zeros(1, c_out, 1))  # stored in broadcast shape: the graph adds it unchanged
        bound = 1.0 / c_in**0.5
        nn.init.uniform_(self.weight, -bound, bound)
        nn.init.uniform_(self.bias, -bound, bound)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, c, h, w = x.shape
        y = torch.matmul(self.weight, x.reshape(b, c, h * w)) + self.bias
        return y.reshape(b, self.weight.shape[0], h, w)


class FourierLayer(nn.Module):
    """x -> pointwise(x) + spectral_conv(x), the sum of FR-011-32."""

    def __init__(self, width: int, modes: tuple[int, int]) -> None:
        super().__init__()
        self.modes = modes
        self.pointwise = Pointwise(width, width)
        scale = 1.0 / (width * width)
        shape = (width, width, 2 * modes[0], modes[1])
        self.weight_re = nn.Parameter(scale * torch.rand(shape))
        self.weight_im = nn.Parameter(scale * torch.rand(shape))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.pointwise(x) + spectral_conv2d(x, self.weight_re, self.weight_im, self.modes[0], self.modes[1])


class FnoModel(nn.Module):
    """The 2-D Fourier neural operator (direct map, real arithmetic only)."""

    def __init__(
        self, in_channels: int, out_channels: int, *, width: int = 32, layers: int = 4, modes: tuple[int, int] = (MODES, MODES)
    ) -> None:
        super().__init__()
        if min(in_channels, out_channels, width, layers) < 1:
            raise ValueError("in_channels, out_channels, width and layers must be positive")
        self.in_channels, self.out_channels = in_channels, out_channels
        self.width, self.n_layers, self.modes = width, layers, tuple(modes)
        self.lift = Pointwise(in_channels, width)
        self.fourier_layers = nn.ModuleList(FourierLayer(width, self.modes) for _ in range(layers))
        self.layer_has_activation = [k < layers - 1 for k in range(layers)]
        self.project = Pointwise(width, out_channels)
        self.gelu = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.lift(x)
        for layer, active in zip(self.fourier_layers, self.layer_has_activation, strict=True):
            h = layer(h)
            if active:
                h = self.gelu(h)
        return self.project(h)


def build_tailings_model() -> FnoModel:
    """The tailings instance: 5 input channels to 9 output channels (h(t_1) ... h(t_8), h_max)."""
    return FnoModel(len(TAILINGS_INPUT_CHANNELS), len(TAILINGS_OUTPUT_CHANNELS))


def build_dust_model() -> FnoModel:
    """The dust instance: 5 input channels to the time-averaged concentration."""
    return FnoModel(len(DUST_INPUT_CHANNELS), len(DUST_OUTPUT_CHANNELS))
