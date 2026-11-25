"""The loopback `llama-server` driver (FR-015-11, FR-015-12, NFR-015-04).

llama.cpp runs as `llama-server` bound to 127.0.0.1 on an ephemeral port with `--mmproj`, started inside the stage's
job object and terminated at stage end. The driver opens connections only to that loopback server. A query that fails
(non-zero exit of the process, more than `query_timeout_s`, a connection failure, an out-of-memory answer or a
malformed answer) restarts the server and is retried once; a second failure records it as `error`, restarts the server
for the next query and counts in the error rate. A stage with more than 2 % errored queries fails."""

from __future__ import annotations

import contextlib
import http.client
import json
import socket
import subprocess
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOOPBACK = "127.0.0.1"
MAX_ERROR_RATE = 0.02
STOP_WAIT_S = 10.0


class ServerStartError(RuntimeError):
    """The server did not answer `GET /health` in time or exited while starting."""


@dataclass
class QueryResult:
    status: str  # "ok" or "error"
    text: str | None
    top_logprobs: dict[str, float] | None
    attempts: int
    error: str | None = None
    elapsed_s: float = 0.0


class _Failure(Exception):
    """One failed attempt (the reason is for the record, never the model text)."""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((LOOPBACK, 0))
        return int(s.getsockname()[1])


class ServerDriver:
    """Start, query, restart and stop a llama-server; see the module docstring."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        model: Path,
        mmproj: Path,
        host: str = LOOPBACK,
        job: Any = None,
        query_timeout_s: float = 120.0,
        startup_timeout_s: float = 120.0,
        extra_args: Sequence[str] = (),
    ) -> None:
        if host != LOOPBACK:
            raise ValueError(f"the server binds to {LOOPBACK} only, not {host!r}")
        self.command = list(command)
        self.model, self.mmproj = Path(model), Path(mmproj)
        self.job = job
        self.query_timeout_s = query_timeout_s
        self.startup_timeout_s = startup_timeout_s
        self.extra_args = list(extra_args)
        self.process: subprocess.Popen[bytes] | None = None
        self.port: int | None = None
        self._stderr: Any = None

    # ------------------------------------------------------------------------------------------ life cycle
    def start(self) -> None:
        self.port = _free_port()
        self._stderr = tempfile.TemporaryFile()  # noqa: SIM115  (closed in `_kill`)
        argv = [
            *self.command,
            "--model",
            str(self.model),
            "--mmproj",
            str(self.mmproj),
            "--host",
            LOOPBACK,
            "--port",
            str(self.port),
            *self.extra_args,
        ]
        self.process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=self._stderr)
        if self.job is not None:
            self.job.assign(self.process.pid)
        deadline = time.monotonic() + self.startup_timeout_s
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise ServerStartError(f"llama-server exited with code {self.process.returncode} while starting")
            if self._health():
                return
            time.sleep(0.1)
        self._kill()
        raise ServerStartError(f"llama-server did not answer /health within {self.startup_timeout_s} s")

    def _health(self) -> bool:
        try:
            conn = http.client.HTTPConnection(LOOPBACK, self.port, timeout=1.0)
            conn.request("GET", "/health")
            ok = conn.getresponse().status == 200
            conn.close()
            return ok
        except OSError, http.client.HTTPException:
            return False

    def _kill(self) -> None:
        proc = self.process
        if proc is not None and proc.poll() is None:
            proc.kill()
        if proc is not None:
            with contextlib.suppress(subprocess.TimeoutExpired):  # a process that survives kill
                proc.wait(timeout=STOP_WAIT_S)
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None

    def restart(self) -> None:
        self._kill()
        self.start()

    def stop(self) -> None:
        self._kill()
        if self.job is not None:
            self.job.terminate()

    def __enter__(self) -> ServerDriver:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # ------------------------------------------------------------------------------------------ queries
    def _post(self, request: dict[str, Any]) -> tuple[str, dict[str, float] | None]:
        conn = http.client.HTTPConnection(LOOPBACK, self.port, timeout=self.query_timeout_s)
        try:
            conn.request("POST", "/v1/chat/completions", json.dumps(request), {"Content-Type": "application/json"})
            response = conn.getresponse()
            body = response.read()
        except (OSError, http.client.HTTPException) as exc:
            raise _Failure(f"{type(exc).__name__}") from None
        finally:
            conn.close()
        if response.status != 200:
            raise _Failure(f"HTTP {response.status}")
        try:
            choice = json.loads(body)["choices"][0]
            text = choice["message"]["content"]
        except ValueError, KeyError, IndexError, TypeError:
            raise _Failure("malformed answer") from None
        top = None
        try:
            entries = choice["logprobs"]["content"][0]["top_logprobs"]
            top = {e["token"]: float(e["logprob"]) for e in entries}
        except KeyError, IndexError, TypeError, ValueError:
            top = None
        return str(text), top

    def ask(self, request: dict[str, Any]) -> QueryResult:
        t0 = time.monotonic()
        reason = ""
        for attempt in (1, 2):
            try:
                text, top = self._post(request)
                if self.process is not None and self.process.poll() not in (None, 0):
                    raise _Failure("the server exited after answering")
                return QueryResult("ok", text, top, attempt, None, time.monotonic() - t0)
            except _Failure as failure:
                reason = str(failure)
                self.restart()
        return QueryResult("error", "", None, 2, reason, time.monotonic() - t0)

    def run_queries(self, requests: Sequence[dict[str, Any]]) -> list[QueryResult]:
        return [self.ask(r) for r in requests]


def error_rate(results: Sequence[Any]) -> float:
    """Share of results whose status is "error"; ValueError for no results."""
    if len(results) == 0:
        raise ValueError("n = 0: no results")
    return sum(1 for r in results if r.status == "error") / len(results)


def stage_failed(results: Sequence[Any]) -> bool:
    """A stage with more than 2 % errored queries fails (integer arithmetic: errors * 50 > n)."""
    if len(results) == 0:
        raise ValueError("n = 0: no results")
    return sum(1 for r in results if r.status == "error") * 50 > len(results)
