# ruff: noqa: E501, PT018
"""T-002-051: the run manifest and the event log (US-002-5).

Requirements: FR-002-46, FR-002-47, DC-002-04.

Expected behaviour (stated for the implementer):
  * every run maintains `runs/<run_id>/manifest.json` (spec 001 manifest `kind: run`, `published: false`), rewritten
    atomically at each stage end (a reader never sees a partial file; after a stage ends its record is already there),
    and `runs/<run_id>/events.jsonl`, one JSON object per line valid against contracts/events.schema.json#/$defs/event,
    `seq` strictly increasing, first event `run-started`, last `run-finished`;
  * `recipe` = {id, path relative to studio/recipes/, sha256 of the recipe file's bytes}, `git_sha`/`git_dirty` of the
    repository at start, `profile`, `seed` (recipe seed), `launcher`, `gpu`, `created` (UTC start);
  * each stage record: `tool`, `env` {name, python, lock_sha256 = SHA-256 of the environment's lock file bytes, versions =
    the versions of the packages named by the tool's registry entry, READ FROM THE LOCK (never typed)}, `cache_key`,
    `cache`, `status`, `exit_code`, `error_class`, `attempts`, `params`, derived `seed`, `determinism`, `performance`
    (copied from the tool's registry entry), `telemetry`, `thermal_flag`, `inputs`, `outputs`; `gpu.backend` is `fake`.
Oracles: the manifest/events schemas (Python `jsonschema`), lock files written by the fixture with known versions,
hashlib digests of the recipe and lock bytes, `git rev-parse HEAD`.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import itertools

import runner_world as rw
import schemas
from runner_world import recipe, stage, up


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


def two_stage() -> dict[str, Any]:
    return recipe(
        "manifest-me",
        [
            stage("st50_physics", gpu="exclusive", vram=2.0, params={"payload": "gpu"}),
            stage("s10_preprocess", inputs=[up("st50_physics", "out.bin")]),
            stage("st53_sensors", gpu="exclusive", vram=2.0, inputs=[up("s10_preprocess", "out.bin")]),
        ],
        seed=77,
    )


@pytest.mark.req("FR-002-46")
def test_fr_002_46_the_manifest_is_valid_and_carries_the_documented_run_facts(world) -> None:
    world.write_recipe(two_stage())
    head = world.commit()
    t0 = time.time()
    assert world.run("manifest-me").code == 0
    m = world.manifest()
    assert schemas.errors("manifest", m, "#/$defs/run") == []
    assert (m["kind"], m["published"], m["launcher"], m["profile"], m["seed"]) == (
        "run",
        False,
        "test",
        "test-profile",
        77,
    )
    assert m["run_id"] == world.last_run().name and re.fullmatch(r"\d{8}T\d{6}Z-manifest-me", m["run_id"])
    assert m["recipe"] == {
        "id": "manifest-me",
        "path": "cases/manifest-me.yaml",
        "sha256": sha(world.recipes["manifest-me"].read_bytes()),
    }
    assert m["git_sha"] == head and m["git_dirty"] is False
    assert re.fullmatch(r"\d+\.\d+\.\d+", m["runner_version"])
    import calendar

    created = calendar.timegm(time.strptime(m["created"][:19], "%Y-%m-%dT%H:%M:%S"))
    assert abs(created - t0) < 120, "created is the UTC start of the run"
    assert [s["key"]["id"] for s in m["stages"]] == ["st50_physics", "s10_preprocess", "st53_sensors"]
    assert m["artefacts"] == [] or isinstance(m["artefacts"], list)


@pytest.mark.req("FR-002-46")
def test_fr_002_46_git_dirty_reflects_uncommitted_changes(world) -> None:
    world.write_recipe(recipe("dirty", [stage("s10_preprocess")]))
    world.commit()
    (world.repo / "studio" / "src" / "__init__.py").write_text("# edited after the commit\n", encoding="utf-8")
    assert world.run("dirty").code == 0
    assert world.manifest()["git_dirty"] is True


@pytest.mark.req("FR-002-46")
def test_fr_002_46_the_manifest_is_rewritten_atomically_at_each_stage_end(world) -> None:
    long_tail = recipe(
        "watched",
        [
            stage("s10_preprocess"),
            stage(
                "s20_feature_extraction",
                inputs=[up("s10_preprocess", "out.bin")],
                params={"mode": "sleep", "sleep_s": 3.0},
            ),
        ],
    )
    world.write_recipe(long_tail)
    bad: list[str] = []
    seen: list[list[str]] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            for p in world.store.glob("runs/*/manifest.json"):
                try:
                    text = p.read_text(encoding="utf-8")
                except FileNotFoundError, PermissionError:
                    continue
                try:
                    doc = json.loads(text)
                except ValueError as e:
                    bad.append(f"partial manifest: {e}")
                    continue
                seen.append([f"{s['key']['id']}:{s['status']}" for s in doc.get("stages", [])])
                errs = schemas.errors("manifest", doc, "#/$defs/run")
                if errs:
                    bad.append(f"invalid manifest mid-run: {errs[:2]}")
            time.sleep(0.005)

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        assert world.run("watched").code == 0
    finally:
        stop.set()
        t.join(10)
    assert bad == [], bad[:3]
    assert ["s10_preprocess:succeeded"] in seen, "stage 1 was recorded in the manifest while stage 2 was still running"


@pytest.mark.req("FR-002-46")
def test_fr_002_46_events_are_valid_lines_with_strictly_increasing_seq_framed_by_run_started_and_run_finished(
    world,
) -> None:
    world.write_recipe(two_stage())
    assert world.run("manifest-me").code == 0
    raw = (world.last_run() / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ev = [json.loads(ln) for ln in raw]
    assert all(len(ln.encode()) <= 16384 for ln in raw)
    for e in ev:
        assert schemas.errors("events", e, "#/$defs/event") == [], e
        assert e["run_id"] == world.last_run().name
    seqs = [e["seq"] for e in ev]
    assert seqs[0] >= 1 and all(b > a for a, b in itertools.pairwise(seqs))
    assert ev[0]["type"] == "run-started" and ev[-1]["type"] == "run-finished"
    started = [e["stage"]["id"] for e in ev if e["type"] == "stage-started"]
    finished = [e["stage"]["id"] for e in ev if e["type"] == "stage-finished"]
    assert started == finished == ["st50_physics", "s10_preprocess", "st53_sensors"]
    assert all(e["t"] >= ev[0]["t"] for e in ev), "timestamps do not run backwards"


@pytest.mark.req("FR-002-46")
@pytest.mark.parametrize(
    ("label", "params", "code"),
    [
        ("failed", {"mode": "fail"}, 1),
        ("invalid-result", {"mode": "raw_result", "raw": "x"}, 1),
        ("not-run", {"mode": "notrun", "reason": "tool unavailable"}, 0),
        ("oom-then-fine", {"mode": "oom_if_big", "particles": 9, "limit": 5}, 0),
        ("missing-output", {"mode": "missing_output"}, 1),
    ],
)
def test_fr_002_46_manifests_of_every_outcome_validate_against_the_schema(
    world, label: str, params: dict[str, Any], code: int
) -> None:
    retry = [{"particles": 3}] if "particles" in params else None
    world.write_recipe(
        recipe(
            "outcomes",
            [
                stage("st50_physics", gpu="exclusive", vram=2.0, params=params, retry=retry),
                stage("s10_preprocess", inputs=[up("st50_physics", "out.bin")]),
            ],
        )
    )
    r = world.run("outcomes")
    assert r.code == code, f"{label}: {r.text}"
    m = world.manifest()
    assert schemas.errors("manifest", m, "#/$defs/run") == [], label
    ev = world.events()
    assert all(schemas.errors("events", e, "#/$defs/event") == [] for e in ev)


# ---- FR-002-47 ----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-47")
def test_fr_002_47_versions_are_read_from_the_lock_file_never_typed(world) -> None:
    world.write_recipe(recipe("versions", [stage("st50_physics", gpu="exclusive", vram=2.0)]))
    assert world.run("versions").code == 0
    rec = world.stage_record("st50_physics")
    lock = world.repo / "studio" / "uv.lock"
    assert rec["env"]["name"] == "studio" and rec["env"]["lock_sha256"] == sha(lock.read_bytes())
    assert rec["env"]["versions"].get("warp-lang") == "1.17.0"
    assert set(rec["env"]["versions"]) <= {"warp-lang", "pitstudio_stagekit", "pitstudio-stagekit", "pitstudio"}, (
        "only the tool's packages (and the stage helper)"
    )
    assert rec["tool"] == "warp"
    # change the version in the lock: the next run reports it (so nothing is typed in the runner)
    lock.write_text(
        lock.read_text(encoding="utf-8").replace('version = "1.17.0"', 'version = "9.9.9"'),
        encoding="utf-8",
        newline="\n",
    )
    time.sleep(1.1)
    assert world.run("versions").code == 0
    rec2 = world.stage_record("st50_physics")
    assert (
        rec2["env"]["versions"]["warp-lang"] == "9.9.9"
        and rec2["env"]["lock_sha256"] == sha(lock.read_bytes()) != rec["env"]["lock_sha256"]
    )


@pytest.mark.req("FR-002-47")
def test_fr_002_47_each_stage_reads_its_own_environments_lock(world) -> None:
    world.write_recipe(
        recipe(
            "envs",
            [
                stage("st50_physics", gpu="exclusive", vram=2.0),
                stage("st53_sensors", gpu="exclusive", vram=2.0),
                stage("s10_preprocess"),
            ],
        )
    )
    assert world.run("envs").code == 0
    by = {s["key"]["id"]: s for s in world.manifest()["stages"]}
    assert by["st53_sensors"]["env"]["name"] == "rtx" and by["st53_sensors"]["env"]["versions"].get("ovrtx") == "0.5.0"
    assert by["st53_sensors"]["env"]["lock_sha256"] == sha((world.repo / "studio" / "rtx" / "uv.lock").read_bytes())
    assert by["s10_preprocess"]["env"]["name"] == "pipeline" and by["s10_preprocess"]["env"]["lock_sha256"] == sha(
        (world.repo / "pipeline" / "uv.lock").read_bytes()
    )
    assert by["st50_physics"]["env"]["lock_sha256"] != by["st53_sensors"]["env"]["lock_sha256"]


@pytest.mark.req("FR-002-47")
def test_fr_002_47_performance_is_copied_from_the_tool_registry_and_the_backend_is_recorded(world) -> None:
    world.write_recipe(
        recipe(
            "perf", [stage("st50_physics", gpu="exclusive", vram=2.0), stage("st53_sensors", gpu="exclusive", vram=2.0)]
        )
    )
    assert world.run("perf").code == 0
    by = {s["key"]["id"]: s for s in world.manifest()["stages"]}
    assert by["st50_physics"]["performance"] == "public" and by["st53_sensors"]["performance"] == "local-only"
    assert world.manifest()["gpu"]["backend"] == "fake"
    # the registry decides: flip a tool to local-only and the next run follows it
    tools = world.repo / "studio" / "tools.yaml"
    tools.write_text(
        tools.read_text(encoding="utf-8").replace("performance: public", "performance: local-only"), encoding="utf-8"
    )
    time.sleep(1.1)
    assert world.run("perf").code == 0
    assert {s["performance"] for s in world.manifest()["stages"]} == {"local-only"}


@pytest.mark.req("FR-002-47")
def test_fr_002_47_outputs_and_cache_fields_are_recorded_per_stage(world) -> None:
    world.write_recipe(
        recipe("outs", [stage("s10_preprocess", files=["out.bin", "sub/meta.bin"], variant="a")], seed=5)
    )
    assert world.run("outs").code == 0
    rec = world.stage_record("s10_preprocess@a")
    assert (
        rec["cache"] == "miss"
        and re.fullmatch(r"[0-9a-f]{64}", rec["cache_key"])
        and rec["exit_code"] == 0
        and rec["error_class"] is None
    )
    assert [o["name"] for o in rec["outputs"]] == ["out.bin", "sub/meta.bin"]
    for o in rec["outputs"]:
        data = (world.store / "cas" / "sha256" / o["sha256"][:2] / o["sha256"]).read_bytes()
        assert sha(data) == o["sha256"] and len(data) == o["bytes"]
    seed = int.from_bytes(hashlib.sha256(rw.jcs_simple([5, "s10_preprocess@a", 0])).digest()[:8], "big") & (2**63 - 1)
    assert rec["seed"] == seed and rec["params"]["files"] == ["out.bin", "sub/meta.bin"]
    assert rec["determinism"]["class"] == "bitwise" and rec["thermal_flag"] is False and rec["telemetry"] is None
