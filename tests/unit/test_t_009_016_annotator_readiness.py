# ruff: noqa: PT018
"""T-009-016 (fix): the Isaac renderer plays the timeline and a failed run cannot pass (FR-009-02).

Requirements: FR-009-02, NFR-009-03.

Bisection of 2026-11-22 on Isaac Sim 6.1 headless: every Replicator annotator returned an empty array (rgb (0,)) for
30 steps while the timeline was stopped, on a cube scene as on the Bingham scene; with `timeline.play()` and two
`app.update()` before the steps the first step is still empty and the second returns the 1280x720 image. So the renderer
(a) plays the timeline before it creates the render product's first capture, (b) steps with `pause_timeline=False`, and
(c) reads through `capture_until_ready`, which steps until every annotator has data in a bounded number of attempts and
raises `EmptyAnnotatorData` otherwise (an empty array is never written as a frame).

The Isaac process also ends in `renderer.close()` (fast shutdown, exit status 0), so the driver writes `run_result.json`
before it closes the renderer and the job script checks it with `run_job --check-result`.

Oracles: the number of steps a double needs before it returns data (counted by hand), the exit codes written in the
module contract (0 complete or limited, 75 block over with frames left, 1 failed or unknown).
"""

from __future__ import annotations

import contextlib
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_isaac.sdg import driver, run_job, scene_render  # noqa: E402

FULL = (np.ones((4, 6, 4), np.uint8), np.ones((4, 6), np.float32), {"data": np.ones((4, 6), np.uint32), "info": {}})
EMPTY = (np.zeros((0,), np.uint8), np.zeros((0,), np.float32), {"data": np.zeros((0, 0), np.uint32), "info": {}})


def _stepper(ready_after: int):
    """A step double and a read double: data from the `ready_after`-th step on (1 = at once)."""
    calls = {"steps": 0}

    def step() -> None:
        calls["steps"] += 1

    def read():
        return FULL if calls["steps"] >= ready_after else EMPTY

    return calls, step, read


@pytest.mark.req("FR-009-02")
@pytest.mark.parametrize("ready_after", [1, 2, 5])
def test_capture_steps_until_every_annotator_has_data(ready_after: int) -> None:
    calls, step, read = _stepper(ready_after)
    rgb, depth, seg = scene_render.capture_until_ready(step, read, max_attempts=8)
    assert calls["steps"] == ready_after
    assert rgb.shape == (4, 6, 4) and depth.shape == (4, 6) and seg["data"].shape == (4, 6)


@pytest.mark.req("FR-009-02")
def test_capture_raises_a_clear_error_after_a_bounded_number_of_steps() -> None:
    calls, step, read = _stepper(99)
    with pytest.raises(scene_render.EmptyAnnotatorData, match=r"rgb, depth, segmentation.*3 steps"):
        scene_render.capture_until_ready(step, read, max_attempts=3)
    assert calls["steps"] == 3


@pytest.mark.req("FR-009-02")
def test_one_empty_annotator_is_not_ready() -> None:
    """RGB present but depth empty (job 88 found exactly this shape) keeps stepping, then fails."""
    calls = {"steps": 0}

    def step() -> None:
        calls["steps"] += 1

    def read():
        return FULL[0], EMPTY[1], FULL[2]

    with pytest.raises(scene_render.EmptyAnnotatorData, match="depth"):
        scene_render.capture_until_ready(step, read, max_attempts=2)
    assert calls["steps"] == 2


# ---------------------------------------------------------------------------------------------------------------
# start-up order of the Isaac renderer (fake Kit modules)
# ---------------------------------------------------------------------------------------------------------------
def _fake_kit(monkeypatch: pytest.MonkeyPatch, events: list[str]):
    class _App:
        def update(self) -> None:
            events.append("update")

    class _Annotator:
        def attach(self, products) -> None:
            events.append("attach")

    class _Registry:
        @staticmethod
        def get_annotator(name, init_params=None):
            return _Annotator()

    class _Timeline:
        def play(self) -> None:
            events.append("play")

    def mod(name: str, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, m)
        return m

    rep = mod(
        "omni.replicator.core",
        orchestrator=types.SimpleNamespace(set_capture_on_play=lambda flag: events.append(f"capture_on_play={flag}")),
        create=types.SimpleNamespace(render_product=lambda cam, res: events.append("render_product") or object()),
        AnnotatorRegistry=_Registry,
    )
    timeline = mod("omni.timeline", get_timeline_interface=lambda: _Timeline())
    mod("omni", replicator=types.SimpleNamespace(core=rep), timeline=timeline)
    mod("carb")
    stage_mod = mod(
        "isaacsim.core.experimental.utils.stage",
        open_stage=lambda path: events.append("open_stage") or (True, object()),
    )
    mod("isaacsim")
    mod("isaacsim.core")
    mod("isaacsim.core.experimental")
    mod("isaacsim.core.experimental.utils", stage=stage_mod)
    monkeypatch.setattr(scene_render, "_start_isaac", lambda: _App())
    monkeypatch.setattr(scene_render.SdgRenderer, "_prepare_stage", lambda self, stage: events.append("prepare"))


@pytest.mark.req("FR-009-02")
def test_the_timeline_plays_after_the_render_product_exists_and_before_the_first_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _fake_kit(monkeypatch, events)
    scene_render.SdgRenderer(tmp_path, {})
    assert events.index("capture_on_play=False") < events.index("open_stage") < events.index("prepare")
    last_attach = len(events) - 1 - events[::-1].index("attach")
    play = events.index("play")
    assert events.index("render_product") < play, events
    assert play > last_attach, "the timeline plays once every annotator is attached"
    assert events[play + 1 :].count("update") >= 2, "two app updates follow the play (Isaac Sim troubleshooting)"


