"""Registry loader: the whole `data/sources.yaml` is validated before any connection (FR-008-01, FR-008-02)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from pitstudio.contracts.io import ContractError, load_yaml
from pitstudio.contracts.sources import SOURCES_MAX_BYTES, TOO_PERMISSIVE, too_permissive_entries
from pitstudio.contracts.validate import CONTRACTS_DIR, validate
from pitstudio_pipeline.errors import RegistryError, RegistryViolation

SHARE_ALIKE_SPDX = frozenset({"CC-BY-SA-3.0", "CC-BY-SA-4.0"})


def _entry_id(registry: Any, pointer: str) -> str | None:
    parts = pointer.split("/")
    if len(parts) >= 3 and parts[1] == "sources" and parts[2].isdigit() and isinstance(registry, dict):
        entries = registry.get("sources")
        index = int(parts[2])
        if isinstance(entries, list) and index < len(entries) and isinstance(entries[index], dict):
            ident = entries[index].get("id")
            return ident if isinstance(ident, str) else None
    return None


def _schema_violations(registry: Any, schema_path: Path | None) -> list[tuple[str, str]]:
    """(pointer, rule) of every schema and post-schema violation (data-model 1.3 of spec 001)."""
    if schema_path is None or Path(schema_path).resolve() == (CONTRACTS_DIR / "sources.schema.json").resolve():
        return [(e.pointer, f"{e.keyword}: {e.message}") for e in validate(registry, "sources")]
    # another schema file (a draft under test or a promoted revision): the same jsonschema engine, no post-schema rules
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    out = []
    for error in Draft202012Validator(schema).iter_errors(registry):
        pointer = "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in error.absolute_path)
        out.append((pointer, f"{error.validator}: {error.message[:200]}"))
    return sorted(out)


def _cross_entry_violations(registry: Any) -> list[tuple[str, str]]:
    """Rules a schema cannot state (FR-001-52, -58): fallback ids, mixed share-alike, class below a file's class."""
    out: list[tuple[str, str]] = []
    entries = registry.get("sources") if isinstance(registry, dict) else None
    if not isinstance(entries, list):
        return out
    ids = {e["id"] for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        base = f"/sources/{index}"
        fallback = entry.get("fallback")
        sources = fallback.get("sources") if isinstance(fallback, dict) else None
        for position, other in enumerate(sources if isinstance(sources, list) else []):
            if other == entry.get("id"):
                out.append((f"{base}/fallback/sources/{position}", "fallback-self: a fallback names the entry itself"))
            elif isinstance(other, str) and other not in ids:
                out.append((f"{base}/fallback/sources/{position}", f"fallback-unknown: {other} is not a registry id"))
        files = [f for f in entry.get("files") or [] if isinstance(f, dict)]
        spdx = {f.get("spdx", entry.get("spdx")) for f in files} or {entry.get("spdx")}
        spdx.discard(None)
        if spdx & SHARE_ALIKE_SPDX and len(spdx) > 1:
            out.append((f"{base}/files", "share-alike-mixed: a share-alike id is mixed with another id in one entry"))
    for index, _, message in too_permissive_entries(registry):
        out.append((f"/sources/{index}", f"{TOO_PERMISSIVE}: {message}"))
    return out


def load_registry(path: Path | str, *, schema_path: Path | str | None = None) -> dict[str, Any]:
    """Parse the YAML registry and validate the whole document; raise `RegistryError` listing every violation."""
    path = Path(path)
    try:
        registry = load_yaml(path, max_bytes=SOURCES_MAX_BYTES)
    except ContractError as exc:
        raise RegistryError([RegistryViolation(None, "", f"unreadable: {exc.reason}")]) from None
    found = _schema_violations(registry, Path(schema_path) if schema_path is not None else None)
    found.extend(_cross_entry_violations(registry))
    if found:
        seen: set[tuple[str, str]] = set()
        violations = []
        for pointer, rule in sorted(found):
            if (pointer, rule) not in seen:
                seen.add((pointer, rule))
                violations.append(RegistryViolation(_entry_id(registry, pointer), pointer, rule))
        raise RegistryError(violations)
    assert isinstance(registry, dict)
    return registry
