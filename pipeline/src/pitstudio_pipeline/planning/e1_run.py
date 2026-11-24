"""E1 run: min-cut shells over the revenue-factor grid on an `oreblocks` deposit, pushbacks, and the chart-series files
of the case page (FR-017-14..17, FR-017-51, NFR-017-06).

Usage: python -m pitstudio_pipeline.planning.e1_run RECIPE.yaml OUT_DIR

Writes `e1-shells.json` (a DC-017-03 result: shells, ultimate pit and pushbacks; units and schedule are optional in
the contract and absent here, the scheduler is not part of this run), `charts/e1-*.json` (DC-020-05 chart-series,
case E1) and
`e1-run.json` (inputs, versions, the min-cut timing, the oracle comparison). The deposit is synthetic.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio.planning.pushbacks import build_pushbacks
from pitstudio.planning.shells import LAMBDA_GRID, ShellTable, compute_shells, encode_bitset
from pitstudio.planning.timing import record_mincut_time, timing_manifest_entries
from pitstudio_pipeline.planning.oreblocks_io import TwinInstance, twin_instance

MINEPHYS_PIN = "98d5b25"  # the `minephys` revision of pyproject.toml; its package version string is 0.0.0
LABEL = "calibrated synthetic: seeded oreblocks deposit, not validated against a real deposit"
SERVES = ["FR-018-16", "FR-017-16"]
MILLION = 1e6


def _en_es(en: str, es: str) -> dict:
    return {"en": en, "es": es}


def _producer(inst: TwinInstance, method: str) -> dict:
    return {
        "tool": "pitstudio",
        "method": method,
        "version": f"minephys-{MINEPHYS_PIN}-oreblocks-{inst.version}",
        "label": LABEL,
    }


def _chart(inst: TwinInstance, cid: str, ctype: str, title: dict, method: str, serves: list[str], **body: Any) -> dict:
    return {
        "schema_version": "1.0",
        "kind": "chart-series",
        "id": cid,
        "case": "E1",
        "chart_type": ctype,
        "status": "ok",
        "title": title,
        "producer": _producer(inst, method),
        "serves": serves,
        **body,
    }


def _lambda_axis() -> dict:
    return {"label": _en_es("Revenue factor", "Factor de ingreso"), "unit": "1"}


def _section(inst: TwinInstance, masks: dict[float, np.ndarray]) -> dict:
    """The central east-west section: the pit floor at every column that holds a pit block, one polyline per lambda."""
    nx, ny, nz = inst.dims
    dx, _, dz = inst.block_size_m
    iy = ny // 2
    top = nz * dz
    lines = [
        {
            "id": "ground",
            "label": _en_es("Original ground (deposit top)", "Terreno original (tope del depósito)"),
            "role": "ground",
            "points": [[0.0, top], [nx * dx, top]],
        }
    ]
    for lam, mask in masks.items():
        cube = mask.reshape(nz, ny, nx)[:, iy, :]  # (level, ix)
        cols = [ix for ix in range(nx) if cube[:, ix].any()]
        if not cols:
            continue
        pts = [[cols[0] * dx, top]]
        pts += [[(ix + 0.5) * dx, float(np.flatnonzero(cube[:, ix]).min() * dz)] for ix in cols]
        pts.append([(cols[-1] + 1) * dx, top])
        lines.append(
            {
                "id": f"shell-{round(lam * 1000):04d}",
                "label": _en_es(f"Shell at revenue factor {lam:g}", f"Cascarón con factor de ingreso {lam:g}"),
                "role": "shell",
                "points": pts,
            }
        )
    return {"polylines": lines}


def run_e1(
    out_dir: Path,
    *,
    archetype: str,
    dims: tuple[int, int, int],
    seed: int,
    t_min_t: float,
    section_lambdas: Sequence[float],
    clock: Any = time,
) -> dict:
    """Solve the shells of one deposit and write every output; returns the content of `e1-run.json`."""
    out_dir = Path(out_dir)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)
    inst = twin_instance(archetype, dims, seed)
    econ = inst.econ
    econ_args = {
        "recovery": econ["recovery"],
        "net_price": econ["price"],
        "processing_cost": econ["processing_cost"],
        "mining_cost": econ["mining_cost"],
    }
    cpu = platform.processor() or "unknown"
    records, parts = [], []
    for lam in LAMBDA_GRID:  # one min-cut per revenue factor, each timed against the 60 s budget of NFR-017-06
        rec = record_mincut_time(
            f"{inst.name}-lambda-{lam:.3f}",
            inst.n_blocks,
            lambda lam=lam: compute_shells(inst.tonnage, inst.grade, inst.arcs, lambdas=[lam], **econ_args),
            clock=clock,
            cpu=cpu,
        )
        parts.append(rec.pop("result"))
        records.append(rec)
    table = ShellTable(
        rows=[p.rows[0] for p in parts],
        masks=[p.masks[0] for p in parts],
        ultimate_pit=parts[-1].ultimate_pit | {"shell": len(parts) - 1},
    )
    # A pushback is accounted by the destination of its blocks at the ultimate pit (revenue factor of the last
    # shell), so its ore and waste tonnages never fall (at a smaller shell's own factor a block may be waste that is
    # ore later).
    last_lam = LAMBDA_GRID[-1]
    ore_final = (last_lam * inst.grade * econ["recovery"] * econ["price"] - econ["processing_cost"]) > 0
    shells = [
        {
            "lambda": r["lambda"],
            "mask": m,
            "ore_t": float(inst.tonnage[m & ore_final].sum()),
            "waste_t": float(inst.tonnage[m & ~ore_final].sum()),
        }
        for r, m in zip(table.rows, table.masks, strict=True)
    ]
    pushbacks = build_pushbacks(shells, t_min_t=t_min_t)
    final = table.ultimate_pit

    doc = {
        "schema_version": "1.0",
        "block_model": {"id": inst.name, "sha256": inst.sha256(), "n_blocks": inst.n_blocks},
        "licence": {"spdx": "CC-BY-4.0", "licence_class": "own"},
        "block_set_encoding": "bitset-lsb0-base64",
        "config": {"lambdas": list(LAMBDA_GRID), "t_min_t": float(t_min_t)},
        "shells": table.rows,
        "ultimate_pit": final,
        "pushbacks": [
            {
                "shell": pb["shell"],
                "blocks": encode_bitset(pb["mask"]),
                "ore_t": pb["ore_t"],
                "waste_t": pb["waste_t"],
                "strip_ratio_incremental": pb["strip_ratio_incremental"],
                "strip_ratio_cumulative": pb["strip_ratio_cumulative"],
            }
            for pb in pushbacks
        ],
    }
    (out_dir / "e1-shells.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")

    rows = table.rows
    lam_x = [r["lambda"] for r in rows]
    method = "minimum cut (minephys.planning) over the revenue-factor grid"
    charts = [
        _chart(
            inst,
            "e1-value-vs-lambda",
            "line",
            _en_es("Pit value against revenue factor", "Valor del pit según el factor de ingreso"),
            method,
            SERVES,
            x_axis=_lambda_axis(),
            y_axis={"label": _en_es("Pit value", "Valor del pit"), "unit": "MUSD"},
            series=[
                {
                    "id": "pit-value",
                    "label": _en_es("Value of the ultimate pit", "Valor del pit último"),
                    "x": lam_x,
                    "y": [r["value_cents"] / 1e8 for r in rows],
                    "n": inst.n_blocks,
                }
            ],
            markers=[
                {
                    "id": "ultimate-pit",
                    "label": _en_es("Ultimate pit (revenue factor 1)", "Pit último (factor de ingreso 1)"),
                    "value_text": f"{final['value_cents'] / 1e8:,.1f} MUSD",
                    "orientation": "point",
                    "x": rows[-1]["lambda"],
                    "y": final["value_cents"] / 1e8,
                }
            ],
            caption=_en_es(
                "Exact minimum cut of the block precedence graph at each of the 40 revenue factors.",
                "Corte mínimo exacto del grafo de precedencias de bloques en cada uno de los 40 factores de ingreso.",
            ),
        ),
        _chart(
            inst,
            "e1-strip-ratio-vs-lambda",
            "line",
            _en_es("Strip ratio against revenue factor", "Razón estéril/mineral según el factor de ingreso"),
            method,
            SERVES,
            x_axis=_lambda_axis(),
            y_axis={"label": _en_es("Strip ratio (waste / ore)", "Razón estéril/mineral"), "unit": "t/t"},
            series=[
                {
                    "id": "strip-ratio",
                    "label": _en_es("Strip ratio of the shell", "Razón estéril/mineral del cascarón"),
                    "x": lam_x,
                    "y": [r["strip_ratio"] for r in rows],
                    "n": inst.n_blocks,
                }
            ],
        ),
        _chart(
            inst,
            "e1-shell-table",
            "table",
            _en_es("Shell table", "Tabla de cascarones"),
            method,
            SERVES,
            table={
                "columns": [
                    {
                        "id": "lambda",
                        "label": _en_es("Revenue factor", "Factor de ingreso"),
                        "type": "number",
                        "unit": "1",
                    },
                    {"id": "blocks", "label": _en_es("Blocks", "Bloques"), "type": "number", "unit": "1"},
                    {"id": "ore", "label": _en_es("Ore", "Mineral"), "type": "number", "unit": "Mt"},
                    {"id": "waste", "label": _en_es("Waste", "Estéril"), "type": "number", "unit": "Mt"},
                    {"id": "value", "label": _en_es("Value", "Valor"), "type": "number", "unit": "MUSD"},
                    {
                        "id": "strip",
                        "label": _en_es("Strip ratio", "Razón estéril/mineral"),
                        "type": "number",
                        "unit": "t/t",
                    },
                ],
                "rows": [
                    [
                        r["lambda"],
                        r["block_count"],
                        r["ore_t"] / MILLION,
                        r["waste_t"] / MILLION,
                        r["value_cents"] / 1e8,
                        r["strip_ratio"],
                    ]
                    for r in rows
                ],
            },
        ),
        _chart(
            inst,
            "e1-pushbacks",
            "bar",
            _en_es("Pushback tonnage", "Tonelaje por pushback"),
            "pushback rule on the nested shells (minimum incremental ore tonnage)",
            ["FR-018-16", "FR-017-17"],
            y_axis={"label": _en_es("Incremental tonnage", "Tonelaje incremental"), "unit": "Mt"},
            categories=[
                {"id": f"pushback-{k}", "label": _en_es(f"Pushback {k}", f"Pushback {k}")}
                for k in range(1, len(pushbacks) + 1)
            ],
            series=[
                {
                    "id": "ore",
                    "label": _en_es("Ore", "Mineral"),
                    "y": [pb["ore_t"] / MILLION for pb in pushbacks],
                },
                {
                    "id": "waste",
                    "label": _en_es("Waste", "Estéril"),
                    "y": [pb["waste_t"] / MILLION for pb in pushbacks],
                },
            ],
            caption=_en_es(
                f"A pushback closes when its incremental ore reaches {t_min_t / MILLION:g} Mt.",
                f"Un pushback se cierra cuando su mineral incremental llega a {t_min_t / MILLION:g} Mt.",
            ),
        ),
        _chart(
            inst,
            "e1-sections",
            "section",
            _en_es("Nested pit shells in a central section", "Cascarones anidados en una sección central"),
            method,
            ["FR-018-16", "FR-017-16"],
            x_axis={"label": _en_es("Distance along the section", "Distancia a lo largo de la sección"), "unit": "m"},
            y_axis={"label": _en_es("Height above the deposit base", "Altura sobre la base del depósito"), "unit": "m"},
            section=_section(inst, {lam: table.masks[LAMBDA_GRID.index(lam)] for lam in section_lambdas}),
        ),
    ]
    for chart in charts:
        (out_dir / "charts" / f"{chart['id']}.json").write_text(
            json.dumps(chart, indent=1) + "\n", encoding="utf-8", newline="\n"
        )

    stamped = inst.stamped_pit_value_usd
    ours = final["value_cents"] / 100.0
    tol = 0.005 * rows[-1]["block_count"] + 1e-6
    summary = {
        "kind": "e1-run",
        "case": "E1",
        "label": LABEL,
        "inputs": {
            "deposit": inst.name,
            "archetype": archetype,
            "dims": list(dims),
            "seed": seed,
            "block_size_m": list(inst.block_size_m),
            "n_blocks": inst.n_blocks,
            "n_arcs": len(inst.arcs),
            "slope_deg": inst.slope_deg,
            "economics": econ,
            "block_model_sha256": inst.sha256(),
            "t_min_t": float(t_min_t),
        },
        "versions": {"oreblocks": inst.version, "minephys_pin": MINEPHYS_PIN, "python": platform.python_version()},
        "timing": timing_manifest_entries(records),
        "oracle": {
            "name": "oreblocks exact solver (stamped optimum)",
            "stamped_pit_value_usd": stamped,
            "pit_value_usd": ours,
            "tolerance_usd": tol,
            "agrees": abs(ours - stamped) <= tol,
            "mask_differences": int(np.count_nonzero(table.masks[-1] != inst.stamped_pit_mask)),
        },
        "scheduler": {"status": "not-run", "reason": "the scheduler is outside this run (units and schedule absent)"},
        "pushbacks": len(pushbacks),
        "charts": [c["id"] for c in charts],
    }
    (out_dir / "e1-run.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8", newline="\n")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    import yaml

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("recipe", type=Path, help="a recipe YAML: the params of its first stage are the run parameters")
    p.add_argument("out_dir", type=Path)
    a = p.parse_args(argv)
    params = yaml.safe_load(a.recipe.read_text(encoding="utf-8"))["stages"][0]["params"]
    summary = run_e1(
        a.out_dir,
        archetype=params["archetype"],
        dims=tuple(params["dims"]),
        seed=int(params["seed"]),
        t_min_t=float(params["t_min_t"]),
        section_lambdas=params["section_lambdas"],
    )
    print(json.dumps({k: summary[k] for k in ("oracle", "pushbacks")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
