"""`s00_download`: fetch every registered source, verify it against its pin, record where each byte came from."""

from __future__ import annotations

import datetime as dt
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from pitstudio_pipeline.download.hashing import sha256_file
from pitstudio_pipeline.download.http import HttpxDownloader
from pitstudio_pipeline.download.names import local_name
from pitstudio_pipeline.download.registry import load_registry
from pitstudio_pipeline.errors import ChecksumMismatch
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
) -> DownloadResult:
    """Run `s00_download` over the registry; see `DownloadResult` for what comes back."""
    environment = dict(os.environ) if env is None else dict(env)
    repo = Path(repo_root) if repo_root is not None else find_repo_root()
    root = resolve_data_root(data_root, environment, repo)
    registry = load_registry(
        Path(registry_path) if registry_path is not None else repo / "data" / "sources.yaml", schema_path=schema_path
    )
    clock = now if now is not None else (lambda: dt.datetime.now(dt.UTC))
    result = DownloadResult()
    downloader = HttpxDownloader(transport, sleep=sleep)
    try:
        for entry in registry["sources"]:
            _run_entry(entry, root, downloader, clock, result)
    finally:
        downloader.close()
    result.exit_status = 0 if not result.errors else 1
    return result


def _run_entry(
    entry: Mapping[str, Any],
    root: Path,
    downloader: HttpxDownloader,
    clock: Callable[[], dt.datetime],
    result: DownloadResult,
) -> None:
    folder = "raw" if entry["access"] in ("direct", "api") else "external"
    complete = True
    for file in entry["files"]:
        name = local_name(file["url"], file.get("name"))
        target_dir = root / folder / entry["id"]
        target = target_dir / name
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + ".part")
            fetched = downloader.fetch(file["url"], part, max_bytes=file.get("bytes"))
            digest, size = sha256_file(part), part.stat().st_size
            if digest != file.get("sha256") or size != file.get("bytes"):
                part.unlink(missing_ok=True)
                raise ChecksumMismatch(
                    entry["id"],
                    name,
                    expected_sha256=file.get("sha256"),
                    actual_sha256=digest,
                    expected_bytes=file.get("bytes"),
                    actual_bytes=size,
                )
            os.replace(part, target)
        except Exception as exc:
            result.errors.setdefault(entry["id"], exc)
            result.records.append(_record(entry, file, name))
            complete = False
            break
        result.records.append(
            _record(
                entry,
                file,
                name,
                final_url=fetched.final_url,
                stored_as=f"{folder}/{entry['id']}/{name}",
                bytes=size,
                sha256=digest,
                retrieved=_utc_text(clock()),
                status="verified",
                attempts=fetched.attempts,
                publisher_checksum_status="not-declared" if not file.get("publisher_checksum") else "not-checked",
            )
        )
    result.complete[entry["id"]] = complete
