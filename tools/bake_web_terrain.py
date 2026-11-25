"""Bake the terrain of a composed scene into validated glTF and 3D Tiles for the web, and write its import spec
(T-016-033).

Usage:
    uv run python tools/bake_web_terrain.py --scene <processed/scene/<id>> --out <processed/web-bake/<id>> [--check-
    determinism]

The scene folder is the output folder of the scene stages (`st45_validate/scene` inside it holds the composed
scene). Two
environments do the work, each in its own process: the studio environment reads OpenUSD
(`pitstudio_studio.scene.web_terrain`), the pipeline environment writes the files and runs the Khronos glTF
Validator and the
3D Tiles Validator (`pitstudio_pipeline.export.web_terrain`). Under `--out`:

    exchange/         arrays and provenance handed from the studio step to the pipeline step
    tiles/            the baked tilesets, tiles, shared texture and `bake-report.json`
    import-spec.json  the `studio import-run` spec (also written to `--spec-out`, by default the runner's imports
    folder)

`--check-determinism` bakes a second time into `<out>-verify` and fails when any file digest differs. Exit code: 0
done, 1 a
guard or validator refused an asset or the two bakes differ, 2 usage or a missing input.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
JOB = "43-web-terrain-bingham"
SLUG = "web-terrain-bingham"
RECIPE = "cases/a1-scene.yaml"
MAX_STAGE_OUTPUTS = 64  # contracts/manifest.schema.json: stage.outputs maxItems
TERRAIN_SOURCES = ("usgs-3dep-bingham", "usda-naip-bingham")
ROCK_SOURCE = "polyhaven-rock-boulder-dry"
PD = {"licence_class": "public-domain", "spdx": "LicenseRef-USGov-PD"}
CC0 = {"licence_class": "open-no-attribution", "spdx": "CC0-1.0"}


class BakeToolError(Exception):
    """A step failed or the report is not publishable; the message says why."""


def artefact_id(path: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", re.sub(r"\.(glb|json|jpg)$", "", path.lower()))
    return ("bingham-" + stem.strip("-").removeprefix("tiles-"))[:96].strip("-")


def build_import_spec(report: dict[str, Any], exchange: dict[str, Any]) -> dict[str, Any]:
    """The `studio import-run` spec (kind bake) of a bake report; every file of the report is one output of stage
    s60_export.

    Raises `BakeToolError` for a report with a validator error, more files than a stage record can hold or a repeated
    id.
    """
    if report["totals"]["validator_errors"]:
        raise BakeToolError("the bake report lists validator errors: nothing is published")
    if len(report["files"]) + 1 > MAX_STAGE_OUTPUTS:
        raise BakeToolError(f"{len(report['files']) + 1} outputs exceed the {MAX_STAGE_OUTPUTS} of a stage record")
    digests = exchange["input_digests"]
    terrain = [{"id": sid, "sha256": digests[sid], "kind": "source"} for sid in TERRAIN_SOURCES]
    rock = [{"id": ROCK_SOURCE, "sha256": digests[ROCK_SOURCE], "kind": "source"}]
    outputs: list[dict[str, Any]] = []
    for f in report["files"]:
        path = f["path"]
        base = {"name": path, "from": path, "budget_class": "tiles-glb", "publish": True, "id": artefact_id(path)}
        if f["role"] == "texture":
            outputs.append({**base, "kind": "image", "media_type": "image/jpeg", "inputs": rock, **CC0})
        elif f["role"] == "tileset":
            outputs.append({**base, "kind": "tiles", "media_type": "application/json", "inputs": terrain, **PD})
        else:
            outputs.append({**base, "kind": "tiles", "media_type": "model/gltf-binary", "inputs": terrain, **PD})
    outputs.append(
        {
            "name": "tiles/bake-report.json",
            "from": "tiles/bake-report.json",
            "id": "bingham-terrain-bake-report",
            "kind": "table",
            "media_type": "application/json",
            "budget_class": "tiles-glb",
            "publish": True,
            "inputs": terrain,
            **PD,
            "required_fields": ["files", "totals", "level_scheme"],
        }
    )
    ids = [o["id"] for o in outputs]
    if len(set(ids)) != len(ids):
        raise BakeToolError("two files map to the same artefact id")
    return {
        "job": JOB,
        "kind": "bake",
        "case": "A1",
        "all_cases": True,
        "recipe": RECIPE,
        "slug": SLUG,
        "seed": 0,
        "label": (
            "Bingham Canyon terrain baked from the OpenUSD scene a1-bingham-v3: USGS 3DEP elevation, USDA NAIP 2018 "
            "colour, CC0 rock normal map; glTF tiles in 3D Tiles 1.1, validators 0 errors"
        ),
        "notes": [
            f"Read with OpenUSD (usd-core {exchange['producer']['version']}), written by "
            f"pitstudio_pipeline.export.web_bake; scene manifest {exchange['scene']['manifest_id']}.",
            "Web LOD-0 is one whole-site tile; the detail tileset adds two levels (scene lod2 and lod1 tiles); "
            "scene lod0 is not baked.",
        ],
        "stages": [{"id": "s60_export", "tool": "openusd", "outputs": outputs}],
    }


def _run(cmd: list[str], env_extra: dict[str, str]) -> None:
    proc = subprocess.run(cmd, cwd=ROOT, env={**os.environ, **env_extra}, check=False)
    if proc.returncode:
        raise BakeToolError(f"step {' '.join(cmd[3:7])} exited {proc.returncode}")


def _bake(scene: Path, exchange: Path, out: Path, web_dir: str | None) -> None:
    env = {"PYTHONUTF8": "1"}
    web = {"PITSTUDIO_WEB_DIR": web_dir} if web_dir else {}
    studio = ["uv", "run", "--no-sync", "--project", "studio", "python", "-m", "pitstudio_studio.scene.web_terrain"]
    _run(
        [*studio, "--scene", str(scene / "st45_validate" / "scene"), "--out", str(exchange)],
        {**env, "PYTHONPATH": str(ROOT / "studio" / "src")},
    )
    pipeline = [
        "uv",
        "run",
        "--no-sync",
        "--project",
        "pipeline",
        "python",
        "-m",
        "pitstudio_pipeline.export.web_terrain",
    ]
    _run(
        [*pipeline, "--exchange", str(exchange), "--out", str(out)],
        {**env, **web, "PYTHONPATH": str(ROOT / "pipeline" / "src")},
    )


def _digests(report: dict[str, Any]) -> dict[str, str]:
    return {f["path"]: f["sha256"] for f in report["files"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--scene", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    default_spec = ROOT / "src" / "pitstudio" / "runner" / "imports" / f"{JOB}.json"
    parser.add_argument("--spec-out", type=Path, default=default_spec)
    parser.add_argument("--web-dir", default=None, help="the web/ folder with the installed validators")
    parser.add_argument("--check-determinism", action="store_true")
    args = parser.parse_args(argv)
    if not (args.scene / "st45_validate" / "scene" / "scene.manifest.json").is_file():
        print(f"bake-web-terrain: {args.scene} holds no st45_validate/scene/scene.manifest.json", file=sys.stderr)
        return 2
    try:
        exchange = args.out / "exchange"
        _bake(args.scene, exchange, args.out, args.web_dir)
        report = json.loads((args.out / "tiles" / "bake-report.json").read_text(encoding="utf-8"))
        if args.check_determinism:
            verify = args.out.with_name(args.out.name + "-verify")
            shutil.rmtree(verify, ignore_errors=True)
            _bake(args.scene, verify / "exchange", verify, args.web_dir)
            second = json.loads((verify / "tiles" / "bake-report.json").read_text(encoding="utf-8"))
            shutil.rmtree(verify, ignore_errors=True)
            first_digests, second_digests = _digests(report), _digests(second)
            if first_digests != second_digests:
                bad = sorted(k for k in first_digests if first_digests[k] != second_digests.get(k))
                raise BakeToolError(
                    f"two bakes differ in {len(bad)} file(s), first {bad[0] if bad else 'a missing one'}"
                )
            print(f"bake-web-terrain: two bakes identical: {len(first_digests)} file digests equal")
        spec = build_import_spec(report, json.loads((exchange / "web-bake-input.json").read_text(encoding="utf-8")))
    except BakeToolError as e:
        print(f"bake-web-terrain: {e}", file=sys.stderr)
        return 1
    text = json.dumps(spec, indent=1) + "\n"
    (args.out / "import-spec.json").write_text(text, encoding="utf-8", newline="\n")
    args.spec_out.write_text(text, encoding="utf-8", newline="\n")
    print(f"bake-web-terrain: {len(spec['stages'][0]['outputs'])} outputs; spec {args.spec_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
