"""s05_synthesize (spec 008): the CPU synthetic generators, the studio-output collector and the shared-validator hook.

Every generator is deterministic: the same seed and configuration give byte-identical files (FR-008-38), recorded with
their SHA-256. Every set and every record carries `synthetic: true` (FR-008-33). Studio outputs (SDG images, sensor
clouds, ...) are produced on the GPU side; this stage only collects them by digest and marks a set `not-run` when one is
missing or differs from the studio manifest (FR-008-35).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

from pitstudio_pipeline.download.hashing import sha256_file
from pitstudio_pipeline.ingest import files as ingest_files
from pitstudio_pipeline.ingest.series import validate_series
from pitstudio_pipeline.paths import check_data_root
from pitstudio_pipeline.splits import MAX_SEED
from pitstudio_pipeline.synthesize import physics

STAGE = "s05_synthesize"
GENERATORS = ("des-cycles", "kuz-ram-psd", "voight-creep", "gaussian-plume", "oreblocks", "comminution-sweep")
STOCHASTIC = frozenset({"des-cycles", "voight-creep", "oreblocks"})


@dataclass
class SynthResult:
    """What a generator wrote: the files and their SHA-256 (keyed by POSIX path relative to the data root)."""

    files: list[Path]
    sha256: dict[str, str]
    records: list[dict[str, Any]]
    manifest: dict[str, Any]
    synthetic: bool = True
    config: dict[str, Any] = field(default_factory=dict)


def _json_bytes(obj: Any) -> bytes:
    """Canonical, compact JSON (sorted keys, UTF-8, LF, no NaN): the same object always gives the same bytes."""
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


def _npy_bytes(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, np.ascontiguousarray(array), allow_pickle=False)
    return buffer.getvalue()


# ------------------------------------------------------------------------------------------------------ generators
def _des_cycles(seed: int, config: dict[str, Any]) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    import minehaulsim as mh

    spec = mh.generate_open_pit(None, seed)
    shift = spec.run(None, seed=seed)
    kpis = {"cycles": shift.cycles, "tonnes": shift.tonnes, "truck_wait_s": shift.truck_wait_s}
    events = {"scenario_seed": seed, "events": shift.events, "kpis": kpis, "synthetic": True}
    record = {"id": f"des-cycles-{seed}", "synthetic": True, "scenario_seed": seed, **kpis}
    return {f"shift-{seed}.json": _json_bytes(events)}, [record]


def _kuz_ram_psd(seed: int, config: dict[str, Any]) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    p = {**physics.default_blast(), **config}
    x50 = physics.kuz_ram_x50_cm(
        p["burden_m"], p["spacing_m"], p["bench_m"], p["charge_kg"], p["rock_factor"], p["rws"]
    )
    n = physics.kuz_ram_n(
        p["burden_m"],
        p["spacing_m"],
        p["diameter_mm"],
        p["drill_sd_m"],
        p["bottom_charge_m"],
        p["column_charge_m"],
        p["bench_m"],
    )
    x_max = 100.0 * min(p["spacing_m"], p["burden_m"])  # cm: the largest block a joint-free round can leave
    sizes = np.geomspace(0.1, x_max, 60)
    document = {
        "synthetic": True,
        "x50_cm": x50,
        "uniformity_n": n,
        "x_max_cm": x_max,
        "x_cm": sizes.tolist(),
        "kuz_ram_passing": physics.rosin_rammler_passing(sizes, x50, n).tolist(),
        "swebrec_passing": physics.swebrec_passing(sizes, x50, x_max, p["swebrec_b"]).tolist(),
        "parameters": p,
    }
    return {"psd.json": _json_bytes(document)}, [{"id": "kuz-ram-psd", "synthetic": True, "x50_cm": x50, "n": n}]


def _voight_creep(seed: int, config: dict[str, Any]) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    rng = np.random.default_rng(seed)
    alpha = float(rng.choice([1.6, 1.8, 2.0, 2.2, 2.4]))
    a = float(rng.uniform(0.5, 2.0))
    t_failure = float(rng.uniform(150.0, 400.0))
    samples = int(config.get("samples", 200))
    t = np.linspace(0.0, 0.97 * t_failure, samples)
    clean = physics.voight_displacement(t, alpha, a, t_failure)
    x = clean + rng.normal(0.0, 0.002 * float(clean[-1]), samples)
    record = {
        "id": f"voight-creep-{seed}",
        "synthetic": True,
        "event_seed": seed,
        "alpha": alpha,
        "a": a,
        "t_failure": t_failure,
        "t": t.tolist(),
        "x": x.tolist(),
    }
    return {f"series-{seed}.json": _json_bytes(record)}, [record]


def _gaussian_plume(seed: int, config: dict[str, Any]) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    x = np.arange(50.0, 2050.0, 50.0)
    y = np.arange(-300.0, 301.0, 15.0)
    field_ = physics.plume_ground_concentration(
        x,
        y,
        float(config.get("emission_g_s", 1.0)),
        float(config.get("wind_m_s", 3.0)),
        float(config.get("height_m", 10.0)),
    )
    files = {"concentration.npy": _npy_bytes(field_), "grid.json": _json_bytes({"x_m": x.tolist(), "y_m": y.tolist()})}
    return files, [{"id": "gaussian-plume", "synthetic": True, "peak_g_m3": float(field_.max())}]


def _oreblocks(seed: int, config: dict[str, Any]) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    import oreblocks as ob

    grid = ob.BlockGrid(int(config.get("nx", 12)), int(config.get("ny", 12)), int(config.get("nz", 6)))
    deposit = ob.make_deposit(grid, str(config.get("archetype", "porphyry")), seed)
    files = {"grade.npy": _npy_bytes(deposit.grade), "density.npy": _npy_bytes(deposit.density)}
    record = {"id": f"oreblocks-{seed}", "synthetic": True, "scene_seed": seed, "blocks": int(deposit.grade.size)}
    return files, [record]


def _comminution_sweep(seed: int, config: dict[str, Any]) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    f80 = float(config.get("f80_um", 12_500.0))
    rows = [
        {"work_index_kwh_t": wi, "p80_um": p80, "energy_kwh_t": physics.bond_energy_kwh_t(wi, p80, f80)}
        for wi in (8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0)
        for p80 in (75.0, 106.0, 150.0, 212.0, 300.0, 425.0)
    ]
    return {"sweep.json": _json_bytes({"synthetic": True, "f80_um": f80, "rows": rows})}, [
        {"id": "comminution-sweep", "synthetic": True, "rows": len(rows)}
    ]


_GENERATORS: dict[str, Callable[[int, dict[str, Any]], tuple[dict[str, bytes], list[dict[str, Any]]]]] = {
    "des-cycles": _des_cycles,
    "kuz-ram-psd": _kuz_ram_psd,
    "voight-creep": _voight_creep,
    "gaussian-plume": _gaussian_plume,
    "oreblocks": _oreblocks,
    "comminution-sweep": _comminution_sweep,
}


def run(
    generator: str,
    *,
    seed: int,
    config: Mapping[str, Any] | None = None,
    data_root: Path | str,
    repo_root: Path | str | None = None,
    now: Callable[[], dt.datetime] | None = None,
) -> SynthResult:
    """Run one CPU generator; files go to `<data_root>/synthetic/<generator>/`.

    `config=None` means the generator's documented defaults. Same seed and configuration: same bytes (FR-008-38).
    """
    if generator not in _GENERATORS:
        raise ValueError(f"unknown generator {generator!r}; known: {', '.join(GENERATORS)}")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError(f"the seed must be an integer, not {type(seed).__name__}")
    if not 0 <= seed <= MAX_SEED:
        raise ValueError(f"the seed must be in 0 ... {MAX_SEED}")
    root = check_data_root(data_root, repo_root=repo_root)
    settings = dict(config or {})
    contents, records = _GENERATORS[generator](seed, settings)
    folder = root / "synthetic" / generator
    folder.mkdir(parents=True, exist_ok=True)
    files, digests = [], {}
    for name, data in contents.items():
        path = folder / name
        path.write_bytes(data)
        files.append(path)
        digests[path.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
    manifest = {
        "stage": STAGE,
        "generator": generator,
        "seed": seed,
        "config_sha256": hashlib.sha256(_json_bytes(settings)).hexdigest(),
        "determinism": {"class": "bitwise"},
        "stochastic": generator in STOCHASTIC,
        "files": digests,
        "synthetic": True,
    }
    return SynthResult(files=files, sha256=digests, records=records, manifest=manifest, config=settings)


# ------------------------------------------------------------------------------------------------ studio outputs
def _not_run(reason: str) -> dict[str, Any]:
    return {"status": "not-run", "reason": reason, "sha256": None, "path": None}


def _safe_member(path: str) -> bool:
    posix = path.replace("\\", "/")
    parts = PurePosixPath(posix).parts
    drive = len(posix) > 1 and posix[1] == ":"
    return bool(posix) and not posix.startswith("/") and not drive and ".." not in parts


def collect_studio_outputs(
    studio_manifest: Path | str, outputs_dir: Path | str, *, needed: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """Collect the studio outputs named in `needed` by digest; a missing or changed output makes only its set `not-run`.

    `studio_manifest` is a JSON file `{"artefacts": [{"id", "path", "sha256", "bytes"}]}` with paths relative to
    `outputs_dir`. Nothing is created or substituted for a set that is not collected (FR-008-35).
    """
    outputs = Path(outputs_dir)
    try:
        document = json.loads(Path(studio_manifest).read_bytes().decode("utf-8"))
        artefacts = {a["id"]: a for a in document["artefacts"] if isinstance(a, dict) and "id" in a}
    except OSError, ValueError, KeyError, TypeError:
        return {i: _not_run("the studio manifest is missing or unreadable") for i in needed}
    result: dict[str, dict[str, Any]] = {}
    for artefact_id in needed:
        entry = artefacts.get(artefact_id)
        if entry is None:
            result[artefact_id] = _not_run(f"{artefact_id} is not in the studio manifest")
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not _safe_member(path):
            result[artefact_id] = _not_run(f"the manifest path of {artefact_id} is not inside the outputs folder")
            continue
        target = outputs / PurePosixPath(path.replace("\\", "/"))
        if not target.is_file():
            result[artefact_id] = _not_run(f"the output file of {artefact_id} is missing")
            continue
        digest = sha256_file(target)
        if digest != entry.get("sha256") or (
            entry.get("bytes") is not None and target.stat().st_size != entry["bytes"]
        ):
            result[artefact_id] = _not_run(f"the output of {artefact_id} differs from its studio manifest digest")
            continue
        result[artefact_id] = {"status": "collected", "reason": None, "sha256": digest, "path": path}
    return result


# ------------------------------------------------------------------------- the shared validators of real data
def validate_set(set_type: str, subject: Any, **kw: Any) -> None:
    """Pass a synthetic set through the validator of its real counterpart (FR-008-34); same verdict, same violations."""
    if set_type == "muck-pile-masks":
        return ingest_files.validate_mask(subject, **kw)
    if set_type == "procedural-terrain":
        return ingest_files.validate_raster(subject, **kw)
    if set_type == "voight-creep-series":
        return validate_series(subject["t"], subject["x"], **kw)
    raise ValueError(f"no real-data validator for the set type {set_type!r}")


__all__ = ["GENERATORS", "SynthResult", "collect_studio_outputs", "run", "validate_set"]
