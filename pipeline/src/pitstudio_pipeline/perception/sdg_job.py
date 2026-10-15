"""Pipeline-side steps of the `st55_sdg` queue job: the seed-grouped splits before rendering, the index check after it.

`python -m pitstudio_pipeline.perception.sdg_job splits --plan P --out O`
    reads the scenarios (seed, layout id) of the structured pit arm from the studio sampler's plan and writes the
    train / validation / test seeds (`splits.assign_splits`: whole layouts per split, 80 / 10 / 10 %).
`python -m pitstudio_pipeline.perception.sdg_job verify --root R [--plan P | --requested arm=N ...]`
    reads `R/index.jsonl` through the dataset loader, checks every frame file (`loader.filter_frames`: schema, files,
    SHA-256, mask sizes, class values), the arm volume (NFR-009-05) and the seed / layout leaks between splits
    (`splits.check_leaks`; the perceptual-hash leaks are counted and reported). Exit 0 only when no record is rejected,
    every arm has at least 95 % of its requested images and no seed or layout is shared between splits.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pitstudio_pipeline.perception import loader, splits


def cmd_splits(args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    scenarios = [(int(s["seed"]), str(s["layout_id"])) for s in plan["scenarios"]]
    assignment = splits.assign_splits(scenarios, rng_seed=int(plan["recipe_seed"]))
    doc = {"train": list(assignment.train), "validation": list(assignment.validation), "test": list(assignment.test)}
    Path(args.out).write_text(json.dumps(doc), encoding="utf-8")
    print(f"[splits] train {len(doc['train'])}, validation {len(doc['validation'])}, test {len(doc['test'])}")
    return 0


def verify(root: Path, requested: dict[str, int], *, phash: bool = True) -> dict[str, Any]:
    """The checks of the `verify` command; returns the report (`ok` is the exit decision)."""
    result = loader.read_index(root / "index.jsonl")
    kept = loader.filter_frames(list(result.records), root)
    by_arm: dict[str, int] = {}
    for record in kept.accepted:
        by_arm[record["arm"]] = by_arm.get(record["arm"], 0) + 1
    volume = {arm: splits.arm_volume_ok(n, min(by_arm.get(arm, 0), n)) for arm, n in requested.items()}
    leaks: list[tuple[str, str, str]] = []
    try:
        splits.check_leaks(list(kept.accepted))
    except splits.SplitError as exc:
        leaks.extend(exc.pairs)
    phash_pairs = 0
    if phash:
        try:
            splits.check_leaks(list(kept.accepted), root=root)
        except splits.SplitError as exc:
            phash_pairs = sum(1 for p in exc.pairs if p[2] == "phash")
    report = {
        "records": len(result.records),
        "index_rejected": len(result.rejected),
        "frames_rejected": len(kept.rejected),
        "accepted_by_arm": by_arm,
        "volume_ok": volume,
        "seed_or_layout_leaks": len(leaks),
        "phash_leak_pairs": phash_pairs,
    }
    report["ok"] = (
        not result.rejected and not kept.rejected and all(volume.values()) and not leaks and sum(by_arm.values()) > 0
    )
    return report


def cmd_verify(args: argparse.Namespace) -> int:
    requested: dict[str, int] = {}
    if args.plan:
        requested.update({arm: int(n) for arm, n in json.loads(Path(args.plan).read_text("utf-8"))["counts"].items()})
    for item in args.requested:
        arm, _, count = item.partition("=")
        requested[arm] = int(count)
    report = verify(Path(args.root), requested, phash=not args.no_phash)
    print("[verify] " + json.dumps(report, sort_keys=True))
    return 0 if report["ok"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("splits")
    p.add_argument("--plan", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_splits)
    p = sub.add_parser("verify")
    p.add_argument("--root", required=True)
    p.add_argument("--plan", help="the plan file of the table step: its `counts` are the requested images per arm")
    p.add_argument("--requested", nargs="*", default=[], help="arm=count, e.g. structured=10000")
    p.add_argument("--no-phash", action="store_true")
    p.set_defaults(fn=cmd_verify)
    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
