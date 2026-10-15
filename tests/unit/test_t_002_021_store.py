# ruff: noqa: E501, PT018
"""T-002-021: the content-addressed store (US-002-3): hits, corruption, atomic promotion, invalid outputs, --force.

Requirements: FR-002-10, FR-002-11, FR-002-12, FR-002-13, FR-002-14, P-002-06.

Expected behaviour / layout (plan.md D3; assumptions marked A are listed in the red report):
  * `pitstudio.runner.cli.main(["run", <recipe>, "--profile", <id>, ["--force"]])` runs a foreground worker and returns
    the job's exit code (0 success, 1 a stage failed);
  * objects: `$PITSTUDIO_STORE/cas/sha256/<first two hex>/<digest>` (name = SHA-256 of content); index entries
    `index/<first two hex of key>/<cache key>.json` = {"stage": {...}, "outputs": [{"name", "sha256", "bytes"}],
    "run_id", "created"}; corrupted objects move to `quarantine/`; every run writes `runs/<run_id>/manifest.json`
    (stage records with `cache` hit|miss, `status`, `error_class`, `outputs`, `cache_key`) and `events.jsonl`;
  * A: current outputs are also visible under `views/<recipe id>/<stage key>/<output path>` (hard links or copies);
  * A: run ids are `YYYYMMDDTHHMMSSZ-<recipe>`; two runs of one recipe in the same second are NOT assumed to differ,
    so the tests wait for the next second between runs.
Oracles: hashlib SHA-256 of every object and of the bytes the fake stage writes (hand-derived from its documented
content rule), launcher/ledger counts, fault injection at every write/rename point in a fresh interpreter
(tests/support/fault_run.py), the invariant "every cas file is named by its content hash and every index entry
references only existing objects" (P-002-06).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import recipe, stage, up

SEED0 = 20261004


def ref_seed(seed0: int, key: str, i: int) -> int:
    return int.from_bytes(hashlib.sha256(rw.jcs_simple([seed0, key, i])).digest()[:8], "big") & (2**63 - 1)


def expected_bytes(stage_id: str, variant: str | None, name: str, payload: str = "x", shard: int = 0) -> bytes:
    """The fake stage's documented content rule (tests/support/ps_fake_stages/generic.py), seed derived by FR-002-09."""
    key = stage_id + (f"@{variant}" if variant else "")
    seed = ref_seed(SEED0, key, shard)
    return f"{stage_id}|{variant}|{seed}|{shard}|{name}|{payload}\n".encode()


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def cas_file(store: Path, digest: str) -> Path:
    return store / "cas" / "sha256" / digest[:2] / digest


def chain(payload2: str = "x") -> dict[str, Any]:
    return recipe(
        "chain",
        [
            stage("s10_preprocess", files=["out.bin", "sub/meta.bin"]),
            stage("s20_feature_extraction", inputs=[up("s10_preprocess", "out.bin")], params={"payload": payload2}),
        ],
        seed=SEED0,
    )


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path, recipes=[chain()])
    yield w
    rw.cleanup_world(w)


def next_second() -> None:
    time.sleep(1.1)


def stage_launches(spy: rw.PopenSpy) -> int:
    return sum(1 for a in spy.argv_lists() if "ps_fake_stages.generic" in " ".join(a))


def objects(store: Path) -> set[str]:
    d = store / "cas" / "sha256"
    return {f.name for f in d.rglob("*") if f.is_file()} if d.is_dir() else set()


def index_files(store: Path) -> list[Path]:
    d = store / "index"
    return sorted(d.rglob("*.json")) if d.is_dir() else []


