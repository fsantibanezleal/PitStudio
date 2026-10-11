"""T-011-050 - FR-011-32, P-011-12 ... P-011-16: DFT-matmul spectral layer of the FNO.

Oracles (independent of the code under test):
- the numpy FFT as reference implementation: `numpy.fft.rfft2` at the kept modes (P-011-12), and the spectral
    convolution
  rfft2 -> per-mode complex weights on the kept modes -> irfft2 (P-011-13), written out in this file;
- kept modes k1 in {0..11} u {N-12..N-1} (rows), k2 in {0..11} (columns) for N = 64 (spec FR-011-32);
- the relations of plan 011: circular-shift equivariance (P-011-14), linearity (P-011-15), and resolution change
    (P-011-16):
  for an input band-limited to the kept modes, the layer with the same weights on the 128 x 128 trigonometric
      interpolation
  equals the trigonometric interpolation of the 64 x 64 output (interpolation = zero-padding of the spectrum,
      written here with
  numpy.fft; exact in real arithmetic);
- tolerances of the spec: float64 <= 1e-12 ||ref||_2 and float32 <= 1e-4 ||ref||_2 (P-011-12 ... P-011-15), 1e-10
    ||u||_2 for
  the resolution change (P-011-16);
- a source-level check of FR-011-32: no `torch.fft` call and no complex tensor anywhere in the spectral module, and
    every
  tensor produced by the layer is real.

Expected public API (module `pitstudio_pipeline.surrogates.fno.spectral`, package under `pipeline/src/`; torch tensors):

    kept_rows(n: int, modes1: int = 12) -> list[int]       [0..modes1-1] + [n-modes1..n-1]
    dft_forward(x, modes1: int = 12, modes2: int = 12) -> tuple[Tensor, Tensor]
        x [..., N, N] real; returns (re, im) of shape [..., 2 modes1, modes2]: the unnormalised forward transform
        sum x[n1, n2] exp(-2 pi i (k1 n1 + k2 n2) / N) at the kept modes, as real cosine and sine matrix products.
    spectral_conv2d(x, weight_re, weight_im, modes1: int = 12, modes2: int = 12) -> Tensor
        x [B, C_in, N, N] real, weights [C_in, C_out, 2 modes1, modes2] real (re and im parts of the per-mode complex
        weights); returns [B, C_out, N, N] real: forward at the kept modes, per-mode complex channel mixing,
            inverse weighted
        1 for k2 = 0 and 2 otherwise and divided by N^2, with real matrix products only. N is taken from x (64 or 128).
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

torch = pytest.importorskip("torch")  # pipeline/ job; skipped in the root job

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from hypothesis import given, settings  # noqa: E402  (locked in the pipeline/ env by T-011-002)
from hypothesis import strategies as st  # noqa: E402
from pitstudio_pipeline.surrogates.fno import spectral  # noqa: E402

EXAMPLES = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "property_tests"
]["ci_examples_per_test"]
M1, M2 = 12, 12


def rows_of(n: int) -> list[int]:
    return list(range(M1)) + list(range(n - M1, n))


def rng_for(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def ref_forward(x: np.ndarray) -> np.ndarray:
    n = x.shape[-1]
    return np.fft.rfft2(x)[..., rows_of(n), :M2]


def ref_conv(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    n = x.shape[-1]
    spec = ref_forward(x)  # [B, Cin, 24, 12]
    mixed = np.einsum("bixy,ioxy->boxy", spec, w)
    out = np.zeros((x.shape[0], w.shape[1], n, n // 2 + 1), dtype=complex)
    out[:, :, rows_of(n), :M2] = mixed
    return np.fft.irfft2(out, s=(n, n))


def rel(err: np.ndarray, ref: np.ndarray) -> float:
    return float(np.linalg.norm(err) / np.linalg.norm(ref))


def weights(seed: int, cin: int, cout: int, dtype=np.float64) -> tuple[np.ndarray, np.ndarray]:
    r = rng_for(seed)
    return r.normal(size=(cin, cout, 2 * M1, M2)).astype(dtype), r.normal(size=(cin, cout, 2 * M1, M2)).astype(dtype)


def run_conv(x: np.ndarray, wr: np.ndarray, wi: np.ndarray) -> np.ndarray:
    with torch.no_grad():
        return spectral.spectral_conv2d(torch.from_numpy(x), torch.from_numpy(wr), torch.from_numpy(wi)).numpy()


# ------------------------------------------------------------------ FR-011-32 structure


@pytest.mark.req("FR-011-32")
def test_kept_rows_are_the_low_positive_and_low_negative_frequencies() -> None:
    assert spectral.kept_rows(64) == list(range(12)) + list(range(52, 64))
    assert spectral.kept_rows(128) == list(range(12)) + list(range(116, 128))


@pytest.mark.req("FR-011-32")
def test_the_spectral_module_calls_no_fft_and_uses_no_complex_tensor() -> None:
    src = inspect.getsource(spectral)
    code = "\n".join(line.split("#", 1)[0] for line in src.splitlines())
    for pattern in (
        r"torch\.fft",
        r"\bfft\b",
        r"rfft",
        r"view_as_complex",
        r"torch\.complex",
        r"cfloat",
        r"cdouble",
        r"complex64",
        r"complex128",
    ):
        assert re.search(pattern, code) is None, pattern


@pytest.mark.req("FR-011-32")
def test_every_tensor_the_layer_returns_is_real_and_has_the_documented_shape() -> None:
    x = rng_for(1).normal(size=(2, 3, 64, 64))
    wr, wi = weights(2, 3, 4)
    out = spectral.spectral_conv2d(torch.from_numpy(x), torch.from_numpy(wr), torch.from_numpy(wi))
    assert not out.is_complex()
    assert tuple(out.shape) == (2, 4, 64, 64)
    re_, im_ = spectral.dft_forward(torch.from_numpy(x))
    assert not re_.is_complex()
    assert not im_.is_complex()
    assert tuple(re_.shape) == (2, 3, 24, 12)
    assert tuple(im_.shape) == (2, 3, 24, 12)


@pytest.mark.req("FR-011-32")
def test_a_unit_impulse_has_the_hand_known_spectrum_and_the_dc_component_is_the_sum() -> None:
    # delta at (0, 0): every kept mode equals 1 + 0i; a constant field c has X[0, 0] = c N^2 and zeros elsewhere
    n = 64
    delta = np.zeros((1, n, n))
    delta[0, 0, 0] = 1.0
    re_, im_ = spectral.dft_forward(torch.from_numpy(delta))
    assert np.allclose(re_.numpy(), 1.0, atol=1e-12)
    assert np.allclose(im_.numpy(), 0.0, atol=1e-12)
    const = np.full((1, n, n), 2.5)
    re_c, im_c = spectral.dft_forward(torch.from_numpy(const))
    assert re_c.numpy()[0, 0, 0] == pytest.approx(2.5 * n * n, rel=1e-12)
    mask = np.ones_like(re_c.numpy(), dtype=bool)
    mask[0, 0, 0] = False
    assert np.allclose(re_c.numpy()[mask], 0.0, atol=1e-9)
    assert np.allclose(im_c.numpy(), 0.0, atol=1e-9)


# ------------------------------------------------------------------ P-011-12 forward transform


@pytest.mark.req("P-011-12")
@settings(max_examples=EXAMPLES, deadline=None)
@given(seed=st.integers(0, 2**32 - 1), dtype=st.sampled_from([np.float64, np.float32]))
def test_forward_transform_equals_numpy_rfft2_at_the_kept_modes(seed: int, dtype) -> None:
    x = rng_for(seed).normal(size=(2, 3, 64, 64)).astype(dtype)
    re_, im_ = spectral.dft_forward(torch.from_numpy(x))
    got = re_.numpy().astype(np.float64) + 1j * im_.numpy().astype(np.float64)
    ref = ref_forward(x.astype(np.float64))
    tol = 1e-12 if dtype == np.float64 else 1e-4
    assert rel(got - ref, ref) <= tol


# ------------------------------------------------------------------ P-011-13 spectral convolution against the FFT
#   reference


@pytest.mark.req("P-011-13")
@settings(max_examples=EXAMPLES, deadline=None)
@given(seed=st.integers(0, 2**32 - 1), dtype=st.sampled_from([np.float64, np.float32]))
def test_spectral_convolution_equals_the_fft_reference(seed: int, dtype) -> None:
    x = rng_for(seed).normal(size=(2, 3, 64, 64)).astype(dtype)
    wr, wi = weights(seed + 1, 3, 2, dtype)
    got = run_conv(x, wr, wi).astype(np.float64)
    ref = ref_conv(x.astype(np.float64), wr.astype(np.float64) + 1j * wi.astype(np.float64))
    assert rel(got - ref, ref) <= (1e-12 if dtype == np.float64 else 1e-4)


@pytest.mark.req("P-011-13")
def test_a_single_mode_weight_gives_the_hand_known_cosine_wave() -> None:
    # weight 1 + 0i on mode (k1, k2) = (0, 1) only, one channel: y = (2 / N^2) Re(X[0, 1] e^{2 pi i n2 / N}) summed
    #   over modes
    n = 64
    x = np.cos(2.0 * np.pi * np.arange(n)[None, :] / n) * np.ones((n, 1))  # cos(2 pi n2 / N), constant in n1
    wr = np.zeros((1, 1, 2 * M1, M2))
    wi = np.zeros_like(wr)
    wr[0, 0, 0, 1] = 1.0  # row k1 = 0, column k2 = 1
    out = run_conv(x[None, None], wr, wi)[0, 0]
    # X[0, 1] = N^2 / 2 for x = cos(2 pi n2 / N), so y = (2 / N^2) (N^2 / 2) cos(2 pi n2 / N) = x
    assert np.allclose(out, x, atol=1e-12)


# ------------------------------------------------------------------ P-011-14 .. P-011-16 metamorphic relations


@pytest.mark.req("P-011-14")
@settings(max_examples=EXAMPLES, deadline=None)
@given(
    seed=st.integers(0, 2**32 - 1),
    s1=st.integers(0, 63),
    s2=st.integers(0, 63),
    dtype=st.sampled_from([np.float64, np.float32]),
)
def test_circular_shift_of_the_input_shifts_the_output(seed: int, s1: int, s2: int, dtype) -> None:
    x = rng_for(seed).normal(size=(1, 2, 64, 64)).astype(dtype)
    wr, wi = weights(seed + 2, 2, 2, dtype)
    base = run_conv(x, wr, wi).astype(np.float64)
    shifted = run_conv(np.roll(x, (s1, s2), axis=(2, 3)), wr, wi).astype(np.float64)
    expected = np.roll(base, (s1, s2), axis=(2, 3))
    assert rel(shifted - expected, expected) <= (1e-12 if dtype == np.float64 else 1e-4)


@pytest.mark.req("P-011-15")
@settings(max_examples=EXAMPLES, deadline=None)
@given(
    seed=st.integers(0, 2**32 - 1),
    alpha=st.floats(-10.0, 10.0),
    beta=st.floats(-10.0, 10.0),
    dtype=st.sampled_from([np.float64, np.float32]),
)
def test_the_spectral_convolution_is_linear(seed: int, alpha: float, beta: float, dtype) -> None:
    r = rng_for(seed)
    x = r.normal(size=(1, 2, 64, 64)).astype(dtype)
    y = r.normal(size=(1, 2, 64, 64)).astype(dtype)
    wr, wi = weights(seed + 3, 2, 2, dtype)
    lhs = run_conv((alpha * x + beta * y).astype(dtype), wr, wi).astype(np.float64)
    rhs = alpha * run_conv(x, wr, wi).astype(np.float64) + beta * run_conv(y, wr, wi).astype(np.float64)
    tol = 1e-12 if dtype == np.float64 else 1e-4
    scale = np.linalg.norm(np.abs(alpha) * run_conv(x, wr, wi).astype(np.float64)) + np.linalg.norm(
        np.abs(beta) * run_conv(y, wr, wi).astype(np.float64)
    )  # cancellation-safe reference scale for alpha x + beta y
    assert np.linalg.norm(lhs - rhs) <= tol * max(scale, 1e-30)


def interpolate_128(field64: np.ndarray) -> np.ndarray:
    """Trigonometric interpolation 64 x 64 -> 128 x 128 by zero-padding the spectrum (band-limited fields only)."""
    spec = np.fft.rfft2(field64)  # [..., 64, 33]
    big = np.zeros((*field64.shape[:-2], 128, 65), dtype=complex)
    big[..., :32, :33] = spec[..., :32, :]
    big[..., 128 - 32 :, :33] = spec[..., 32:, :]
    return np.fft.irfft2(big * 4.0, s=(128, 128))  # (128 / 64)^2 keeps the amplitude of the interpolant


@pytest.mark.req("P-011-16")
@settings(max_examples=min(EXAMPLES, 60), deadline=None)
@given(seed=st.integers(0, 2**32 - 1))
def test_resolution_change_commutes_with_trigonometric_interpolation_for_band_limited_inputs(seed: int) -> None:
    r = rng_for(seed)
    spec = np.zeros((1, 2, 64, 33), dtype=complex)
    block = r.normal(size=(1, 2, 24, 12)) + 1j * r.normal(size=(1, 2, 24, 12))
    spec[:, :, rows_of(64), :M2] = block
    spec[..., 0, 0] = spec[..., 0, 0].real  # a real field has a real DC component
    x64 = np.fft.irfft2(spec, s=(64, 64))  # band-limited to the kept modes
    wr, wi = weights(seed + 4, 2, 3)
    y64 = run_conv(x64, wr, wi)
    x128 = interpolate_128(x64)
    y128_direct = run_conv(x128, wr, wi)  # the layer on the 128 x 128 grid, same weights
    y128_interp = interpolate_128(y64)
    assert rel(y128_direct - y128_interp, y128_interp) <= 1e-10


# ------------------------------------------------------------------ hostile inputs


@pytest.mark.req("FR-011-32")
@pytest.mark.parametrize(
    "shape",
    [(1, 2, 64, 32), (2, 64, 64), (1, 2, 8, 8)],
    ids=["non-square", "no-batch-axis", "smaller-than-kept-modes"],
)
def test_inputs_that_the_kept_modes_do_not_fit_are_rejected(shape: tuple[int, ...]) -> None:
    wr, wi = weights(5, 2, 2)
    x = np.zeros(shape)
    with pytest.raises((ValueError, RuntimeError)):
        spectral.spectral_conv2d(torch.from_numpy(x), torch.from_numpy(wr), torch.from_numpy(wi))


@pytest.mark.req("FR-011-32")
def test_a_complex_valued_input_is_rejected_because_the_layer_is_real_only() -> None:
    wr, wi = weights(6, 2, 2)
    x = torch.zeros(1, 2, 64, 64, dtype=torch.complex128)
    with pytest.raises((ValueError, RuntimeError, TypeError)):
        spectral.spectral_conv2d(x, torch.from_numpy(wr), torch.from_numpy(wi))


@pytest.mark.req("FR-011-32")
def test_weights_with_the_wrong_mode_shape_or_channel_count_are_rejected() -> None:
    x = torch.zeros(1, 2, 64, 64, dtype=torch.float64)
    bad_modes = torch.zeros(2, 2, 24, 11, dtype=torch.float64)
    bad_channels = torch.zeros(3, 2, 24, 12, dtype=torch.float64)
    ok = torch.zeros(2, 2, 24, 12, dtype=torch.float64)
    with pytest.raises((ValueError, RuntimeError)):
        spectral.spectral_conv2d(x, bad_modes, bad_modes)
    with pytest.raises((ValueError, RuntimeError)):
        spectral.spectral_conv2d(x, bad_channels, bad_channels)
    with pytest.raises((ValueError, RuntimeError)):
        spectral.spectral_conv2d(x, ok, bad_modes)
