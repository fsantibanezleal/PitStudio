# ruff: noqa: E501
"""T-015-016: the loopback llama-server driver: bind address, ephemeral port, job object, network audit, retries and the 2 % error threshold.

Requirements: FR-015-11, FR-015-12, NFR-015-04.

Spec: specs/015-vlm/spec.md
- FR-015-11: the lane drives llama.cpp as `llama-server` bound to 127.0.0.1 on an ephemeral port with `--mmproj`, started inside the stage's job
  object and terminated at stage end; no `st59_*` stage opens a network connection other than to that loopback server (and, during downloads only,
  to the Hugging Face hub).
- FR-015-12: if the llama.cpp process exits with a non-zero code, a query exceeds 120 s, or the process reports out-of-memory, the lane restarts the
  server and retries that query once, then records it as `error` (excluded from scoring, counted in the error rate); a stage with more than 2 %
  errored queries fails.
- NFR-015-04: errored queries per stage <= 2 % (stage summary).

Oracle: a real child process, a fake `llama-server` written by this test (standard library `http.server`; it accepts the llama-server flags
`--model --mmproj --host --port`, serves `GET /health` and the OpenAI-style `POST /v1/chat/completions` of llama-server, logs its arguments and follows a
scripted sequence of actions per request: ok, crash, exit with a code, hang, out-of-memory), so the expected behaviour of every query is known by
construction; the socket layer is wrapped to record every address the process opens a connection to; the error-rate arithmetic by hand
(2/100 = 2 % passes, 3/100 = 3 % fails, 1/50 = 2 % passes, 2/50 = 4 % fails).

Expected API of the implementation (package `pitstudio_pipeline`), `pitstudio_pipeline.reason.server`:
- `ServerDriver(command, *, model, mmproj, host="127.0.0.1", job=None, query_timeout_s=120.0, startup_timeout_s=30.0)`: `command` is the argv prefix
  of the server (production: the verified `llama-server.exe`); any `host` other than "127.0.0.1" raises ValueError. A context manager and also
  `start()` / `stop()`. `start()` picks a free ephemeral port, runs `command + ["--model", <model>, "--mmproj", <mmproj>, "--host", "127.0.0.1",
  "--port", <port>]`, calls `job.assign(pid)` when a job is given, and returns when `GET /health` answers 200; `stop()` terminates the process (and
  calls `job.terminate()`). `.process` is the current `subprocess.Popen`, `.port` the current port.
- `ask(request: dict) -> QueryResult` posts the JSON request to `/v1/chat/completions` of the server. `QueryResult` has `status` ("ok" or "error"),
  `text` (the first choice's message content), `top_logprobs` (dict token -> log-probability of the first generated token, from the first choice's
  `logprobs.content[0].top_logprobs`, or None) and `attempts` (1 or 2). On a non-zero exit of the process, a request longer than `query_timeout_s`, a
  connection failure or a response reporting out of memory it restarts the server and retries once; a second failure gives status "error".
- `run_queries(requests) -> list[QueryResult]`.
- `error_rate(results) -> float` (share of results with status "error"; ValueError for no results) and `stage_failed(results) -> bool` (error rate above 0.02).
"""

from __future__ import annotations

import http.client
import json
import socket
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from pitstudio_pipeline.reason import server

FAKE = textwrap.dedent(
    """
    import argparse, json, os, sys, time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    ap = argparse.ArgumentParser()
    ap.add_argument("--model"); ap.add_argument("--mmproj"); ap.add_argument("--host"); ap.add_argument("--port", type=int)
    ap.add_argument("--ctx-size", default=None)
    a, _ = ap.parse_known_args()
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "host": a.host, "port": a.port, "mmproj": a.mmproj, "model": a.model, "pid": os.getpid()}) + "\\n")
    SCEN = os.environ["FAKE_SCENARIO"]; COUNT = SCEN + ".count"

    def next_action():
        n = int(open(COUNT).read()) if os.path.exists(COUNT) else 0
        open(COUNT, "w").write(str(n + 1))
        actions = json.load(open(SCEN))
        return actions[n] if n < len(actions) else "ok"

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_GET(self):
            self._send(200, {"status": "ok"}) if self.path == "/health" else self._send(404, {})
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0)); self.rfile.read(n)
            act = next_action()
            if act == "crash": os._exit(1)
            if act.startswith("exit"): os._exit(int(act[4:]))
            if act == "hang": time.sleep(30)
            if act == "oom":
                sys.stderr.write("ggml_backend_cuda_buffer_type_alloc_buffer: allocating 9999 MiB on device 0: cudaMalloc failed: out of memory\\n"); sys.stderr.flush()
                self._send(500, {"error": {"message": "out of memory", "type": "server_error"}}); os._exit(1)
            self._send(200, {"choices": [{"message": {"content": "<answer>yes</answer>"}, "logprobs": {"content": [{"token": "yes", "logprob": -0.2, "top_logprobs": [{"token": "yes", "logprob": -0.2}, {"token": "no", "logprob": -1.7}]}]}}]})

    ThreadingHTTPServer((a.host, a.port), H).serve_forever()
    """
)


