# ruff: noqa: E501
"""Test support for spec 003 (console): a minimal in-process ASGI 3 HTTP client with full control of the request line,
headers and body framing (no httpx, no server, no third-party import).

`Client(app, port)` sends a request to an ASGI application the way a server (uvicorn) would present it:
  * `target` is the raw request target (`/runs/a%2Fb?x=1`); `scope["raw_path"]` is its path part, `scope["path"]` is that path
    percent-decoded (uvicorn unquotes it), `scope["query_string"]` the part after `?`;
  * default `Host` header is `127.0.0.1:<port>`; `headers` replaces or adds (a header given twice stays twice);
  * `body` is sent with `Content-Length` unless `content_length=False` (no header) or `chunks` is given (several
    `http.request` messages with `more_body=True`, and no Content-Length: a chunked upload as seen by the application);
  * an exception escaping the application is reported as status 599 (a server would answer 500 and log it).
`Stream` opens a long-lived GET (server-sent events) on a background event loop; the test reads the messages the
application sends, then disconnects. Both return plain data, so tests assert on bytes, statuses and headers only.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote


@dataclass
class Response:
    status: int
    headers: list[tuple[str, str]]
    body: bytes
    exception: BaseException | None = None

    def header(self, name: str) -> str | None:
        for k, v in self.headers:
            if k == name.lower():
                return v
        return None

    def headers_all(self, name: str) -> list[str]:
        return [v for k, v in self.headers if k == name.lower()]

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def build_scope(
    method: str, target: str, port: int, headers: list[tuple[str, str]], host: str | None
) -> dict[str, Any]:
    raw_path, _, query = target.partition("?")
    hdrs = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers]
    if not any(k == b"host" for k, _ in hdrs) and host != "":
        hdrs.insert(0, (b"host", (host if host is not None else f"127.0.0.1:{port}").encode("latin-1")))
    return {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1", "method": method.upper(), "scheme": "http",
        "path": unquote(raw_path), "raw_path": raw_path.encode("latin-1"), "query_string": query.encode("latin-1"), "root_path": "",
        "headers": hdrs, "client": ("127.0.0.1", 50000), "server": ("127.0.0.1", port),
    }  # fmt: skip


class Client:
    def __init__(self, app: Any, port: int = 8765) -> None:
        self.app = app
        self.port = port

    def request(
        self,
        method: str,
        target: str,
        *,
        headers: list[tuple[str, str]] | dict[str, str] | None = None,
        body: bytes | None = None,
        chunks: list[bytes] | None = None,
        content_length: bool = True,
        host: str | None = None,
        json_body: Any = None,
        timeout: float = 30.0,
    ) -> Response:
        hdrs = list(headers.items()) if isinstance(headers, dict) else list(headers or [])
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            if not any(k.lower() == "content-type" for k, _ in hdrs):
                hdrs.append(("content-type", "application/json"))
        if chunks is not None:
            hdrs.append(("transfer-encoding", "chunked"))
        elif body is not None and content_length:
            hdrs.append(("content-length", str(len(body))))
        scope = build_scope(method, target, self.port, hdrs, host)
        return asyncio.run(asyncio.wait_for(self._call(scope, body, chunks), timeout))

    async def _call(self, scope: dict[str, Any], body: bytes | None, chunks: list[bytes] | None) -> Response:
        parts: list[bytes] = list(chunks) if chunks is not None else [body or b""]
        state = {"i": 0}
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            if state["i"] < len(parts):
                i = state["i"]
                state["i"] += 1
                return {"type": "http.request", "body": parts[i], "more_body": i < len(parts) - 1}
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        exc: BaseException | None = None
        try:
            await self.app(scope, receive, send)
        except Exception as e:
            exc = e
        start = next((m for m in sent if m["type"] == "http.response.start"), None)
        if start is None:
            return Response(599 if exc else 0, [], b"", exc)
        hdrs = [(k.decode("latin-1").lower(), v.decode("latin-1")) for k, v in start.get("headers", [])]
        data = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        return Response(start["status"] if exc is None else 599, hdrs, data, exc)

    def get(self, target: str, **kw: Any) -> Response:
        return self.request("GET", target, **kw)

    def post(self, target: str, **kw: Any) -> Response:
        return self.request("POST", target, **kw)

    def stream(
        self, target: str, *, headers: list[tuple[str, str]] | dict[str, str] | None = None, host: str | None = None
    ) -> Stream:
        hdrs = list(headers.items()) if isinstance(headers, dict) else list(headers or [])
        return Stream(self.app, build_scope("GET", target, self.port, hdrs, host))


@dataclass
class SseEvent:
    id: str | None
    event: str | None
    data: str
    t: float = 0.0


@dataclass
class Stream:
    app: Any
    scope: dict[str, Any]
    status: int | None = None
    headers: list[tuple[str, str]] = field(default_factory=list)
    comments: list[float] = field(default_factory=list)  # monotonic arrival times of SSE comment lines (keep-alives)
    raw: bytes = b""
    ended: threading.Event = field(default_factory=threading.Event)
    exception: BaseException | None = None

    def __post_init__(self) -> None:
        self._q: queue.Queue[dict[str, Any]] = queue.Queue()
        self._buf = b""
        self._loop = asyncio.new_event_loop()
        self._recv: asyncio.Queue[dict[str, Any]] | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        assert self._ready.wait(10), "event loop did not start"
        self._started = time.monotonic()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())
        self.ended.set()

    async def _main(self) -> None:
        self._recv = asyncio.Queue()
        self._recv.put_nowait({"type": "http.request", "body": b"", "more_body": False})
        self._ready.set()

        async def receive() -> dict[str, Any]:
            assert self._recv is not None
            return await self._recv.get()

        async def send(message: dict[str, Any]) -> None:
            self._q.put({**message, "_t": time.monotonic()})

        try:
            await self.scope_app()(self.scope, receive, send)
        except Exception as e:
            self.exception = e
            self._q.put({"type": "exception", "_t": time.monotonic()})

    def scope_app(self) -> Any:
        return self.app

    def disconnect(self) -> None:
        if self._recv is not None:
            self._loop.call_soon_threadsafe(self._recv.put_nowait, {"type": "http.disconnect"})

    def _pump(self, timeout: float) -> bool:
        """Take one message from the application; False on timeout."""
        try:
            m = self._q.get(timeout=timeout)
        except queue.Empty:
            return False
        if m["type"] == "http.response.start":
            self.status = m["status"]
            self.headers = [(k.decode("latin-1").lower(), v.decode("latin-1")) for k, v in m.get("headers", [])]
        elif m["type"] == "http.response.body":
            self.raw += m.get("body", b"")
            self._buf += m.get("body", b"")
        return True

    def wait_headers(self, timeout: float = 10.0) -> None:
        end = time.monotonic() + timeout
        while self.status is None and time.monotonic() < end:
            self._pump(0.05)
            if self.exception is not None:
                break

    def header(self, name: str) -> str | None:
        for k, v in self.headers:
            if k == name.lower():
                return v
        return None

    def events(self, count: int, timeout: float = 10.0) -> list[SseEvent]:
        """Read until `count` complete SSE events arrived (or the timeout); comments are recorded in `comments`."""
        out: list[SseEvent] = []
        end = time.monotonic() + timeout
        while len(out) < count and time.monotonic() < end:
            while b"\n\n" in self._buf.replace(b"\r\n", b"\n") and len(out) < count:
                norm = self._buf.replace(b"\r\n", b"\n")
                block, _, rest = norm.partition(b"\n\n")
                self._buf = rest
                ev = self._parse(block.decode("utf-8", errors="replace"))
                if ev is not None:
                    out.append(ev)
            if len(out) >= count:
                break
            self._pump(0.05)
            if self.ended.is_set() and self._q.empty() and b"\n\n" not in self._buf.replace(b"\r\n", b"\n"):
                break
        return out

    def _parse(self, block: str) -> SseEvent | None:
        ev = SseEvent(None, None, "", time.monotonic())
        data: list[str] = []
        comment_only = True
        for line in block.split("\n"):
            if line.startswith(":"):
                self.comments.append(time.monotonic())
                continue
            comment_only = False
            name, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if name == "id":
                ev.id = value
            elif name == "event":
                ev.event = value
            elif name == "data":
                data.append(value)
        if comment_only:
            return None
        ev.data = "\n".join(data)
        return ev

    def drain(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self._pump(0.05)

    def close(self, wait: float = 5.0) -> bool:
        """Disconnect and report whether the application's task ended within `wait` seconds."""
        self.disconnect()
        end = time.monotonic() + wait
        while time.monotonic() < end and not self.ended.is_set():
            self._pump(0.05)
        return self.ended.is_set()
