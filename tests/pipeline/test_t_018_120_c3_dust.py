"""T-018-120: case C3 dust, the AP-42 haul-road emission factor and the Gaussian plume over the pit with real wind records
(pipeline test, pipeline environment).

Requirements: FR-018-16, FR-018-51, FR-020-08, DC-020-05.

Spec: spec 018 FR-018-51 (the `minephys.environment` functions: AP-42 section 13.2.2 equation 1a and the ISC3 Gaussian
plume), FR-018-16 (each KPI with its unit), FR-020-08 (the maximum ground-level concentration and its distance drawn as a
labelled marker), DC-020-05 (chart series). Recipe `studio/recipes/cases/c3.yaml` is the parameter source.

Expected public API (package `pitstudio_pipeline.dust`):
    emission.emission_factor_kg_per_vkt(silt_fraction, mean_weight_kg, size_class="PM10") -> float or array [kg/VKT]
    emission.ap42_in_range(silt_fraction, mean_weight_kg) -> bool or array (Table 13.2.2-3 ranges, bounds inclusive)
    emission.fleet_mean_weight_kg(empty_kg, payload_kg, loaded_fraction) -> float
    plume.discretise(lines, spacing_m) -> (points (m, 2), lengths (m,))
    plume.concentration(sources, q_kg_s, receptors, *, wind_speed_m_s, wind_from_deg, stability, release_height_m,
        receptor_height_m, terrain="rural", min_downwind_m=10.0, sigmas=None) -> kg/m3 at each receptor, the sum over the
        sources; wind_from_deg is the meteorological direction (the wind blows from it); `sigmas(x) -> (sy, sz)` replaces the
        ISC3 coefficients (oracle hook)
    plume.receptor_statistics(sources, q_kg_s, receptors, speeds, from_degs, **plume_args) -> dict mean_kg_per_m3, p99_...,
        n_modelled, n_not_modelled (hours with a speed below 1 m/s or without a direction are not modelled)
    c3_run.compute(params, data_root) -> {"summary": dict, "charts": list[dict]}; c3_run.write_outputs(result, out) -> list

Oracles (none of them is the code under test):
- equation 1a by hand: E = k (s/12)^a (W/3)^b lb/VMT with k = 1.5, a = 0.9, b = 0.45 for PM10 (Table 13.2.2-2, p. 13.2.2-5),
  s in percent and W in short tons, then x 0.45359237 kg/lb / 1.609344 km/mile; the numeric worked examples of AP-42 itself
  could not be read (the EPA PDF answered 403), so the hand calculation and the fleet-mean example of the text (98 % of
  2 ton and 2 % of 20 ton vehicles give 2.4 tons, p. 13.2.2-6) are the references;
- the ground-level centre line of a point source at ground level: C = q / (pi u sy sz);
- mass balance: the flux u x integral of C dy dz through a plane across the plume equals the emission rate;
- Turner's maximum for sigma_y = a x, sigma_z = b x: C_max = 2 q b / (pi e u H^2 a) at sigma_z = H / sqrt(2);
- the infinite crosswind line source at ground level: C = sqrt(2 / pi) q_l / (u sz).
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest
import yaml
from pitstudio_pipeline import chartkit
from pitstudio_pipeline.dust import c3_run, plume
from pitstudio_pipeline.dust.emission import ap42_in_range, emission_factor_kg_per_vkt, fleet_mean_weight_kg
from pitstudio_pipeline.ingest.schemas import GHCNH_VARIABLES, QUALIFIERS

ROOT = Path(__file__).resolve().parents[2]
RECIPE = yaml.safe_load((ROOT / "studio/recipes/cases/c3.yaml").read_text(encoding="utf-8"))
STAGE = RECIPE["stages"][0]
LB, MILE, SHORT_TON = 0.45359237, 1609.344, 907.18474


def _hand_pm10(silt_percent: float, weight_short_tons: float) -> float:
    e_lb = 1.5 * (silt_percent / 12) ** 0.9 * (weight_short_tons / 3) ** 0.45
    return e_lb * LB / MILE * 1000  # kg per vehicle-km


# --- emission factor ---------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-018-51")
@pytest.mark.parametrize(("silt", "tons"), [(8.4, 40.0), (1.8, 2.0), (25.2, 290.0), (6.0, 300.0), (12.0, 3.0)])
def test_the_pm10_factor_equals_equation_1a_by_hand(silt: float, tons: float) -> None:
    got = emission_factor_kg_per_vkt(silt / 100, tons * SHORT_TON)
    assert got == pytest.approx(_hand_pm10(silt, tons), rel=1e-12)


@pytest.mark.req("FR-018-51")
def test_the_reference_point_of_the_equation_is_k_in_kg_per_vkt() -> None:
    # s = 12 % and W = 3 short tons make both ratios 1, so E = k = 1.5 lb/VMT = 0.42281 kg/VKT
    assert emission_factor_kg_per_vkt(0.12, 3 * SHORT_TON) == pytest.approx(1.5 * LB / MILE * 1000, rel=1e-12)


@pytest.mark.req("FR-018-51")
def test_the_factor_is_a_power_law_in_silt_and_weight() -> None:
    e = emission_factor_kg_per_vkt
    w = 100_000.0
    assert e(0.08, w) / e(0.04, w) == pytest.approx(2**0.9, rel=1e-12)
    assert e(0.08, 2 * w) / e(0.08, w) == pytest.approx(2**0.45, rel=1e-12)
    arr = e(np.array([0.02, 0.05, 0.2]), w)
    assert arr.shape == (3,)
    assert np.all(np.diff(arr) > 0)


@pytest.mark.req("FR-018-51")
def test_the_validity_ranges_are_those_of_table_13_2_2_3() -> None:
    inside = ap42_in_range(np.array([0.018, 0.252, 0.017, 0.2521, 0.1]), np.array([2, 290, 100, 100, 1.99]) * SHORT_TON)
    # silt 1.8 to 25.2 %, weight 2 to 290 short tons, bounds inclusive; the last one is 1.99 tons
    assert inside.tolist() == [True, True, False, False, False]
    assert bool(ap42_in_range(0.06, 291 * SHORT_TON)) is False


@pytest.mark.req("FR-018-51")
def test_the_fleet_mean_weight_is_the_traffic_weighted_mean() -> None:
    assert fleet_mean_weight_kg(162_000.0, 220_000.0, 0.5) == pytest.approx(272_000.0, rel=1e-14)
    assert fleet_mean_weight_kg(1000.0, 4000.0, 0.0) == 1000.0
    assert fleet_mean_weight_kg(1000.0, 4000.0, 1.0) == 5000.0
    # AP-42 p. 13.2.2-6: 98 % of 2 ton vehicles and 2 % of 20 ton vehicles give 2.4 tons (empty = 2 ton, payload = 18 ton)
    assert fleet_mean_weight_kg(2 * SHORT_TON, 18 * SHORT_TON, 0.02) / SHORT_TON == pytest.approx(2.36, rel=1e-12)


# --- Gaussian plume ----------------------------------------------------------------------------------------------------

SIG = {"B": (0.2, 0.12), "D": (0.1, 0.06)}


def _linear_sigmas(a: float, b: float):
    return lambda x: (a * np.asarray(x, dtype=float), b * np.asarray(x, dtype=float))


@pytest.mark.req("FR-018-51")
@pytest.mark.parametrize("wind_from", [270.0, 0.0, 135.0, 41.3])
def test_the_ground_level_centre_line_is_q_over_pi_u_sy_sz(wind_from: float) -> None:
    a, b = SIG["D"]
    q, u, x = 3.0, 4.0, 750.0
    toward = math.radians(wind_from + 180.0)
    rec = np.array([[x * math.sin(toward), x * math.cos(toward)]])
    c = plume.concentration(
        np.zeros((1, 2)), np.array([q]), rec, wind_speed_m_s=u, wind_from_deg=wind_from, stability="D",
        release_height_m=0.0, receptor_height_m=0.0, sigmas=_linear_sigmas(a, b),
    )  # fmt: skip
    assert c[0] == pytest.approx(q / (math.pi * u * a * x * b * x), rel=1e-12)


@pytest.mark.req("FR-018-51")
def test_upwind_and_crosswind_far_receptors_see_nothing() -> None:
    rec = np.array([[-500.0, 0.0], [500.0, 0.0], [0.0, 1e6]])  # wind from the west: east is downwind
    c = plume.concentration(
        np.zeros((1, 2)), np.array([1.0]), rec, wind_speed_m_s=3.0, wind_from_deg=270.0, stability="D",
        release_height_m=2.0, receptor_height_m=1.5,
    )  # fmt: skip
    assert c[0] == 0.0
    assert c[1] > 0.0
    assert c[2] == 0.0


@pytest.mark.req("FR-018-51")
def test_the_flux_through_a_cross_wind_plane_is_the_emission_rate() -> None:
    q, u, h, x = 2.5, 3.2, 8.0, 900.0
    sy, sz = _linear_sigmas(*SIG["B"])(x)
    ys = np.linspace(-12 * sy, 12 * sy, 481)
    zs = np.linspace(0.0, 14 * sz, 561)
    total = 0.0
    for z in zs:
        rec = np.column_stack([np.full_like(ys, x), ys])  # wind from the west, plane at x
        c = plume.concentration(
            np.zeros((1, 2)), np.array([q]), rec, wind_speed_m_s=u, wind_from_deg=270.0, stability="B",
            release_height_m=h, receptor_height_m=float(z), sigmas=_linear_sigmas(*SIG["B"]),
        )  # fmt: skip
        total += np.trapezoid(c, ys) * (1.0 if 0 < z < zs[-1] else 0.5)
    flux = u * total * (zs[1] - zs[0])
    assert flux == pytest.approx(q, rel=2e-4)


@pytest.mark.req("FR-018-51")
@pytest.mark.req("FR-020-08")
def test_the_maximum_ground_concentration_is_turners_closed_form_at_sz_equal_h_over_root_2() -> None:
    a, b = 0.12, 0.07
    q, u, h = 1.7, 5.0, 15.0
    x_star = h / (math.sqrt(2) * b)
    xs = np.linspace(0.3 * x_star, 3 * x_star, 4001)
    rec = np.column_stack([xs, np.zeros_like(xs)])
    c = plume.concentration(
        np.zeros((1, 2)), np.array([q]), rec, wind_speed_m_s=u, wind_from_deg=270.0, stability="D",
        release_height_m=h, receptor_height_m=0.0, sigmas=_linear_sigmas(a, b),
    )  # fmt: skip
    i = int(np.argmax(c))
    assert xs[i] == pytest.approx(x_star, rel=2e-3)
    assert c[i] == pytest.approx(2 * q * b / (math.pi * math.e * u * h**2 * a), rel=1e-6)


@pytest.mark.req("FR-018-51")
def test_a_long_road_across_the_wind_is_the_infinite_line_source() -> None:
    # 40 km road along y at x = 0 discretised every 10 m; wind from the west; receptor 600 m downwind at the centre
    ys = np.arange(-20_000.0, 20_000.0 + 1, 10.0)
    line = np.column_stack([np.zeros_like(ys), ys])
    pts, lens = plume.discretise([line], 10.0)
    assert lens.sum() == pytest.approx(40_000.0, rel=1e-12)
    q_l = 2.0e-4  # kg/(m s)
    c = plume.concentration(
        pts, q_l * lens, np.array([[600.0, 0.0]]), wind_speed_m_s=4.0, wind_from_deg=270.0, stability="D",
        release_height_m=0.0, receptor_height_m=0.0, sigmas=lambda x: (0.1 * np.asarray(x) + 1e-9, 0.06 * np.asarray(x)),
    )  # fmt: skip
    sz = 0.06 * 600.0
    assert c[0] == pytest.approx(math.sqrt(2 / math.pi) * q_l / (4.0 * sz), rel=2e-3)


@pytest.mark.req("FR-018-51")
def test_discretise_keeps_the_length_and_places_points_at_segment_midpoints() -> None:
    pts, lens = plume.discretise([np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 50.0]])], 30.0)
    assert lens.sum() == pytest.approx(150.0, rel=1e-14)
    assert lens.max() <= 30.0 + 1e-12
    assert pts[0].tolist() == pytest.approx([100.0 / 8, 0.0])  # four pieces of 25 m on the first leg
    assert len(pts) == 4 + 2


@pytest.mark.req("FR-018-51")
def test_the_concentration_is_linear_in_q_and_symmetric_about_the_wind_axis() -> None:
    kw = {"wind_speed_m_s": 3.0, "wind_from_deg": 270.0, "stability": "C", "release_height_m": 3.0, "receptor_height_m": 1.5}
    rec = np.array([[800.0, 120.0], [800.0, -120.0]])
    c1 = plume.concentration(np.zeros((1, 2)), np.array([1.0]), rec, **kw)
    c3 = plume.concentration(np.zeros((1, 2)), np.array([3.0]), rec, **kw)
    assert c1[0] == pytest.approx(c1[1], rel=1e-12)
    assert c3 == pytest.approx(3 * c1, rel=1e-12)


@pytest.mark.req("FR-018-51")
def test_receptor_statistics_weight_the_hours_exactly_and_count_the_hours_not_modelled() -> None:
    src, rec = np.zeros((1, 2)), np.array([[1000.0, 0.0]])
    kw = {"stability": "D", "release_height_m": 3.0, "receptor_height_m": 1.5}
    one = plume.concentration(src, np.array([1.0]), rec, wind_speed_m_s=4.0, wind_from_deg=270.0, **kw)[0]
    speeds = np.array([4.0, 4.0, 4.0, 4.0, 0.4, 5.0])
    dirs = np.array([270.0, 270.0, 270.0, 90.0, 270.0, np.nan])
    st = plume.receptor_statistics(src, np.array([1.0]), rec, speeds, dirs, **kw)
    assert st["n_modelled"] == 4
    assert st["n_not_modelled"] == 2
    assert st["mean_kg_per_m3"][0] == pytest.approx(3 * one / 4, rel=1e-12)  # three downwind hours, one upwind (zero)
    assert st["p99_kg_per_m3"][0] == pytest.approx(one, rel=1e-12)


# --- the run -----------------------------------------------------------------------------------------------------------


def _psv(tmp_path: Path) -> Path:
    header = [
        "STATION", "Station_name", "DATE", "Year", "Month", "Day", "Hour", "Minute", "LATITUDE", "LONGITUDE", "ELEVATION",
        *[v + q for v in GHCNH_VARIABLES for q in ("", *QUALIFIERS)],
    ]  # fmt: skip
    rows = []
    for h in range(24):  # a west wind of 5 m/s for 18 hours, a south wind of 3 m/s for 6 hours
        wd, ws = ("270", "5.0") if h < 18 else ("180", "3.0")
        cell = dict.fromkeys(header, "")
        cell.update(
            STATION="USW00024127", Station_name="X", DATE=f"2020-03-01T{h:02d}:53:00", Year="2020", Month="03", Day="01",
            Hour=f"{h:02d}", Minute="53", LATITUDE="40.7706", LONGITUDE="-111.965", ELEVATION="1288.4",
            wind_speed=ws, wind_speed_Quality_Code="5", wind_direction=wd, wind_direction_Quality_Code="5",
        )  # fmt: skip
        rows.append("|".join(cell[c] for c in header))
    path = tmp_path / "raw" / "w.psv"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(["|".join(header), *rows]) + "\n", encoding="utf-8", newline="\n")
    return path


def _data_root(tmp_path: Path) -> Path:
    _psv(tmp_path)
    ring = [[-1000, -1000], [1000, -1000], [1000, 1000], [-1000, 1000], [-1000, -1000]]
    (tmp_path / "outline.geojson").write_text(json.dumps({"type": "Polygon", "coordinates": [ring]}), encoding="utf-8")
    road = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-800.0, 0.0, 0.0]}, "properties": {"kind": "node"}},
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-800.0, 0.0, 0.0], [800.0, 0.0, 10.0]]}, "properties": {"kind": "edge", "length_m": 1600.0}},
        ],
    }  # fmt: skip
    (tmp_path / "roads.geojson").write_text(json.dumps(road), encoding="utf-8")
    return tmp_path


def _params(*, with_wind: bool = True) -> dict:
    p = copy.deepcopy(STAGE["params"])
    p["inputs"].update(road_network="roads.geojson", pit_outline="outline.geojson")
    p["inputs"]["wind_files"] = ["raw/w.psv"] if with_wind else ["raw/absent.psv"]
    p["map"].update(nx=40, ny=36, half_width_m=2500.0, source_spacing_m=50.0)
    p["receptors"]["source_spacing_m"] = 100.0
    p["profile"]["n"] = 60
    return p


@pytest.fixture(scope="module")
def result(tmp_path_factory) -> dict:
    root = _data_root(tmp_path_factory.mktemp("c3data"))
    return c3_run.compute(_params(), root)


def _chart(result: dict, cid: str) -> dict:
    return next(c for c in result["charts"] if c["id"] == cid)


@pytest.mark.req("DC-020-05")
def test_the_charts_of_the_recipe_are_the_charts_the_run_returns_and_all_validate(result, tmp_path) -> None:
    ids = [c["id"] for c in result["charts"]]
    assert ids == [Path(o["path"]).stem for o in STAGE["outputs"] if o["path"].startswith("charts/")]
    assert all(c["case"] == "C3" for c in result["charts"])
    for c in result["charts"]:
        assert chartkit.problems(c) == []
        assert c["status"] == "ok"
        assert {"tool", "method", "version", "label"} <= set(c["producer"])
    written = c3_run.write_outputs(result, tmp_path)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in written) == sorted(o["path"] for o in STAGE["outputs"])


@pytest.mark.req("FR-018-16")
def test_the_headline_emission_factor_is_equation_1a_for_the_fleet_mean_and_carries_its_unit(result) -> None:
    s = STAGE["params"]["scenario"]
    w = s["truck"]["empty_mass_kg"] + s["truck"]["loaded_fraction"] * s["truck"]["payload_kg"]
    want = _hand_pm10(100 * s["silt_fraction"], w / SHORT_TON)
    head = {h["kpi"]: h for h in result["summary"]["headline"]}
    assert head["pm10_per_vkt"]["unit"] == "kg/VKT"
    assert head["pm10_per_vkt"]["value"] == pytest.approx(want, rel=1e-4)  # published at six significant digits
    assert head["receptor_concentration"]["unit"] == "ug/m3"
    assert head["receptor_concentration"]["value"] > 0
    assert result["summary"]["label"].startswith("screening")
    assert "not AERMOD" in result["summary"]["label"]


@pytest.mark.req("FR-018-51")
def test_the_emission_charts_mark_the_ap42_validity_range(result) -> None:
    silt = _chart(result, "c3-ef-vs-silt")
    assert silt["chart_type"] == "line"
    assert silt["y_axis"]["unit"] == "kg/VKT"
    marks = {m["x"] for m in silt["markers"] if m["orientation"] == "vertical"}
    assert marks == {1.8, 25.2}  # percent, Table 13.2.2-3
    w = _chart(result, "c3-ef-vs-weight")
    assert {round(m["x"], 3) for m in w["markers"] if m["orientation"] == "vertical"} == {
        round(2 * SHORT_TON / 1000, 3),
        round(290 * SHORT_TON / 1000, 3),
    }
    for s in silt["series"]:  # each point of a curve is the hand equation (the series label names the weight in t)
        t = float(s["id"].rsplit("-", 1)[1])
        for x, y in zip(s["x"][::7], s["y"][::7], strict=False):
            assert y == pytest.approx(_hand_pm10(x, t * 1000 / SHORT_TON), rel=1e-4)


@pytest.mark.req("FR-018-51")
def test_the_table_lists_the_controlled_factors_as_e_times_one_minus_ce(result) -> None:
    t = _chart(result, "c3-ef-table")["table"]
    cols = [c["id"] for c in t["columns"]]
    base = [r for r in t["rows"] if r[cols.index("control-percent")] == 0][0]
    for r in t["rows"]:
        ce = r[cols.index("control-percent")]
        assert r[cols.index("pm10-kg-per-vkt")] == pytest.approx(base[cols.index("pm10-kg-per-vkt")] * (1 - ce / 100), rel=1e-4)


@pytest.mark.req("FR-018-16")
def test_the_wind_rose_is_the_record_tally(result) -> None:
    rose = _chart(result, "c3-wind-rose")
    assert rose["chart_type"] == "bar"
    assert len(rose["categories"]) == 16
    total = sum(sum(s["y"]) for s in rose["series"])
    assert total == pytest.approx(100.0, abs=1e-6)  # percent of all 24 hours, all hours have wind and a direction
    west = rose["categories"].index(next(c for c in rose["categories"] if c["id"] == "w"))
    south = rose["categories"].index(next(c for c in rose["categories"] if c["id"] == "s"))
    assert sum(s["y"][west] for s in rose["series"]) == pytest.approx(100 * 18 / 24, abs=1e-6)
    assert sum(s["y"][south] for s in rose["series"]) == pytest.approx(100 * 6 / 24, abs=1e-6)


@pytest.mark.req("FR-018-16")
@pytest.mark.req("FR-020-08")
def test_the_plume_map_has_units_a_colour_scale_and_the_maximum_marked(result) -> None:
    m = _chart(result, "c3-plume-map")
    r = m["raster"]
    assert (r["nx"], r["ny"]) == (40, 36)
    assert len(r["values"]) == 40 * 36
    assert r["colour"]["unit"] == "ug/m3"
    assert r["colour"]["colormap"] in {"viridis", "cividis", "inferno", "magma"}
    assert r["colour"]["vmin"] == 0 and r["colour"]["vmax"] > 0
    assert m["x_axis"]["unit"] == "m" and m["y_axis"]["unit"] == "m"
    e = r["extent"]
    assert e["x0"] <= -2500 + 1e-9 and e["x1"] >= 2500 - 1e-9  # the grid covers the pit outline (+-1000 m) and more
    vals = np.array([np.nan if v is None else v for v in r["values"]]).reshape(36, 40)
    mark = next(k for k in m["markers"] if k["id"] == "max-concentration")
    top = float(np.nanmax(vals))
    assert float(mark["value_text"].split()[0]) == pytest.approx(top, rel=5e-3)
    assert mark["value_text"].endswith("ug/m3")
    cx = e["x0"] + (np.arange(40) + 0.5) * (e["x1"] - e["x0"]) / 40
    iy, ix = np.unravel_index(np.nanargmax(vals), vals.shape)
    assert mark["x"] == pytest.approx(cx[ix], abs=1e-6)
    assert cx[ix] > 0  # the prevailing wind is from the west, so the maximum lies on the east half, downwind of the road


@pytest.mark.req("FR-020-08")
def test_the_distance_profile_marks_the_maximum_of_each_stability_class(result) -> None:
    c = _chart(result, "c3-conc-vs-distance")
    assert c["chart_type"] == "line"
    assert len(c["series"]) == len(STAGE["params"]["profile"]["classes"])
    points = [m for m in c["markers"] if m["orientation"] == "point"]
    assert len(points) == len(c["series"])
    for s, m in zip(c["series"], points, strict=True):
        i = int(np.argmax(s["y"]))
        assert m["x"] == s["x"][i]
        assert m["y"] == s["y"][i]


@pytest.mark.req("FR-018-16")
def test_the_receptor_chart_has_the_four_receptors_with_a_mean_and_a_hourly_p99(result) -> None:
    c = _chart(result, "c3-receptor-concentration")
    assert [k["id"] for k in c["categories"]] == ["r-n", "r-e", "r-s", "r-w"]
    assert {s["id"] for s in c["series"]} == {"mean", "p99-hourly"}
    mean = next(s for s in c["series"] if s["id"] == "mean")["y"]
    p99 = next(s for s in c["series"] if s["id"] == "p99-hourly")["y"]
    assert all(b >= a >= 0 for a, b in zip(mean, p99, strict=True))
    assert mean[1] == max(mean)  # the east receptor is downwind of the road for 18 of 24 hours


@pytest.mark.req("FR-018-16")
def test_the_summary_names_its_inputs_by_digest_and_never_by_a_path(result) -> None:
    text = json.dumps(result["summary"]) + json.dumps(result["charts"])
    assert ":\\" not in text and "Users" not in text and "\\\\" not in text
    s = result["summary"]["extra"]
    assert s["wind"]["station"] == "USW00024127"
    assert s["wind"]["hours"] == 24
    assert all(len(d["sha256"]) == 64 for d in s["inputs"])
    for d in s["inputs"]:
        assert not Path(d["name"]).is_absolute()
        assert "\\" not in d["name"]
    assert s["assumptions"]


@pytest.mark.req("DC-020-05")
def test_the_run_is_deterministic(tmp_path) -> None:
    root = _data_root(tmp_path)
    a = c3_run.compute(_params(), root)
    b = c3_run.compute(_params(), root)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.mark.req("DC-020-05")
def test_without_the_wind_file_the_wind_charts_are_not_run_with_the_reason_and_the_emission_charts_stay(tmp_path) -> None:
    out = c3_run.compute(_params(with_wind=False), _data_root(tmp_path))
    by = {c["id"]: c for c in out["charts"]}
    for cid in ("c3-wind-rose", "c3-plume-map", "c3-receptor-concentration"):
        assert by[cid]["status"] == "not-run"
        assert "wind" in by[cid]["not_run_reason"]["en"].lower()
        assert chartkit.problems(by[cid]) == []
    assert by["c3-ef-vs-silt"]["status"] == "ok"
    assert by["c3-conc-vs-distance"]["status"] == "not-run"  # the reference wind comes from the record
    assert {h["kpi"] for h in out["summary"]["headline"]} == {"pm10_per_vkt"}
