# ruff: noqa: E501, PT018
"""T-002-040: how a stage process is launched, the job spec it receives, hostile result files, runner overhead.

Requirements: FR-002-24, FR-002-25, NFR-002-03.

Expected API (stated for the implementer):
  * `pitstudio.runner.execute.build_command(*, launcher: str, repo: Path, env: str, entry: str, job_path: Path)
    -> list[str]`: launcher "uv" gives `["uv", "run", "--project", <repo>/<project dir of plan.md D7>, "--frozen",
    "python", "-m", entry, "--job", str(job_path)]` (the first element may be an absolute path to uv); launcher "test"
    gives `[sys.executable, "-m", entry, "--job", str(job_path)]`; never a string, never `shell=True`;
  * a stage process (observed from inside by tests/support/ps_fake_stages/generic.py) sees the environment variables
    PITSTUDIO_RUN_ID (the run id), PITSTUDIO_STAGE (stage key), PITSTUDIO_SHARD (shard index first),
    PITSTUDIO_SEED (derived seed, decimal), PITSTUDIO_NVTX_RANGE (equal to the job spec's `nvtx_range`),
    PITSTUDIO_CPU_SLOTS (integer >= 1), PITSTUDIO_VRAM_FRACTION (GPU stages only: 0 < x <= 1),
    CUDA_VISIBLE_DEVICES ("0" for a GPU stage) and a PYTHONPATH entry that holds `pitstudio_stagekit.py`;
  * the job spec the stage reads is valid against contracts/job.schema.json#/$defs/job_spec and states the effective
    parameters, the derived seed, the verified input files and `output_dir` = `<store>/runs/<run_id>/tmp/<stage key>/<shard>`;
  * a stage that exits without a valid `result.json` fails with `error_class: invalid-result` (FR-002-25).
Oracles: the plan.md D7 table written out by hand, the job schema (Python `jsonschema`), the seed formula of FR-002-09
recomputed with hashlib, hostile result files built by hand.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
import schemas
from runner_world import PopenSpy, recipe, stage, up


def ref_seed(seed0: int, key: str, i: int) -> int:
    return int.from_bytes(hashlib.sha256(rw.jcs_simple([seed0, key, i])).digest()[:8], "big") & (2**63 - 1)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


# ---- the argument list -----------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-24")
@pytest.mark.parametrize("env", rw.ALL_ENVS)
def test_fr_002_24_uv_command_line_per_environment_follows_plan_d7(tmp_path: Path, env: str) -> None:
    from pitstudio.runner import execute

    job = tmp_path / "job.json"
    argv = execute.build_command(
        launcher="uv", repo=tmp_path, env=env, entry="pitstudio_studio.stages.demo", job_path=job
    )
    assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
    assert Path(argv[0]).stem.lower() == "uv"
    assert argv[1:3] == ["run", "--project"]
    assert Path(argv[3]) == tmp_path / rw.ENV_PROJECT[env]
    assert argv[4:] == ["--frozen", "python", "-m", "pitstudio_studio.stages.demo", "--job", str(job)]


@pytest.mark.req("FR-002-24")
def test_fr_002_24_test_launcher_uses_the_current_interpreter_and_never_a_shell(tmp_path: Path) -> None:
    from pitstudio.runner import execute

    job = tmp_path / "job.json"
    assert execute.build_command(launcher="test", repo=tmp_path, env="studio", entry="a.b", job_path=job) == [
        sys.executable,
        "-m",
        "a.b",
        "--job",
        str(job),
    ]


@pytest.mark.req("FR-002-24")
def test_fr_002_24_a_real_launch_passes_the_documented_environment_and_a_valid_job_spec(world) -> None:
    world.write_recipe(
        recipe(
            "launch",
            [
                stage("s10_preprocess", variant="alpha", params={"payload": "p1", "mode": "ok"}),
                stage(
                    "st50_physics",
                    gpu="exclusive",
                    vram=6.0,
                    shardable=(10, 20),
                    inputs=[up("s10_preprocess", "out.bin", "alpha")],
                    params={"payload": "gpu"},
                ),
            ],
            seed=20261004,
        )
    )
    spy = PopenSpy(world.monkeypatch)
    r = world.run("launch")
    assert r.code == 0, r.text
    for args, kw in spy.calls:
        assert isinstance(args, (list, tuple)), "never a command string"
        assert not kw.get("shell"), "never through a shell"
    rows = world.starts()
    assert len(rows) == 3  # one CPU execution and two GPU shards
    run_id = world.last_run().name
    cpu = next(x for x in rows if x["stage"]["id"] == "s10_preprocess")
    gpus = sorted((x for x in rows if x["stage"]["id"] == "st50_physics"), key=lambda x: x["shard"])
    for row in rows:
        env = row["env"]
        assert env["PITSTUDIO_RUN_ID"] == run_id
        key = row["stage"]["id"] + (f"@{row['stage']['variant']}" if row["stage"].get("variant") else "")
        assert env["PITSTUDIO_STAGE"] == key
        assert int(env["PITSTUDIO_SEED"]) == row["seed"] == ref_seed(20261004, key, row["shard"])
        assert int(re.match(r"\d+", env["PITSTUDIO_SHARD"]).group()) == row["shard"]
        assert 1 <= int(env["PITSTUDIO_CPU_SLOTS"]) <= 4
        assert env["PITSTUDIO_NVTX_RANGE"] == row["job"]["nvtx_range"] and 0 < len(env["PITSTUDIO_NVTX_RANGE"]) <= 200
        kit_dirs = [
            p for p in env["PYTHONPATH"].split(os.pathsep) if p and (Path(p) / "pitstudio_stagekit.py").is_file()
        ]
        assert kit_dirs, f"PYTHONPATH must contain the stage helper folder: {env['PYTHONPATH']}"
    assert "PITSTUDIO_VRAM_FRACTION" not in cpu["env"]
    for g in gpus:
        assert 0 < float(g["env"]["PITSTUDIO_VRAM_FRACTION"]) <= 1
        assert g["env"]["CUDA_VISIBLE_DEVICES"] == "0"
        assert g["job"]["vram_fraction"] == pytest.approx(float(g["env"]["PITSTUDIO_VRAM_FRACTION"]))
    # job specs: schema-valid, effective parameters, derived seeds, verified inputs, execution folder
    for row in rows:
        job = row["job"]
        assert schemas.errors("job", job, "#/$defs/job_spec") == []
        assert job["run_id"] == run_id and job["entry"] == "ps_fake_stages.generic"
        assert job["profile"] == {"id": "test-profile", "cpu_slots": 4}
        assert (job["resume"], job["rerun"], job["profiling"]) == (False, False, False)
        assert job["output_dir"].endswith(f"/runs/{run_id}/tmp/{row['env']['PITSTUDIO_STAGE']}/{row['shard']}")
    assert cpu["job"]["shard"] is None and cpu["job"]["vram_fraction"] is None and cpu["job"]["inputs"] == []
    assert cpu["job"]["params"]["payload"] == "p1" and cpu["job"]["stage"] == {
        "id": "s10_preprocess",
        "variant": "alpha",
    }
    assert [g["job"]["shard"] for g in gpus] == [
        {"index": 0, "size": 10, "total": 20},
        {"index": 1, "size": 10, "total": 20},
    ]
    out_sha = hashlib.sha256(f"s10_preprocess|alpha|{cpu['seed']}|0|out.bin|p1\n".encode()).hexdigest()
    for g in gpus:
        (inp,) = g["inputs"]
        assert inp["name"] == "s10_preprocess@alpha/out.bin" and inp["declared"] == inp["actual"] == out_sha
        assert g["job"]["inputs"][0]["name"] == inp["name"] and g["job"]["inputs"][0]["sha256"] == out_sha


# ---- FR-002-25: hostile result.json --------------------------------------------------------------------------------------------------
GOOD_FAILED = '{"schema_version":"1.0","status":"failed","error_class":"unknown","outputs":[],"checkpoint":false}'
GOOD_OK = (
    '{"schema_version":"1.0","status":"succeeded","error_class":null,"outputs":[{"path":"out.bin"}],"checkpoint":false}'
)
HOSTILE_RESULTS: list[tuple[str, dict[str, Any]]] = [
    ("absent", {"mode": "no_result"}),
    ("empty-file", {"mode": "raw_result", "raw": ""}),
    ("not-json", {"mode": "raw_result", "raw": "{not json"}),
    ("json-array", {"mode": "raw_result", "raw": "[1, 2]"}),
    ("json-null", {"mode": "raw_result", "raw": "null"}),
    (
        "nan-constant",
        {
            "mode": "raw_result",
            "raw": GOOD_OK.replace('"checkpoint":false', '"checkpoint":false,"observables":{"a":NaN}'),
        },
    ),
    ("unknown-status", {"mode": "raw_result", "raw": GOOD_OK.replace("succeeded", "ok")}),
    ("missing-required-field", {"mode": "raw_result", "raw": '{"schema_version":"1.0","status":"succeeded"}'}),
    (
        "unknown-field",
        {"mode": "raw_result", "raw": GOOD_OK.replace('"checkpoint":false', '"checkpoint":false,"extra":1')},
    ),
    (
        "error-class-on-success",
        {"mode": "raw_result", "raw": GOOD_OK.replace('"error_class":null', '"error_class":"oom"')},
    ),
    (
        "failed-without-error-class",
        {"mode": "raw_result", "raw": GOOD_FAILED.replace('"unknown"', "null"), "exit_code": 1},
    ),
    (
        "unknown-error-class",
        {"mode": "raw_result", "raw": GOOD_FAILED.replace('"unknown"', '"gremlins"'), "exit_code": 1},
    ),
    ("output-path-traversal", {"mode": "raw_result", "raw": GOOD_OK.replace("out.bin", "../x.bin")}),
    ("outputs-wrong-type", {"mode": "raw_result", "raw": GOOD_OK.replace('[{"path":"out.bin"}]', '"out.bin"')}),
    ("oversized-over-65536-bytes", {"mode": "big_result"}),
    ("succeeded-but-exit-1", {"mode": "exit_nonzero_ok_result"}),
    ("failed-but-exit-0", {"mode": "raw_result", "raw": GOOD_FAILED, "exit_code": 0}),
    ("binary-garbage", {"mode": "raw_result", "raw": "\u0000\u0001\u0002" * 50}),
]


@pytest.mark.req("FR-002-25")
@pytest.mark.parametrize(("label", "params"), HOSTILE_RESULTS, ids=[h[0] for h in HOSTILE_RESULTS])
def test_fr_002_25_a_missing_invalid_oversized_or_inconsistent_result_is_invalid_result(
    world, label: str, params: dict[str, Any]
) -> None:
    world.write_recipe(
        recipe(
            "hostile",
            [
                stage("s10_preprocess", params=params),
                stage("s20_feature_extraction", inputs=[up("s10_preprocess", "out.bin")]),
            ],
        )
    )
    r = world.run("hostile")
    assert r.code == 1, f"{label}: {r.text}"
    rec = world.stage_record("s10_preprocess")
    assert (rec["status"], rec["error_class"]) == ("failed", "invalid-result"), (
        label,
        rec["status"],
        rec["error_class"],
    )
    assert world.stage_record("s20_feature_extraction")["status"] == "skipped"
    assert len(world.starts()) == 1
    assert not (world.store / "cas").exists() or not [f for f in (world.store / "cas").rglob("*") if f.is_file()], (
        "nothing is promoted"
    )


@pytest.mark.req("FR-002-25")
def test_fr_002_25_a_consistent_failure_is_not_an_invalid_result(world) -> None:
    world.write_recipe(recipe("honest-fail", [stage("s10_preprocess", params={"mode": "fail"})]))
    assert world.run("honest-fail").code == 1
    assert world.stage_record("s10_preprocess")["error_class"] != "invalid-result"


# ---- NFR-002-03: overhead per execution -----------------------------------------------------------------------------------------------
@pytest.mark.req("NFR-002-03")
def test_nfr_002_03_runner_overhead_per_stage_execution_is_at_most_one_second(world) -> None:
    n = 5
    big = {"repeat": 20000, "payload": "pad"}  # about 1 MB of output per stage
    world.write_recipe(recipe("warm", [stage("s10_preprocess", params={"payload": "warm"})]))
    assert world.run("warm").code == 0  # imports, caches and the database are warmed up
    time.sleep(1.1)
    stages = [stage("s10_preprocess", variant="v0", params=big)]
    stages += [
        stage("s10_preprocess", variant=f"v{i}", params=big, inputs=[up("s10_preprocess", "out.bin", f"v{i - 1}")])
        for i in range(1, n)
    ]
    world.write_recipe(recipe("overhead", stages))
    t0 = time.perf_counter()
    r = world.run("overhead")
    total = time.perf_counter() - t0
    assert r.code == 0, r.text
    m = world.manifest()
    assert all(s["outputs"][0]["bytes"] >= 900_000 for s in m["stages"]), "each stage promotes about 1 MB"
    if all("wall_s" in s for s in m["stages"]):
        own = sum(s["wall_s"] for s in m["stages"])  # process lifetime as measured by the runner
    else:  # fall back to the time between the first and last ledger line of each stage process
        rows = world.ledger_rows()
        own = sum(
            (e["t_ns"] - s["t_ns"]) / 1e9
            for s in rows
            if s["event"] == "start"
            for e in rows
            if e["event"] == "end" and e["pid"] == s["pid"]
        )
    overhead = (total - own) / n
    assert overhead <= 1.0, f"overhead per execution {overhead:.2f}s (total {total:.2f}s, stages {own:.2f}s)"
