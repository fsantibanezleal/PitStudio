# SPDX-License-Identifier: Apache-2.0
"""Render a scene recipe into stills, flyover frames, a clip, a manifest and a digest file; resumable and checked.

`run` is backend-agnostic (the backend is passed in) and holds every guard that is not the GPU's: the scene must
exist, the disk must hold the output, each frame is written atomically so an interrupted run resumes from the last
written frame, a resumed run must be the same recipe on the same scene, a flat image or a camera that does not move
the image stops the run, and nothing is published unless every image and the clip exist. `dry_run` is the
pre-flight of the GPU job: it plans a reduced render and checks every prerequisite without starting the renderer.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_rtx.backend import check_runtime_isolation
from pitstudio_rtx.render.backend import RenderBackend
from pitstudio_rtx.render.encode import EncodeInfo, encode_clip, find_ffmpeg, pick_encoder
from pitstudio_rtx.render.gpu import CudaDevice, assert_cuda_visible
from pitstudio_rtx.render.imageio import is_complete_png, write_png
from pitstudio_rtx.render.manifest import (
    DIGESTS_FILE,
    MANIFEST_FILE,
    STATE_FILE,
    build_manifest,
    dump_json,
    write_digests,
)
from pitstudio_rtx.render.plan import Pose, plan
from pitstudio_rtx.render.recipe import Recipe, Scene, resolve_scene
from pitstudio_rtx.render.usd import session_layer

PNG_BYTES_PER_RAW_BYTE = 0.75  # worst-case PNG size of a rendered image against its raw RGB size (no compression gain)
CLIP_ALLOWANCE_BYTES = 200 * 1024 * 1024
FREE_DISK_MARGIN = 1.25
FLAT_STD = 1.0  # an 8-bit image with a standard deviation below this is flat: the scene did not render
DRY_RESOLUTION = (320, 180)
DRY_STILLS = 2
DRY_FRAMES = 3
NO_EFFECT = "{}: the camera pose has no effect on the image, even with the layer re-authored per pose"
SUN_NOTE = "the scene's own sun is replaced by the recipe sun and sky (the scene has no sky and a sun straight down)"


class RenderError(RuntimeError):
    """The render cannot start or cannot continue."""


class RenderResumeError(RenderError):
    """The output folder belongs to a different recipe, scene or pose plan than the run asked for."""


@dataclass(frozen=True)
class RunResult:
    manifest_path: Path
    manifest: dict[str, Any]
    rendered: int
    skipped: int


@dataclass(frozen=True)
class DryRunReport:
    reduced_poses: dict[str, Any]
    full_poses: dict[str, Any]
    device: CudaDevice
    encoder: str
    scene: Scene


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def _existing_ancestor(path: Path) -> Path:
    path = path.resolve()
    while not path.exists():
        path = path.parent
    return path


def estimate_bytes(recipe: Recipe, poses: list[Pose]) -> int:
    """Worst-case size of the frames, the stills and the clip, from the raw image size (no compression assumed)."""
    width, height = recipe.data["camera"]["resolution"]
    return int(len(poses) * width * height * 3 * PNG_BYTES_PER_RAW_BYTE) + CLIP_ALLOWANCE_BYTES


def _preflight_disk(recipe: Recipe, poses: list[Pose], where: Path, disk_free: Callable[[Path], int]) -> None:
    need = estimate_bytes(recipe, poses)
    limit = recipe.data["output"]["disk_limit_gib"] * 2**30
    if need > limit:
        raise RenderError(
            f"the estimated output of {need / 2**30:.1f} GiB exceeds the disk limit of {limit / 2**30:.0f} GiB"
        )
    free = disk_free(_existing_ancestor(where))
    if free < need * FREE_DISK_MARGIN:
        raise RenderError(
            f"not enough free disk: {need * FREE_DISK_MARGIN / 2**30:.1f} GiB needed, {free / 2**30:.1f} GiB free"
        )


def _plan_digest(recipe: Recipe, poses: list[Pose]) -> str:
    payload = json.dumps([list(map(repr, p.__dict__.values())) for p in poses] + [recipe.data["camera"]["resolution"]])
    return hashlib.sha256(payload.encode()).hexdigest()


def _pose_key(pose: Pose) -> tuple[Any, ...]:
    return (pose.eye, pose.target, pose.up, pose.focal_length_mm, pose.sun_azimuth_deg, pose.sun_elevation_deg)


def _load_state(out: Path, resume: bool, recipe: Recipe, scene: Scene, plan_sha: str, now: str) -> dict[str, Any]:
    path = out / STATE_FILE
    if resume and path.is_file():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state["recipe_sha256"] != recipe.sha256:
            raise RenderResumeError(
                "this output folder was started from a different recipe: use a new folder or --no-resume"
            )
        if state["scene_sha256"] != scene.sha256:
            raise RenderResumeError(
                "the scene changed since this output folder was started: use a new folder or --no-resume"
            )
        if state["plan_sha256"] != plan_sha:
            raise RenderResumeError(
                "the pose plan or resolution differs from the one this output folder was started with"
            )
        return state
    return {
        "recipe_sha256": recipe.sha256,
        "scene_sha256": scene.sha256,
        "plan_sha256": plan_sha,
        "created": now,
        "camera_update": "write",
        "encode": None,
    }


def _render_pose(backend: RenderBackend, pose: Pose, tick: Callable[[], None]) -> np.ndarray:
    backend.apply(pose)
    for _ in range(pose.steps):
        tick()
        backend.step()
    image = backend.grab()
    if float(image.std()) < FLAT_STD:
        raise RenderError(f"{pose.out}: the image is flat (std below {FLAT_STD}): the scene did not render")
    return image


def _local_record(path: Path, started: str, ended: str, gpu_seconds: float, completed: bool) -> None:
    """Append this session to `<output>.local.json` (local-only: it holds timing, which is never published)."""
    doc = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.is_file()
        else {"performance": "local-only", "sessions": []}
    )
    doc["sessions"].append(
        {"started": started, "ended": ended, "gpu_seconds": round(gpu_seconds, 1), "completed": completed}
    )
    doc["gpu_hours"] = round(sum(s["gpu_seconds"] for s in doc["sessions"]) / 3600, 3)
    dump_json(path, doc)


def run(
    recipe: Recipe,
    out_dir: str | Path,
    resume: bool = True,
    *,
    backend: RenderBackend,
    data_root: str | Path,
    tick: Callable[[], None] | None = None,
    encode: Callable[..., EncodeInfo] | None = None,
    disk_free: Callable[[Path], int] = _free_bytes,
    now: Callable[[], str] = utc_now,
    gpu: dict[str, str] | None = None,
    gpu_seconds: Callable[[], float] = lambda: 0.0,
) -> RunResult:
    """Render every missing image, encode the clip, and write the manifest and the digests; return what was done."""
    out = Path(out_dir)
    scene = resolve_scene(recipe, data_root)  # refuses a missing scene before anything is created
    poses = plan(recipe)
    _preflight_disk(recipe, poses, out, disk_free)
    out.mkdir(parents=True, exist_ok=True)
    state = _load_state(out, resume, recipe, scene, _plan_digest(recipe, poses), now())
    dump_json(out / STATE_FILE, state)  # written first, so an interrupted run still pins the recipe, scene and plan
    for leftover in out.rglob("*.part"):
        leftover.unlink()
    todo = [p for p in poses if not (resume and is_complete_png(out / p.out))]
    skipped = len(poses) - len(todo)
    clip = out / recipe.data["output"]["clip"]
    notes = [SUN_NOTE]
    if todo:
        for stale in (MANIFEST_FILE, DIGESTS_FILE):
            (out / stale).unlink(missing_ok=True)
        state["encode"] = None
        clip.unlink(missing_ok=True)
        _render_all(
            backend,
            recipe,
            scene,
            todo,
            out,
            state,
            tick or (lambda: None),
            now,
            gpu_seconds,
            out.with_name(out.name + ".local.json"),
        )
    dump_json(out / STATE_FILE, state)
    fps = recipe.data["flyover"]["fps"]
    if state["encode"] is None or not clip.is_file():
        encoder = encode or encode_clip
        info = encoder(out / "flyover", "frame_%05d.png", fps, clip, recipe.data["output"])
        state["encode"] = {
            "name": info.name,
            "fallback": info.fallback,
            "ffmpeg_version": info.ffmpeg_version,
            "args": info.args,
        }
        dump_json(out / STATE_FILE, state)
    if scene.missing_layers:
        notes.append(
            f"layers missing from the composed stage, rendered without them: {', '.join(scene.missing_layers)}"
        )
    if state["camera_update"] == "reload":
        notes.append(
            "camera update mode: reload (write_attribute was unusable or had no effect; layer re-authored per pose)"
        )
    if state["encode"]["fallback"]:
        wanted = recipe.data["output"]["encoder"]["name"]
        notes.append(f"{state['encode']['name']} used because NVENC ({wanted}) is missing in this FFmpeg build")
    if recipe.is_reduced:
        notes.append("reduced render: fewer stills, a short flyover and a small image (the dry-run cut of the recipe)")
    manifest = build_manifest(
        out=out,
        recipe=recipe,
        scene=scene,
        poses=poses,
        producer=state.setdefault("producer", backend.describe()),
        created=state["created"],
        gpu=gpu,
        encoder=state["encode"],
        camera_update=state["camera_update"],
        notes=notes,
    )
    dump_json(out / STATE_FILE, state)
    dump_json(out / MANIFEST_FILE, manifest)
    write_digests(out)
    return RunResult(manifest_path=out / MANIFEST_FILE, manifest=manifest, rendered=len(todo), skipped=skipped)


def _render_all(
    backend: RenderBackend,
    recipe: Recipe,
    scene: Scene,
    todo: list[Pose],
    out: Path,
    state: dict[str, Any],
    tick: Callable[[], None],
    now: Callable[[], str],
    gpu_seconds: Callable[[], float],
    local_path: Path,
) -> None:
    started, completed = now(), False
    backend.open(scene.root.as_posix(), recipe)
    state["producer"] = backend.describe()
    try:
        previous: tuple[tuple[Any, ...], str] | None = None
        for pose in todo:
            image = _render_pose(backend, pose, tick)
            digest = hashlib.sha256(image.tobytes()).hexdigest()
            if previous and _pose_key(pose) != previous[0] and digest == previous[1]:
                if backend.mode != "write":
                    raise RenderError(NO_EFFECT.format(pose.out))
                backend.set_mode("reload")  # the attribute writes are ignored: re-author the layer per pose
                image = _render_pose(backend, pose, tick)
                digest = hashlib.sha256(image.tobytes()).hexdigest()
                if digest == previous[1]:
                    raise RenderError(NO_EFFECT.format(pose.out))
            previous = (_pose_key(pose), digest)
            write_png(out / pose.out, image)
        completed = True
    finally:
        state["camera_update"] = backend.mode
        dump_json(out / STATE_FILE, state)
        backend.close()
        _local_record(local_path, started, now(), gpu_seconds(), completed)


def _ovrtx_version() -> str | None:
    try:
        return metadata.version("ovrtx")
    except metadata.PackageNotFoundError:
        return None


def dry_run(
    recipe: Recipe,
    data_root: str | Path,
    out_dir: str | Path,
    *,
    run: Callable[..., Any],
    ffmpeg: str | None = None,
    disk_free: Callable[[Path], int] = _free_bytes,
    ovrtx_version: Callable[[], str | None] = _ovrtx_version,
) -> DryRunReport:
    """Check every prerequisite of the full render and plan the reduced one, without starting the renderer or the GPU.

    ovrtx has no CPU render path, and the GPU is reserved for the queue job, so the renderer is not started: the dry run
    plans two stills and three flyover frames at 320 x 180, asserts that a CUDA device is visible and that ovrtx is
    installed and may be imported in this process, builds the session layer of the first pose, finds an H.264 encoder
    and checks the disk. Nothing is written to the output folder.
    """
    scene = resolve_scene(recipe, data_root)
    reduced = recipe.reduced(resolution=DRY_RESOLUTION, stills=DRY_STILLS, flyover_frames=DRY_FRAMES)
    small, full = plan(reduced), plan(recipe)
    version = ovrtx_version()
    if version is None:
        raise RenderError("ovrtx is not installed in this environment: run `uv sync --project studio/rtx`")
    check_runtime_isolation("ovrtx")
    device = assert_cuda_visible(run)
    layer = session_layer(scene.root.as_posix(), reduced, small[0])
    if f"@{scene.root.as_posix()}@" not in layer:
        raise RenderError("the session layer does not sublayer the scene root")
    encoder, fell_back = pick_encoder(ffmpeg or find_ffmpeg(), recipe.data["output"]["encoder"]["name"], run)
    _preflight_disk(recipe, full, Path(out_dir), disk_free)
    w, h = DRY_RESOLUTION
    missing = ", ".join(scene.missing_layers) or "none"
    gib = estimate_bytes(recipe, full) / 2**30
    fw, fh = recipe.data["camera"]["resolution"]
    n_still, n_fly = len([p for p in full if p.kind == "still"]), len([p for p in full if p.kind == "flyover"])
    print(f"scene: {scene.id} ({len(scene.layers)} layer files, digest {scene.sha256[:12]}, missing layers: {missing})")
    print(f"ovrtx {version}, no conflicting runtime loaded")
    print(f"CUDA device: {device.name} (driver {device.driver}, {device.temperature_c} C)")
    print(f"encoder: {encoder}" + (" (fallback: NVENC is missing)" if fell_back else ""))
    print(f"planned frames: {DRY_STILLS} stills + {DRY_FRAMES} flyover frames at {w}x{h}")
    print(f"full run: {n_still} stills + {n_fly} flyover frames at {fw}x{fh}, estimated output {gib:.1f} GiB")
    return DryRunReport(
        reduced_poses={"stills": DRY_STILLS, "flyover": DRY_FRAMES, "resolution": DRY_RESOLUTION},
        full_poses={"stills": n_still, "flyover": n_fly, "resolution": (fw, fh)},
        device=device,
        encoder=encoder,
        scene=scene,
    )
