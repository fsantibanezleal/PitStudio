"""Resumable HTTPS downloader on httpx with a classified retry ladder (FR-008-10, FR-008-11, FR-008-12).

`pooch` verifies and caches but cannot resume a transfer, so the transfer itself is this downloader. It follows the
pooch downloader protocol (`__call__(url, output_file, pooch, check_only=False)`), so pooch can drive it, while the
stage calls `fetch` directly: it needs the quarantine and per-file bookkeeping that pooch's delete-on-mismatch lacks.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from pitstudio_pipeline.errors import DownloadFailed, InsecureRedirect, Oversize

log = logging.getLogger("pitstudio_pipeline.download")
BACKOFFS_S = (1, 2, 4, 8, 16)  # FR-008-12: up to five retries
MAX_ATTEMPTS = len(BACKOFFS_S) + 1
MAX_REDIRECTS = 10
MAX_UNPINNED_BYTES = 64 * (
    1 << 30
)  # the registry's size bound (spec 001 data-model 5.1.1) caps a file with unknown size
REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


@dataclass
class Fetched:
    """Outcome of a completed transfer: the URL the bytes came from and the number of tries it took."""

    final_url: str
    attempts: int


class _Retry(Exception):
    """Internal: this try failed in a way the ladder retries."""


class _Restart(Exception):
    """Internal: discard the partial file and start again at once (misaligned or refused range)."""


class HttpxDownloader:
    """Download one URL into a `.part` file, resuming at the received offset, within `max_bytes`, over HTTPS only."""

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        *,
        sleep: Callable[[float], None] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._client = httpx.Client(transport=transport, follow_redirects=False, timeout=timeout)
        self._sleep = sleep if sleep is not None else time.sleep

    def close(self) -> None:
        self._client.close()

    # -- pooch downloader protocol -------------------------------------------------------------------------------
    def __call__(self, url: str, output_file: Any, pooch: Any = None, check_only: bool = False) -> bool | None:
        if check_only:
            return None
        self.fetch(url, Path(output_file), max_bytes=MAX_UNPINNED_BYTES)
        return None

    # -- the transfer ---------------------------------------------------------------------------------------------
    def fetch(self, url: str, part: Path, *, max_bytes: int | None) -> Fetched:
        """Fetch `url` into `part` (appending when it already holds bytes of the same file).

        Transient failures (connection errors, timeouts, HTTP 429 and 5xx) are retried up to five times after back-offs
        of 1, 2, 4, 8 and 16 s, resuming at the received offset when the server answers 206 and restarting when it
        answers 200. Any other failure raises at once. No partial file is left behind by a failed transfer.
        """
        cap = max_bytes if max_bytes is not None else MAX_UNPINNED_BYTES
        if part.exists() and part.stat().st_size > cap:
            part.unlink()  # a leftover larger than the declared file cannot be a prefix of it
        attempts = 0
        last = "no response"
        while attempts < MAX_ATTEMPTS:
            attempts += 1
            try:
                return Fetched(self._once(url, part, cap), attempts)
            except (DownloadFailed, Oversize, InsecureRedirect) as exc:
                part.unlink(missing_ok=True)
                exc.attempts = attempts  # type: ignore[attr-defined]  # read by the stage for the fetch record
                raise
            except _Restart:
                part.unlink(missing_ok=True)
                last = "range not honoured"
                continue  # a restart is not a failure: no back-off
            except _Retry as exc:
                last = str(exc)
            except httpx.TransportError as exc:
                last = type(exc).__name__
            if attempts <= len(BACKOFFS_S):
                log.debug("transfer failed (%s); retry %d after %s s", last, attempts, BACKOFFS_S[attempts - 1])
                self._sleep(BACKOFFS_S[attempts - 1])
        part.unlink(missing_ok=True)
        failure = DownloadFailed(f"download failed after {attempts} tries: {last}")
        failure.attempts = attempts  # type: ignore[attr-defined]
        raise failure

    def _once(self, url: str, part: Path, cap: int) -> str:
        offset = part.stat().st_size if part.exists() else 0
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            headers = {"Accept-Encoding": "identity"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            with self._client.stream("GET", current, headers=headers) as response:
                code = response.status_code
                if code in REDIRECT_CODES and "location" in response.headers:
                    target = urljoin(current, response.headers["location"])
                    if not target.lower().startswith("https://"):
                        raise InsecureRedirect("a redirect led to a non-HTTPS URL")
                    current = target
                    continue
                if code == 429 or code >= 500:
                    raise _Retry(f"HTTP {code}")
                if code == 416:  # the range is not satisfiable: start the file again
                    raise _Restart
                if code not in (200, 206):  # other 4xx (and a redirect without Location) fail at once
                    raise DownloadFailed(f"HTTP {code}")
                self._write(response, part, offset, cap)
                return current
        raise DownloadFailed("too many redirects")

    def _write(self, response: httpx.Response, part: Path, offset: int, cap: int) -> None:
        code = response.status_code
        start = offset
        mode = "ab"
        if code == 206:
            if _range_start(response.headers.get("content-range")) != offset:
                raise _Restart  # a misaligned 206 must never be appended
        elif offset:  # 200 to a range request: the server ignored it, the whole file follows
            start, mode = 0, "wb"
        announced = response.headers.get("content-length")
        if announced is not None and announced.isdigit() and start + int(announced) > cap:
            raise Oversize(f"the server announced {start + int(announced)} bytes, above the declared {cap}")
        written = start
        with part.open(mode if offset or code == 206 else "wb") as handle:
            for chunk in response.iter_bytes():
                written += len(chunk)
                if written > cap:
                    raise Oversize(f"the server delivered more than the declared {cap} bytes")
                handle.write(chunk)


def _range_start(header: str | None) -> int | None:
    """Start offset of a `Content-Range: bytes a-b/total` header, or None when absent or malformed."""
    if not header or not header.startswith("bytes "):
        return None
    first = header[6:].split("-", 1)[0]
    return int(first) if first.isdigit() else None
