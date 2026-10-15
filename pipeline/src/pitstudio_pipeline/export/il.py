# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""ONNX export of the trained IL policies (FR-014-27, FR-014-28, FR-014-49, NFR-014-03, SC-014-10).

``export_il_policy`` reads a policy handoff (``contracts/il-policy-handoff.schema.json``), checks it, and writes the actor
as an ONNX graph (opset 17, IR version 10, fp32) with the observation normaliser inside it:

    action = actor((obs - mean) / (sqrt(var) + 1e-2))

The graph is built node by node with ``onnx.helper`` from the checkpoint tensors, so it does not depend on a torch exporter
and holds exactly the layers named. It is checked against a PyTorch module built from the same tensors on the golden
observations (rtol 1e-3, atol 1e-5, max abs 1e-4) before anything is written. A handoff that fails any check raises
``ExportRejected`` naming the JSON pointer and writes nothing. A checkpoint whose digest differs from the handoff raises
``StaleInput`` (error class ``input-stale``) before the checkpoint is read as a model.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

from pitstudio.robots.fixture import is_fixture
from pitstudio_pipeline._contracts import _validator

__all__ = ["ExportRejected", "ExportResult", "StaleInput", "export_il_policy"]

NORMALISER_EPS = 1e-2  # EmpiricalNormalization eps of rsl_rl
OPSET = 17
IR_VERSION = 10
RTOL, ATOL, MAX_ABS = 1e-3, 1e-5, 1e-4
MIN_GOLDENS = 200
_QUOTED = re.compile(r"'([^']+)'")
_ACTIVATIONS = {"elu": "Elu", "relu": "Relu", "tanh": "Tanh"}
_SIZES = {"IL-1": (63, 2), "IL-2": (46, 4), "IL-3": (46, 4)}


class ExportRejected(ValueError):
    """The handoff or one of its files is refused; ``pointer`` names the first offending member."""

    def __init__(self, pointer: str, message: str) -> None:
        super().__init__(f"{pointer}: {message}")
        self.pointer = pointer


class StaleInput(ExportRejected):
    """The checkpoint now present is not the one the handoff describes (error class ``input-stale``)."""

    error_class = "input-stale"

    def __init__(self, input_id: str, path: str, expected: str, actual: str) -> None:
        super().__init__(
            "/checkpoint/sha256",
            f"input-stale: checkpoint {input_id} ({path}) has sha256 {actual}, the handoff expects {expected}",
        )
        self.input = input_id
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True)
class ExportResult:
    onnx_path: Path
    sha256: str
    bytes: int
    parity: dict[str, Any]
    input_name: str = "obs"
    output_name: str = "action"
    fixture: bool = False


def _pointer(path: Any) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in path)


def _non_finite(node: Any, path: tuple[Any, ...] = ()) -> list[str]:
    if isinstance(node, float) and not math.isfinite(node):
        return [f"{_pointer(path)}: must be finite"]
    out: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            out.extend(_non_finite(value, (*path, key)))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out.extend(_non_finite(value, (*path, i)))
    return out


def _schema_problems(doc: dict[str, Any]) -> list[str]:
    out = _non_finite(doc)
    if out:
        return out
    for error in _validator("il-policy-handoff.schema.json").iter_errors(doc):
        base = _pointer(error.absolute_path)
        if error.validator in ("required", "additionalProperties"):
            out.extend(f"{base}/{name}: {error.message[:160]}" for name in _QUOTED.findall(error.message))
        else:
            out.append(f"{base or '/'}: {error.message[:160]}")
    return out


