"""GNS export (FR-011-07): opset 17, IR version 10, the padded-layout live graph in fp32 and fp16, the ScatterElements
bench graph.

`export_gns` writes `<model_id>-fp32.onnx`, `<model_id>-fp16.onnx` (Gather + masked ReduceSum, no ScatterElements) and
`<model_id>-scatter-bench.onnx` (ScatterElements(reduction = add), fp32, bench only), each with its DC-011-02
description
(`<name>.io.json` next to it). The standardisation statistics are written into the model in place and into the graph,
so the
PyTorch model and the graphs agree (SC-011-04). The fp16 graph keeps float32 inputs and outputs (Cast nodes at the
boundary).
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import onnx
import torch

from pitstudio_pipeline.surrogates.gns.model import HISTORY, K_MAX, GnsStep

OPSET = 17
IR_VERSION = 10
N_MAX = 5000  # the `gns` web engine's particle cap (spec 018)
LIVE_BYTES_MAX = 25_000_000  # NFR-011-01
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
INPUT_NAMES = ["positions", "velocities", "particle_type", "bounds", "neighbour_index", "neighbour_mask"]
OUTPUT_NAMES = ["acceleration"]
KEYS = ("fp32", "fp16", "scatter-bench")


@dataclass(frozen=True)
class GnsExport:
    model_id: str
    paths: dict[str, Path]
    io: dict[str, dict[str, Any]]


def export_gns(
    model: GnsStep,
    out_dir: str | Path,
    *,
    model_id: str,
    particle_diameter_m: float,
    envelope: Mapping[str, Any],
    normalisation: Mapping[str, Mapping[str, Sequence[float]]],
    cases: Sequence[str] = ("A3",),
    categories: Sequence[str] = ("grain",),
) -> GnsExport:
    """Write the three graphs and their descriptions under `out_dir` and return them; see the module docstring."""
    if not isinstance(model, GnsStep):
        raise TypeError(f"model must be a GnsStep, got {type(model).__name__}")
    if not envelope:
        raise ValueError("envelope must hold at least one parameter range (DC-011-02 training_envelope)")
    if not SLUG.fullmatch(model_id or ""):
        raise ValueError(f"model_id must be a slug of lower-case letters, digits and hyphens, got {model_id!r}")
    if not categories or len(categories) > model.n_particle_types:
        raise ValueError(f"categories must name 1 to {model.n_particle_types} particle types, got {list(categories)}")
    if not particle_diameter_m > 0:
        raise ValueError("particle_diameter_m must be positive")
    model.set_normalisation(
        velocity_mean=normalisation["velocities"]["mean"],
        velocity_std=normalisation["velocities"]["std"],
        acceleration_mean=normalisation["acceleration"]["mean"],
        acceleration_std=normalisation["acceleration"]["std"],
    )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fp32_bytes = _trace(model, aggregation="padded")
    scatter_bytes = _trace(model, aggregation="scatter")
    fp16_bytes = _to_fp16(fp32_bytes)
    files = {"fp32": fp32_bytes, "fp16": fp16_bytes, "scatter-bench": scatter_bytes}

    paths: dict[str, Path] = {}
    docs: dict[str, dict[str, Any]] = {}
    for key in KEYS:
        path = out / f"{model_id}-{key}.onnx"
        path.write_bytes(files[key])
        paths[key] = path
        docs[key] = _description(
            model,
            key=key,
            path=path,
            relative=f"{out.name}/{path.name}",
            model_id=model_id,
            particle_diameter_m=particle_diameter_m,
            envelope=envelope,
            normalisation=normalisation,
            cases=cases,
            categories=categories,
        )
        (out / f"{model_id}-{key}.io.json").write_text(json.dumps(docs[key], indent=2) + "\n", encoding="utf-8")
    return GnsExport(model_id=model_id, paths=paths, io=docs)


def _trace(model: GnsStep, *, aggregation: str) -> bytes:
    """ONNX bytes of the model with the given aggregation (the argument model is not modified)."""
    work = copy.deepcopy(model).cpu().float().eval()
    work.aggregation = aggregation
    n = 7
    example = (
        torch.linspace(0.0, 1.0, n * 2).reshape(n, 2) * work.connectivity_radius * 3.0,
        torch.zeros(n, HISTORY, 2),
        torch.zeros(n, dtype=torch.int64),
        torch.tensor([0.0, 0.0, 1.0, 1.0]),
        torch.arange(n, dtype=torch.int64).unsqueeze(1).expand(n, K_MAX).contiguous(),
        torch.zeros(n, K_MAX, dtype=torch.bool),
    )
    dynamic = {name: {0: "N"} for name in INPUT_NAMES if name != "bounds"}
    dynamic["acceleration"] = {0: "N"}
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        torch.onnx.export(
            work,
            example,
            buffer,
            input_names=INPUT_NAMES,
            output_names=OUTPUT_NAMES,
            dynamic_axes=dynamic,
            opset_version=OPSET,
            dynamo=False,
            do_constant_folding=True,
        )
    proto = onnx.load_from_string(buffer.getvalue())
    proto.ir_version = IR_VERSION
    onnx.checker.check_model(proto)
    return proto.SerializeToString()


def _to_fp16(fp32_bytes: bytes) -> bytes:
    """fp16 weights and arithmetic with float32 graph inputs and outputs (Cast nodes at the boundary)."""
    from onnxruntime.transformers.float16 import convert_float_to_float16

    proto = convert_float_to_float16(onnx.load_from_string(fp32_bytes), keep_io_types=True, disable_shape_infer=False)
    sort_topologically(proto.graph)  # the converter appends the input Cast nodes after their consumers
    proto.ir_version = IR_VERSION
    onnx.checker.check_model(proto)
    return proto.SerializeToString()


def sort_topologically(graph: onnx.GraphProto) -> None:
    """Reorder `graph.node` in place so that every node follows the producers of its inputs (stable)."""
    available = {i.name for i in graph.input} | {i.name for i in graph.initializer}
    pending = list(graph.node)
    ordered: list[onnx.NodeProto] = []
    while pending:
        progressed = False
        still: list[onnx.NodeProto] = []
        for node in pending:
            if all(name == "" or name in available for name in node.input):
                ordered.append(node)
                available.update(node.output)
                progressed = True
            else:
                still.append(node)
        if not progressed:
            raise ValueError("the graph has a cycle or an input that nothing produces")
        pending = still
    del graph.node[:]
    graph.node.extend(ordered)


def _description(
    model: GnsStep,
    *,
    key: str,
    path: Path,
    relative: str,
    model_id: str,
    particle_diameter_m: float,
    envelope: Mapping[str, Any],
    normalisation: Mapping[str, Mapping[str, Sequence[float]]],
    cases: Sequence[str],
    categories: Sequence[str],
) -> dict[str, Any]:
    raw = path.read_bytes()
    bench = key == "scatter-bench"

    def standardise(group: str) -> dict[str, Any]:
        return {
            "rule": "standardise",
            "applied_in_graph": True,
            "mean": [float(v) for v in normalisation[group]["mean"]],
            "std": [float(v) for v in normalisation[group]["std"]],
        }

    doc: dict[str, Any] = {
        "model_id": model_id,
        "engine": "gns",
        "cases": list(cases),
        "description": (
            "2-D GNS step, ScatterElements aggregation, CPU and TensorRT bench graph"
            if bench
            else "2-D GNS step, padded neighbour layout, live graph"
        ),
        "onnx": {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)},
        "opset": OPSET,
        "ir_version": IR_VERSION,
        "precision": "fp16" if key == "fp16" else "fp32",
        "delivery": "bench-only" if bench else "live",
        "aggregation": "scatter-add" if bench else "padded-gather",
        "symbolic_dims": {"N": {"min": 1, "max": N_MAX}},
        "constants": {
            "particle_diameter_m": float(particle_diameter_m),
            "connectivity_radius_m": model.connectivity_radius,
            "max_neighbours": K_MAX,
            "velocity_history": HISTORY,
            "frame_interval_s": model.frame_interval,
        },
        "inputs": [
            {"name": "positions", "dtype": "float32", "shape": ["N", 2], "unit": "m"},
            {
                "name": "velocities",
                "dtype": "float32",
                "shape": ["N", HISTORY, 2],
                "unit": "m/s",
                "normalisation": standardise("velocities"),
            },
            {"name": "particle_type", "dtype": "int64", "shape": ["N"], "unit": "1", "categories": list(categories)},
            {"name": "bounds", "dtype": "float32", "shape": [4], "unit": "m"},
            {"name": "neighbour_index", "dtype": "int64", "shape": ["N", K_MAX], "unit": "1"},
            {"name": "neighbour_mask", "dtype": "bool", "shape": ["N", K_MAX], "unit": "1"},
        ],
        "outputs": [
            {
                "name": "acceleration",
                "dtype": "float32",
                "shape": ["N", 2],
                "unit": "m/s^2",
                "normalisation": standardise("acceleration"),
            }
        ],
        "training_envelope": copy.deepcopy(dict(envelope)),
    }
    if bench:
        doc["delivery_reason"] = (
            "ScatterElements(reduction = add) is unverified on WebGPU; used for the CPU and TensorRT bench only"
        )
    elif len(raw) > LIVE_BYTES_MAX:
        raise ValueError(f"live graph {key} is {len(raw)} bytes, above the {LIVE_BYTES_MAX} byte limit (NFR-011-01)")
    return doc
