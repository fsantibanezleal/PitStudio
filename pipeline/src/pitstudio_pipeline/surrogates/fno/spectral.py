"""Spectral convolution of the FNO as real matrix products (FR-011-32, P-011-12 ... P-011-16).

The layer keeps the modes k1 in {0 ... m1-1} and {N-m1 ... N-1} (rows) and k2 in {0 ... m2-1} (columns) of the two-dimensional
Fourier transform of a real field. The forward transform at those modes is the unnormalised sum

    X[k1, k2] = sum_{n1, n2} x[n1, n2] exp(-2 pi i (k1 n1 + k2 n2) / N),

written as real products with precomputed cosine and sine bases (real part C1 x C2^T - S1 x S2^T, imaginary part -(S1 x C2^T +
C1 x S2^T)). The per-mode channel mixing multiplies the two real planes with the real and imaginary weights, one batched matrix
product per mode. The inverse transform (weight 1 for k2 = 0 and 2 otherwise, divided by N^2) is again four real products. No call
to the transform of any library is made and no tensor of a two-component number type is created, so the graph exports to ONNX with
MatMul, Add, Sub, Reshape and Transpose only (the whitelist of FR-011-36): the bases are constants, there is no negation node (the
negated bases are constants too) and no broadcast node.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache

import numpy as np
import torch

MODES = 12


def kept_rows(n: int, modes1: int = MODES) -> list[int]:
    """The kept row frequencies: the low positive ones and the low negative ones."""
    return list(range(modes1)) + list(range(n - modes1, n))


@lru_cache(maxsize=16)
def _bases_np(n: int, modes1: int, modes2: int) -> dict[str, np.ndarray]:
    """Cosine and sine bases (float64) at the kept modes; angles from exact integer products modulo N."""
    rows = np.array(kept_rows(n, modes1))
    cols = np.arange(modes2)
    grid = np.arange(n)
    a1 = 2.0 * math.pi * ((rows[:, None] * grid[None, :]) % n) / n  # [2 m1, N]
    a2 = 2.0 * math.pi * ((cols[:, None] * grid[None, :]) % n) / n  # [m2, N]
    c1, s1, c2, s2 = np.cos(a1), np.sin(a1), np.cos(a2), np.sin(a2)
    w = np.where(cols == 0, 1.0, 2.0)[:, None] / (n * n)  # inverse weight and 1 / N^2, per kept column
    return {
        "c1": c1, "ns1": -s1, "nc1": -c1,  # forward, rows: real = c1 A + ns1 B, imaginary = ns1 A + nc1 B
        "c2t": c2.T, "s2t": s2.T,  # forward, columns [N, m2]
        "c1t": c1.T, "ns1t": -s1.T,  # inverse, rows [N, 2 m1]
        "c2w": w * c2, "s2w": w * s2,  # inverse, columns with the weights folded in [m2, N]
    }  # fmt: skip


def _bases(n: int, modes1: int, modes2: int, like: torch.Tensor) -> dict[str, torch.Tensor]:
    return {k: torch.from_numpy(v).to(dtype=like.dtype, device=like.device) for k, v in _bases_np(n, modes1, modes2).items()}


def _check_field(x: torch.Tensor, modes1: int, modes2: int) -> int:
    if x.is_complex():
        raise ValueError("the spectral layer is real-valued: the input must be a real tensor")
    if x.dim() < 3 or x.shape[-1] != x.shape[-2]:
        raise ValueError(f"the input must have square trailing axes [..., N, N], got {list(x.shape)}")
    n = int(x.shape[-1])
    if n < 2 * modes1 or n // 2 + 1 < modes2:
        raise ValueError(f"a {n} x {n} grid cannot hold {2 * modes1} x {modes2} kept modes")
    return n


def dft_forward(x: torch.Tensor, modes1: int = MODES, modes2: int = MODES) -> tuple[torch.Tensor, torch.Tensor]:
    """Real and imaginary parts [..., 2 modes1, modes2] of the unnormalised transform of `x` [..., N, N] at the kept modes."""
    n = _check_field(x, modes1, modes2)
    b = _bases(n, modes1, modes2, x)
    cols_c = torch.matmul(x, b["c2t"])  # [..., N, m2]
    cols_s = torch.matmul(x, b["s2t"])
    real = torch.matmul(b["c1"], cols_c) + torch.matmul(b["ns1"], cols_s)
    imag = torch.matmul(b["ns1"], cols_c) + torch.matmul(b["nc1"], cols_s)
    return real, imag


def spectral_conv2d(
    x: torch.Tensor, weight_re: torch.Tensor, weight_im: torch.Tensor, modes1: int = MODES, modes2: int = MODES
) -> torch.Tensor:
    """x [B, C_in, N, N] real, weights [C_in, C_out, 2 modes1, modes2] real -> [B, C_out, N, N] real."""
    n = _check_field(x, modes1, modes2)
    if x.dim() != 4:
        raise ValueError(f"the input must be [B, C_in, N, N], got {list(x.shape)}")
    c_in = int(x.shape[1])
    expected = (2 * modes1, modes2)
    for name, w in (("weight_re", weight_re), ("weight_im", weight_im)):
        if w.dim() != 4 or tuple(w.shape[2:]) != expected or int(w.shape[0]) != c_in:
            raise ValueError(f"{name} must have shape [{c_in}, C_out, {expected[0]}, {expected[1]}], got {list(w.shape)}")
    if weight_re.shape != weight_im.shape:
        raise ValueError("weight_re and weight_im must have the same shape")
    batch, c_out = int(x.shape[0]), int(weight_re.shape[1])
    xr, xi = dft_forward(x, modes1, modes2)  # [B, C_in, 2 m1, m2]
    k = expected[0] * expected[1]

    def mode_major(t: torch.Tensor) -> torch.Tensor:  # [B, C, K1, K2] -> [K1 K2, B, C]
        return t.permute(2, 3, 0, 1).reshape(k, batch, -1)

    wr = weight_re.permute(2, 3, 0, 1).reshape(k, c_in, c_out)
    wi = weight_im.permute(2, 3, 0, 1).reshape(k, c_in, c_out)
    xr_m, xi_m = mode_major(xr), mode_major(xi)
    yr = torch.matmul(xr_m, wr) - torch.matmul(xi_m, wi)  # [K, B, C_out]
    yi = torch.matmul(xr_m, wi) + torch.matmul(xi_m, wr)

    def plane(t: torch.Tensor) -> torch.Tensor:  # [K, B, C_out] -> [B, C_out, 2 m1, m2]
        return t.reshape(expected[0], expected[1], batch, c_out).permute(2, 3, 0, 1)

    yr, yi = plane(yr), plane(yi)
    b = _bases(n, modes1, modes2, x)
    t1 = torch.matmul(yr, b["c2w"])  # [B, C_out, 2 m1, N]
    t2 = torch.matmul(yr, b["s2w"])
    t3 = torch.matmul(yi, b["c2w"])
    t4 = torch.matmul(yi, b["s2w"])
    return torch.matmul(b["c1t"], t1 - t4) + torch.matmul(b["ns1t"], t2 + t3)


_VERSION = re.compile(r"^[0-9]+(\.[0-9]+)*$")


def spectral_oracle_statement(*, neuraloperator_version: str | None) -> str:
    """The sentence of the model card that names the spectral oracle (FR-011-43).

    Without `neuraloperator` the card states that the numpy FFT reference is the only spectral oracle; with it, that the layer was
    also checked against its spectral convolution with the same weights (named with its version).
    """
    if neuraloperator_version is None:
        return "The numpy FFT reference is the only spectral oracle of the spectral layer (neuraloperator did not resolve in the lock)."
    if not isinstance(neuraloperator_version, str) or not _VERSION.fullmatch(neuraloperator_version):
        raise ValueError(f"neuraloperator_version must be a dotted version such as '2.0.0', got {neuraloperator_version!r}")
    return (
        "The spectral layer was checked against the numpy FFT reference and also against the spectral convolution of "
        f"neuraloperator {neuraloperator_version} with the same weights."
    )
