"""The de Wit archive evidence and the state of the single real event of case C1 (FR-010-12 to FR-010-14, FR-010-27).

``dewit.ingest`` accepts only a series CSV or a map stack with units and a stated failure time. The real ``Data.zip``
holds a Quikslope prism export (``radar-deformation-data``) whose headers carry no unit and whose members state no
failure time. This module records that evidence (member list, the outcome of ``dewit.ingest`` and, for a prism export,
the count, the time span and a unit check of its Diff columns) and turns it into the "not run" state of the real-event
panel. Nothing is guessed: with no failure time there is no t_f, no SNR_obs (FR-010-12 reads the record between t_0 and
t_f) and no forecast number.
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from pathlib import Path
from typing import Any

from pitstudio_pipeline.slope import dewit

LABEL = "single real event — no significance test"
LABEL_ES = "evento real único — sin prueba de significancia"
UNIT_TOLERANCE_MM = 0.1


def _prism_export(name: str, data: bytes) -> dict[str, Any] | None:
    lines = data.decode("utf-8", "replace").splitlines()
    start = next((i for i, line in enumerate(lines[:20]) if line.startswith("Prism,") and "Easting Diff" in line), None)
    if start is None:
        return None
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    rows = [r for r in reader if r.get("Prism")]
    if not rows:
        return None
    prisms = list(dict.fromkeys(r["Prism"] for r in rows))
    first_prism = [r for r in rows if r["Prism"] == prisms[0]]
    try:
        base = float(first_prism[0]["Easting"])
        residual = max(abs(float(r["Easting Diff"]) - 1000.0 * (float(r["Easting"]) - base)) for r in first_prism)
    except ValueError, KeyError:
        residual = float("inf")
    unit = "mm" if residual < UNIT_TOLERANCE_MM else "unknown"
    return {
        "member": name,
        "prisms": len(prisms),
        "rows": len(rows),
        "first": f"{rows[0]['Date']} {rows[0]['Time']}",
        "last": f"{rows[-1]['Date']} {rows[-1]['Time']}",
        "columns": list(rows[0].keys()),
        "units_evidence": {
            "easting_diff_unit": unit,
            "max_abs_residual": residual if residual != float("inf") else None,
            "basis": "Easting Diff compared with 1000 times the change of Easting (metres) over the first prism",
        },
    }


def archive_evidence(archive: str | Path, *, expected_bytes: int, expected_md5: str) -> dict[str, Any]:
    """Checksum, members, the outcome of ``dewit.ingest`` and the prism-export evidence of ``archive``."""
    path = Path(archive)
    raw = path.read_bytes()
    out: dict[str, Any] = {
        "bytes": len(raw),
        "md5": hashlib.md5(raw).hexdigest(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "expected_bytes": expected_bytes,
        "expected_md5": expected_md5,
    }
    out["checksum_ok"] = len(raw) == expected_bytes and out["md5"] == expected_md5
    out["failure_time_in_archive"] = False
    if not out["checksum_ok"]:
        out["members"] = []
        out["ingest"] = {
            "accepted": False,
            "reason": "archive checksum mismatch: size or MD5 differs from the Zenodo record",
        }
        return out
    members: list[dict[str, Any]] = []
    prism: dict[str, Any] | None = None
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for info in z.infolist():
            if info.filename.endswith("/"):
                continue
            entry: dict[str, Any] = {"name": info.filename, "bytes": info.file_size}
            if info.filename.lower().endswith((".csv", ".txt", ".dat")) and info.file_size < 64 * 1024 * 1024:
                data = z.read(info)
                head = next((ln for ln in data.decode("utf-8", "replace").splitlines() if "," in ln or "\t" in ln), "")
                entry["header"] = head[:200]
                if prism is None and info.filename.lower().endswith(".csv"):
                    prism = _prism_export(info.filename, data)
            members.append(entry)
    out["members"] = members
    try:
        series = dewit.ingest(path, expected_bytes=expected_bytes, expected_md5=expected_md5)
        out["ingest"] = {"accepted": True, "reason": None}
        out["failure_time_in_archive"] = series.document["t_f_h"] is not None
    except dewit.DewitRejected as exc:
        out["ingest"] = {"accepted": False, "reason": exc.reason}
    if prism is not None:
        out["prism_export"] = prism
    return out


def real_event_state(evidence: dict[str, Any]) -> dict[str, Any]:
    """The ``real_event`` block of the results: not run, with the reason, the label and no number."""
    state: dict[str, Any] = {
        "event_id": dewit.EVENT_ID,
        "status": "not run",
        "label": LABEL,
        "label_es": LABEL_ES,
        "snr_obs": None,
    }
    if not evidence["checksum_ok"]:
        state["reason"] = "the archive fails its checksum (size or MD5 differs from the Zenodo record)"
    elif not evidence["ingest"]["accepted"]:
        state["reason"] = (
            "the archive states no failure time and its layout (a prism survey export without a displacement unit "
            "in its headers) is not one the ingestion accepts: " + str(evidence["ingest"]["reason"])
        )
    else:
        state["reason"] = "the ingestion accepted the archive but no forecast was run in this unit"
    return state
