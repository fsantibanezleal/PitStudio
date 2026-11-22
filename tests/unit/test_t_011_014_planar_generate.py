"""Planar reference-data generator, dataset side (T-011-014, FR-011-03, FR-011-14): payload, metadata, run, verification, GPU plumbing.

Not locked. A real (tiny) feed is generated on the Warp CPU device end to end: state, payload, metadata that passes the
DC-011-01 schema and the repo's strict loader, resume bookkeeping, and the verification that recomputes the rules from disk.
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

from pitstudio_studio.physics.planar import engine, generate, gpujob, space, verify  # noqa: E402

D = space.D


class _Guard:
    since = None
    paused_s = 0.0


class _Lock:
    released = 0

    def release(self) -> None:
        self.released += 1


def _session():
    lock = _Lock()
    return (lambda: (_Guard(), lock, engine.NoPacer())), lock


def _tiny_ranges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(space, "N_FEED", 24)
    monkeypatch.setitem(space.FEED_RANGES, "pile-formation", {"x_p_D": (0.0, 0.0), "z_o_D": (12.0, 13.0), "w_o_D": (10.0, 11.0)})
    monkeypatch.setattr(generate, "MIN_HEIGHT_D", 0.0)  # 24 grains are no 30 d pile: the floor is exercised through verify


@pytest.fixture(scope="module")
def tiny_run(tmp_path_factory: pytest.TempPathFactory):
    """One real pile geometry (3 seeds) generated on the CPU device."""
    mp = pytest.MonkeyPatch()
    _tiny_ranges(mp)
    out = tmp_path_factory.mktemp("planar") / "rollouts"
    session, lock = _session()
    args = generate.RunArgs(out=out, mu_r=1.0, mu_s=0.5, k_feed=3, limit_batches=1, families=("pile-formation",), phase="trainval", device="cpu")
    rc = generate.run(args, session=session)
    yield out, rc, lock
    mp.undo()


@pytest.mark.req("FR-011-03")
def test_011_a_run_writes_valid_rollouts_updates_the_state_and_releases_the_lock(tiny_run) -> None:
    out, rc, lock = tiny_run
    assert rc == 0 and lock.released >= 1
    st = generate.load_state(out)
    done = [s for s in st["slots"] if s["done"]]
    assert len(done) == 1 and done[0]["family"] == "pile-formation" and done[0]["split"] == "val"
    metas = sorted((out / "meta").glob("*.json"))
    assert len(metas) == 3 and not list((out / "meta").glob("*.tmp"))
    from pitstudio.granular.loader import validate_rollout_metadata

    for f in metas:
        meta = json.loads(f.read_text(encoding="utf-8"))
        generate.validate_meta(meta)
        validate_rollout_metadata(meta)
        assert meta["particle_types"] == ["grain"] and meta["dimensions"] == 2 and meta["particle_count"] == 24
        assert meta["geometry"]["pour_rate_m2_per_s"] == pytest.approx(done[0]["rate"])
        assert meta["geometry"]["pour_height_m"] == pytest.approx(done[0]["params"]["z_o_D"] * D)
        assert meta["store"]["sha256"] == generate.store_digest(out / meta["store"]["path"])
        assert meta["material"]["rolling_friction"]["value"] == 1.0 and meta["material"]["sliding_friction"]["value"] == 0.5
    assert st["contact"]["friction_rolling"] == 1.0 and st["solver_version"].startswith("pitstudio-dem-") and st["runs"][-1]["stop"] == "batch limit"


@pytest.mark.req("FR-011-03")
def test_011_a_state_made_with_another_contact_law_is_refused(tiny_run) -> None:
    out, _, _ = tiny_run
    session, _ = _session()
    with pytest.raises(SystemExit):
        generate.run(generate.RunArgs(out=out, mu_r=0.5, mu_s=0.5, limit_batches=1, families=("pile-formation",), device="cpu"), session=session)


@pytest.mark.req("FR-011-03")
def test_011_a_finished_geometry_is_not_issued_again_and_the_next_batch_continues(tiny_run) -> None:
    out, _, _ = tiny_run
    st = generate.load_state(out)
    pairs = generate.make_batch(st, "pile-formation", ("val",), 1)
    assert pairs and all(s["done"] is False for s, _ in pairs)
    assert {s["id"] for s, _ in pairs}.isdisjoint({s["id"] for s in st["slots"] if s["done"]})


@pytest.mark.req("FR-011-03")
def test_011_the_per_rollout_check_recomputes_rest_overflow_digest_and_the_pile_floor(tiny_run) -> None:
    out, _, _ = tiny_run
    st = generate.load_state(out)
    slot = next(s for s in st["slots"] if s["done"])
    meta = json.loads((out / "meta" / f"{slot['seeds'][0]['id']}.json").read_text(encoding="utf-8"))
    row = verify.check_rollout(out, meta, slot["params"])
    assert row["family"] == "pile-formation"
    assert row["overflow_fraction"] == 0.0 and row["left_in_feed_fraction"] <= 1.0 - engine.DISCHARGED_MIN
    assert any("30 d floor" in p for p in row["problems"])  # 24 grains are not a 30 d pile: the floor is checked from the payload
    assert not any("digest" in p or "schema" in p or "at rest" in p for p in row["problems"])
    # a corrupted payload is caught by the digest
    store = out / meta["store"]["path"]
    victim = next(p for p in sorted(store.rglob("*")) if p.is_file() and p.stat().st_size > 8 and "positions" in str(p))
    original = victim.read_bytes()
    victim.write_bytes(original[:-1] + bytes([original[-1] ^ 0xFF]))
    try:
        assert any("digest" in p for p in verify.check_rollout(out, meta, slot["params"])["problems"])
    finally:
        victim.write_bytes(original)


@pytest.mark.req("FR-011-03")
def test_011_verification_of_an_incomplete_set_reports_every_missing_rule_and_writes_the_card(tiny_run) -> None:
    out, _, _ = tiny_run
    report = verify.verify(out)
    assert report["ok"] is False
    text = "\n".join(report["problems"])
    assert "1 geometries on disk, 100 required" in text and "split by geometry" in text
    assert (out / "index.json").exists()
    card = (out / "DATASET_CARD.md").read_text(encoding="utf-8")
    assert "pitstudio_studio.physics.planar" in card and "27.2" in card and "pile-formation" in card


@pytest.mark.req("FR-011-03")
def test_011_the_machine_lock_plumbing_finds_filelock_in_a_named_site_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "filelock.py").write_text("class FileLock:\n    pass\n", encoding="utf-8")
    real_import = gpujob.importlib.import_module

    def fake(name: str, *a, **k):
        if name == "filelock" and str(site) not in sys.path:
            raise ImportError("no filelock here")
        return real_import(name, *a, **k)

    monkeypatch.setattr(gpujob.importlib, "import_module", fake)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delitem(sys.modules, "filelock", raising=False)
    monkeypatch.delenv(gpujob.FILELOCK_SITE_ENV, raising=False)
    with pytest.raises(RuntimeError, match=gpujob.FILELOCK_SITE_ENV):
        gpujob.import_filelock()
    monkeypatch.setenv(gpujob.FILELOCK_SITE_ENV, str(site))
    assert hasattr(gpujob.import_filelock(), "FileLock")
    monkeypatch.delitem(sys.modules, "filelock", raising=False)


@pytest.mark.req("FR-011-03")
def test_011_the_pacer_releases_the_lock_for_a_cooldown_and_takes_it_again() -> None:
    calls: list[str] = []

    class G:
        paused_s, max_temp = 0.0, 71

        def __init__(self) -> None:
            self.first = True

        def check(self) -> str:
            first, self.first = self.first, False
            return "cooldown" if first else "ok"

        def cool_down(self) -> None:
            calls.append("cool")

    class L:
        def release(self) -> None:
            calls.append("release")

        def acquire(self, timeout: int = 0) -> None:
            calls.append("acquire")

    p = gpujob.Pacer(G(), L())
    p.check()
    p.check()
    assert calls == ["release", "cool", "acquire"] and p.pauses_cool == 1 and p.max_temp == 71
    assert gpujob.load_guard_module().START_MAX_C == 80


@pytest.mark.req("FR-011-03")
def test_011_the_command_line_dry_run_exercises_the_real_code_path_on_the_cpu() -> None:
    from pitstudio_studio.physics.planar import __main__ as cli

    assert cli.main(["dry-run", "--allow-cpu"]) == 0
    assert np.isfinite(space.SimConfig(1.0, 0.5).dt)
