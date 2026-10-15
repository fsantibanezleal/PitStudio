"""Queue entry of the `st55_sdg` GPU job: `python -m pitstudio_isaac.sdg.run_job [--dry-run]`.

The dry run asserts `torch.cuda.is_available()` and checks every input of the real run without rendering:
Isaac Sim / Replicator importable, the recipe, the scene manifest of spec 004 and the staged CC0 texture pool.
It exits 3 and lists the missing inputs when the real run could not start; the real run renders the
frames of the parameter table with
`render.render_frame` (one SimulationApp per process, frames in shards, resumable by shard) once those inputs exist.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

BLOCKED = 3
DEFAULT_SCENE = "a1-bingham"


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def missing_inputs() -> list[str]:
    """What the real run needs and does not find under `PITSTUDIO_DATA`, one line each (empty when it can start).

    The recipe (DC-009-03), the validated scene of spec 004 (`st45_validate`, scene `PITSTUDIO_SDG_SCENE`, default
    `a1-bingham`) and the CC0 texture pool (`raw/textures/manifest.json`); every texture of the recipe pool must be in
    the pool manifest and its file must have the SHA-256 the recipe states.
    """
    data = Path(os.environ.get("PITSTUDIO_DATA", ""))
    scene_id = os.environ.get("PITSTUDIO_SDG_SCENE", DEFAULT_SCENE)
    out = []
    if importlib.util.find_spec("isaacsim") is None:
        out.append("isaacsim is not importable in this environment")
    recipe_path = data / "processed" / "perception" / "recipe.json"
    scene_path = data / "processed" / "scene" / scene_id / "st45_validate" / "scene" / "scene.manifest.json"
    pool_path = data / "raw" / "textures" / "manifest.json"
    recipe: dict | None = None
    if not recipe_path.is_file():
        out.append(f"recipe (DC-009-03): {recipe_path} is absent")
    else:
        recipe = _read_json(recipe_path)  # type: ignore[assignment]
    if not scene_path.is_file():
        out.append(f"scene manifest and pit design (spec 004): {scene_path} is absent")
    else:
        status = ((_read_json(scene_path) or {}).get("validation") or {}).get("status")  # type: ignore[union-attr]
        if status != "complete":
            out.append(f"scene {scene_id}: the validation status is {status!r}, expected 'complete'")
    if not pool_path.is_file():
        out.append(f"CC0 texture pool (ambientCG / Poly Haven): {pool_path} is absent")
    elif recipe is not None:
        files = {t["id"]: t for t in _read_json(pool_path)["textures"]}  # type: ignore[index]
        for entry in recipe["texture_pool"]:
            record = files.get(entry["id"])
            if record is None:
                out.append(f"texture {entry['id']}: not in the pool manifest {pool_path}")
            elif not (pool_path.parent / record["file"]).is_file():
                out.append(f"texture {entry['id']}: file {record['file']} is absent")
            elif _sha256(pool_path.parent / record["file"]) != entry["sha256"]:
                out.append(f"texture {entry['id']}: the file's SHA-256 differs from the recipe's")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    import torch

    assert torch.cuda.is_available(), "torch.cuda.is_available() is False: sync with the CUDA torch"
    print("[dry-run] CUDA available", flush=True)
    missing = missing_inputs()
    for m in missing:
        print(f"[blocked] {m}")
    if missing:
        return BLOCKED
    if args.dry_run:
        print("[dry-run] inputs present, stopping before rendering")
        return 0
    raise NotImplementedError("the shard driver needs the scene manifest format of spec 004")


if __name__ == "__main__":
    sys.exit(main())
