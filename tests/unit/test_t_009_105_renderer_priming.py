# ruff: noqa: E501, PT018
"""T-009-105: the Isaac renderer renders its first row twice and keeps the second render only.

Requirements: FR-009-59.

Evidence: in the gate history probe of 2026-11-23 (report sdg-finish-2026-11-23) the driver processes the structured file
first, so the first frame of the reversed order was the structured row pit-s-08438 and its sky was black (sky pixel mean
0.5 against 171 to 199 when it was the third frame); the class contact run had a black sky corner in its first frame too.
Warm-up steps (2 and 4 before the capture) and extra app updates (2 and 6) left the black sky; rendering the first row
twice and keeping the second render removed it (mean difference of that row 7.9 levels before, 2.3 and 1.9 after).

Expected (`pitstudio_isaac.sdg.scene_render.SdgRenderer`, exercised here without Isaac Sim by replacing its capture):
- `render_row` first captures the row it receives once more and discards that capture (no frame file, no sidecar data),
  then captures and writes the frame; only the first row of a renderer instance is primed;
- a second renderer instance (the next GPU block) primes again.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_isaac.sdg import scene_render  # noqa: E402

H, W = 4, 6


def _renderer(monkeypatch: pytest.MonkeyPatch, captures: list[str], written: list[str]) -> scene_render.SdgRenderer:
    r = object.__new__(scene_render.SdgRenderer)
    r.last_settings = {}

    def capture(row):
        captures.append(row["record_id"])
        seg = {"data": np.zeros((H, W), dtype=np.uint32), "info": {"idToLabels": {}, "idToSemantics": {}}}
        return np.zeros((H, W, 3), dtype=np.uint8), np.ones(H * W, dtype=np.float32), seg

    r._capture = capture
    monkeypatch.setattr(scene_render, "instance_paths", lambda *_a, **_k: {})

    def write_frame(row, out_dir, *_a, **_k):
        written.append(row["record_id"])
        return {"rec": row["record_id"]}, {}

    monkeypatch.setattr(scene_render, "write_frame", write_frame)
    return r


def _row(rid: str) -> dict:
    return {"record_id": rid, "camera": {"height_px": H, "width_px": W}, "objects": []}


@pytest.mark.req("FR-009-59")
def test_the_first_row_is_captured_twice_and_written_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captures: list[str] = []
    written: list[str] = []
    r = _renderer(monkeypatch, captures, written)
    record, _ = r.render_row(_row("a"), tmp_path / "a")
    assert captures == ["a", "a"]  # the primer, then the capture that is kept
    assert written == ["a"] and record == {"rec": "a"}


@pytest.mark.req("FR-009-59")
def test_only_the_first_row_of_a_renderer_is_primed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captures: list[str] = []
    written: list[str] = []
    r = _renderer(monkeypatch, captures, written)
    for rid in ("a", "b", "c"):
        r.render_row(_row(rid), tmp_path / rid)
    assert captures == ["a", "a", "b", "c"]
    assert written == ["a", "b", "c"]


@pytest.mark.req("FR-009-59")
def test_a_new_renderer_primes_its_first_row_again(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captures: list[str] = []
    written: list[str] = []
    for _ in range(2):  # two GPU blocks of one job
        r = _renderer(monkeypatch, captures, written)
        r.render_row(_row("x"), tmp_path / "x")
    assert captures == ["x", "x", "x", "x"]


@pytest.mark.req("FR-009-59")
def test_the_primer_leaves_no_frame_behind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captures: list[str] = []
    written: list[str] = []
    r = _renderer(monkeypatch, captures, written)
    r.render_row(_row("a"), tmp_path / "a")
    assert not list(tmp_path.rglob("*"))  # the stubbed writer wrote nothing, and the primer never writes
