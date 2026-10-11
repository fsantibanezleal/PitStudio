# ruff: noqa: E501, PT018, RUF001
"""T-003-010: console start-up: loopback-only binding, port rules, no GPU, no lock, no process, no store writes.

Requirements: FR-003-01, FR-003-02, FR-003-03, FR-003-04, FR-003-05.

Expected product facts (stated for the implementer):
  * `python -m pitstudio_api` (= `uv run --extra api python -m pitstudio_api`) starts uvicorn on 127.0.0.1 only and prints
    a line `http://127.0.0.1:<port>/ui/`; every listening socket of the process has local address 127.0.0.1;
  * the port is read from PITSTUDIO_CONSOLE_PORT (decimal integer 1024..65535); unset: an OS-assigned free port, printed;
    `pitstudio_api.config.parse_port(value: str | None) -> int | None` (None = unset) raises ValueError for anything else;
    an invalid value exits 2 naming the variable; a port already in use exits 3;
  * any other bind address (`--host <anything but 127.0.0.1>`, PITSTUDIO_CONSOLE_HOST, `--uds`, `--fd`) exits 2 naming the
    option or variable, before any socket is opened;
  * the console never imports an NVML binding, takes a GPU lock, starts a process or writes to the store, except
    `queue.enqueue`/`queue.cancel` (runner API): statically (no such import in `api/pitstudio_api/`) and dynamically (spies).
Oracles: psutil socket inspection (reference), socket connect attempts, hostile values written by hand, AST of the package.
"""

from __future__ import annotations

import ast
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import psutil
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw

API = rw.ROOT / "api" / "pitstudio_api"
URL_LINE = re.compile(r"http://127\.0\.0\.1:(\d+)/ui/")


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Server:
    def __init__(self, world: rw.World, *args: str, env: dict[str, str] | None = None) -> None:
        e = {**world.env(), **(env or {})}
        for k in ("PITSTUDIO_CONSOLE_PORT", "PITSTUDIO_CONSOLE_HOST"):
            if k not in (env or {}):
                e.pop(k, None)
        self.p = subprocess.Popen(
            [sys.executable, "-m", "pitstudio_api", *args],
            env=e,
            cwd=str(world.base),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.lines: queue.Queue[str] = queue.Queue()
        self.log: list[str] = []
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.p.stdout is not None
        for line in self.p.stdout:
            self.log.append(line.rstrip("\n"))
            self.lines.put(line)

    def wait_url(self, timeout: float = 60.0) -> int | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                m = URL_LINE.search(self.lines.get(timeout=0.2))
            except queue.Empty:
                if self.p.poll() is not None:
                    return None
                continue
            if m:
                return int(m.group(1))
        return None

    def stop(self) -> None:
        if self.p.poll() is None:
            self.p.kill()
        self.p.wait(30)

    @property
    def output(self) -> str:
        return "\n".join(self.log)


def listening(pid: int) -> list[tuple[str, int]]:
    return [
        (c.laddr.ip, c.laddr.port)
        for c in psutil.Process(pid).net_connections(kind="inet")
        if c.status == psutil.CONN_LISTEN
    ]


# ---- FR-003-01 / FR-003-03 --------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-003-01")
@pytest.mark.req("FR-003-03")
def test_fr_003_01_the_server_listens_on_127_0_0_1_only_and_prints_its_url_with_an_os_assigned_port(world) -> None:
    srv = Server(world)
    try:
        port = srv.wait_url()
        assert port is not None, f"no URL line printed:\n{srv.output}"
        assert 1024 <= port <= 65535
        socks = listening(srv.p.pid)
        assert socks, "the process listens on nothing"
        assert all(ip == "127.0.0.1" for ip, _ in socks), f"every listening socket must be bound to 127.0.0.1: {socks}"
        assert ("127.0.0.1", port) in socks, "the printed port is the bound port"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=10) as r:
            assert r.status == 200
        with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=10) as r:
            assert r.status == 200
        # the machine's other addresses refuse the connection
        others = [
            a.address
            for addrs in psutil.net_if_addrs().values()
            for a in addrs
            if a.family == socket.AF_INET and not a.address.startswith("127.")
        ]
        for ip in others[:3]:
            with pytest.raises(OSError, match=r"(?s).*"):  # refused, timed out or unreachable: any OS-level failure
                socket.create_connection((ip, port), timeout=3).close()
    finally:
        srv.stop()


