"""GNS v3: the planar generator's plan and files against the training reader (FR-011-03, DC-011-01, DC-011-02), pipeline
side.

Not locked. The generator lives in `studio/` (Warp); this file runs in the pipeline environment and imports only its
pure
parts by path (parameter space, split rules, state, payload writer). Physics is replaced by a deterministic stand-in so
the whole 100-geometry plan runs in seconds: what is under test is the boundary, the files the generator writes against
what `pitstudio_pipeline.surrogates.gns` reads. Every rule of FR-011-03 that the reader enforces must hold for a dataset
the generator produced: 100 geometries, 3 seeds each, 70 / 10 / 20 by geometry, tests inside the training envelope and
at least 0.05 from every training geometry under the contract metric, every contract parameter inside the declared
range.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("torch")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_pipeline.surrogates.gns import data, stages  # noqa: E402
from pitstudio_studio.physics.planar import generate, space  # noqa: E402

D = space.D


class _Cfg:
    """Stand-in of SimConfig (the real one needs Warp): the material record and the frame interval."""

    frame_dt = 420 * 2.365e-5

    @staticmethod
    def record() -> dict:
        def mv(v: float) -> dict:
            return {"value": v, "source": "recipe"}

        return {
            "density_kg_per_m3": mv(2650.0),
            "sliding_friction": mv(0.5),
            "rolling_friction": mv(1.0),
            "restitution": mv(0.5),
            "youngs_modulus_pa": mv(5.0e7),
            "poisson_ratio": mv(0.25),
        }


def _fake_rate(family: str, p: dict) -> float:
    """A rate law inside the declared range: linear in the orifice width over the draw range of the family."""
    lo, hi = space.CONTRACT_RANGES[family][1][1:]
    w_lo, w_hi = space.FEED_RANGES[family]["w_o_D"]
    t = (p["w_o_D"] - w_lo) / (w_hi - w_lo)
    return lo + (0.08 + 0.84 * t) * (hi - lo)


def _fake_result(family: str, p: dict, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n = 40
    base = np.column_stack([rng.uniform(-0.1, 0.1, n), rng.uniform(0.0, 0.4, n)]).astype(np.float32)
    frames = np.stack([base, base, base, base]).astype(np.float32)
    res = {
        "status": "rest",
        "frames": frames,
        "frame_times": np.arange(4) * _Cfg.frame_dt,
        "radii": np.full(n, D / 2, dtype=np.float32),
        "n": n,
        "bounds": [-2.2, 0.0, 2.2, 0.6],
        "pile_height_D": 41.0,
        "final_vmax": 0.001,
        "wall_s": 1.0,
        "x99_m": 0.1,
        "x01_m": -0.1,
        "mass_ok": True,
        "max_contacts": 6,
        "y_abs_max_m": 0.0,
        "min_z_over_r": 1.0,
    }
    if family != "column-collapse":
        res.update(rate=_fake_rate(family, p), discharged_fraction=0.99)
    else:
        res.update(h0_real_D=p["a"] * p["L0_D"])
    return res


@pytest.fixture(scope="module")
def plan_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The whole 100-geometry plan driven through the generator's own batch, process and replace functions."""
    out = tmp_path_factory.mktemp("planar-plan") / "rollouts"
    (out / "meta").mkdir(parents=True)
    st = generate.new_state(space.SimConfig(1.0, 0.5))
    logs: list[str] = []
    for splits in (("val",), ("train",), ("test",)):
        for family in space.FAMILIES:
            while True:
                pairs = generate.make_batch(st, family, splits, 6)
                if not pairs:
                    break
                for slot in {id(s): s for s, _ in pairs}.values():
                    rs = [(t, _fake_result(family, t["p"], t["seed"])) for s, t in pairs if s is slot]
                    process = generate.process_collapse if family == "column-collapse" else generate.process_feed
                    process(out, st, slot, rs, _Cfg, "pitstudio-dem-0000000+warp1.17.0", logs.append)
        generate.save_state(out, st)
    assert all(s["done"] for s in st["slots"])
    return out


@pytest.mark.req("FR-011-03")
def test_011_the_generator_and_the_reader_declare_the_same_envelope() -> None:
    declared = {fam: {k: (lo, hi) for k, lo, hi in rows} for fam, rows in space.CONTRACT_RANGES.items()}
    assert declared == {fam: dict(rng) for fam, rng in data.FAMILY_RANGES.items()}


