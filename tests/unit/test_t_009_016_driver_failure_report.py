"""T-009-016 (fix): a failure inside a render block is reported before the renderer closes (FR-009-02).

Requirements: FR-009-02.

The real renderer starts Isaac Sim with `--/app/fastShutdown=True`: `SimulationApp.close()` ends the process, so an
exception raised by `render_row` and closed over by the `finally` of `driver.run` was never printed. The queue run of
2026-11-22 (job 89) ended with rc=1, zero frames and no traceback in either the job log or the Kit log. The driver now
logs the exception with its traceback through `log` before it closes the renderer, and re-raises it.

Oracle: the renderer double records, at the moment `close()` is called, every line logged so far; a process killed by
`close()` keeps exactly those lines.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_isaac.sdg import driver  # noqa: E402


class _FailingRenderer:
    """`render_row` raises; `close()` snapshots the log, as a process ended by a fast shutdown would keep it."""

    def __init__(self, logged: list[str]) -> None:
        self._logged = logged
        self.at_close: list[str] | None = None

    def render_row(self, row, out_dir):
        raise KeyError("rgb annotator returned no data")

    def close(self) -> None:
        self.at_close = list(self._logged)


@contextlib.contextmanager
def _no_session():
    yield None


def _row(rid: str) -> dict:
    return {"record_id": rid, "arm": "structured"}


@pytest.mark.req("FR-009-02")
def test_a_render_failure_is_logged_with_its_traceback_before_the_renderer_closes(tmp_path: Path) -> None:
    logged: list[str] = []
    renderers: list[_FailingRenderer] = []

    def factory() -> _FailingRenderer:
        renderers.append(_FailingRenderer(logged))
        return renderers[-1]

    with pytest.raises(KeyError, match="rgb annotator returned no data"):
        driver.run(
            rows=[_row("pit-s-00000"), _row("pit-s-00001")],
            root=tmp_path,
            renderer_factory=factory,
            session=_no_session,
            log=logged.append,
        )
    at_close = "\n".join(renderers[0].at_close or [])
    assert "pit-s-00000" in at_close  # the row that failed is named
    assert "KeyError" in at_close
    assert "rgb annotator returned no data" in at_close
    assert "Traceback (most recent call last)" in at_close
    assert "render_row" in at_close  # the frame that raised is in the traceback


@pytest.mark.req("FR-009-02")
def test_a_failure_while_starting_the_renderer_is_logged_too(tmp_path: Path) -> None:
    logged: list[str] = []

    def factory():
        raise RuntimeError("the scene has no /World/Lights/Sun")

    with pytest.raises(RuntimeError, match="no /World/Lights/Sun"):
        driver.run(
            rows=[_row("pit-s-00000")], root=tmp_path, renderer_factory=factory, session=_no_session, log=logged.append
        )
    text = "\n".join(logged)
    assert "RuntimeError" in text
    assert "Traceback (most recent call last)" in text
