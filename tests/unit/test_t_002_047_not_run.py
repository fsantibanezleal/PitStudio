# ruff: noqa: E501, PT018
"""T-002-047: stages that report "not run" (honesty, FR-000-07) (US-002-4).

Requirements: FR-002-60, FR-002-61.

Expected behaviour (stated for the implementer):
  * `pitstudio_stagekit.NotRun(reason: str)` is an exception (subclass of Exception); the reason must be 1..300
    characters and not blank, else the constructor raises ValueError; raised from a stage function given to
    `pitstudio_stagekit.main`, it becomes `result.json` with `status: not_run`, the `reason`, `error_class: null`,
    `outputs: []` and process exit code 0;
  * the runner records such a stage as `not_run` (status), with the reason, exit_code 0 and error_class null in the
    manifest; emits a `stage-not-run` event (`stage`, `detail` = reason); promotes nothing; does not retry it; marks every
    downstream stage `skipped` with reason `upstream not run: <stage key>`; prints one line
    `not run: <stage key>: <reason>`; never records it `succeeded`; ends the job succeeded (exit 0) only if no other
    stage failed;
  * a `not_run` result with no/empty/blank/over-long reason, any listed output, a non-null error_class, or a non-zero
    process exit code is an `invalid-result` failure (FR-002-25) and promotes nothing.
Oracles: hand-written result documents (reason lengths 0, 1, 300, 301), the stage-result and event schemas.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
import schemas
from runner_world import recipe, stage, up

KIT_DIR = rw.ROOT / "src" / "pitstudio" / "runner" / "stagekit"


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


def objects(world: rw.World) -> set[str]:
    d = world.store / "cas" / "sha256"
    return {f.name for f in d.rglob("*") if f.is_file()} if d.is_dir() else set()


def nr_recipe(reason: str = "ffmpeg is not installed on this machine") -> dict[str, Any]:
    return recipe(
        "norun",
        [
            stage("s10_preprocess", params={"mode": "notrun", "reason": reason}, retry=[{"reason": "other"}]),
            stage("s20_feature_extraction", inputs=[up("s10_preprocess", "out.bin")]),
            stage("s30_train", inputs=[up("s20_feature_extraction", "out.bin")]),
            stage("st10_terrain"),
        ],
    )


# ---- FR-002-60: the helper ------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-60")
@pytest.mark.parametrize(
    "reason",
    ["", "   ", "\t\n", "x" * 301, "two\nlines", "\u0000hidden"],
    ids=["empty", "blank", "whitespace-only", "301-chars", "multi-line", "control-char"],
)
def test_fr_002_60_notrun_requires_a_one_line_reason_of_1_to_300_characters(reason: str) -> None:
    sys.path.insert(0, str(KIT_DIR))
    import pitstudio_stagekit as kit

    with pytest.raises(ValueError, match=r"(?s).+"):  # any non-empty message; its wording is not specified
        kit.NotRun(reason)


@pytest.mark.req("FR-002-60")
@pytest.mark.parametrize(
    "reason", ["x", "x" * 300, "café 中文 \U0001f525", "driver 551.23 is below the tool's floor 560"]
)
def test_fr_002_60_notrun_accepts_valid_reasons_and_the_helper_writes_a_not_run_result(
    tmp_path: Path, reason: str
) -> None:
    sys.path.insert(0, str(KIT_DIR))
    import pitstudio_stagekit as kit

    assert issubclass(kit.NotRun, Exception) and str(kit.NotRun(reason)) == reason
    out = tmp_path / "runs" / "20261004T120000Z-kit" / "tmp" / "s10_preprocess" / "0"
    out.mkdir(parents=True)
    (tmp_path / "scratch").mkdir()
    job = {
        "schema_version": "1.0", "run_id": "20261004T120000Z-kit", "stage": {"id": "s10_preprocess"}, "entry": "ps_nr", "params": {}, "seed": 1,
        "shard": None, "inputs": [], "output_dir": out.as_posix(), "scratch_dir": (tmp_path / "scratch").as_posix(), "resume": False,
        "rerun": False, "profiling": False, "profile": {"id": "p", "cpu_slots": 1}, "vram_fraction": None, "nvtx_range": "r",
    }  # fmt: skip
    (out / "job.json").write_text(json.dumps(job), encoding="utf-8")
    script = f"import sys; sys.path.insert(0, {str(KIT_DIR)!r}); import pitstudio_stagekit as k\n\ndef fn(job):\n    raise k.NotRun({reason!r})\n\nsys.exit(k.main(fn))\n"
    r = subprocess.run(
        [sys.executable, "-c", script, "--job", str(out / "job.json")],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert r.returncode == 0, r.stderr
    doc = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert schemas.errors("job", doc, "#/$defs/stage_result") == []
    assert (doc["status"], doc["reason"], doc["error_class"], doc["outputs"]) == ("not_run", reason, None, [])


# ---- FR-002-60: the runner ---------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-60")
def test_fr_002_60_a_not_run_stage_is_recorded_honestly_and_its_descendants_are_skipped_with_the_reason(world) -> None:
    reason = "ffmpeg is not installed on this machine"
    world.write_recipe(nr_recipe(reason))
    r = world.run("norun")
    assert r.code == 0, "no other stage failed, so the job ends succeeded"
    s10 = world.stage_record("s10_preprocess")
    assert (
        s10["status"] == "not_run" and s10["reason"] == reason and s10["exit_code"] == 0 and s10["error_class"] is None
    )
    assert s10["outputs"] == [] and len(s10["attempts"]) == 1
    for k, upstream in (("s20_feature_extraction", "s10_preprocess"), ("s30_train", "s20_feature_extraction")):
        rec = world.stage_record(k)
        assert rec["status"] == "skipped" and rec["reason"] == f"upstream not run: {upstream}", (k, rec.get("reason"))
    assert world.stage_record("st10_terrain")["status"] == "succeeded"
    assert len(world.starts()) == 2, "no retry of the not-run stage (one execution) plus the independent stage"
    assert [x["stage"]["id"] for x in world.starts()] == ["s10_preprocess", "st10_terrain"]
    lines = [ln for ln in r.out.splitlines() if ln.startswith("not run:")]
    assert lines == [f"not run: s10_preprocess: {reason}"], r.out
    assert all(s["status"] != "succeeded" for s in world.manifest()["stages"] if s["key"]["id"] == "s10_preprocess")


@pytest.mark.req("FR-002-60")
def test_fr_002_60_events_carry_stage_not_run_and_stage_skipped_and_validate(world) -> None:
    world.write_recipe(nr_recipe("tool floor not met"))
    assert world.run("norun").code == 0
    ev = world.events()
    for e in ev:
        assert schemas.errors("events", e, "#/$defs/event") == [], e
    nr = [e for e in ev if e["type"] == "stage-not-run"]
    assert len(nr) == 1 and nr[0]["stage"] == {"id": "s10_preprocess"} and nr[0]["detail"] == "tool floor not met"
    skipped = {e["stage"]["id"] for e in ev if e["type"] == "stage-skipped"}
    assert skipped == {"s20_feature_extraction", "s30_train"}
    assert not any(
        e["type"] == "stage-finished"
        and e.get("stage", {}).get("id") == "s10_preprocess"
        and (e.get("data") or {}).get("status") == "succeeded"
        for e in ev
    )


@pytest.mark.req("FR-002-60")
def test_fr_002_60_nothing_is_promoted_for_a_not_run_stage(world) -> None:
    world.write_recipe(
        recipe("alone", [stage("s10_preprocess", params={"mode": "notrun", "reason": "optional input unavailable"})])
    )
    assert world.run("alone").code == 0
    assert objects(world) == set()
    idx = world.store / "index"
    assert not idx.exists() or not list(idx.rglob("*.json"))
    # it is not cached either: running again executes it again
    import time

    time.sleep(1.1)
    assert world.run("alone").code == 0
    assert len(world.starts()) == 2


@pytest.mark.req("FR-002-60")
def test_fr_002_60_the_job_is_not_succeeded_when_another_stage_failed(world) -> None:
    world.write_recipe(
        recipe(
            "mixed",
            [
                stage("s10_preprocess", params={"mode": "notrun", "reason": "tool too new"}),
                stage("st10_terrain", params={"mode": "fail"}),
            ],
        )
    )
    r = world.run("mixed")
    assert r.code == 1, r.text
    assert (
        world.stage_record("s10_preprocess")["status"] == "not_run"
        and world.stage_record("st10_terrain")["status"] == "failed"
    )


@pytest.mark.req("FR-002-60")
def test_fr_002_60_a_not_run_variant_stage_is_named_with_its_variant(world) -> None:
    world.write_recipe(
        recipe(
            "variant",
            [
                stage(
                    "st50_physics",
                    gpu="exclusive",
                    vram=2.0,
                    variant="dem",
                    params={"mode": "notrun", "reason": "driver below the tool floor"},
                ),
                stage("st56_encode", gpu="nvenc", inputs=[up("st50_physics", "out.bin", "dem")]),
            ],
        )
    )
    r = world.run("variant")
    assert r.code == 0
    assert "not run: st50_physics@dem: driver below the tool floor" in r.out
    assert world.stage_record("st56_encode")["reason"] == "upstream not run: st50_physics@dem"


# ---- FR-002-61: hostile not_run results ----------------------------------------------------------------------------------------------------
def nr_doc(**over: Any) -> str:
    doc = {
        "schema_version": "1.0",
        "status": "not_run",
        "error_class": None,
        "outputs": [],
        "checkpoint": False,
        "reason": "valid reason",
    }
    doc.update(over)
    return json.dumps({k: v for k, v in doc.items() if v is not ...})


HOSTILE = [
    ("missing-reason", {"raw": nr_doc(reason=...)}),
    ("empty-reason", {"raw": nr_doc(reason="")}),
    ("blank-reason", {"raw": nr_doc(reason="   ")}),
    ("301-char-reason", {"raw": nr_doc(reason="r" * 301)}),
    ("multi-line-reason", {"raw": nr_doc(reason="line one\nline two")}),
    ("reason-null", {"raw": nr_doc(reason=None)}),
    ("with-an-output", {"raw": nr_doc(outputs=[{"path": "out.bin"}])}),
    ("with-an-error-class", {"raw": nr_doc(error_class="unknown")}),
    ("oom-error-class", {"raw": nr_doc(error_class="oom")}),
    ("nonzero-exit", {"raw": nr_doc(), "exit_code": 3}),
    ("exit-1", {"raw": nr_doc(), "exit_code": 1}),
]


@pytest.mark.req("FR-002-61")
@pytest.mark.parametrize(("label", "params"), HOSTILE, ids=[h[0] for h in HOSTILE])
def test_fr_002_61_an_invalid_not_run_result_is_an_invalid_result_failure(
    world, label: str, params: dict[str, Any]
) -> None:
    world.write_recipe(
        recipe(
            "hostile",
            [
                stage("s10_preprocess", params={"mode": "raw_result", **params}),
                stage("s20_feature_extraction", inputs=[up("s10_preprocess", "out.bin")]),
            ],
        )
    )
    r = world.run("hostile")
    assert r.code == 1, f"{label}: {r.text}"
    rec = world.stage_record("s10_preprocess")
    assert (rec["status"], rec["error_class"]) == ("failed", "invalid-result"), label
    s20 = world.stage_record("s20_feature_extraction")
    assert s20["status"] == "skipped" and "upstream not run" not in (s20.get("reason") or "")
    assert objects(world) == set()
    assert not any(ln.startswith("not run:") for ln in r.out.splitlines())


@pytest.mark.req("FR-002-61")
@pytest.mark.parametrize("reason", ["r", "r" * 300], ids=["one-char", "exactly-300"])
def test_fr_002_61_the_reason_length_boundaries_are_accepted(world, reason: str) -> None:
    world.write_recipe(
        recipe("edges", [stage("s10_preprocess", params={"mode": "raw_result", "raw": nr_doc(reason=reason)})])
    )
    assert world.run("edges").code == 0
    rec = world.stage_record("s10_preprocess")
    assert rec["status"] == "not_run" and rec["reason"] == reason
