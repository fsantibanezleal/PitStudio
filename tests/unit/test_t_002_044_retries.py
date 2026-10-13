# ruff: noqa: E501, PT018
"""T-002-044: classified retries (US-002-4).

Requirements: FR-002-33, FR-002-34.

Expected behaviour (stated for the implementer):
  * a stage that fails with `error_class: oom` (in `result.json`, or with NO result when the last 200 log lines match
    `CUDA out of memory|OutOfMemoryError|cudaErrorMemoryAllocation|CUDA_ERROR_OUT_OF_MEMORY`, case-insensitive) is
    retried with the next `retry.oom_fallback` override merged into the effective parameters, once per declared step;
    each attempt is a record of the stage's `attempts[]` in the manifest (`n`, `error_class`, `fallback` = the override
    applied in that attempt); the stage's `params` and `cache_key` are those of the successful (or last) attempt;
  * a first-attempt timeout of a stage in env `isaac`, `rtx` or `kit` is retried once with the same parameters
    (`error_class: warmup-timeout` for that attempt); other timeouts are not retried;
  * any other failure, and OOM after the last step, is not retried: the stage is `failed`, every descendant `skipped`,
    the job exits 1, and the manifest holds `log_tail` (last 50 log lines, at most 4,000 characters, paths scrubbed to
    `<repo>`, `~`, `$PITSTUDIO_STORE`); `log_tail` appears for failed stages only.
Oracles: the attempt ledger written by the fake stage (one line per launch, with the parameters it received), the key
formula of FR-002-08 recomputed with hashlib (tests/support/refimpl.py), hand-built log texts.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import refimpl
import runner_world as rw
from runner_world import recipe, stage, up

SEED0 = 20261004


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


def oom_stage(
    mode: str = "oom_if_big",
    *,
    particles: int = 100,
    limit: int = 50,
    retry: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
    **kw: Any,
) -> dict[str, Any]:
    return stage(
        "st50_physics",
        gpu="exclusive",
        vram=2.0,
        variant="v1",
        params={"mode": mode, "particles": particles, "limit": limit, **(extra or {})},
        retry=retry,
        **kw,
    )


def attempts(world: rw.World, key: str = "st50_physics@v1") -> list[dict[str, Any]]:
    return world.stage_record(key)["attempts"]


# ---- FR-002-33: OOM -> fallback --------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-33")
def test_fr_002_33_oom_from_the_result_is_retried_with_the_fallback_and_the_effective_parameters_enter_the_key(
    world,
) -> None:
    world.write_recipe(recipe("oomy", [oom_stage(retry=[{"particles": 10}])], seed=SEED0))
    r = world.run("oomy")
    assert r.code == 0, r.text
    rows = world.starts()
    assert [x["params"]["particles"] for x in rows] == [100, 10], "second launch carries the merged fallback"
    att = attempts(world)
    assert [a["n"] for a in att] == [1, 2]
    assert att[0]["error_class"] == "oom" and att[1]["error_class"] is None
    assert att[1]["fallback"] == {"particles": 10} and "fallback" not in att[0]
    rec = world.stage_record("st50_physics@v1")
    assert rec["status"] == "succeeded" and rec["params"]["particles"] == 10 and rec["params"]["limit"] == 50
    expected = refimpl.ref_key(
        {"id": "st50_physics", "variant": "v1"},
        refimpl.ref_code_digest(world.repo, "studio"),
        refimpl.ref_lock_digest(world.repo, "studio"),
        rec["params"],
        refimpl.ref_seed(SEED0, "st50_physics@v1", 0),
        {},
        {},
        None,
    )
    assert rec["cache_key"] == expected, "the effective parameters of the successful attempt are the key's `params`"


@pytest.mark.req("FR-002-33")
@pytest.mark.parametrize(
    "text",
    [
        "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB",
        "RuntimeError: cudaErrorMemoryAllocation: out of memory",
        "CUDA_ERROR_OUT_OF_MEMORY: out of memory",
        "OutOfMemoryError",
        "cuda OUT OF MEMORY while launching",
        "outofmemoryerror in lower case",
    ],
    ids=[
        "torch-message",
        "cuda-runtime",
        "driver-api",
        "class-name",
        "case-insensitive-message",
        "case-insensitive-class",
    ],
)
def test_fr_002_33_oom_found_only_in_the_log_is_still_oom(world, text: str) -> None:
    world.write_recipe(
        recipe("oomlog", [oom_stage("oom_log_if_big", retry=[{"particles": 10}], extra={"oom_text": text})], seed=SEED0)
    )
    assert world.run("oomlog").code == 0
    assert [a["error_class"] for a in attempts(world)] == ["oom", None]
    assert [x["params"]["particles"] for x in world.starts()] == [100, 10]


@pytest.mark.req("FR-002-33")
def test_fr_002_33_the_log_window_is_the_last_200_lines(world) -> None:
    inside = oom_stage("oom_log_if_big", retry=[{"particles": 10}], extra={"trailing_lines": 150})
    world.write_recipe(recipe("win-in", [inside], seed=SEED0))
    assert world.run("win-in").code == 0, "OOM text 151 lines from the end is within the last 200"
    outside = oom_stage("oom_log_if_big", retry=[{"particles": 10}], extra={"trailing_lines": 250})
    world.write_recipe(recipe("win-out", [outside], seed=SEED0))
    r = world.run("win-out")
    assert r.code == 1, "OOM text 251 lines from the end is older than the window: not an OOM, no retry"
    assert len([x for x in world.starts() if x["params"].get("trailing_lines") == 250]) == 1


@pytest.mark.req("FR-002-33")
def test_fr_002_33_each_declared_step_is_tried_at_most_once_in_order(world) -> None:
    world.write_recipe(
        recipe(
            "steps",
            [oom_stage(particles=100, limit=35, retry=[{"particles": 40}, {"particles": 30}, {"particles": 20}])],
            seed=SEED0,
        )
    )
    assert world.run("steps").code == 0
    assert [x["params"]["particles"] for x in world.starts()] == [100, 40, 30], "stops at the first step that fits"
    assert [a["error_class"] for a in attempts(world)] == ["oom", "oom", None]
    assert [a.get("fallback") for a in attempts(world)] == [None, {"particles": 40}, {"particles": 30}]


@pytest.mark.req("FR-002-33")
@pytest.mark.req("FR-002-34")
def test_fr_002_34_oom_after_the_last_fallback_fails_without_further_retries(world) -> None:
    world.write_recipe(
        recipe(
            "exhausted",
            [
                oom_stage(particles=100, limit=5, retry=[{"particles": 40}, {"particles": 30}]),
                stage("s10_preprocess", inputs=[up("st50_physics", "out.bin", "v1")]),
            ],
            seed=SEED0,
        )
    )
    r = world.run("exhausted")
    assert r.code == 1, r.text
    assert len(world.starts()) == 3
    rec = world.stage_record("st50_physics@v1")
    assert (rec["status"], rec["error_class"]) == ("failed", "oom")
    assert [a["n"] for a in rec["attempts"]] == [1, 2, 3]
    assert world.stage_record("s10_preprocess")["status"] == "skipped"
    assert rec["outputs"] == []


# ---- warm-up timeouts ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-33")
@pytest.mark.parametrize(
    ("stage_id", "env"), [("st52_rtx_render", "isaac"), ("st53_sensors", "rtx"), ("st58_kit_capture", "kit")]
)
def test_fr_002_33_a_first_attempt_timeout_in_isaac_rtx_or_kit_is_retried_once_with_the_same_parameters(
    world, tmp_path: Path, stage_id: str, env: str
) -> None:
    marker = tmp_path / f"marker-{env}"
    st = stage(
        stage_id,
        gpu="exclusive",
        vram=2.0,
        timeout_s=2,
        params={"mode": "slow_first", "marker": str(marker), "sleep_s": 60},
    )
    world.write_recipe(recipe("warm", [st], seed=SEED0))
    r = world.run("warm")
    assert r.code == 0, r.text
    rows = world.starts()
    assert len(rows) == 2 and rows[0]["params"] == rows[1]["params"], "same parameters on the retry"
    att = world.stage_record(stage_id)["attempts"]
    assert [a["error_class"] for a in att] == ["warmup-timeout", None]
    assert all("fallback" not in a for a in att)


@pytest.mark.req("FR-002-33")
def test_fr_002_33_a_second_timeout_in_a_warmup_stage_fails_after_exactly_two_attempts(world) -> None:
    st = stage("st52_rtx_render", gpu="exclusive", vram=2.0, timeout_s=1, params={"mode": "sleep", "sleep_s": 60})
    world.write_recipe(recipe("warm2", [st], seed=SEED0))
    assert world.run("warm2").code == 1
    rec = world.stage_record("st52_rtx_render")
    assert len(world.starts()) == 2 and len(rec["attempts"]) == 2
    assert rec["status"] == "failed" and rec["error_class"] in ("timeout", "warmup-timeout")


@pytest.mark.req("FR-002-33")
def test_fr_002_33_timeouts_in_other_environments_are_not_retried(world) -> None:
    world.write_recipe(
        recipe(
            "nowarm",
            [stage("st50_physics", gpu="exclusive", vram=2.0, timeout_s=1, params={"mode": "sleep", "sleep_s": 60})],
            seed=SEED0,
        )
    )
    assert world.run("nowarm").code == 1
    assert len(world.starts()) == 1 and world.stage_record("st50_physics")["error_class"] == "timeout"


# ---- FR-002-34: everything else fails fast --------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-34")
@pytest.mark.parametrize(
    "params",
    [{"mode": "fail"}, {"mode": "crash"}, {"mode": "raw_result", "raw": "garbage"}],
    ids=["reported-failure", "crash-without-result", "invalid-result"],
)
def test_fr_002_34_other_failures_are_not_retried_even_when_a_fallback_exists(world, params: dict[str, Any]) -> None:
    st = stage(
        "st50_physics",
        gpu="exclusive",
        vram=2.0,
        variant="v1",
        params={**params, "particles": 100},
        retry=[{"particles": 10}],
    )
    world.write_recipe(
        recipe("nofallback", [st, stage("s10_preprocess", inputs=[up("st50_physics", "out.bin", "v1")])], seed=SEED0)
    )
    r = world.run("nofallback")
    assert r.code == 1, r.text
    assert len(world.starts()) == 1 and len(attempts(world)) == 1
    assert world.stage_record("s10_preprocess")["status"] == "skipped"
    assert world.stage_record("st50_physics@v1")["status"] == "failed"


@pytest.mark.req("FR-002-34")
def test_fr_002_34_log_tail_is_the_last_50_lines_scrubbed_and_only_for_failed_stages(world) -> None:
    world.write_recipe(
        recipe(
            "tail",
            [
                stage("s10_preprocess", params={"mode": "fail", "log_lines": 120, "log_width": 5}),
                stage("s20_feature_extraction", inputs=[up("s10_preprocess", "out.bin")]),
            ],
            seed=SEED0,
        )
    )
    assert world.run("tail").code == 1
    rec = world.stage_record("s10_preprocess")
    tail = rec["log_tail"]
    lines = tail.splitlines()
    assert len(lines) <= 50 and len(tail) <= 4000
    assert "line-119" in tail and any("fake stage failed" in ln for ln in lines), "the end of the log is kept"
    assert "line-000" not in tail and "line-060" not in tail, "lines older than the last 50 are dropped"
    home = str(Path.home())
    for secret in (home, home.replace("\\", "/"), str(world.repo), str(world.store), str(world.lock_dir)):
        assert secret not in tail, f"unscrubbed path in log_tail: {secret}"
    assert re.search(r"~|<repo>|\$PITSTUDIO_STORE", tail), "paths are replaced by ~, <repo> or $PITSTUDIO_STORE"
    assert "log_tail" not in world.stage_record("s20_feature_extraction")


@pytest.mark.req("FR-002-34")
def test_fr_002_34_log_tail_is_capped_at_4000_characters(world) -> None:
    world.write_recipe(
        recipe(
            "wide", [stage("s10_preprocess", params={"mode": "fail", "log_lines": 60, "log_width": 200})], seed=SEED0
        )
    )
    assert world.run("wide").code == 1
    tail = world.stage_record("s10_preprocess")["log_tail"]
    assert 0 < len(tail) <= 4000


@pytest.mark.req("FR-002-34")
def test_fr_002_34_a_succeeded_stage_has_no_log_tail_and_one_attempt(world) -> None:
    world.write_recipe(recipe("fine", [stage("s10_preprocess")], seed=SEED0))
    assert world.run("fine").code == 0
    rec = world.stage_record("s10_preprocess")
    assert (
        "log_tail" not in rec
        and len(rec["attempts"]) == 1
        and rec["attempts"][0]["n"] == 1
        and rec["attempts"][0]["error_class"] is None
    )
