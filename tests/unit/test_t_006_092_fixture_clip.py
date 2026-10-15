# ruff: noqa: E501, PT018
"""T-006-092: fixture frames: the encode marks its outputs `fixture: true` and publishes none.

Requirements: FR-006-23.

Spec: specs/006-media-telemetry/spec.md FR-006-23 (while the frame manifest (DC-006-01) or the frames that `st56_encode` reads are a contract
fixture, the stage encodes them for tests, marks the clip pair and the encode report `fixture: true`, and writes them to no published location);
specs/000-foundation/spec.md FR-000-23 and the module map's availability states (ADR-0040); plan.md test strategy (hand calculation: a fixture frame
manifest gives a clip pair and an encode report `fixture: true` under the run folder and nothing under the published asset folder).

Oracle: hand-built jobs on the fake FFmpeg with the hand-calculable curves of the test kit (AV1 chosen cq 34, H.264 chosen cq 32); the literal marks;
a directory listing of everything the run wrote.

Expected API (as in test_t_006_013 for `encode.run`), plus the fixture rules the spec leaves open (see the report):
    a run is a fixture run when the parsed frame manifest has `"fixture": true` or `job["params"]["fixture"] is True`; a non-boolean `fixture`
    (a string, a number) in either place raises `pitstudio_studio.media.errors.FramesInvalid` (or TypeError / ValueError) before any encode.
    On a fixture run the stage encodes exactly as on a real run (same files, same encode report content), and additionally:
      * the encode report has `"fixture": true` at its top level and on every entry of `clips`;
      * no output of the stage result carries an `artefact` entry (nothing is offered for publication, also when `params["publish"]` is true);
      * the result's `message` contains the word "fixture";
      * every file written lies under `job["output_dir"]` (or `job["scratch_dir"]`).
    A non-fixture run has no `fixture` key in its report, or `false`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_studio.media.errors import FramesInvalid


def tree(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file()}


def report_of(ctx) -> dict:
    return json.loads((ctx.out / "encode-report.json").read_text(encoding="utf-8"))


@pytest.mark.req("FR-006-23")
def test_a_fixture_manifest_is_encoded_and_the_report_and_clips_are_marked(tmp_path, monkeypatch):
    ctx = kit.prepare(tmp_path, monkeypatch, extra={"fixture": True})
    result = ctx.run()
    report = report_of(ctx)
    assert report["fixture"] is True and all(c["fixture"] is True for c in report["clips"])
    # encoded exactly like a real run: the hand-calculated settings and both files exist
    clip = report["clips"][0]
    assert (clip["variants"]["av1"]["chosen_cq"], clip["variants"]["h264"]["chosen_cq"]) == (34, 32)
    assert (
        (ctx.out / "fixture-clip.av1.mp4").is_file()
        and (ctx.out / "fixture-clip.h264.mp4").is_file()
        and (ctx.out / "fixture-clip.webp").is_file()
    )
    assert ctx.ff.n_encodes() > 0
    assert "fixture" in result["message"].lower()


@pytest.mark.req("FR-006-23")
def test_a_fixture_run_offers_nothing_for_publication_even_when_the_recipe_publishes(tmp_path, monkeypatch):
    ctx = kit.prepare(tmp_path, monkeypatch, extra={"fixture": True}, params={"publish": True})
    result = ctx.run()
    assert result["outputs"], "the clip pair and the report are still listed as outputs"
    assert all("artefact" not in o for o in result["outputs"])


@pytest.mark.req("FR-006-23")
def test_a_fixture_run_writes_only_under_the_run_folders(tmp_path, monkeypatch):
    ctx = kit.prepare(tmp_path, monkeypatch, extra={"fixture": True})
    before = tree(tmp_path)
    ctx.run()
    new = tree(tmp_path) - before
    out, scratch = ctx.out.resolve(), Path(ctx.job["scratch_dir"]).resolve()
    assert new and all(out in p.resolve().parents or scratch in p.resolve().parents for p in new)
    assert not [p for p in new if "assets" in p.parts or "public" in p.parts]


@pytest.mark.req("FR-006-23")
def test_the_job_parameter_alone_also_marks_a_fixture_run(tmp_path, monkeypatch):
    ctx = kit.prepare(tmp_path, monkeypatch, params={"fixture": True})
    ctx.run()
    report = report_of(ctx)
    assert report["fixture"] is True and all(c["fixture"] is True for c in report["clips"])


@pytest.mark.req("FR-006-23")
@pytest.mark.parametrize("flag", [False, None])
def test_an_explicit_false_or_absent_flag_is_a_real_run(tmp_path, monkeypatch, flag):
    extra = {} if flag is None else {"fixture": flag}
    ctx = kit.prepare(tmp_path, monkeypatch, extra=extra)
    result = ctx.run()
    report = report_of(ctx)
    assert report.get("fixture", False) is False and all(c.get("fixture", False) is False for c in report["clips"])
    assert any("artefact" in o for o in result["outputs"])  # the real run attaches the encoder records
    assert "fixture" not in result.get("message", "").lower()


@pytest.mark.req("FR-006-23")
@pytest.mark.parametrize("flag", ["true", "yes", 1, 0, "", [True], {"x": 1}])
def test_a_non_boolean_fixture_flag_is_rejected_before_any_encode(tmp_path, monkeypatch, flag):
    ctx = kit.prepare(tmp_path, monkeypatch, extra={"fixture": flag})
    with pytest.raises((TypeError, ValueError, FramesInvalid)):
        ctx.run()
    assert ctx.ff.n_encodes() == 0


@pytest.mark.req("FR-006-23")
@pytest.mark.parametrize("flag", ["true", 1])
def test_a_non_boolean_job_flag_is_rejected_before_any_encode(tmp_path, monkeypatch, flag):
    ctx = kit.prepare(tmp_path, monkeypatch, params={"fixture": flag})
    with pytest.raises((TypeError, ValueError, FramesInvalid)):
        ctx.run()
    assert ctx.ff.n_encodes() == 0