class Job:
    def __init__(self) -> None:
        self.assigned: list[int] = []
        self.terminated = 0

    def assign(self, pid: int) -> None:
        self.assigned.append(pid)

    def terminate(self) -> None:
        self.terminated += 1


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    script = tmp_path / "fake_llama_server.py"
    script.write_text(FAKE, encoding="utf-8")
    log = tmp_path / "launches.jsonl"
    scen = tmp_path / "scenario.json"
    scen.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("FAKE_SCENARIO", str(scen))
    model, mmproj = tmp_path / "model-Q8_0.gguf", tmp_path / "mmproj-F16.gguf"
    model.write_bytes(b"GGUF")
    mmproj.write_bytes(b"GGUF")

    def make(actions: list[str] | None = None, **kw) -> SimpleNamespace:
        scen.write_text(json.dumps(actions or []), encoding="utf-8")
        job = kw.pop("job", Job())
        drv = server.ServerDriver([sys.executable, str(script)], model=model, mmproj=mmproj, job=job, **kw)
        return SimpleNamespace(driver=drv, job=job, log=log, model=model, mmproj=mmproj)

    return make


def _launches(log: Path) -> list[dict]:
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]


REQ = {"messages": [{"role": "user", "content": "Is a person within 30 m of a haul truck?"}], "temperature": 0}


def _alive(port: int) -> bool:
    """True when something on the port still answers `GET /health` with 200 (a dead server may leave a half-open port on some platforms)."""
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=1.0)
        c.request("GET", "/health")
        return c.getresponse().status == 200
    except OSError, http.client.HTTPException:
        return False


@pytest.mark.req("FR-015-11")
def test_the_server_is_started_on_loopback_with_an_ephemeral_port_the_projector_and_inside_the_job(rig) -> None:
    r = rig()
    with r.driver:
        (launch,) = _launches(r.log)
        assert launch["host"] == "127.0.0.1"
        assert "--host" in launch["argv"]
        assert launch["argv"][launch["argv"].index("--host") + 1] == "127.0.0.1"
        assert launch["port"] == r.driver.port
        assert launch["port"] > 1023
        assert launch["port"] != 8080
        assert launch["mmproj"] == str(r.mmproj)
        assert "--mmproj" in launch["argv"]
        assert launch["model"] == str(r.model)
        assert r.job.assigned == [r.driver.process.pid]
        assert _alive(launch["port"])
        res = r.driver.ask(REQ)
        assert (res.status, res.text, res.attempts) == ("ok", "<answer>yes</answer>", 1)
        assert res.top_logprobs == {"yes": -0.2, "no": -1.7}


@pytest.mark.req("FR-015-11")
def test_the_server_is_terminated_at_stage_end_and_the_job_is_told_so(rig) -> None:
    r = rig()
    with r.driver:
        port = r.driver.port
        proc = r.driver.process
    assert proc.poll() is not None
    assert r.job.terminated >= 1
    assert not _alive(port)


@pytest.mark.req("FR-015-11")
def test_two_starts_do_not_share_a_fixed_port(rig) -> None:
    ports = []
    for _ in range(2):
        r = rig()
        with r.driver:
            ports.append(r.driver.port)
    assert all(p > 1023 and p != 8080 for p in ports)


