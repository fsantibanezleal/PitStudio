"""Export hooks of the perception detectors for `s60_export`: ONNX signatures, the live set, lanes and variant rejection
(FR-009-35 to FR-009-39, NFR-009-01, NFR-009-02, NFR-009-06).

The generic export, parity layers and TensorRT work belong to spec 016; this module fixes what only spec 009 knows: the
D-FINE and RF-DETR-Seg-N graph signatures, which two ONNX files may ship, when a live candidate falls back to
precompute,
and which reduced-precision variants are rejected.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitstudio_pipeline.perception.robustness import CORRUPTIONS, MODELS, PRECISIONS, delta_rel

LIVE_ONNX_FILES: tuple[str, ...] = ("d-fine-n-fp16.onnx", "d-fine-s-int8.onnx")  # FR-009-37
MAX_LIVE_BYTES = 25_000_000  # budgets.onnx_live_each_mb_max: 25 MB, 1 MB = 10^6 bytes (NFR-009-01)
MAX_T1_MEDIAN_MS = 300.0  # NFR-009-02
MAX_T2_RUN_S = 1.0  # lane_gate.run_s_max
MIN_TIMING_IMAGES = 50
MIN_WARMUP_RUNS = 5
MAX_GALLERY = 300  # NFR-009-06
OPSET = 19
_GRID_SAMPLE_VERSION = 16
_RELPATH = re.compile(
    r"^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$"
)
_DRIFT_LIMIT_PP = 1.0  # FR-009-39: absolute change of mAP50 against fp32, in either direction
_SC03_LIMIT_PCT = 10.0


class SignatureError(ValueError):
    """The ONNX graph breaks its signature: `violations` holds one sentence per violation."""

    def __init__(self, violations: Sequence[str]) -> None:
        self.violations = tuple(violations)
        super().__init__("; ".join(self.violations))


class LaneError(Exception):
    """`code`: live-set (the ONNX files of the web build) or gallery-too-large; `files` names every offending file."""

    def __init__(self, code: str, message: str, files: Sequence[str] = ()) -> None:
        self.code = code
        self.files = tuple(files)
        shown = f": {', '.join(self.files)}" if self.files else ""
        super().__init__(f"{code}: {message}{shown}")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


# ----------------------------------------------------------------------------------------------------------------
# graph signatures (FR-009-35, FR-009-36)
# ----------------------------------------------------------------------------------------------------------------
def _dims(value_info: Any) -> list[int | str | None]:
    out: list[int | str | None] = []
    for d in value_info.type.tensor_type.shape.dim:
        if d.HasField("dim_value"):
            out.append(int(d.dim_value))
        elif d.HasField("dim_param"):
            out.append(str(d.dim_param))
        else:
            out.append(None)
    return out


def _elem_type(value_info: Any) -> int:
    return int(value_info.type.tensor_type.elem_type)


def _default_opset(model: Any) -> int | None:
    for imp in model.opset_import:
        if imp.domain in ("", "ai.onnx"):
            return int(imp.version)
    return None


def _all_nodes(graph: Any) -> list[Any]:
    nodes = []
    for node in graph.node:
        nodes.append(node)
        for attr in node.attribute:
            if attr.HasField("g"):
                nodes.extend(_all_nodes(attr.g))
            for sub in attr.graphs:
                nodes.extend(_all_nodes(sub))
    return nodes


def _runtime_inputs(model: Any) -> list[Any]:
    initialisers = {i.name for i in model.graph.initializer}
    return [i for i in model.graph.input if i.name not in initialisers]


def _check_opset(model: Any, violations: list[str], nodes: Sequence[Any]) -> None:
    import onnx

    opset = _default_opset(model)
    if opset is None:
        violations.append(f"the model declares no default-domain opset import, opset {OPSET} is required")
    elif opset != OPSET:
        violations.append(f"the default-domain opset is {opset}, opset {OPSET} is required")
    if opset is not None and any(n.op_type == "GridSample" and n.domain in ("", "ai.onnx") for n in nodes):
        version = onnx.defs.get_schema("GridSample", max_inclusive_version=opset).since_version
        if version != _GRID_SAMPLE_VERSION:
            violations.append(
                f"GridSample resolves to since-version {version} at opset {opset}, "
                f"version {_GRID_SAMPLE_VERSION} is required"
            )


def _check_tensor(
    info: Any, name: str, dtype: int, shape: Sequence[int | None], kind: str, violations: list[str]
) -> None:
    """`shape` entries: None = any batch dimension (symbolic or a positive int), int = that exact size."""
    got_dims = _dims(info)
    if _elem_type(info) != dtype:
        violations.append(f"{kind} {name} has dtype code {_elem_type(info)}, expected {dtype}")
    if len(got_dims) != len(shape):
        violations.append(f"{kind} {name} has rank {len(got_dims)}, expected {len(shape)}")
        return
    for axis, (got, want) in enumerate(zip(got_dims, shape, strict=True)):
        if want is None:
            if isinstance(got, int) and got < 1:
                violations.append(f"{kind} {name} dimension {axis} is {got}, expected a positive size or a symbol")
        elif got != want:
            violations.append(f"{kind} {name} dimension {axis} is {got}, expected {want}")


def _check_names(infos: Sequence[Any], expected: Sequence[str], kind: str, violations: list[str]) -> dict[str, Any]:
    by_name = {i.name: i for i in infos}
    violations.extend(f"{kind} {name} is missing" for name in expected if name not in by_name)
    violations.extend(
        f"unexpected {kind} {name}: the {kind}s are exactly {', '.join(expected)}"
        for name in by_name
        if name not in expected
    )
    return by_name


def inspect_dfine(model: Any) -> None:
    """Check a D-FINE graph against FR-009-35 and raise `SignatureError` listing every violation."""
    import onnx
    from onnx import TensorProto as TP

    if not isinstance(model, onnx.ModelProto):
        raise SignatureError([f"the model is not an onnx.ModelProto but {type(model).__name__}"])
    violations: list[str] = []
    nodes = _all_nodes(model.graph)
    _check_opset(model, violations, nodes)
    inputs = _check_names(_runtime_inputs(model), ("images", "orig_target_sizes"), "input", violations)
    if "images" in inputs:
        _check_tensor(inputs["images"], "images", TP.FLOAT, (None, 3, 640, 640), "input", violations)
    if "orig_target_sizes" in inputs:
        _check_tensor(inputs["orig_target_sizes"], "orig_target_sizes", TP.INT64, (None, 2), "input", violations)
    outputs = _check_names(list(model.graph.output), ("labels", "boxes", "scores"), "output", violations)
    if "labels" in outputs:
        _check_tensor(outputs["labels"], "labels", TP.INT64, (None, 300), "output", violations)
    if "boxes" in outputs:
        _check_tensor(outputs["boxes"], "boxes", TP.FLOAT, (None, 300, 4), "output", violations)
    if "scores" in outputs:
        _check_tensor(outputs["scores"], "scores", TP.FLOAT, (None, 300), "output", violations)
    if any(n.op_type == "NonMaxSuppression" for n in nodes):
        violations.append("the graph contains a NonMaxSuppression node: the post-processor is NMS-free")
    if not any(n.op_type == "TopK" for n in nodes):
        violations.append("the graph has no TopK node: the top-300 selection must be inside the graph")
    if violations:
        raise SignatureError(violations)


def inspect_rfdetr_seg(model: Any, *, output_names: Sequence[str]) -> None:
    """Check an RF-DETR-Seg-N graph against FR-009-36 (outputs named `output_names` as (boxes, labels, masks))."""
    import onnx
    from onnx import TensorProto as TP

    if not isinstance(model, onnx.ModelProto):
        raise SignatureError([f"the model is not an onnx.ModelProto but {type(model).__name__}"])
    if len(output_names) != 3:
        raise ValueError("output_names must be the three upstream output names (boxes, labels, masks)")
    violations: list[str] = []
    _check_opset(model, violations, _all_nodes(model.graph))
    inputs = _runtime_inputs(model)
    if len(inputs) != 1:
        violations.append(f"the graph has {len(inputs)} inputs, exactly one float32 input is required")
    elif _elem_type(inputs[0]) != TP.FLOAT or len(_dims(inputs[0])) != 4:
        violations.append(f"input {inputs[0].name} must be float32 of rank 4 [N, 3, 312, 312]")
    else:
        dims = _dims(inputs[0])
        if dims[2:] != [312, 312]:
            violations.append(f"input {inputs[0].name} has spatial size {dims[2]} x {dims[3]}, 312 x 312 is required")
    boxes, labels, masks = output_names
    outputs = _check_names(list(model.graph.output), (boxes, labels, masks), "output", violations)
    if boxes in outputs:
        _check_tensor(outputs[boxes], boxes, TP.FLOAT, (None, 100, 4), "output", violations)
    if labels in outputs:
        _check_tensor(outputs[labels], labels, TP.INT64, (None, 100), "output", violations)
    if masks in outputs:
        dims = _dims(outputs[masks])
        if _elem_type(outputs[masks]) != TP.FLOAT or len(dims) != 4 or dims[1] != 100:
            violations.append(f"output {masks} must be float32 of rank 4 with 100 queries on dimension 1")
    if violations:
        raise SignatureError(violations)


def initial_lane(model: str, precision: str) -> str:
    """The lane before any measurement: RF-DETR-Seg-N is precompute at every precision (FR-009-36); a D-FINE variant is
    live only when it is one of the two live candidates (FR-009-37) and then still has to pass
    `decide_detector_lane`."""
    if model not in MODELS:
        raise ValueError(f"model must be one of {MODELS}, got {model!r}")
    if precision not in PRECISIONS:
        raise ValueError(f"precision must be one of {PRECISIONS}, got {precision!r}")
    return "live" if f"{model}-{precision}.onnx" in LIVE_ONNX_FILES else "precompute"


def export_dfine_onnx(checkpoint: Path, output: Path) -> Path:
    """Export a D-FINE checkpoint at opset 19 with the in-graph post-processor (the upstream export logic)."""
    from pitstudio_pipeline.perception import dfine

    return dfine.export_onnx(Path(checkpoint), Path(output), opset=OPSET)


# ----------------------------------------------------------------------------------------------------------------
# the live set and the lanes (FR-009-37, FR-009-38)
# ----------------------------------------------------------------------------------------------------------------
def check_web_perception_onnx(web_root: Path) -> None:
    """The perception ONNX files of the web build (base names starting `d-fine-` or `rf-detr-`) are exactly the two live
    files, each once; `LaneError("live-set")` names every unexpected, duplicated and missing file."""
    root = Path(web_root)
    if not root.is_dir():
        raise FileNotFoundError(root)
    found: dict[str, int] = {}
    for path in sorted(root.rglob("*.onnx")):
        if path.name.startswith(("d-fine-", "rf-detr-")):
            found[path.name] = found.get(path.name, 0) + 1
    unexpected = [n for n in found if n not in LIVE_ONNX_FILES]
    duplicated = [n for n, c in found.items() if c > 1]
    missing = [n for n in LIVE_ONNX_FILES if n not in found]
    files = [*unexpected, *[n for n in duplicated if n not in unexpected], *missing]
    if files:
        raise LaneError("live-set", "the perception ONNX files must be exactly the two live files, each once", files)


def validate_timing_record(record: Mapping[str, Any]) -> None:
    """A web timing record needs >= 50 images and >= 5 warm-up runs for T1 and a T2 run time (NFR-009-02)."""
    t1 = record.get("t1") if isinstance(record, Mapping) else None
    t2 = record.get("t2") if isinstance(record, Mapping) else None
    if not isinstance(t1, Mapping):
        raise ValueError("timing record needs a t1 block")
    if not isinstance(t2, Mapping):
        raise ValueError("timing record needs a t2 block")
    for name, block in (("median_ms", t1), ("run_s", t2)):
        value = block.get(name)
        if not _is_number(value) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite number >= 0, got {value!r}")
    images, warmup = t1.get("images"), t1.get("warmup_runs")
    if not _is_int(images) or images < MIN_TIMING_IMAGES:
        raise ValueError(f"t1 images must be an int >= {MIN_TIMING_IMAGES}, got {images!r}")
    if not _is_int(warmup) or warmup < MIN_WARMUP_RUNS:
        raise ValueError(f"t1 warmup_runs must be an int >= {MIN_WARMUP_RUNS}, got {warmup!r}")


@dataclass(frozen=True)
class LaneDecision:
    """`live`, or `precompute` with one reason per violated limit (each names size, t1 or t2, or `not measured`)."""

    lane: str
    reasons: tuple[str, ...]


def decide_detector_lane(*, size_bytes: int, timing: Mapping[str, Any] | None) -> LaneDecision:
    """live iff size <= 25 x 10^6 bytes, T1 median <= 300 ms and T2 run <= 1 s; no timing means precompute."""
    if not _is_int(size_bytes) or size_bytes < 1:
        raise ValueError(f"size_bytes must be an int >= 1, got {size_bytes!r}")
    reasons: list[str] = []
    if size_bytes > MAX_LIVE_BYTES:
        reasons.append(f"size {size_bytes} B exceeds {MAX_LIVE_BYTES} B")
    if timing is None:
        reasons.append("not measured: no web timing record")
    else:
        validate_timing_record(timing)
        if timing["t1"]["median_ms"] > MAX_T1_MEDIAN_MS:
            reasons.append(f"t1 median {timing['t1']['median_ms']} ms exceeds {MAX_T1_MEDIAN_MS:g} ms")
        if timing["t2"]["run_s"] > MAX_T2_RUN_S:
            reasons.append(f"t2 run {timing['t2']['run_s']} s exceeds {MAX_T2_RUN_S:g} s")
    return LaneDecision("precompute" if reasons else "live", tuple(reasons))


def shipping_plan(variants: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Which variants ship as ONNX files and which only as baked outputs.

    A variant ships as an ONNX file only if it is one of the live files and `decide_detector_lane` says live; every
    other
    variant is baked only; a variant with `accepted: false` ships nowhere and is listed under `rejected`.
    """
    if not isinstance(variants, list):
        raise ValueError("variants must be a list of {model, precision, size_bytes, timing} objects")
    onnx_files: list[str] = []
    baked: list[str] = []
    rejected: list[str] = []
    reasons: dict[str, list[str]] = {}
    for v in variants:
        if not isinstance(v, Mapping):
            raise ValueError(f"variants entry {v!r} is not an object")
        if v.get("model") not in MODELS:
            raise ValueError(f"model must be one of {MODELS}, got {v.get('model')!r}")
        if v.get("precision") not in PRECISIONS:
            raise ValueError(f"precision must be one of {PRECISIONS}, got {v.get('precision')!r}")
        if not _is_int(v.get("size_bytes")):
            raise ValueError(f"size_bytes must be an int, got {v.get('size_bytes')!r}")
        name = f"{v['model']}-{v['precision']}"
        if v.get("accepted", True) is False:
            rejected.append(name)
        elif f"{name}.onnx" in LIVE_ONNX_FILES:
            decision = decide_detector_lane(size_bytes=v["size_bytes"], timing=v.get("timing"))
            if decision.lane == "live":
                onnx_files.append(f"{name}.onnx")
            else:
                baked.append(name)
                reasons[name] = list(decision.reasons)
        else:
            baked.append(name)
    return {
        "onnx_files": sorted(onnx_files),
        "baked_only": sorted(baked),
        "reasons": reasons,
        "rejected": sorted(rejected),
    }


