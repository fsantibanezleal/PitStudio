# ruff: noqa: E501, PT018, SIM105
"""T-006-030: nested NVTX step ranges under the stage helper's range, balanced on exceptions, no-ops without `nvtx`.

Requirements: FR-006-17, P-006-08.

Spec: specs/006-media-telemetry/spec.md FR-006-17 (a studio GPU stage opens, inside the NVTX range that the stage helper opens
(`PITSTUDIO_NVTX_RANGE`, spec 002), one nested range `<range>/<step>` per declared step, for example `st50_physics/dem/step` and
`st56_encode/av1/vmaf`, balanced also when the body raises, and creates Warp timers with `use_nvtx=True`; where the `nvtx` module is not
importable or no profiler is attached the ranges do nothing) and P-006-08 (for any sequence of steps, some of which raise, every pushed
range is popped exactly once, in last-in-first-out order; random step trees of depth <= 4 with random exceptions); spec 002 FR-002-26
(the stage helper opens the range named `PITSTUDIO_NVTX_RANGE` with `nvtx.start_range` where `nvtx` is importable).

Oracle: the push and pop sequence the test computes itself from the shape of each step tree (a push on entry, a pop on exit in last-in-first-out
order, also when the body raises); a fake `nvtx` module (tests/support/p006_kit.py) that records every call; the real `nvtx` package with
no profiler attached (documented as a no-op) when it is importable.

Expected API of the implementation (module `pitstudio_studio.telemetry.nvtx`):
    StepRanges(*, env=None, nvtx_module=<auto>)
        `env` defaults to `os.environ`; `range_name` is `env["PITSTUDIO_NVTX_RANGE"]` (empty string when unset). `nvtx_module` is the module to
        use (anything with `push_range`/`pop_range`, `start_range`/`end_range` or `annotate`); by default `import nvtx` is tried once and, when
        it fails, ranges do nothing; `nvtx_module=None` forces the no-op mode.
    StepRanges.step(name: str)    context manager: on entry opens the range `f"{range_name}/{name}"` (nested in whatever range is open, so the
        stage helper's range is the parent), on exit (normal or by any BaseException) closes it exactly once; never swallows the exception; a
        name that is empty or contains a control character raises ValueError on entry, before any range is opened.
    scoped_timer(name: str, *, warp=None, **kwargs) -> object
        returns `warp.ScopedTimer(name, use_nvtx=True, **kwargs)` (the `warp` module, default `import warp`); `use_nvtx` is always True.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_studio.telemetry.nvtx import StepRanges, scoped_timer

SETTINGS = settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)
BASE = "st50_physics"


class Boom(Exception):
    pass


class Stop(BaseException):
    pass


def normalise(events):
    return [(k, n) if k == "push" else (k, "") for k, n in events]


def make(base=BASE, *, fake=None):
    fake = fake or kit.FakeNVTX()
    return fake, StepRanges(env={"PITSTUDIO_NVTX_RANGE": base}, nvtx_module=fake.as_module())


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-17
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-17")
def test_a_step_opens_and_closes_one_range_named_range_slash_step():
    fake, r = make()
    with r.step("dem/step"):
        pass
    assert normalise(fake.events) == [("push", "st50_physics/dem/step"), ("pop", "")]


@pytest.mark.req("FR-006-17")
def test_the_encode_stage_example_name():
    fake, r = make("st56_encode")
    with r.step("av1/vmaf"):
        pass
    assert normalise(fake.events)[0] == ("push", "st56_encode/av1/vmaf")


@pytest.mark.req("FR-006-17")
def test_steps_nest_inside_the_stage_helpers_range():
    fake = kit.FakeNVTX()
    rng = fake.start_range(BASE)  # what the stage helper does (spec 002, FR-002-26)
    _, r = make(fake=fake)
    with r.step("dem/step"), r.step("contacts"):
        pass
    fake.end_range(rng)
    assert fake.stack_trace() == [
        "st50_physics",
        "st50_physics/st50_physics/dem/step",
        "st50_physics/st50_physics/dem/step/st50_physics/contacts",
        "st50_physics/st50_physics/dem/step",
        "st50_physics",
        "",
    ]
    assert fake.balanced()


@pytest.mark.req("FR-006-17")
def test_a_raising_body_still_closes_the_range_and_the_exception_propagates_unchanged():
    fake, r = make()
    err = Boom("kaput")
    with pytest.raises(Boom) as ei, r.step("dem/step"):
        raise err
    assert ei.value is err
    assert normalise(fake.events) == [("push", "st50_physics/dem/step"), ("pop", "")]


@pytest.mark.req("FR-006-17")
def test_a_base_exception_also_closes_the_range():
    fake, r = make()
    with pytest.raises(Stop), r.step("a"):
        raise Stop
    assert fake.balanced() and len(fake.events) == 2


@pytest.mark.req("FR-006-17")
@pytest.mark.parametrize("name", ["", "a\nb", "a\x00b", "a\x1fb", "\x7f"])
def test_invalid_step_names_are_rejected_before_any_range_is_opened(name):
    fake, r = make()
    with pytest.raises(ValueError), r.step(name):  # noqa: PT011
        pass
    assert fake.events == []


@pytest.mark.req("FR-006-17")
def test_without_the_nvtx_module_the_ranges_do_nothing_and_the_body_runs():
    r = StepRanges(env={"PITSTUDIO_NVTX_RANGE": BASE}, nvtx_module=None)
    seen = []
    with r.step("dem/step"):
        seen.append(1)
        with r.step("inner"):
            seen.append(2)
    assert seen == [1, 2]
    with pytest.raises(Boom), r.step("x"):
        raise Boom


@pytest.mark.req("FR-006-17")
def test_an_unimportable_nvtx_module_means_no_ranges_and_no_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "nvtx", None)  # `import nvtx` now raises ImportError
    r = StepRanges(env={"PITSTUDIO_NVTX_RANGE": BASE})  # auto mode
    with r.step("dem/step"):
        pass


@pytest.mark.req("FR-006-17")
def test_auto_mode_uses_the_importable_nvtx_module(monkeypatch):
    fake = kit.FakeNVTX()
    monkeypatch.setitem(sys.modules, "nvtx", fake.as_module())
    r = StepRanges(env={"PITSTUDIO_NVTX_RANGE": BASE})
    with r.step("dem/step"):
        pass
    assert normalise(fake.events) == [("push", "st50_physics/dem/step"), ("pop", "")]


@pytest.mark.req("FR-006-17")
def test_the_real_nvtx_package_without_a_profiler_is_a_no_op():
    import nvtx  # the studio environment locks nvtx 0.2.16 (plan.md, technical context)

    r = StepRanges(env={"PITSTUDIO_NVTX_RANGE": BASE}, nvtx_module=nvtx)
    with r.step("dem/step"):
        value = 41 + 1
    assert value == 42


@pytest.mark.req("FR-006-17")
def test_warp_timers_are_created_with_use_nvtx_true():
    made = []

    class ScopedTimer:
        def __init__(self, name, **kw):
            made.append((name, kw))

    warp = type("warp", (), {"ScopedTimer": ScopedTimer})
    scoped_timer("dem/step", warp=warp)
    scoped_timer("contacts", warp=warp, active=True, synchronize=False)
    assert made[0] == ("dem/step", {"use_nvtx": True})
    assert made[1] == ("contacts", {"use_nvtx": True, "active": True, "synchronize": False})


@pytest.mark.req("FR-006-17")
def test_the_encode_stage_marks_its_vmaf_steps_inside_the_helpers_range(tmp_path, monkeypatch):
    import pitstudio_stagekit
    from pitstudio_studio.media.encode import run

    fake = kit.FakeNVTX()
    monkeypatch.setitem(sys.modules, "nvtx", fake.as_module())
    monkeypatch.setenv("PITSTUDIO_NVTX_RANGE", "st56_encode")
    ctx = kit.prepare(tmp_path, monkeypatch)
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(ctx.job), encoding="utf-8")
    rc = pitstudio_stagekit.main(
        lambda job: run(job, runner=ctx.ff, clock=ctx.clock, env=ctx.env, driver_version=ctx.driver),
        ["--job", str(job_path)],
    )
    assert rc == 0 and fake.balanced()
    pushes = [n for k, n in fake.events if k == "push"]
    assert pushes[0] == "st56_encode"  # the helper's own range
    assert "st56_encode/av1/vmaf" in pushes and "st56_encode/h264/vmaf" in pushes
    assert all(n == "st56_encode" or n.startswith("st56_encode/") for n in pushes)
    assert fake.events[-1][0] == "pop"  # the helper closes its range last


@pytest.mark.req("FR-006-17")
def test_a_failing_encode_leaves_every_range_closed(tmp_path, monkeypatch):
    import pitstudio_stagekit
    from pitstudio_studio.media.encode import run

    fake = kit.FakeNVTX()
    monkeypatch.setitem(sys.modules, "nvtx", fake.as_module())
    monkeypatch.setenv("PITSTUDIO_NVTX_RANGE", "st56_encode")
    ctx = kit.prepare(tmp_path, monkeypatch, fake_kw={"decode_overrides": {".mp4": {"stderr": "decoder error\n"}}})
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(ctx.job), encoding="utf-8")
    rc = pitstudio_stagekit.main(
        lambda job: run(job, runner=ctx.ff, clock=ctx.clock, env=ctx.env, driver_version=ctx.driver),
        ["--job", str(job_path)],
    )
    assert rc == 1 and fake.balanced()  # the stage failed (decode-failed) and nothing is left open


# ---------------------------------------------------------------------------------------------------------------------
# P-006-08: random step trees
# ---------------------------------------------------------------------------------------------------------------------
NAMES = st.sampled_from(["dem/step", "contacts", "integrate", "av1/vmaf", "h264/encode", "poster", "a", "b/c/d"])


@st.composite
def trees(draw, depth=4):
    name = draw(NAMES)
    raises = draw(st.booleans())
    catches = draw(st.booleans())
    kids = [] if depth <= 1 else draw(st.lists(trees(depth=depth - 1), max_size=3))
    return (name, raises, catches, kids)


def execute(r, node, expected):
    """Run one node; record the push/pop events the specification demands (push on entry, pop on exit, LIFO)."""
    name, raises, catches, kids = node
    expected.append(("push", f"{BASE}/{name}"))
    try:
        with r.step(name):
            for kid in kids:
                if catches:
                    try:
                        execute(r, kid, expected)
                    except Boom:
                        pass
                else:
                    execute(r, kid, expected)
            if raises:
                raise Boom(name)
    finally:
        expected.append(("pop", ""))


@pytest.mark.req("P-006-08")
@SETTINGS
@given(st.lists(trees(), min_size=1, max_size=4))
def test_every_pushed_range_is_popped_once_in_last_in_first_out_order(forest):
    fake, r = make()
    expected: list[tuple[str, str]] = []
    for tree in forest:
        try:
            execute(r, tree, expected)
        except Boom:
            pass
    assert normalise(fake.events) == expected  # same events in the same order
    assert fake.balanced()
    # last-in-first-out: replaying the events with a stack never pops an empty stack and ends empty
    stack: list[str] = []
    for kind, name in normalise(fake.events):
        if kind == "push":
            stack.append(name)
        else:
            assert stack
            stack.pop()
    assert stack == []


@pytest.mark.req("P-006-08")
@SETTINGS
@given(st.lists(st.booleans(), min_size=1, max_size=30))
def test_a_flat_sequence_of_steps_some_of_which_raise_is_balanced(raising):
    fake, r = make()
    for i, bad in enumerate(raising):
        try:
            with r.step(f"s{i}"):
                if bad:
                    raise Boom(i)
        except Boom:
            pass
    assert fake.balanced() and len(fake.events) == 2 * len(raising)
    assert [n for k, n in fake.events if k == "push"] == [f"{BASE}/s{i}" for i in range(len(raising))]
