"""CPU renderer of the dry run: the same rows, driver, file layout and record as the Isaac renderer, no GPU.

It stands in for `SdgRenderer` only when `run_job --dry-run` exercises the driver path on a tiny table: every object is
rasterised as the pinhole projection of its oriented bounding box (painter's order by depth) into the instance-id image
that `scene_render.write_frame` turns into files, so the file layout, COCO, digests, record, sidecar, frame state and
the dataset loader checks all run on real data of the right shape. It is never selectable for a real run.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_isaac.sdg.scene_render import box_corners, write_frame


class CpuRenderer:
    """Same interface as `SdgRenderer` (`render_row`, `close`)."""

    def render_row(self, row: Mapping[str, Any], out_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        camera = row["camera"]
        width, height = int(camera["width_px"]), int(camera["height_px"])
        pos = np.asarray(camera["position_m"], dtype=np.float64)
        fwd = np.asarray(camera["forward"], dtype=np.float64)
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, np.asarray(camera["up"], dtype=np.float64))
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        rng = np.random.default_rng(int(row["scenario_seed"]) % (2**32))
        rgb = (rng.integers(40, 200, size=(height, width, 3))).astype(np.uint8)
        depth = np.full((height, width), 150.0, dtype=np.float32)
        ids = np.zeros((height, width), dtype=np.uint32)
        id_to_path: dict[int, str] = {0: "BACKGROUND", 1: "UNLABELLED"}
        boxes: list[tuple[float, int, tuple[int, int, int, int], float, str]] = []
        for k, (obj, p) in enumerate(zip(row["objects"], row["dr"]["placements"], strict=True)):
            pts = box_corners(
                (p["x_m"], p["y_m"]), p["z_m"], p["yaw_deg"], obj["length_m"], obj["width_m"], obj["height_m"]
            )
            uv, depths = [], []
            for q in pts:
                d = np.asarray(q) - pos
                z = float(d @ fwd)
                if z <= 0.1:
                    continue
                uv.append(
                    (
                        camera["cx_px"] + camera["fx_px"] * float(d @ right) / z,
                        camera["cy_px"] - camera["fy_px"] * float(d @ up) / z,
                    )
                )
                depths.append(z)
            if not uv:
                continue
            u0, v0 = np.min(uv, axis=0)
            u1, v1 = np.max(uv, axis=0)
            x0, x1 = int(max(u0, 0)), int(min(u1, width))
            y0, y1 = int(max(v0, 0)), int(min(v1, height))
            if x1 > x0 and y1 > y0:
                boxes.append((min(depths), 2 + k, (x0, y0, x1, y1), min(depths), f"{obj['prim_id']}/Body"))
        for _, ident, (x0, y0, x1, y1), z, path in sorted(boxes, key=lambda b: -b[0]):  # far first, near paints over
            ids[y0:y1, x0:x1] = ident
            depth[y0:y1, x0:x1] = z
            id_to_path[ident] = path
        return write_frame(row, Path(out_dir), rgb, depth, ids, id_to_path)

    def close(self) -> None:
        return None
