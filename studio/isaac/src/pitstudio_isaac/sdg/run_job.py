"""Queue entry of the `st55_sdg` GPU job (render step): `python -m pitstudio_isaac.sdg.run_job [--dry-run ...]`.

It asserts `torch.cuda.is_available()`, checks every input of the real run (Isaac Sim importable, the recipe, the
validated scene of spec 004, the staged CC0 texture pool; exit 3 lists what is missing) and renders the rows of the
parameter table (`pitstudio_studio.sdg.table`) with `driver.run`: one Isaac Sim application per GPU block, frames
resumable one by one, under the machine lock and the guard. With `--dry-run` the same driver renders a tiny table
into a scratch root with the CPU renderer (the job script runs the whole chain around it), so the driver path is
exercised without the GPU and without writing the real dataset.
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


def _real_textures(data: Path) -> dict[str, Path]:
    from pitstudio_isaac.sdg.scene_render import texture_files

    pool = data / "raw" / "textures"
    return texture_files(pool, _read_json(pool / "manifest.json"))  # type: ignore[arg-type]


def resolve_paths(data: Path, *, dry_run: bool, table_dir: str | None, out_root: str | None) -> tuple[Path, Path]:
    """Table folder and dataset root of a run. A dry run needs both given and never uses the real dataset root."""
    real_root = data / "processed" / "perception"
    if dry_run and (not table_dir or not out_root):
        raise ValueError("--dry-run needs --table-dir and --out-root of a scratch folder")
    root = Path(out_root) if out_root else real_root
    if dry_run and root.resolve() == real_root.resolve():
        raise ValueError("a dry run never writes the real dataset root")
    return (Path(table_dir) if table_dir else real_root / "param_table"), root


def main(argv: list[str] | None = None) -> int:
    """`--dry-run` asserts CUDA, checks the inputs and renders the tiny table of `--table-dir` with the CPU renderer."""
    from pitstudio_isaac.sdg import driver

    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--table-dir", help="folder of the parameter table (default: <data>/processed/perception/param_table)"
    )
    ap.add_argument("--out-root", help="dataset root (default: <data>/processed/perception); required with --dry-run")
    ap.add_argument("--limit", type=int, default=None, help="render at most this many new frames")
    args = ap.parse_args(argv)
    import torch

    assert torch.cuda.is_available(), "torch.cuda.is_available() is False: sync with the CUDA torch"
    print("[sdg] CUDA available", flush=True)
    missing = missing_inputs()
    for m in missing:
        print(f"[blocked] {m}")
    if missing:
        return BLOCKED
    data = Path(os.environ["PITSTUDIO_DATA"])
    try:
        table_dir, out_root = resolve_paths(
            data, dry_run=args.dry_run, table_dir=args.table_dir, out_root=args.out_root
        )
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
    rows = driver.read_rows(table_dir)
    if args.dry_run:
        from pitstudio_isaac.sdg.cpu_renderer import CpuRenderer
        from pitstudio_isaac.sdg.scene_render import stage_selfcheck

        scene = (
            data
            / "processed"
            / "scene"
            / os.environ.get("PITSTUDIO_SDG_SCENE", DEFAULT_SCENE)
            / "st45_validate"
            / "scene"
        )
        print(f"[dry-run] stage self-check on the real scene: {stage_selfcheck(scene, _real_textures(data), rows)}")

        result = driver.run(
            rows=rows, root=out_root, renderer_factory=CpuRenderer, session=driver.no_gpu_session, limit=args.limit
        )
        print(f"[dry-run] CPU renderer, driver path done: {result}")
        return 0 if result["remaining"] == 0 else 1
    from pitstudio_isaac.sdg.scene_render import SdgRenderer

    scene_dir = (
        data / "processed" / "scene" / os.environ.get("PITSTUDIO_SDG_SCENE", DEFAULT_SCENE) / "st45_validate" / "scene"
    )
    textures = _real_textures(data)
    session = driver.gpu_session_factory(os.environ["PITSTUDIO_GPU_LOCK"])
    result = driver.run(
        rows=rows,
        root=out_root,
        renderer_factory=lambda: SdgRenderer(scene_dir, textures),
        session=session,
        limit=args.limit,
    )
    print(f"[sdg] rendered {result}")
    return 0 if result["remaining"] == 0 or args.limit is not None else 1


if __name__ == "__main__":
    sys.exit(main())
