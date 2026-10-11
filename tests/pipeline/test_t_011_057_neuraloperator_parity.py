"""T-011-057 - FR-011-43: optional `neuraloperator` spectral parity, or the card states that the numpy FFT
    reference is the only oracle.

Oracles (independent of the code under test):
- the wording fixed by plan 011 and FR-011-43: where `neuraloperator` 2.0.0 does not resolve in the `pipeline/`
    lock, "the card shall state that the
  numpy FFT reference is the only spectral oracle"; where it resolves, the spectral layer "shall also be checked
      against its spectral
  convolution with the same weights";
- the reference implementation itself: `neuralop` (the import name of `neuraloperator`), when it is installed,
    called directly by the
  parity helper on the same random weights and inputs; the numpy FFT reference of P-011-13 written in
      tests/property/test_t_011_050_dft_spectral.py
  stays the primary oracle either way.

Expected public API (package under `pipeline/src/`):

  module `pitstudio_pipeline.surrogates.fno.spectral`
    spectral_oracle_statement(*, neuraloperator_version: str | None) -> str
        the sentence for the model card: for None exactly the claim "the numpy FFT reference is the only spectral
            oracle" (case-insensitive match
        allowed on the first letter) and no mention that neuraloperator was used; for a version string a sentence
            that names
        "neuraloperator" and that version and says the layer was also checked against it (and never "only spectral
            oracle").
        Raises ValueError for an empty string or a string that is not a dotted version (digits and dots).
  module `pitstudio_pipeline.surrogates.fno.neuralop_oracle` (imports `neuralop` lazily; used only where it is
      installed)
    reference_conv(x, weight_re, weight_im, modes1=12, modes2=12) -> np.ndarray [B, C_out, N, N]
        the output of neuraloperator's spectral convolution loaded with the same weights (same kept modes, same
            real-field convention).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.fno import spectral  # noqa: E402


@pytest.mark.req("FR-011-43")
def test_without_neuraloperator_the_card_states_that_the_numpy_fft_reference_is_the_only_oracle() -> None:
    text = spectral.spectral_oracle_statement(neuraloperator_version=None)
    low = text.lower()
    assert "numpy fft reference is the only spectral oracle" in low
    assert "checked against neuraloperator" not in low


@pytest.mark.req("FR-011-43")
@pytest.mark.parametrize("version", ["2.0.0", "2.0.1", "2.1"])
def test_with_neuraloperator_the_card_names_it_and_its_version_and_drops_the_only_oracle_claim(version: str) -> None:
    text = spectral.spectral_oracle_statement(neuraloperator_version=version)
    low = text.lower()
    assert "neuraloperator" in low
    assert version in text
    assert "only spectral oracle" not in low
    assert "also" in low


@pytest.mark.req("FR-011-43")
@pytest.mark.parametrize("version", ["", " ", "two", "2.0.0; rm", "v2.0.0", "2..0", "NoneType"])
def test_a_malformed_version_is_refused(version: str) -> None:
    with pytest.raises(ValueError, match=r"."):
        spectral.spectral_oracle_statement(neuraloperator_version=version)


@pytest.mark.req("FR-011-43")
def test_the_statement_is_deterministic_and_single_line() -> None:
    a = spectral.spectral_oracle_statement(neuraloperator_version="2.0.0")
    assert a == spectral.spectral_oracle_statement(neuraloperator_version="2.0.0")
    assert "\n" not in a
    b = spectral.spectral_oracle_statement(neuraloperator_version=None)
    assert "\n" not in b
    assert a != b


@pytest.mark.req("FR-011-43")
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_the_layer_equals_neuraloperators_spectral_convolution_with_the_same_weights(seed: int) -> None:
    pytest.importorskip("neuralop")  # resolves only where `neuraloperator` 2.0.0 is in the pipeline/ lock (optional)
    from pitstudio_pipeline.surrogates.fno import neuralop_oracle

    rng = np.random.default_rng(seed)
    x = rng.normal(size=(2, 3, 64, 64)).astype(np.float32)
    wr = rng.normal(size=(3, 2, 24, 12)).astype(np.float32)
    wi = rng.normal(size=(3, 2, 24, 12)).astype(np.float32)
    ref = neuralop_oracle.reference_conv(x, wr, wi)
    with torch.no_grad():
        got = spectral.spectral_conv2d(torch.from_numpy(x), torch.from_numpy(wr), torch.from_numpy(wi)).numpy()
    assert np.linalg.norm(got - ref) <= 1e-4 * np.linalg.norm(ref)
