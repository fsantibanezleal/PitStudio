"""Asset licence guard and people-asset ingest of `st55_sdg` (FR-009-10, FR-009-11, FR-009-12).

Every asset of an SDG scene needs a licence record and must not come from an `omniverse://` URL or from a vendor asset
root. People come from MakeHuman export records (DC-009-04: official zip pinned by SHA-256, bundled system assets only,
export settings) or, when no valid record remains, from the procedural mannequin generator.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pitstudio_studio.sdg._schemas import best_error

_PEOPLE_SCHEMA = "people-asset-record"
MAKEHUMAN_LICENCE_TEXT = (
    "People source: MakeHuman 1.3.0 official release; the bundled system assets and the exported characters are "
    "released under the licence CC0-1.0 (SPDX identifier)."
)
MANNEQUIN_LICENCE_TEXT = (
    "People source: the procedural mannequin generator of this repository (own data), licence CC-BY-4.0 (SPDX identifier)."
)


class AssetLicenceError(Exception):
    """One or more assets of an SDG scene are refused (error code `asset-licence`); `paths` lists every one."""

    code = "asset-licence"

    def __init__(self, paths: Sequence[str]) -> None:
        self.paths = tuple(paths)
        super().__init__(f"{self.code}: {len(self.paths)} asset path(s) refused: " + "; ".join(repr(p) for p in self.paths))


class AssetDigestError(Exception):
    """The SHA-256 of an exported people file differs from its record (`asset-digest-mismatch`): the file is not used."""

    code = "asset-digest-mismatch"

    def __init__(self, character_id: str, expected: str, actual: str) -> None:
        self.character_id, self.expected, self.actual = character_id, expected, actual
        super().__init__(f"{self.code}: record {character_id}: the file has SHA-256 {actual}, the record states {expected}")


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_DRIVE = re.compile(r"^[A-Za-z]:")


def verify_export_digest(record: Mapping[str, Any], root: Path) -> Path:
    """Path of the record's exported file below `root` when its SHA-256 equals `export_sha256`; else `AssetDigestError`.

    The file is read in full, in blocks, and never executed or imported.
    """
    rel = record.get("export_path")
    if not isinstance(rel, str) or rel == "" or rel.startswith(("/", "\\")) or "\\" in rel or _DRIVE.match(rel) or ".." in rel.split("/"):
        raise ValueError(f"export_path {rel!r} must be a relative path without '..', a drive letter or a backslash")
    expected = record.get("export_sha256")
    if not isinstance(expected, str) or not _HEX64.match(expected):
        raise ValueError(f"export_sha256 must be 64 lower-case hex characters, got {expected!r}")
    path = Path(root) / rel
    digest = hashlib.sha256()
    with path.open("rb") as handle:  # FileNotFoundError when absent
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != expected:
        raise AssetDigestError(str(record.get("character_id")), expected, actual)
    return path


def _norm(path: str) -> str:
    return posixpath.normpath(path.replace("\\", "/"))


def _under_root(path: str, roots: Sequence[str]) -> bool:
    norm = _norm(path)
    for root in roots:
        r = _norm(root)
        if norm == r or norm.startswith(r.rstrip("/") + "/"):
            return True
    return False


def _has_licence(path: str, records: Mapping[str, Mapping[str, object]]) -> bool:
    record = records.get(path)
    if not isinstance(record, Mapping):
        return False
    spdx = record.get("spdx")
    return isinstance(spdx, str) and spdx != ""


def check_scene_assets(
    asset_paths: Sequence[str],
    *,
    licence_records: Mapping[str, Mapping[str, object]],
    vendor_roots: Sequence[str],
) -> None:
    """Raise `AssetLicenceError` listing every offending asset path; return `None` when all are clean.

    An asset is offending when it is an `omniverse://` URL, resolves to or below a vendor asset root, has no licence
    record with a usable SPDX id, or is the empty string. Each offending path is listed once, in input order.
    """
    offending: list[str] = []
    for path in asset_paths:
        if path in offending:
            continue
        bad = (
            path == ""
            or path.lower().startswith("omniverse://")
            or _under_root(path, vendor_roots)
            or not _has_licence(path, licence_records)
        )
        if bad:
            offending.append(path)
    if offending:
        raise AssetLicenceError(offending)


@dataclass(frozen=True)
class Rejection:
    """A rejected people record: its character id (when readable), the JSON pointer of the error and the reason."""

    character_id: str | None
    pointer: str
    reason: str


@dataclass(frozen=True)
class PeopleSelection:
    """The people source chosen for the SDG scenes, the valid records of that source and every rejected record."""

    people_source: Literal["makehuman", "mannequins"]
    characters: tuple[dict[str, Any], ...]
    rejected: tuple[Rejection, ...]
    licence_text: str


def select_people(
    records: Sequence[object], *, pinned_zip_sha256: str, root: Path | None = None
) -> PeopleSelection:
    """Validate the people records and choose the source: MakeHuman if one valid record remains, else mannequins.

    A MakeHuman record is valid when it satisfies the DC-009-04 schema and its zip SHA-256 equals
    `pinned_zip_sha256`; one `Rejection` is made per bad record (the first schema error, else the digest mismatch).
    With `root`, every such record's exported file must also exist and match `export_sha256` (FR-009-49).
    """
    makehuman: list[dict[str, Any]] = []
    mannequins: list[dict[str, Any]] = []
    rejected: list[Rejection] = []
    for record in records:
        if not isinstance(record, Mapping):
            rejected.append(Rejection(None, "", "the record is not an object"))
            continue
        cid = record.get("character_id")
        character_id = cid if isinstance(cid, str) else None
        source = record.get("source")
        if source not in ("makehuman", "mannequin"):
            rejected.append(Rejection(character_id, "/source", "source must be 'makehuman' or 'mannequin'"))
            continue
        # the record's own `source` picks the branch of the schema's oneOf, so the error comes from that branch
        first = best_error(_PEOPLE_SCHEMA, record, source)
        if first is not None:
            rejected.append(Rejection(character_id, first[0], first[1]))
            continue
        if record["source"] == "makehuman" and record["zip_sha256"] != pinned_zip_sha256:
            rejected.append(
                Rejection(character_id, "/zip_sha256", "the zip SHA-256 differs from the pinned value of the official zip")
            )
            continue
        if root is not None:
            try:
                verify_export_digest(record, root)
            except AssetDigestError as exc:
                rejected.append(Rejection(character_id, "/export_sha256", str(exc)))
                continue
            except FileNotFoundError:
                rejected.append(Rejection(character_id, "/export_sha256", f"the export file {record['export_path']} is missing"))
                continue
        (makehuman if record["source"] == "makehuman" else mannequins).append(dict(record))
    if makehuman:
        return PeopleSelection("makehuman", tuple(makehuman), tuple(rejected), MAKEHUMAN_LICENCE_TEXT)
    return PeopleSelection("mannequins", tuple(mannequins), tuple(rejected), MANNEQUIN_LICENCE_TEXT)
