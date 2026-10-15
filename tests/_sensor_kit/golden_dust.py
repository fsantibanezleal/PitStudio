# ruff: noqa: E501, RUF001
"""Golden dust-slider frames for the Python and TypeScript parity tests (spec 013, P-013-15), written by an independent
reference: the dust rule of FR-013-11 to FR-013-14 implemented in `sensor_kit` from the spec text, the MurmurHash3 reference
and a hand-written 16-bit quantiser and payload packer. Nothing here calls the code under test.

Run `python tests/_sensor_kit/golden_dust.py <out_dir>` to (re)write `dust-golden-<n>.json`; the committed copies live in
`web/src/engines/sensors/__fixtures__/` and are locked.

Display rule fixed here (the web display and the Python bake both follow it): the displayed uint8 intensity of a kept return is
`floor(I0_code * exp(-2 tau) + 0.5)` clipped to 0..255 (round half up, the JavaScript `Math.round` rule); a dust return is
displayed with `floor(255 * dust_return_intensity + 0.5)`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sensor_kit as kit

RETRO, DIFFUSE, DUST = 0, 1, 2
LEVELS = 41
EXPECTED_LEVELS = (0, 1, 7, 20, 33, 40)  # levels for which the attenuated intensities are stored in full


def make_golden(
    seed: int, n: int, *, frame: int, run_seed: int, dust_return_intensity: float = 0.05, tau_ref: float = 1.0
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    beam = np.sort(rng.choice(200_000, n, replace=False)).astype(np.uint32)
    rng_m = rng.uniform(5.0, 120.0, n)
    d = rng.normal(size=(n, 3))
    xyz = d / np.linalg.norm(d, axis=1, keepdims=True) * rng_m[:, None]
    cls = np.where(rng.uniform(size=n) < 0.2, RETRO, DIFFUSE).astype(np.uint8)
    i0 = rng.integers(20, 256, n).astype(np.uint8)
    edge = rng.uniform(3.0, 25.0, n)
    beta_unit = rng.uniform(0.008, 0.012, n)
    in_dust = rng_m > edge
    tau_unit = np.where(in_dust, beta_unit * (rng_m - edge), 0.0).astype(np.float32)
    r_edge = np.where(in_dust, edge, 0.0).astype(np.float32)
    hashes = np.array([kit.beam_hash_ref(frame, int(b), run_seed) for b in beam], dtype=np.uint32)
    off = xyz.min(axis=0)
    ext = xyz.max(axis=0) - off
    scale = ext / 65535
    q = np.rint((xyz - off) / scale).astype(np.uint16)
    k = [0.0, *np.geomspace(0.01, -math.log(0.02) / tau_ref, 40).tolist()]
    payload = b"".join(
        [
            q[:, 0].astype("<u2").tobytes(),
            q[:, 1].astype("<u2").tobytes(),
            q[:, 2].astype("<u2").tobytes(),
            i0.tobytes(),
            cls.tobytes(),
            tau_unit.astype("<f4").tobytes(),
            r_edge.astype("<f4").tobytes(),
            hashes.astype("<u4").tobytes(),
        ]
    )
    assert len(payload) == 20 * n
    header = {
        "schema_version": "1.0",
        "source": {"run_id": "20261007T120000Z-b1-sensors", "sensor": "rotary-64", "frame": frame},
        "returns": n,
        "levels": LEVELS,
        "k": k,
        "tau_ref": tau_ref,
        "rule": {"tau_on": 0.3216, "tau_floor_retro": 3.912, "tau_floor_diffuse": 2.8134},
        "dust_return_intensity": dust_return_intensity,
        "material_codes": {"retro": RETRO, "diffuse": DIFFUSE, "dust": DUST},
        "label": "own Beer–Lambert dust model",
        "quantisation": {"offset_m": off.tolist(), "scale_m": scale.tolist()},
        "encoding": {
            "position": "uint16",
            "intensity": "uint8",
            "class": "uint8",
            "tau_unit": "float32",
            "r_edge_m": "float32",
            "hash": "uint32",
            "byte_order": "little",
            "layout": "planar",
        },
        "payload": {
            "path": f"sensors/s1/dust-slider-{frame:05d}.bin",
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
    }
    expected: dict[str, Any] = {}
    u = hashes.astype(np.float64) / 2.0**32
    floor = np.where(cls == RETRO, 3.912, 2.8134)
    display_dust = math.floor(255 * dust_return_intensity + 0.5)
    tau_unit64 = tau_unit.astype(np.float64)
    for max_returns in (1, 2):
        levels = []
        for j in range(LEVELS):
            tau = k[j] * tau_unit64
            keep = (tau <= 0.3216) | ((tau <= floor) & (u * (floor - 0.3216) < floor - tau))
            emit = (tau > 0.3216) & (~keep | (max_returns >= 2))
            att = i0.astype(np.float64) * np.exp(-2.0 * tau)
            display = np.clip(np.floor(att + 0.5), 0, 255).astype(int)
            entry: dict[str, Any] = {
                "level": j,
                "kept": "".join("1" if x else "0" for x in keep),
                "emit": "".join("1" if x else "0" for x in emit),
                "dust_count": int(emit.sum()),
                "r_edge": [float(x) for x in r_edge[emit].astype(np.float64)],
                "display": display[keep].tolist(),
                "dust_display": display_dust,
            }
            if j in EXPECTED_LEVELS:
                entry["intensity"] = att[keep].tolist()
            levels.append(entry)
        expected[f"max_returns_{max_returns}"] = levels
    inputs = {
        "positions": xyz,
        "intensity_code": i0,
        "class_codes": cls,
        "tau_unit": tau_unit,
        "r_edge": r_edge,
        "beam": beam,
    }
    return {
        "header": header,
        "payload_b64": base64.b64encode(payload).decode("ascii"),
        "expected": expected,
        "inputs": inputs,
    }  # `inputs` (the arrays behind the payload) is kept in memory only, never written


GOLDENS = [  # (seed, returns, frame, run seed)
    (1, 300, 3, 20261007),
    (2, 250, 17, 99),
    (3, 350, 0, 4294967295),
]


def write_all(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, (seed, n, frame, run_seed) in enumerate(GOLDENS, start=1):
        doc = make_golden(seed, n, frame=frame, run_seed=run_seed)
        doc.pop("inputs")
        path = out_dir / f"dust-golden-{i}.json"
        path.write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


if __name__ == "__main__":
    for p in write_all(Path(sys.argv[1])):
        print(p, p.stat().st_size)