@pytest.mark.req("FR-003-03")
def test_fr_003_03_the_port_comes_from_the_environment_when_set(world) -> None:
    port = free_port()
    srv = Server(world, env={"PITSTUDIO_CONSOLE_PORT": str(port)})
    try:
        assert srv.wait_url() == port, srv.output
        assert ("127.0.0.1", port) in listening(srv.p.pid)
    finally:
        srv.stop()


@pytest.mark.req("FR-003-03")
def test_fr_003_03_no_port_number_is_hard_coded_in_the_package() -> None:
    src = "\n".join(p.read_text(encoding="utf-8") for p in sorted(API.rglob("*.py")))
    assert src, "api/pitstudio_api does not exist"
    assert not re.search(r"\bport\s*(=|:\s*int\s*=)\s*(80|[1-9]\d{3}|[1-6]\d{4})\b", src), (
        "a default port must never be hard-coded"
    )
    assert not re.search(r"uvicorn\.run\([^)]*port\s*=\s*\d", src), "uvicorn must receive the configured port"
    from pitstudio_api import config

    assert config.parse_port(None) is None, "unset means an OS-assigned port"


@pytest.mark.req("FR-003-03")
@pytest.mark.req("FR-003-04")
@pytest.mark.parametrize(("value", "expected"), [(None, None), ("1024", 1024), ("8765", 8765), ("65535", 65535)])
def test_fr_003_04_valid_port_values(value: str | None, expected: int | None) -> None:
    from pitstudio_api import config

    assert config.parse_port(value) == expected


HOSTILE_PORTS = [
    "abc",
    "80",
    "1023",
    "65536",
    "8765.0",
    "-1",
    "",
    " 8765",
    "8765 ",
    "0x2000",
    "８７６５",
    "1e4",
    "+8765",
    "0",
    "99999999999999999999",
    "8765\n",
    "NaN",
]


@pytest.mark.req("FR-003-04")
@pytest.mark.parametrize("value", HOSTILE_PORTS, ids=[repr(v) for v in HOSTILE_PORTS])
def test_fr_003_04_invalid_port_values_are_rejected(value: str) -> None:
    from pitstudio_api import config

    with pytest.raises(ValueError, match=r"(?s).+"):  # any non-empty message (the wording is not specified)
        config.parse_port(value)


@pytest.mark.req("FR-003-04")
@pytest.mark.parametrize(
    "value", ["abc", "80", "65536", "8765.0", "-1", ""], ids=["abc", "80", "65536", "float", "negative", "empty"]
)
def test_fr_003_04_an_invalid_port_exits_2_naming_the_variable_and_opens_no_socket(world, value: str) -> None:
    srv = Server(world, env={"PITSTUDIO_CONSOLE_PORT": value})
    try:
        assert srv.p.wait(timeout=60) == 2, srv.output
        assert "PITSTUDIO_CONSOLE_PORT" in srv.output
        assert not URL_LINE.search(srv.output), "no URL may be printed for an invalid port"
    finally:
        srv.stop()


@pytest.mark.req("FR-003-04")
def test_fr_003_04_a_port_in_use_exits_3(world) -> None:
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    srv = Server(world, env={"PITSTUDIO_CONSOLE_PORT": str(port)})
    try:
        assert srv.p.wait(timeout=60) == 3, srv.output
    finally:
        srv.stop()
        blocker.close()


