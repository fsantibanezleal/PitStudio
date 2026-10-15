"""Static-stability stage of case C1 (`s20_feature_extraction`, geotech): FoS and PoF tables (DC-010-04)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pitstudio.slope import lem, pof, results


def analyse(sections: Sequence[dict[str, Any]], *, mode: str | None = None) -> dict[str, Any]:
    """The slope-results document: FoS by every requested method and the PoF when the section asks for it."""
    rows = []
    for doc in sections:
        entry: dict[str, Any] = {"section_id": doc["section_id"], "section_sha256": results.section_digest(doc)}
        entry["fos"] = lem.analyse_section(doc)["fos"]
        if doc["analysis"].get("pof") is not None:
            entry["pof"] = pof.probability_of_failure(doc)
        rows.append(entry)
    return {"schema_version": "1.0", "mode": mode or sections[0]["analysis"]["mode"], "sections": rows}
