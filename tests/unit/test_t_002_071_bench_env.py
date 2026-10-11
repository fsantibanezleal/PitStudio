# ruff: noqa: E501, PT018
"""T-002-071: `studio bench env` wraps `studio/bench/run_bench.py` (US-002-6).

Requirement: FR-002-53.

Expected behaviour (stated for the implementer): `studio bench env [probe...] [--timeout S] [--no-write]` loads
`<repo>/studio/bench/run_bench.py` (PITSTUDIO_REPO or the checkout) and calls its `main(argv)` with
`argv = [<program name>, *the arguments after "bench env", in order]` (run_bench's own parser skips argv[0]); the return value
of `main` (0..4, or 2 for its usage error) is the exit code of the command, unchanged. Under a hold file, the real
run_bench exits 4 before importing an NVML binding or `filelock`, and so does `studio bench env`. `studio bench` with
anything other than `env` is a usage error (exit 2).
Oracles: a stub `run_bench.py` that records its argv and returns a scripted code (tests/support/runner_world.py
RUN_BENCH_STUB), the real run_bench's documented hold behaviour (tests/unit/test_run_bench_hold.py), and a Popen guard so
that no probe can start.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


def recorded(w: rw.World) -> list[str]:
    return json.loads((w.base / "bench-argv.json").read_text(encoding="utf-8"))


@pytest.mark.req("FR-002-53")
@pytest.mark.parametrize("code", [0, 1, 2, 3, 4])
def test_fr_002_53_the_exit_code_of_run_bench_is_returned_unchanged(world, code: int) -> None:
    world.monkeypatch.setenv("PS_BENCH_EXIT", str(code))
    world.monkeypatch.setenv("PS_BENCH_ARGV_FILE", str(world.base / "bench-argv.json"))
    assert world.cli("bench", "env").code == code


@pytest.mark.req("FR-002-53")
@pytest.mark.parametrize(
    "args",
    [
        [],
        ["warp_newton"],
        ["warp_newton", "nvenc"],
        ["--timeout", "30"],
        ["--no-write"],
        ["tensorrt", "--timeout", "600", "--no-write"],
        ["--no-write", "nvenc", "--timeout", "5"],
    ],
    ids=["none", "one-probe", "two-probes", "timeout", "no-write", "all-options", "options-first"],
)
def test_fr_002_53_arguments_reach_run_bench_in_order(world, args: list[str]) -> None:
    world.monkeypatch.setenv("PS_BENCH_ARGV_FILE", str(world.base / "bench-argv.json"))
    r = world.cli("bench", "env", *args)
    assert r.code == 0, r.text
    argv = recorded(world)
    assert argv[1:] == args, argv
    assert world.ledger_rows() == [] and world.run_dirs() == []


@pytest.mark.req("FR-002-53")
def test_fr_002_53_under_a_hold_the_real_run_bench_exits_4_through_the_command_without_gpu_libraries(world) -> None:
    world.monkeypatch.setenv(
        "PITSTUDIO_REPO", str(rw.ROOT)
    )  # the real studio/bench/run_bench.py (safe: the hold stops it first)
    world.hold("bugcheck under investigation")
    rw.block_modules(world.monkeypatch, "pynvml", "filelock")
    calls = rw.forbid_popen(world.monkeypatch)
    r = world.cli("bench", "env", "warp_newton", "--no-write")
    assert r.code == 4, r.text
    assert "bugcheck under investigation" in r.text and "not starting" in r.text
    assert calls == []


@pytest.mark.req("FR-002-53")
def test_fr_002_53_the_real_run_bench_rejects_an_unknown_probe_before_touching_the_gpu(world) -> None:
    world.monkeypatch.setenv("PITSTUDIO_REPO", str(rw.ROOT))
    rw.block_modules(world.monkeypatch, "pynvml", "filelock")
    calls = rw.forbid_popen(world.monkeypatch)
    r = world.cli("bench", "env", "../../etc/passwd")
    assert r.code == 2, r.text
    assert calls == []


@pytest.mark.req("FR-002-53")
@pytest.mark.parametrize(
    "argv", [["bench"], ["bench", "st50_physics"], ["bench", "suite", "x"]], ids=["bare", "suite-name", "unknown-sub"]
)
def test_fr_002_53_bench_without_env_is_not_a_command(world, argv: list[str]) -> None:
    r = world.cli(*argv)
    assert r.code == 2, r.text
