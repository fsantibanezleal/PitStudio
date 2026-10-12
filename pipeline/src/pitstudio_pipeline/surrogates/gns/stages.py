"""GNS stages as the GPU runner calls them: s30_train, s50_evaluate, s60_export and the speed measurement.

    python -m pitstudio_pipeline.surrogates.gns train    --data <rollouts> --out <dir> [--config cfg.json] [--device
    cuda]
    python -m pitstudio_pipeline.surrogates.gns evaluate --data <rollouts> --run <dir> [--device cuda]
    python -m pitstudio_pipeline.surrogates.gns export   --data <rollouts> --run <dir> [--ort-provider cuda]
    python -m pitstudio_pipeline.surrogates.gns speed    --data <rollouts> --run <dir> [--device cuda]

`<rollouts>` holds `meta/*.json` (DC-011-01 metadata) and the payloads they name, plus (optionally) the generator's
`_state.json`, whose `slots[*].split` assigns each geometry to train, val or test (checked against the rules of
FR-011-03).
A CUDA stage needs the machine lock (`PITSTUDIO_HELD_LOCKS` holds `gpu0.compute`, set by whatever acquired the lock),
honours
the hold file in `GPU_LOCK_DIR`, halves the batch on a CUDA out-of-memory error at most twice and records it in the
manifest
(FR-011-44). GPU hours are recorded in every training manifest (NFR-011-04). Inputs are verified against their recorded
digests before any step (FR-011-51).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch

from pitstudio.granular.observables import observables
from pitstudio.surrogate_budget import attach_gpu_hours
from pitstudio.surrogate_inputs import run_stage
from pitstudio.surrogate_manifests import LABEL
from pitstudio.surrogate_runtime import check_hold, require_gpu_lock, run_with_oom_fallback
from pitstudio_pipeline.surrogates.errors import DatasetError, ExportError
from pitstudio_pipeline.surrogates.fixture import publishable
from pitstudio_pipeline.surrogates.gns import data, evaluate, export, infer, parity, speed, train

ENVELOPE_KEYS = {
    "aspect_ratio": ("column_aspect_ratio", "1"),
    "column_width_m": ("column_width", "m"),
    "pour_height_m": ("pour_height", "m"),
    "pour_rate_m2_per_s": ("pour_rate", "m^2/s"),
    "crest_height_m": ("crest_height", "m"),
    "dump_rate_m2_per_s": ("dump_rate", "m^2/s"),
}
DEFAULT_CONFIG: dict[str, Any] = {
    "noise_scales": [0.0, 0.05, 0.2],
    "epochs": 40,
    "batch_size": 4,
    "lr": 1e-3,
    "lr_final_ratio": 0.1,
    "latent": 128,
    "steps": 10,
    "checkpoint_steps": True,
    "samples_per_epoch": 1500,
    "val_samples": 24,
}


# ------------------------------------------------------------------ dataset view


def geometry_records(meta_dir: Path) -> list[dict[str, Any]]:
    """One {"geometry_id", "family", "params"} per geometry found in the metadata files (first packing seed)."""
    seen: dict[str, dict[str, Any]] = {}
    for path in sorted(meta_dir.glob("*.json")):
        meta = data.read_metadata(path)
        gid = meta.get("geometry_id")
        if isinstance(gid, str) and gid not in seen:
            seen[gid] = {"geometry_id": gid, "family": meta.get("family"), "params": dict(meta.get("geometry", {}))}
    return list(seen.values())


def split_from_state(state_path: Path) -> dict[str, list[str]]:
    """The generator's split: geometry ids by `train` | `val` | `test`."""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    for slot in state["slots"]:
        out[slot["split"]].append(slot["id"])
    return out