def _load_handoff(handoff: Any) -> dict[str, Any]:
    if isinstance(handoff, Path):
        try:
            handoff = json.loads(handoff.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ExportRejected("/", f"the handoff file {handoff.name} is not readable JSON") from exc
    if not isinstance(handoff, dict) or not handoff:
        raise ExportRejected("/", "the handoff must be a non-empty JSON object")
    return handoff


def _inside(root: Path, rel: str, pointer: str) -> Path:
    candidate = (root / PurePosixPath(rel)).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ExportRejected(pointer, f"{rel} leaves the run folder")
    return candidate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _goldens(handoff: dict[str, Any], root: Path, n_obs: int) -> np.ndarray:
    spec = handoff["goldens"]
    path = _inside(root, spec["path"], "/goldens/path")
    if not path.is_file():
        raise ExportRejected("/goldens", f"golden file {spec['path']} is missing")
    if _sha256(path) != spec["sha256"]:
        raise ExportRejected("/goldens", f"golden file {spec['path']} does not match goldens.sha256")
    try:
        with np.load(path, allow_pickle=False) as data:
            obs = np.asarray(data["observations"])
    except (OSError, ValueError, KeyError) as exc:
        raise ExportRejected("/goldens", f"golden file {spec['path']} holds no readable observations array") from exc
    need = max(int(spec["count"]), MIN_GOLDENS)
    if obs.ndim != 2 or obs.shape[1] != n_obs:
        raise ExportRejected("/goldens", f"observations must have shape (count, {n_obs}), got {obs.shape}")
    if obs.shape[0] < need:
        raise ExportRejected("/goldens", f"golden file holds {obs.shape[0]} rows, fewer than the {need} required")
    if not np.all(np.isfinite(obs)):
        raise ExportRejected("/goldens", "golden observations hold a non-finite value")
    return obs[: int(spec["count"])].astype(np.float32)


def _actor_tensors(path: Path, n_obs: int, n_act: int) -> list[tuple[np.ndarray, np.ndarray]]:
    import torch

    try:
        state = torch.load(path, map_location="cpu", weights_only=True)
        tensors = state["model_state_dict"]
    except Exception as exc:  # any unreadable or foreign file is one rejection
        raise ExportRejected("/checkpoint", f"{path.name} is not a readable training checkpoint") from exc
    shapes = [(256, n_obs), (256, 256), (n_act, 256)]
    layers: list[tuple[np.ndarray, np.ndarray]] = []
    for i, shape in enumerate(shapes):
        w_key, b_key = f"actor.{2 * i}.weight", f"actor.{2 * i}.bias"
        if w_key not in tensors or b_key not in tensors:
            raise ExportRejected("/checkpoint", f"{path.name} lacks the actor tensor {w_key} or {b_key}")
        w, b = tensors[w_key], tensors[b_key]
        if tuple(w.shape) != shape or tuple(b.shape) != (shape[0],):
            raise ExportRejected(
                "/checkpoint",
                f"{w_key} has shape {tuple(w.shape)}, the handoff (/actor/hidden_units, observation and action sizes) "
                f"needs {shape}",
            )
        layers.append((w.numpy().astype(np.float32), b.numpy().astype(np.float32)))
    return layers


def _build_onnx(
    layers: list[tuple[np.ndarray, np.ndarray]], mean: np.ndarray, var: np.ndarray, activation: str
) -> bytes:
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    n_obs, n_act = layers[0][0].shape[1], layers[-1][0].shape[0]
    denom = (np.sqrt(var) + NORMALISER_EPS).astype(np.float32)
    inits = [
        numpy_helper.from_array(mean.astype(np.float32), "obs_mean"),
        numpy_helper.from_array(denom, "obs_denominator"),
    ]
    nodes = [
        helper.make_node("Sub", ["obs", "obs_mean"], ["obs_centred"]),
        helper.make_node("Div", ["obs_centred", "obs_denominator"], ["obs_normalised"]),
    ]
    current = "obs_normalised"
    for i, (w, b) in enumerate(layers):
        inits.append(numpy_helper.from_array(w, f"actor_{i}_weight"))
        inits.append(numpy_helper.from_array(b, f"actor_{i}_bias"))
        out = "action" if i == len(layers) - 1 else f"actor_{i}_linear"
        nodes.append(helper.make_node("Gemm", [current, f"actor_{i}_weight", f"actor_{i}_bias"], [out], transB=1))
        current = out
        if i < len(layers) - 1:
            nodes.append(helper.make_node(_ACTIVATIONS[activation], [current], [f"actor_{i}_act"]))
            current = f"actor_{i}_act"
    graph = helper.make_graph(
        nodes,
        "il_policy",
        [helper.make_tensor_value_info("obs", TensorProto.FLOAT, ["batch", n_obs])],
        [helper.make_tensor_value_info("action", TensorProto.FLOAT, ["batch", n_act])],
        initializer=inits,
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", OPSET)], producer_name="pitstudio")
    model.ir_version = IR_VERSION
    onnx.checker.check_model(model, full_check=True)
    return model.SerializeToString()


def _reference(layers: list[tuple[np.ndarray, np.ndarray]], mean: np.ndarray, var: np.ndarray, activation: str, obs):
    import torch

    act = {"elu": torch.nn.ELU, "relu": torch.nn.ReLU, "tanh": torch.nn.Tanh}[activation]
    modules: list[Any] = []
    for i, (w, b) in enumerate(layers):
        linear = torch.nn.Linear(w.shape[1], w.shape[0])
        linear.weight.data = torch.from_numpy(w)
        linear.bias.data = torch.from_numpy(b)
        modules.append(linear)
        if i < len(layers) - 1:
            modules.append(act())
    net = torch.nn.Sequential(*modules)
    z = (obs.astype(np.float64) - mean) / (np.sqrt(var) + NORMALISER_EPS)
    with torch.no_grad():
        return net(torch.tensor(z, dtype=torch.float32)).numpy()


def export_il_policy(
    handoff: Any,
    *,
    root: Path | str,
    out_dir: Path | str,
    fixture: bool | None = None,
    handoff_path: Path | str | None = None,
) -> ExportResult:
    """Validate the handoff, export the actor as ONNX, check parity on the goldens, then write the file.

    The export runs the same way for a contract fixture; the result carries ``fixture`` (FR-014-48): the explicit flag, or
    the location of ``handoff_path`` under ``contracts/examples`` or ``data/samples``.
    """
    marked = is_fixture(handoff_path, flag=fixture)
    doc = _load_handoff(handoff)
    problems = _schema_problems(doc)
    if problems:
        pointer = problems[0].split(":", 1)[0]
        raise ExportRejected(pointer, "; ".join(problems[:8]))
    n_obs, n_act = _SIZES[doc["policy"]]
    if doc["observation_size"] != n_obs or doc["action_size"] != n_act:
        raise ExportRejected("/observation_size", f"{doc['policy']} needs {n_obs} observations and {n_act} actions")
    mean = np.asarray(doc["normaliser"]["mean"], dtype=np.float64)
    var = np.asarray(doc["normaliser"]["var"], dtype=np.float64)
    if mean.shape != (n_obs,) or var.shape != (n_obs,):
        raise ExportRejected("/normaliser", f"mean and var must hold {n_obs} values")
    if np.any(var <= 0.0):
        raise ExportRejected("/normaliser/var", "every variance must be > 0")
    base = Path(root)
    ckpt = doc["checkpoint"]
    ckpt_path = _inside(base, ckpt["path"], "/checkpoint/path")
    if not ckpt_path.is_file():
        raise ExportRejected("/checkpoint", f"checkpoint {ckpt['path']} is missing")
    actual = _sha256(ckpt_path)
    if actual != ckpt["sha256"]:
        raise StaleInput(ckpt["id"], ckpt["path"], ckpt["sha256"], actual)
    obs = _goldens(doc, base, n_obs)
    layers = _actor_tensors(ckpt_path, n_obs, n_act)
    activation = doc["actor"]["activation"]
    blob = _build_onnx(layers, mean, var, activation)

    import onnxruntime as ort

    session = ort.InferenceSession(blob, providers=["CPUExecutionProvider"])
    got = session.run(None, {"obs": obs})[0]
    want = _reference(layers, mean, var, activation, obs)
    max_abs = float(np.max(np.abs(got - want)))
    ok = bool(np.allclose(got, want, rtol=RTOL, atol=ATOL) and max_abs <= MAX_ABS)
    parity = {"count": int(obs.shape[0]), "max_abs": max_abs, "rtol": RTOL, "atol": ATOL, "ok": ok}
    if not ok:
        raise ExportRejected("/parity", f"ONNX output differs from PyTorch by {max_abs:.3g} on {obs.shape[0]} goldens")
    if len(blob) >= 1_000_000:
        raise ExportRejected("/parity", f"the exported policy is {len(blob)} bytes, the limit is below 1,000,000")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{doc['policy'].lower().replace('-', '')}.onnx"
    tmp = target.with_suffix(".onnx.tmp")
    tmp.write_bytes(blob)
    tmp.replace(target)
    return ExportResult(target, hashlib.sha256(blob).hexdigest(), len(blob), parity, fixture=marked)
