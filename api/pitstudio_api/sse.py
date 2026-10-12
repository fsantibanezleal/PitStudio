"""The server-sent event stream of a run: replay, follow, telemetry at most once a second, keep-alive (FR-003-15, 16)."""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import collections
import contextlib
import json
import re
import threading
import time
from pathlib import Path

from starlette.responses import StreamingResponse

from pitstudio.runner.recipe import first_errors, strict_json

MAX_STREAMS, MAX_LINE, POLL_S, PING_S, BACKLOG = 8, 16384, 0.25, 10.0, 10
_open, _lock = 0, threading.Lock()


def parse_last_event_id(value: str | None) -> int:
    """0 when absent; a decimal integer in 0..2**63-1 otherwise, else ValueError (a 422)."""
    if value is None:
        return 0
    if not re.fullmatch(r"[0-9]{1,19}", value, re.ASCII) or int(value) > 2**63 - 1:
        raise ValueError("Last-Event-ID must be a decimal integer in 0..9223372036854775807")
    return int(value)


class Tail:
    """The complete lines a file gained since the last call; half a line waits for its newline."""

    def __init__(self, path: Path) -> None:
        self.path, self.pos, self.n = path, 0, 0

    def lines(self) -> list[tuple[int, bytes]]:
        try:
            with open(self.path, "rb") as fh:
                fh.seek(self.pos)
                data = fh.read()
        except OSError:
            return []
        end = data.rfind(b"\n") + 1
        rows = data[:end].split(b"\n")[:-1]
        out = [(self.n + i + 1, raw) for i, raw in enumerate(rows)]
        self.pos, self.n = self.pos + end, self.n + len(rows)
        return out


def frame(event: str, data: object, id_: object = None) -> str:
    return (
        f"id: {id_}\n" if id_ is not None else ""
    ) + f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def event_frame(n: int, raw: bytes, after: int) -> str | None:
    """The frame of one events.jsonl line: an `event`, an `error` naming the line, or None (blank or already seen)."""
    if not raw.strip():
        return None
    try:
        if len(raw) > MAX_LINE:
            raise ValueError(f"the line is longer than {MAX_LINE} bytes")
        doc = strict_json(raw.decode("utf-8"))
        if errs := first_errors("events", doc, "#/$defs/event", n=1):
            raise ValueError(errs[0])
    except (ValueError, RecursionError) as e:
        return frame("error", {"line": n, "message": " ".join(str(e).split())[:300] or "invalid line"})
    return None if doc["seq"] <= after else frame("event", doc, doc["seq"])


def top_seq(rows: list[tuple[int, bytes]]) -> int:
    """The highest seq of the valid events among these lines (0 when none)."""
    top = 0
    for _, raw in rows:
        with contextlib.suppress(ValueError, RecursionError, KeyError, TypeError):
            top = max(top, strict_json(raw.decode("utf-8"))["seq"])
    return top


def samples(rows: list[tuple[int, bytes]]) -> list[dict]:
    """The valid telemetry samples among the new lines of telemetry.jsonl, oldest first."""
    out = []
    for _, raw in rows:
        try:
            doc = strict_json(raw.decode("utf-8"))
        except ValueError, RecursionError:
            continue
        if not first_errors("events", doc, "#/$defs/telemetry_sample", n=1):
            out.append(doc)
    return out


async def stream(run_dir: Path, after: int):
    events, tele, last_sent, last_out = (
        Tail(run_dir / "events.jsonl"),
        Tail(run_dir / "telemetry.jsonl"),
        0.0,
        time.monotonic(),
    )
    backlog: collections.deque[dict] = collections.deque(maxlen=BACKLOG)  # samples waiting for their second
    while True:
        out = [f for n, raw in events.lines() if (f := event_frame(n, raw, after))]
        backlog.extend(samples(tele.lines()))
        now = time.monotonic()
        if backlog and now - last_sent >= 1.0:  # at most one telemetry event per second, oldest waiting sample first
            out.append(frame("telemetry", backlog.popleft()))
            last_sent = now
        if out or now - last_out >= PING_S:
            last_out = now
            for f in out or [": keep-alive\n\n"]:
                yield f
        await asyncio.sleep(POLL_S)


class Slot(StreamingResponse):
    """An event stream that gives its slot back however it ends (finished, cancelled, client gone)."""

    async def __call__(self, scope, receive, send) -> None:
        global _open
        try:
            await super().__call__(scope, receive, send)
        finally:
            with _lock:
                _open -= 1


def open_stream(run_dir: Path, after: int) -> Slot | None:
    """A stream response, or None when 8 streams are already open."""
    global _open
    with _lock:
        if _open >= MAX_STREAMS:
            return None
        _open += 1
    after = min(
        after, top_seq(Tail(run_dir / "events.jsonl").lines())
    )  # a resume point past the last event means: follow from the end
    return Slot(
        stream(run_dir, after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