def check_split(records: Sequence[Mapping[str, Any]], split: Mapping[str, Sequence[str]]) -> None:
    """The test rules of FR-011-03 on the geometries present: envelope of the training set and distance >= 0.05."""
    by_id = {r["geometry_id"]: r for r in records}
    ranges = data.FAMILY_RANGES

    def vec(r: Mapping[str, Any]) -> np.ndarray:
        return np.array([(r["params"][p] - lo) / (hi - lo) for p, (lo, hi) in ranges[r["family"]].items()])

    train_set = [by_id[i] for i in split["train"] if i in by_id]
    for tid in split["test"]:
        if tid not in by_id:
            continue
        test = by_id[tid]
        same = [vec(r) for r in train_set if r["family"] == test["family"]]
        if not same:
            raise DatasetError(f"test geometry {tid}: no training geometry of its family (envelope)")
        stack = np.array(same)
        if float(np.linalg.norm(stack - vec(test), axis=1).min()) < data.MIN_DISTANCE:
            raise DatasetError(
                f"test geometry {tid} is at a normalised distance below {data.MIN_DISTANCE} from a training geometry"
            )
        if ((vec(test) < stack.min(axis=0) - 1e-12) | (vec(test) > stack.max(axis=0) + 1e-12)).any():
            raise DatasetError(f"test geometry {tid} lies outside the training envelope")


def training_envelope(records: Sequence[Mapping[str, Any]], ids: Sequence[str], d: float) -> dict[str, dict[str, Any]]:
    """The DC-011-02 `training_envelope` over the training geometries (parameter ranges and the particle diameter)."""
    chosen = [r for r in records if r["geometry_id"] in set(ids)]
    out: dict[str, dict[str, Any]] = {}
    for param, (key, unit) in ENVELOPE_KEYS.items():
        values = [r["params"][param] for r in chosen if param in r["params"]]
        if values:
            out[key] = {"min": float(min(values)), "max": float(max(values)), "unit": unit}
    out["particle_diameter"] = {"min": d, "max": d, "unit": "m"}
    return out


class Dataset:
    """A rollout directory with its split, inputs list and fixture flag."""

    def __init__(self, root: Path, *, split: Mapping[str, Sequence[str]] | None = None) -> None:
        self.root = Path(root)
        self.meta_dir = self.root / "meta"
        if not self.meta_dir.is_dir():
            raise DatasetError(f"{self.meta_dir} does not exist")
        self.records = geometry_records(self.meta_dir)
        state = self.root / "_state.json"
        self.split = dict(split) if split else (split_from_state(state) if state.is_file() else {})
        if not self.split:
            raise DatasetError("no split: give one or provide _state.json with slots[*].split")
        check_split(self.records, self.split)
        present = {r["geometry_id"] for r in self.records}
        self.split = {name: [i for i in ids if i in present] for name, ids in self.split.items()}
        self.fixture = any(bool(data.read_metadata(p).get("fixture")) for p in self.meta_dir.glob("*.json"))
        self.manifest: dict[str, Any] = {"id": "gns-rollouts", "fixture": self.fixture}

    def paths_of(self, geometry_id: str) -> list[Path]:
        """The metadata files of a geometry, in file-name order."""
        return [
            p for p in sorted(self.meta_dir.glob("*.json")) if data.read_metadata(p).get("geometry_id") == geometry_id
        ]

    def inputs(self, names: Sequence[str]) -> list[dict[str, str]]:
        ids = {i for n in names for i in self.split[n]}
        out = []
        for path in sorted(self.meta_dir.glob("*.json")):
            meta = data.read_metadata(path)
            if meta.get("geometry_id") in ids:
                out.append(
                    {
                        "id": f"{meta['geometry_id']}-s{meta['packing_seed']}",
                        "path": meta["store"]["path"],
                        "sha256": meta["store"]["sha256"],
                    }
                )
        return out

    def splits(self, cache_size: int = 300) -> data.DirectorySplits:
        return data.DirectorySplits(self.meta_dir, root=self.root, split=self.split, cache_size=cache_size)


# ------------------------------------------------------------------ guards and helpers


def _gpu_guard(device: str, env: Mapping[str, str]) -> None:
    require_gpu_lock(device, env=env)
    if device != "cpu":
        lock_dir = env.get("GPU_LOCK_DIR")
        if not lock_dir:
            raise RuntimeError("GPU_LOCK_DIR is not set: a CUDA stage must check the hold file")
        check_hold(device, lock_dir=lock_dir)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_json_default) + "\n", encoding="utf-8")


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def _device_name(device: str) -> str:
    if device.startswith("cuda") and torch.cuda.is_available():
        return torch.cuda.get_device_name(torch.device(device))
    return "cpu"


