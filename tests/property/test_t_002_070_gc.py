# ruff: noqa: E501, PT018
"""T-002-070: `studio gc` (US-002-6, P2).

Requirements: FR-002-51, FR-002-52, P-002-11.

Expected behaviour (stated for the implementer; A = assumption listed in the red report):
  * `studio gc [--keep-last N] [--dry-run] [--verify] [--keep-pinned]` keeps every run that is pinned (a `PINNED` file in
    its run folder), listed in `web/public/assets/manifest.json` (`runs[].run_id`), the `run_id` of a
    `models/cards/*/manifest.json`, the run of a queued/running job, or among the newest N runs of its recipe (default 3,
    newest by run id); it deletes the run folders, index entries (`index/<aa>/<key>.json`) and cas objects reachable from
    no kept run (a kept run reaches the index entries of its stages' `cache_key`s and the objects of its stage outputs),
    and prints the bytes freed; `--dry-run` deletes nothing and prints what would be freed; `--verify` re-hashes every
    kept object and moves a mismatching one to `quarantine/`; `--keep-pinned` is accepted and always in effect;
  * A: the printed number of bytes freed counts the files removed from cas/, index/ and runs/ (any thousands separator);
  * gc exits 3 and deletes nothing when another worker holds `locks/worker.lock`.
Oracles: a hand-written reachability reference (tests/support/gc_world.py `reference`, FR-002-51 transcribed; the plan names
networkx for this, a hand-written set computation is the same oracle), byte counts measured on disk before and after,
Hypothesis over random store states (runs, pins, shared objects).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import psutil
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import contextlib

import gc_world as g
import runner_world as rw
from runner_world import recipe, stage


def rid(n: int, recipe_id: str) -> str:
    return f"20261001T00{n:02d}00Z-{recipe_id}"


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    sha = w.commit()
    yield w, sha
    rw.cleanup_world(w)


def reset(w: rw.World) -> None:
    shutil.rmtree(w.store, ignore_errors=True)
    w.store.mkdir(parents=True)
    for d in (w.repo / "models" / "cards").glob("card-*"):
        shutil.rmtree(d, ignore_errors=True)


def numbers(text: str) -> set[int]:
    return {int(re.sub(r"[,_ ]", "", m)) for m in re.findall(r"\d[\d,_]*", text) if re.sub(r"[,_ ]", "", m).isdigit()}


def scenario() -> list[g.SeedRun]:
    return [
        g.SeedRun(rid(0, "recipe-a"), "recipe-a", (8, 9)),  # oldest, unprotected, objects used by nobody else
        g.SeedRun(rid(1, "recipe-a"), "recipe-a", (0, 1), pinned=True),
        g.SeedRun(rid(2, "recipe-a"), "recipe-a", (1, 2), in_web=True),
        g.SeedRun(rid(3, "recipe-a"), "recipe-a", (3, 4)),
        g.SeedRun(rid(4, "recipe-a"), "recipe-a", (4, 5)),
        g.SeedRun(rid(5, "recipe-a"), "recipe-a", (3, 4)),  # same key as run 3: a cache hit on run 3's entry
        g.SeedRun(rid(1, "recipe-b"), "recipe-b", (6,), in_models=True),
        g.SeedRun(rid(2, "recipe-b"), "recipe-b", (7, 0)),
    ]


@pytest.mark.req("FR-002-51")
def test_fr_002_51_gc_keeps_pinned_indexed_carded_and_newest_runs_and_deletes_the_rest_exactly(world) -> None:
    w, sha = world
    runs = scenario()
    g.seed(w, runs, sha)
    ref = g.reference(runs, 2)
    assert not {rid(0, "recipe-a"), rid(3, "recipe-a")} & ref["runs"] and rid(1, "recipe-a") in ref["runs"], (
        "sanity of the oracle: runs 0 and 3 lose"
    )
    assert g.sha(g.POOL[8]) not in ref["objects"] and g.sha(g.POOL[3]) in ref["objects"]
    before = g.total_bytes(w.store)
    r = w.cli("gc", "--keep-last", "2")
    assert r.code == 0, r.text
    got = g.present(w.store)
    assert got["runs"] == ref["runs"] and got["keys"] == ref["keys"] and got["objects"] == ref["objects"]
    freed = before - g.total_bytes(w.store)
    assert freed > 0 and freed in numbers(r.out + r.err), f"the freed byte count {freed} must be printed: {r.out!r}"
    # run 3's index entry survives because run 5 (kept) reaches it by cache key, even though run 3's folder is gone
    assert (w.store / "index" / runs[2].key[:2] / f"{runs[2].key}.json").is_file()


@pytest.mark.req("FR-002-51")
def test_fr_002_51_every_kept_runs_outputs_still_materialise_with_their_recorded_digests(world) -> None:
    w, sha = world
    runs = scenario()
    g.seed(w, runs, sha)
    assert w.cli("gc", "--keep-last", "1").code == 0
    import json

    for d in (w.store / "runs").iterdir():
        m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        for s in m["stages"]:
            for o in s["outputs"]:
                data = (w.store / "cas" / "sha256" / o["sha256"][:2] / o["sha256"]).read_bytes()
                assert g.sha(data) == o["sha256"] and len(data) == o["bytes"]


@pytest.mark.req("FR-002-51")
def test_fr_002_51_dry_run_deletes_nothing_and_reports_the_same_number_a_real_run_frees(world) -> None:
    w, sha = world
    g.seed(w, scenario(), sha)
    snap = rw.tree_digest(w.store)
    before = g.total_bytes(w.store)
    dry = w.cli("gc", "--keep-last", "2", "--dry-run")
    assert dry.code == 0, dry.text
    assert rw.tree_digest(w.store) == snap, "dry run must not change the store"
    real = w.cli("gc", "--keep-last", "2")
    freed = before - g.total_bytes(w.store)
    assert freed in numbers(dry.out + dry.err) and freed in numbers(real.out + real.err)


@pytest.mark.req("FR-002-51")
@pytest.mark.req("P-002-11")
def test_p_002_11_a_second_gc_frees_nothing(world) -> None:
    w, sha = world
    g.seed(w, scenario(), sha)
    assert w.cli("gc", "--keep-last", "2").code == 0
    snap = rw.tree_digest(w.store)
    r = w.cli("gc", "--keep-last", "2")
    assert r.code == 0 and rw.tree_digest(w.store) == snap
    assert 0 in numbers(r.out + r.err), "prints 0 bytes freed"


@pytest.mark.req("FR-002-51")
def test_fr_002_51_default_keeps_the_newest_three_and_keep_pinned_is_accepted(world) -> None:
    w, sha = world
    runs = [g.SeedRun(rid(n, "recipe-a"), "recipe-a", (n % 8,)) for n in range(1, 8)]
    g.seed(w, runs, sha)
    assert w.cli("gc", "--keep-pinned").code == 0
    assert g.present(w.store)["runs"] == {rid(n, "recipe-a") for n in (5, 6, 7)}


@pytest.mark.req("FR-002-51")
def test_fr_002_51_keep_last_zero_keeps_only_what_is_pinned_or_referenced(world) -> None:
    w, sha = world
    runs = scenario()
    g.seed(w, runs, sha)
    assert w.cli("gc", "--keep-last", "0").code == 0
    assert (
        g.present(w.store)["runs"]
        == g.reference(runs, 0)["runs"]
        == {rid(1, "recipe-a"), rid(2, "recipe-a"), rid(1, "recipe-b")}
    )


@pytest.mark.req("FR-002-51")
def test_fr_002_51_verify_quarantines_a_corrupted_kept_object(world) -> None:
    w, sha = world
    runs = [
        g.SeedRun(rid(1, "recipe-a"), "recipe-a", (0, 1), pinned=True),
        g.SeedRun(rid(2, "recipe-a"), "recipe-a", (2,)),
    ]
    g.seed(w, runs, sha)
    victim = w.store / "cas" / "sha256" / g.sha(g.POOL[1])[:2] / g.sha(g.POOL[1])
    data = bytearray(victim.read_bytes())
    data[0] ^= 0xFF
    victim.write_bytes(bytes(data))
    r = w.cli("gc", "--keep-last", "1", "--verify")
    assert r.code == 0, r.text
    assert not victim.exists(), "the mismatching object leaves cas/"
    q = w.store / "quarantine"
    assert q.is_dir() and len([p for p in q.rglob("*") if p.is_file()]) == 1
    assert g.sha(g.POOL[0]) in g.present(w.store)["objects"], "intact kept objects stay"


@pytest.mark.req("FR-002-51")
def test_fr_002_51_stray_files_and_damaged_run_folders_never_crash_gc_and_pins_win(world) -> None:
    w, sha = world
    runs = [
        g.SeedRun(rid(1, "recipe-a"), "recipe-a", (0,), pinned=True),
        g.SeedRun(rid(2, "recipe-a"), "recipe-a", (1,)),
        g.SeedRun(rid(3, "recipe-a"), "recipe-a", (2,)),
    ]
    g.seed(w, runs, sha)
    (w.store / "runs" / "stray-notes.txt").write_text("hello", encoding="utf-8")
    (w.store / "runs" / "not-a-run-id").mkdir()
    (w.store / "runs" / rid(1, "recipe-a") / "manifest.json").write_text(
        "{corrupt", encoding="utf-8"
    )  # pinned AND damaged
    (w.store / "runs" / rid(2, "recipe-a") / "manifest.json").write_bytes(b"\xff\xfe")
    bad = w.store / "index" / "ab"
    bad.mkdir(parents=True)
    (bad / ("ab" + "0" * 62 + ".json")).write_text("not json", encoding="utf-8")
    r = w.cli("gc", "--keep-last", "1")
    assert r.code == 0 and "Traceback" not in r.text, r.text
    got = g.present(w.store)["runs"]
    assert rid(1, "recipe-a") in got, "a pinned run is kept even when its manifest cannot be read"
    assert rid(3, "recipe-a") in got, "the newest run is kept"


@pytest.mark.req("FR-002-51")
def test_fr_002_51_other_store_areas_are_left_alone(world) -> None:
    w, sha = world
    g.seed(w, scenario(), sha)
    (w.store / "publish" / "assets-v1.00.001").mkdir(parents=True)
    (w.store / "publish" / "assets-v1.00.001" / "big.bin").write_bytes(b"staged for the asset release")
    (w.store / "views" / "recipe-a" / "s10_preprocess").mkdir(parents=True)
    (w.store / "views" / "recipe-a" / "s10_preprocess" / "o.bin").write_bytes(b"view")
    (w.store / "quarantine").mkdir()
    (w.store / "quarantine" / "evidence").write_bytes(b"corrupted earlier")
    assert w.cli("gc", "--keep-last", "0").code == 0
    assert (w.store / "publish" / "assets-v1.00.001" / "big.bin").read_bytes() == b"staged for the asset release"
    assert (w.store / "quarantine" / "evidence").is_file()


# ---- FR-002-52 ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-52")
def test_fr_002_52_gc_exits_3_and_deletes_nothing_while_a_worker_holds_the_lock(world) -> None:
    from filelock import FileLock

    w, sha = world
    g.seed(w, scenario(), sha)
    (w.store / "locks").mkdir(exist_ok=True)
    snap = rw.tree_digest(w.store)
    with FileLock(w.store / "locks" / "worker.lock", timeout=0):
        r = w.cli("gc", "--keep-last", "0")
        assert r.code == 3, r.text
        dry = w.cli("gc", "--dry-run")
        assert dry.code == 3
    assert {k: v for k, v in rw.tree_digest(w.store).items() if not k.startswith("locks")} == {
        k: v for k, v in snap.items() if not k.startswith("locks")
    }


@pytest.mark.req("FR-002-51")
def test_fr_002_51_the_run_of_a_running_job_is_kept(world) -> None:
    w, sha = world
    runs = [g.SeedRun(rid(n, "recipe-a"), "recipe-a", (n % 8,)) for n in range(1, 5)]
    g.seed(w, runs, sha)
    w.write_recipe(
        recipe("live-one", [stage("s10_preprocess", timeout_s=120, params={"mode": "sleep", "sleep_s": 60})])
    )
    p = subprocess.Popen(
        [sys.executable, "-m", "pitstudio.runner", "run", str(w.recipes["live-one"]), "--profile", "test-profile"],
        env=w.env(),
        cwd=str(w.base),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert rw.wait_until(lambda: bool(w.ledger_rows()), 90, proc=p), "the stage did not start"
        live_run = max(d.name for d in (w.store / "runs").iterdir() if d.name.endswith("live-one"))
        psutil.Process(
            p.pid
        ).kill()  # the worker dies: the job stays `running` in the queue until the next worker starts
        p.wait(30)
        for r in w.ledger_rows():
            with contextlib.suppress(psutil.Error):
                psutil.Process(r["pid"]).kill()
        gc = w.cli("gc", "--keep-last", "0")
        assert gc.code == 0, gc.text
        got = g.present(w.store)["runs"]
        assert live_run in got, "a run whose job is queued or running is never collected"
        assert not {rid(n, "recipe-a") for n in range(1, 5)} & got, "unprotected old runs are collected"
    finally:
        if p.poll() is None:
            p.kill()


# ---- P-002-11 ------------------------------------------------------------------------------------------------------------------------------------
@st.composite
def states(draw: st.DrawFn) -> tuple[list[g.SeedRun], int]:
    n = draw(st.integers(0, 9))
    runs = []
    for i in range(n):
        recipe_id = draw(st.sampled_from(["recipe-a", "recipe-b"]))
        objs = tuple(sorted(draw(st.sets(st.integers(0, 7), min_size=1, max_size=3))))
        runs.append(
            g.SeedRun(
                rid(i, recipe_id),
                recipe_id,
                objs,
                pinned=draw(st.booleans()) and draw(st.booleans()),
                in_web=draw(st.integers(0, 4)) == 0,
                in_models=draw(st.integers(0, 4)) == 0,
            )
        )
    return runs, draw(st.integers(0, 3))


@pytest.mark.req("P-002-11")
def test_p_002_11_gc_is_safe_exact_and_idempotent_on_random_stores(world) -> None:
    w, sha = world

    @settings(max_examples=40, deadline=None)
    @given(state=states())
    def prop(state: tuple[list[g.SeedRun], int]) -> None:
        runs, keep = state
        reset(w)
        g.seed(w, runs, sha)
        ref = g.reference(runs, keep)
        r = w.cli("gc", "--keep-last", str(keep))
        assert r.code == 0, r.text
        got = g.present(w.store)
        assert got["runs"] == ref["runs"], "kept runs"
        assert got["keys"] == ref["keys"], "index entries reachable from kept runs"
        assert got["objects"] == ref["objects"], "objects reachable from kept runs"
        import json

        for run_id in got["runs"]:  # P-002-11: every kept run's outputs materialise with their recorded SHA-256
            m = json.loads((w.store / "runs" / run_id / "manifest.json").read_text(encoding="utf-8"))
            for o in (o for s in m["stages"] for o in s["outputs"]):
                blob = (w.store / "cas" / "sha256" / o["sha256"][:2] / o["sha256"]).read_bytes()
                assert g.sha(blob) == o["sha256"]
        snap = rw.tree_digest(w.store)
        again = w.cli("gc", "--keep-last", str(keep))
        assert again.code == 0 and rw.tree_digest(w.store) == snap, "a second gc frees 0 bytes"

    prop()
