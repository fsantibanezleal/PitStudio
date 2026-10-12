"""T-011-019 - FR-011-15: hostile GNS step inputs in Python (PyTorch and ONNX Runtime); the web engine is in
web/src/engines/gns/inputGuards.test.ts.

Oracles (independent of the code under test; plan 011 test strategy FR-011-15: "invalid inputs written in the
    test"): the list of
the requirement, one input per class, written here with hand-chosen values: N = 0, shapes other than those of FR-011-01
(positions [N, 2], velocities [N, 5, 2], particle type [N], bounds [4], neighbour index [N, 32], mask of the
    index's shape), a
neighbour index outside [0, N), an unknown particle type, a non-finite value. Every one must raise
    `InvalidGraphError` and return
no acceleration; a valid call made afterwards must still succeed (the failure leaves no state behind).

Expected public API:
  - `pitstudio_pipeline.surrogates.gns.model.GnsStep.forward(positions, velocities, particle_type, bounds,
      neighbour_index,
    neighbour_mask)` (torch tensors) raising `pitstudio.granular.errors.InvalidGraphError`; the message names the
        offending
    argument (`positions`, `velocities`, `particle_type`, `bounds`, `neighbour_index`, `neighbour_mask`);
  - `pitstudio_pipeline.surrogates.gns.infer.OrtGnsStep(onnx_path, *, n_particle_types: int)`; calling it with
      numpy arrays of the same
    six arguments returns the acceleration [N, 2] float32 (ONNX Runtime, CPU provider) and raises the same error,
        with the same
    messages, before the session is run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("onnxruntime")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.gns import export, infer  # noqa: E402
from pitstudio_pipeline.surrogates.gns.model import GnsStep  # noqa: E402

from pitstudio.granular.errors import InvalidGraphError  # noqa: E402
from pitstudio.granular.graph import build_radius_graph  # noqa: E402

D = 0.004
R = 2.5 * D
N_TYPES = 2
ENVELOPE = {"column_aspect_ratio": {"min": 0.5, "max": 4, "unit": "1"}}
NORM = {
    "velocities": {"mean": [0.0, 0.0], "std": [0.08, 0.09]},
    "acceleration": {"mean": [0.0, 0.0], "std": [3.1, 4.2]},
}
ARGS = ("positions", "velocities", "particle_type", "bounds", "neighbour_index", "neighbour_mask")


@pytest.fixture(scope="module")
def backends(tmp_path_factory):
    torch.manual_seed(1)
    model = GnsStep(connectivity_radius=R, frame_interval=0.01, n_particle_types=N_TYPES, latent=8, steps=1).eval()
    res = export.export_gns(
        model,
        tmp_path_factory.mktemp("guards") / "m",
        model_id="gns-guard",
        particle_diameter_m=D,
        envelope=ENVELOPE,
        normalisation=NORM,
    )

    def call_torch(**kw):
        with torch.no_grad():
            return model(*[torch.from_numpy(np.asarray(kw[k])) for k in ARGS]).numpy()

    session = infer.OrtGnsStep(res.paths["fp32"], n_particle_types=N_TYPES)

    def call_ort(**kw):
        return session(*[np.asarray(kw[k]) for k in ARGS])

    return {"torch": call_torch, "ort": call_ort}


def valid(n: int = 12) -> dict:
    rng = np.random.default_rng(0)
    pos = rng.uniform(0.0, 0.05, (n, 2)).astype(np.float32)
    g = build_radius_graph(pos, R)
    return {
        "positions": pos,
        "velocities": rng.normal(0, 0.05, (n, 5, 2)).astype(np.float32),
        "particle_type": rng.integers(0, N_TYPES, n).astype(np.int64),
        "bounds": np.array([0.0, 0.0, 0.05, 0.05], dtype=np.float32),
        "neighbour_index": g.neighbour_index.astype(np.int64),
        "neighbour_mask": g.neighbour_mask,
    }


def edit(**changes) -> dict:
    args = valid()
    args.update(changes)
    return args


def set_at(name: str, index: tuple, value) -> dict:
    args = valid()
    arr = np.array(args[name])
    arr[index] = value
    args[name] = arr
    return args


def empty() -> dict:
    return {
        "positions": np.zeros((0, 2), np.float32),
        "velocities": np.zeros((0, 5, 2), np.float32),
        "particle_type": np.zeros((0,), np.int64),
        "bounds": np.array([0.0, 0.0, 1.0, 1.0], np.float32),
        "neighbour_index": np.zeros((0, 32), np.int64),
        "neighbour_mask": np.zeros((0, 32), bool),
    }


N = 12
NAN, INF = np.nan, np.inf
HOSTILE = [
    ("n-zero", empty(), "positions"),
    ("positions-3-columns", edit(positions=np.zeros((N, 3), np.float32)), "positions"),
    ("positions-1d", edit(positions=np.zeros((N,), np.float32)), "positions"),
    ("velocities-4-steps", edit(velocities=np.zeros((N, 4, 2), np.float32)), "velocities"),
    ("velocities-3-components", edit(velocities=np.zeros((N, 5, 3), np.float32)), "velocities"),
    ("velocities-other-n", edit(velocities=np.zeros((N + 1, 5, 2), np.float32)), "velocities"),
    ("type-other-n", edit(particle_type=np.zeros((N + 1,), np.int64)), "particle_type"),
    ("type-2d", edit(particle_type=np.zeros((N, 1), np.int64)), "particle_type"),
    ("bounds-3", edit(bounds=np.zeros((3,), np.float32)), "bounds"),
    ("bounds-2x2", edit(bounds=np.zeros((2, 2), np.float32)), "bounds"),
    (
        "index-31",
        edit(neighbour_index=np.zeros((N, 31), np.int64), neighbour_mask=np.zeros((N, 31), bool)),
        "neighbour_index",
    ),
    (
        "index-33",
        edit(neighbour_index=np.zeros((N, 33), np.int64), neighbour_mask=np.zeros((N, 33), bool)),
        "neighbour_index",
    ),
    ("mask-other-shape", edit(neighbour_mask=np.zeros((N, 31), bool)), "neighbour_mask"),
    ("mask-other-n", edit(neighbour_mask=np.zeros((N + 1, 32), bool)), "neighbour_mask"),
    ("index-minus-one", set_at("neighbour_index", (0, 0), -1), "neighbour_index"),
    ("index-equals-n", set_at("neighbour_index", (3, 5), N), "neighbour_index"),
    ("index-far-beyond", set_at("neighbour_index", (7, 31), 2**40), "neighbour_index"),
    ("type-unknown", set_at("particle_type", (2,), N_TYPES), "particle_type"),
    ("type-negative", set_at("particle_type", (2,), -1), "particle_type"),
    ("position-nan", set_at("positions", (4, 1), NAN), "positions"),
    ("position-inf", set_at("positions", (4, 0), INF), "positions"),
    ("velocity-nan", set_at("velocities", (1, 2, 0), NAN), "velocities"),
    ("velocity-minus-inf", set_at("velocities", (1, 4, 1), -INF), "velocities"),
    ("bounds-nan", set_at("bounds", (2,), NAN), "bounds"),
    ("bounds-inf", set_at("bounds", (3,), INF), "bounds"),
]


@pytest.mark.req("FR-011-15")
@pytest.mark.parametrize("backend", ["torch", "ort"])
@pytest.mark.parametrize(("label", "args", "name"), HOSTILE, ids=[h[0] for h in HOSTILE])
def test_every_hostile_input_raises_invalid_graph_error_naming_the_argument(
    backends, backend: str, label: str, args: dict, name: str
) -> None:
    with pytest.raises(InvalidGraphError, match=name):
        backends[backend](**args)


@pytest.mark.req("FR-011-15")
@pytest.mark.parametrize("backend", ["torch", "ort"])
def test_a_valid_call_after_a_failed_one_still_returns_an_acceleration(backends, backend: str) -> None:
    with pytest.raises(InvalidGraphError):
        backends[backend](**set_at("positions", (0, 0), NAN))
    out = backends[backend](**valid())
    assert out.shape == (N, 2)
    assert np.isfinite(out).all()


@pytest.mark.req("FR-011-15")
def test_the_two_backends_agree_on_a_valid_input(backends) -> None:
    a = backends["torch"](**valid())
    b = backends["ort"](**valid())
    assert np.allclose(a, b, rtol=1e-3, atol=1e-5)


@pytest.mark.req("FR-011-15")
@pytest.mark.parametrize("backend", ["torch", "ort"])
def test_a_single_isolated_particle_with_an_all_false_mask_is_valid(backends, backend: str) -> None:
    args = {
        "positions": np.array([[0.01, 0.02]], np.float32),
        "velocities": np.zeros((1, 5, 2), np.float32),
        "particle_type": np.zeros((1,), np.int64),
        "bounds": np.array([0.0, 0.0, 0.05, 0.05], np.float32),
        "neighbour_index": np.zeros((1, 32), np.int64),
        "neighbour_mask": np.zeros((1, 32), bool),
    }
    assert backends[backend](**args).shape == (1, 2)
