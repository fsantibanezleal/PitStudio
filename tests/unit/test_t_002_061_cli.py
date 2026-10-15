# ruff: noqa: E501, PT018
"""T-002-061: hostile command lines and environment variables, and the exit codes of plan.md D2 (US-002-6).

Requirements: FR-002-42, FR-002-43.

Expected behaviour (stated for the implementer): a command that receives an unknown subcommand or option, a recipe
path that is not a `.yaml` file inside the repository's `studio/recipes/` (after resolving links), an unknown or malformed
profile, a stage key absent from the recipe, a malformed run or job id, a negative `--keep-last`, a PITSTUDIO_STORE that
is relative, longer than 64 characters (Windows), unwritable or inside the repository, or a GPU_LOCK_DIR that is relative
or not a directory, exits 2 with ONE line of message (standard output and error together) and changes nothing (repository,
store, lock folder). Exit codes: 0 success, 1 stage failure, 2 usage or validation, 3 lock held, 4 GPU hold, 5 guard
refused, 6 cancelled or interrupted. `--help` exits 0.
Oracles: hand-built hostile arguments; snapshots of the repository, store and lock folder before and after; the D2 table.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import recipe, stage


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path, recipes=[recipe("r1", [stage("s10_preprocess"), stage("st10_terrain")])])
    yield w
    rw.cleanup_world(w)


def snap(w: rw.World) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    return w.snapshot_repo(), w.snapshot_store(), rw.tree_digest(w.lock_dir)


def make_junction_or_symlink(link: Path, target: Path) -> None:
    import subprocess as sp

    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        sp.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def assert_one_line_usage_error(r: rw.Result, label: str) -> None:
    lines = [ln for ln in (r.out + r.err).splitlines() if ln.strip()]
    assert r.code == 2, f"{label}: exit {r.code}: {r.text!r}"
    assert len(lines) == 1, f"{label}: expected one message line, got {lines}"
    assert "Traceback" not in r.text


# ---- FR-002-42: command-line hostility --------------------------------------------------------------------------------------------------
def cases(w: rw.World, tmp_path: Path) -> list[tuple[str, list[str]]]:
    rp = str(w.recipes["r1"])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "o.yaml").write_text(w.recipes["r1"].read_text(encoding="utf-8"), encoding="utf-8")
    other_dir = w.repo / "other"
    other_dir.mkdir()
    (other_dir / "x.yaml").write_text(w.recipes["r1"].read_text(encoding="utf-8"), encoding="utf-8")
    (w.repo / "studio" / "recipes" / "cases" / "r.txt").write_text("not yaml", encoding="utf-8")
    (w.repo / "studio" / "recipes" / "cases" / "r.yml").write_text(
        w.recipes["r1"].read_text(encoding="utf-8"), encoding="utf-8"
    )
    make_junction_or_symlink(w.repo / "studio" / "recipes" / "cases" / "linked", outside)
    p = "--profile"
    return [
        ("unknown subcommand", ["frobnicate"]),
        ("no subcommand", []),
        ("unknown option of plan", ["plan", rp, p, "test-profile", "--bogus"]),
        ("unknown option of run", ["run", rp, p, "test-profile", "--turbo"]),
        ("unknown option of gc", ["gc", "--wipe-everything"]),
        ("plan without recipe", ["plan", p, "test-profile"]),
        ("plan without profile", ["plan", rp]),
        (
            "recipe with the wrong extension txt",
            ["plan", str(w.repo / "studio" / "recipes" / "cases" / "r.txt"), p, "test-profile"],
        ),
        (
            "recipe with the wrong extension yml",
            ["plan", str(w.repo / "studio" / "recipes" / "cases" / "r.yml"), p, "test-profile"],
        ),
        ("recipe outside studio/recipes (in the repository)", ["plan", str(other_dir / "x.yaml"), p, "test-profile"]),
        ("recipe outside the repository", ["plan", str(outside / "o.yaml"), p, "test-profile"]),
        (
            "recipe by traversal",
            [
                "plan",
                str(w.repo / "studio" / "recipes" / "cases" / ".." / ".." / ".." / "other" / "x.yaml"),
                p,
                "test-profile",
            ],
        ),
        (
            "recipe through a link leaving studio/recipes",
            ["plan", str(w.repo / "studio" / "recipes" / "cases" / "linked" / "o.yaml"), p, "test-profile"],
        ),
        ("recipe is a directory", ["plan", str(w.repo / "studio" / "recipes" / "cases"), p, "test-profile"]),
        (
            "recipe does not exist",
            ["plan", str(w.repo / "studio" / "recipes" / "cases" / "ghost.yaml"), p, "test-profile"],
        ),
        ("recipe path with NUL", ["plan", rp + "\x00.yaml", p, "test-profile"]),
        ("unknown profile", ["plan", rp, p, "no-such-profile"]),
        ("profile with traversal", ["plan", rp, p, "../test-profile"]),
        ("profile with uppercase", ["plan", rp, p, "Test-Profile"]),
        ("profile that is empty", ["plan", rp, p, ""]),
        ("stage key absent from the recipe", ["run", rp, p, "test-profile", "--stage", "st50_physics"]),
        ("stage variant absent from the recipe", ["run", rp, p, "test-profile", "--stage", "s10_preprocess@nosuch"]),
        ("malformed stage key", ["run", rp, p, "test-profile", "--stage", "not a key"]),
        ("stage key with trailing @", ["run", rp, p, "test-profile", "--stage", "s10_preprocess@"]),
        ("malformed run id on resume", ["run", "--resume", "../../x", p, "test-profile"]),
        ("unknown run id on resume", ["run", "--resume", "20250101T000000Z-ghost", p, "test-profile"]),
        ("malformed run id on publish", ["publish", "not-a-run"]),
        ("malformed job id on cancel", ["queue", "cancel", "123"]),
        ("negative keep-last", ["gc", "--keep-last", "-1"]),
        ("non-numeric keep-last", ["gc", "--keep-last", "many"]),
        ("fractional keep-last", ["gc", "--keep-last", "1.5"]),
        ("profile command without --stage", ["profile", rp, p, "test-profile"]),
    ]


@pytest.mark.req("FR-002-42")
def test_fr_002_42_hostile_command_lines_exit_2_with_one_line_and_change_nothing(world, tmp_path: Path) -> None:
    table = cases(world, tmp_path)
    before = snap(world)
    for label, argv in table:
        r = world.cli(*argv)
        assert_one_line_usage_error(r, label)
        assert snap(world) == before, f"{label}: a refused command must change nothing"
    assert world.ledger_rows() == []


@pytest.mark.req("FR-002-42")
@pytest.mark.parametrize("argv", [["--help"], ["plan", "--help"], ["run", "-h"]], ids=["top", "plan", "run"])
def test_fr_002_42_help_exits_0_and_lists_the_commands(world, argv: list[str]) -> None:
    r = world.cli(*argv)
    assert r.code == 0, r.text
    text = r.out + r.err
    assert ("plan" in text and "run" in text) or "--profile" in text


@pytest.mark.req("FR-002-42")
def test_fr_002_42_zero_and_positive_keep_last_are_accepted(world) -> None:
    assert world.cli("gc", "--keep-last", "0", "--dry-run").code == 0
    assert world.cli("gc", "--keep-last", "3", "--dry-run").code == 0


# ---- FR-002-42: environment variables -------------------------------------------------------------------------------------------------------
def store_cases(w: rw.World, tmp_path: Path) -> list[tuple[str, str, int]]:
    a_file = tmp_path / "a-file"
    a_file.write_text("x", encoding="utf-8")
    long_dir = tmp_path / ("d" * 70)
    long_dir.mkdir()
    return [
        ("relative store", "relative-store", 2),
        ("dot store", ".", 2),
        ("store inside the repository", str(w.repo / "ps-store"), 2),
        ("store is the repository", str(w.repo), 2),
        ("store under a regular file (unwritable)", str(a_file / "store"), 2),
        ("store is a regular file", str(a_file), 2),
        ("store path longer than 64 characters", str(long_dir / "store"), 2 if rw.IS_WINDOWS else 0),
    ]


@pytest.mark.req("FR-002-42")
@pytest.mark.parametrize(
    "command", [["queue", "ls"], ["status"], ["gc", "--dry-run"]], ids=["queue-ls", "status", "gc"]
)
def test_fr_002_42_a_bad_store_variable_exits_2_naming_it_and_creates_nothing(
    world, tmp_path: Path, command: list[str]
) -> None:
    for label, value, expected in store_cases(world, tmp_path):
        world.monkeypatch.setenv("PITSTUDIO_STORE", value)
        before_repo = world.snapshot_repo()
        r = world.cli(*command)
        if expected == 2:
            assert_one_line_usage_error(r, label)
            assert "PITSTUDIO_STORE" in r.text, f"{label}: the message must name the variable"
        else:
            assert r.code == 0, f"{label}: {r.text}"
        assert world.snapshot_repo() == before_repo
    world.monkeypatch.setenv("PITSTUDIO_STORE", str(world.store))


@pytest.mark.req("FR-002-42")
def test_fr_002_42_a_bad_store_variable_also_stops_plan_and_run(world, tmp_path: Path) -> None:
    world.monkeypatch.setenv("PITSTUDIO_STORE", "relative-store")
    for argv in (
        ["plan", str(world.recipes["r1"]), "--profile", "test-profile"],
        ["run", str(world.recipes["r1"]), "--profile", "test-profile"],
    ):
        r = world.cli(*argv)
        assert_one_line_usage_error(r, argv[0])
    assert world.ledger_rows() == [] and not (tmp_path / "relative-store").exists()


@pytest.mark.req("FR-002-42")
def test_fr_002_42_a_bad_lock_dir_exits_2_for_commands_that_use_locks(world, tmp_path: Path) -> None:
    a_file = tmp_path / "lockfile"
    a_file.write_text("x", encoding="utf-8")
    for label, value in (
        ("relative lock dir", "locks-relative"),
        ("lock dir is a file", str(a_file)),
        ("dot lock dir", "."),
    ):
        world.monkeypatch.setenv("GPU_LOCK_DIR", value)
        for argv in (["run", str(world.recipes["r1"]), "--profile", "test-profile"], ["status"], ["worker"]):
            r = world.cli(*argv)
            assert_one_line_usage_error(r, f"{label}: {argv[0]}")
            assert "GPU_LOCK_DIR" in r.text
    assert world.ledger_rows() == [] and not (tmp_path / "locks-relative").exists()


# ---- FR-002-43: the exit codes ------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-43")
def test_fr_002_43_exit_codes_0_to_5_follow_plan_d2(world) -> None:
    from filelock import FileLock

    gpu = recipe("gpu", [stage("st50_physics", gpu="exclusive", vram=2.0)])
    big = recipe("toobig", [stage("st50_physics", gpu="exclusive", vram=60.0)])
    bad = recipe("badstage", [stage("s10_preprocess", params={"mode": "fail"})])
    for d in (gpu, big, bad):
        world.write_recipe(d)
    prof = ("--profile", "test-profile")
    assert world.cli("plan", str(world.recipes["r1"]), *prof).code == 0, "0: success"
    assert world.run("badstage").code == 1, "1: a stage failed"
    assert world.cli("plan", str(world.recipes["r1"]), "--nope").code == 2, "2: usage"
    (world.store / "locks").mkdir(exist_ok=True)
    with FileLock(world.store / "locks" / "worker.lock", timeout=0):
        assert world.cli("worker").code == 3, "3: a lock is held (worker lock)"
    world.hold("exit code 4")
    assert world.run("gpu").code == 4, "4: GPU hold"
    world.release_hold()
    assert world.run("toobig").code == 5, "5: a guard refused"


@pytest.mark.req("FR-002-43")
def test_fr_002_43_exit_code_6_for_a_cancelled_job(world) -> None:
    from pitstudio.runner import queue

    world.write_recipe(
        recipe("cancelme", [stage("s10_preprocess", timeout_s=120, params={"mode": "sleep", "sleep_s": 60})])
    )
    p = subprocess.Popen(
        [sys.executable, "-m", "pitstudio.runner", "run", str(world.recipes["cancelme"]), "--profile", "test-profile"],
        env=world.env(),
        cwd=str(world.base),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert rw.wait_until(
            lambda: any(j["state"] == "running" for j in queue.jobs()) and bool(world.ledger_rows()), 90, proc=p
        ), "the job never started running"
        (job,) = queue.jobs()
        assert world.cli("queue", "cancel", job["job_id"]).code == 0
        assert p.wait(timeout=40) == 6, "6: cancelled"
        assert queue.job(job["job_id"])["state"] == "cancelled"
    finally:
        if p.poll() is None:
            p.kill()
        for r in world.ledger_rows():
            try:
                import psutil

                psutil.Process(r["pid"]).kill()
            except Exception:
                pass


@pytest.mark.req("FR-002-43")
def test_fr_002_43_every_command_returns_an_integer_in_0_to_6(world) -> None:
    for argv in (
        ["plan", str(world.recipes["r1"]), "--profile", "test-profile"],
        ["queue", "ls"],
        ["status"],
        ["gc", "--dry-run"],
        ["--help"],
        ["nonsense"],
    ):
        r = world.cli(*argv)
        assert isinstance(r.code, int) and 0 <= r.code <= 6, (argv, r.code)
