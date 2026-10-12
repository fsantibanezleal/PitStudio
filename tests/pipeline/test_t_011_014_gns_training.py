"""T-011-014 - FR-011-03, FR-011-04: dataset families, geometry split, validation-only selection.

Oracles (independent of the code under test; plan 011 test strategy FR-011-03 / FR-011-04):
- split counts by hand (FR-011-03 and spec section 7): 100 geometries -> 70 training + 10 validation + 20 test by
    geometry id, the
  test set holding 8 column collapses, 6 piles and 6 dumps; 3 packing seeds per geometry give 300 rollouts;
- the envelope rule written out from the DC-011-02 example envelope (`surrogate-io.valid.json`: aspect ratio 0.5
    ... 4, column width
  0.1 ... 0.4 m, pour height, pour rate, crest height, dump rate): parameters normalised to [0, 1] by their range,
      distance =
  Euclidean distance between normalised parameter vectors of two geometries of the same family (geometries of
      different families
  are never near each other); every test geometry lies inside the training envelope (per parameter between the
      training minimum and
  maximum) and at a distance >= 0.05 from every training geometry; a fixture with near-twin geometries (distance
      0.02) makes the
  rule bite;
- replacement counting by hand: 108 candidates, five of which have a reference pile at rest lower than 30 d, give
    the first 100 passing
  candidates in order and `replaced == 5`;
- hand loss: with a zero network and acceleration statistics mean (0.1, 0.2), std (2, 4), a target acceleration
    (2.1, 4.2) normalises
  to (1, 1) and the mean squared error of the normalised accelerations is 1.0;
- random-walk noise: the variance across the 5 velocity-history entries grows with the entry index (a cumulative
    sum of independent
  increments), the noise is zero for scale 0 and reproducible by seed;
- validation-only selection: a split object that raises on any access to the test split, a chosen noise scale equal
    to the argmin of
  the validation losses recorded in the log, and a checkpoint epoch equal to the argmin of the logged per-epoch
      validation loss;
  statistics (normalisation) computed from the training split alone (changing the validation rollouts leaves them
      unchanged,
  changing the training rollouts changes them).

Expected public API (package under `pipeline/src/`):

  module `pitstudio_pipeline.surrogates.gns.data` (numpy only)
    FAMILY_RANGES: dict family -> dict parameter -> (min, max), the training envelope of DC-011-02
    make_geometry_split(geometries, *, seed, min_distance=0.05) -> GeometrySplit
        geometries: list of {"geometry_id": str, "family": "column-collapse" | "pile-formation" | "dump-over-crest",
        "params": {parameter: value}} (parameters named as in FAMILY_RANGES); exactly 100 geometries are split into
            train (70),
        val (10) and test (20: 8 collapses, 6 piles, 6 dumps) id lists; reproducible by seed. Attributes train,
            val, test.
        Raises `pitstudio_pipeline.surrogates.errors.DatasetError` when the rules cannot be met.
    packing_plan(geometry_ids, *, seed, seeds_per_geometry=3) -> list[dict]   {"geometry_id", "packing_seed"} per
        rollout, distinct
    select_geometries(candidates, *, n=100, min_pile_height_d=30.0) -> SelectionResult
        candidates in order, each {"geometry_id", "rest_height_m", "particle_diameter_m", ...}; attributes
            geometries (the first n that
        pass rest_height >= min_pile_height_d x d), replaced (int, candidates that failed and were replaced);
            DatasetError if fewer than n pass.
  module `pitstudio_pipeline.surrogates.gns.train`
    random_walk_noise(n_particles, history, scale, *, seed) -> np.ndarray [n, history, 2] float
    one_step_loss(model, batch, *, stats) -> torch.Tensor (scalar): mean squared error of normalised accelerations;
        batch keys
        positions, velocities, particle_type, bounds, neighbour_index, neighbour_mask, target_acceleration [N, 2]; stats
        {"acceleration": {"mean": [2], "std": [2]}}.
    train_gns(splits, config, *, seed) -> TrainResult
        splits.rollouts(name) for name in "train" | "val" | "test" returns a list of rollouts (dict: positions [T,
            N, 2] float32,
        particle_types [N], bounds [4], d, dt); config: noise_scales (list >= 1 non-negative floats), epochs (>=
            1), batch_size, lr,
        latent, steps, connectivity_radius. Never reads "test". TrainResult attributes: checkpoint (dict:
            model_state, config, stats,
        epoch, noise_scale, selected_on == "validation"), log (dict: noise_candidates [{"scale", "val_loss"}],
            chosen_noise_scale,
        epochs [{"epoch", "train_loss", "val_loss"}], best_epoch, initial_val_loss, selection_split == "validation").
        Raises DatasetError for an empty train or validation split and ValueError for invalid config values.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.errors import DatasetError  # noqa: E402
from pitstudio_pipeline.surrogates.gns import data, train  # noqa: E402
from pitstudio_pipeline.surrogates.gns.model import GnsStep  # noqa: E402

EX = ROOT / "specs" / "011-surrogates" / "contracts" / "examples"
ENVELOPE = json.loads((EX / "surrogate-io.valid.json").read_text(encoding="utf-8"))["training_envelope"]
FAMILIES = {
    "column-collapse": {"aspect_ratio": "column_aspect_ratio", "column_width_m": "column_width"},
    "pile-formation": {"pour_height_m": "pour_height", "pour_rate_m2_per_s": "pour_rate"},
    "dump-over-crest": {"crest_height_m": "crest_height", "dump_rate_m2_per_s": "dump_rate"},
}


def rng_of(family: str, name: str) -> tuple[float, float]:
    e = ENVELOPE[FAMILIES[family][name]]
    return e["min"], e["max"]


def make_geometry(i: int, family: str, u: float, v: float) -> dict:
    (a, b), (c, d) = (rng_of(family, p) for p in FAMILIES[family])
    p1, p2 = list(FAMILIES[family])
    return {"geometry_id": f"g{i:03d}", "family": family, "params": {p1: a + u * (b - a), p2: c + v * (d - c)}}


def lattice(family: str, nu: int, nv: int, start: int) -> list[dict]:
    return [
        make_geometry(start + k, family, iu / (nu - 1), iv / (nv - 1))
        for k, (iu, iv) in enumerate((iu, iv) for iu in range(nu) for iv in range(nv))
    ]


def fixture_geometries(with_twins: bool = True) -> list[dict]:
    """40 collapses (8 x 5), 30 piles (6 x 5), 30 dumps (6 x 5); optionally 3 near-twin pairs replace lattice
    points in the interior."""
    geoms = (
        lattice("column-collapse", 8, 5, 0) + lattice("pile-formation", 6, 5, 40) + lattice("dump-over-crest", 6, 5, 70)
    )
    if with_twins:
        for k, family in ((10, "column-collapse"), (50, "pile-formation"), (80, "dump-over-crest")):
            base = geoms[k]
            (a, b) = rng_of(family, next(iter(FAMILIES[family])))
            twin = copy.deepcopy(base)
            twin["geometry_id"] = base["geometry_id"] + "t"
            first = next(iter(FAMILIES[family]))
            twin["params"][first] = base["params"][first] + 0.02 * (b - a)  # normalised distance 0.02 < 0.05
            geoms[k + 1] = twin  # replaces the neighbouring lattice point (keeps 100 geometries)
    return geoms


def normalised(g: dict) -> np.ndarray:
    return np.array(
        [
            (g["params"][p] - rng_of(g["family"], p)[0]) / (rng_of(g["family"], p)[1] - rng_of(g["family"], p)[0])
            for p in FAMILIES[g["family"]]
        ]
    )


def distance(a: dict, b: dict) -> float:
    return float("inf") if a["family"] != b["family"] else float(np.linalg.norm(normalised(a) - normalised(b)))


# ------------------------------------------------------------------ FR-011-03


@pytest.mark.req("FR-011-03")
def test_the_family_ranges_are_the_dc_011_02_training_envelope() -> None:
    for family, params in FAMILIES.items():
        for p in params:
            assert tuple(data.FAMILY_RANGES[family][p]) == rng_of(family, p)


@pytest.mark.req("FR-011-03")
def test_the_split_is_70_10_20_by_geometry_id_with_8_6_6_test_geometries() -> None:
    geoms = fixture_geometries()
    s = data.make_geometry_split(geoms, seed=1)
    by_id = {g["geometry_id"]: g for g in geoms}
    assert (len(s.train), len(s.val), len(s.test)) == (70, 10, 20)
    assert set(s.train).isdisjoint(s.val)
    assert set(s.train).isdisjoint(s.test)
    assert set(s.val).isdisjoint(s.test)
    assert set(s.train) | set(s.val) | set(s.test) == set(by_id)
    counts = {f: sum(by_id[i]["family"] == f for i in s.test) for f in FAMILIES}
    assert counts == {"column-collapse": 8, "pile-formation": 6, "dump-over-crest": 6}


@pytest.mark.req("FR-011-03")
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_test_geometries_are_inside_the_training_envelope_and_at_least_0_05_from_every_training_geometry(
    seed: int,
) -> None:
    geoms = fixture_geometries()
    by_id = {g["geometry_id"]: g for g in geoms}
    s = data.make_geometry_split(geoms, seed=seed)
    for t in s.test:
        tg = by_id[t]
        assert min(distance(tg, by_id[r]) for r in s.train) >= 0.05
        same = [by_id[r] for r in s.train if by_id[r]["family"] == tg["family"]]
        for p in FAMILIES[tg["family"]]:
            values = [r["params"][p] for r in same]
            assert min(values) <= tg["params"][p] <= max(values)


@pytest.mark.req("FR-011-03")
def test_near_twin_geometries_never_straddle_the_training_and_test_sets() -> None:
    geoms = fixture_geometries()
    s = data.make_geometry_split(geoms, seed=9)
    ids = {g["geometry_id"] for g in geoms}
    for base in ("g010", "g050", "g080"):
        twin = base + "t"
        assert base in ids
        assert twin in ids
        assert not (base in s.test and twin in s.train)
        assert not (twin in s.test and base in s.train)


@pytest.mark.req("FR-011-03")
def test_the_split_is_reproducible_by_seed_and_depends_on_it() -> None:
    geoms = fixture_geometries()
    a, b, c = (
        data.make_geometry_split(geoms, seed=7),
        data.make_geometry_split(geoms, seed=7),
        data.make_geometry_split(geoms, seed=8),
    )
    assert (a.train, a.val, a.test) == (b.train, b.val, b.test)
    assert a.test != c.test


@pytest.mark.req("FR-011-03")
def test_a_split_that_cannot_meet_the_distance_rule_is_refused() -> None:
    geoms = fixture_geometries(with_twins=False)
    for g in geoms:  # all geometries of a family collapse onto one point: distance 0 between any two
        first = list(FAMILIES[g["family"]])
        for p in first:
            g["params"][p] = rng_of(g["family"], p)[0] * 1.5 + rng_of(g["family"], p)[1] * 0.0 + 0.0
    with pytest.raises(DatasetError, match=r"distance|envelope"):
        data.make_geometry_split(geoms, seed=1)


@pytest.mark.req("FR-011-03")
@pytest.mark.parametrize("count", [0, 99, 101])
def test_exactly_100_geometries_are_required(count: int) -> None:
    geoms = fixture_geometries()
    geoms = geoms[:count] if count < 100 else [*geoms, make_geometry(1000, "column-collapse", 0.5, 0.5)]
    with pytest.raises(DatasetError, match="100"):
        data.make_geometry_split(geoms, seed=1)


@pytest.mark.req("FR-011-03")
def test_too_few_geometries_of_a_family_for_the_test_quota_are_refused() -> None:
    geoms = lattice("column-collapse", 10, 7, 0)[:100]  # 70 collapses only: the pile and dump test quota cannot be met
    geoms += [make_geometry(200 + k, "pile-formation", 0.1 * k, 0.5) for k in range(30)]
    with pytest.raises(DatasetError):
        data.make_geometry_split(geoms, seed=1)


@pytest.mark.req("FR-011-03")
def test_duplicate_geometry_ids_and_unknown_families_are_refused() -> None:
    geoms = fixture_geometries()
    dup = copy.deepcopy(geoms)
    dup[3]["geometry_id"] = dup[4]["geometry_id"]
    with pytest.raises(DatasetError, match=r"duplicate|unique"):
        data.make_geometry_split(dup, seed=1)
    odd = copy.deepcopy(geoms)
    odd[0]["family"] = "landslide"
    with pytest.raises(DatasetError, match="family"):
        data.make_geometry_split(odd, seed=1)


@pytest.mark.req("FR-011-03")
def test_three_packing_seeds_per_geometry_make_300_distinct_rollouts() -> None:
    ids = [f"g{i:03d}" for i in range(100)]
    plan = data.packing_plan(ids, seed=5)
    assert len(plan) == 300
    assert {(p["geometry_id"], p["packing_seed"]) for p in plan} == {
        (p["geometry_id"], p["packing_seed"]) for p in plan
    }
    assert len({p["packing_seed"] for p in plan}) == 300  # distinct seeds across the dataset
    for gid in ids:
        assert sum(p["geometry_id"] == gid for p in plan) == 3
    assert all(isinstance(p["packing_seed"], int) and 0 <= p["packing_seed"] < 2**32 for p in plan)
    assert plan == data.packing_plan(ids, seed=5)


@pytest.mark.req("FR-011-03")
def test_reference_piles_lower_than_30_d_are_replaced_and_counted() -> None:
    d = 0.004
    failing = {3, 17, 40, 41, 90}
    cands = [
        {
            "geometry_id": f"c{i:03d}",
            "rest_height_m": (25 if i in failing else 31 + (i % 7)) * d,
            "particle_diameter_m": d,
        }
        for i in range(108)
    ]
    sel = data.select_geometries(cands, n=100)
    assert sel.replaced == 5
    assert len(sel.geometries) == 100
    assert [g["geometry_id"] for g in sel.geometries] == [
        c["geometry_id"] for c in cands if int(c["geometry_id"][1:]) not in failing
    ][:100]
    assert all(g["rest_height_m"] >= 30 * g["particle_diameter_m"] for g in sel.geometries)


@pytest.mark.req("FR-011-03")
def test_a_pile_exactly_30_d_high_is_accepted_and_too_few_passing_candidates_are_refused() -> None:
    d = 0.01
    ok = [{"geometry_id": f"a{i}", "rest_height_m": 30 * d, "particle_diameter_m": d} for i in range(100)]
    assert data.select_geometries(ok, n=100).replaced == 0
    with pytest.raises(DatasetError):
        data.select_geometries(
            [{"geometry_id": f"b{i}", "rest_height_m": 29.9 * d, "particle_diameter_m": d} for i in range(120)], n=100
        )


# ------------------------------------------------------------------ FR-011-04


def tiny_rollout(seed: int, accel: tuple[float, float], n: int = 8, frames: int = 9, dt: float = 0.01) -> dict:
    rng = np.random.default_rng(seed)
    x0 = rng.uniform(0.2, 0.8, (n, 2))
    v0 = rng.normal(0.0, 0.05, (n, 2))
    t = np.arange(frames)[:, None, None] * dt
    pos = (x0[None] + v0[None] * t + 0.5 * np.array(accel)[None, None, :] * t**2).astype(np.float32)
    return {
        "positions": pos,
        "particle_types": np.zeros(n, dtype=np.int64),
        "bounds": np.array([-5, -5, 5, 5], dtype=np.float32),
        "d": 0.04,
        "dt": dt,
    }


class Splits:
    def __init__(self, train, val, test_spy=True):
        self._data = {"train": train, "val": val}
        self.reads: list[str] = []
        self.test_spy = test_spy

    def rollouts(self, name: str):
        self.reads.append(name)
        if name == "test":
            raise AssertionError("the test split was read during training")
        return self._data[name]


CONFIG = {
    "noise_scales": [0.0, 0.005, 0.05],
    "epochs": 6,
    "batch_size": 2,
    "lr": 3e-3,
    "latent": 8,
    "steps": 1,
    "connectivity_radius": 0.1,
}


def tiny_splits(
    train_accels=((1.0, -9.8), (2.0, -9.0), (-1.0, -10.5)), val_accels=((1.5, -9.4), (0.0, -9.9))
) -> Splits:
    train = [tiny_rollout(i, a) for i, a in enumerate(train_accels)]
    val = [tiny_rollout(100 + i, a) for i, a in enumerate(val_accels)]
    return Splits(train, val)


@pytest.mark.req("FR-011-04")
def test_the_loss_is_the_mean_squared_error_of_normalised_accelerations_by_hand() -> None:
    model = GnsStep(
        connectivity_radius=0.1,
        frame_interval=0.01,
        n_particle_types=1,
        latent=4,
        steps=1,
        acceleration_mean=(0.1, 0.2),
        acceleration_std=(2.0, 4.0),
    )
    with torch.no_grad():
        for p in model.parameters():
            p.zero_()  # the network outputs 0: the acceleration equals the mean (0.1, 0.2), normalised 0
    n = 3
    batch = {
        "positions": torch.zeros(n, 2),
        "velocities": torch.zeros(n, 5, 2),
        "particle_type": torch.zeros(n, dtype=torch.int64),
        "bounds": torch.tensor([-1.0, -1.0, 1.0, 1.0]),
        "neighbour_index": torch.zeros(n, 32, dtype=torch.int64),
        "neighbour_mask": torch.zeros(n, 32, dtype=torch.bool),
        "target_acceleration": torch.tensor([[2.1, 4.2]] * n),  # normalised (2.1 - 0.1) / 2 = 1 and (4.2 - 0.2) / 4 = 1
    }
    stats = {"acceleration": {"mean": [0.1, 0.2], "std": [2.0, 4.0]}}
    assert float(train.one_step_loss(model, batch, stats=stats)) == pytest.approx(1.0, abs=1e-6)
    batch["target_acceleration"] = torch.tensor([[0.1, 0.2]] * n)  # a perfect prediction
    assert float(train.one_step_loss(model, batch, stats=stats)) == pytest.approx(0.0, abs=1e-12)
    batch["target_acceleration"] = torch.tensor([[4.1, 0.2]] * n)  # normalised (2, 0): mean of (4, 0) = 2
    assert float(train.one_step_loss(model, batch, stats=stats)) == pytest.approx(2.0, abs=1e-6)


@pytest.mark.req("FR-011-04")
def test_random_walk_noise_variance_grows_along_the_history_and_is_zero_for_scale_zero() -> None:
    noise = train.random_walk_noise(40_000, 5, 0.01, seed=3)
    assert noise.shape == (40_000, 5, 2)
    var = noise.var(axis=(0, 2))
    assert all(var[i] < var[i + 1] for i in range(4))
    assert var[4] >= 3.0 * var[0]  # a cumulative sum of 4 or 5 independent increments: ratio 4 or 5
    assert np.abs(noise.mean()) < 1e-3
    assert not np.any(train.random_walk_noise(100, 5, 0.0, seed=3))
    assert np.array_equal(train.random_walk_noise(50, 5, 0.01, seed=3), train.random_walk_noise(50, 5, 0.01, seed=3))
    assert not np.array_equal(
        train.random_walk_noise(50, 5, 0.01, seed=3), train.random_walk_noise(50, 5, 0.01, seed=4)
    )


@pytest.mark.req("FR-011-04")
def test_random_walk_noise_scales_linearly_with_its_scale() -> None:
    a = train.random_walk_noise(1000, 5, 0.01, seed=2)
    b = train.random_walk_noise(1000, 5, 0.04, seed=2)
    assert np.allclose(b, 4.0 * a, rtol=1e-9, atol=1e-12)


@pytest.mark.req("FR-011-04")
@pytest.mark.parametrize(
    ("n", "history", "scale"), [(0, 5, 0.01), (10, 0, 0.01), (10, 5, -0.1), (10, 5, float("nan")), (-3, 5, 0.01)]
)
def test_hostile_noise_arguments_are_refused(n: int, history: int, scale: float) -> None:
    with pytest.raises(ValueError, match=r"."):
        train.random_walk_noise(n, history, scale, seed=1)


@pytest.mark.req("FR-011-04")
def test_training_never_reads_the_test_split_and_selects_on_validation() -> None:
    splits = tiny_splits()
    res = train.train_gns(splits, dict(CONFIG), seed=0)
    assert "test" not in splits.reads
    assert set(splits.reads) <= {"train", "val"}
    assert res.checkpoint["selected_on"] == "validation"
    assert res.log["selection_split"] == "validation"


@pytest.mark.req("FR-011-04")
def test_the_noise_scale_and_the_checkpoint_epoch_are_the_argmins_of_the_validation_losses() -> None:
    res = train.train_gns(tiny_splits(), dict(CONFIG), seed=0)
    cands = res.log["noise_candidates"]
    assert [c["scale"] for c in cands] == CONFIG["noise_scales"]
    best_scale = min(cands, key=lambda c: c["val_loss"])["scale"]
    assert res.log["chosen_noise_scale"] == best_scale
    assert res.checkpoint["noise_scale"] == best_scale
    epochs = res.log["epochs"]
    assert [e["epoch"] for e in epochs] == list(range(1, CONFIG["epochs"] + 1))
    best_epoch = min(epochs, key=lambda e: e["val_loss"])["epoch"]
    assert res.log["best_epoch"] == best_epoch
    assert res.checkpoint["epoch"] == best_epoch
    assert all(np.isfinite(e["train_loss"]) and np.isfinite(e["val_loss"]) for e in epochs)


@pytest.mark.req("FR-011-04")
def test_the_chosen_checkpoint_beats_the_untrained_network_on_validation() -> None:
    res = train.train_gns(tiny_splits(), dict(CONFIG, epochs=12, noise_scales=[0.0]), seed=0)
    best = min(e["val_loss"] for e in res.log["epochs"])
    assert best < res.log["initial_val_loss"]


@pytest.mark.req("FR-011-04")
def test_training_is_reproducible_by_seed() -> None:
    a = train.train_gns(tiny_splits(), dict(CONFIG, epochs=3), seed=5)
    b = train.train_gns(tiny_splits(), dict(CONFIG, epochs=3), seed=5)
    assert a.log == b.log
    for k, v in a.checkpoint["model_state"].items():
        assert torch.equal(v, b.checkpoint["model_state"][k])


@pytest.mark.req("FR-011-04")
def test_normalisation_statistics_come_from_the_training_split_alone() -> None:
    base = train.train_gns(tiny_splits(), dict(CONFIG, epochs=1, noise_scales=[0.0]), seed=0).checkpoint["stats"]
    other_val = train.train_gns(
        tiny_splits(val_accels=((9.0, 9.0), (-9.0, 3.0))), dict(CONFIG, epochs=1, noise_scales=[0.0]), seed=0
    ).checkpoint["stats"]
    other_train = train.train_gns(
        tiny_splits(train_accels=((5.0, -1.0), (6.0, -2.0), (7.0, -3.0))),
        dict(CONFIG, epochs=1, noise_scales=[0.0]),
        seed=0,
    ).checkpoint["stats"]
    assert base == other_val
    assert base != other_train
    assert base["acceleration"]["mean"] == pytest.approx(
        [(1.0 + 2.0 - 1.0) / 3.0, (-9.8 - 9.0 - 10.5) / 3.0], abs=0.05
    )  # mean of the training accelerations


@pytest.mark.req("FR-011-04")
def test_an_empty_training_or_validation_split_is_refused() -> None:
    with pytest.raises(DatasetError):
        train.train_gns(Splits([], [tiny_rollout(1, (0.0, -9.8))]), dict(CONFIG), seed=0)
    with pytest.raises(DatasetError):
        train.train_gns(Splits([tiny_rollout(1, (0.0, -9.8))], []), dict(CONFIG), seed=0)


@pytest.mark.req("FR-011-04")
@pytest.mark.parametrize(
    "change",
    [
        {"epochs": 0},
        {"epochs": -1},
        {"noise_scales": []},
        {"noise_scales": [-0.1]},
        {"noise_scales": [float("nan")]},
        {"batch_size": 0},
        {"lr": 0.0},
        {"lr": float("inf")},
    ],
)
def test_invalid_hyperparameters_are_refused_before_training(change: dict) -> None:
    splits = tiny_splits()
    with pytest.raises(ValueError, match=r"."):
        train.train_gns(splits, dict(CONFIG, **change), seed=0)
    assert splits.reads == [] or "test" not in splits.reads
