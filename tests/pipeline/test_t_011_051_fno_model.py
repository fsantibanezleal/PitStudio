"""T-011-051 - FR-011-33 (and the FNO architecture of FR-011-32): tailings and dust models, channels, direct map.

Oracles (independent of the code under test; plan 011 test strategy FR-011-33):
- channel order and units from the DC-011-02 example corpus (`surrogate-io.valid-fno.json`: the tailings input and
    output
  channels) and from the DC-011-03 examples (`field-dataset.valid.json` and `valid-dust.json`);
- the normalisation formulas written in the DC-011-02 draft schema (description of `normalisation.rule`): standardise
  (x - mean) / std; log-standardise (ln x - mean) / std; patch-relief (x - patch mean) / patch relief. Hand numbers
      with the
  example statistics: release depth 2.0 m -> (2.0 - 0.42) / 1.1 = 1.436364; 0.0 m -> -0.381818; yield stress 150 Pa ->
  (150 - 105) / 55 = 0.818182; plastic viscosity 0.3 Pa.s -> (ln 0.3 + 1.5) / 0.8 = (-1.203973 + 1.5) / 0.8 =
      0.370034; density
  1900 kg/m^3 -> (1900 - 1800) / 115 = 0.869565; a bed of two levels 100 m and 110 m: patch mean 105, relief 10, so
      -0.5 / +0.5;
  wind from 225 deg: cos = sin = -sqrt(2) / 2 = -0.7071068;
- parameter count by hand (width 32, 4 Fourier layers, 24 x 12 kept modes): the spectral weights hold 2 x 32 x 32 x
    24 x 12 =
  589,824 numbers per layer, the pointwise maps 32 x 32 + 32 = 1,056 per layer, the lifting 32 C_in + 32 and the
      projection
  about 32 C_out + C_out: about 2.36 x 10^6 parameters (spec NFR-011-03: ~5 MB at fp16 = 2.5 x 10^6 x 2 bytes), accepted
  range [2.3 x 10^6, 2.6 x 10^6].

Expected public API (package under `pipeline/src/`):

  module `pitstudio_pipeline.surrogates.fno.model`
    TAILINGS_INPUT_CHANNELS, TAILINGS_OUTPUT_CHANNELS, DUST_INPUT_CHANNELS, DUST_OUTPUT_CHANNELS: tuples of channel
        names
    FnoModel(in_channels, out_channels, *, width=32, layers=4, modes=(12, 12))   (torch.nn.Module)
        attributes: width, n_layers, modes, in_channels, out_channels, lift (the pointwise lifting module),
        fourier_layers (ModuleList), layer_has_activation (list of bool: GELU after every layer but the last).
        forward(x [B, C_in, N, N]) -> [B, C_out, N, N]; a direct map: one call returns every output channel.
    build_tailings_model() -> FnoModel (5 -> 9 channels) ; build_dust_model() -> FnoModel (5 -> 1 channel)
  module `pitstudio_pipeline.surrogates.fno.inputs`
    build_fno_input(fields: dict, io: dict) -> np.ndarray [1, C_in, 64, 64] float32
        fields: channel name -> 2-D array [64, 64] or a scalar (a constant channel); io: a DC-011-02 document of an FNO;
        applies each input channel's normalisation rule (none, standardise, log-standardise, patch-relief) and
            stacks the
        channels in the order of io["inputs"][0]["channels"]. Raises
        `pitstudio_pipeline.surrogates.errors.InvalidFieldInputError` for a missing or extra channel, a shape other than
        [64, 64], a non-finite value, a zero patch relief, or a non-positive value under log-standardise.
    wind_direction_channels(direction_deg: float) -> tuple[float, float]   (cos, sin) of the direction angle in degrees
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.errors import InvalidFieldInputError  # noqa: E402
from pitstudio_pipeline.surrogates.fno import inputs, model  # noqa: E402

EX = ROOT / "specs" / "011-surrogates" / "contracts" / "examples"
IO = json.loads((EX / "surrogate-io.valid-fno.json").read_text(encoding="utf-8"))
TAIL_FIELD = json.loads((EX / "field-dataset.valid.json").read_text(encoding="utf-8"))
DUST_FIELD = json.loads((EX / "field-dataset.valid-dust.json").read_text(encoding="utf-8"))
N = 64


def names(doc: dict, role: str) -> tuple[str, ...]:
    return tuple(c["name"] for c in doc["channels"] if c["role"] == role)


def two_level_bed() -> np.ndarray:
    bed = np.full((N, N), 100.0)
    bed[:, N // 2 :] = 110.0
    return bed


def tailings_fields(**over) -> dict:
    release = np.zeros((N, N))
    release[31, 12] = 2.0
    fields = {
        "bed_elevation": two_level_bed(),
        "release_depth": release,
        "yield_stress": 150.0,
        "plastic_viscosity": 0.3,
        "density": 1900.0,
    }
    fields.update(over)
    return fields


# ------------------------------------------------------------------ FR-011-33 channels


@pytest.mark.req("FR-011-33")
def test_tailings_channels_follow_the_dc_011_02_order() -> None:
    io_in = tuple(c["name"] for c in IO["inputs"][0]["channels"])
    io_out = tuple(c["name"] for c in IO["outputs"][0]["channels"])
    assert io_in == model.TAILINGS_INPUT_CHANNELS
    assert io_out == model.TAILINGS_OUTPUT_CHANNELS
    assert (*tuple(f"depth_t{k}" for k in range(1, 9)), "depth_max") == model.TAILINGS_OUTPUT_CHANNELS
    assert names(TAIL_FIELD, "input") == model.TAILINGS_INPUT_CHANNELS
    assert names(TAIL_FIELD, "output") == model.TAILINGS_OUTPUT_CHANNELS


@pytest.mark.req("FR-011-33")
def test_dust_channels_follow_the_dc_011_03_order() -> None:
    assert names(DUST_FIELD, "input") == model.DUST_INPUT_CHANNELS
    assert names(DUST_FIELD, "output") == model.DUST_OUTPUT_CHANNELS
    assert model.DUST_INPUT_CHANNELS == (
        "bed_elevation",
        "source_strength",
        "wind_speed",
        "wind_dir_cos",
        "wind_dir_sin",
    )
    assert model.DUST_OUTPUT_CHANNELS == ("concentration_mean",)


@pytest.mark.req("FR-011-33")
def test_the_two_instances_have_their_own_input_and_output_widths() -> None:
    t, d = model.build_tailings_model(), model.build_dust_model()
    assert (t.in_channels, t.out_channels) == (5, 9)
    assert (d.in_channels, d.out_channels) == (5, 1)
    assert t is not d


@pytest.mark.req("FR-011-33")
def test_the_tailings_model_is_a_direct_map_to_eight_snapshots_and_the_maximum_in_one_call() -> None:
    t = model.build_tailings_model().eval()
    x = torch.zeros(1, 5, N, N)
    with torch.no_grad():
        y1 = t(x)
        y2 = t(x)
    assert tuple(y1.shape) == (1, 9, N, N)  # h(t_1) ... h(t_8) and h_max at once, no autoregression
    assert torch.equal(y1, y2)  # stateless: the output depends on the input alone
    assert not y1.is_complex()


# ------------------------------------------------------------------ FR-011-32 architecture counted by hand


@pytest.mark.req("FR-011-32")
def test_width_layers_modes_and_activations_match_the_spec() -> None:
    t = model.build_tailings_model()
    assert t.width == 32
    assert t.n_layers == 4
    assert tuple(t.modes) == (12, 12)
    assert len(t.fourier_layers) == 4
    assert list(t.layer_has_activation) == [True, True, True, False]  # GELU after every layer but the last


@pytest.mark.req("FR-011-32")
def test_parameter_count_equals_the_hand_calculation() -> None:
    t = model.build_tailings_model()
    total = sum(p.numel() for p in t.parameters())
    assert 2_300_000 <= total <= 2_600_000
    spectral = [p for p in t.parameters() if tuple(p.shape) == (32, 32, 24, 12)]
    assert len(spectral) == 8  # real and imaginary weights of 4 layers: 4 x 589,824 / 2 numbers each
    assert sum(p.numel() for p in spectral) == 4 * 589_824


@pytest.mark.req("FR-011-32")
def test_the_model_runs_without_complex_tensors_anywhere() -> None:
    t = model.FnoModel(5, 9, width=8, layers=2).eval()
    seen: list[torch.dtype] = []
    hooks = [
        m.register_forward_hook(lambda _m, _i, out: seen.append(out.dtype) if torch.is_tensor(out) else None)
        for m in t.modules()
    ]
    with torch.no_grad():
        t(torch.randn(1, 5, N, N))
    for h in hooks:
        h.remove()
    assert seen
    assert not any(dt.is_complex for dt in seen)
    assert not any(p.is_complex() for p in t.parameters())


@pytest.mark.req("FR-011-32")
def test_a_small_model_follows_the_requested_width_and_layers() -> None:
    t = model.FnoModel(3, 2, width=8, layers=2)
    assert (t.width, t.n_layers) == (8, 2)
    assert list(t.layer_has_activation) == [True, False]
    with torch.no_grad():
        assert tuple(t(torch.zeros(2, 3, N, N)).shape) == (2, 2, N, N)


# ------------------------------------------------------------------ FR-011-33 input normalisation by hand


@pytest.mark.req("FR-011-33")
def test_tailings_input_applies_the_dc_011_02_normalisation_rules_by_hand() -> None:
    x = inputs.build_fno_input(tailings_fields(), IO)
    assert x.shape == (1, 5, N, N)
    assert x.dtype == np.float32
    assert np.allclose(x[0, 0, :, : N // 2], -0.5, atol=1e-6)  # patch-relief: (100 - 105) / 10
    assert np.allclose(x[0, 0, :, N // 2 :], 0.5, atol=1e-6)
    assert x[0, 1, 31, 12] == pytest.approx((2.0 - 0.42) / 1.1, abs=1e-5)  # 1.436364
    assert x[0, 1, 0, 0] == pytest.approx((0.0 - 0.42) / 1.1, abs=1e-5)  # -0.381818
    assert np.allclose(x[0, 2], (150.0 - 105.0) / 55.0, atol=1e-6)  # constant channel, 0.818182
    assert np.allclose(x[0, 3], 0.370034, atol=1e-5)  # (ln 0.3 + 1.5) / 0.8
    assert np.allclose(x[0, 4], (1900.0 - 1800.0) / 115.0, atol=1e-6)  # 0.869565


@pytest.mark.req("FR-011-33")
def test_a_constant_channel_is_constant_over_the_whole_patch() -> None:
    x = inputs.build_fno_input(tailings_fields(yield_stress=37.0), IO)
    assert np.ptp(x[0, 2]) == 0.0
    assert x[0, 2, 5, 7] == pytest.approx((37.0 - 105.0) / 55.0, abs=1e-6)


@pytest.mark.req("FR-011-33")
def test_the_bed_channel_has_zero_mean_and_unit_relief_after_the_patch_relief_rule() -> None:
    rng = np.random.default_rng(3)
    bed = 1000.0 + rng.normal(0.0, 7.0, (N, N))
    x = inputs.build_fno_input(tailings_fields(bed_elevation=bed), IO)
    assert x[0, 0].mean() == pytest.approx(0.0, abs=1e-5)
    assert np.ptp(x[0, 0]) == pytest.approx(1.0, abs=1e-5)  # max - min = patch relief


@pytest.mark.req("FR-011-33")
def test_the_wind_direction_is_encoded_as_cosine_and_sine_of_the_angle() -> None:
    c, s = inputs.wind_direction_channels(225.0)
    assert c == pytest.approx(-np.sqrt(2.0) / 2.0, abs=1e-12)
    assert s == pytest.approx(-np.sqrt(2.0) / 2.0, abs=1e-12)
    assert inputs.wind_direction_channels(0.0) == pytest.approx((1.0, 0.0), abs=1e-12)
    assert inputs.wind_direction_channels(90.0) == pytest.approx((0.0, 1.0), abs=1e-12)


# ------------------------------------------------------------------ hostile builder inputs


def bad_cases() -> list[tuple[str, dict]]:
    flat = np.full((N, N), 120.0)
    nan_bed = two_level_bed()
    nan_bed[3, 3] = np.nan
    return [
        ("missing", {k: v for k, v in tailings_fields().items() if k != "density"}),
        ("extra", {**tailings_fields(), "wind_speed": 3.0}),
        ("wrong-shape", tailings_fields(bed_elevation=np.zeros((N, N + 1)))),
        ("nan-field", tailings_fields(bed_elevation=nan_bed)),
        ("nan-constant", tailings_fields(yield_stress=float("nan"))),
        ("inf-constant", tailings_fields(density=float("inf"))),
        ("flat-bed", tailings_fields(bed_elevation=flat)),
        ("log-of-zero", tailings_fields(plastic_viscosity=0.0)),
        ("log-of-negative", tailings_fields(plastic_viscosity=-0.2)),
    ]


@pytest.mark.req("FR-011-40")
@pytest.mark.parametrize(("label", "fields"), bad_cases(), ids=[c[0] for c in bad_cases()])
def test_hostile_field_dictionaries_raise_invalid_field_input_error(label: str, fields: dict) -> None:
    with pytest.raises(InvalidFieldInputError):
        inputs.build_fno_input(fields, IO)
