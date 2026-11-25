# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: PT018  (compound assertions read as one fact in these tests)
"""`run`: stills, flyover frames, clip, manifest, digests, resume and the refusals, with a backend double."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml
from conftest import RECIPE_PATH, FakeBackend, fake_encode, make_scene
from pitstudio_rtx.render.encode import EncodeInfo
from pitstudio_rtx.render.recipe import Recipe, RenderRecipeError
from pitstudio_rtx.render.run import RenderError, RenderResumeError, run

FORBIDDEN_KEYS = {
    "wall_s",
    "gpu_hours",
    "gpu_seconds",
    "frame_time_ms",
    "throughput",
    "ended",
    "finished",
    "end_time",
    "render_fps",
}
HUGE = 10**12


def keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from keys(v)


def go(recipe, out, data_root, backend=None, **kw):
    backend = backend or FakeBackend()
    kw.setdefault("encode", fake_encode)
    kw.setdefault("disk_free", lambda path: HUGE)
    return run(recipe, out, backend=backend, data_root=data_root, **kw), backend


def test_full_run_outputs_and_manifest(small_recipe, data_root, tmp_path):
    out = tmp_path / "out"
    result, _ = go(
        small_recipe, out, data_root, gpu={"name": "NVIDIA RTX 5000 Ada Generation Laptop GPU", "driver": "582.78"}
    )
    assert sorted(p.name for p in (out / "stills").iterdir()) == sorted(
        f"{s['id']}.png" for s in small_recipe.data["stills"]
    )
    assert sorted(p.name for p in (out / "flyover").iterdir()) == [f"frame_{i:05d}.png" for i in range(6)]
    assert (out / "flyover.mp4").read_bytes() == b"mp4:6"
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert result.manifest == m
    assert m["kind"] == "render" and m["schema_version"] == "1.0"
    assert re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-bingham-flyover", m["run_id"])
    assert m["label"] == "Rendered with NVIDIA Omniverse RTX (ovrtx)"
    assert m["producer"] == {"tool": "test-double", "version": "0.0.0", "runtime": "none"}
    assert m["recipe"] == {
        "id": "bingham-flyover",
        "path": "render/bingham-flyover.yaml",
        "sha256": small_recipe.sha256,
    }
    assert re.fullmatch(r"[0-9a-f]{64}", m["scene"]["sha256"])
    assert m["scene"]["id"] == "a1-bingham"
    assert m["resolution"] == [32, 18]
    assert m["frames"] == {"stills": 6, "flyover": 6, "playback_fps": 30, "duration_s": 0.2}
    assert m["missing_layers"] == []
    assert m["gpu"] == {"name": "NVIDIA RTX 5000 Ada Generation Laptop GPU", "driver": "582.78"}
    assert m["encoder"]["name"] == "h264_nvenc" and m["encoder"]["fallback"] is False
    assert m["reduced"] is True
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", m["created"])
    assert len(m["artefacts"]) == 6 + 6 + 1


def test_artefact_records_match_the_files(small_recipe, data_root, tmp_path):
    out = tmp_path / "out"
    go(small_recipe, out, data_root)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    ids = set()
    for a in m["artefacts"]:
        data = (out / a["path"]).read_bytes()
        assert a["sha256"] == hashlib.sha256(data).hexdigest() and a["bytes"] == len(data)
        assert a["kind"] in {"image", "video"} and a["producer"]["tool"] == "test-double"
        assert a["producer"]["stage"]["id"] == "rtx_render"
        assert a["media_type"] == ("video/mp4" if a["kind"] == "video" else "image/png")
        ids.add(a["id"])
    assert len(ids) == len(m["artefacts"])
    clip = next(a for a in m["artefacts"] if a["kind"] == "video")
    assert clip["encoder"]["codec"] == "h264" and clip["encoder"]["frames"] == 6 and clip["encoder"]["fps"] == 30


def test_digests_file_covers_every_file(small_recipe, data_root, tmp_path):
    out = tmp_path / "out"
    go(small_recipe, out, data_root)
    lines = (out / "digests.sha256").read_text(encoding="utf-8").splitlines()
    listed = {}
    for line in lines:
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
        listed[name] = digest
    on_disk = {
        p.relative_to(out).as_posix()
        for p in out.rglob("*")
        if p.is_file() and p.name not in {"digests.sha256", ".render-state.json"}
    }
    assert set(listed) == on_disk
    assert "manifest.json" in listed and lines == sorted(lines, key=lambda s: s.split("  ", 1)[1])


def test_no_performance_number_in_any_publishable_file(small_recipe, data_root, tmp_path):
    out = tmp_path / "out"
    go(small_recipe, out, data_root)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert not set(keys(m)) & FORBIDDEN_KEYS
    for p in out.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".sha256"}:
            assert "gpu_hours" not in p.read_text(encoding="utf-8")
    local = tmp_path / "out.local.json"  # outside the publishable folder
    doc = json.loads(local.read_text(encoding="utf-8"))
    assert doc["performance"] == "local-only" and "gpu_hours" in doc and len(doc["sessions"]) == 1


def test_missing_layer_is_rendered_without_and_reported(small_recipe, tmp_path):
    root = tmp_path / "d"
    make_scene(root, layers=("lights", "design", "terrain"), materials=False)
    out = tmp_path / "out"
    go(small_recipe, out, root)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["missing_layers"] == ["fleet", "materials"]
    assert any("fleet" in n and "materials" in n for n in m["notes"])


def test_missing_scene_is_refused_and_nothing_is_written(small_recipe, tmp_path):
    out = tmp_path / "out"
    backend = FakeBackend()
    with pytest.raises(RenderRecipeError, match="scene root not found"):
        go(small_recipe, out, tmp_path / "nowhere", backend)
    assert not out.exists() and backend.opened == 0


def test_resume_skips_written_frames(small_recipe, data_root, tmp_path):
    out = tmp_path / "out"
    with pytest.raises(RuntimeError, match="boom"):
        go(small_recipe, out, data_root, FakeBackend(fail_at_apply=9))  # the first apply is the noise-floor calibration
    done = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*.png")}
    assert len(done) == 8
    assert not (out / "manifest.json").exists()  # an interrupted run publishes nothing
    result, second = go(small_recipe, out, data_root)
    assert len(second.applied) == 4  # only the missing poses
    assert result.skipped == 8 and result.rendered == 4
    for name, data in done.items():
        assert (out / name).read_bytes() == data
    assert (out / "manifest.json").is_file()
    assert len(list(out.rglob("*.png"))) == 12


def test_corrupt_or_partial_files_are_rendered_again(small_recipe, data_root, tmp_path):
    out = tmp_path / "out"
    go(small_recipe, out, data_root)
    (out / "flyover" / "frame_00002.png").write_bytes(b"")
    (out / "flyover" / "frame_00003.png").write_bytes(b"not a png")
    (out / "flyover" / "frame_00004.png.part").write_bytes(b"left over")
    (out / "flyover.mp4").unlink()
    result, backend = go(small_recipe, out, data_root)
    assert result.rendered == 2 and len(backend.applied) == 2
    assert not list(out.rglob("*.part"))


def test_resume_false_renders_everything(small_recipe, data_root, tmp_path):
    out = tmp_path / "out"
    go(small_recipe, out, data_root)
    result, backend = go(small_recipe, out, data_root, resume=False)
    assert len(backend.applied) == 12 + 1 and result.skipped == 0  # plus the noise-floor calibration


def test_resume_refuses_a_changed_recipe(small_recipe, data_root, tmp_path):
    out = tmp_path / "out"
    with pytest.raises(RuntimeError, match="boom"):
        go(small_recipe, out, data_root, FakeBackend(fail_at_apply=3))
    changed = Recipe(data=small_recipe.data, sha256="0" * 64, path=small_recipe.path)
    with pytest.raises(RenderResumeError, match="recipe"):
        go(changed, out, data_root)


def test_resume_refuses_a_changed_scene(small_recipe, data_root, tmp_path):
    out = tmp_path / "out"
    with pytest.raises(RuntimeError, match="boom"):
        go(small_recipe, out, data_root, FakeBackend(fail_at_apply=3))
    (data_root / "processed/scene/a1-bingham/st45_validate/scene/layers/design.usda").write_bytes(b"edited")
    with pytest.raises(RenderResumeError, match="scene"):
        go(small_recipe, out, data_root)


def test_clip_is_not_encoded_twice(small_recipe, data_root, tmp_path):
    out, calls = tmp_path / "out", []

    def counting(*args):
        calls.append(1)
        return fake_encode(*args)

    go(small_recipe, out, data_root, encode=counting)
    go(small_recipe, out, data_root, encode=counting)
    assert len(calls) == 1


def test_guard_tick_before_every_renderer_step(small_recipe, data_root, tmp_path):
    ticks = []
    _, backend = go(small_recipe, tmp_path / "out", data_root, tick=lambda: ticks.append(1))
    assert len(ticks) == backend.steps > 0
    recipe_steps = sum(p.steps for p in __import__("pitstudio_rtx.render.plan", fromlist=["plan"]).plan(small_recipe))
    first = __import__("pitstudio_rtx.render.plan", fromlist=["plan"]).plan(small_recipe)[0]
    assert backend.steps == recipe_steps + first.steps + 1  # the calibration: the first pose and one more step


def test_ignored_ovstage_camera_falls_back_to_reload_and_records_it(small_recipe, data_root, tmp_path):
    backend = FakeBackend(ignore_ovstage=True)
    go(small_recipe, tmp_path / "out", data_root, backend)
    assert backend.mode == "reload"
    m = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert m["camera_update"] == "reload" and any("reload" in n for n in m["notes"])


def test_ovstage_camera_mode_is_recorded_when_it_works(small_recipe, data_root, tmp_path):
    go(small_recipe, tmp_path / "out", data_root)
    m = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert m["camera_update"] == "ovstage"


def test_a_camera_that_never_moves_stops_the_run_before_the_clashing_still_is_written(
    small_recipe, data_root, tmp_path
):
    out = tmp_path / "out"
    with pytest.raises(RenderError, match="distinct"):
        go(small_recipe, out, data_root, FakeBackend(ignore_all=True))
    written = sorted(p.name for p in (out / "stills").glob("*.png"))
    assert written == [f"{small_recipe.data['stills'][0]['id']}.png"]  # only the first still: it clashes with nobody


def test_the_distinct_threshold_comes_from_the_measured_noise_floor_and_is_recorded(small_recipe, data_root, tmp_path):
    go(small_recipe, tmp_path / "out", data_root)
    state = json.loads((tmp_path / "out" / ".render-state.json").read_text(encoding="utf-8"))
    d = state["distinct"]
    assert 0.0 < d["noise_floor"] < 2.0  # the double wobbles by one level between step counts
    assert d["threshold"] == pytest.approx(max(small_recipe.data["distinct"]["min_threshold"], 10 * d["noise_floor"]))
    assert d["min_still_difference"] > d["threshold"]
    m = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert any("distinct" in n and "noise floor" in n for n in m["notes"])


def test_a_dark_scene_is_lit_until_every_image_is_inside_the_exposure_band(small_recipe, data_root, tmp_path):
    from pitstudio_rtx.render.checks import luminance
    from pitstudio_rtx.render.imageio import read_png

    out = tmp_path / "out"
    backend = FakeBackend(brightness=0.2)
    go(small_recipe, out, data_root, backend)
    lo, hi = small_recipe.data["exposure"]["band"]
    for png in [*(out / "stills").glob("*.png"), *(out / "flyover").glob("*.png")]:
        assert lo <= luminance(read_png(png)) <= hi, png.name
    assert max(backend.gains) > 2.0  # the lights were raised to get there
    state = json.loads((out / ".render-state.json").read_text(encoding="utf-8"))
    assert all(lo <= v["luminance"] <= hi for v in state["images"].values())


def test_an_image_that_light_cannot_bring_into_the_band_is_refused_and_not_written(small_recipe, data_root, tmp_path):
    out = tmp_path / "out"
    with pytest.raises(RenderError, match="exposure"):
        go(small_recipe, out, data_root, FakeBackend(brightness=0.2, ignore_gain=True))
    assert not list((out / "stills").glob("*.png"))


def test_flat_image_is_refused(small_recipe, data_root, tmp_path):
    with pytest.raises(RenderError, match="flat"):
        go(small_recipe, tmp_path / "out", data_root, FakeBackend(flat=True))
    assert not list((tmp_path / "out").rglob("*.png"))


def test_disk_preflight_refuses_before_rendering(small_recipe, data_root, tmp_path):
    backend = FakeBackend()
    with pytest.raises(RenderError, match="free disk"):
        go(small_recipe, tmp_path / "out", data_root, backend, disk_free=lambda path: 1000)
    assert backend.opened == 0 and not (tmp_path / "out").exists()


def test_disk_estimate_above_the_limit_is_refused(data_root, tmp_path):
    from pitstudio_rtx.render.recipe import load_recipe

    data = yaml.safe_load(RECIPE_PATH.read_text(encoding="utf-8"))
    data["output"]["disk_limit_gib"] = 1
    recipe = Recipe(data=data, sha256="1" * 64, path="render/x.yaml")
    backend = FakeBackend()
    with pytest.raises(RenderError, match="disk limit"):
        go(recipe, tmp_path / "out", data_root, backend)
    assert backend.opened == 0
    assert load_recipe(RECIPE_PATH).data["output"]["disk_limit_gib"] == 10


def test_encoder_fallback_is_recorded(small_recipe, data_root, tmp_path):
    def fallback(frames_dir, pattern, fps, out, output):
        out.write_bytes(b"x")
        return EncodeInfo(name="libx264", fallback=True, ffmpeg_version="8.1", args=["-c:v", "libx264"])

    go(small_recipe, tmp_path / "out", data_root, encode=fallback)
    m = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert m["encoder"] == {"name": "libx264", "fallback": True, "ffmpeg_version": "8.1"}
    assert any("libx264" in n and "NVENC" in n for n in m["notes"])


def test_no_machine_path_in_the_manifest(small_recipe, data_root, tmp_path):
    go(small_recipe, tmp_path / "out", data_root)
    text = (tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in text and not re.search(r"\b[A-Za-z]:[\\/]|/Users/|/home/", text)


def test_backend_is_closed_even_on_failure(small_recipe, data_root, tmp_path):
    backend = FakeBackend(fail_at_apply=1)
    with pytest.raises(RuntimeError, match="boom"):
        go(small_recipe, tmp_path / "out", data_root, backend)
    assert backend.closed == 1


def test_package_has_no_placeholder_code():
    pkg = Path(__file__).resolve().parents[1] / "src" / "pitstudio_rtx" / "render"
    text = "\n".join(p.read_text(encoding="utf-8") for p in pkg.glob("*.py"))
    assert not re.search(r"NotImplementedError|\bTODO\b|\bFIXME\b|(?i:placeholder|\bstub\b)|FakeBackend", text)
