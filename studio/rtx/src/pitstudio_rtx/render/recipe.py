# SPDX-License-Identifier: Apache-2.0
"""Render recipe: load, validate, reduce for the dry run, and resolve the USD scene it names.

The recipe is a YAML file under `studio/recipes/render/`; it names the scene by id and stage (never by path) and the
scene is found under `<data root>/processed/scene/<id>/<stage>/`. A scene that is not there is refused, and a layer role
the camera needs that the scene lacks is listed (never invented): the render goes ahead without it.
"""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
MIN_STILLS = 6
MIN_CONTROL_POINTS = 4


class RenderRecipeError(ValueError):
    """The recipe or the scene it names is unusable."""


@dataclass(frozen=True)
class Recipe:
    """A validated recipe: its parsed content, the SHA-256 of the file bytes and its path under `studio/recipes/`."""

    data: dict[str, Any]
    sha256: str
    path: str

    @property
    def is_reduced(self) -> bool:
        return bool(self.data.get("reduced"))

    def reduced(self, *, resolution: tuple[int, int], stills: int, flyover_frames: int) -> Recipe:
        """The same recipe cut down for the dry run or a test: fewer stills, a short flyover, a small image.

        The digest stays the one of the file so a reduced run is traceable to the recipe it was cut from.
        """
        data = copy.deepcopy(self.data)
        data["camera"]["resolution"] = [int(resolution[0]), int(resolution[1])]
        data["stills"] = data["stills"][:stills]
        data["flyover"]["frame_override"] = int(flyover_frames)
        data["reduced"] = True
        return Recipe(data=data, sha256=self.sha256, path=self.path)


@dataclass(frozen=True)
class Scene:
    """A resolved scene: the root layer, the digest of its layers and the layer roles that are missing."""

    id: str
    root: Path
    sha256: str
    manifest_id: str | None
    layers: tuple[tuple[str, str], ...]
    missing_layers: tuple[str, ...]


def _fail(pointer: str, message: str) -> RenderRecipeError:
    return RenderRecipeError(f"{pointer}: {message}")


def _vec3(value: Any, pointer: str) -> None:
    if not (isinstance(value, list) and len(value) == 3 and all(isinstance(v, (int, float)) for v in value)):
        raise _fail(pointer, "must be a list of three numbers (eye, target and up are x, y, z in metres)")


def _positive(value: Any, pointer: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise _fail(pointer, "must be a positive number")


def _validate(data: Any) -> None:
    if not isinstance(data, dict):
        raise RenderRecipeError("/: the recipe must be a mapping")
    for key in ("id", "scene", "camera", "sun", "sky", "steps", "stills", "flyover", "output", "label"):
        if key not in data:
            raise _fail(f"/{key}", "is required")
    if not SLUG.fullmatch(str(data["id"])):
        raise _fail("/id", "must be a slug")
    scene = data["scene"]
    for key in ("id", "stage", "root", "required_layers"):
        if key not in scene:
            raise _fail(f"/scene/{key}", "is required")
    camera = data["camera"]
    res = camera.get("resolution")
    if not (isinstance(res, list) and len(res) == 2 and all(isinstance(v, int) and 16 <= v <= 8192 for v in res)):
        raise _fail("/camera/resolution", "must be [width, height] integers between 16 and 8192")
    for key in ("focal_length_mm", "horizontal_aperture_mm"):
        _positive(camera.get(key), f"/camera/{key}")
    stills = data["stills"]
    if not isinstance(stills, list) or len(stills) < MIN_STILLS:
        raise _fail("/stills", f"needs at least {MIN_STILLS} stills")
    seen: set[str] = set()
    for i, still in enumerate(stills):
        sid = str(still.get("id", ""))
        if not SLUG.fullmatch(sid):
            raise _fail(f"/stills/{i}/id", f"still id {sid!r} must be a slug")
        if sid in seen:
            raise _fail(f"/stills/{i}/id", f"duplicate still id {sid!r}")
        seen.add(sid)
        _vec3(still.get("eye"), f"/stills/{i}/eye")
        _vec3(still.get("target"), f"/stills/{i}/target")
        if "up" in still:
            _vec3(still["up"], f"/stills/{i}/up")
    fly = data["flyover"]
    _positive(fly.get("duration_s"), "/flyover/duration_s")
    fps = fly.get("fps")
    if not (isinstance(fps, int) and 1 <= fps <= 240):
        raise _fail("/flyover/fps", "must be an integer between 1 and 240")
    points = fly.get("control_points")
    if not isinstance(points, list) or len(points) < MIN_CONTROL_POINTS:
        raise _fail("/flyover/control_points", f"needs at least {MIN_CONTROL_POINTS} control points")
    for i, point in enumerate(points):
        _vec3(point.get("eye"), f"/flyover/control_points/{i}/eye")
        _vec3(point.get("target"), f"/flyover/control_points/{i}/target")
    _positive(data["output"].get("disk_limit_gib"), "/output/disk_limit_gib")
    for key in ("warmup", "still", "frame"):
        if not (isinstance(data["steps"].get(key), int) and data["steps"][key] >= 1):
            raise _fail(f"/steps/{key}", "must be an integer of at least 1")


def load_recipe(path: str | Path) -> Recipe:
    """Read and validate a render recipe; the digest is the SHA-256 of the file bytes."""
    path = Path(path)
    raw = path.read_bytes()
    data = yaml.safe_load(raw.decode("utf-8"))
    _validate(data)
    parts = path.resolve().parts
    rel = "/".join(parts[parts.index("recipes") + 1 :]) if "recipes" in parts else path.name
    return Recipe(data=data, sha256=hashlib.sha256(raw).hexdigest(), path=rel)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _layer_file(scene_dir: Path, role: str) -> Path | None:
    """The file of a layer role: `layers/<role>.usd[a|c]`, or `assets/materials.usda` for the materials."""
    if role == "materials":
        candidate = scene_dir / "assets" / "materials.usda"
        return candidate if candidate.is_file() else None
    for suffix in ("usda", "usdc", "usd"):
        candidate = scene_dir / "layers" / f"{role}.{suffix}"
        if candidate.is_file():
            return candidate
    return None


def resolve_scene(recipe: Recipe, data_root: str | Path) -> Scene:
    """Locate the scene under the data root, digest its layers and list the required roles that are missing."""
    spec = recipe.data["scene"]
    scene_dir = Path(data_root) / "processed" / "scene" / spec["id"] / spec["stage"] / "scene"
    root = scene_dir.parent / spec["root"]
    if not root.is_file():
        raise RenderRecipeError(
            f"scene root not found: {spec['id']}/{spec['stage']}/{spec['root']} under the data root"
        )
    files = {"root.usda": root}
    for role in ("layers", "assets"):
        folder = root.parent / role
        if folder.is_dir():
            files.update(
                {
                    f"{role}/{p.name}": p
                    for p in sorted(folder.iterdir())
                    if p.is_file() and p.suffix in {".usda", ".usdc", ".usd"}
                }
            )
    layers = tuple((name, _sha256_file(p)) for name, p in sorted(files.items()))
    combined = hashlib.sha256("\n".join(f"{n}:{d}" for n, d in layers).encode()).hexdigest()
    missing = tuple(sorted(r for r in spec["required_layers"] if _layer_file(root.parent, r) is None))
    found = re.search(r'string manifest_id = "([^"]+)"', root.read_text(encoding="utf-8", errors="replace")[:4096])
    return Scene(
        id=spec["id"],
        root=root,
        sha256=combined,
        manifest_id=found.group(1) if found else None,
        layers=layers,
        missing_layers=missing,
    )
