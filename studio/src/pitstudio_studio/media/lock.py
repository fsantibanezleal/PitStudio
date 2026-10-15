"""Recipe check for the NVENC lock (FR-006-07).

Every recipe stage `st56_encode` declares `resources.gpu: nvenc` (never `exclusive`), so that the runner holds the
`gpu0.nvenc` lock for it. The held-lock check of the running stage is `pitstudio_stagekit.require_lock("nvenc",
0)` (FR-006-22), called first by `media.encode.run`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ENCODE_STAGE = "st56_encode"


def check_encode_stage(stage: dict) -> None:
    """Raise ValueError naming the stage when an `st56_encode` stage does not declare `resources.gpu: nvenc`."""
    if stage.get("id") != ENCODE_STAGE:
        return
    resources = stage.get("resources")
    gpu = resources.get("gpu") if isinstance(resources, dict) else None
    if gpu != "nvenc":
        raise ValueError(f"stage {ENCODE_STAGE} must declare resources.gpu: nvenc, found {gpu!r}")


def check_recipes(folder: Path) -> list[str]:
    """One problem string per encode stage of any `*.yaml` under `folder` that fails `check_encode_stage`."""
    problems: list[str] = []
    root = Path(folder)
    if not root.is_dir():
        return problems
    for path in sorted(root.rglob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("stages"), list):
            continue
        for stage in doc["stages"]:
            if not isinstance(stage, dict):
                continue
            try:
                check_encode_stage(stage)
            except ValueError as e:
                problems.append(f"recipe {doc.get('id', path.name)}: {e}")
    return problems
