"""T-017-046: reconstruction route with fake COLMAP and Brush binaries; Umeyama; per-cell gridding (unit, studio env).

Requirements: FR-017-37, FR-017-38, P-017-16.

Spec: specs/017-planning-survey/spec.md
- FR-017-37: the reconstruction (`st58b_capture_splat`) runs COLMAP 4.2.1 feature extraction, matching and mapping,
  aligns
  the model to the true camera centres by a least-squares similarity transform (Umeyama), runs COLMAP dense stereo and
  fusion, and grids the fused points at 0.25 m by per-cell median elevation (empty cells left as no data) to give the
  photogrammetric surface;
- FR-017-38: Brush v0.3.0 trains a 3D Gaussian splat from the COLMAP output, and the Gaussian means with opacity >=
  0.5
  gridded at 0.25 m by per-cell median give the splat surface; the splat is a visual layer and its surface is
  reported,
  never used as ground truth;
- P-017-16: the Umeyama alignment recovers a known similarity transform from noise-free correspondences, and is
  unchanged
  by permuting the correspondences together (scale in [0.1, 10], random rotations and shifts, >= 3 non-collinear
  points,
  rtol 1e-9; condition number <= 1e5).
plan.md test strategy rows FR-017-37 / FR-017-38 (fake COLMAP / Brush binaries emitting known outputs; Umeyama on
known
transforms (P-017-16); per-cell median gridding by hand on a 2 x 2 grid). The GPU smoke on the real binaries is
tests/gpu/test_t_017_046_reconstruction_smoke.py.

Oracles:
- Umeyama (1991, "Least-squares estimation of transformation parameters between two point patterns", IEEE TPAMI
  13(4)):
  a known similarity (s, R, t) applied by the test to random points is recovered; optimality: the residual sum of
  squares of
  the returned transform on noisy correspondences is not larger than that of 200 random perturbations of it;
- the per-cell median on a 2 x 2 grid of 0.25 m cells by hand: cell (row 0, col 0) holds z = (1, 2, 10) -> 2; (0,
  1) holds
  (4, 6) -> 5 (mean of the two middle values); (1, 0) holds (7) -> 7; (1, 1) is empty -> NaN; a point outside the
  grid is
  ignored;
- the splat opacity: Gaussian-splat PLY files store opacity as a logit, so opacity >= 0.5 is logit >= 0 (sigmoid(0)
  = 0.5
  exactly): logits (0.0, -0.01, 2.0, -3.0) keep the first and the third;
- fake tools: Python scripts run through `sys.executable` that log their sub-command and write known outputs: a fake
  COLMAP whose "model" is the true scene under a hidden similarity (scale 2.5, a rotation, a shift), so that the
  aligned
  centres and the aligned fused points must equal the truth; a fake Brush that exports a splat PLY of known
  Gaussians. The
  COLMAP command line follows the COLMAP CLI documentation (`feature_extractor --database_path --image_path`,
  `exhaustive_matcher --database_path`, `mapper --database_path --image_path --output_path` (writes `<out>/0/` with
  the
  text model `images.txt`, or a binary model that `model_converter` converts), `image_undistorter --image_path
  --input_path --output_path`, `patch_match_stereo --workspace_path`, `stereo_fusion --workspace_path --output_path`;
  UNVERIFIED for 4.2.1); Brush is run as `<brush> <dataset_dir> --export-path <dir>` and exports `<dir>/*.ply`
  (UNVERIFIED for v0.3.0).

Expected public API:
module `pitstudio.survey.align` (root, numpy):
    @dataclass(frozen=True) SimilarityTransform: scale: float, rotation: np.ndarray (3, 3), translation: np.ndarray
    (3,);
        apply(points: np.ndarray (n, 3)) -> np.ndarray = scale * points @ rotation.T + translation
    umeyama(source: np.ndarray, target: np.ndarray) -> SimilarityTransform     # minimises sum |target - T(source)|^2
        ValueError for fewer than 3 points, mismatched shapes, non-finite values or (near-)collinear points
module `pitstudio.survey.grid` (root, numpy):
    grid_median(points: np.ndarray (n, 3), *, origin_xy: tuple[float, float], cell_m: float,
                shape: tuple[int, int]) -> np.ndarray       # (ny, nx), NaN where a cell has no point
    opaque_means(means: np.ndarray (n, 3), opacity_logit: np.ndarray (n,), *, min_opacity: float = 0.5) -> np.ndarray
module `pitstudio_studio.survey.colmap` (studio):
    reconstruct(images_dir: Path, workdir: Path, *, colmap: Sequence[str], true_centres: Mapping[str,
    Sequence[float]],
                origin_xy, cell_m: float, shape, env: Mapping[str, str] | None = None) -> Reconstruction
        runs the sub-commands in the order feature_extractor, a matcher (name ending "matcher"), mapper,
        [model_converter,]
        image_undistorter, patch_match_stereo, stereo_fusion; reads the registered image poses (text model: centre
        = -R^T t)
        and the fused PLY (binary little endian; x, y, z float32 first); aligns with `umeyama(model centres, true
        centres)` (matched by image name); Reconstruction: alignment (SimilarityTransform from the model frame to the
        world), centres (aligned model centres by name), points (aligned fused points), surface (grid_median of the
        aligned points), commands (the list of sub-commands run, in order), n_images_registered, n_images_total.
module `pitstudio_studio.survey.brush` (studio):
    train_splat(dataset_dir: Path, workdir: Path, *, brush: Sequence[str], alignment: SimilarityTransform, origin_xy,
                cell_m: float, shape, env=None) -> SplatResult
        runs `<brush> <dataset_dir> --export-path <workdir/export>`; reads the exported PLY (properties x, y, z and
        opacity as a logit), keeps the Gaussians with sigmoid(opacity) >= 0.5, aligns their means with `alignment`,
        grids
        them; SplatResult: surface, n_gaussians, n_opaque, ply_path, commands.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pitstudio.survey.align import SimilarityTransform, umeyama
from pitstudio.survey.grid import grid_median, opaque_means
from pitstudio_studio.survey.brush import train_splat
from pitstudio_studio.survey.colmap import reconstruct

# ----------------------------------------------------------------------------------------------------------------------
# helpers: random similarity transforms
# ----------------------------------------------------------------------------------------------------------------------


def _rotation(seed: int) -> np.ndarray:
    q, r = np.linalg.qr(np.random.default_rng(seed).standard_normal((3, 3)))
    q = q @ np.diag(np.sign(np.diag(r)))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    return q


def _points(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).uniform(-50.0, 50.0, (n, 3))


def _cost(points_src, points_dst, s, rot, t) -> float:
    return float(np.sum((points_dst - (s * points_src @ rot.T + t)) ** 2))


# ----------------------------------------------------------------------------------------------------------------------
# P-017-16
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("P-017-16")
@settings(max_examples=200, deadline=None)
@given(
    n=st.integers(4, 60),
    seed=st.integers(0, 2**32 - 1),
    scale=st.floats(0.1, 10.0),
    shift=st.tuples(st.floats(-1e3, 1e3), st.floats(-1e3, 1e3), st.floats(-1e3, 1e3)),
)
def test_umeyama_recovers_a_known_similarity_from_noise_free_correspondences(n, seed, scale, shift):
    src = _points(n, seed)
    centred = src - src.mean(axis=0)
    assume(np.linalg.cond(centred) <= 1e5)  # the generator's condition: non-degenerate point sets
    rot = _rotation(seed + 1)
    dst = scale * src @ rot.T + np.array(shift)
    got = umeyama(src, dst)
    assert isinstance(got, SimilarityTransform)
    assert got.scale == pytest.approx(scale, rel=1e-9)
    np.testing.assert_allclose(got.rotation, rot, rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(got.translation, shift, rtol=1e-9, atol=1e-6)
    np.testing.assert_allclose(got.apply(src), dst, rtol=1e-9, atol=1e-6)


@pytest.mark.req("P-017-16")
@settings(max_examples=200, deadline=None)
@given(n=st.integers(4, 40), seed=st.integers(0, 2**32 - 1), scale=st.floats(0.1, 10.0))
def test_permuting_the_correspondences_together_changes_nothing(n, seed, scale):
    src = _points(n, seed)
    assume(np.linalg.cond(src - src.mean(axis=0)) <= 1e5)
    dst = scale * src @ _rotation(seed + 3).T + np.array([5.0, -7.0, 2.0])
    perm = np.random.default_rng(seed + 9).permutation(n)
    a, b = umeyama(src, dst), umeyama(src[perm], dst[perm])
    assert a.scale == pytest.approx(b.scale, rel=1e-9)
    np.testing.assert_allclose(a.rotation, b.rotation, atol=1e-9)
    np.testing.assert_allclose(a.translation, b.translation, rtol=1e-9, atol=1e-8)


@pytest.mark.req("P-017-16")
@pytest.mark.parametrize("seed", range(5))
def test_the_least_squares_solution_is_not_beaten_by_random_perturbations_on_noisy_data(seed: int) -> None:
    rng = np.random.default_rng(seed)
    src = _points(30, seed)
    dst = 2.0 * src @ _rotation(seed).T + np.array([1.0, 2.0, 3.0]) + rng.normal(0, 0.3, (30, 3))
    got = umeyama(src, dst)
    best = _cost(src, dst, got.scale, got.rotation, got.translation)
    for _ in range(200):
        s = got.scale * (1 + rng.normal(0, 0.01))
        small = _rotation(int(rng.integers(0, 2**31)))
        rot = got.rotation @ (np.eye(3) + 0.01 * (small - np.eye(3)))
        u, _, vt = np.linalg.svd(rot)
        rot = u @ vt  # back onto the rotation group
        t = got.translation + rng.normal(0, 0.05, 3)
        assert best <= _cost(src, dst, s, rot, t) + 1e-9


@pytest.mark.req("P-017-16")
def test_degenerate_inputs_are_refused() -> None:
    p = _points(5, 0)
    with pytest.raises(ValueError, match=r"."):
        umeyama(p[:2], p[:2])  # fewer than 3 points
    with pytest.raises(ValueError, match=r"."):
        umeyama(p, p[:4])  # mismatched
    line = np.outer(np.arange(6.0), [1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match=r"."):
        umeyama(line, line * 2)  # collinear
    bad = p.copy()
    bad[1, 1] = np.nan
    with pytest.raises(ValueError, match=r"."):
        umeyama(bad, p)


# ----------------------------------------------------------------------------------------------------------------------
# gridding
# ----------------------------------------------------------------------------------------------------------------------

CELL = 0.25
TRUTH_POINTS = np.array(
    [
        [0.05, 0.05, 1.0], [0.10, 0.20, 2.0], [0.20, 0.10, 10.0],  # cell (row 0, col 0): median 2
        [0.30, 0.05, 4.0], [0.40, 0.20, 6.0],  # cell (0, 1): median 5
        [0.10, 0.30, 7.0],  # cell (1, 0): 7
        [5.0, 5.0, 99.0], [-1.0, 0.1, 99.0],  # outside the 2 x 2 grid: ignored
    ]
)  # fmt: skip
EXPECTED_GRID = np.array([[2.0, 5.0], [7.0, np.nan]])


@pytest.mark.req("FR-017-37")
def test_per_cell_median_on_a_2_x_2_grid_by_hand() -> None:
    z = grid_median(TRUTH_POINTS, origin_xy=(0.0, 0.0), cell_m=CELL, shape=(2, 2))
    assert z.shape == (2, 2)
    np.testing.assert_array_equal(z, EXPECTED_GRID)  # NaN == NaN under assert_array_equal


@pytest.mark.req("FR-017-37")
def test_a_point_exactly_on_a_cell_edge_belongs_to_the_cell_above_or_right_of_it() -> None:
    z = grid_median(np.array([[0.25, 0.0, 3.0]]), origin_xy=(0.0, 0.0), cell_m=CELL, shape=(2, 2))
    assert z[0, 1] == 3.0
    assert np.isnan(z[0, 0])


@pytest.mark.req("FR-017-37")
def test_the_median_ignores_outliers_unlike_the_mean() -> None:
    pts = np.array([[0.1, 0.1, 1.0], [0.1, 0.1, 1.2], [0.1, 0.1, 1.1], [0.1, 0.1, 1000.0]])
    z = grid_median(pts, origin_xy=(0.0, 0.0), cell_m=CELL, shape=(1, 1))
    assert z[0, 0] == pytest.approx(1.15)


@pytest.mark.req("FR-017-38")
def test_gaussians_with_opacity_at_least_one_half_are_kept_and_opacity_is_a_logit() -> None:
    means = np.array([[0.1, 0.1, 1.0], [0.2, 0.2, 2.0], [0.3, 0.3, 3.0], [0.4, 0.4, 4.0]])
    kept = opaque_means(means, np.array([0.0, -0.01, 2.0, -3.0]))
    np.testing.assert_array_equal(kept, means[[0, 2]])  # sigmoid(0) = 0.5 exactly is kept; sigmoid(-0.01) < 0.5 is not
    assert opaque_means(means, np.full(4, -5.0)).shape == (0, 3)


# ----------------------------------------------------------------------------------------------------------------------
# the fake tools
# ----------------------------------------------------------------------------------------------------------------------

FAKE_COLMAP = textwrap.dedent(
    """
    import json, os, struct, sys
    import numpy as np
    spec = json.load(open(os.environ["FAKE_TOOL_SPEC"]))
    sub = sys.argv[1]
    open(spec["log"], "a").write(sub + "\\n")
    if sub == "--version":
        print("COLMAP 4.2.1")
        sys.exit(0)
    args = dict(zip(sys.argv[2::2], sys.argv[3::2]))
    s, rot, t = spec["similarity"]["scale"], np.array(spec["similarity"]["R"]), np.array(spec["similarity"]["t"])
    to_model = lambda p: s * np.asarray(p) @ rot.T + t
    if sub in ("feature_extractor", "exhaustive_matcher", "sequential_matcher"):
        open(args["--database_path"], "ab").write(b"db")
    elif sub == "mapper":
        out = os.path.join(args["--output_path"], "0"); os.makedirs(out, exist_ok=True)
        lines = ["# Image list"]
        for i, im in enumerate(spec["images"], start=1):
            c = to_model(im["centre"])  # identity rotation: t = -c
            lines += [f"{i} 1 0 0 0 {float(-c[0])!r} {float(-c[1])!r} {float(-c[2])!r} 1 {im['name']}", ""]
        open(os.path.join(out, "images.txt"), "w").write("\\n".join(lines) + "\\n")
        open(os.path.join(out, "cameras.txt"), "w").write("1 PINHOLE 4000 3000 6000 6000 2000 1500\\n")
        open(os.path.join(out, "points3D.txt"), "w").write("")
    elif sub == "model_converter":
        pass
    elif sub in ("image_undistorter", "patch_match_stereo"):
        os.makedirs(args.get("--output_path", args.get("--workspace_path", ".")), exist_ok=True)
    elif sub == "stereo_fusion":
        pts = to_model(np.array(spec["points"], dtype=float)).astype("<f4")
        header = ("ply\\nformat binary_little_endian 1.0\\nelement vertex %d\\nproperty float x\\nproperty float y\\n"
                  "property float z\\nproperty float nx\\nproperty float ny\\nproperty float nz\\n"
                  "property uchar red\\nproperty uchar green\\nproperty uchar blue\\nend_header\\n" % len(pts))
        with open(args["--output_path"], "wb") as f:
            f.write(header.encode())
            for p in pts:
                f.write(struct.pack("<ffffffBBB", p[0], p[1], p[2], 0, 0, 1, 128, 128, 128))
    else:
        sys.exit(2)
    """
)

FAKE_BRUSH = textwrap.dedent(
    """
    import json, os, struct, sys
    import numpy as np
    spec = json.load(open(os.environ["FAKE_TOOL_SPEC"]))
    open(spec["log"], "a").write("brush\\n")
    if sys.argv[1] == "--version":
        print("brush 0.3.0")
        sys.exit(0)
    out = sys.argv[sys.argv.index("--export-path") + 1]
    os.makedirs(out, exist_ok=True)
    s, rot, t = spec["similarity"]["scale"], np.array(spec["similarity"]["R"]), np.array(spec["similarity"]["t"])
    g = np.array(spec["gaussians"], dtype=float)  # columns: x, y, z (world), opacity logit
    means = (s * g[:, :3] @ rot.T + t).astype("<f4")
    header = ("ply\\nformat binary_little_endian 1.0\\nelement vertex %d\\nproperty float x\\nproperty float y\\n"
              "property float z\\nproperty float opacity\\nproperty float scale_0\\nend_header\\n" % len(g))
    with open(os.path.join(out, "export_000.ply"), "wb") as f:
        f.write(header.encode())
        for m, op in zip(means, g[:, 3]):
            f.write(struct.pack("<ffff f", m[0], m[1], m[2], op, -3.0))
    """
)

SIMILARITY = {"scale": 2.5, "R": _rotation(5).tolist(), "t": [100.0, -40.0, 7.0]}
IMAGES = [
    {"name": f"img_{i:04d}.png", "centre": c}
    for i, c in enumerate(
        [
            [0.0, 0.0, 120.0],
            [80.0, 0.0, 120.0],
            [0.0, 60.0, 120.0],
            [80.0, 60.0, 120.0],
            [40.0, 30.0, 118.0],
            [20.0, 10.0, 121.0],
        ]
    )
]


def _tools(tmp_path: Path, **extra):
    colmap, brush = tmp_path / "fake_colmap.py", tmp_path / "fake_brush.py"
    colmap.write_text(FAKE_COLMAP, encoding="utf-8")
    brush.write_text(FAKE_BRUSH, encoding="utf-8")
    spec = {
        "log": str(tmp_path / "calls.log"),
        "similarity": SIMILARITY,
        "images": IMAGES,
        "points": TRUTH_POINTS.tolist(),
        "gaussians": [[0.05, 0.05, 1.0, 0.0], [0.10, 0.20, 3.0, 4.0], [0.30, 0.05, 5.0, -0.01], [0.30, 0.20, 9.0, 2.0]],
        **extra,
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    (tmp_path / "images").mkdir(exist_ok=True)
    env = {"FAKE_TOOL_SPEC": str(spec_path)}
    return [sys.executable, str(colmap)], [sys.executable, str(brush)], env, tmp_path / "calls.log"


def _reconstruct(tmp_path: Path):
    colmap, brush, env, log = _tools(tmp_path)
    rec = reconstruct(
        tmp_path / "images",
        tmp_path / "work",
        colmap=colmap,
        true_centres={im["name"]: im["centre"] for im in IMAGES},
        origin_xy=(0.0, 0.0),
        cell_m=CELL,
        shape=(2, 2),
        env=env,
    )
    return rec, brush, env, log


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-37
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-37")
def test_the_sub_commands_run_in_the_colmap_order(tmp_path: Path) -> None:
    rec, _, _, log = _reconstruct(tmp_path)
    ran = [c for c in log.read_text().split() if c != "--version"]
    assert ran == list(rec.commands)
    order = {
        name: [i for i, c in enumerate(ran) if c == name or (name == "matcher" and c.endswith("_matcher"))]
        for name in ("feature_extractor", "matcher", "mapper", "patch_match_stereo", "stereo_fusion")
    }
    assert all(order[name] for name in order), order
    assert max(order["feature_extractor"]) < min(order["matcher"]) < min(order["mapper"])
    assert max(order["mapper"]) < min(order["patch_match_stereo"]) < min(order["stereo_fusion"])


@pytest.mark.req("FR-017-37")
def test_the_model_is_aligned_to_the_true_camera_centres_by_a_similarity_and_the_fused_points_follow(
    tmp_path: Path,
) -> None:
    rec, *_ = _reconstruct(tmp_path)
    true_centres = np.array([im["centre"] for im in IMAGES])
    got = np.array([rec.centres[im["name"]] for im in IMAGES])
    np.testing.assert_allclose(got, true_centres, rtol=1e-9, atol=1e-6)
    # the recovered transform is the inverse of the hidden one: scale 1 / 2.5, rotation R^T
    assert rec.alignment.scale == pytest.approx(1 / 2.5, rel=1e-6)
    np.testing.assert_allclose(rec.alignment.rotation, np.array(SIMILARITY["R"]).T, atol=1e-6)
    np.testing.assert_allclose(rec.points, TRUTH_POINTS, rtol=1e-6, atol=1e-4)  # the fake stores float32 coordinates
    assert (rec.n_images_registered, rec.n_images_total) == (6, 6)


@pytest.mark.req("FR-017-37")
def test_the_photogrammetric_surface_is_the_per_cell_median_of_the_aligned_fused_points(tmp_path: Path) -> None:
    rec, *_ = _reconstruct(tmp_path)
    np.testing.assert_allclose(rec.surface, EXPECTED_GRID, atol=1e-3)  # empty cells stay NaN (no data)
    assert np.isnan(rec.surface[1, 1])


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-38
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-38")
def test_brush_is_run_on_the_colmap_output_and_the_opaque_gaussian_means_give_the_splat_surface(tmp_path: Path) -> None:
    rec, brush, env, log = _reconstruct(tmp_path)
    result = train_splat(
        tmp_path / "work",
        tmp_path / "splat",
        brush=brush,
        alignment=rec.alignment,
        origin_xy=(0.0, 0.0),
        cell_m=CELL,
        shape=(2, 2),
        env=env,
    )
    assert "brush" in log.read_text().split()
    assert (result.n_gaussians, result.n_opaque) == (4, 3)  # logits 0.0, 4.0 and 2.0 pass; -0.01 does not
    assert result.ply_path.suffix == ".ply"
    # kept Gaussians (world frame): (0.05, 0.05, 1) and (0.10, 0.20, 3) in cell (0, 0) -> median 2; (0.30, 0.20, 9)
    # in (0, 1) -> 9
    np.testing.assert_allclose(result.surface[0, 0], 2.0, atol=1e-3)
    np.testing.assert_allclose(result.surface[0, 1], 9.0, atol=1e-3)
    assert np.isnan(result.surface[1, 0])
    assert np.isnan(result.surface[1, 1])


@pytest.mark.req("FR-017-38")
def test_the_splat_surface_is_reported_and_never_replaces_the_photogrammetric_one(tmp_path: Path) -> None:
    rec, brush, env, _ = _reconstruct(tmp_path)
    result = train_splat(
        tmp_path / "work",
        tmp_path / "splat",
        brush=brush,
        alignment=rec.alignment,
        origin_xy=(0.0, 0.0),
        cell_m=CELL,
        shape=(2, 2),
        env=env,
    )
    assert not np.array_equal(result.surface, rec.surface, equal_nan=True)  # two surfaces, reported side by side
    np.testing.assert_allclose(
        rec.surface, EXPECTED_GRID, atol=1e-3
    )  # the COLMAP surface is untouched by the splat run