@pytest.mark.req("FR-015-11")
@pytest.mark.parametrize(
    "host", ["0.0.0.0", "localhost", "::1", "127.0.0.2", "192.168.1.10", "", "example.org", "127.0.0.1 "]
)
def test_a_bind_address_other_than_127_0_0_1_is_refused(rig, host: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        rig(host=host)


@pytest.mark.req("FR-015-11")
def test_the_stage_opens_connections_only_to_the_loopback_server(rig, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list = []
    names: list = []
    real_connect, real_gai = socket.socket.connect, socket.getaddrinfo

    def connect(self, address):
        seen.append(address)
        return real_connect(self, address)

    def gai(host, *a, **k):
        names.append(host)
        return real_gai(host, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", gai)
    r = rig(["ok", "crash", "ok", "ok"])
    with r.driver:
        for _ in range(3):
            r.driver.ask(REQ)
    assert seen, "the driver must talk to the server over a socket"
    assert {a[0] for a in seen if isinstance(a, tuple)} == {"127.0.0.1"}
    assert {a[1] for a in seen} <= {launch["port"] for launch in _launches(r.log)}
    assert {n for n in names if n is not None} <= {"127.0.0.1"}


@pytest.mark.req("FR-015-12")
@pytest.mark.parametrize("fault", ["crash", "exit3", "oom"])
def test_a_process_failure_restarts_the_server_and_the_query_is_retried_once(rig, fault: str) -> None:
    r = rig([fault, "ok", "ok"])
    with r.driver:
        res = r.driver.ask(REQ)
        assert (res.status, res.attempts, res.text) == ("ok", 2, "<answer>yes</answer>")
        assert len(_launches(r.log)) == 2  # the server was restarted exactly once
        nxt = r.driver.ask(REQ)
        assert (nxt.status, nxt.attempts) == ("ok", 1)
    assert len(_launches(r.log)) == 2
    assert len(r.job.assigned) == 2  # the restarted process is inside the job as well


@pytest.mark.req("FR-015-12")
def test_a_query_longer_than_the_limit_is_cut_the_server_restarted_and_the_query_retried(rig) -> None:
    r = rig(["hang", "ok"], query_timeout_s=1.5)
    with r.driver:
        t0 = time.monotonic()
        res = r.driver.ask(REQ)
        elapsed = time.monotonic() - t0
    assert (res.status, res.attempts) == ("ok", 2)
    assert 1.4 <= elapsed < 20.0  # about one timeout plus a restart, never the 30 s the hung request would take
    assert len(_launches(r.log)) == 2


@pytest.mark.req("FR-015-12")
@pytest.mark.parametrize("faults", [["crash", "crash"], ["exit3", "oom"], ["oom", "oom"], ["hang", "hang"]])
def test_a_second_failure_records_the_query_as_error_and_the_run_goes_on(rig, faults: list[str]) -> None:
    r = rig([*faults, "ok", "ok"], query_timeout_s=1.0)
    with r.driver:
        bad = r.driver.ask(REQ)
        assert (bad.status, bad.attempts) == ("error", 2)
        assert bad.text in ("", None)
        good = r.driver.ask(REQ)
        assert (good.status, good.attempts) == ("ok", 1)
    assert len(_launches(r.log)) == 3  # first start, restart for the retry, restart after the second failure


@pytest.mark.req("FR-015-12")
def test_run_queries_returns_one_result_per_request_in_order(rig) -> None:
    r = rig(["ok", "crash", "ok", "crash", "crash", "ok"])
    with r.driver:
        out = r.driver.run_queries([REQ] * 4)
    assert [(x.status, x.attempts) for x in out] == [("ok", 1), ("ok", 2), ("error", 2), ("ok", 1)]


def _results(n: int, errors: int) -> list:
    return [SimpleNamespace(status="error" if i < errors else "ok") for i in range(n)]


@pytest.mark.req("NFR-015-04")
@pytest.mark.req("FR-015-12")
@pytest.mark.parametrize(
    ("n", "errors", "failed"),
    [
        (100, 0, False),
        (100, 2, False),
        (100, 3, True),
        (50, 1, False),
        (50, 2, True),
        (1000, 20, False),
        (1000, 21, True),
        (1, 1, True),
        (6480, 129, False),
        (6480, 130, True),
    ],
)
def test_a_stage_with_more_than_2_percent_errored_queries_fails(n: int, errors: int, failed: bool) -> None:
    res = _results(n, errors)
    assert server.error_rate(res) == pytest.approx(errors / n, abs=1e-15)
    assert server.stage_failed(res) is failed


@pytest.mark.req("FR-015-12")
def test_the_error_rate_of_no_results_is_refused() -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        server.error_rate([])
    with pytest.raises(ValueError):  # noqa: PT011
        server.stage_failed([])
