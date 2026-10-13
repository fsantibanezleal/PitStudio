# ruff: noqa: E501, PT018
"""T-006-014: `resources.gpu: nvenc` in every encode recipe stage; the held-lock check of `st56_encode` and `lock-not-held`.

Requirements: FR-006-07, FR-006-22.

Spec: specs/006-media-telemetry/spec.md FR-006-07 (every recipe stage of `st56_encode` declares `resources.gpu: nvenc`, never
`exclusive`, so that the runner holds `gpu0.nvenc` for it) and FR-006-22 (if, when it starts, the runner's held-lock list
`PITSTUDIO_HELD_LOCKS` (FR-002-62) does not contain `gpu0.nvenc` or is malformed, `st56_encode` refuses through the stage
helper's guard `require_lock("nvenc", 0)` (FR-002-63) with `error_class: lock-not-held`, before launching FFmpeg); spec 002
FR-002-63 (malformed: an entry not matching `^gpu[0-9]{1,2}\\.(compute|nvenc)$`, a duplicate entry, more than 4 entries or more than
64 characters); plan.md test strategy (hand-written lock values and a spy asserting FFmpeg is never launched without the lock).

Oracle: the hand-written `PITSTUDIO_HELD_LOCKS` values below, each classified by the FR-002-63 rule written out in this file; a
spy runner (the fake FFmpeg) and a patched `subprocess.run` that fail the test if FFmpeg is launched; the recipe stage of the
contract fixture `tests/contract/fixtures/repo/clean/studio/recipes/cases/a2-haulage.yaml` (a valid `st56_encode` stage) modified by hand.

Expected API of the implementation (modules `pitstudio_studio.media.lock` and `pitstudio_studio.media.encode`):
    lock.check_encode_stage(stage: dict) -> None
        `stage` is one stage mapping of a recipe; raises ValueError naming the stage id when `stage["id"] == "st56_encode"` and
        `stage["resources"]["gpu"]` is anything other than `"nvenc"` (including a missing `resources` or `gpu`); any other stage id passes.
    lock.check_recipes(folder: Path) -> list[str]
        every `*.yaml` under `folder` (recursively): one problem string per `st56_encode` stage that fails `check_encode_stage`, each
        naming the recipe id and the stage id; an empty list when none fails (also for a folder without encode stages).
    encode.run(job, *, runner=None, clock=None, env=None, driver_version=None) -> dict       (see test_t_006_013 for the full contract)
        first action: `pitstudio_stagekit.require_lock("nvenc", 0)`, which reads `os.environ["PITSTUDIO_HELD_LOCKS"]` and raises
        `pitstudio_stagekit.LockNotHeldError` (the stage helper then reports error_class `lock-not-held`); nothing is launched before.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_studio.media.encode import run
from pitstudio_studio.media.lock import check_encode_stage, check_recipes

FIXTURE_RECIPE = (
    kit.ROOT / "tests" / "contract" / "fixtures" / "repo" / "clean" / "studio" / "recipes" / "cases" / "a2-haulage.yaml"
)
LOCK_RE = re.compile(r"^gpu[0-9]{1,2}\.(compute|nvenc)$")  # FR-002-63


def encode_stage() -> dict:
    doc = yaml.safe_load(FIXTURE_RECIPE.read_text(encoding="utf-8"))
    return copy.deepcopy(next(s for s in doc["stages"] if s["id"] == "st56_encode"))


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-07: recipe stages declare nvenc
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-07")
def test_the_fixture_encode_stage_declares_nvenc_and_passes():
    st = encode_stage()
    assert st["resources"]["gpu"] == "nvenc"  # oracle: the stage as written in the contract fixture
    check_encode_stage(st)


@pytest.mark.req("FR-006-07")
@pytest.mark.parametrize(
    "resources",
    [
        {"gpu": "exclusive", "vram_gib_est": 4.0},
        {"gpu": "none"},
        {},
        None,
        {"gpu": "NVENC"},
        {"gpu": ""},
        {"gpu": None},
    ],
)
def test_any_other_gpu_declaration_is_rejected_naming_the_stage(resources):
    st = encode_stage()
    if resources is None:
        del st["resources"]
    else:
        st["resources"] = resources
    with pytest.raises(ValueError, match="st56_encode"):
        check_encode_stage(st)


@pytest.mark.req("FR-006-07")
@pytest.mark.parametrize("stage_id", ["st50_physics", "s30_train", "st52_rtx_render"])
def test_other_stages_are_not_constrained(stage_id):
    check_encode_stage({"id": stage_id, "resources": {"gpu": "exclusive", "vram_gib_est": 6.0}})
    check_encode_stage({"id": stage_id})


@pytest.mark.req("FR-006-07")
def test_recipe_folder_scan_flags_exactly_the_bad_encode_stages(tmp_path):
    good = yaml.safe_load(FIXTURE_RECIPE.read_text(encoding="utf-8"))
    bad = copy.deepcopy(good)
    bad["id"] = "a2-haulage-bad"
    next(s for s in bad["stages"] if s["id"] == "st56_encode")["resources"] = {"gpu": "exclusive", "vram_gib_est": 2.0}
    (tmp_path / "cases").mkdir()
    (tmp_path / "cases" / "good.yaml").write_text(yaml.safe_dump(good), encoding="utf-8")
    (tmp_path / "cases" / "bad.yaml").write_text(yaml.safe_dump(bad), encoding="utf-8")
    (tmp_path / "other.yaml").write_text(
        yaml.safe_dump(
            {"id": "x", "stages": [{"id": "st50_physics", "resources": {"gpu": "exclusive", "vram_gib_est": 6.0}}]}
        ),
        encoding="utf-8",
    )
    problems = check_recipes(tmp_path)
    assert len(problems) == 1
    assert "a2-haulage-bad" in problems[0] and "st56_encode" in problems[0]


@pytest.mark.req("FR-006-07")
def test_the_repository_recipes_pass_the_check():
    folder = kit.ROOT / "studio" / "recipes"
    assert check_recipes(folder) == []  # an absent or empty folder has no encode stage to fail


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-22: the held-lock check
# ---------------------------------------------------------------------------------------------------------------------
def classify(value: str | None) -> str:
    """The FR-002-63 rule: 'ok' when `gpu0.nvenc` is listed in a well-formed list, else 'refuse'."""
    if value is None or value == "":
        return "refuse"
    names = value.split(",")
    well_formed = (
        len(value) <= 64 and len(names) <= 4 and len(set(names)) == len(names) and all(LOCK_RE.match(n) for n in names)
    )
    return "ok" if well_formed and "gpu0.nvenc" in names else "refuse"


HELD_VALUES = [
    "gpu0.nvenc",
    "gpu0.compute,gpu0.nvenc",
    "gpu0.nvenc,gpu1.compute",
    None,  # unset
    "",
    "gpu0.compute",
    "gpu1.nvenc",  # another device's encode lock
    "gpu0.nvenc,gpu0.nvenc",  # duplicate entry
    "GPU0.nvenc",
    "gpu0.nvenc ",
    "gpu0.nvenc,",  # empty entry
    "gpu0.nvenc,gpu1.compute,gpu2.compute,gpu3.compute,gpu4.compute",  # five entries
    ",".join(["gpu0.nvenc"] + [f"gpu{i}.compute" for i in range(10, 20)]),  # more than 64 characters
    "gpu0.nvenc;rm -rf /",
    "nvenc",
    "gpu100.nvenc",
]


@pytest.mark.req("FR-006-22")
@pytest.mark.parametrize("value", HELD_VALUES, ids=[repr(v) for v in HELD_VALUES])
def test_ffmpeg_is_never_launched_unless_gpu0_nvenc_is_listed_in_a_well_formed_list(value, tmp_path, monkeypatch):
    from pitstudio_stagekit import LockNotHeldError

    def no_launch(*a, **k):
        raise AssertionError("a process was launched")

    ctx = kit.prepare(tmp_path, monkeypatch, held=value)
    if classify(value) == "refuse":
        monkeypatch.setattr(subprocess, "run", no_launch)
        monkeypatch.setattr(subprocess, "Popen", no_launch)
        with pytest.raises(LockNotHeldError, match=r"gpu0\.nvenc"):
            ctx.run()
        assert ctx.ff.calls == []  # before FFmpeg is launched, not even `-version`
        assert list(ctx.out.iterdir()) == []  # and nothing is written
    else:
        result = ctx.run()
        assert result["outputs"] and ctx.ff.calls


@pytest.mark.req("FR-006-22")
def test_the_stage_helper_reports_error_class_lock_not_held_and_names_the_lock(tmp_path, monkeypatch):
    import pitstudio_stagekit

    ctx = kit.prepare(tmp_path, monkeypatch, held="gpu0.compute")  # compute only: the encode lock is missing
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(ctx.job), encoding="utf-8")
    rc = pitstudio_stagekit.main(
        lambda job: run(job, runner=ctx.ff, clock=ctx.clock, env=ctx.env, driver_version=ctx.driver),
        ["--job", str(job_path)],
    )
    doc = json.loads((ctx.out / "result.json").read_text(encoding="utf-8"))
    assert rc == 1 and doc["status"] == "failed" and doc["error_class"] == "lock-not-held"
    assert "gpu0.nvenc" in doc["message"] and doc["outputs"] == []
    assert ctx.ff.calls == []


@pytest.mark.req("FR-006-22")
def test_a_direct_launch_outside_the_runner_has_no_held_lock_list(tmp_path, monkeypatch):
    from pitstudio_stagekit import LockNotHeldError

    ctx = kit.prepare(tmp_path, monkeypatch, held=None)
    with pytest.raises(LockNotHeldError):
        ctx.run()
    assert ctx.ff.calls == []