@pytest.mark.req("FR-011-03")
def test_011_a_generated_plan_is_100_geometries_with_3_seeds_split_70_10_20(plan_dir: Path) -> None:
    metas = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((plan_dir / "meta").glob("*.json"))]
    assert len(metas) == 300
    by_geom: dict[str, list[dict]] = {}
    for m in metas:
        by_geom.setdefault(m["geometry_id"], []).append(m)
    assert len(by_geom) == 100
    assert {len(v) for v in by_geom.values()} == {3}
    for ms in by_geom.values():
        assert len({json.dumps(m["geometry"], sort_keys=True) for m in ms}) == 1
    ds = stages.Dataset(plan_dir)  # the reader's own split rules run here (check_split)
    assert {k: len(v) for k, v in ds.split.items()} == {"train": 70, "val": 10, "test": 20}
    fam = {r["geometry_id"]: r["family"] for r in ds.records}
    assert {f: sum(1 for v in fam.values() if v == f) for f in space.FAMILIES} == {
        "column-collapse": 45,
        "pile-formation": 27,
        "dump-over-crest": 28,
    }
    test_fam = [fam[i] for i in ds.split["test"]]
    assert {f: test_fam.count(f) for f in space.FAMILIES} == data.TEST_QUOTA


@pytest.mark.req("FR-011-03")
def test_011_every_contract_parameter_of_the_plan_is_inside_the_declared_range_and_the_envelope_is_recorded(
    plan_dir: Path,
) -> None:
    ds = stages.Dataset(plan_dir)
    for rec in ds.records:
        for key, (lo, hi) in data.FAMILY_RANGES[rec["family"]].items():
            assert lo - 1e-9 <= rec["params"][key] <= hi + 1e-9, (rec["geometry_id"], key)
    env = stages.training_envelope(ds.records, ds.split["train"], D)
    assert {"pour_height", "pour_rate", "crest_height", "dump_rate", "column_width", "particle_diameter"} <= set(env)
    assert env["pour_rate"]["unit"] == "m^2/s"


@pytest.mark.req("FR-011-14")
def test_011_a_generated_rollout_is_accepted_by_the_strict_reader(plan_dir: Path) -> None:
    meta_path = sorted((plan_dir / "meta").glob("g001-*.json"))[0]
    pre = data.s10_preprocess(meta_path, root=plan_dir)
    assert pre.positions.shape[1] == 40
    assert set(np.unique(pre.particle_types)) == {0}
    assert pre.meta["particle_types"] == ["grain"]


@pytest.mark.req("FR-011-03")
def test_011_the_spec_the_example_and_the_reader_state_one_envelope() -> None:
    """Spec 011 section 7, the DC-011-02 example and data.FAMILY_RANGES must not differ from what the generator
    draws."""
    ex = json.loads(
        (ROOT / "specs/011-surrogates/contracts/examples/surrogate-io.valid.json").read_text(encoding="utf-8")
    )
    env = ex["training_envelope"]
    names = {
        "aspect_ratio": "column_aspect_ratio",
        "column_width_m": "column_width",
        "pour_height_m": "pour_height",
        "pour_rate_m2_per_s": "pour_rate",
        "crest_height_m": "crest_height",
        "dump_rate_m2_per_s": "dump_rate",
    }
    for params in space.CONTRACT_RANGES.values():
        for key, lo, hi in params:
            assert (env[names[key]]["min"], env[names[key]]["max"]) == (lo, hi), key
    text = (ROOT / "specs/011-surrogates/spec.md").read_text(encoding="utf-8").replace("\n", " ")
    start = text.index("The GNS training envelope")
    section = " ".join(text[start : start + 1800].split())
    for label, key in (
        ("pour height", "pour_height_m"),
        ("pour rate", "pour_rate_m2_per_s"),
        ("crest height", "crest_height_m"),
        ("dump rate", "dump_rate_m2_per_s"),
    ):
        lo, hi = next((lo, hi) for fam in space.CONTRACT_RANGES.values() for k, lo, hi in fam if k == key)
        assert f"{label} {lo:g} to {hi:g}" in section, (label, lo, hi)
    assert "free-fall" not in section  # the feed is a funnel hopper now


@pytest.mark.req("FR-011-03")
def test_011_a_feed_geometry_whose_measured_rate_leaves_the_declared_envelope_is_replaced(tmp_path: Path) -> None:
    out = tmp_path / "rollouts"
    (out / "meta").mkdir(parents=True)
    st = generate.new_state(space.SimConfig(1.0, 0.5))
    pairs = generate.make_batch(st, "pile-formation", ("val",), 1)
    slot = pairs[0][0]
    hi = space.CONTRACT_RANGES["pile-formation"][1][2]
    rs = [(t, {**_fake_result("pile-formation", t["p"], t["seed"]), "rate": hi * 1.5}) for _, t in pairs]
    generate.process_feed(out, st, slot, rs, _Cfg, "pitstudio-dem-0000000+warp1.17.0", lambda line: None)
    assert slot["done"] is False
    assert slot["attempt"] == 1
    assert slot["params"] is None
    assert "outside" in slot["failed_geometries"][0]["reason"]
    assert not list((out / "meta").glob("*.json"))
