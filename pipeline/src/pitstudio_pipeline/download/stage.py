"""`s00_download`: fetch every registered source, verify it against its pin, record where each byte came from."""

from __future__ import annotations

import datetime as dt
import logging
import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from pitstudio_pipeline.download.hashing import md5_file, sha256_file
from pitstudio_pipeline.download.http import HttpxDownloader
from pitstudio_pipeline.download.names import local_name
from pitstudio_pipeline.download.registry import load_registry
from pitstudio_pipeline.errors import ChecksumMismatch, InsufficientDisk, PublisherChecksumMismatch, UnpinnedSource
from pitstudio_pipeline.paths import find_repo_root, resolve_data_root

log = logging.getLogger("pitstudio_pipeline.download")
RECORD_SCHEMA_VERSION = "1.0"


@dataclass
class DownloadResult:
    """What a run did. `records` are fetch records (DC-008-02), one per registry file, in registry order."""

    exit_status: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)
    errors: dict[str, Exception] = field(default_factory=dict)
    unavailable: list[str] = field(default_factory=list)
    not_run: dict[str, str] = field(default_factory=dict)
    complete: dict[str, bool] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)


def _utc_text(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record(entry: Mapping[str, Any], file: Mapping[str, Any], name: str, **over: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "source": entry["id"],
        "name": name,
        "url": file["url"],
        "final_url": None,
        "stored_as": None,
        "bytes": None,
        "expected_bytes": file.get("bytes"),
        "sha256": None,
        "expected_sha256": file.get("sha256"),
        "publisher_checksum": file.get("publisher_checksum"),
        "publisher_checksum_status": "not-declared" if not file.get("publisher_checksum") else "not-checked",
        "spdx": file.get("spdx", entry["spdx"]),
        "licence_class": entry["licence_class"],
        "redistribution": entry["redistribution"],
        "retrieved": None,
        "status": "unavailable",
        "fallback_sources": [],
        "attempts": 0,
    }
    record.update(over)
    return record


def run_download(
    registry_path: Path | str | None = None,
    data_root: Path | str | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    env: Mapping[str, str] | None = None,
    now: Callable[[], dt.datetime] | None = None,
    sleep: Callable[[float], None] | None = None,
    schema_path: Path | str | None = None,
    repo_root: Path | str | None = None,
    pin: bool = False,
    publishable: bool = False,
    pins_dir: Path | str | None = None,
    free_disk: Callable[[Path], int] | None = None,
) -> DownloadResult:
    """Run `s00_download` over the registry; see `DownloadResult` for what comes back."""
    environment = dict(os.environ) if env is None else dict(env)
    repo = Path(repo_root) if repo_root is not None else find_repo_root()
    root = resolve_data_root(data_root, environment, repo)
    registry = load_registry(
        Path(registry_path) if registry_path is not None else repo / "data" / "sources.yaml", schema_path=schema_path
    )
    _refuse_unpinned(registry, pin=pin, publishable=publishable)
    clock = now if now is not None else (lambda: dt.datetime.now(dt.UTC))
    result = DownloadResult()
    pins = Path(pins_dir) if pins_dir is not None else repo / "data" / "pins"
    downloader = HttpxDownloader(transport, sleep=sleep)
    try:
        for entry in registry["sources"]:
            _run_entry(entry, root, downloader, clock, result, pin=pin, pins_dir=pins, free_disk=free_disk or _free)
    finally:
        downloader.close()
    result.manifest = {
        "stage": "s00_download",
        "unpublishable": any(r["status"] == "pin-proposed" for r in result.records),
    }
    result.exit_status = 0 if not result.errors else 1
    return result


def _refuse_unpinned(registry: Mapping[str, Any], *, pin: bool, publishable: bool) -> None:
    """FR-008-08: a file without a pinned SHA-256 needs `--pin`, and a publishable run never uses one."""
    unpinned = sorted(
        {entry["id"] for entry in registry["sources"] for file in entry["files"] if file.get("sha256") is None}
    )
    if unpinned and (publishable or not pin):
        why = "a publishable run uses pinned files only" if publishable else "run with --pin to propose a pin"
        raise UnpinnedSource(f"source(s) without a pinned sha256: {', '.join(unpinned)} ({why})")


def _free(path: Path) -> int:
    return shutil.disk_usage(path).free


def _check_disk(base: Path, file: Mapping[str, Any], free_disk: Callable[[Path], int]) -> None:
    """FR-008-10: refuse to start a file when the free space is below 1.2 x (bytes + uncompressed bytes)."""
    need = (file.get("bytes") or 0) + (file.get("uncompressed_bytes") or 0)
    probe = base
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    free = free_disk(probe)
    if free * 5 < need * 6:  # free < 1.2 x need, in integers
        raise InsufficientDisk(f"{free} bytes free, {need * 6 // 5} needed (1.2 x {need}) for {file['url']}")


def _quarantine(path: Path, root: Path, source: str, name: str) -> Path:
    """Move a file that failed verification to `quarantine/<id>/<name>` (FR-008-06)."""
    target = root / "quarantine" / source / name
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(path, target)
    return target


def _publisher_status(path: Path, file: Mapping[str, Any], digest: str) -> str:
    """Compare the file with the checksum its publisher states (`md5:<hex>` or `sha256:<hex>`): `match`, `mismatch`,
    `not-declared`."""
    declared = file.get("publisher_checksum")
    if not declared:
        return "not-declared"
    algorithm, _, expected = declared.partition(":")
    actual = digest if algorithm == "sha256" else md5_file(path)
    return "match" if actual == expected else "mismatch"


def _verify(path: Path, entry: Mapping[str, Any], file: Mapping[str, Any], name: str) -> tuple[str, int, str]:
    """(sha256, bytes, publisher status) of `path`; raise `ChecksumMismatch` when it differs from the pin."""
    digest, size = sha256_file(path), path.stat().st_size
    if file.get("sha256") is None:  # an unpinned file (`--pin`): the digest is proposed, not compared
        return digest, size, _publisher_status(path, file, digest)
    if digest != file.get("sha256") or size != file.get("bytes"):
        raise ChecksumMismatch(
            entry["id"],
            name,
            expected_sha256=file.get("sha256"),
            actual_sha256=digest,
            expected_bytes=file.get("bytes"),
            actual_bytes=size,
        )
    return digest, size, _publisher_status(path, file, digest)


def _run_entry(
    entry: Mapping[str, Any],
    root: Path,
    downloader: HttpxDownloader,
    clock: Callable[[], dt.datetime],
    result: DownloadResult,
    *,
    pin: bool,
    pins_dir: Path,
    free_disk: Callable[[Path], int],
) -> None:
    proposals: list[dict[str, Any]] = []
    folder = "raw" if entry["access"] in ("direct", "api") else "external"
    complete = True
    for file in entry["files"]:
        name = "unsafe-name"  # replaced as soon as the local name passed FR-008-11
        fetched = None
        try:
            name = local_name(file["url"], file.get("name"))
            target = root / folder / entry["id"] / name
            part = target.with_name(target.name + ".part")
            if target.exists():  # a cached file is re-verified before it is reused (FR-008-05)
                digest, size, publisher = _verify_cached(target, root, entry, file, name)
            elif entry["access"] == "manual":
                result.records.append(_record(entry, file, name))
                complete = False
                continue
            else:
                _check_disk(root / folder, file, free_disk)
                target.parent.mkdir(parents=True, exist_ok=True)
                fetched = downloader.fetch(file["url"], part, max_bytes=file.get("bytes"))
                digest, size, publisher = _verify_part(part, root, entry, file, name)
                os.replace(part, target)
        except Exception as exc:
            result.errors.setdefault(entry["id"], exc)
            result.records.append(_failure_record(entry, file, name, exc))
            complete = False
            break
        proposed = file.get("sha256") is None
        if proposed:
            proposals.append({"url": file["url"], "name": name, "sha256": digest, "bytes": size})
        result.records.append(
            _record(
                entry,
                file,
                name,
                final_url=fetched.final_url if fetched else file["url"],
                stored_as=f"{folder}/{entry['id']}/{name}",
                bytes=size,
                sha256=digest,
                retrieved=_utc_text(clock()),
                status="pin-proposed" if proposed else "verified",
                attempts=fetched.attempts if fetched else 0,
                publisher_checksum_status=publisher,
            )
        )
    if proposals and entry["id"] not in result.errors:
        _write_proposal(pins_dir, entry["id"], proposals)
    result.complete[entry["id"]] = complete and not proposals


def _write_proposal(pins_dir: Path, source: str, files: list[dict[str, Any]]) -> None:
    """`<pins_dir>/<id>.proposed.yaml` for the maintainer to review; the registry itself is never edited (FR-008-07)."""
    pins_dir.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump({"source": source, "files": files}, sort_keys=False, allow_unicode=True)
    (pins_dir / f"{source}.proposed.yaml").write_bytes(text.encode("utf-8"))


def _verify_cached(target: Path, root: Path, entry: Mapping[str, Any], file: Mapping[str, Any], name: str):
    try:
        return _verify_or_raise(target, entry, file, name)
    except ChecksumMismatch, PublisherChecksumMismatch:
        _quarantine(target, root, entry["id"], name)
        raise


def _verify_part(part: Path, root: Path, entry: Mapping[str, Any], file: Mapping[str, Any], name: str):
    try:
        return _verify_or_raise(part, entry, file, name)
    except ChecksumMismatch, PublisherChecksumMismatch:
        _quarantine(part, root, entry["id"], name)
        raise


def _verify_or_raise(path: Path, entry: Mapping[str, Any], file: Mapping[str, Any], name: str):
    digest, size, publisher = _verify(path, entry, file, name)
    if publisher == "mismatch":
        raise PublisherChecksumMismatch(f"{entry['id']}/{name}: the publisher checksum differs from the computed one")
    return digest, size, publisher


def _failure_record(entry: Mapping[str, Any], file: Mapping[str, Any], name: str, exc: Exception) -> dict[str, Any]:
    over: dict[str, Any] = {"attempts": getattr(exc, "attempts", 0)}
    if isinstance(exc, ChecksumMismatch):
        over.update(sha256=exc.actual_sha256, bytes=exc.actual_bytes)
    if isinstance(exc, PublisherChecksumMismatch):
        over.update(publisher_checksum_status="mismatch")
    return _record(entry, file, name, **over)
