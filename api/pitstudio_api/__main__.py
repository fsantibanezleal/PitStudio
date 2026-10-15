"""`python -m pitstudio_api`: serve the console on 127.0.0.1 only (FR-003-01..04, 21)."""

from __future__ import annotations

import os
import socket
import sys

import uvicorn

from pitstudio_api import config
from pitstudio_api.app import create_app


class Server(uvicorn.Server):
    """uvicorn that prints the console URL once it is accepting connections."""

    def __init__(self, config: uvicorn.Config, port: int) -> None:
        super().__init__(config)
        self.port = port

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets)
        print(f"http://127.0.0.1:{self.port}/ui/", flush=True)


def fail(code: int, text: str) -> int:
    print(f"pitstudio_api: {text}", file=sys.stderr, flush=True)
    return code


def main(argv: list[str]) -> int:
    """Exit 2 for an option or variable that asks for another address, port or origin; exit 3 when the port is taken."""
    args = iter(argv)
    for arg in args:
        name, _, inline = arg.partition("=")
        value = inline if "=" in arg else next(args, None)
        if name != "--host" or value != config.HOST:
            return fail(2, f"unsupported option {name}: the console binds {config.HOST} and takes no other bind option")
    if (host := os.environ.get("PITSTUDIO_CONSOLE_HOST")) is not None and host != config.HOST:
        return fail(2, f"PITSTUDIO_CONSOLE_HOST must be unset or {config.HOST}, got {host[:40]!r}")
    try:
        wanted = config.parse_port(os.environ.get("PITSTUDIO_CONSOLE_PORT"))
        allow = config.parse_allow_origins(os.environ.get("PITSTUDIO_CONSOLE_ALLOW_ORIGINS"))
    except ValueError as e:
        return fail(2, str(e))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((config.HOST, wanted or 0))
    except OSError as e:
        sock.close()
        return fail(3, f"cannot bind {config.HOST}:{wanted}: {e.strerror or e}")
    port = sock.getsockname()[1]
    server = Server(
        uvicorn.Config(create_app(port=port, allow_origins=allow), log_level="warning", access_log=False), port
    )
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