# ------------------------------------------------------------------ stages


def s30_train(
    dataset: Dataset,
    out: Path,
    config: Mapping[str, Any],
    *,
    seed: int,
    device: str,
    env: Mapping[str, str],
    hooks: train.TrainHooks | None = None,
) -> dict[str, Any]:
    """Train on the training split, select on validation, write checkpoint, log and manifest."""
    _gpu_guard(device, env)
    cfg = {**DEFAULT_CONFIG, **config, "device": device}
    cfg.setdefault("connectivity_radius", None)
    if cfg["connectivity_radius"] is None:
        train_paths = [p for gid in dataset.split["train"] for p in dataset.paths_of(gid)]
        if not train_paths:
            raise DatasetError("the training split is empty")
        cfg["connectivity_radius"] = float(data.read_metadata(train_paths[0])["connectivity_radius_m"])  # metadata only
    manifest: dict[str, Any] = {
        "stage": "s30_train",
        "model": "gns",
        "seed": seed,
        "device": device,
        "hardware": _device_name(device),
        "dataset": dataset.manifest,
        "inputs": dataset.inputs(["train", "val"]),
        "label": LABEL,
        "notes": [f"gns-checkpoint: {LABEL}"],
        "split": dataset.split,
    }
    splits = dataset.splits()
    started = time.perf_counter()

    def work() -> Any:
        def attempt(params: dict[str, Any]) -> Any:
            if device != "cpu":
                torch.cuda.empty_cache()
            first = (
                params["batch_size"] == cfg["batch_size"]
            )  # a resumed position is only valid at the original batch size
            return train.train_gns(
                splits, {**cfg, **params}, seed=seed, dataset_manifest=dataset.manifest, hooks=hooks if first else None
            )

        return run_with_oom_fallback("gns", {"batch_size": cfg["batch_size"]}, attempt, manifest=manifest)

    result = run_stage("s30_train", manifest, root=dataset.root, work=work)
    seconds = time.perf_counter() - started + float(getattr(hooks, "elapsed_before_s", 0.0))
    attach_gpu_hours(manifest, "gns", seconds)
    manifest["wall_s"] = seconds
    manifest["config"] = {k: v for k, v in cfg.items() if k != "device"}
    out.mkdir(parents=True, exist_ok=True)
    torch.save(result.checkpoint, out / "checkpoint.pt")
    _write_json(out / "train_log.json", result.log)
    _write_json(out / "train_manifest.json", manifest)
    return manifest


def _load_checkpoint(run: Path) -> dict[str, Any]:
    return torch.load(run / "checkpoint.pt", map_location="cpu", weights_only=False)


def s50_evaluate(dataset: Dataset, run: Path, *, device: str, env: Mapping[str, str]) -> dict[str, Any]:
    """Roll the trained GNS out on the held-out geometries and write the report (a fixture report is not published)."""
    _gpu_guard(device, env)
    checkpoint = _load_checkpoint(run)
    model = train.load_model(checkpoint).to(device).eval()
    expected = [
        {"geometry_id": r["geometry_id"], "family": r["family"]}
        for r in dataset.records
        if r["geometry_id"] in set(_state_ids(dataset, "test"))
    ]
    manifest = {"inputs": dataset.inputs(["test"])}

    def work() -> dict[str, Any]:
        geometries = data.evaluation_geometries(dataset.meta_dir, root=dataset.root, geometry_ids=dataset.split["test"])
        surrogate = infer.make_surrogate(infer.torch_advance(model))
        return evaluate.evaluate_held_out(geometries, surrogate, expected=expected, dataset_manifest=dataset.manifest)

    report = run_stage("s50_evaluate", manifest, root=dataset.root, work=work)
    report["label"] = LABEL
    _write_json(run / "evaluation.json", report)
    published = publishable(report)
    if published is not None:
        _write_json(run / "evaluation.published.json", published)
    return report


def _state_ids(dataset: Dataset, name: str) -> list[str]:
    state = dataset.root / "_state.json"
    return split_from_state(state)[name] if state.is_file() else dataset.split[name]


