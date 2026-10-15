"""TCN and PatchTST forecasters of case C1 (FR-010-21).

Both map a float32 context (B, 2, 128) (scaled inverse velocity, mask) to the quantiles 0.1 ... 0.9 of the next 64
steps,
(B, 9, 64), in the units of the scaled context. The quantiles are non-crossing by construction: the median path plus
cumulative softplus increments up and down. TCN: residual blocks of dilated causal 1-D convolutions (kernel 3, dilations
1 ... 32). PatchTST: channel-independent Transformer encoder over patches of 16 with stride 8 (15 patches).
"""

from __future__ import annotations

import torch
from torch import nn

CONTEXT_LENGTH = 128
HORIZON = 64
N_QUANTILES = 9
MEDIAN_ROW = 4
ARMS = ("tcn", "patchtst")


class _Quantile(nn.Module):
    """Head: features -> median path and positive increments -> non-crossing quantile paths (B, 9, 64)."""

    def __init__(self, features: int) -> None:
        super().__init__()
        self.out = nn.Linear(features, HORIZON * (1 + (N_QUANTILES - 1)))

    def forward(self, h: torch.Tensor) -> torch.Tensor:
        raw = self.out(h).reshape(-1, N_QUANTILES, HORIZON)
        median = raw[:, :1]
        up = torch.cumsum(nn.functional.softplus(raw[:, 1:5] - 2.0), dim=1)
        down = torch.cumsum(nn.functional.softplus(raw[:, 5:9] - 2.0), dim=1)
        return torch.cat([(median - down).flip(1), median, median + up], dim=1)


class _Block(nn.Module):
    def __init__(self, channels: int, dilation: int) -> None:
        super().__init__()
        self.pad = 2 * dilation
        self.c1 = nn.Conv1d(channels, channels, 3, dilation=dilation)
        self.c2 = nn.Conv1d(channels, channels, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = torch.cat([torch.zeros_like(x[:, :, : self.pad]), x], dim=2)  # causal padding without a Pad op (opset 17)
        return x + self.c2(torch.relu(self.c1(h)))


class TCN(nn.Module):
    def __init__(self, channels: int = 48) -> None:
        super().__init__()
        self.inp = nn.Conv1d(2, channels, 1)
        self.blocks = nn.Sequential(*[_Block(channels, d) for d in (1, 2, 4, 8, 16, 32)])
        self.head = _Quantile(channels * 2)

    def forward(self, context: torch.Tensor) -> torch.Tensor:
        h = self.blocks(self.inp(context))
        # sum / length instead of mean: ReduceMean takes its axes as an input from opset 18 and would block opset 17
        return self.head(torch.cat([h[:, :, -1], h.sum(dim=2) / CONTEXT_LENGTH], dim=1))


class PatchTST(nn.Module):
    patch_length = 16
    stride = 8

    def __init__(self, d_model: int = 32, layers: int = 3) -> None:
        super().__init__()
        self.n_patches = (CONTEXT_LENGTH - self.patch_length) // self.stride + 1
        self.embed = nn.Linear(self.patch_length, d_model)
        self.pos = nn.Parameter(torch.zeros(1, self.n_patches, d_model))
        layer = nn.TransformerEncoderLayer(d_model, 4, 4 * d_model, dropout=0.0, batch_first=True)
        self.encoder = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.head = _Quantile(2 * self.n_patches * d_model)

    def forward(self, context: torch.Tensor) -> torch.Tensor:
        b = context.shape[0]
        patches = context.unfold(2, self.patch_length, self.stride)  # (B, 2, P, 16): channels are independent
        x = self.embed(patches).reshape(b * 2, self.n_patches, -1) + self.pos
        h = self.encoder(x).reshape(b, -1)
        return self.head(h)


def build_model(arm: str, *, seed: int = 0) -> nn.Module:
    """A freshly initialised model of ``arm`` ("tcn" or "patchtst"); the same seed gives identical weights."""
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {list(ARMS)}, got {arm!r}")
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        return TCN() if arm == "tcn" else PatchTST()