# ---- FR-002-10 ---------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-10")
def test_fr_002_10_second_run_is_all_hits_launches_nothing_and_materialises_identical_outputs(world) -> None:
    r1 = world.run("chain")
    assert r1.code == 0, r1.text
    assert len(world.starts()) == 2
    m1 = world.manifest()
    good = expected_bytes("s10_preprocess", None, "out.bin")
    assert sha(good) in objects(world.store)
    next_second()
    spy = rw.PopenSpy(world.monkeypatch)
    r2 = world.run("chain")
    assert r2.code == 0, r2.text
    assert stage_launches(spy) == 0 and len(world.starts()) == 2, "a hit must not launch a stage process"
    m2 = world.manifest()
    assert m2["run_id"] != m1["run_id"]
    for s1, s2 in zip(m1["stages"], m2["stages"], strict=True):
        assert (s2["cache"], s2["status"]) == ("hit", "succeeded")
        assert s2["cache_key"] == s1["cache_key"]
        assert s2["outputs"] == s1["outputs"]
        for o in s2["outputs"]:
            data = cas_file(world.store, o["sha256"]).read_bytes()
            assert sha(data) == o["sha256"] and len(data) == o["bytes"]
    view = world.store / "views" / "chain" / "s10_preprocess" / "out.bin"
    assert view.read_bytes() == good
    assert (world.store / "views" / "chain" / "s10_preprocess" / "sub" / "meta.bin").read_bytes() == expected_bytes(
        "s10_preprocess", None, "sub/meta.bin"
    )
    assert any(e["type"] == "stage-cache-hit" for e in world.events())


@pytest.mark.req("FR-002-10")
def test_fr_002_10_a_missing_object_is_a_miss_not_a_crash(world) -> None:
    assert world.run("chain").code == 0
    victim = cas_file(world.store, sha(expected_bytes("s10_preprocess", None, "out.bin")))
    victim.unlink()
    next_second()
    assert world.run("chain").code == 0
    assert victim.is_file() and sha(victim.read_bytes()) == victim.name
    assert [r["stage"]["id"] for r in world.starts()].count("s10_preprocess") == 2


# ---- FR-002-11 ---------------------------------------------------------------------------------------------------------
def corrupt_same_size(p: Path) -> None:
    b = bytearray(p.read_bytes())
    b[0] ^= 0xFF
    p.write_bytes(bytes(b))


def corrupt_append(p: Path) -> None:
    p.write_bytes(p.read_bytes() + b"!")


def corrupt_truncate(p: Path) -> None:
    p.write_bytes(b"")


@pytest.mark.req("FR-002-11")
@pytest.mark.parametrize(
    "damage", [corrupt_same_size, corrupt_append, corrupt_truncate], ids=["same-size", "grown", "emptied"]
)
def test_fr_002_11_corrupted_object_is_a_miss_is_quarantined_and_never_handed_to_a_stage(world, damage: Any) -> None:
    assert world.run("chain").code == 0
    good = expected_bytes("s10_preprocess", None, "out.bin")
    obj = cas_file(world.store, sha(good))
    damage(obj)
    # s20 becomes a miss too (its parameter changes), so it needs s10's output as input
    world.write_recipe(chain(payload2="changed"))
    world.ledger.unlink()
    next_second()
    r = world.run("chain")
    assert r.code == 0, r.text
    ev = world.events()
    assert any(e["type"] == "store-corrupt" for e in ev), [e["type"] for e in ev]
    q = world.store / "quarantine"
    assert q.is_dir() and any(q.iterdir()), "the corrupted object must be moved to quarantine/"
    assert obj.is_file() and obj.read_bytes() == good, "the object is rebuilt from a fresh execution"
    s20 = [r_ for r_ in world.starts() if r_["stage"]["id"] == "s20_feature_extraction"]
    assert len(s20) == 1
    (inp,) = s20[0]["inputs"]
    assert inp["actual"] == inp["declared"] == sha(good), "a stage may only ever read verified bytes"
    assert rw.cas_violations(world.store) == []


