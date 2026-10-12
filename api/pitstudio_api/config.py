"""Console settings read from the environment: the port and the CORS allowlist (FR-003-03, 04, 21)."""

# ruff: noqa: E501

from __future__ import annotations

import re

HOST = "127.0.0.1"
DEFAULT_ORIGIN = "https://fsantibanezleal.github.io"
_PORT = re.compile(r"[0-9]{4,5}", re.ASCII)
_ORIGIN = re.compile(
    r"(https://[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?|http://(127\.0\.0\.1|localhost))(:([0-9]{1,5}))?", re.ASCII
)


def parse_port(value: str | None) -> int | None:
    """The port of PITSTUDIO_CONSOLE_PORT: None when unset (the OS assigns one), else an integer in 1024..65535."""
    if value is None:
        return None
    if not _PORT.fullmatch(value) or not 1024 <= int(value) <= 65535:
        raise ValueError(f"PITSTUDIO_CONSOLE_PORT must be a decimal integer in 1024..65535, got {value[:40]!r}")
    return int(value)


def parse_allow_origins(value: str | None) -> list[str]:
    """Exact origins: https with an optional port, or http://127.0.0.1:<port> / http://localhost:<port> (never `*`, paths or userinfo)."""
    if value is None:
        return [DEFAULT_ORIGIN]
    for entry in value.split(","):
        m = _ORIGIN.fullmatch(entry)
        port = int(m.group(5)) if m and m.group(5) else None
        if not m or (m.group(3) and port is None) or (port is not None and not 1 <= port <= 65535):
            raise ValueError(
                f"PITSTUDIO_CONSOLE_ALLOW_ORIGINS entry {entry[:80]!r} is not an exact https origin or loopback http origin"
            )
    return value.split(",")
