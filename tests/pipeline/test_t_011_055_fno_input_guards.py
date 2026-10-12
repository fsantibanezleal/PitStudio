"""T-011-055 - FR-011-40: hostile FNO inputs in Python (PyTorch and ONNX Runtime); the web engine is in
web/src/engines/fno/inputGuards.test.ts.

Oracles (independent of the code under test; plan 011 test strategy FR-011-40: "invalid inputs written in the
    test"): one input per class
of the requirement, built here by hand: a shape other than [1, C_in, 64, 64], a channel order that differs from the
    DC-011-02 description
(here the order of the example `surrogate-io.valid-fno.json`: bed_elevation, release_depth, yield_stress,
    plastic_viscosity, density), a
non-finite value, an unknown patch id. Every one must raise `InvalidFieldInputError` and return no field; a valid
    call made afterwards
must still succeed.

Expected public API (module `pitstudio_pipeline.surrogates.fno.infer`, package under `pipeline/src/`; error class
`pitstudio_pipeline.surrogates.errors.InvalidFieldInputError`):

    FnoPredictor(backend, io, known_patches)
        backend: a `FnoModel` (PyTorch) or a path (str or Path) to an exported ONNX file (ONNX Runtime, CPU provider);
        io: the DC-011-02 document of the model; known_patches: a collection of valid patch ids.
        __call__(x, *, channels, patch_id) -> np.ndarray [1, C_out, 64, 64] float32
            x: numpy float array; channels: the channel names of x in order; patch_id: str. Raises
                InvalidFieldInputError, with a message
            naming the offending argument (`x` shape, `channels`, `x` non-finite, `patch_id`), before any model
                evaluation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("onnxruntime")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.errors import InvalidFieldInputError  # noqa: E402
from pitstudio_pipeline.surrogates.fno import export, infer  # noqa: E402
from pitstudio_pipeline.surrogates.fno.model import FnoModel  # noqa: E402

EXAMPLE = json.loads(
    (ROOT / "specs" / "011-surrogates" / "contracts" / "examples" / "surrogate-io.valid-fno.json").read_text(
        encoding="utf-8"
    )
)
CHANNELS = [c["name"] for c in EXAMPLE["inputs"][0]["channels"]]
PATCHES = {"p00", "p07", "p63"}


@pytest.fixture(scope="module")
def predictors(tmp_path_factory):
    torch.manual_seed(0)
    model = FnoModel(5, 9, width=4, layers=1).eval()
    res = export.export_fno(
        model,
        tmp_path_factory.mktemp("fno_guard") / "m",
        model_id="fno-guard",
        inputs=EXAMPLE["inputs"][0]["channels"],
        outputs=EXAMPLE["outputs"][0]["channels"],
        envelope=EXAMPLE["training_envelope"],
    )
    return {
        "torch": infer.FnoPredictor(model, res.io["fp32"], PATCHES),
        "ort": infer.FnoPredictor(res.paths["fp32"], res.io["fp32"], PATCHES),
    }


def valid_x() -> np.ndarray:
    return np.random.default_rng(0).normal(size=(1, 5, 64, 64)).astype(np.float32)


def call(p, x=None, channels=None, patch_id="p07"):
    return p(valid_x() if x is None else x, channels=CHANNELS if channels is None else channels, patch_id=patch_id)


def poisoned(value: float, index=(0, 3, 10, 20)) -> np.ndarray:
    x = valid_x()
    x[index] = value
    return x


HOSTILE = [
    ("batch-2", {"x": np.zeros((2, 5, 64, 64), np.float32)}, "shape"),
    ("channels-4", {"x": np.zeros((1, 4, 64, 64), np.float32)}, "shape"),
    ("channels-6", {"x": np.zeros((1, 6, 64, 64), np.float32)}, "shape"),
    ("width-32", {"x": np.zeros((1, 5, 64, 32), np.float32)}, "shape"),
    ("grid-128", {"x": np.zeros((1, 5, 128, 128), np.float32)}, "shape"),
    ("no-batch-axis", {"x": np.zeros((5, 64, 64), np.float32)}, "shape"),
    ("extra-axis", {"x": np.zeros((1, 5, 64, 64, 1), np.float32)}, "shape"),
    ("empty", {"x": np.zeros((0, 5, 64, 64), np.float32)}, "shape"),
    ("scalar", {"x": np.float32(1.0)}, "shape"),
    ("swapped-channels", {"channels": [CHANNELS[1], CHANNELS[0], *CHANNELS[2:]]}, "channels"),
    ("reversed-channels", {"channels": CHANNELS[::-1]}, "channels"),
    ("missing-channel", {"channels": CHANNELS[:4]}, "channels"),
    ("extra-channel", {"channels": [*CHANNELS, "wind_speed"]}, "channels"),
    ("unknown-channel", {"channels": [*CHANNELS[:4], "pressure"]}, "channels"),
    ("upper-case-channel", {"channels": ["Bed_elevation", *CHANNELS[1:]]}, "channels"),
    ("no-channel-names", {"channels": []}, "channels"),
    ("nan", {"x": poisoned(np.nan)}, "finite"),
    ("inf", {"x": poisoned(np.inf)}, "finite"),
    ("minus-inf", {"x": poisoned(-np.inf, (0, 0, 0, 0))}, "finite"),
    ("unknown-patch", {"patch_id": "p99"}, "patch_id"),
    ("empty-patch", {"patch_id": ""}, "patch_id"),
    ("unicode-patch", {"patch_id": "pátch-ñ"}, "patch_id"),
    ("case-patch", {"patch_id": "P07"}, "patch_id"),
    ("none-patch", {"patch_id": None}, "patch_id"),
    ("injection-patch", {"patch_id": "p07; rm -rf /"}, "patch_id"),
]


@pytest.mark.req("FR-011-40")
@pytest.mark.parametrize("backend", ["torch", "ort"])
@pytest.mark.parametrize(("label", "kwargs", "needle"), HOSTILE, ids=[h[0] for h in HOSTILE])
def test_every_hostile_input_raises_invalid_field_input_error_naming_the_argument(
    predictors, backend: str, label: str, kwargs: dict, needle: str
) -> None:
    with pytest.raises(InvalidFieldInputError, match=needle):
        call(predictors[backend], **kwargs)


@pytest.mark.req("FR-011-40")
@pytest.mark.parametrize("backend", ["torch", "ort"])
def test_a_valid_call_returns_all_output_channels_and_a_failed_call_leaves_no_state(predictors, backend: str) -> None:
    with pytest.raises(InvalidFieldInputError):
        call(predictors[backend], x=poisoned(np.nan))
    out = call(predictors[backend])
    assert out.shape == (1, 9, 64, 64)
    assert out.dtype == np.float32
    assert np.isfinite(out).all()


@pytest.mark.req("FR-011-40")
def test_the_two_backends_agree_on_a_valid_field(predictors) -> None:
    a = call(predictors["torch"])
    b = call(predictors["ort"])
    assert np.allclose(a, b, rtol=1e-3, atol=1e-5)


@pytest.mark.req("FR-011-40")
@pytest.mark.parametrize("patch", sorted(PATCHES))
def test_every_known_patch_id_is_accepted(predictors, patch: str) -> None:
    assert call(predictors["torch"], patch_id=patch).shape == (1, 9, 64, 64)