@pytest.mark.req("FR-002-11")
@pytest.mark.parametrize(
    "garbage",
    [
        b"",
        b"{not json",
        b"\xff\xfe\x00",
        b'{"outputs": [{"name": "out.bin", "sha256": "' + b"0" * 64 + b'", "bytes": 1}]}',
        b"[]",
        b"null",
    ],
    ids=["empty", "truncated", "binary", "points-at-nothing", "list", "null"],
)
def test_fr_002_11_a_damaged_index_entry_is_a_miss_and_is_replaced(world, garbage: bytes) -> None:
    assert world.run("chain").code == 0
    entries = index_files(world.store)
    assert len(entries) == 2
    for e in entries:
        e.write_bytes(garbage)
    next_second()
    r = world.run("chain")
    assert r.code == 0, r.text
    assert "Traceback" not in r.text
    assert len(world.starts()) == 4, "both stages re-executed"
    assert rw.cas_violations(world.store) == []
    for e in index_files(world.store):
        json.loads(e.read_text(encoding="utf-8"))


# ---- FR-002-12 / FR-002-13 ---------------------------------------------------------------------------------------------
def invalid_case(name: str) -> tuple[dict[str, Any], str]:
    """(recipe, expected error class) for each way an output can be invalid."""
    two_files = ["out.bin", "second.bin"]
    cases: dict[str, tuple[dict[str, Any], str]] = {
        "missing": (stage("s10_preprocess", files=two_files, params={"mode": "missing_output"}), "invalid-output"),
        "empty-file": (stage("s10_preprocess", files=two_files, params={"mode": "empty_output"}), "invalid-output"),
        "bad-json": (
            stage("s10_preprocess", files=two_files, params={"mode": "bad_json_output"}, validator="json"),
            "invalid-output",
        ),
        "bad-jsonl": (
            stage("s10_preprocess", files=two_files, params={"text": '{"a": 1}\n{broken\n'}, validator="jsonl"),
            "invalid-output",
        ),
        "contract-mismatch": (
            stage("s10_preprocess", files=two_files, params={"text": '{"nope": 1}'}, validator="contract-capabilities"),
            "invalid-output",
        ),
        "stage-side-unvalidated": (stage("s10_preprocess", files=two_files, validator="stage-fake"), "invalid-output"),
        "stage-side-false": (
            stage(
                "s10_preprocess",
                files=two_files,
                validator="stage-fake",
                params={"validated": False, "validator_id": "stage-fake"},
            ),
            "invalid-output",
        ),
    }
    return recipe(
        "invalid",
        [cases[name][0], stage("s20_feature_extraction", inputs=[up("s10_preprocess", "out.bin")])],
        seed=SEED0,
    ), cases[name][1]


INVALID = [
    "missing",
    "empty-file",
    "bad-json",
    "bad-jsonl",
    "contract-mismatch",
    "stage-side-unvalidated",
    "stage-side-false",
]


@pytest.mark.req("FR-002-13")
@pytest.mark.parametrize("name", INVALID)
def test_fr_002_13_invalid_output_fails_the_stage_enters_nothing_in_the_store_and_skips_descendants(
    world, name: str
) -> None:
    doc, klass = invalid_case(name)
    world.write_recipe(doc)
    r = world.run("invalid")
    assert r.code == 1, r.text
    s10 = world.stage_record("s10_preprocess")
    assert (s10["status"], s10["error_class"]) == ("failed", klass)
    assert s10["outputs"] == []
    assert world.stage_record("s20_feature_extraction")["status"] == "skipped"
    assert len(world.starts()) == 1, "descendants of a failed stage never start"
    assert objects(world.store) == set(), "no output of a failed execution may enter the store"
    assert index_files(world.store) == []
    assert rw.cas_violations(world.store) == []


@pytest.mark.req("FR-002-13")
def test_fr_002_13_a_valid_output_next_to_an_invalid_one_is_not_promoted_either(world) -> None:
    doc, _ = invalid_case("missing")
    world.write_recipe(doc)
    assert world.run("invalid").code == 1
    first_good = sha(expected_bytes("s10_preprocess", None, "out.bin"))
    assert first_good not in objects(world.store)


