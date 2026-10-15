# ruff: noqa: E501, PT018
"""T-006-022: PyNvVideoCodec previews can never be published.

Requirements: FR-006-15.

Spec: specs/006-media-telemetry/spec.md FR-006-15 (if a recipe stage selects the in-process PyNvVideoCodec encoder (local previews)
and declares any output `publish: true`, `st56_encode` fails at start with error class `not-publishable`; PyNvVideoCodec outputs are
local previews only) and the preamble of section 3 (error classes travel as the prefix of the detail, with `error_class: unknown`
in the stage result).

Oracle: hand-built jobs (mode and publish flag are the only variables); a spy runner that must not be called; the stage helper's own
result.json for the error class.

Expected API of the implementation (module `pitstudio_studio.media.encode`; error in `pitstudio_studio.media.errors`):
    errors.NotPublishable(EncodeError)     error_class "not-publishable"
    job["params"]["encoder_mode"]   "ffmpeg" (default) or "pynvvideocodec"
    job["params"]["publish"]        True when the recipe declares any output of the stage `publish: true`
    encode.run(job, ...) raises NotPublishable, before the held-lock check, FFmpeg discovery or any frame is read, when
        `encoder_mode == "pynvvideocodec"` and `publish is True`; mode "ffmpeg" with `publish: true` is the normal published path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_studio.media.encode import run
from pitstudio_studio.media.errors import EncodeError, NotPublishable


@pytest.mark.req("FR-006-15")
def test_pynvvideocodec_with_a_published_output_fails_at_start(tmp_path, monkeypatch):
    ctx = kit.prepare(tmp_path, monkeypatch, params={"encoder_mode": "pynvvideocodec", "publish": True})
    with pytest.raises(NotPublishable) as ei:
        ctx.run()
    e = ei.value
    assert isinstance(e, EncodeError) and e.error_class == "not-publishable" and str(e).startswith("not-publishable: ")
    assert ctx.ff.calls == []  # not even discovery
    assert list(ctx.out.iterdir()) == []


@pytest.mark.req("FR-006-15")
def test_the_refusal_comes_before_the_lock_check_and_before_the_frames_are_read(tmp_path, monkeypatch):
    ctx = kit.prepare(
        tmp_path, monkeypatch, held=None, params={"encoder_mode": "pynvvideocodec", "publish": True}
    )  # no held-lock list
    for p in ctx.seq.frames:
        p.unlink()  # no frames at all
    ctx.seq.manifest_path.unlink()  # not even a manifest
    with pytest.raises(NotPublishable):
        ctx.run()
    assert ctx.ff.calls == []


@pytest.mark.req("FR-006-15")
def test_the_ffmpeg_mode_may_publish(tmp_path, monkeypatch):
    ctx = kit.prepare(tmp_path, monkeypatch, params={"encoder_mode": "ffmpeg", "publish": True})
    result = ctx.run()
    assert {o["path"] for o in result["outputs"]} >= {"fixture-clip.av1.mp4", "fixture-clip.h264.mp4"}


@pytest.mark.req("FR-006-15")
def test_the_default_mode_is_ffmpeg(tmp_path, monkeypatch):
    ctx = kit.prepare(tmp_path, monkeypatch, params={"publish": True})
    assert "encoder_mode" not in ctx.job["params"]
    assert ctx.run()["outputs"]


@pytest.mark.req("FR-006-15")
def test_the_stage_result_carries_error_class_unknown_and_the_class_in_the_message(tmp_path, monkeypatch):
    import pitstudio_stagekit

    ctx = kit.prepare(tmp_path, monkeypatch, params={"encoder_mode": "pynvvideocodec", "publish": True})
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(ctx.job), encoding="utf-8")
    rc = pitstudio_stagekit.main(
        lambda job: run(job, runner=ctx.ff, clock=ctx.clock, env=ctx.env, driver_version=ctx.driver),
        ["--job", str(job_path)],
    )
    doc = json.loads((ctx.out / "result.json").read_text(encoding="utf-8"))
    assert rc == 1 and doc["status"] == "failed" and doc["error_class"] == "unknown"
    assert "not-publishable: " in doc["message"] and doc["outputs"] == []
