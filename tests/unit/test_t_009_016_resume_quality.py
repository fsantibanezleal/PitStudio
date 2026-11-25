# ruff: noqa: PT018
"""T-009-016 (fix): the first-frames probe runs on an empty dataset only; a rolling window guards every run (FR-009-02).

Requirements: FR-009-02, NFR-009-03.

Job 89 of 2026-11-22 rendered 2,408 frames, ended its first GPU block `partial` and was stopped on its resume by the
first-frames probe, which ran again on the pending rows: one legitimately flat frame (rgb std 0.02) stopped a healthy
run. Decision of the main session (owner standing directive, 2026-11-22):
- the probe (`check_probe`) runs only when the dataset root holds no valid frame yet;
- over each window of 50 consecutive frames rendered by this process, more than 5 flat frames (rgb std below 1) stop the
  run with `QualityDrift` (result file `failed`, written before the renderer closes); one legitimate flat frame never
  stops a run, a regression does within 50 frames; a shorter window at the end of a block applies the same ratio pro
  rata (more than 10 percent flat, with a floor of one frame so that a single flat frame never stops a run).

Oracles: the counts of the rule written above, by hand (5 of 50 passes, 6 of 50 stops, 1 of 7 passes, 2 of 7 stops).
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_isaac.sdg import driver  # noqa: E402
from pitstudio_isaac.sdg.cpu_renderer import CpuRenderer  # noqa: E402
from test_t_009_016_shard_driver import _Guard, _row  # noqa: E402


class _Scripted:
    """CPU renderer whose `rgb_std` is flat (0.02) for the frames whose position in this process is in `flat_at`."""

    def __init__(self, flat_at: set[int]) -> None:
        self.flat_at, self.count, self.rendered = set(flat_at), 0, []
        self._inner = CpuRenderer()
        self.closed = 0

    def render_row(self, row, out_dir):
        record, measured = self._inner.render_row(row, out_dir)
        measured = dict(measured)
        if self.count in self.flat_at:
            measured["rgb_std"] = 0.02
        self.count += 1
        self.rendered.append(row["record_id"])
        return record, measured

    def close(self) -> None:
        self.closed += 1


@contextlib.contextmanager
def _no_session():
    yield None


def _rows(n: int) -> list[dict]:
    return [_row(f"pit-s-{i:05d}", x=40.0 + (i % 50) * 0.1) for i in range(n)]


def _run(rows, root: Path, renderer: _Scripted, **kw):
    return driver.run(rows=rows, root=root, renderer_factory=lambda: renderer, session=_no_session, **kw)


def _result(root: Path) -> dict:
    return json.loads((root / driver.RESULT_FILE).read_text(encoding="utf-8"))


@pytest.mark.req("NFR-009-03")
def test_the_probe_runs_on_an_empty_dataset(tmp_path: Path) -> None:
    rows = _rows(4)
    with pytest.raises(driver.ProbeFailed, match="flat"):
        _run(rows, tmp_path, _Scripted({0}))
    assert _result(tmp_path)["status"] == "failed"


@pytest.mark.req("NFR-009-03")
def test_a_resume_does_not_run_the_probe_and_continues_in_table_order(tmp_path: Path) -> None:
    rows = _rows(8)
    _run(rows, tmp_path, _Scripted(set()), limit=2)
    resumed = _Scripted({0})  # the first frame of the resume is flat: the probe would have stopped the run
    result = _run(rows, tmp_path, resumed)
    assert result == {"rendered": 6, "remaining": 0}
    assert resumed.rendered == [f"pit-s-{i:05d}" for i in range(2, 8)]  # the first frame without a valid sidecar first
    assert _result(tmp_path)["status"] == "complete"


@pytest.mark.req("FR-009-02")
def test_one_legitimate_flat_frame_never_stops_a_run(tmp_path: Path) -> None:
    rows = _rows(60)
    _run(rows, tmp_path, _Scripted(set()), limit=3)  # a first block, so the later flat frames meet no probe
    result = _run(rows, tmp_path, _Scripted({20}))
    assert result["remaining"] == 0 and _result(tmp_path)["status"] == "complete"


@pytest.mark.req("FR-009-02")
def test_five_flat_frames_in_a_window_of_fifty_pass_and_six_stop_the_run(tmp_path: Path) -> None:
    rows = _rows(120)
    _run(rows, tmp_path / "a", _Scripted(set()), limit=3)
    assert _run(rows, tmp_path / "a", _Scripted({0, 10, 20, 30, 49}))["remaining"] == 0  # 5 of 50, then 67 clean frames
    _run(rows, tmp_path / "b", _Scripted(set()), limit=3)
    renderer = _Scripted({0, 10, 20, 30, 40, 49})  # 6 of the first 50
    with pytest.raises(driver.QualityDrift, match=r"6 flat frames in the last 50"):
        _run(rows, tmp_path / "b", renderer)
    assert renderer.count == 50  # stopped at the end of the window, not later
    result = _result(tmp_path / "b")
    assert result["status"] == "failed" and "QualityDrift" in result["error"]
    assert renderer.closed == 1  # the result file was written before the renderer closed


@pytest.mark.req("FR-009-02")
def test_a_regression_stops_the_run_within_fifty_frames_of_its_start(tmp_path: Path) -> None:
    rows = _rows(300)
    _run(rows, tmp_path, _Scripted(set()), limit=3)
    renderer = _Scripted(set(range(60, 300)))  # every frame from the 61st on is flat
    with pytest.raises(driver.QualityDrift):
        _run(rows, tmp_path, renderer)
    assert renderer.count <= 100  # the second window of 50 ends the run


@pytest.mark.req("FR-009-02")
def test_the_window_counts_only_frames_rendered_by_this_process(tmp_path: Path) -> None:
    rows = _rows(70)
    _run(rows, tmp_path, _Scripted(set()), limit=10)
    for i in range(10):  # ten flat frames left by an earlier run
        sidecar = tmp_path / "frames" / rows[i]["record_id"] / driver.SIDECAR
        doc = json.loads(sidecar.read_text(encoding="utf-8"))
        doc["measured"]["rgb_std"] = 0.02
        sidecar.write_text(json.dumps(doc), encoding="utf-8")
    assert _run(rows, tmp_path, _Scripted({0, 1}))["remaining"] == 0


@pytest.mark.req("FR-009-02")
def test_a_short_window_at_the_end_of_a_block_applies_the_ratio_pro_rata(tmp_path: Path) -> None:
    rows = _rows(30)
    _run(rows, tmp_path / "a", _Scripted(set()), limit=3)
    assert _run(rows, tmp_path / "a", _Scripted({5}))["remaining"] == 0  # 1 of 27: floor of one frame
    _run(rows, tmp_path / "b", _Scripted(set()), limit=3)
    with pytest.raises(driver.QualityDrift, match=r"4 flat frames in the last 27"):
        _run(rows, tmp_path / "b", _Scripted({1, 5, 9, 13}))  # 4 of 27 is more than 10 percent (2.7)
    _run(rows, tmp_path / "c", _Scripted(set()), limit=3)
    with pytest.raises(driver.QualityDrift, match=r"2 flat frames in the last 7"):
        _run(rows[:10], tmp_path / "c", _Scripted({0, 3}))  # 2 of 7: more than the floor of one


@pytest.mark.req("FR-009-02")
def test_each_gpu_block_end_checks_its_own_trailing_window(tmp_path: Path) -> None:
    """Blocks of 30 frames: 3 flat frames per block pass (10 percent of 30), a fourth in a block stops the run."""
    rows = _rows(130)
    _run(rows, tmp_path, _Scripted(set()), limit=3)

    def session_for(guard):
        @contextlib.contextmanager
        def session():
            yield guard

        return session

    shared = _Scripted({0, 1, 2, 30, 31, 32})  # positions in this process
    result = driver.run(
        rows=rows, root=tmp_path, renderer_factory=lambda: shared, session=session_for(_Guard(cooldown_after=30))
    )
    assert result["remaining"] == 0
    shared = _Scripted({0, 1, 2, 3})
    other = tmp_path / "other"
    _run(rows, other, _Scripted(set()), limit=3)
    with pytest.raises(driver.QualityDrift, match=r"4 flat frames in the last 30"):
        driver.run(
            rows=rows, root=other, renderer_factory=lambda: shared, session=session_for(_Guard(cooldown_after=30))
        )
