"""Planar reference data: rest judged as the verification measures it, the box of a rollout contains its solids, and
the rollouts that are not at rest are re-simulated (T-011-014, FR-011-03, FR-011-10).

Not locked. gns-rollouts-v2 failed its verification on two defects that no rule of the generator caught:

- 84 of 300 rollouts were "not at rest": the generator stopped a rollout when the instantaneous maximum grain speed was
  under 0.01 sqrt(g d) on three frames, the verification measures the displacement between the stored (float32) frames
  over the same three intervals, and the two differ at the threshold (median of the dataset 0.00309 m/s against the
  threshold 0.00313);
- 48 dump rollouts had boundary particles "outside the bounds of the rollout": the platform row starts exactly on the
  left wall of the box, the payload stores float32, and a float32 that rounds down lies 1e-8 to 1e-7 m outside the
  float64 bound written to the metadata.

The fixes: the rest test reads the same displacement the verification reads, the writer widens the recorded bounds to
contain the stored solids, `requeue_not_at_rest` takes the rollouts that fail the rest rule back to the generator (the
files kept under `superseded/`, the seed re-simulated under the same id, a failed seed replaced by the next seed of
the geometry as FR-011-10 says), and `rewrite_bounds` repairs the recorded box of finished rollouts from their static
geometry without touching a payload.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.physics.planar import engine, generate, measure, space, verify  # noqa: E402

D = space.D
CFG = space.SimConfig(1.0, 0.5)
THR = space.REST_FRAC * (space.G * D) ** 0.5
PILE = {"x_p_D": 0.0, "z_o_D": 12.0, "w_o_D": 10.0, "n": 24}


# ------------------------------------------------------------------------------------------------ rest measurement
@pytest.mark.req("FR-011-10")
def test_011_b_the_rest_speed_is_the_displacement_between_stored_frames_over_the_last_intervals() -> None:
    dt = 0.01
    frames = np.zeros((6, 2, 2), dtype=np.float32)
    frames[3, 1, 0] = 0.00004  # one grain moves 4e-5 m between frames 2 and 3, then returns
    frames[4:] = frames[3]
    assert measure.step_speed(frames[2], frames[3], dt) == pytest.approx(0.004, rel=1e-4)
    assert measure.step_speed(frames[3], frames[4], dt) == 0.0
    # the last three intervals are (2,3), (3,4) and (4,5): the move is inside the window
    assert measure.rest_speed(frames, dt) == pytest.approx(0.004, rel=1e-4)
    # with one more static frame the move leaves the window
    assert measure.rest_speed(np.concatenate([frames, frames[-1:]]), dt) == 0.0
    # fewer frames than a window: speed is infinite, never "at rest"
    assert measure.rest_speed(frames[:2], dt) == 1.0 / dt * np.linalg.norm(frames[1] - frames[0], axis=1).max()
    assert measure.rest_speed(frames[:1], dt) == float("inf")


@pytest.mark.req("FR-011-10")
def test_011_b_the_threshold_and_the_slack_are_the_ones_of_the_verification() -> None:
    assert measure.rest_threshold() == pytest.approx(THR)
    assert measure.REST_SLACK == 1.05
    assert space.REST_FRAMES == 3


@pytest.mark.req("FR-011-10")
def test_011_b_a_finished_feed_passes_the_verification_rest_rule_on_the_frames_it_stored() -> None:
    (res,) = engine.simulate_feed(
        "pile-formation", [{"p": PILE, "seed": 1, "geom_seed": 1}], engine.NoPacer(), CFG, "cpu", t_cap=6.0
    )
    assert res["status"] == "rest"
    speed = measure.rest_speed(res["frames"], CFG.frame_dt)
    assert speed < THR  # the generator declared rest on exactly this quantity, with no slack needed
    assert res["final_vmax"] < THR


@pytest.mark.req("FR-011-10")
def test_011_b_a_rollout_whose_stored_frames_still_move_is_not_at_rest_whatever_the_instantaneous_speed() -> None:
    judge = measure.RestJudge(THR)
    # the instantaneous maximum speed alone (the old input) would end this run: it is under the threshold
    assert [judge.update(t, 0.5 * THR) for t in (0.4, 0.5, 0.6)][-1] == "rest"
    # the combined speed the generator now feeds the judge: the displacement of a frame pair is over the threshold
    judge = measure.RestJudge(THR)
    frames = np.zeros((2, 3, 2), dtype=np.float32)
    frames[1, 0, 0] = 0.0000445  # 4.45e-3 m/s over 0.01 s
    combined = measure.combined_speed(0.5 * THR, frames[0], frames[1], 0.01)
    assert combined == pytest.approx(0.00445, rel=1e-3)
    assert [judge.update(t, combined) for t in (0.4, 0.5, 0.6)] == ["run", "run", "run"]


# ------------------------------------------------------------------------------------------------ bounds of the box
def _result_with_boundary(boundary: np.ndarray, bounds: list[float]) -> dict:
    t, n = 40, 3
    rng = np.random.default_rng(2)
    frames = np.repeat(rng.uniform(0.1, 0.2, (1, n, 2)).astype(np.float32), t, axis=0)
    return {
        "status": "rest",
        "frames": frames,
        "frame_times": np.arange(t) * 0.01,
        "radii": np.full(n, 0.005, dtype=np.float32),
        "bounds": bounds,
        "boundary": boundary,
        "n_boundary": len(boundary),
    }


@pytest.mark.req("FR-011-03")
def test_011_b_float32_solids_on_the_edge_of_the_box_are_inside_the_recorded_bounds(tmp_path: Path) -> None:
    lx0 = -2.1337310823686404  # a real dump: float32(lx0) = -2.1337311267852783 is 4.4e-8 m below it
    assert float(np.float32(lx0)) < lx0
    lx1 = 2.2
    top = np.array([[lx0, 0.5], [lx0 + 0.1, 0.5], [0.0, 0.5]], dtype=np.float32)
    res = _result_with_boundary(top, [lx0, 0.0, lx1, 1.0])
    meta = generate.write_rollout(
        tmp_path,
        "r1",
        "dump-over-crest",
        "g1",
        {"x_c_D": 0.0, "h_c_D": 9.0, "z_o_D": 12.0, "w_o_D": 10.0, "x_off_D": 6.0, "n": 24},
        space.geometry_record("dump-over-crest", {"x_c_D": 0.0, "h_c_D": 9.0, "x_off_D": 6.0}, 0.1),
        1,
        res,
        CFG,
        "v",
    )
    x0, z0, x1, z1 = meta["bounds_m"]
    assert x0 <= float(top[:, 0].min())
    assert z0 == 0.0
    assert x1 == lx1
    assert z1 == 1.0
    assert x0 == pytest.approx(lx0, abs=1e-6)  # widened by the rounding only
    (tmp_path / "meta").mkdir(exist_ok=True)
    (tmp_path / "meta" / "r1.json").write_text(json.dumps(meta), encoding="utf-8")
    row = verify.check_rollout(tmp_path, meta, {"h_c_D": 9.0, "z_o_D": 12.0})
    assert not any("outside the bounds" in p for p in row["problems"])


@pytest.mark.req("FR-011-03")
def test_011_b_the_bounds_keep_the_domain_when_the_solids_are_inside_and_widen_on_every_side() -> None:
    inside = np.array([[0.1, 0.1], [0.5, 0.5]], dtype=np.float32)
    assert generate.contain_bounds([0.0, 0.0, 1.0, 1.0], inside) == [0.0, 0.0, 1.0, 1.0]
    assert generate.contain_bounds([0.0, 0.0, 1.0, 1.0], None) == [0.0, 0.0, 1.0, 1.0]
    out = generate.contain_bounds([0.0, 0.0, 1.0, 1.0], np.array([[-0.25, -0.5], [1.5, 2.0]], dtype=np.float32))
    assert out == [-0.25, -0.5, 1.5, 2.0]


# ------------------------------------------------------------------------------------------------ tiny generated set
def _tiny_ranges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(space, "N_FEED", 24)
    monkeypatch.setitem(
        space.FEED_RANGES, "pile-formation", {"x_p_D": (0.0, 0.0), "z_o_D": (12.0, 13.0), "w_o_D": (10.0, 11.0)}
    )
    monkeypatch.setitem(
        space.CONTRACT_RANGES,
        "pile-formation",
        (("pour_height_m", 0.0, 10.0), ("pour_rate_m2_per_s", 0.0, 10.0)),
    )
    monkeypatch.setattr(generate, "MIN_HEIGHT_D", 0.0)


class _Guard:
    since = None
    paused_s = 0.0


class _Lock:
    def release(self) -> None:
        return None


def _run(out: Path) -> int:
    args = generate.RunArgs(
        out=out,
        mu_r=1.0,
        mu_s=0.5,
        k_feed=3,
        limit_batches=1,
        families=("pile-formation",),
        phase="trainval",
        device="cpu",
    )
    return generate.run(args, session=lambda: (_Guard(), _Lock(), engine.NoPacer()))


@pytest.fixture(scope="module")
def tiny_master(tmp_path_factory: pytest.TempPathFactory):
    mp = pytest.MonkeyPatch()
    _tiny_ranges(mp)
    out = tmp_path_factory.mktemp("planar_final") / "master"
    assert _run(out) == 0
    yield out
    mp.undo()


@pytest.fixture
def tiny(tiny_master: Path, tmp_path: Path):
    """A private copy of the generated set (each test may rewrite it)."""
    out = tmp_path / "rollouts"
    shutil.copytree(tiny_master, out)
    return out


def _digests(out: Path) -> dict[str, str]:
    return {p.name: generate.store_digest(p) for p in sorted((out / "payload").glob("*.zarr"))}


@pytest.mark.req("FR-011-10")
def test_011_b_the_rollouts_over_the_rest_limit_are_listed_with_their_speed(tiny: Path) -> None:
    speeds = {r["id"]: r["speed"] for r in generate.not_at_rest(tiny, limit=-1.0)}
    assert len(speeds) == 3
    assert all(0.0 <= s < measure.rest_threshold() * measure.REST_SLACK for s in speeds.values())  # a clean set
    assert generate.not_at_rest(tiny) == []
    mid = sorted(speeds.values())
    limit = 0.5 * (mid[1] + mid[2])
    (worst,) = generate.not_at_rest(tiny, limit=limit)
    assert worst["id"] == max(speeds, key=speeds.get)
    assert worst["geometry_id"]
    assert worst["speed"] == pytest.approx(max(speeds.values()))


@pytest.mark.req("FR-011-10")
def test_011_b_a_requeued_rollout_is_kept_aside_and_resimulated_under_the_same_id_while_the_others_stay(
    tiny: Path,
) -> None:
    before = _digests(tiny)
    speeds = {r["id"]: r["speed"] for r in generate.not_at_rest(tiny, limit=-1.0)}
    mid = sorted(speeds.values())
    limit = 0.5 * (mid[1] + mid[2])
    (worst,) = generate.not_at_rest(tiny, limit=limit)
    rid = worst["id"]
    moved = generate.requeue_not_at_rest(tiny, limit=limit, reason="test")
    assert [m["id"] for m in moved] == [rid]
    st = generate.load_state(tiny)
    (slot,) = [s for s in st["slots"] if s["done"] is False and s["seeds"]]
    assert len(slot["seeds"]) == 2
    assert rid not in {s["id"] for s in slot["seeds"]}
    assert slot["superseded"][0]["id"] == rid
    assert slot["superseded"][0]["sha256"] == before[f"{rid}.zarr"]
    assert slot["superseded"][0]["reason"] == "test"
    assert not (tiny / "meta" / f"{rid}.json").exists()
    assert not (tiny / "payload" / f"{rid}.zarr").exists()
    kept = tiny / "superseded" / "test" / f"{rid}.zarr"
    assert kept.exists()
    assert generate.store_digest(kept) == before[f"{rid}.zarr"]
    assert (tiny / "superseded" / "test" / f"{rid}.json").exists()
    # the generator resumes: only the missing seed is simulated, under the same id; the other two are untouched
    assert _run(tiny) == 0
    after = _digests(tiny)
    assert set(after) == set(before)
    for name in before:
        if name != f"{rid}.zarr":
            assert after[name] == before[name]
    st = generate.load_state(tiny)
    slot = next(s for s in st["slots"] if s["id"] == worst["geometry_id"])
    assert slot["done"]
    assert {s["id"] for s in slot["seeds"]} == set(speeds)
    assert slot["superseded"][0]["id"] == rid  # the count stays in the state
    metas = [json.loads((tiny / "meta" / f"{i}.json").read_text(encoding="utf-8")) for i in sorted(speeds)]
    assert len({json.dumps(m["geometry"], sort_keys=True) for m in metas}) == 1  # one geometry record
    rates = [e["rate"] for e in slot["seeds"]]
    assert metas[0]["geometry"]["pour_rate_m2_per_s"] == pytest.approx(float(np.mean(rates)))
    for m in metas:
        assert m["store"]["sha256"] == generate.store_digest(tiny / m["store"]["path"])
    # nothing is left to requeue: a second call is a no-op (a resumed job calls it again)
    assert generate.requeue_not_at_rest(tiny) == []


@pytest.mark.req("FR-011-10")
def test_011_b_a_requeue_with_nothing_over_the_limit_changes_nothing(tiny: Path) -> None:
    state = (tiny / "_state.json").read_bytes()
    assert generate.requeue_not_at_rest(tiny) == []
    assert (tiny / "_state.json").read_bytes() == state
    assert not (tiny / "superseded").exists()


# ------------------------------------------------------------------------------------------------ rewrite of the box
@pytest.mark.req("FR-011-03")
def test_011_b_the_bounds_of_finished_rollouts_are_rewritten_from_their_geometry_and_the_payload_is_untouched(
    tiny: Path,
) -> None:
    import zarr

    before = _digests(tiny)
    f = sorted((tiny / "meta").glob("*.json"))[0]
    meta = json.loads(f.read_text(encoding="utf-8"))
    g = zarr.open_group(str(tiny / meta["store"]["path"]), mode="r")
    types = np.asarray(g["type_index"][:])
    bnd = np.asarray(g["positions"][0, int(np.flatnonzero(types == 1)[0]) :, :])
    grains_before = np.asarray(g["positions"][:, : int((types == 0).sum()), :]).tobytes()
    # the defect: the recorded box is a hair inside the left-most solid
    meta["bounds_m"][0] = float(bnd[:, 0].min()) + 1e-7
    f.write_text(json.dumps(meta), encoding="utf-8")
    slot = next(s for s in generate.load_state(tiny)["slots"] if s["done"])
    assert (
        "boundary particles outside the bounds of the rollout"
        in verify.check_rollout(tiny, meta, slot["params"])["problems"]
    )
    rep = generate.rewrite_bounds(tiny)
    assert rep["checked"] == 3
    assert rep["rewritten"] == [f.stem]
    assert rep["mismatched"] == []
    fixed = json.loads(f.read_text(encoding="utf-8"))
    assert fixed["bounds_m"][0] <= float(bnd[:, 0].min())
    assert fixed["store"]["sha256"] == meta["store"]["sha256"]  # the payload digest is the same: nothing re-written
    assert _digests(tiny) == before
    g = zarr.open_group(str(tiny / fixed["store"]["path"]), mode="r")
    assert np.asarray(g["positions"][:, : int((types == 0).sum()), :]).tobytes() == grains_before
    assert generate.rewrite_bounds(tiny)["rewritten"] == []  # idempotent
    for p in generate.rewrite_bounds(tiny)["proof"]:
        assert p["static_geometry_equals_stored"] is True


@pytest.mark.req("FR-011-03")
def test_011_b_a_stored_boundary_that_is_not_the_static_geometry_is_reported_and_left_alone(tiny: Path) -> None:
    import zarr

    f = sorted((tiny / "meta").glob("*.json"))[0]
    meta = json.loads(f.read_text(encoding="utf-8"))
    store = tiny / meta["store"]["path"]
    g = zarr.open_group(str(store), mode="r+")
    types = np.asarray(g["type_index"][:])
    start = int(np.flatnonzero(types == 1)[0])
    arr = np.asarray(g["positions"][:])
    arr[:, start] += 0.01  # the solid moved: not what the geometry says
    g["positions"][:] = arr
    meta["store"]["sha256"] = generate.store_digest(store)
    meta["bounds_m"][0] += 5.0  # and the box is wrong too
    f.write_text(json.dumps(meta), encoding="utf-8")
    snapshot = f.read_bytes()
    rep = generate.rewrite_bounds(tiny)
    assert rep["mismatched"] == [f.stem]
    assert f.read_bytes() == snapshot  # not rewritten on a guess


@pytest.mark.req("FR-011-03")
def test_011_b_the_command_line_has_the_requeue_flag_and_the_rewrite_command(tiny: Path, capsys) -> None:
    from pitstudio_studio.physics.planar import __main__ as cli

    assert cli.main(["rewrite-bounds", "--out", str(tiny)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["checked"] == 3
    assert out["rewritten"] == []
    assert out["mismatched"] == []
    parser_help = cli.build_parser().format_help()
    assert "rewrite-bounds" in parser_help
    gen_help = [a for a in cli.build_parser()._subparsers._group_actions[0].choices["generate"]._actions]
    assert any("--requeue-not-at-rest" in a.option_strings for a in gen_help)