# ---------------------------------------------------------------------------------------------------------------
# result file and exit status
# ---------------------------------------------------------------------------------------------------------------
class _SnapshotRenderer:
    """`close()` snapshots the result file as a process ended by the fast shutdown would leave it."""

    def __init__(self, root: Path, *, fail: bool = False) -> None:
        self.root, self.fail, self.at_close = root, fail, None

    def render_row(self, row, out_dir):
        if self.fail:
            raise RuntimeError("rgb annotator returned no data")
        raise AssertionError("not reached")

    def close(self) -> None:
        path = self.root / driver.RESULT_FILE
        self.at_close = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


@contextlib.contextmanager
def _no_session():
    yield None


def _row(rid: str) -> dict:
    return {"record_id": rid, "arm": "structured"}


@pytest.mark.req("FR-009-02")
def test_a_failed_run_leaves_a_failed_result_before_the_renderer_closes(tmp_path: Path) -> None:
    renderers: list[_SnapshotRenderer] = []

    def factory() -> _SnapshotRenderer:
        renderers.append(_SnapshotRenderer(tmp_path, fail=True))
        return renderers[-1]

    with pytest.raises(RuntimeError):
        driver.run(
            rows=[_row("pit-s-00000")], root=tmp_path, renderer_factory=factory, session=_no_session, log=lambda m: None
        )
    snap = renderers[0].at_close
    assert snap is not None and snap["status"] == "failed"
    assert "rgb annotator returned no data" in snap["error"]
    assert driver.result_exit_code(tmp_path) == 1


@pytest.mark.req("FR-009-02")
def test_a_failure_while_starting_the_renderer_is_a_failed_result(tmp_path: Path) -> None:
    def factory():
        raise RuntimeError("no /World/Lights/Sun")

    with pytest.raises(RuntimeError):
        driver.run(
            rows=[_row("pit-s-00000")], root=tmp_path, renderer_factory=factory, session=_no_session, log=lambda m: None
        )
    assert driver.result_exit_code(tmp_path) == 1


@pytest.mark.req("FR-009-02")
def test_no_result_file_is_a_failure_and_a_stale_result_is_removed_at_start(tmp_path: Path) -> None:
    assert driver.result_exit_code(tmp_path) == 1  # the process died before it wrote anything
    (tmp_path / driver.RESULT_FILE).write_text(json.dumps({"status": "complete", "remaining": 0}), encoding="utf-8")

    def factory():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        driver.run(
            rows=[_row("pit-s-00000")], root=tmp_path, renderer_factory=factory, session=_no_session, log=lambda m: None
        )
    assert json.loads((tmp_path / driver.RESULT_FILE).read_text(encoding="utf-8"))["status"] == "failed"


@pytest.mark.req("FR-009-02")
@pytest.mark.parametrize(
    ("doc", "code"),
    [
        ({"status": "complete", "remaining": 0}, 0),
        ({"status": "limited", "remaining": 7}, 0),
        ({"status": "partial", "remaining": 7}, 75),
        ({"status": "failed", "remaining": 7, "error": "x"}, 1),
        ({"status": "complete", "remaining": 3}, 1),  # a result that claims more than it did cannot pass
        ({"status": "unknown", "remaining": 0}, 1),
    ],
)
def test_the_exit_status_follows_the_result_file(tmp_path: Path, doc: dict, code: int) -> None:
    (tmp_path / driver.RESULT_FILE).write_text(json.dumps(doc), encoding="utf-8")
    assert driver.result_exit_code(tmp_path) == code
    assert run_job.main(["--check-result", "--out-root", str(tmp_path)]) == code
    assert driver.EXIT_BLOCK_OVER == 75


@pytest.mark.req("FR-009-02")
def test_a_guard_block_end_with_frames_left_is_partial_and_a_full_run_is_complete(tmp_path: Path) -> None:
    """Uses the CPU renderer: two rows, a guard that ends the block after the first frame, then a clean second run."""
    from pitstudio_isaac.sdg.cpu_renderer import CpuRenderer

    class _EndOfProcess(Exception):
        """The real guard sleeps in `cool_down`; with the Isaac renderer the process has ended before that."""

    class _Guard:
        def check(self) -> str:
            return "cooldown"

        def cool_down(self) -> None:
            raise _EndOfProcess

    @contextlib.contextmanager
    def session():
        yield _Guard()

    # a table row of the real format is needed by the CPU renderer: reuse the shard driver's helper
    sys.path.insert(0, str(Path(__file__).parent))
    from test_t_009_016_shard_driver import _row as table_row

    rows = [table_row("pit-s-00000"), table_row("pit-s-00001", x=45.0)]
    with pytest.raises(_EndOfProcess):
        driver.run(rows=rows, root=tmp_path, renderer_factory=CpuRenderer, session=session, log=lambda m: None)
    doc = json.loads((tmp_path / driver.RESULT_FILE).read_text(encoding="utf-8"))
    assert doc["status"] == "partial" and doc["remaining"] == 1 and doc["rendered"] == 1
    assert driver.result_exit_code(tmp_path) == driver.EXIT_BLOCK_OVER
    driver.run(rows=rows, root=tmp_path, renderer_factory=CpuRenderer, session=_no_session, log=lambda m: None)
    assert json.loads((tmp_path / driver.RESULT_FILE).read_text(encoding="utf-8"))["status"] == "complete"
    assert driver.result_exit_code(tmp_path) == 0
