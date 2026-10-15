"""Terrain sources: which of the sources a recipe lists actually run, and the licence records of the scene manifest
(FR-004-09)."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitstudio.contracts.licence import source_class_of

OPENTOPOGRAPHY_KEY = "OPENTOPOGRAPHY_API_KEY"
KEYED_SOURCES = {"ot-mckinley-2023": OPENTOPOGRAPHY_KEY}  # source id -> environment variable holding its API key
MAX_REASON = 256  # DC-004-02 `sources[].reason`

# Licence facts of the scene's sources, used until the data pipeline (spec 008) registers them in data/sources.yaml.
# `attribution` may use {project}. Classes are derived from the SPDX id with the registry rules (contracts.licence).
KNOWN_SOURCES: dict[str, dict[str, Any]] = {
    "usgs-3dep-bingham": {
        "role": "terrain",
        "spdx": "LicenseRef-USGov-PD",
        "attribution": "Elevation data: U.S. Geological Survey, 3D Elevation Program (3DEP), project {project}.",
    },
    "ot-mckinley-2023": {
        "role": "terrain",
        "spdx": "CC-BY-4.0",
        "attribution": "Lidar data: OpenTopography, McKinley 2023 survey.",
    },
    "nrw-hambach-dgm1": {
        "role": "terrain",
        "spdx": "DL-DE-ZERO-2.0",
        "attribution": "Elevation data: Land NRW, Digitales Gelaendemodell DGM1 (dl-de/zero-2-0).",
    },
    "polyhaven": {"role": "texture", "spdx": "CC0-1.0", "attribution": "Textures: Poly Haven (CC0)."},
    "ambientcg": {"role": "texture", "spdx": "CC0-1.0", "attribution": "Textures: ambientCG (CC0)."},
}


@dataclass(frozen=True)
class SourceStatus:
    """One source of a recipe: used, or not run with a one-line reason (the DC-004-02 `sources[].status` values)."""

    id: str
    status: str
    reason: str | None = None


def resolve_sources(
    spec: Mapping[str, Any], *, env: Mapping[str, str] | None, available: Mapping[str, Sequence[Any]]
) -> list[SourceStatus]:
    """One status per source listed in `spec["terrain"]["sources"]`, in order.

    A source with `optional: true` is used only when its data is present and, for a keyed source (OpenTopography), its
    environment variable holds a non-empty value; the reason never contains the key. A required source without data is
    reported `not_run` too, and the stage then fails on it.
    """
    env = os.environ if env is None else env
    out: list[SourceStatus] = []
    for source in spec["terrain"]["sources"]:
        sid = source["id"]
        key_name = KEYED_SOURCES.get(sid)
        has_data = bool(available.get(sid))
        if source.get("optional") and key_name and not str(env.get(key_name, "")).strip():
            out.append(
                SourceStatus(sid, "not_run", f"OpenTopography API key not configured ({key_name} is empty or unset)")
            )
        elif not has_data:
            out.append(SourceStatus(sid, "not_run", "data not fetched: no input files for this source"))
        else:
            out.append(SourceStatus(sid, "used"))
    return out


def source_record(
    source: Mapping[str, Any], status: SourceStatus, registry: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The DC-004-02 `sources[]` entry of a terrain source; licence facts come from the registry, else
    `KNOWN_SOURCES`."""
    sid = source["id"]
    entry = next((e for e in (registry or {}).get("sources", []) if e.get("id") == sid), None)
    known = KNOWN_SOURCES.get(sid, {})
    spdx = (entry or {}).get("spdx") or known.get("spdx", "LicenseRef-Unregistered")
    record: dict[str, Any] = {
        "id": sid,
        "role": "terrain",
        "spdx": spdx,
        "licence_class": (entry or {}).get("licence_class") or source_class_of(spdx, "real") or "reference-only",
        "redistribution": (entry or {}).get("redistribution", "redistributable" if known else "no-redistribution"),
        "attribution": (entry or {}).get("attribution")
        or known.get("attribution", "Attribution pending data registry entry").format(
            project=source.get("project", "")
        ),
        "project": source["project"],
        "epoch": int(source["epoch"]),
        "status": status.status,
    }
    if status.status == "not_run":
        record["reason"] = (status.reason or "not run")[:MAX_REASON]
    return record


def load_registry(root: Path | None = None) -> dict[str, Any]:
    """`data/sources.yaml` of the repository as a mapping (an empty registry when it cannot be read)."""
    import yaml

    path = (root or Path(__file__).resolve().parents[5]) / "data" / "sources.yaml"
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError, yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}
