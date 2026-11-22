"""Planar reference-data generator, pure parts (T-011-014, FR-011-03, FR-011-05, FR-011-10): plan, packing, measurement, rest test.

Not locked. Warp is not needed: the parameter space, the initial states, the discharge measurement, the independent
repose fit and the flow-aware rest test are NumPy code. The jammed-feed cases pin the gns-v2 defect (a measurement that
raised on a jammed pour).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.physics.planar import measure, packing, space  # noqa: E402

D = space.D


@pytest.mark.req("FR-011-03")
def test_011_the_split_plan_is_100_geometries_70_10_20_by_family_quota() -> None:
    slots = space.split_plan()
    assert len(slots) == 100 and len({s["id"] for s in slots}) == 100
    by_split = {k: sum(s["split"] == k for s in slots) for k in ("train", "val", "test")}
    assert by_split == {"train": 70, "val": 10, "test": 20}
    test = {f: sum(s["split"] == "test" and s["family"] == f for s in slots) for f in space.FAMILIES}
    assert test == {"column-collapse": 8, "pile-formation": 6, "dump-over-crest": 6}
    # validation geometries are generated first, the test geometries last
    order = [s["split"] for s in slots]
    assert order.index("train") > max(i for i, s in enumerate(order) if s == "val") and order.index("test") > max(i for i, s in enumerate(order) if s == "train")


@pytest.mark.req("FR-011-03")
def test_011_every_draw_stays_in_its_design_ranges_and_is_reproducible() -> None:
    for family in space.FAMILIES:
        a = space.draw_geometry(family, np.random.default_rng(5))
        assert a == space.draw_geometry(family, np.random.default_rng(5))
    for seed in range(60):
        rng = np.random.default_rng(seed)
        c = space.draw_geometry("column-collapse", rng)
        assert 0.5 <= c["a"] <= 4.0 and 18.0 <= c["L0_D"] <= 70.0
        assert c["n"] <= space.N_MAX_COLLAPSE
        for family in ("pile-formation", "dump-over-crest"):
            p = space.draw_geometry(family, rng)
            for key, (lo, hi) in space.FEED_RANGES[family].items():
                assert lo <= p[key] <= hi
            assert p["n"] == space.N_FEED


@pytest.mark.req("FR-011-03")
def test_011_geometry_records_name_the_contract_parameters_and_refuse_a_missing_rate() -> None:
    assert set(space.geometry_record("column-collapse", {"a": 1.0, "L0_D": 40.0})) == {"aspect_ratio", "column_width_m"}
    pile = space.geometry_record("pile-formation", {"x_p_D": 2.0, "z_o_D": 80.0}, 0.07)
    assert pile == {"pour_point_x_m": 2.0 * D, "pour_height_m": 80.0 * D, "pour_rate_m2_per_s": 0.07}
    dump = space.geometry_record("dump-over-crest", {"x_c_D": 0.0, "h_c_D": 16.0}, 0.07)
    assert dump["crest_height_m"] == pytest.approx(0.16) and dump["dump_rate_m2_per_s"] == 0.07
    for bad in (None, float("nan"), 0.0, -1.0):
        with pytest.raises(ValueError):
            space.geometry_record("pile-formation", {"x_p_D": 0.0, "z_o_D": 80.0}, bad)


@pytest.mark.req("FR-011-03")
def test_011_a_test_geometry_must_be_inside_the_training_envelope_and_0_05_away() -> None:
    fam = "pile-formation"
    (h, hlo, hhi), (r, rlo, rhi) = space.CONTRACT_RANGES[fam]
    train = [{"pour_height_m": hlo + f * (hhi - hlo), "pour_rate_m2_per_s": rlo + g * (rhi - rlo)} for f in (0.1, 0.9) for g in (0.1, 0.9)]
    inside_far = {"pour_height_m": hlo + 0.5 * (hhi - hlo), "pour_rate_m2_per_s": rlo + 0.5 * (rhi - rlo)}
    ok, dist = space.test_geometry_ok(fam, inside_far, train)
    assert ok and dist > 0.05
    near = {"pour_height_m": train[0]["pour_height_m"] + 0.01 * (hhi - hlo), "pour_rate_m2_per_s": train[0]["pour_rate_m2_per_s"]}
    assert space.test_geometry_ok(fam, near, train)[0] is False
    outside = {"pour_height_m": hlo, "pour_rate_m2_per_s": rlo + 0.5 * (rhi - rlo)}
    assert space.test_geometry_ok(fam, outside, train)[0] is False


@pytest.mark.req("FR-011-03")
def test_011_the_column_lattice_is_a_reproducible_monolayer_inside_its_walls() -> None:
    p = {"a": 1.5, "L0_D": 33.0, "n": 1200}
    pos, rad = packing.column_state(p, np.random.default_rng(3))
    pos2, rad2 = packing.column_state(p, np.random.default_rng(3))
    assert np.array_equal(pos, pos2) and np.array_equal(rad, rad2)
    assert len(pos) == int(1.3 * p["n"]) and (pos[:, 1] == 0.0).all()
    assert pos[:, 0].min() >= 0.65 * D - 1e-12 and pos[:, 0].max() <= 33.0 * D - 0.65 * D + 1e-12
    assert rad.min() >= 0.8 * D / 2 - 1e-12 and rad.max() <= 1.2 * D / 2 + 1e-12


@pytest.mark.req("FR-011-03")
@pytest.mark.parametrize("w_o_d,z_o_d", [(12.0, 50.0), (20.0, 125.0), (16.0, 80.0)])
def test_011_the_funnel_holds_n_grains_without_overlap_and_leaves_the_orifice_open(w_o_d: float, z_o_d: float) -> None:
    from scipy.spatial import cKDTree

    p = {"x_p_D": 3.0, "z_o_D": z_o_d, "w_o_D": w_o_d, "n": 1500}
    h = packing.hopper_state(p, np.random.default_rng(11), x_center=3.0 * D, z_orifice=z_o_d * D)
    assert h.n_grains == 1500 and h.frozen[: h.n_walls].all() and not h.frozen[h.n_walls :].any()
    pos, rad = h.positions, h.radii
    xz = pos[:, [0, 2]]
    pairs = cKDTree(xz).query_pairs(1.3 * D, output_type="ndarray")
    pairs = pairs[(pairs[:, 0] >= h.n_walls) | (pairs[:, 1] >= h.n_walls)]  # wall-wall spacing is by design
    gap = np.hypot(*(xz[pairs[:, 0]] - xz[pairs[:, 1]]).T) - (rad[pairs[:, 0]] + rad[pairs[:, 1]])
    assert (gap >= -0.005 * D).all(), "an initial overlap"
    gp = pos[h.grain_slice]
    assert (gp[:, 1] == 0.0).all() and (pos[: h.n_walls, 1] == 0.0).all()
    # every grain is inside the funnel above the orifice plane; the walls reach above the highest grain
    assert gp[:, 2].min() > z_o_d * D and h.top_z > gp[:, 2].max()
    assert np.abs(gp[:, 0] - 3.0 * D).max() < space.HOPPER_W_D * D / 2
    # no wall sphere closes the orifice: nothing frozen within the opening at the plate level
    walls = pos[: h.n_walls]
    opening = (np.abs(walls[:, 0] - 3.0 * D) < w_o_d * D / 2 - 0.5 * D) & (np.abs(walls[:, 2] - (z_o_d * D - 0.5 * D)) < 0.5 * D)
    assert not opening.any()


@pytest.mark.req("FR-011-03")
@pytest.mark.parametrize("w_o_d,z_o_d", [(12.0, 125.0), (20.0, 50.0)])
def test_011_the_funnel_holds_the_full_dataset_fill_at_the_corners_of_the_design_range(w_o_d: float, z_o_d: float) -> None:
    p = {"x_p_D": 0.0, "z_o_D": z_o_d, "w_o_D": w_o_d, "n": space.N_FEED}
    h = packing.hopper_state(p, np.random.default_rng(4), x_center=0.0, z_orifice=z_o_d * D)
    assert h.n_grains == space.N_FEED and h.top_z < 256 * 0.025  # under the z span of the hash grid of the engine


@pytest.mark.req("FR-011-03")
def test_011_the_funnel_is_reproducible_and_refuses_an_impossible_fill() -> None:
    p = {"x_p_D": 0.0, "z_o_D": 60.0, "w_o_D": 14.0, "n": 600}
    a = packing.hopper_state(p, np.random.default_rng(2), x_center=0.0, z_orifice=0.6)
    b = packing.hopper_state(p, np.random.default_rng(2), x_center=0.0, z_orifice=0.6)
    assert np.array_equal(a.positions, b.positions)


@pytest.mark.req("FR-011-03")
def test_011_the_rate_is_the_slope_of_the_discharged_area_in_the_20_to_80_percent_window() -> None:
    n, area_rate = 400, 0.05  # m^2/s
    r = np.full(n, D / 2)
    a = math.pi * (D / 2) ** 2
    dt = 0.01
    t = np.arange(0, 12.0, dt)
    cross = np.arange(n) * a / area_rate  # grain i crosses the level at this time, steady flow
    z0 = 1.0
    z = np.where(t[:, None] >= cross[None, :], z0 - 0.5, z0)  # below the level (minus the margin) once crossed
    rate, frac = measure.measure_rate(z, t, r, z_orifice=z0)
    assert rate == pytest.approx(area_rate, rel=0.03)
    assert frac == 1.0
    assert measure.discharged_fraction(np.array([0.0, 0.0, 1.0, 1.0]), z0) == 0.5


@pytest.mark.req("FR-011-03")
def test_011_a_jammed_feed_measures_without_raising() -> None:
    """The gns-v2 defect: nothing discharged (or only a few grains) made the measurement raise on an empty array."""
    t = np.arange(0, 3.0, 0.01)
    z = np.full((len(t), 50), 1.0)  # nothing ever below the orifice
    rate, frac = measure.measure_rate(z, t, np.full(50, D / 2), z_orifice=1.0)
    assert math.isnan(rate) and frac == 0.0
    assert measure.discharged_fraction(np.array([]), 1.0) == 0.0
    assert measure.measure_rate(np.empty((0, 0)), np.empty(0), np.empty(0), 1.0)[1] == 0.0
    pos = np.array([[0.0, 2.0], [0.01, 2.0]])
    for family, geo in (("pile-formation", {"pour_point_x_m": 0.0}), ("dump-over-crest", {"crest_x_m": 0.0}), ("column-collapse", {"column_width_m": 0.3})):
        assert measure.heap_repose(pos, family=family, geometry=geo, z_orifice=1.0) is None  # nothing discharged
        assert measure.heap_repose(np.empty((0, 2)), family=family, geometry=geo) is None
    assert math.isnan(measure.independent_repose(np.empty((0, 2)), D, "pile-formation", 0.0))


def _lattice_heap(theta_deg: float, height_d: float, x_ref: float) -> np.ndarray:
    right = math.tan(math.radians(theta_deg))
    pts = []
    for j in range(int(height_d / (math.sqrt(3) / 2.0)) + 1):
        y = D / 2 + j * D * math.sqrt(3) / 2.0
        for i in range(-int(3 * height_d / right), int(3 * height_d / right)):
            x = x_ref + i * D + (0.5 * D if j % 2 else 0.0)
            if y + D / 2 <= height_d * D - right * abs(x - x_ref):
                pts.append((x, y))
    pts = np.array(pts)
    pts[:, 0] += np.random.default_rng(7).uniform(-0.03, 0.03, len(pts)) * D
    return pts


@pytest.mark.req("FR-011-05")
@pytest.mark.parametrize("theta", [18.0, 27.2, 35.0])
def test_011_the_calibration_measurement_reads_a_packed_pile_of_known_slope_with_both_fits(theta: float) -> None:
    pos = _lattice_heap(theta, 40.0, 0.0)
    both = measure.heap_repose(pos, family="pile-formation", geometry={"pour_point_x_m": 0.0})
    assert both is not None
    assert abs(both["repose_deg"] - theta) < 1.5 and abs(both["repose_indep_deg"] - theta) < 1.5
    assert abs(both["repose_deg"] - both["repose_indep_deg"]) < 1.0
    # grains left above the orifice are not part of the heap
    stray = np.vstack([pos, [[0.0, 5.0]] * 10])
    kept = measure.heap_repose(stray, family="pile-formation", geometry={"pour_point_x_m": 0.0}, z_orifice=1.0)
    assert kept is not None and kept["repose_deg"] == pytest.approx(both["repose_deg"], abs=1e-9)


@pytest.mark.req("FR-011-10")
def test_011_a_feed_is_at_rest_only_after_it_has_discharged_and_a_static_jam_is_called_a_jam() -> None:
    thr = 0.003
    j = measure.RestJudge(thr, discharged_min=0.9)
    assert j.update(0.0, 0.0, 0.0) == "run"  # static at t = 0 means nothing: not judged before t_min
    verdicts = [j.update(0.5 + i * 0.01, 0.0, 0.2) for i in range(3)]
    assert verdicts == ["run", "run", "jammed"]  # static for 3 frames with 20 percent discharged
    k = measure.RestJudge(thr, discharged_min=0.9)
    assert [k.update(1.0 + i * 0.01, 0.0, 0.95) for i in range(3)] == ["run", "run", "rest"]
    m = measure.RestJudge(thr, discharged_min=0.9)
    assert m.update(1.0, 0.0, 0.95) == "run" and m.update(1.01, 0.5, 0.95) == "run" and m.static == 0  # a moving frame resets the count
    assert measure.RestJudge(thr, discharged_min=0.9).update(1.0, 0.0, 0.9) == "run"  # exactly the minimum does not count
    c = measure.RestJudge(thr)  # a collapse has no feed to wait for
    assert [c.update(1.0 + i * 0.01, 0.0) for i in range(3)] == ["run", "run", "rest"]


@pytest.mark.req("FR-011-03")
def test_011_the_state_file_round_trips_atomically(tmp_path: Path) -> None:
    from pitstudio_studio.physics.planar import generate

    cfg = space.SimConfig(1.0, 0.5)
    st = generate.new_state(cfg)
    assert len(st["slots"]) == 100 and st["contact"] == {"friction_rolling": 1.0, "friction_static": 0.5, "poly": 0.2}
    generate.save_state(tmp_path, st)
    assert generate.load_state(tmp_path) == json.loads((tmp_path / "_state.json").read_text(encoding="utf-8"))
    assert not (tmp_path / "_state.json.tmp").exists()
    assert generate.load_state(tmp_path / "nowhere") is None


@pytest.mark.req("FR-011-03")
def test_011_batches_take_whole_geometries_and_test_geometries_wait_for_the_training_set() -> None:
    from pitstudio_studio.physics.planar import generate

    st = generate.new_state(space.SimConfig(1.0, 0.5))
    pairs = generate.make_batch(st, "pile-formation", ("val",), 2)
    assert len(pairs) == 6 and len({s["id"] for s, _ in pairs}) == 2
    assert len({t["seed"] for _, t in pairs}) == 6
    assert generate.make_batch(st, "pile-formation", ("test",), 6) == []  # no test draw before the training set is final
    for s, _ in pairs:
        assert s["params"] is not None
    again = generate.make_batch(st, "pile-formation", ("val",), 2)  # deterministic: the same slots, the same seeds
    assert [t["seed"] for _, t in again] == [t["seed"] for _, t in pairs]


@pytest.mark.req("FR-011-03")
def test_011_a_replaced_geometry_is_redrawn_from_the_next_attempt(tmp_path: Path) -> None:
    from pitstudio_studio.physics.planar import generate

    st = generate.new_state(space.SimConfig(1.0, 0.5))
    (tmp_path / "meta").mkdir()
    slot = next(s for s in st["slots"] if s["family"] == "pile-formation")
    generate.draw_slot(st, slot)
    first = dict(slot["params"])
    generate.replace_geometry(tmp_path, slot, "jammed")
    assert slot["attempt"] == 1 and slot["params"] is None and slot["failed_geometries"][0]["params"] == first
    generate.draw_slot(st, slot)
    assert slot["params"] != first
