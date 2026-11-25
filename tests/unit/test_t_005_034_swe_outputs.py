"""T-005-034 - FR-005-30, FR-005-31: C2 maps (arrival time, maximum depth and speed, inundated area) and the breach
volume.

Oracles: the maps are recomputed here from snapshots of the depth taken at known times (no solver code), and the breach
volume from the closed form of the triangular hydrograph (V = Q_p T / 2 with T = 2 V / Q_p).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.physics.swe import Breach, SweParams, SweSimulation  # noqa: E402

THR = 0.05


@pytest.fixture(scope="module")
def dam_break_with_snapshots():
    n, dx = 300, 0.5
    h0 = np.zeros((3, n))
    h0[:, :20] = 2.0
    s = SweSimulation(
        np.zeros((3, n)), h0, dx=dx, boundaries={"x-max": "open"}, params=SweParams(h_thr=THR), device="cpu"
    )
    times, snaps, speeds = [0.0], [s.h], [np.zeros((3, n))]
    for k in range(1, 61):
        s.advance(0.25 * k)
        times.append(s.time)
        snaps.append(s.h)
        speeds.append(np.hypot(s.qx, s.qy) / np.maximum(s.h, 1e-300))
    return s, dx, np.array(times), np.array(snaps), np.array(speeds)


def test_arrival_time_lies_in_the_first_snapshot_interval_with_depth_over_the_threshold(dam_break_with_snapshots):
    s, _, times, snaps, _ = dam_break_with_snapshots
    arrival = s.maps()["arrival_time_s"]
    wet = snaps > THR
    for j, i in [(1, 0), (1, 19), (1, 20), (1, 25), (1, 40), (1, 60), (0, 33), (2, 47)]:
        hits = np.where(wet[:, j, i])[0]
        if hits.size == 0:
            assert np.isnan(arrival[j, i])
            continue
        k = hits[0]
        a = arrival[j, i]
        assert times[k - 1] < a <= times[k] + 1e-12 if k > 0 else a == 0.0, (j, i, a, times[k])


def test_cells_wet_at_the_start_arrive_at_time_zero_and_unreached_cells_are_nan(dam_break_with_snapshots):
    s, _, _, _, _ = dam_break_with_snapshots
    arrival = s.maps()["arrival_time_s"]
    assert np.all(arrival[:, :20] == 0.0)
    assert np.isnan(arrival[:, -1]).all()  # the bore (about 6 m/s) has not covered the 140 m to the far end in 15 s
    assert np.nanmin(arrival[:, 20:]) > 0.0


def test_arrival_time_grows_downstream(dam_break_with_snapshots):
    s, _, _, _, _ = dam_break_with_snapshots
    row = s.maps()["arrival_time_s"][1]
    reached = row[~np.isnan(row)]
    assert np.all(np.diff(reached) >= 0.0)


def test_maximum_depth_and_speed_cover_every_snapshot_and_never_exceed_the_initial_head(dam_break_with_snapshots):
    s, _, _, snaps, speeds = dam_break_with_snapshots
    m = s.maps()
    assert np.all(m["max_depth_m"] >= snaps.max(axis=0) - 1e-15)
    assert np.all(m["max_speed_m_s"] >= speeds.max(axis=0) - 1e-12)
    assert m["max_depth_m"].max() <= 2.0 + 1e-12  # a dam break over a flat bed cannot deepen beyond the reservoir
    assert np.all(m["max_speed_m_s"] >= 0.0)


def test_inundated_area_is_the_count_of_cells_over_the_threshold_times_the_cell_area(dam_break_with_snapshots):
    s, dx, _, _, _ = dam_break_with_snapshots
    m = s.maps()
    assert m["inundated_area_m2"] == float((m["max_depth_m"] > THR).sum()) * dx * dx
    assert m["inundated_area_m2"] >= float((np.nan_to_num(m["arrival_time_s"], nan=-1.0) >= 0.0).sum()) * dx * dx - 1e-9


def test_a_higher_threshold_gives_a_later_arrival_and_a_smaller_area():
    out = []
    for thr in (0.01, 0.2):
        h0 = np.zeros((3, 60))
        h0[:, :10] = 1.0
        s = SweSimulation(np.zeros((3, 60)), h0, dx=1.0, params=SweParams(h_thr=thr), device="cpu")
        s.advance(12.0)
        out.append(s.maps())
    lo, hi = out
    both = ~np.isnan(lo["arrival_time_s"]) & ~np.isnan(hi["arrival_time_s"])
    assert np.all(hi["arrival_time_s"][both] >= lo["arrival_time_s"][both])
    assert hi["inundated_area_m2"] <= lo["inundated_area_m2"]


# -- breach hydrograph -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("frac", [0.5, 0.25, 0.8])
def test_triangular_hydrograph_injects_the_prescribed_volume(frac):
    volume, q_peak = 250_000.0, 80.0
    br = Breach(cells=[(3, 3), (3, 4), (4, 3), (4, 4)], volume=volume, peak_discharge=q_peak, peak_fraction=frac)
    assert br.base_time == pytest.approx(2.0 * volume / q_peak)
    z = np.zeros((8, 8))
    s = SweSimulation(
        z, np.zeros_like(z), dx=20.0, breach=br, params=SweParams(max_dt=br.base_time / 200), device="cpu"
    )
    s.advance(1.1 * br.base_time)
    assert math.isclose(s.injected_volume(), volume, rel_tol=1e-6)
    assert math.isclose(s.volume(), volume, rel_tol=1e-6)  # all of it is in the closed box


def test_the_hydrograph_peaks_at_the_declared_fraction_with_the_declared_discharge():
    br = Breach(cells=[(0, 0)], volume=1000.0, peak_discharge=10.0, peak_fraction=0.3)
    tp, eps = 0.3 * br.base_time, 1e-3
    q = lambda t: (br.released(t + eps) - br.released(t - eps)) / (2 * eps)  # noqa: E731
    assert q(tp) == pytest.approx(10.0, rel=1e-4)
    assert q(0.5 * tp) == pytest.approx(5.0, rel=1e-6)
    assert q(tp + 0.5 * (br.base_time - tp)) == pytest.approx(5.0, rel=1e-6)
    assert br.released(0.0) == 0.0
    assert br.released(br.base_time) == pytest.approx(1000.0, rel=1e-14)
    assert br.released(1.0e9) == pytest.approx(1000.0, rel=1e-14)
    assert br.released(tp) == pytest.approx(0.3 * 1000.0, rel=1e-12)  # the rising limb holds the fraction of the volume


def test_the_breach_starts_at_its_declared_time():
    br = Breach(cells=[(1, 1)], volume=100.0, peak_discharge=5.0, start=7.0)
    z = np.zeros((3, 3))
    s = SweSimulation(z, np.zeros_like(z), dx=1.0, breach=br, params=SweParams(max_dt=0.5), device="cpu")
    s.advance(7.0)
    assert s.injected_volume() == 0.0
    assert s.volume() == 0.0
    s.advance(7.0 + br.base_time)
    assert math.isclose(s.injected_volume(), 100.0, rel_tol=1e-9)
