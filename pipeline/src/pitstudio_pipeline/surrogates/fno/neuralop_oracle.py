"""The `neuraloperator` spectral convolution as a second oracle for the layer of `spectral` (FR-011-43, optional).

`neuralop` (the import name of `neuraloperator`, installed through the optional `neuralop` extra of `pipeline/`) is imported lazily.
Its `SpectralConv` stores the kept rows in fftshifted order (the negative frequencies -m1 ... -1 first, then 0 ... m1 - 1), so the
weights of `spectral` (rows 0 ... m1 - 1 then the negative rows) are rotated by m1 rows before they are loaded; the unnormalised
forward and the 1 / N^2 inverse of `spectral` equal its "forward" normalisation. This module is for checks, not for the model: the
model never imports it.
"""

from __future__ import annotations

import numpy as np


def reference_conv(x: np.ndarray, weight_re: np.ndarray, weight_im: np.ndarray, modes1: int = 12, modes2: int = 12) -> np.ndarray:
    """Output [B, C_out, N, N] of neuraloperator's spectral convolution loaded with the weights of the layer of `spectral`."""
    import torch
    from neuralop.layers.spectral_convolution import SpectralConv

    c_in, c_out = weight_re.shape[0], weight_re.shape[1]
    conv = SpectralConv(c_in, c_out, n_modes=(2 * modes1, 2 * (modes2 - 1)), bias=False, fft_norm="forward", init_std=1.0)
    weight = np.concatenate([weight_re[:, :, modes1:], weight_re[:, :, :modes1]], axis=2) + 1j * np.concatenate(
        [weight_im[:, :, modes1:], weight_im[:, :, :modes1]], axis=2
    )
    with torch.no_grad():
        conv.weight.tensor.copy_(torch.from_numpy(weight.astype(np.complex64)))
        return conv(torch.from_numpy(np.asarray(x, dtype=np.float32))).numpy()