def can_symlink(tmp: Path) -> bool:
    try:
        (tmp / "t").write_text("x")
        os.symlink(tmp / "t", tmp / "l")
        return True
    except OSError:
        return False


@pytest.mark.req("FR-002-13")
@pytest.mark.parametrize("mode", ["link_output", "escape_output"])
def test_fr_002_13_a_link_or_a_path_resolving_outside_the_stage_folder_is_rejected(
    world, tmp_path: Path, mode: str
) -> None:
    # A symlink needs a privilege Windows may not grant: then the fake stage uses a directory junction instead, which
    # makes the declared output resolve outside the stage folder (the same clause of FR-002-13).
    out_path = "out.bin" if (mode == "link_output" and can_symlink(tmp_path)) else "jdir/secret.bin"
    st = stage(
        "s10_preprocess", params={"mode": mode, "files": [out_path]}, outputs=[{"path": out_path, "schema": "file"}]
    )
    world.write_recipe(
        recipe("linky", [st, stage("s20_feature_extraction", inputs=[up("s10_preprocess", out_path)])], seed=SEED0)
    )
    r = world.run("linky")
    assert r.code == 1, r.text
    s10 = world.stage_record("s10_preprocess")
    assert (s10["status"], s10["error_class"]) == ("failed", "invalid-output")
    assert world.stage_record("s20_feature_extraction")["status"] == "skipped"
    assert sha(b"outside the stage folder") not in objects(world.store), (
        "bytes outside the stage folder must never be stored"
    )
    assert objects(world.store) == set()


@pytest.mark.req("FR-002-13")
@pytest.mark.parametrize(
    ("validator", "params"),
    [
        ("json", {"text": '{"a": [1, 2, {"b": null}]}'}),
        ("jsonl", {"text": '{"a": 1}\n{"b": 2}\n'}),
        ("contract-capabilities", {"text": json.dumps(rw.capabilities_doc())}),
        ("stage-fake", {"validated": True, "validator_id": "stage-fake"}),
        ("file", {"text": "x"}),
    ],
)
def test_fr_002_12_every_validator_accepts_a_valid_output(world, validator: str, params: dict[str, Any]) -> None:
    world.write_recipe(recipe("valid", [stage("s10_preprocess", validator=validator, params=params)], seed=SEED0))
    r = world.run("valid")
    assert r.code == 0, r.text
    (rec,) = world.manifest()["stages"]
    assert rec["status"] == "succeeded" and len(rec["outputs"]) == 1


@pytest.mark.req("FR-002-12")
def test_fr_002_12_a_stage_writes_only_inside_its_execution_folder_and_outputs_are_promoted_by_digest(world) -> None:
    assert world.run("chain").code == 0
    run_dir = world.last_run()
    folder = run_dir / "tmp" / "s10_preprocess" / "0"
    assert folder.is_dir() and (folder / "job.json").is_file()
    assert sorted(p.name for p in objects_dir_files(world.store)) == sorted(
        o["sha256"] for s in world.manifest()["stages"] for o in s["outputs"]
    )
    for o in world.manifest()["stages"][0]["outputs"]:
        assert o["name"] in ("out.bin", "sub/meta.bin")
        assert cas_file(world.store, o["sha256"]).stat().st_size == o["bytes"]


def objects_dir_files(store: Path) -> list[Path]:
    d = store / "cas" / "sha256"
    return [f for f in d.rglob("*") if f.is_file()] if d.is_dir() else []


# ---- P-002-06: atomic promotion under injected faults -------------------------------------------------------------------
def fault_run(world: rw.World, fail_at: int, *argv: str) -> dict[str, Any]:
    r = subprocess.run(
        [sys.executable, str(rw.SUPPORT / "fault_run.py"), str(fail_at), *argv],
        capture_output=True, text=True, env=world.env(), cwd=str(world.base), timeout=180,
    )  # fmt: skip
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("FAULT-RESULT ")]
    assert lines, f"no result line: {r.stdout[-500:]} {r.stderr[-500:]}"
    return json.loads(lines[-1].removeprefix("FAULT-RESULT "))


