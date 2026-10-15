"""Guarded torch.onnx dynamo export with cleanup, IR pin and checks (FR-016-01, FR-016-02, P-016-11, NFR-016-03).

The export is validated twice: the config against `contracts/export-config.schema.json` before anything runs, and the
written graph (IR version, operator domains, GridSample for web graphs, ONNX checker, ONNX Runtime CPU load) before the
file appears. A refused model leaves no file at `out_path`; the file is written atomically.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitstudio_pipeline._contracts import schema_errors

IR_VERSION = 10
DEFAULT_DOMAINS = ("", "ai.onnx")
GRIDSAMPLE_WEB_MAX_SINCE = 19
DYNAMO_MIN_OPSET = 18


class ExportError(Exception):
    """A refused export; `.reason` is the message and is never empty."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason or "export refused")
        self.reason = reason or "export refused"


@dataclass(frozen=True)
class ExportResult:
    path: Path
    sha256: str
    opset: int
    opset_reason: str
    ir_version: int


def pin_ir_version(model: Any, version: int = IR_VERSION) -> Any:
    """A copy of `model` that differs from it only in `ir_version`; idempotent."""
    pinned = type(model)()
    pinned.CopyFrom(model)
    pinned.ir_version = version
    return pinned


def _default_opset(model: Any) -> int | None:
    for imported in model.opset_import:
        if imported.domain in DEFAULT_DOMAINS:
            return int(imported.version)
    return None


def check_graph(model: Any, config: Mapping[str, Any]) -> None:
    """Raise ExportError for a wrong IR version, a node domain outside the allow-list or a web GridSample >= 20."""
    import onnx

    if model.ir_version != IR_VERSION:
        raise ExportError(f"ir_version {model.ir_version} is not {IR_VERSION}")
    allowed = {"" if d == "ai.onnx" else d for d in config.get("domains", ["ai.onnx"])}
    for node in model.graph.node:
        domain = "" if node.domain == "ai.onnx" else node.domain
        if domain not in allowed:
            raise ExportError(f"node {node.name or node.op_type} uses domain {node.domain!r} outside the allow-list")
    if config.get("web"):
        opset = _default_opset(model)
        if opset is not None and any(n.op_type == "GridSample" and n.domain in DEFAULT_DOMAINS for n in model.graph.node):
            since = onnx.defs.get_schema("GridSample", opset).since_version
            if since > GRIDSAMPLE_WEB_MAX_SINCE:
                raise ExportError(f"GridSample resolves to since-version {since} at opset {opset}; the web runtime stops at 19")


def _strip_opset18_attributes(model: Any) -> Any:
    """The ONNX converter keeps `noop_with_empty_axes` (opset 18) on reductions it moves to opset 17; drop the default."""
    for node in model.graph.node:
        for attr in list(node.attribute):
            if attr.name == "noop_with_empty_axes":
                if attr.i != 0:
                    raise ExportError(f"{node.op_type} needs noop_with_empty_axes, which opset 17 cannot express")
                node.attribute.remove(attr)
    return model


def _validate_config(config: Mapping[str, Any], known_models: Collection[str] | None) -> None:
    errors = schema_errors("export-config.schema.json", dict(config))
    if errors:
        pointer, message = errors[0]
        raise ExportError(f"export config invalid at {pointer or '/'}: {message}")
    if known_models is not None and config["model"] not in known_models:
        raise ExportError(f"unknown model {config['model']!r}")


def export_model(
    model: Any,
    example_inputs: tuple,
    config: dict,
    out_path: Path,
    *,
    known_models: Collection[str] | None = None,
) -> ExportResult:
    """Export `model` at `config["opset"]`, clean, pin IR 10, check and write `out_path` (or raise and write nothing)."""
    import onnx
    import onnxruntime as ort
    import onnxslim
    import torch

    _validate_config(config, known_models)
    out_path = Path(out_path)
    opset = int(config["opset"])
    try:
        with torch.no_grad():
            # the dynamo exporter is native from opset 18; opset 17 is reached by converting the cleaned graph
            program = torch.onnx.export(
                model.eval(), example_inputs, opset_version=max(opset, DYNAMO_MIN_OPSET), dynamo=True, optimize=True
            )
        proto = onnxslim.slim(program.model_proto)
        if opset < DYNAMO_MIN_OPSET:
            proto = _strip_opset18_attributes(onnx.version_converter.convert_version(proto, opset))
    except Exception as exc:
        raise ExportError(f"export failed: {type(exc).__name__}: {exc}") from exc
    proto = pin_ir_version(proto)
    if _default_opset(proto) != opset:
        raise ExportError(f"exported opset {_default_opset(proto)} differs from the configured opset {opset}")
    check_graph(proto, config)
    try:
        onnx.checker.check_model(proto, full_check=True)
    except Exception as exc:
        raise ExportError(f"ONNX checker refused the graph: {exc}") from exc
    data = proto.SerializeToString()
    try:
        ort.InferenceSession(data, providers=["CPUExecutionProvider"])
    except Exception as exc:
        raise ExportError(f"ONNX Runtime CPU cannot load the graph: {exc}") from exc
    out_path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=out_path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(data)
        os.replace(tmp_name, out_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return ExportResult(out_path, hashlib.sha256(data).hexdigest(), opset, config["opset_reason"], IR_VERSION)