def fp16_deltas(dataset: Dataset, paths: Mapping[str, Path], model: Any, *, provider: str) -> list[dict[str, Any]]:
    """Per held-out geometry, the change of the 3-packing mean repose and run-out between the fp16 and fp32 rollouts."""
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if provider == "cuda" else ["CPUExecutionProvider"]
    n_types = model.n_particle_types
    steppers = {
        key: infer.make_surrogate(
            infer.OrtGnsStep(
                paths[key], n_particle_types=n_types, providers=providers, frame_interval=model.frame_interval
            ).advance
        )
        for key in ("fp32", "fp16")
    }
    out = []
    for geometry in data.evaluation_geometries(dataset.meta_dir, root=dataset.root, geometry_ids=dataset.split["test"]):
        means: dict[str, list[tuple[float, float]]] = {"fp32": [], "fp16": []}
        for ref in geometry["references"][: evaluate.N_PACKINGS]:
            frames = np.asarray(ref["positions"])
            state = {
                "geometry_id": geometry["geometry_id"],
                "seed": ref["seed"],
                "positions": frames[0],
                "velocities": np.zeros((frames.shape[1], 5, 2), dtype=np.float32),
                "particle_type": np.asarray(ref["particle_types"]),
                "bounds": np.asarray(geometry["bounds"], dtype=np.float32),
                "d": geometry["d"],
                "dt": geometry["dt"],
            }
            for key, surrogate in steppers.items():
                rollout = surrogate(state, frames.shape[0] - 1)
                try:
                    o = observables(
                        rollout.positions[-1], d=geometry["d"], family=geometry["family"], geometry=geometry["geometry"]
                    )
                    value = (o["repose_deg"], o["run_out_m"]) if rollout.status == "ok" else (math.nan, math.nan)
                except ValueError:
                    value = (math.nan, math.nan)  # no observable: the change is unknown, so fp32 stays live
                means[key].append(value)
        a, b = np.mean(means["fp32"], axis=0), np.mean(means["fp16"], axis=0)
        out.append(
            {
                "geometry_id": geometry["geometry_id"],
                "delta_repose_deg": float(abs(b[0] - a[0])),
                "delta_runout_rel": float(abs(b[1] - a[1]) / abs(a[1])),
            }
        )
    return out


def s60_export(dataset: Dataset, run: Path, *, ort_provider: str, model_id: str = "gns-a3") -> dict[str, Any]:
    """Export the checkpoint to ONNX (fp32, fp16, bench), check parity, decide the live precision and write the card."""
    checkpoint = _load_checkpoint(run)
    model = train.load_model(checkpoint)
    first = next(iter(dataset.splits().rollouts("train")))
    d = float(first["d"])
    result = export.export_gns(
        model,
        run / "models",
        model_id=model_id,
        particle_diameter_m=d,
        envelope=training_envelope(dataset.records, dataset.split["train"], d),
        normalisation=checkpoint["stats"],
        categories=("grain",)
        if model.n_particle_types == 1
        else tuple(f"type-{i}" for i in range(model.n_particle_types)),
    )
    report = parity.check_parity(model, result.paths["fp32"])
    if not report.passed:
        raise ExportError(f"ONNX Runtime CPU fp32 does not match PyTorch fp32 (max abs {report.max_abs})")
    deltas = fp16_deltas(dataset, result.paths, model, provider=ort_provider)
    live = parity.choose_live_precision(deltas)
    card = {
        "model_id": model_id,
        "label": LABEL,
        "fixture": bool(checkpoint.get("fixture", False)),
        "live_precision": live,
        "parity": {
            "passed": report.passed,
            "n_golden": report.n_golden,
            "max_abs": report.max_abs,
            "max_rel": report.max_rel,
            "tolerances": report.tolerances,
        },
        "fp16_rollout_deltas": deltas,
        "files": {key: {"path": str(path.name), "bytes": path.stat().st_size} for key, path in result.paths.items()},
        "descriptions": {key: f"{model_id}-{key}.io.json" for key in result.paths},
    }
    _write_json(run / "export_card.json", card)
    return card