def gallery_budget(thumbnails: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The B2 SDG gallery: at most 300 thumbnails, counted in the replay budget class `shards-clouds`."""
    if not isinstance(thumbnails, list):
        raise ValueError("thumbnails must be a list of {path, bytes} objects")
    total = 0
    for t in thumbnails:
        if (
            not isinstance(t, Mapping)
            or not isinstance(t.get("path"), str)
            or not _is_int(t.get("bytes"))
            or t["bytes"] < 0
        ):
            raise ValueError(f"thumbnails entry {t!r} needs a path and a non-negative int bytes")
        total += t["bytes"]
    if len(thumbnails) > MAX_GALLERY:
        raise LaneError("gallery-too-large", f"{len(thumbnails)} thumbnails, at most {MAX_GALLERY} are allowed")
    return {"count": len(thumbnails), "bytes": total, "budget_class": "shards-clouds"}


# ----------------------------------------------------------------------------------------------------------------
# reduced-precision variants (FR-009-39)
# ----------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class VariantVerdict:
    """`accepted` or `rejected` with reasons (each starts with `delta-map50` or `sc-009-03`) and their numbers."""

    model: str
    precision: str
    status: str
    reasons: tuple[str, ...]
    numbers: dict[str, float]


def _score(name: str, value: object) -> float:
    if not _is_number(value) or not math.isfinite(value) or not 0.0 <= value <= 1.0:  # type: ignore[operator]
        raise ValueError(f"{name} must be a finite number in [0, 1], got {value!r}")
    return float(value)  # type: ignore[arg-type]


def judge_variant(
    *,
    model: str,
    precision: str,
    map50_fp32: float,
    map50_variant: float,
    corruption_points: Sequence[Mapping[str, Any]],
) -> VariantVerdict:
    """Reject an fp16 or int8 variant whose mAP50 differs from fp32 by more than 1 pp, or whose relative drop exceeds
    10 %
    for a corruption at severity 1 or 2 (SC-009-03 on its own clean score)."""
    if precision not in ("fp16", "int8"):
        raise ValueError(f"precision must be 'fp16' or 'int8', got {precision!r}")
    if model not in ("d-fine-n", "d-fine-s"):
        raise ValueError(f"model must be 'd-fine-n' or 'd-fine-s', got {model!r}")
    ref, var = _score("map50_fp32", map50_fp32), _score("map50_variant", map50_variant)
    if not isinstance(corruption_points, list):
        raise ValueError("corruption_points must be a list of {corruption, severity, m_clean, m_corrupted} rows")
    drops: list[tuple[float, str, int]] = []
    for p in corruption_points:
        try:
            ok = (
                isinstance(p, Mapping)
                and p["corruption"] in CORRUPTIONS
                and _is_int(p["severity"])
                and 1 <= p["severity"] <= 5
            )
            drop = delta_rel(p["m_clean"], p["m_corrupted"]) if ok else None
        except KeyError, ValueError:
            drop = None
        if drop is None:
            raise ValueError(f"corruption_points row {p!r} is malformed")
        if p["severity"] in (1, 2):
            drops.append((drop, p["corruption"], int(p["severity"])))
    delta_pp = 100.0 * abs(var - ref)
    numbers = {"delta_pp": delta_pp}
    reasons: list[str] = []
    if delta_pp > _DRIFT_LIMIT_PP:
        reasons.append(
            f"delta-map50: mAP50 changes by {delta_pp:.2f} pp against fp32, more than {_DRIFT_LIMIT_PP:g} pp"
        )
    if drops:
        worst = max(drops)
        numbers["worst_delta_rel_pct"] = worst[0]
        for drop, corruption, severity in sorted(drops):
            if drop > _SC03_LIMIT_PCT:
                reasons.append(
                    f"sc-009-03: {corruption} severity {severity} loses {drop:.2f} % of the clean score, "
                    f"more than {_SC03_LIMIT_PCT:g} %"
                )
    return VariantVerdict(model, precision, "rejected" if reasons else "accepted", tuple(reasons), numbers)


def rejected_input_row(verdict: VariantVerdict, path: str) -> dict[str, str]:
    """The `rejected_inputs` row of DC-009-05 for a rejected variant: its file path and the reason with the numbers."""
    if verdict.status != "rejected":
        raise ValueError("verdict must be a rejected verdict")
    if not isinstance(path, str) or not _RELPATH.match(path):
        raise ValueError(f"path {path!r} must be a safe relative path")
    text = f"{verdict.model} {verdict.precision} rejected: " + "; ".join(verdict.reasons)
    return {"input": path, "reason": text[:300]}