def reset_store(world: rw.World) -> None:
    shutil.rmtree(world.store, ignore_errors=True)
    world.store.mkdir(parents=True)
    if world.ledger.exists():
        world.ledger.unlink()


@pytest.mark.req("P-002-06")
@pytest.mark.req("FR-002-12")
def test_p_002_06_no_interruption_point_leaves_a_partial_object_or_a_dangling_index_entry(world) -> None:
    two = recipe("faulty", [stage("s10_preprocess", files=["out.bin", "sub/meta.bin"])], seed=SEED0)
    world.write_recipe(two)
    argv = ("run", str(world.recipes["faulty"]), "--profile", "test-profile")
    clean = fault_run(world, -1, *argv)
    assert clean["code"] == 0, clean
    total = clean["ticks"]
    assert total >= 6, f"a promotion of two outputs plus an index entry needs several writes/renames, saw {total}"
    expected = {sha(expected_bytes("s10_preprocess", None, n)) for n in ("out.bin", "sub/meta.bin")}
    assert expected <= objects(world.store)
    points = sorted({0, 1, 2, total - 1, *(int(total * i / 12) for i in range(13))} & set(range(total)))
    fired = 0
    for k in points:
        reset_store(world)
        res = fault_run(world, k, *argv)
        fired += res["fired"]
        assert rw.cas_violations(world.store) == [], (
            f"fault at write #{k}: {rw.cas_violations(world.store)} (run result {res})"
        )
        # the next run, with no fault, completes and repairs everything (a later second: run ids carry the start second)
        time.sleep(1.05)
        ok = fault_run(world, -1, *argv)
        assert ok["code"] == 0, f"fault at #{k}: the clean re-run did not succeed: {ok}"
        assert rw.cas_violations(world.store) == []
        assert expected <= objects(world.store)
    assert fired >= len(points) // 2, "most injected faults must actually fire"


# ---- FR-002-14: --force ----------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-14")
def test_fr_002_14_force_executes_even_on_a_hit_and_the_index_points_to_the_new_run(world) -> None:
    assert world.run("chain").code == 0
    first = world.last_run().name
    keys = {s["key"]["id"]: s["cache_key"] for s in world.manifest()["stages"]}
    assert len(world.starts()) == 2
    next_second()
    assert world.run("chain", "--force").code == 0
    assert len(world.starts()) == 4, "--force executes every selected stage even on a hit"
    second = world.last_run().name
    assert second != first
    entry = json.loads(
        (world.store / "index" / keys["s10_preprocess"][:2] / f"{keys['s10_preprocess']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert entry["run_id"] == second
    assert rw.cas_violations(world.store) == []


@pytest.mark.req("FR-002-14")
def test_fr_002_14_a_failing_forced_execution_leaves_the_old_index_entry_untouched(world) -> None:
    assert world.run("chain").code == 0
    entries = {p: p.read_bytes() for p in index_files(world.store)}
    before_objects = objects(world.store)
    assert len(entries) == 2
    world.monkeypatch.setenv("PS_FAKE_FAIL", "1")  # stages now fail, but only when actually executed
    next_second()
    r = world.run("chain", "--force")
    assert r.code == 1, r.text
    assert {p: p.read_bytes() for p in index_files(world.store)} == entries, (
        "index entries are replaced only after promotion"
    )
    assert objects(world.store) == before_objects
    assert rw.cas_violations(world.store) == []
    world.monkeypatch.delenv("PS_FAKE_FAIL")
    next_second()
    spy = rw.PopenSpy(world.monkeypatch)
    assert world.run("chain").code == 0
    assert stage_launches(spy) == 0, "the old entries still serve hits"
