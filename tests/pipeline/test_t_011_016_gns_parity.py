"""T-011-016 - FR-011-08, SC-011-04, NFR-011-01: CPU fp32 parity of the GNS export and the fp16 rollout rule.

Oracles (independent of the code under test; plan 011 test strategy FR-011-08):
- ONNX Runtime CPU against PyTorch fp32 (reference implementation, spec SC-011-04) on the golden steps returned by
  `golden_steps`, recomputed here: tolerances read from `specs/000-foundation/thresholds.yaml`
      (`models.onnx_cpu_fp32`: rtol 1e-3,
  atol 1e-5, max abs 1e-4), the pass criterion |ort - torch| <= atol + rtol |torch| elementwise and max |ort -
      torch| <= max_abs;
- a perturbed graph that must be refused: one bias initializer of the exported file shifted by 0.05 (hand-made, far
    above the
  tolerances);
- the fp16 acceptance rule of FR-011-08 by hand (thresholds `models.surrogate_fp16_rollout_delta`: 0.5 deg and 1
    %): on every held-out
  geometry the fp16 rollout changes theta_r by <= 0.5 deg and L by <= 1 % relative to the fp32 rollout, else fp32
      is the live
  model; cases: all inside, one geometry at 0.51 deg, one at 1.01 %, values exactly on the limits (accepted), NaN
      (refused);
- NFR-011-01 by hand: 1.6 x 10^6 parameters x 2 bytes = 3.2 MB at fp16 (spec "about 3 MB"), x 4 bytes = 6.4 MB at
    fp32, both
  far below 25 x 10^6 bytes.

Expected public API (module `pitstudio_pipeline.surrogates.gns.parity`; export as in T-011-012):

    golden_steps(model, n: int = 200, *, seed: int = 0) -> list[dict]
        n deterministic GNS step inputs (dicts of numpy arrays keyed by the DC-011-02 input names), with particle
            counts that
        differ between steps (at least 3 distinct counts), valid graphs (indices inside [0, N), mask shape equal to
            the index shape).
    check_parity(model, onnx_path, *, n_golden: int = 200, seed: int = 0) -> ParityReport
        runs the ONNX file with ONNX Runtime (CPU provider) and `model` (PyTorch fp32) on the golden steps.
            Attributes: passed (bool),
        n_golden (int), max_abs (float), max_rel (float), tolerances (dict rtol, atol, max_abs from
            thresholds.yaml), worst_step (int).
        Raises ValueError when n_golden < 200.
    choose_live_precision(deltas: list[dict]) -> str
        deltas: one dict per held-out geometry {"geometry_id", "delta_repose_deg", "delta_runout_rel"} (absolute
            changes of the fp16
        rollout against the fp32 rollout); returns "fp16" iff the list is non-empty and every delta is finite and
            within the limits
        (inclusive), else "fp32".
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

torch = pytest.importorskip("torch")
onnx = pytest.importorskip("onnx")
ort = pytest.importorskip("onnxruntime")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.gns import export, parity  # noqa: E402
from pitstudio_pipeline.surrogates.gns.model import GnsStep  # noqa: E402

THRESHOLDS = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "models"
]
TOL = THRESHOLDS["onnx_cpu_fp32"]
FP16 = THRESHOLDS["surrogate_fp16_rollout_delta"]
ENVELOPE = {"column_aspect_ratio": {"min": 0.5, "max": 4, "unit": "1"}}
NORM = {
    "velocities": {"mean": [0.0, 0.0], "std": [0.08, 0.09]},
    "acceleration": {"mean": [0.0, 0.0], "std": [3.1, 4.2]},
}
D = 0.004
R = 2.5 * D
DT = 0.01


def make_model(latent: int = 16, steps: int = 2, seed: int = 0) -> GnsStep:
    torch.manual_seed(seed)
    model = GnsStep(connectivity_radius=R, frame_interval=DT, n_particle_types=1, latent=latent, steps=steps)
    with torch.no_grad():
        for p in model.parameters():
            p.normal_(0.0, 0.1)
    return model.eval()


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    model = make_model()
    out = tmp_path_factory.mktemp("parity") / "models"
    res = export.export_gns(
        model, out, model_id="gns-par", particle_diameter_m=D, envelope=ENVELOPE, normalisation=NORM
    )
    return model, res


def torch_step(model: GnsStep, feed: dict) -> np.ndarray:
    with torch.no_grad():
        args = [
            torch.from_numpy(np.asarray(feed[k]))
            for k in ("positions", "velocities", "particle_type", "bounds", "neighbour_index", "neighbour_mask")
        ]
        return model(*args).numpy()


# ------------------------------------------------------------------ golden steps


@pytest.mark.req("FR-011-08")
def test_the_golden_set_has_at_least_200_valid_reproducible_steps_of_varying_size() -> None:
    model = make_model()
    steps = parity.golden_steps(model, 200, seed=3)
    assert len(steps) == 200
    assert len({s["positions"].shape[0] for s in steps}) >= 3
    for s in steps:
        n = s["positions"].shape[0]
        assert s["velocities"].shape == (n, 5, 2)
        assert s["neighbour_index"].shape == (n, 32) == s["neighbour_mask"].shape
        assert s["neighbour_index"].min() >= 0
        assert s["neighbour_index"].max() < n
        assert np.isfinite(s["positions"]).all()
        assert np.isfinite(s["velocities"]).all()
    again = parity.golden_steps(model, 200, seed=3)
    assert all(np.array_equal(a["positions"], b["positions"]) for a, b in zip(steps, again, strict=True))
    other = parity.golden_steps(model, 200, seed=4)
    assert not all(
        np.array_equal(a["positions"], b["positions"])
        for a, b in zip(steps, other, strict=True)
        if a["positions"].shape == b["positions"].shape
    )


# ------------------------------------------------------------------ FR-011-08 / SC-011-04 parity


@pytest.mark.req("SC-011-04")
@pytest.mark.req("FR-011-08")
def test_ort_cpu_fp32_matches_pytorch_fp32_on_200_golden_steps(small) -> None:
    model, res = small
    report = parity.check_parity(model, res.paths["fp32"], n_golden=200, seed=0)
    assert report.passed is True
    assert report.n_golden == 200
    assert report.tolerances == {"rtol": TOL["rtol"], "atol": TOL["atol"], "max_abs": TOL["max_abs"]}
    assert report.max_abs <= TOL["max_abs"]
    # recompute independently on the same golden steps
    sess = ort.InferenceSession(str(res.paths["fp32"]), providers=["CPUExecutionProvider"])
    worst = 0.0
    for feed in parity.golden_steps(model, 200, seed=0):
        a = sess.run(None, {k: np.asarray(v) for k, v in feed.items()})[0]
        b = torch_step(model, feed)
        assert np.all(np.abs(a - b) <= TOL["atol"] + TOL["rtol"] * np.abs(b))
        worst = max(worst, float(np.abs(a - b).max()))
    assert report.max_abs == pytest.approx(worst, rel=1e-6, abs=1e-9)


@pytest.mark.req("SC-011-04")
def test_a_perturbed_graph_fails_the_parity_check(small, tmp_path: Path) -> None:
    model, res = small
    m = onnx.load(str(res.paths["fp32"]))
    for init in m.graph.initializer:
        if init.data_type == onnx.TensorProto.FLOAT and init.name.endswith("bias"):
            arr = onnx.numpy_helper.to_array(init).copy() + 0.05  # far above every tolerance
            init.CopyFrom(onnx.numpy_helper.from_array(arr, init.name))
            break
    else:
        pytest.fail("no float bias initializer found in the exported graph")
    bad = tmp_path / "perturbed.onnx"
    onnx.save(m, str(bad))
    report = parity.check_parity(model, bad, n_golden=200, seed=0)
    assert report.passed is False
    assert report.max_abs > TOL["max_abs"]


@pytest.mark.req("FR-011-08")
@pytest.mark.parametrize("n", [0, 1, 199, -5])
def test_fewer_than_200_golden_steps_are_refused(small, n: int) -> None:
    model, res = small
    with pytest.raises(ValueError, match="200"):
        parity.check_parity(model, res.paths["fp32"], n_golden=n)


@pytest.mark.req("FR-011-08")
def test_a_missing_or_corrupt_onnx_file_is_an_error_not_a_pass(small, tmp_path: Path) -> None:
    model, _ = small
    with pytest.raises(
        Exception, match=r"."
    ):  # the error type is the runtime's; what matters is that no report is returned
        parity.check_parity(model, tmp_path / "absent.onnx")
    junk = tmp_path / "junk.onnx"
    junk.write_bytes(b"not an onnx file")
    with pytest.raises(Exception, match=r"."):
        parity.check_parity(model, junk)


# ------------------------------------------------------------------ FR-011-08 fp16 rule


def deltas(*pairs: tuple[float, float]) -> list[dict]:
    return [{"geometry_id": f"g{i}", "delta_repose_deg": a, "delta_runout_rel": b} for i, (a, b) in enumerate(pairs)]


@pytest.mark.req("FR-011-08")
def test_the_thresholds_are_the_spec_values() -> None:
    assert FP16 == {"repose_deg": 0.5, "runout_rel": 0.01}


@pytest.mark.req("FR-011-08")
def test_fp16_is_accepted_only_when_every_geometry_is_inside_both_limits() -> None:
    inside = deltas(*[(0.1 * (i % 5), 0.002 * (i % 5)) for i in range(20)])
    assert parity.choose_live_precision(inside) == "fp16"


@pytest.mark.req("FR-011-08")
@pytest.mark.parametrize(
    "worst",
    [(0.51, 0.0), (0.0, 0.0101), (0.6, 0.02), (5.0, 0.0), (0.0, 0.5)],
    ids=["repose-0.51", "runout-1.01pct", "both", "repose-huge", "runout-huge"],
)
def test_one_geometry_over_a_limit_keeps_fp32_live(worst: tuple[float, float]) -> None:
    pairs = [(0.1, 0.002)] * 19 + [worst]
    assert parity.choose_live_precision(deltas(*pairs)) == "fp32"


@pytest.mark.req("FR-011-08")
def test_values_exactly_on_the_limits_are_accepted() -> None:
    assert parity.choose_live_precision(deltas((0.5, 0.01), (0.0, 0.0))) == "fp16"


@pytest.mark.req("FR-011-08")
@pytest.mark.parametrize(
    "bad",
    [(float("nan"), 0.0), (0.0, float("nan")), (float("inf"), 0.0), (-0.1, 0.0)],
    ids=["nan-repose", "nan-runout", "inf", "negative"],
)
def test_non_finite_or_negative_deltas_never_accept_fp16(bad: tuple[float, float]) -> None:
    assert parity.choose_live_precision(deltas((0.1, 0.001), bad)) == "fp32"


@pytest.mark.req("FR-011-08")
def test_no_evidence_means_fp32() -> None:
    assert parity.choose_live_precision([]) == "fp32"


# ------------------------------------------------------------------ NFR-011-01 size of the full-size export


@pytest.mark.req("NFR-011-01")
@pytest.mark.slow
def test_the_full_size_live_graphs_are_far_below_25_megabytes_and_fp16_is_about_3_megabytes(tmp_path: Path) -> None:
    model = make_model(latent=128, steps=10)
    res = export.export_gns(
        model, tmp_path / "full", model_id="gns-full", particle_diameter_m=D, envelope=ENVELOPE, normalisation=NORM
    )
    fp16 = res.paths["fp16"].stat().st_size
    fp32 = res.paths["fp32"].stat().st_size
    assert fp16 <= 25_000_000
    assert fp32 <= 25_000_000
    assert 2_500_000 <= fp16 <= 4_500_000  # 1.6e6 parameters x 2 bytes = 3.2 MB (about 3 MB)
    assert 5_000_000 <= fp32 <= 8_500_000  # x 4 bytes = 6.4 MB
    assert res.io["fp16"]["onnx"]["bytes"] == fp16
