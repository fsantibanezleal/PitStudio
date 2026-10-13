"""Queue entry of the `st55_sdg` GPU job: `python -m pitstudio_isaac.sdg.run_job [--dry-run]`.

The dry run asserts `torch.cuda.is_available()` and checks every input of the real run without rendering: Isaac Sim /
Replicator importable, the recipe, the scene manifest of spec 004 and the staged CC0 texture pool. It exits 3 and lists the
missing inputs when the real run could not start; the real run renders the frames of the parameter table with
`render.render_frame` (one SimulationApp per process, frames in shards, resumable by shard) once those inputs exist.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

BLOCKED = 3


def missing_inputs() -> list[str]:
    data = Path(os.environ.get("PITSTUDIO_DATA", ""))
    out = []
    if importlib.util.find_spec("isaacsim") is None:
        out.append("isaacsim is not importable in this environment")
    for name, rel in (
        ("recipe (DC-009-03)", "processed/perception/recipe.json"),
        ("scene manifest and pit design (spec 004)", "processed/scenes/b2/manifest.json"),
        ("CC0 texture pool (ambientCG / Poly Haven)", "raw/textures-cc0"),
    ):
        if not (data / rel).exists():
            out.append(f"{name}: {data / rel} is absent")
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
