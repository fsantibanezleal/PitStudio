"""The console application: request hygiene (Host, Origin, paths, CORS of /health), problem bodies, OpenAPI."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import Response

from pitstudio.contracts._generated.console import JobRequest
from pitstudio_api import __version__, config
from pitstudio_api.problem import line, problem, secure
from pitstudio_api.routes import ID, router

log = logging.getLogger("pitstudio_api")
# route shapes: literal segments and `{kind}` parameters; a parameter is checked on the RAW path (%2F stays %2F)
SHAPES = [
    ("health",),
    ("recipes",),
    ("recipes", "{slug}"),
    ("queue",),
    ("jobs",),
    ("jobs", "{job}"),
    ("jobs", "{job}", "cancel"),
    ("runs",),
    ("runs", "{run}"),
    ("runs", "{run}", "artefacts", "{art}"),
    ("runs", "{run}", "events"),
    ("openapi.json",),
]
STATIC = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
Wrap = Callable[[Any], Any]


def route_problem(raw: bytes) -> str | None:
    """A path parameter that does not match its pattern (raw path), or a UI path that could leave its folder."""
    segs = raw.decode("latin-1").split("/")[1:]
    if segs[:1] == ["ui"]:
        return None if all(s == "" or STATIC.fullmatch(s) for s in segs[1:]) else "the console file path is not valid"
    for shape in SHAPES:
        if len(shape) == len(segs) and all(w.startswith("{") or w == s for w, s in zip(shape, segs, strict=True)):
            for w, s in zip(shape, segs, strict=True):
                if w.startswith("{") and not re.fullmatch(ID[w[1:-1]], s, re.ASCII):
                    return f"path parameter {w[1:-1]} does not match its pattern"
    return None


def with_cors(send: Any, origin: str) -> Any:
    async def wrapped(message: dict) -> None:
        if message["type"] == "http.response.start":
            message = {
                **message,
                "headers": [
                    *message["headers"],
                    (b"access-control-allow-origin", origin.encode()),
                    (b"vary", b"Origin"),
                ],
            }
        await send(message)

    return wrapped


class Guard:
    """Pure ASGI middleware, outermost of the user middleware: runs before routing and before any body is read."""

    def __init__(self, app: Any, *, port: int, allow: list[str]) -> None:
        self.app, self.port, self.allow = app, port, allow
        self.own = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started, sec = False, secure(send)

        async def tracked(message: dict) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await sec(message)

        try:
            refusal, wrap = self.check(scope)
            await (refusal(scope, receive, tracked) if refusal else self.app(scope, receive, wrap(tracked)))
        except Exception:
            log.exception("unexpected error while serving %s", scope.get("path"))
            if not started:
                await problem(500, "the console failed to handle the request")(scope, receive, tracked)

    def check(self, scope: dict) -> tuple[Response | None, Wrap]:
        """(a refusal or None, a `send` wrapper): Host, preflight, cross-site POST, path parameters, CORS of /health."""
        heads: dict[str, list[str]] = {}
        for k, v in scope["headers"]:
            heads.setdefault(k.decode("latin-1").lower(), []).append(v.decode("latin-1"))
        host, origin, method, path = heads.get("host", []), heads.get("origin", []), scope["method"], scope["path"]
        m = re.fullmatch(r"(127\.0\.0\.1|localhost):([0-9]+)", host[0], re.I) if len(host) == 1 else None
        if not (m and m.group(2) == str(self.port)):
            return problem(400, f"the Host header must be 127.0.0.1:{self.port} or localhost:{self.port}"), lambda s: s
        if method == "OPTIONS" and origin:
            if not (
                origin[0] in self.allow and path == "/health" and heads.get("access-control-request-method") == ["GET"]
            ):
                return problem(
                    403, "cross-origin preflight is allowed for GET /health from allowlisted origins only"
                ), lambda s: s
            cors = {
                "Access-Control-Allow-Origin": origin[0],
                "Access-Control-Allow-Methods": "GET",
                "Access-Control-Max-Age": "600",
                "Vary": "Origin",
            }
            cors |= (
                {"Access-Control-Allow-Private-Network": "true"}
                if heads.get("access-control-request-private-network") == ["true"]
                else {}
            )
            return Response(status_code=204, headers=cors), lambda s: s
        cross = any(v.lower() == "cross-site" for v in heads.get("sec-fetch-site", []))
        if method == "POST" and ((origin and origin[0] not in self.own) or cross):
            return problem(403, "cross-site requests are refused"), lambda s: s
        if bad := route_problem(scope.get("raw_path") or path.encode()):
            return problem(422, bad), lambda s: s
        allowed = method == "GET" and path == "/health" and origin and origin[0] in self.allow
        return None, (lambda s: with_cors(s, origin[0])) if allowed else (lambda s: s)


def create_app(*, port: int, allow_origins: list[str] | None = None) -> FastAPI:
    allow = (
        allow_origins
        if allow_origins is not None
        else config.parse_allow_origins(os.environ.get("PITSTUDIO_CONSOLE_ALLOW_ORIGINS"))
    )
    app = FastAPI(title="PitStudio console API", version=__version__, docs_url=None, redoc_url=None)
    app.router.redirect_slashes = False
    app.include_router(router)
    app.add_middleware(Guard, port=port, allow=allow)

    @app.exception_handler(HTTPException)
    async def http_error(_: Any, exc: HTTPException) -> Response:
        return problem(exc.status_code, str(exc.detail), headers=dict(exc.headers or {}))

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Any, exc: RequestValidationError) -> Response:
        items = [
            {
                "pointer": "/" + "/".join(map(str, e["loc"])),
                "keyword": str(e["type"])[:48],
                "message": line(e["msg"]) or "invalid",
            }
            for e in exc.errors()
        ]
        return problem(422, "the request does not match the contract", errors=items)

    plain = app.openapi

    def openapi() -> dict:
        """The generated document with every error response described as `application/problem+json`."""
        if not app.openapi_schema:
            doc = plain()
            for op in (op for item in doc["paths"].values() for op in item.values()):
                for code, resp in op["responses"].items():
                    if code.isdigit() and int(code) >= 400 and "application/json" in resp.get("content", {}):
                        resp["content"] = {"application/problem+json": resp["content"]["application/json"]}
            schema = JobRequest.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )  # the POST /jobs body, from the contract
            for name, sub in schema.pop("$defs", {}).items():
                doc["components"]["schemas"].setdefault(name, sub)
            doc["components"]["schemas"]["JobRequest"] = schema
            app.openapi_schema = doc
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app