def s_speed(dataset: Dataset, run: Path, *, device: str, env: Mapping[str, str], n_steps: int = 100) -> dict[str, Any]:
    """Time `n_steps` single steps of the first held-out geometry on the CPU and on `device` (FR-011-16)."""
    _gpu_guard(device, env)
    checkpoint = _load_checkpoint(run)
    model = train.load_model(checkpoint)
    geometry = data.evaluation_geometries(dataset.meta_dir, root=dataset.root, geometry_ids=dataset.split["test"][:1])[
        0
    ]
    pos = np.asarray(geometry["references"][0]["positions"][-1], dtype=np.float32)
    n = pos.shape[0]
    arrays = {
        "vel": np.zeros((n, 5, 2), dtype=np.float32),
        "types": np.asarray(geometry["references"][0]["particle_types"]),
        "bounds": np.asarray(geometry["bounds"], dtype=np.float32),
    }

    def time_device(name: str) -> list[float]:
        model_d = model.to(name).eval()
        step = infer.torch_advance(model_d)
        from pitstudio.granular.graph import build_radius_graph

        graph = build_radius_graph(pos, model.connectivity_radius)
        times = []
        for _ in range(n_steps + 3):
            start = time.perf_counter()
            step(pos, arrays["vel"], arrays["types"], arrays["bounds"], graph.neighbour_index, graph.neighbour_mask)
            if name.startswith("cuda"):
                torch.cuda.synchronize()
            times.append(time.perf_counter() - start)
        return times[3:]

    state_path = dataset.root / "_state.json"
    wall = 1.0
    if state_path.is_file():
        slots = json.loads(state_path.read_text(encoding="utf-8"))["slots"]
        seeds = [s for slot in slots for s in slot.get("seeds", [])]
        if seeds:
            wall = float(np.median([s["wall_s"] / max(1, s["frames"] * 420) for s in seeds]))  # s per solver step
    gpu_entry: dict[str, Any] = {"reason": "no CUDA device was requested"}
    if device != "cpu":
        gpu_entry = {"hardware": _device_name(device), "step_times_s": time_device(device)}
    report = speed.build_speed_report(
        geometry_id=geometry["geometry_id"],
        particles=n,
        python_cpu={"hardware": "CPU", "step_times_s": time_device("cpu")},
        python_gpu=gpu_entry,
        browser={
            "T1": {
                "hardware": "not measured here",
                "browser": "n/a",
                "reason": "measured by the web lane suite (spec 018)",
            },
            "T2": {
                "hardware": "not measured here",
                "browser": "n/a",
                "reason": "measured by the web lane suite (spec 018)",
            },
        },
        solver={"hardware": "solver run recorded in _state.json", "wall_s_per_step": wall},
    )
    _write_json(run / "speed.json", report)
    return report


# ------------------------------------------------------------------ command line


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pitstudio_pipeline.surrogates.gns", description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    for name in ("train", "evaluate", "export", "speed"):
        p = sub.add_parser(name)
        p.add_argument("--data", required=True, type=Path, help="rollout directory (meta/, payload/, _state.json)")
        p.add_argument("--device", default="cpu", help="cpu, cuda or cuda:N")
        if name == "train":
            p.add_argument("--out", required=True, type=Path)
            p.add_argument("--config", type=Path, help="JSON file overriding the defaults")
            p.add_argument("--seed", type=int, default=0)
        else:
            p.add_argument("--run", required=True, type=Path, help="the --out directory of the train stage")
        if name == "export":
            p.add_argument("--ort-provider", default="cpu", choices=["cpu", "cuda"])
    args = parser.parse_args(argv)
    dataset = Dataset(args.data)
    env = os.environ
    if args.stage == "train":
        config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
        s30_train(dataset, args.out, config, seed=args.seed, device=args.device, env=env)
    elif args.stage == "evaluate":
        report = s50_evaluate(dataset, args.run, device=args.device, env=env)
        print(json.dumps({k: report[k] for k in ("status", "n_geometries", "sc_011_01")}))
    elif args.stage == "export":
        card = s60_export(dataset, args.run, ort_provider=args.ort_provider)
        print(json.dumps({"live_precision": card["live_precision"], "parity": card["parity"]["passed"]}))
    else:
        s_speed(dataset, args.run, device=args.device, env=env)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
