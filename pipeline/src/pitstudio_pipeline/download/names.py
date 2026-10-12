"""The local name of a downloaded file."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit


def local_name(url: str, name: str | None = None) -> str:
    """The entry's `name` when given, else the percent-decoded last segment of the URL path."""
    return name if name is not None else unquote(urlsplit(url).path.rsplit("/", 1)[-1])
