"""Adapter to the upstream D-FINE code (Apache-2.0, github.com/Peterande/D-FINE) pinned at a commit (FR-009-18,
FR-009-35).

The upstream repository is a research code base driven by YAML files, not an installable package: this module imports
it from
a checkout (`PITSTUDIO_DFINE_CODE`, at `pins.DFINE_CODE_COMMIT`), builds the model, the criterion and the
post-processor from
the upstream configuration files with the overrides below, loads the pinned COCO-pretrained checkpoint (the weights
whose
shapes match; the class heads are re-initialised for the five perception classes) and exports the deployment graph.
Nothing here trains: the training loop of `s30_train` is `train_dfine`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from pitstudio_pipeline.perception.pins import DFINE_CODE_COMMIT, DFINE_CODE_ENV

CONFIGS = {"d-fine-n": "dfine_hgnetv2_n_coco.yml", "d-fine-s": "dfine_hgnetv2_s_coco.yml"}
INPUT_SIZE = 640  # eval_spatial_size of the upstream configuration, [640, 640]
NUM_QUERIES = 300  # num_queries and num_top_queries of the upstream configuration


def code_dir() -> Path:
    """The upstream checkout from `PITSTUDIO_DFINE_CODE`; refuses a checkout that is not at the pinned commit."""
    value = os.environ.get(DFINE_CODE_ENV)
    if not value:
        raise FileNotFoundError(f"environment variable {DFINE_CODE_ENV} is not set: it locates the D-FINE checkout")
    path = Path(value)
    if not (path / "src" / "core").is_dir():
        raise FileNotFoundError(f"{path} is not a D-FINE checkout (no src/core)")
    if (path / ".git").exists():
        head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        if head != DFINE_CODE_COMMIT:
            raise ValueError(f"the D-FINE checkout is at {head}, the pin is {DFINE_CODE_COMMIT}")
    return path


def import_upstream() -> Any:
    """Import and return the upstream `src.core` module (registers the models, criteria and post-processors)."""
    root = str(code_dir())
    if root not in sys.path:
        sys.path.insert(0, root)
    import src  # noqa: F401  (registers the upstream modules)
    from src import core

    return core


def make_config(model: str, *, num_classes: int, **overrides: Any) -> Any:
    """The upstream `YAMLConfig` of D-FINE-N or D-FINE-S with `num_classes` and no backbone download."""
    if model not in CONFIGS:
        raise ValueError(f"model must be one of {sorted(CONFIGS)}, got {model!r}")
    core = import_upstream()
    cfg_path = code_dir() / "configs" / "dfine" / CONFIGS[model]
    merged: dict[str, Any] = {
        "num_classes": int(num_classes),
        "remap_mscoco_category": False,
        "HGNetv2": {"pretrained": False},  # the pinned checkpoint carries every weight
        "use_amp": False,
        "use_ema": False,
    }
    merged.update(overrides)
    return core.YAMLConfig(str(cfg_path), **merged)


def read_state(checkpoint: Path) -> dict[str, Any]:
    """The weights of an upstream checkpoint (`ema.module` when present, else `model`), loaded as tensors only."""
    import torch

    blob = torch.load(str(checkpoint), map_location="cpu", weights_only=True)
    return blob["ema"]["module"] if "ema" in blob else blob["model"]  # type: ignore[no-any-return]


def load_matched(model: Any, state: dict[str, Any]) -> tuple[int, list[str]]:
    """Load into `model` every weight of `state` whose name and shape match; return (loaded count, skipped names)."""
    own = model.state_dict()
    matched = {k: v for k, v in state.items() if k in own and own[k].shape == v.shape}
    skipped = sorted(k for k in own if k not in matched)
    model.load_state_dict(matched, strict=False)
    return len(matched), skipped


def infer_variant(state: dict[str, Any]) -> tuple[str, int]:
    """(model name, number of classes) of a checkpoint, from the class head of its decoder."""
    head = state["decoder.enc_score_head.weight"]
    return ("d-fine-n" if int(head.shape[1]) == 128 else "d-fine-s"), int(head.shape[0])


def export_onnx(checkpoint: Path, output: Path, *, opset: int = 19) -> Path:
    """Export the deployment graph of a checkpoint with the post-processor and the top-300 selection inside (no NMS).

    Inputs `images` float32 [N, 3, 640, 640] and `orig_target_sizes` int64 [N, 2]; outputs `labels` int64 [N, 300],
    `boxes` float32 [N, 300, 4] (xyxy, px) and `scores` float32 [N, 300]; the upstream exporter's logic at opset 19,
    where
    GridSample keeps its since-version 16.
    """
    import torch
    from torch import nn

    state = read_state(checkpoint)
    name, n_classes = infer_variant(state)
    cfg = make_config(name, num_classes=n_classes)
    cfg.model.load_state_dict(state)  # the train-mode state; `deploy()` converts it

    class Deploy(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.model = cfg.model.deploy()
            self.postprocessor = cfg.postprocessor.deploy()

        def forward(self, images: torch.Tensor, orig_target_sizes: torch.Tensor) -> Any:
            return self.postprocessor(self.model(images), orig_target_sizes)

    net = Deploy().eval()
    images = torch.rand(2, 3, INPUT_SIZE, INPUT_SIZE)
    sizes = torch.tensor([[INPUT_SIZE, INPUT_SIZE]] * 2)
    with torch.no_grad():
        net(images, sizes)  # one forward pass: the trace needs a consistent state
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        torch.onnx.export(
            net,
            (images, sizes),
            str(output),
            input_names=["images", "orig_target_sizes"],
            output_names=["labels", "boxes", "scores"],
            dynamic_axes={"images": {0: "N"}, "orig_target_sizes": {0: "N"}},
            opset_version=opset,
            do_constant_folding=True,
            dynamo=False,
        )
    _declare_output_shapes(Path(output))
    return Path(output)


def _declare_output_shapes(path: Path) -> None:
    """Declare the output shapes the graph always produces: the exporter leaves the top-300 dimensions as inferred
    placeholders (`Sublabels_dim_1`), the signature of FR-009-35 states them (labels [N, 300], boxes [N, 300, 4],
    scores [N, 300]); the file is checked again afterwards."""
    import onnx

    model = onnx.load(str(path))
    wanted = {"labels": [300], "boxes": [300, 4], "scores": [300]}
    for out in model.graph.output:
        dims = out.type.tensor_type.shape.dim
        del dims[:]
        dims.add().dim_param = "N"
        for size in wanted[out.name]:
            dims.add().dim_value = size
    onnx.checker.check_model(model)
    onnx.save(model, str(path))
