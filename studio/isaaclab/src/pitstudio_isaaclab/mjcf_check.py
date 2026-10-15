# SPDX-License-Identifier: Apache-2.0
"""MuJoCo compile check of a generated machine model (T-014-062, FR-014-05); CPU only.

``python -m pitstudio_isaaclab.mjcf_check --model model.xml`` prints one JSON object: whether MuJoCo's own compiler accepts
the file, its body and joint counts and the total mass.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pitstudio_isaaclab import runtime


def check(model: Path) -> dict[str, object]:
    import mujoco

    try:
        m = mujoco.MjModel.from_xml_path(str(model))
    except Exception as exc:
        return {"compiled": False, "nbody": 0, "njnt": 0, "total_mass_kg": 0.0, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "compiled": True,
        "nbody": int(m.nbody),
        "njnt": int(m.njnt),
        "total_mass_kg": float(m.body_mass.sum()),
        "error": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args(argv)
    result = check(args.model)
    runtime.emit(result)
    return 0 if result["compiled"] else 1


if __name__ == "__main__":
    sys.exit(main())
