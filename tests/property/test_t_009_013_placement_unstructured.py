# ruff: noqa: E501
"""T-009-013 - FR-009-07, FR-009-08, P-009-12 (placement half): structured placement and unstructured ranges.

Oracles (independent of the code under test):
- FR-009-07 / P-009-12: reference implementation `shapely` (Polygon.contains(Point), with a polygon that has a hole and
  an L-shaped one) for "the footprint centroid lies inside a road or bench polygon"; analytical planar terrain
  h(x, y) = 1500 + 0.03 x - 0.02 y for "the base is within 0.05 m of the terrain height at that point"; the texture list
  of the lithology is the fixture's own dictionary (spec 009 FR-009-07: "only from the lithology's CC0 texture list").
- FR-009-08: analytical distributions, tested with `scipy.stats` at n = 10,000 and a fixed seed, p >= 1e-3 (plan 009
  tolerances: a correct sampler fails one fixed seed with probability <= 1e-3):
    * light intensity factor log-uniform on [0.1, 10]: (log10 x + 1) / 2 is uniform on [0, 1] (kstest);
    * colour temperature uniform on [2,000, 12,000] K: (T - 2000) / 10000 uniform (kstest);
    * sun direction uniform over the upper hemisphere: the unit vector's z = sin(elevation) is uniform on [0, 1]
      (Archimedes' hat-box theorem) and the azimuth is uniform on [0, 360) (kstest on both);
    * distractor count uniform on the integers 0..20: 21 equal expected bins (chisquare);
    * textures drawn uniformly from the whole pool: equal expected counts per id (chisquare);
    * object positions uniform over the visible ground region: an L-shaped region of area 300 m^2 + 200 m^2 puts 40 % of
      the points in the 200 m^2 arm (binomtest), and x, y are uniform inside a rectangle (kstest);
    * independence from any physical field: the Pearson correlation of every pair of drawn quantities is below 0.05 in
      magnitude (standard error 0.01 at n = 10,000).

Expected public API (module `pitstudio_studio.sdg.placement`, package under `studio/src/`; `rng` is a
`numpy.random.Generator`; areas are shapely Polygons in the site-local stage frame, metres):

    sample_structured_placements(rng, *, areas: Sequence[Polygon], terrain_height: Callable[[float, float], float],
                                 object_classes: Sequence[str], max_base_offset_m: float = 0.05) -> list[dict]
        One placement per entry of `object_classes` (in order), each a DC-009-01 `placement` object
        {"class", "x_m", "y_m", "z_m", "yaw_deg"}: (x_m, y_m) is the footprint centroid and lies inside one of `areas`
        (holes excluded); |z_m - terrain_height(x_m, y_m)| <= max_base_offset_m; yaw_deg in [0, 360). Classes allowed:
        haul_truck, shovel, light_vehicle, person.
        ValueError: empty `areas` (message contains "areas"); a class outside the four, e.g. "boulder" (message contains
        "object_classes"); max_base_offset_m negative or non-finite (message contains "max_base_offset_m"); a
        terrain_height that returns a non-finite value (message contains "terrain_height").
    sample_rock_textures(rng, lithology: str, lithologies: Mapping[str, Sequence[str]], *, count: int) -> list[str]
        `count` ids, each drawn uniformly from lithologies[lithology] (with replacement).
        ValueError: unknown lithology or an empty list (message contains "lithology"); count < 1 (message contains "count").
    sample_unstructured(rng, *, texture_ids: Sequence[str], ground_region: Polygon, terrain_height: Callable,
                        object_classes: Sequence[str], textures_per_image: int = 4,
                        light_range: tuple[float, float] = (0.1, 10.0),
                        colour_temperature_range_k: tuple[float, float] = (2000.0, 12000.0),
                        max_distractors: int = 20) -> dict
        A DC-009-01 `dr_unstructured` object: {"texture_ids": [...textures_per_image ids drawn uniformly with
        replacement from texture_ids], "light_intensity_factor": log-uniform over light_range, "colour_temperature_k":
        uniform over colour_temperature_range_k, "sun_elevation_deg" / "sun_azimuth_deg": uniform over the upper
        hemisphere (z = sin(elevation) uniform on [0, 1], azimuth uniform on [0, 360)), "distractor_count": uniform
        integer in 0..max_distractors, "placements": one per object_classes entry, positions uniform over
        `ground_region`, z_m = terrain_height(x, y), yaw uniform on [0, 360)}. Nothing is read from a physical field.
        ValueError: empty texture_ids ("texture_ids"); a range with min >= max or non-finite ("light_range" /
        "colour_temperature_range_k"); max_distractors outside 0..20 ("max_distractors"); textures_per_image < 1
        ("textures_per_image").
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)

from pitstudio_studio.sdg import placement  # noqa: E402

EXAMPLES = 200
VEHICLES = ["haul_truck", "shovel", "light_vehicle", "person"]
LITH = {"quartz_monzonite": ["rock-quartz-monzonite-01", "rock-gravel-02"], "limestone": ["rock-limestone-01"]}
POOL = [f"tex-{i:02d}" for i in range(8)]
N = 10_000


def h(x: float, y: float) -> float:
    """Planar terrain fixture (analytical)."""
    return 1500.0 + 0.03 * x - 0.02 * y


def _areas():
    from shapely.geometry import Polygon

    road = Polygon([(0, 0), (200, 0), (200, 20), (0, 20)])
    bench = Polygon(
        [(0, 50), (120, 50), (120, 150), (0, 150)],
        holes=[[(40, 80), (80, 80), (80, 120), (40, 120)]],
    )
    ell = Polygon([(300, 0), (330, 0), (330, 10), (310, 10), (310, 30), (300, 30)])  # concave
    return [road, bench, ell]


def _placement_validator():
    from jsonschema import Draft202012Validator

    for p in (
        ROOT / "contracts" / "perception-dataset.schema.json",
        ROOT / "specs" / "009-perception" / "contracts" / "perception-dataset.schema.json",
    ):
        if p.is_file():
            s = json.loads(p.read_text(encoding="utf-8"))
            return Draft202012Validator({"$ref": "#/$defs/placement", "$defs": s["$defs"]})
    raise AssertionError("perception-dataset.schema.json not found")


def _unstructured_validator():
    from jsonschema import Draft202012Validator

    for p in (
        ROOT / "contracts" / "perception-dataset.schema.json",
        ROOT / "specs" / "009-perception" / "contracts" / "perception-dataset.schema.json",
    ):
        if p.is_file():
            s = json.loads(p.read_text(encoding="utf-8"))
            return Draft202012Validator({"$ref": "#/$defs/dr_unstructured", "$defs": s["$defs"]})
    raise AssertionError("perception-dataset.schema.json not found")


def _inside_some_area(areas, x: float, y: float) -> bool:
    from shapely.geometry import Point

    return any(a.contains(Point(x, y)) for a in areas)


# ---------------------------------------------------------------- FR-009-07


@pytest.mark.req("FR-009-07")
def test_every_structured_placement_is_inside_a_polygon_on_the_terrain_and_valid() -> None:
    areas = _areas()
    classes = (VEHICLES * 100)[:400]
    out = placement.sample_structured_placements(
        np.random.default_rng(5), areas=areas, terrain_height=h, object_classes=classes
    )
    v = _placement_validator()
    assert [p["class"] for p in out] == classes
    for p in out:
        assert list(v.iter_errors(p)) == []
        assert _inside_some_area(areas, p["x_m"], p["y_m"]), p  # hole and concave notch excluded
        assert abs(p["z_m"] - h(p["x_m"], p["y_m"])) <= 0.05 + 1e-12
    assert len({(p["x_m"], p["y_m"]) for p in out}) == len(out)  # positions are drawn, not repeated


@pytest.mark.req("FR-009-07")
def test_a_zero_base_offset_puts_the_base_exactly_on_the_terrain() -> None:
    out = placement.sample_structured_placements(
        np.random.default_rng(6), areas=_areas(), terrain_height=h, object_classes=VEHICLES * 10, max_base_offset_m=0.0
    )
    for p in out:
        assert p["z_m"] == pytest.approx(h(p["x_m"], p["y_m"]), abs=1e-12)


@pytest.mark.req("FR-009-07")
def test_placement_is_deterministic_for_a_generator_state() -> None:
    kw = {"areas": _areas(), "terrain_height": h, "object_classes": VEHICLES * 5}
    a = placement.sample_structured_placements(np.random.default_rng(9), **kw)
    b = placement.sample_structured_placements(np.random.default_rng(9), **kw)
    c = placement.sample_structured_placements(np.random.default_rng(10), **kw)
    assert a == b
    assert a != c


@pytest.mark.req("FR-009-07")
@pytest.mark.req("P-009-12")
@given(
    seed=st.integers(0, 2**32 - 1),
    x0=st.floats(-5000, 5000),
    y0=st.floats(-5000, 5000),
    w=st.floats(5, 500),
    d=st.floats(5, 500),
    a=st.floats(-0.2, 0.2),
    b=st.floats(-0.2, 0.2),
    offset=st.floats(0, 0.05),
)
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_every_vehicle_and_person_is_inside_a_polygon_and_within_the_offset_of_the_terrain(
    seed: int, x0: float, y0: float, w: float, d: float, a: float, b: float, offset: float
) -> None:
    from shapely.geometry import box

    areas = [box(x0, y0, x0 + w, y0 + d)]

    def terrain(x: float, y: float) -> float:
        return 1000.0 + a * x + b * y

    out = placement.sample_structured_placements(
        np.random.default_rng(seed),
        areas=areas,
        terrain_height=terrain,
        object_classes=(VEHICLES * 5)[:20],
        max_base_offset_m=offset,
    )
    assert len(out) == 20
    for p in out:
        assert _inside_some_area(areas, p["x_m"], p["y_m"])
        assert abs(p["z_m"] - terrain(p["x_m"], p["y_m"])) <= offset + 1e-9
        assert 0.0 <= p["yaw_deg"] < 360.0


@pytest.mark.req("FR-009-07")
@pytest.mark.parametrize(
    ("kwargs", "arg"),
    [
        ({"areas": []}, "areas"),
        ({"object_classes": ["boulder"]}, "object_classes"),
        ({"object_classes": ["truck"]}, "object_classes"),
        ({"max_base_offset_m": -0.01}, "max_base_offset_m"),
        ({"max_base_offset_m": float("nan")}, "max_base_offset_m"),
        ({"terrain_height": lambda x, y: float("nan")}, "terrain_height"),
    ],
)
def test_hostile_structured_arguments_are_rejected_naming_the_argument(kwargs: dict, arg: str) -> None:
    kw = {"areas": _areas(), "terrain_height": h, "object_classes": ["person"]} | kwargs
    with pytest.raises(ValueError, match=arg):
        placement.sample_structured_placements(np.random.default_rng(0), **kw)


@pytest.mark.req("FR-009-07")
def test_rock_textures_come_only_from_the_lithology_list_and_use_every_entry() -> None:
    rng = np.random.default_rng(12)
    got = placement.sample_rock_textures(rng, "quartz_monzonite", LITH, count=400)
    assert len(got) == 400
    assert set(got) == set(LITH["quartz_monzonite"])  # nothing else, and both entries reachable
    assert set(placement.sample_rock_textures(rng, "limestone", LITH, count=7)) == {"rock-limestone-01"}


@pytest.mark.req("FR-009-07")
@pytest.mark.parametrize(
    ("lithology", "lithologies", "count", "arg"),
    [
        ("granite", LITH, 3, "lithology"),
        ("empty", {"empty": []}, 3, "lithology"),
        ("limestone", LITH, 0, "count"),
        ("limestone", LITH, -1, "count"),
    ],
)
def test_hostile_texture_requests_are_rejected(lithology: str, lithologies: dict, count: int, arg: str) -> None:
    with pytest.raises(ValueError, match=arg):
        placement.sample_rock_textures(np.random.default_rng(0), lithology, lithologies, count=count)


# ---------------------------------------------------------------- FR-009-08


def _draws(n: int = N, **kw) -> list[dict]:
    from shapely.geometry import box

    rng = np.random.default_rng(20261007)
    args = {
        "texture_ids": POOL,
        "ground_region": box(0, 0, 100, 50),
        "terrain_height": h,
        "object_classes": ["haul_truck"],
    }
    args.update(kw)
    return [placement.sample_unstructured(rng, **args) for _ in range(n)]


@pytest.mark.req("FR-009-08")
def test_an_unstructured_draw_validates_against_the_dr_unstructured_definition() -> None:
    v = _unstructured_validator()
    for d in _draws(50, object_classes=["haul_truck", "person"]):
        assert list(v.iter_errors(d)) == []
        assert len(d["placements"]) == 2
        assert len(d["texture_ids"]) == 4
        assert set(d["texture_ids"]) <= set(POOL)


@pytest.mark.req("FR-009-08")
def test_light_intensity_is_log_uniform_over_0_1_to_10() -> None:
    from scipy import stats

    x = np.array([d["light_intensity_factor"] for d in _draws()])
    assert x.min() >= 0.1
    assert x.max() <= 10.0
    assert stats.kstest((np.log10(x) + 1.0) / 2.0, "uniform").pvalue >= 1e-3


@pytest.mark.req("FR-009-08")
def test_colour_temperature_is_uniform_over_2000_to_12000_kelvin() -> None:
    from scipy import stats

    t = np.array([d["colour_temperature_k"] for d in _draws()])
    assert t.min() >= 2000.0
    assert t.max() <= 12000.0
    assert stats.kstest((t - 2000.0) / 10000.0, "uniform").pvalue >= 1e-3


@pytest.mark.req("FR-009-08")
def test_sun_direction_is_uniform_over_the_upper_hemisphere() -> None:
    from scipy import stats

    draws = _draws()
    el = np.array([d["sun_elevation_deg"] for d in draws])
    az = np.array([d["sun_azimuth_deg"] for d in draws])
    assert el.min() >= 0.0
    assert el.max() <= 90.0
    assert az.min() >= 0.0
    assert az.max() < 360.0
    assert stats.kstest(np.sin(np.radians(el)), "uniform").pvalue >= 1e-3  # z uniform on [0, 1]
    assert stats.kstest(az / 360.0, "uniform").pvalue >= 1e-3


@pytest.mark.req("FR-009-08")
def test_distractor_count_is_uniform_over_the_integers_0_to_20() -> None:
    from scipy import stats

    c = np.array([d["distractor_count"] for d in _draws()])
    assert c.min() == 0
    assert c.max() == 20
    counts = np.bincount(c, minlength=21)
    assert len(counts) == 21
    assert stats.chisquare(counts).pvalue >= 1e-3  # equal expected counts, N / 21 each


@pytest.mark.req("FR-009-08")
def test_textures_are_drawn_uniformly_from_the_whole_pool() -> None:
    from scipy import stats

    ids = [t for d in _draws(2500) for t in d["texture_ids"]]  # 10,000 texture draws
    counts = np.array([ids.count(t) for t in POOL])
    assert counts.sum() == 10_000
    assert (counts > 0).all()
    assert stats.chisquare(counts).pvalue >= 1e-3


@pytest.mark.req("FR-009-08")
def test_object_positions_are_uniform_over_the_visible_ground_region() -> None:
    from scipy import stats
    from shapely.geometry import Point, Polygon

    xy = np.array([(p["x_m"], p["y_m"]) for d in _draws() for p in d["placements"]])
    assert xy[:, 0].min() >= 0.0
    assert xy[:, 0].max() <= 100.0
    assert xy[:, 1].min() >= 0.0
    assert xy[:, 1].max() <= 50.0
    assert stats.kstest(xy[:, 0] / 100.0, "uniform").pvalue >= 1e-3
    assert stats.kstest(xy[:, 1] / 50.0, "uniform").pvalue >= 1e-3
    # L-shaped region: arm A = [0, 30] x [0, 10] (300 m^2), arm B = [0, 10] x [10, 30] (200 m^2) -> 40 % in B
    ell = Polygon([(0, 0), (30, 0), (30, 10), (10, 10), (10, 30), (0, 30)])
    pts = np.array([(p["x_m"], p["y_m"]) for d in _draws(ground_region=ell) for p in d["placements"]])
    assert all(ell.covers(Point(x, y)) for x, y in pts[:500])
    in_b = int((pts[:, 1] >= 10.0).sum())
    assert stats.binomtest(in_b, len(pts), 0.4).pvalue >= 1e-3


@pytest.mark.req("FR-009-08")
def test_the_drawn_quantities_are_independent_of_each_other() -> None:
    draws = _draws()
    cols = {
        "log_light": np.log10([d["light_intensity_factor"] for d in draws]),
        "temp": [d["colour_temperature_k"] for d in draws],
        "sin_el": np.sin(np.radians([d["sun_elevation_deg"] for d in draws])),
        "az": [d["sun_azimuth_deg"] for d in draws],
        "distract": [d["distractor_count"] for d in draws],
        "x": [d["placements"][0]["x_m"] for d in draws],
    }
    names = list(cols)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            r = float(np.corrcoef(np.asarray(cols[a], float), np.asarray(cols[b], float))[0, 1])
            assert abs(r) < 0.05, (a, b, r)


@pytest.mark.req("FR-009-08")
def test_the_ranges_are_parameters_and_the_draw_is_deterministic() -> None:
    from scipy import stats

    draws = _draws(4000, light_range=(1.0, 4.0), colour_temperature_range_k=(5000.0, 6000.0), max_distractors=3)
    light = np.array([d["light_intensity_factor"] for d in draws])
    assert light.min() >= 1.0
    assert light.max() <= 4.0
    assert stats.kstest(np.log(light) / math.log(4.0), "uniform").pvalue >= 1e-3
    temps = [d["colour_temperature_k"] for d in draws]
    assert 5000.0 <= min(temps) <= max(temps) <= 6000.0
    assert max(d["distractor_count"] for d in draws) == 3
    assert _draws(5) == _draws(5)


@pytest.mark.req("FR-009-08")
@pytest.mark.parametrize(
    ("kwargs", "arg"),
    [
        ({"texture_ids": []}, "texture_ids"),
        ({"light_range": (10.0, 0.1)}, "light_range"),
        ({"light_range": (0.0, 1.0)}, "light_range"),
        ({"light_range": (float("nan"), 1.0)}, "light_range"),
        ({"colour_temperature_range_k": (5000.0, 5000.0)}, "colour_temperature_range_k"),
        ({"max_distractors": 21}, "max_distractors"),
        ({"max_distractors": -1}, "max_distractors"),
        ({"textures_per_image": 0}, "textures_per_image"),
    ],
)
def test_hostile_unstructured_arguments_are_rejected(kwargs: dict, arg: str) -> None:
    with pytest.raises(ValueError, match=arg):
        _draws(1, **kwargs)
