# ruff: noqa: E501, PT018, RUF001
"""T-002-048: the runner tells each stage which machine-wide locks it holds; the stage helper refuses GPU work otherwise.

Requirements: FR-002-62, FR-002-63.

Expected behaviour (stated for the implementer):
  * every stage process gets the environment variable PITSTUDIO_HELD_LOCKS: the sorted, comma-separated names of the
    locks the runner holds for that execution (`gpu0.compute` for `resources.gpu: exclusive`, `gpu0.nvenc` for `nvenc`),
    or the EMPTY STRING (variable present) for a stage that holds none;
  * `pitstudio_stagekit.held_locks() -> frozenset[str]` exposes it (empty when unset or empty);
  * `pitstudio_stagekit.require_lock(kind: str, device: int) -> None` (kind `compute` or `nvenc`) raises
    `pitstudio_stagekit.LockNotHeldError` (an Exception) when PITSTUDIO_HELD_LOCKS is unset, malformed (an entry not
    matching ^gpu[0-9]{1,2}\\.(compute|nvenc)$, a duplicate entry, more than 4 entries, more than 64 characters) or does not
    list `gpu<device>.<kind>`; the message names the missing lock; a stage using `pitstudio_stagekit.main` then ends
    `failed` with `error_class: lock-not-held` (exit code 1) before any GPU work starts; an invalid `kind` or a `device`
    outside 0..99 raises ValueError.
Oracles: the plan.md rule table (hand-written values for every clause), the stage-result schema, a stage program that
logs when "GPU work" starts (tests/support/ps_fake_stages/kit_stage.py).
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
from runner_world import PopenSpy, recipe, stage

KIT_DIR = rw.ROOT / "src" / "pitstudio" / "runner" / "stagekit"


def kit_module(monkeypatch: pytest.MonkeyPatch, held: str | None):
    sys.path.insert(0, str(KIT_DIR))
    import pitstudio_stagekit as kit

    if held is None:
        monkeypatch.delenv("PITSTUDIO_HELD_LOCKS", raising=False)
    else:
        monkeypatch.setenv("PITSTUDIO_HELD_LOCKS", held)
    return kit


# ---- FR-002-62: the helper reads the variable ---------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-62")
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, frozenset()),
        ("", frozenset()),
        ("gpu0.compute", frozenset({"gpu0.compute"})),
        ("gpu0.nvenc", frozenset({"gpu0.nvenc"})),
        ("gpu0.compute,gpu0.nvenc", frozenset({"gpu0.compute", "gpu0.nvenc"})),
        (
            "gpu0.compute,gpu1.compute,gpu0.nvenc,gpu1.nvenc",
            frozenset({"gpu0.compute", "gpu1.compute", "gpu0.nvenc", "gpu1.nvenc"}),
        ),
    ],
)
def test_fr_002_62_held_locks_is_a_frozen_set_of_the_listed_names(
    monkeypatch: pytest.MonkeyPatch, value: str | None, expected: frozenset[str]
) -> None:
    kit = kit_module(monkeypatch, value)
    got = kit.held_locks()
    assert isinstance(got, frozenset) and got == expected


# ---- FR-002-62: the runner exports it -------------------------------------------------------------------------------------------------
@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


@pytest.mark.req("FR-002-62")
def test_fr_002_62_each_resource_kind_gets_its_own_lock_names_and_a_cpu_stage_the_empty_string(world) -> None:
    world.write_recipe(
        recipe(
            "held",
            [
                stage("st50_physics", gpu="exclusive", vram=2.0),
                stage("st56_encode", gpu="nvenc", inputs=[rw.up("st50_physics", "out.bin")]),
                stage("s10_preprocess"),
            ],
        )
    )
    spy = PopenSpy(world.monkeypatch)
    r = world.run("held")
    assert r.code == 0, r.text
    held = {row["stage"]["id"]: row["env"] for row in world.starts()}
    assert held["st50_physics"]["PITSTUDIO_HELD_LOCKS"] == "gpu0.compute"
    assert held["st56_encode"]["PITSTUDIO_HELD_LOCKS"] == "gpu0.nvenc"
    assert "PITSTUDIO_HELD_LOCKS" in held["s10_preprocess"] and held["s10_preprocess"]["PITSTUDIO_HELD_LOCKS"] == ""
    # the launcher sees the same variable (what the stage reads is what the runner passed)
    seen = [
        kw["env"]["PITSTUDIO_HELD_LOCKS"]
        for args, kw in spy.calls
        if "ps_fake_stages.generic" in " ".join(map(str, args))
    ]
    assert sorted(seen) == ["", "gpu0.compute", "gpu0.nvenc"]
    for v in seen:
        assert v == ",".join(sorted(x for x in v.split(",") if x)), "names are sorted"


# ---- FR-002-63: require_lock ----------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-63")
@pytest.mark.parametrize(
    ("held", "kind", "device"),
    [
        ("gpu0.compute", "compute", 0),
        ("gpu0.nvenc", "nvenc", 0),
        ("gpu0.compute,gpu0.nvenc", "compute", 0),
        ("gpu0.compute,gpu0.nvenc", "nvenc", 0),
        ("gpu1.compute", "compute", 1),
        ("gpu12.nvenc", "nvenc", 12),
        ("gpu0.compute,gpu1.compute,gpu0.nvenc,gpu1.nvenc", "nvenc", 1),
    ],
)
def test_fr_002_63_require_lock_passes_when_the_needed_lock_is_listed(
    monkeypatch: pytest.MonkeyPatch, held: str, kind: str, device: int
) -> None:
    kit = kit_module(monkeypatch, held)
    assert kit.require_lock(kind, device) is None


HOSTILE: list[tuple[str, str | None, str, int, str]] = [
    ("unset", None, "compute", 0, "gpu0.compute"),
    ("empty", "", "compute", 0, "gpu0.compute"),
    ("other-kind-held", "gpu0.nvenc", "compute", 0, "gpu0.compute"),
    ("other-device-held", "gpu0.compute", "compute", 1, "gpu1.compute"),
    ("duplicate-entry", "gpu0.compute,gpu0.compute", "compute", 0, "gpu0.compute"),
    ("duplicate-among-others", "gpu0.compute,gpu0.nvenc,gpu0.compute", "nvenc", 0, "gpu0.nvenc"),
    ("uppercase", "GPU0.compute", "compute", 0, "gpu0.compute"),
    ("unknown-kind", "gpu0.render", "compute", 0, "gpu0.compute"),
    ("five-entries", "gpu0.compute,gpu1.compute,gpu2.compute,gpu3.compute,gpu4.compute", "compute", 0, "gpu0.compute"),
    ("longer-than-64-characters", "gpu0.compute," + "x" * 60, "compute", 0, "gpu0.compute"),
    ("exactly-65-characters-of-junk", "g" * 65, "compute", 0, "gpu0.compute"),
    ("leading-space", " gpu0.compute", "compute", 0, "gpu0.compute"),
    ("trailing-comma", "gpu0.compute,", "compute", 0, "gpu0.compute"),
    ("three-digit-index", "gpu100.compute", "compute", 0, "gpu0.compute"),
    ("semicolon-separator", "gpu0.compute;gpu0.nvenc", "nvenc", 0, "gpu0.nvenc"),
    ("negative-index", "gpu-1.compute", "compute", 0, "gpu0.compute"),
    ("newline-in-value", "gpu0.compute\ngpu0.nvenc", "nvenc", 0, "gpu0.nvenc"),
    ("unicode-digit", "gpu٠.compute", "compute", 0, "gpu0.compute"),
]


@pytest.mark.req("FR-002-63")
@pytest.mark.parametrize(("label", "held", "kind", "device", "missing"), HOSTILE, ids=[h[0] for h in HOSTILE])
def test_fr_002_63_require_lock_refuses_unset_malformed_or_incomplete_values(
    monkeypatch: pytest.MonkeyPatch, label: str, held: str | None, kind: str, device: int, missing: str
) -> None:
    kit = kit_module(monkeypatch, held)
    with pytest.raises(kit.LockNotHeldError) as e:
        kit.require_lock(kind, device)
    assert isinstance(e.value, Exception)
    assert missing in str(e.value), f"the message must name the missing lock {missing}: {e.value}"


@pytest.mark.req("FR-002-63")
@pytest.mark.parametrize(
    ("kind", "device"),
    [("render", 0), ("", 0), ("COMPUTE", 0), ("compute", -1), ("compute", 100), ("nvenc", "0"), ("compute", None)],
    ids=["render", "empty", "uppercase", "negative", "above-99", "string-device", "none-device"],
)
def test_fr_002_63_arguments_outside_the_documented_domain_are_value_errors(
    monkeypatch: pytest.MonkeyPatch, kind: str, device: Any
) -> None:
    kit = kit_module(monkeypatch, "gpu0.compute,gpu0.nvenc")
    with pytest.raises((ValueError, TypeError)):
        kit.require_lock(kind, device)


# ---- FR-002-63: through the stage helper and a real run -------------------------------------------------------------------------------
def run_kit_stage(
    tmp_path: Path, held: str | None, kind: str = "compute"
) -> tuple[subprocess.CompletedProcess[str], Path]:
    out = tmp_path / "runs" / "20261004T120000Z-kit" / "tmp" / "st50_physics" / "0"
    out.mkdir(parents=True)
    (tmp_path / "scratch").mkdir()
    job = {
        "schema_version": "1.0", "run_id": "20261004T120000Z-kit", "stage": {"id": "st50_physics"}, "entry": "ps_fake_stages.kit_stage", "params": {"kind": kind},
        "seed": 1, "shard": None, "inputs": [], "output_dir": out.as_posix(), "scratch_dir": (tmp_path / "scratch").as_posix(), "resume": False,
        "rerun": False, "profiling": False, "profile": {"id": "p", "cpu_slots": 1}, "vram_fraction": 0.5, "nvtx_range": "r",
    }  # fmt: skip
    (out / "job.json").write_text(json.dumps(job), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PITSTUDIO_HELD_LOCKS"}
    env.update(
        {
            "PYTHONPATH": os.pathsep.join([str(KIT_DIR), str(rw.SUPPORT)]),
            "PS_FAKE_LEDGER": str(tmp_path / "ledger.jsonl"),
        }
    )
    if held is not None:
        env["PITSTUDIO_HELD_LOCKS"] = held
    r = subprocess.run(
        [sys.executable, "-m", "ps_fake_stages.kit_stage", "--job", str(out / "job.json")],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        cwd=str(tmp_path),
    )
    assert "No module named 'pitstudio_stagekit'" not in r.stderr, (
        f"the stage helper does not exist yet: {r.stderr[-300:]}"
    )
    return r, out


@pytest.mark.req("FR-002-63")
@pytest.mark.parametrize(
    ("held", "kind", "missing"),
    [
        (None, "compute", "gpu0.compute"),
        ("gpu0.nvenc", "compute", "gpu0.compute"),
        ("gpu0.compute", "nvenc", "gpu0.nvenc"),
        ("gpu0.compute,gpu0.compute", "compute", "gpu0.compute"),
    ],
)
def test_fr_002_63_a_stage_without_the_lock_fails_with_lock_not_held_before_any_gpu_work(
    tmp_path: Path, held: str | None, kind: str, missing: str
) -> None:
    r, out = run_kit_stage(tmp_path, held, kind)
    assert r.returncode == 1, r.stderr
    doc = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert schemas.errors("job", doc, "#/$defs/stage_result") == []
    assert (doc["status"], doc["error_class"]) == ("failed", "lock-not-held")
    assert missing in doc["message"]
    ledger = [json.loads(ln) for ln in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [x["event"] for x in ledger] == ["start"], "no GPU work may start before the lock check passes"


@pytest.mark.req("FR-002-63")
def test_fr_002_63_with_the_lock_listed_the_stage_proceeds(tmp_path: Path) -> None:
    r, out = run_kit_stage(tmp_path, "gpu0.compute", "compute")
    assert r.returncode == 0, r.stderr
    assert json.loads((out / "result.json").read_text(encoding="utf-8"))["status"] == "succeeded"
    ledger = [json.loads(ln) for ln in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [x["event"] for x in ledger] == ["start", "gpu-work"]
    assert ledger[0]["held_api"] == ["gpu0.compute"]


@pytest.mark.req("FR-002-63")
@pytest.mark.req("FR-002-62")
def test_fr_002_63_end_to_end_the_runner_grants_exactly_the_lock_the_resources_declare(world) -> None:
    ok = stage("st50_physics", gpu="exclusive", vram=2.0, entry="ps_fake_stages.kit_stage", params={"kind": "compute"})
    world.write_recipe(recipe("e2e-ok", [ok]))
    assert world.run("e2e-ok").code == 0
    assert [x["event"] for x in world.ledger_rows()] == ["start", "gpu-work"]
    # an nvenc stage that tries to start compute work must be refused by the helper, and the runner must record the class
    bad = stage("st56_encode", gpu="nvenc", entry="ps_fake_stages.kit_stage", params={"kind": "compute"})
    world.write_recipe(recipe("e2e-bad", [bad]))
    r = world.run("e2e-bad")
    assert r.code == 1, r.text
    rec = world.stage_record("st56_encode")
    assert (rec["status"], rec["error_class"]) == ("failed", "lock-not-held")
    assert not any(x["event"] == "gpu-work" and x["held"] == "gpu0.nvenc" for x in world.ledger_rows())
    cpu = stage("s10_preprocess", entry="ps_fake_stages.kit_stage", params={"kind": "compute"})
    world.write_recipe(recipe("e2e-cpu", [cpu]))
    r = world.run("e2e-cpu")
    assert r.code == 1 and world.stage_record("s10_preprocess")["error_class"] == "lock-not-held"
