"""Planar reference-data generator on the Warp CPU device (T-011-014, FR-011-03, FR-011-10): the engine and one feed end
to end.

Not locked, not a GPU test: the same kernels and batch functions the GPU jobs run, on a few dozen grains, so the planar
constraint, the frozen funnel, the flow-aware rest test and the batch bookkeeping are exercised before a queue job
exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.physics.planar import engine, space  # noqa: E402

D = space.D
CFG = space.SimConfig(1.0, 0.5)


@pytest.mark.req("FR-011-03")
def test_011_the_planar_constraint_keeps_y_and_the_x_z_spin_at_zero_and_frozen_spheres_in_place() -> None:
    from pitstudio_studio.physics.dem.step import Plane

    rng = np.random.default_rng(1)
    grains = np.column_stack([rng.uniform(-0.02, 0.02, 8), rng.uniform(-0.002, 0.002, 8), 0.03 + np.arange(8) * 0.012])
    wall = np.array([[0.05, 0.0, 0.01], [0.062, 0.0, 0.01]])
    pos = np.vstack([wall, grains])
    frozen = np.array([1, 1] + [0] * 8)
    ps = engine.PlanarSim(
        pos, np.full(len(pos), D / 2), frozen, [Plane((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))], CFG, device="cpu"
    )
    ps.advance(300)
    out = ps.sim.positions
    assert np.abs(out[:, 1]).max() == 0.0
    assert np.abs(ps.sim.angular_velocities[:, [0, 2]]).max() == 0.0
    assert np.abs(ps.sim.velocities[:, 1]).max() == 0.0
    assert np.array_equal(out[:2], wall)
    assert np.abs(ps.sim.velocities[:2]).max() == 0.0
    assert out[2:, 2].mean() < grains[:, 2].mean()  # the grains fell


def _tiny(**kw) -> dict:
    p = {"x_p_D": 0.0, "z_o_D": 12.0, "w_o_D": 10.0, "n": 24}
    p.update(kw)
    return p


@pytest.mark.req("FR-011-03")
def test_011_a_small_feed_drains_rests_and_records_only_its_grains() -> None:
    p = _tiny()
    (res,) = engine.simulate_feed(
        "pile-formation", [{"p": p, "seed": 1, "geom_seed": 1}], engine.NoPacer(), CFG, "cpu", t_cap=2.0
    )
    assert res["status"] == "rest"
    assert res["discharged_fraction"] > engine.DISCHARGED_MIN
    frames = res["frames"]
    assert frames.ndim == 3
    assert frames.shape[1:] == (24, 2)
    assert frames.dtype == np.float32  # grains only: the funnel is not recorded
    assert len(res["frame_times"]) == len(frames)
    assert res["frame_times"][0] == 0.0
    assert (np.diff(res["frame_times"]) > 0).all()
    assert np.isfinite(res["rate"])
    assert res["rate"] > 0.0
    assert res["radii"].shape == (24,)
    assert res["n"] == 24
    assert frames[-1][:, 1].max() < frames[0][:, 1].min()  # everything ended below where the fill started
    assert res["y_abs_max_m"] == 0.0
    assert res["mass_ok"]


@pytest.mark.req("FR-011-10")
def test_011_a_funnel_too_narrow_to_pass_a_grain_is_rejected_as_jammed_not_rested() -> None:
    p = _tiny(w_o_D=1.2)
    (res,) = engine.simulate_feed(
        "pile-formation", [{"p": p, "seed": 1, "geom_seed": 1}], engine.NoPacer(), CFG, "cpu", t_cap=2.0
    )
    assert res["status"] in ("jammed", "no-rest")
    assert res["discharged_fraction"] < 0.5
    assert "frames" not in res


@pytest.mark.req("FR-011-03")
def test_011_a_dump_feed_runs_over_a_crest_and_the_batch_keeps_its_instances_apart() -> None:
    q = {"x_c_D": 0.0, "h_c_D": 9.0, "z_o_D": 12.0, "w_o_D": 10.0, "x_off_D": 6.0, "n": 24}
    tasks = [{"p": q, "seed": 1, "geom_seed": 1}, {"p": q, "seed": 2, "geom_seed": 2}]
    res = engine.simulate_feed("dump-over-crest", tasks, engine.NoPacer(), CFG, "cpu", t_cap=2.0)
    assert len(res) == 2
    for r in res:
        assert r["status"] in ("rest", "no-rest", "jammed")
        if r["status"] == "rest":
            assert r["frames"].shape[1] == 24
            assert (
                np.abs(r["frames"][:, :, 0]).max() < space.BOX_HALF * D
            )  # local frame: each instance stays in its own domain
    geo = engine.feed_geometry("dump-over-crest", q)
    assert geo["z_orifice"] == pytest.approx((9.0 + 12.0) * D)
    assert geo["x_center"] == pytest.approx(-6.0 * D)
    assert geo["crest_z"] == pytest.approx(9.0 * D)


@pytest.mark.req("FR-011-03")
def test_011_a_collapse_batch_returns_one_valid_result_per_task() -> None:
    p = {"a": 1.0, "L0_D": 8.0, "n": 66}
    tasks = [{"p": p, "seed": 1, "geom_seed": 1}, {"p": p, "seed": 2, "geom_seed": 1}]
    res = engine.simulate_collapse(tasks, engine.NoPacer(), CFG, "cpu", t_cap=0.3, settle_cap=1.0)
    assert len(res) == 2
    assert all(r["status"] in ("rest", "no-rest", "no-settle", "underfilled", "non-finite") for r in res)
    walls = engine.collapse_walls([{"p": p, "X0": 0.0, "X1": 1.0, "shift": 0.0}], False)
    released = engine.collapse_walls([{"p": p, "X0": 0.0, "X1": 1.0, "shift": 0.0}], True)
    assert walls[2].point[0] == pytest.approx(8.0 * D)
    assert released[2].point[0] == pytest.approx(1.0)  # the retaining wall moves out on release


@pytest.mark.req("FR-011-03")
def test_011_no_wall_of_one_dump_instance_touches_the_grains_of_another() -> None:
    """The crest face is a plane that is infinite along x: without a vertical offset between the instances of a batch it
    pushes every instance to its left (the gns-v3 calibration saw the last instance rest and the others never
    finish)."""
    q = {"x_c_D": 0.0, "h_c_D": 22.0, "z_o_D": 100.0, "w_o_D": 18.0, "x_off_D": 14.0, "n": 24}
    tasks = [{"p": q, "seed": i, "geom_seed": i} for i in range(4)]
    insts = engine.feed_instances("dump-over-crest", tasks, CFG)
    assert [it["elev"] for it in insts] == sorted((it["elev"] for it in insts), reverse=True)
    xs = np.linspace(0.0, 1.0, 40)
    for k, it in enumerate(insts):
        pts_x = it["X0"] + xs * (it["X1"] - it["X0"])
        pts_z = it["elev"] + np.linspace(0.0, 4.0, 80)
        for j, other in enumerate(insts):
            if j == k:
                continue
            for plane in engine.instance_walls("dump-over-crest", other):
                n = np.array(plane.normal)
                for x in pts_x:
                    for z in pts_z:
                        if plane.tangent_range is not None:
                            axis, lo, hi = plane.tangent_range
                            if not lo <= (x, 0.0, z)[axis] <= hi:
                                continue
                        assert np.dot(np.array([x, 0.0, z]) - np.array(plane.point), n) > 0.0, (k, j, plane)


@pytest.mark.req("FR-011-03")
def test_011_recorded_dump_frames_are_in_the_local_frame_without_the_batch_elevation() -> None:
    q = {"x_c_D": 0.0, "h_c_D": 9.0, "z_o_D": 12.0, "w_o_D": 10.0, "x_off_D": 6.0, "n": 24}
    tasks = [{"p": q, "seed": 1, "geom_seed": 1}, {"p": q, "seed": 2, "geom_seed": 2}]
    res = engine.simulate_feed("dump-over-crest", tasks, engine.NoPacer(), CFG, "cpu", t_cap=2.0)
    for r in res:
        if r["status"] == "rest":
            assert r["frames"][:, :, 1].min() >= 0.0
            assert (
                r["frames"][0, :, 1].min() > (9.0 + 12.0) * D
            )  # the fill starts above the orifice of its own instance
            assert r["bounds"][3] < 2.0
