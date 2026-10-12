"""Downloader on httpx (FR-008-05, FR-008-10, FR-008-11): HTTPS GETs streamed into a `.part` file within a size cap.

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


class HttpxDownloader:
    """Download one URL into a `.part` file, within `max_bytes`, over HTTPS only (redirects included)."""

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

    def fetch(self, url: str, part: Path, *, max_bytes: int | None) -> Fetched:
        """Fetch `url` into `part`; raise a class of `errors` on any failure (no partial file is left behind)."""
        cap = max_bytes if max_bytes is not None else MAX_UNPINNED_BYTES
        try:
            return Fetched(self._once(url, part, cap), 1)
        except BaseException as exc:
            part.unlink(missing_ok=True)
            if isinstance(exc, (DownloadFailed, Oversize, InsecureRedirect)):
                exc.attempts = 1  # type: ignore[attr-defined]  # read by the stage for the fetch record
            raise

    def _once(self, url: str, part: Path, cap: int) -> str:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            with self._client.stream("GET", current, headers={"Accept-Encoding": "identity"}) as response:
                code = response.status_code
                if code in REDIRECT_CODES and "location" in response.headers:
                    target = urljoin(current, response.headers["location"])
                    if not target.lower().startswith("https://"):
                        raise InsecureRedirect("a redirect led to a non-HTTPS URL")
                    current = target
                    continue
                if code != 200:
                    raise DownloadFailed(f"HTTP {code}")
                self._write(response, part, cap)
                return current
        raise DownloadFailed("too many redirects")

    def _write(self, response: httpx.Response, part: Path, cap: int) -> None:
        announced = response.headers.get("content-length")
        if announced is not None and announced.isdigit() and int(announced) > cap:
            raise Oversize(f"the server announced {announced} bytes, above the declared {cap}")
        written = 0
        with part.open("wb") as handle:
            for chunk in response.iter_bytes():
                written += len(chunk)
                if written > cap:
                    raise Oversize(f"the server delivered more than the declared {cap} bytes")
                handle.write(chunk)
