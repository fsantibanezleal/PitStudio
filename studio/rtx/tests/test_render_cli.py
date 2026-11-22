# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: PT018  (compound assertions read as one fact in these tests)
"""The dry run and the command line of `python -m pitstudio_rtx.render`, plus the clearance of the real recipe."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import numpy as np
import pytest
from conftest import RECIPE_PATH, make_scene
from pitstudio_rtx.render.__main__ import main
from pitstudio_rtx.render.plan import plan
from pitstudio_rtx.render.recipe import load_recipe
from pitstudio_rtx.render.run import RenderError, dry_run

SMI = "0, NVIDIA RTX 5000 Ada Generation Laptop GPU, 582.78, 68\n"
ENCODERS = " V....D h264_nvenc NVIDIA NVENC H.264 encoder\n"


def fake_run(smi: str = SMI, encoders: str = ENCODERS):
    def run(cmd, **kwargs):
        text = {"nvidia-smi": smi}.get(Path(cmd[0]).name, "")
        if "-encoders" in cmd:
            text = encoders
        if "-version" in cmd:
            text = "ffmpeg version n8.1.3-14-gabc\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=text, stderr="")

    return run


def test_dry_run_reports_plan_cuda_and_encoder(tmp_path, capsys):
    root = tmp_path / "d"
    make_scene(root)
    out = tmp_path / "out"
    report = dry_run(
        load_recipe(RECIPE_PATH),
        root,
        out,
        run=fake_run(),
        ffmpeg="ffmpeg",
        disk_free=lambda p: 10**12,
        ovrtx_version=lambda: "0.5.0.377615",
    )
    text = capsys.readouterr().out
    assert report.reduced_poses == {"stills": 2, "flyover": 3, "resolution": (320, 180)}
    assert report.full_poses == {"stills": 6, "flyover": 600, "resolution": (1920, 1080)}
    assert "planned frames: 2 stills + 3 flyover frames at 320x180" in text
    assert "full run: 6 stills + 600 flyover frames at 1920x1080" in text
    assert "CUDA device: NVIDIA RTX 5000 Ada Generation Laptop GPU" in text
    assert "encoder: h264_nvenc" in text
    assert "ovrtx 0.5.0.377615" in text
    assert not out.exists()  # a dry run writes nothing into the output folder


def test_dry_run_prints_no_timing(tmp_path, capsys):
    root = tmp_path / "d"
    make_scene(root)
    dry_run(
        load_recipe(RECIPE_PATH),
        root,
        tmp_path / "o",
        run=fake_run(),
        ffmpeg="ffmpeg",
        disk_free=lambda p: 10**12,
        ovrtx_version=lambda: "1",
    )
    text = capsys.readouterr().out.lower()
    assert "fps" not in text.replace("playback", "") and " ms" not in text and "seconds" not in text


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"run": fake_run(smi="")}, "no CUDA device"),
        ({"run": fake_run(encoders=" V....D mpeg4 x")}, "no H.264 encoder"),
        ({"disk_free": lambda p: 1000}, "free disk"),
        ({"ovrtx_version": lambda: None}, "ovrtx is not installed"),
    ],
)
def test_dry_run_failures(tmp_path, kwargs, message):
    root = tmp_path / "d"
    make_scene(root)
    base = {"run": fake_run(), "ffmpeg": "ffmpeg", "disk_free": lambda p: 10**12, "ovrtx_version": lambda: "1"}
    with pytest.raises((RenderError, RuntimeError), match=message):
        dry_run(load_recipe(RECIPE_PATH), root, tmp_path / "o", **{**base, **kwargs})


def test_dry_run_missing_scene(tmp_path):
    from pitstudio_rtx.render.recipe import RenderRecipeError

    with pytest.raises(RenderRecipeError, match="scene root not found"):
        dry_run(
            load_recipe(RECIPE_PATH),
            tmp_path / "none",
            tmp_path / "o",
            run=fake_run(),
            ffmpeg="ffmpeg",
            disk_free=lambda p: 10**12,
            ovrtx_version=lambda: "1",
        )


def test_main_requires_data_root_and_lock_for_a_real_run(tmp_path, capsys):
    code = main(["--recipe", str(RECIPE_PATH), "--out", str(tmp_path / "o")], env={})
    assert code == 2
    assert "PITSTUDIO_DATA" in capsys.readouterr().err
    root = tmp_path / "d"
    make_scene(root)
    code = main(["--recipe", str(RECIPE_PATH), "--out", str(tmp_path / "o")], env={"PITSTUDIO_DATA": str(root)})
    assert code == 2
    assert "PITSTUDIO_GPU_LOCK" in capsys.readouterr().err
    assert not (tmp_path / "o").exists()


def test_main_has_no_backend_switch():
    with pytest.raises(SystemExit):
        main(["--backend", "fake"], env={})


SCENE = Path(os.environ.get("PITSTUDIO_DATA", "")) / "processed/scene/a1-bingham/st45_validate/scene"


@pytest.mark.skipif(not (SCENE / "terrain/grid.zarr").is_dir(), reason="the Bingham scene is not on this machine")
def test_every_planned_eye_clears_the_terrain():
    import zarr

    elevation = np.asarray(zarr.open(str(SCENE / "terrain/grid.zarr"), mode="r")["elevation"])
    rows, cols = elevation.shape
    worst = 1e9
    for pose in plan(load_recipe(RECIPE_PATH)):
        col, row = round(pose.eye[0] + 1500), round(1400 - pose.eye[1])
        assert 0 <= row < rows and 0 <= col < cols, f"{pose.out}: eye outside the terrain grid"
        worst = min(worst, pose.eye[2] - float(elevation[row, col]))
    assert worst >= 30.0, f"closest eye is {worst:.1f} m above the terrain"
