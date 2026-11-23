"""Planar reference-data generator: the funnel and the dump platform as boundary particles (T-011-014, FR-011-03).

Not locked. The grains of a pile or dump are held by a funnel (and, for a dump, by a platform and a crest face) that the
GNS only sees if the rollout records it. The generator records those solids as static particles of their own type
("boundary"), grains first, with their positions in every frame; the verification fails a funnel family whose rollouts
carry none. Sanchez-Gonzalez et al. 2020 (arXiv:2002.09405), Appendix B.2 and B.3: rigid obstacles are represented as
boundary particles, nodes of the graph with a type feature.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.physics.planar import engine, generate, packing, space, verify  # noqa: E402

D = space.D
CFG = space.SimConfig(1.0, 0.5)
PILE = {"x_p_D": 0.0, "z_o_D": 12.0, "w_o_D": 10.0, "n": 24}
DUMP = {"x_c_D": 0.0, "h_c_D": 9.0, "z_o_D": 12.0, "w_o_D": 10.0, "x_off_D": 6.0, "n": 24}


def _insts(family: str, p: dict, k: int = 1) -> list[dict]:
    tasks = [{"p": p, "seed": 1 + i, "geom_seed": 1 + i} for i in range(k)]
    return engine.feed_instances(family, tasks, CFG)


@pytest.mark.req("FR-011-03")
def test_011_a_pile_records_its_funnel_spheres_as_boundary_in_the_frame_of_the_instance() -> None:
    insts = _insts("pile-formation", PILE, 2)
    for it in insts:
        b = engine.instance_boundary("pile-formation", it)
        h = it["hopper"]
        assert b.dtype == np.float32
        assert b.shape == (h.n_walls, 2)
        assert np.allclose(b[:, 0], h.positions[: h.n_walls, 0], atol=1e-6)
        assert np.allclose(b[:, 1], h.positions[: h.n_walls, 2], atol=1e-6)
        # the instance frame: the hopper is centred on its own pour point, whatever the batch shift
        assert abs(b[:, 0].mean() - it["geo"]["x_center"]) < 0.5 * D


@pytest.mark.req("FR-011-03")
def test_011_a_dump_adds_its_platform_and_crest_face_inside_the_solid_and_never_those_of_another_instance() -> None:
    insts = _insts("dump-over-crest", DUMP, 2)
    first, second = (engine.instance_boundary("dump-over-crest", it) for it in insts)
    n_walls = [it["hopper"].n_walls for it in insts]
    # the same geometry twice (only the funnel top follows the random fill): stacking in z and shift do not leak in
    assert np.allclose(first[n_walls[0] :], second[n_walls[1] :], atol=1e-6)
    geo = insts[0]["geo"]
    hopper = insts[0]["hopper"]
    solid = first[hopper.n_walls :]
    assert len(solid) > 0
    assert (solid[:, 0] <= geo["crest"] - 0.5 * D + 1e-6).all()  # D/2 inside the solid: the plane is x = crest
    assert (solid[:, 1] <= geo["crest_z"] - 0.5 * D + 1e-6).all()  # and the platform top is z = crest height
    assert solid[:, 0].min() == pytest.approx(geo["lx0"], abs=1e-6)  # the platform reaches the left wall of the box
    top = solid[np.isclose(solid[:, 1], geo["crest_z"] - 0.5 * D)]
    assert np.diff(np.sort(top[:, 0])).max() <= packing.WALL_PITCH * D + 1e-6  # a closed row: no grain slips between
    face = solid[np.isclose(solid[:, 0], geo["crest"] - 0.5 * D)]
    assert face[:, 1].min() == pytest.approx(0.0, abs=1e-6)  # down to the floor
    assert np.diff(np.sort(face[:, 1])).max() <= packing.WALL_PITCH * D + 1e-6


@pytest.mark.req("FR-011-03")
def test_011_a_finished_feed_returns_its_grains_and_its_static_boundary_separately() -> None:
    (res,) = engine.simulate_feed(
        "pile-formation", [{"p": PILE, "seed": 1, "geom_seed": 1}], engine.NoPacer(), CFG, "cpu", t_cap=2.0
    )
    assert res["status"] == "rest"
    assert res["frames"].shape[1:] == (24, 2)  # grains only: every measurement of the generator reads grains
    assert res["boundary"].shape == (res["n_boundary"], 2)
    assert res["n_boundary"] > 0
    # the bounds of the rollout contain the funnel, so a reference state never lies outside its own box
    x0, z0, x1, z1 = res["bounds"]
    bx, bz = res["boundary"][:, 0], res["boundary"][:, 1]
    assert (bx >= x0).all()
    assert (bx <= x1).all()
    assert (bz >= z0).all()
    assert (bz <= z1).all()


def _result(n_boundary: int = 5) -> dict:
    t, n = 4, 3
    rng = np.random.default_rng(0)
    return {
        "status": "rest",
        "frames": rng.uniform(0.1, 0.2, (t, n, 2)).astype(np.float32),
        "frame_times": np.arange(t) * 0.1,
        "radii": np.full(n, 0.005, dtype=np.float32),
        "bounds": [0.0, 0.0, 1.0, 1.0],
        "boundary": np.column_stack([np.linspace(0.1, 0.5, n_boundary), np.full(n_boundary, 0.05)]).astype(np.float32)
        if n_boundary
        else None,
        "n_boundary": n_boundary,
    }


@pytest.mark.req("FR-011-03")
def test_011_the_payload_holds_grains_then_boundary_with_a_type_each_and_the_boundary_does_not_move(
    tmp_path: Path,
) -> None:
    import zarr

    res = _result()
    meta = generate.write_rollout(
        tmp_path,
        "r1",
        "pile-formation",
        "g1",
        PILE,
        space.geometry_record("pile-formation", PILE, 0.1),
        1,
        res,
        CFG,
        "v",
    )
    assert meta["particle_types"] == ["grain", "boundary"]
    assert meta["particle_count"] == 3 + 5
    g = zarr.open_group(str(tmp_path / meta["store"]["path"]), mode="r")
    pos, types, rad = np.asarray(g["positions"][:]), np.asarray(g["type_index"][:]), np.asarray(g["radius_m"][:])
    assert pos.shape == (4, 8, 2)
    assert types.tolist() == [0, 0, 0, 1, 1, 1, 1, 1]
    assert rad.shape == (8,)
    assert (pos[:, 3:] == pos[0, 3:]).all()  # static in every frame
    assert np.array_equal(pos[:, :3], res["frames"])


@pytest.mark.req("FR-011-03")
def test_011_a_collapse_without_boundary_keeps_one_particle_type(tmp_path: Path) -> None:
    res = _result(0)
    meta = generate.write_rollout(
        tmp_path,
        "r2",
        "column-collapse",
        "g2",
        PILE,
        space.geometry_record("column-collapse", {"a": 1.0, "L0_D": 40.0}),
        1,
        res,
        CFG,
        "v",
    )
    assert meta["particle_types"] == ["grain"]
    assert meta["particle_count"] == 3


def _write_with_boundary(tmp_path: Path, boundary: np.ndarray | None, moving: bool = False) -> tuple[Path, dict]:
    import zarr

    res = _result(0)
    n = res["frames"].shape[1]
    rng = np.random.default_rng(2)
    # a settled grain block: grains at rest on the floor, so the per-rollout checks of verify can run
    res["frames"] = np.repeat(rng.uniform(0.1, 0.2, (1, n, 2)).astype(np.float32), 40, axis=0)
    res["frame_times"] = np.arange(40) * 0.1
    res["boundary"] = boundary
    res["n_boundary"] = 0 if boundary is None else len(boundary)
    meta = generate.write_rollout(
        tmp_path,
        "r3",
        "pile-formation",
        "g3",
        PILE,
        space.geometry_record("pile-formation", PILE, 0.1),
        1,
        res,
        CFG,
        "v",
    )
    if moving:  # corrupt one boundary frame, then refresh the digest
        store = tmp_path / meta["store"]["path"]
        g = zarr.open_group(str(store), mode="r+")
        arr = np.asarray(g["positions"][:])
        arr[10, n] += 0.01
        g["positions"][:] = arr
        meta["store"]["sha256"] = generate.store_digest(store)
    (tmp_path / "meta").mkdir(exist_ok=True)
    (tmp_path / "meta" / "r3.json").write_text(json.dumps(meta), encoding="utf-8")
    return tmp_path, meta


@pytest.mark.req("FR-011-03")
def test_011_verification_fails_a_funnel_family_whose_rollout_has_no_boundary(tmp_path: Path) -> None:
    root, meta = _write_with_boundary(tmp_path, None)
    row = verify.check_rollout(root, meta, PILE)
    assert any("boundary particles missing" in p for p in row["problems"])
    assert row["boundary_particles"] == 0


@pytest.mark.req("FR-011-03")
def test_011_verification_reads_the_observables_on_grains_and_the_graph_on_everything(tmp_path: Path) -> None:
    boundary = np.column_stack([np.linspace(0.05, 0.9, 40), np.full(40, 0.9)]).astype(np.float32)
    root, meta = _write_with_boundary(tmp_path, boundary)
    row = verify.check_rollout(root, meta, PILE)
    assert row["boundary_particles"] == 40
    assert row["particles"] == 3 + 40  # the overflow of the radius graph is counted with the boundary particles
    assert not any("boundary" in p for p in row["problems"])
    assert row["pile_height_d"] < 40  # the funnel row at z = 0.9 m is not a pile of 90 d
    assert row["left_in_feed_fraction"] <= 1.0


@pytest.mark.req("FR-011-03")
def test_011_verification_fails_a_boundary_that_moves_or_leaves_its_box(tmp_path: Path) -> None:
    boundary = np.column_stack([np.linspace(0.05, 0.9, 10), np.full(10, 0.9)]).astype(np.float32)
    root, meta = _write_with_boundary(tmp_path, boundary, moving=True)
    assert any("boundary particles move" in p for p in verify.check_rollout(root, meta, PILE)["problems"])
    out = tmp_path / "other"
    out.mkdir()
    outside = boundary.copy()
    outside[:, 1] = 5.0
    root, meta = _write_with_boundary(out, outside)
    assert any("outside the bounds" in p for p in verify.check_rollout(root, meta, PILE)["problems"])