# ---- FR-003-02 --------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-003-02")
@pytest.mark.parametrize(
    "host", ["0.0.0.0", "::", "::1", "localhost", "192.168.1.5", "example.org", "", "127.0.0.2", "127.0.0.1 ", "0"]
)
def test_fr_003_02_any_other_host_option_exits_2_naming_it(world, host: str) -> None:
    srv = Server(world, "--host", host)
    try:
        assert srv.p.wait(timeout=60) == 2, srv.output
        assert "--host" in srv.output
        assert not URL_LINE.search(srv.output)
    finally:
        srv.stop()


@pytest.mark.req("FR-003-02")
@pytest.mark.parametrize("value", ["0.0.0.0", "::", "192.168.1.5", "localhost", ""])
def test_fr_003_02_the_host_variable_is_refused_too(world, value: str) -> None:
    srv = Server(world, env={"PITSTUDIO_CONSOLE_HOST": value})
    try:
        assert srv.p.wait(timeout=60) == 2, srv.output
        assert "PITSTUDIO_CONSOLE_HOST" in srv.output
    finally:
        srv.stop()


@pytest.mark.req("FR-003-02")
@pytest.mark.parametrize(
    "args",
    [["--uds", "/tmp/x.sock"], ["--fd", "3"], ["--host=0.0.0.0"], ["--ssl-keyfile", "k.pem"]],
    ids=["uds", "fd", "host-equals", "ssl"],
)
def test_fr_003_02_bind_related_uvicorn_options_are_refused(world, args: list[str]) -> None:
    srv = Server(world, *args)
    try:
        assert srv.p.wait(timeout=60) == 2, srv.output
        assert args[0].split("=")[0] in srv.output
    finally:
        srv.stop()


# ---- FR-003-05 ----------------------------------------------------------------------------------------------------------------------------------
FORBIDDEN_IMPORTS = {"pynvml", "nvidia_smi", "pynvml_utils", "filelock", "subprocess", "multiprocessing"}


@pytest.mark.req("FR-003-05")
def test_fr_003_05_the_package_imports_nothing_that_could_touch_the_gpu_a_lock_or_start_a_process() -> None:
    files = sorted(API.rglob("*.py"))
    assert files, "api/pitstudio_api does not exist"
    for f in files:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            assert not (set(names) & FORBIDDEN_IMPORTS), f"{f.name} imports {set(names) & FORBIDDEN_IMPORTS}"
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("system", "popen", "Popen", "spawn", "execv", "fork")
            ):
                raise AssertionError(f"{f.name} starts a process: {node.func.attr}")


@pytest.mark.req("FR-003-05")
def test_fr_003_05_serving_requests_uses_no_nvml_no_gpu_lock_no_process_and_writes_nothing_but_the_queue(world) -> None:
    from asgi_client import Client
    from filelock import FileLock
    from pitstudio_api.app import create_app

    rw.block_modules(world.monkeypatch, "pynvml")
    calls = rw.forbid_popen(world.monkeypatch)
    taken: list[str] = []
    real_init = FileLock.__init__

    def spy(self, lock_file, *a, **k):
        taken.append(str(lock_file))
        return real_init(self, lock_file, *a, **k)

    world.monkeypatch.setattr(FileLock, "__init__", spy)
    client = Client(create_app(port=8765), 8765)
    before = rw.tree_digest(world.store)
    repo_before = world.snapshot_repo()
    for path in ("/health", "/recipes", "/queue", "/runs"):
        assert client.get(path).status == 200
    r = client.post("/jobs", json_body={"recipe": "pub-case", "profile": "test-profile"})
    assert r.status in (202, 404, 422), r.text
    after = rw.tree_digest(world.store)
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    assert all(k.startswith("queue.db") for k in changed), f"the console wrote outside the queue: {sorted(changed)}"
    assert world.snapshot_repo() == repo_before
    assert calls == [] and not [t for t in taken if "gpu0." in t], taken
