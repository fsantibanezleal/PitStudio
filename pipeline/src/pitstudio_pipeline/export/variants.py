"""Deployed and parity variants of a model with an in-graph post-processor (FR-016-05)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitstudio_pipeline.export.onnx_export import ExportResult, export_model


def _chain(backbone: Any, postprocessor: Any) -> Any:
    import torch

    class Deployed(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.backbone, self.post = backbone, postprocessor

        def forward(self, *args: Any) -> Any:
            return self.post(self.backbone(*args))

    return Deployed().eval()


def export_variants(
    backbone: Any, postprocessor: Any, example_inputs: tuple, config: dict, out_dir: Path
) -> dict[str, ExportResult | None]:
    """`deployed` (post-processor in the graph) and `parity` (the backbone alone, same weights)."""
    out_dir = Path(out_dir)
    name = config["model"]
    if not config["post_processor_in_graph"]:
        return {"deployed": export_model(backbone, example_inputs, config, out_dir / f"{name}.onnx"), "parity": None}
    return {
        "deployed": export_model(_chain(backbone, postprocessor), example_inputs, config, out_dir / f"{name}-deployed.onnx"),
        "parity": export_model(backbone, example_inputs, config, out_dir / f"{name}-parity.onnx"),
    }
