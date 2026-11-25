# SPDX-License-Identifier: Apache-2.0
"""The run manifest of a render and its digest file.

The manifest is the publishable record of a render: what produced it, from which scene and recipe, and the digest of
every image and of the clip. It carries no performance number (NVIDIA SLA 8.9: ovrtx timings stay local): no wall
time, no GPU-hours, no frame time, no end time. Those live in `<output>.local.json`, outside the output folder.
Field names follow the run and artefact records of spec 001 (`run_id`, `recipe`, `artefacts` with `id`, `path`,
`bytes`, `sha256`, `kind`, `media_type`, `producer`, the video `encoder` record); the importer fills the publication
fields (`licence_class`, `asset_host`, `budget_class`) when it publishes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pitstudio_rtx.render.plan import Pose
from pitstudio_rtx.render.recipe import Recipe, Scene

SCHEMA_VERSION = "1.0"
STATE_FILE = ".render-state.json"
DIGESTS_FILE = "digests.sha256"
MANIFEST_FILE = "manifest.json"
STAGE_ID = "rtx_render"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump_json(path: Path, doc: Any) -> None:
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")


def run_id(created: str, recipe: Recipe) -> str:
    """`YYYYMMDDTHHMMSSZ-<recipe id>` from the UTC start stamp of the first session."""
    stamp = created.replace("-", "").replace(":", "")
    return f"{stamp}-{recipe.data['id']}"


def _artefact(out: Path, pose: Pose, recipe: Recipe, producer: dict[str, str]) -> dict[str, Any]:
    file = out / pose.out
    still = next((s for s in recipe.data["stills"] if s["id"] == pose.id), {}) if pose.kind == "still" else {}
    record: dict[str, Any] = {
        "id": f"still-{pose.id}" if pose.kind == "still" else f"frame-{pose.index:05d}",
        "path": pose.out,
        "bytes": file.stat().st_size,
        "sha256": sha256_file(file),
        "kind": "image",
        "media_type": "image/png",
        "producer": {"tool": producer["tool"], "stage": {"id": STAGE_ID}},
    }
    if still.get("description"):
        record["description"] = still["description"]
    return record


def build_manifest(
    *,
    out: Path,
    recipe: Recipe,
    scene: Scene,
    poses: list[Pose],
    producer: dict[str, str],
    created: str,
    gpu: dict[str, str] | None,
    encoder: dict[str, Any],
    camera_update: str,
    notes: list[str],
) -> dict[str, Any]:
    """Assemble the manifest from the files on disk (every digest is read back, none is carried over)."""
    data = recipe.data
    clip_name = data["output"]["clip"]
    flyover = [p for p in poses if p.kind == "flyover"]
    fps = data["flyover"]["fps"]
    width, height = data["camera"]["resolution"]
    artefacts = [_artefact(out, p, recipe, producer) for p in poses]
    clip_file = out / clip_name
    duration = len(flyover) / fps
    frames_digest = hashlib.sha256(
        "".join(a["sha256"] for a in artefacts if a["id"].startswith("frame-")).encode()
    ).hexdigest()
    artefacts.append(
        {
            "id": "flyover-clip",
            "path": clip_name,
            "bytes": clip_file.stat().st_size,
            "sha256": sha256_file(clip_file),
            "kind": "video",
            "media_type": "video/mp4",
            "producer": {"tool": producer["tool"], "stage": {"id": STAGE_ID}},
            "encoder": {
                "codec": data["output"]["encoder"]["codec"],
                "pix_fmt": data["output"]["encoder"]["pix_fmt"],
                "width": width,
                "height": height,
                "fps": fps,
                "frames": len(flyover),
                "duration_s": duration,
                "bitrate_kbps": round(clip_file.stat().st_size * 8 / duration / 1000, 1),
                "source_frames_sha256": frames_digest,
                "encoder": {
                    "name": encoder["name"],
                    "ffmpeg_version": encoder["ffmpeg_version"],
                    "args": encoder["args"],
                },
            },
        }
    )
    return {
        "kind": "render",
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id(created, recipe),
        "label": data["label"],
        "producer": producer,
        "recipe": {"id": data["id"], "path": recipe.path, "sha256": recipe.sha256},
        "scene": {
            "id": scene.id,
            "sha256": scene.sha256,
            "manifest_id": scene.manifest_id,
            "layers": [{"path": p, "sha256": d} for p, d in scene.layers],
        },
        "seed": data["seed"],
        "created": created,
        "reduced": recipe.is_reduced,
        "resolution": [width, height],
        "frames": {
            "stills": len([p for p in poses if p.kind == "still"]),
            "flyover": len(flyover),
            "playback_fps": fps,
            "duration_s": duration,
        },
        "missing_layers": list(scene.missing_layers),
        "gpu": gpu,
        "encoder": {
            "name": encoder["name"],
            "fallback": encoder["fallback"],
            "ffmpeg_version": encoder["ffmpeg_version"],
        },
        "camera_update": camera_update,
        "performance": "local-only",
        "artefacts": artefacts,
        "notes": notes,
    }


def write_digests(out: Path) -> None:
    """`digests.sha256` (`<sha256>  <path>`, sorted) over every file but itself, the state and `.part` files."""
    skip = {DIGESTS_FILE, STATE_FILE}
    rows = sorted(
        (p.relative_to(out).as_posix(), sha256_file(p))
        for p in out.rglob("*")
        if p.is_file() and p.name not in skip and p.suffix != ".part"
    )
    (out / DIGESTS_FILE).write_text(
        "".join(f"{digest}  {name}\n" for name, digest in rows), encoding="utf-8", newline="\n"
    )
