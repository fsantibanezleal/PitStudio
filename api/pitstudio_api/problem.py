"""RFC 9457 problem responses and the security headers every response carries (FR-003-22)."""

# ruff: noqa: E501

from __future__ import annotations

import http
from typing import Any

from starlette.responses import JSONResponse

CSP = "default-src 'self'; frame-ancestors 'none'"
PROBLEM = "application/problem+json"


def line(text: object, limit: int = 300) -> str:
    return " ".join(str(text).split())[:limit]


def problem(status: int, detail: str, *, title: str | None = None, kind: str = "about:blank", errors: list[dict] | None = None,
            headers: dict[str, str] | None = None) -> JSONResponse:  # fmt: skip
    """A `problem` body (contracts/console.schema.json#/$defs/problem): one-line texts, no trace, no path."""
    body: dict[str, Any] = {
        "type": kind,
        "title": title or http.HTTPStatus(status).phrase,
        "status": status,
        "detail": line(detail),
    }
    if errors:
        body["errors"] = errors[:50]
    return JSONResponse(body, status, headers, media_type=PROBLEM)


def secure(send):
    """Wrap `send` so that every response gets nosniff, JSON is never cached and HTML carries the CSP."""

    async def wrapped(message: dict) -> None:
        if message["type"] == "http.response.start":
            headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-content-type-options"]
            kind = next((v.decode("latin-1").lower() for k, v in headers if k.lower() == b"content-type"), "")
            has = {k.lower() for k, _ in headers}
            headers.append((b"x-content-type-options", b"nosniff"))
            if kind.startswith(("application/json", PROBLEM)) and b"cache-control" not in has:
                headers.append((b"cache-control", b"no-store"))
            if kind.startswith("text/html"):
                headers.append((b"content-security-policy", CSP.encode()))
            message = {**message, "headers": headers}
        await send(message)

    return wrapped
