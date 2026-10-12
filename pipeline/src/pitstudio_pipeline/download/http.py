"""Downloader on httpx (FR-008-05): one HTTPS GET streamed into a `.part` file.

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

import httpx

from pitstudio_pipeline.errors import DownloadFailed

log = logging.getLogger("pitstudio_pipeline.download")
CHUNK = 1 << 20
MAX_UNPINNED_BYTES = 64 * (
    1 << 30
)  # the registry's size bound (spec 001 data-model 5.1.1) caps a file with unknown size


@dataclass
class Fetched:
    """Outcome of a completed transfer: the URL the bytes came from and the number of tries it took."""

    final_url: str
    attempts: int


class HttpxDownloader:
    """Download one URL into a `.part` file."""

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        *,
        sleep: Callable[[float], None] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._client = httpx.Client(transport=transport, follow_redirects=True, timeout=timeout)
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
        """Fetch `url` into `part`; raise `DownloadFailed` on any HTTP error status."""
        with self._client.stream("GET", url, headers={"Accept-Encoding": "identity"}) as response:
            if response.status_code != 200:
                raise DownloadFailed(f"HTTP {response.status_code}")
            with part.open("wb") as handle:
                for chunk in response.iter_raw(CHUNK):
                    handle.write(chunk)
            return Fetched(str(response.url), 1)
