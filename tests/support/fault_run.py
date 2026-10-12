"""Test support: run the runner command line in a fresh interpreter with ONE injected write/rename fault.

Usage: python fault_run.py <fail_at> <runner argv...>
  fail_at = -1: count only. Otherwise the fail_at-th (0-based) call to `os.replace`, `os.rename`, `shutil.move` or to
  `open`/`io.open` in a writing mode raises OSError("injected fault ...") once.
The last stdout line is `FAULT-RESULT {"ticks": n, "fired": bool, "code": <int or "exception:<Name>">}`.
Used by tests/unit/test_t_002_021_store.py to prove the store invariants of P-002-06 under every interruption point.
"""

from __future__ import annotations

import builtins
import io
import json
import os
import shutil
import sys


def main() -> None:
    fail_at = int(sys.argv[1])
    argv = sys.argv[2:]
    state = {"n": 0, "fired": False}
    _real_open, _real_replace, _real_rename, _real_move = builtins.open, os.replace, os.rename, shutil.move

    def tick(kind: str) -> None:
        i = state["n"]
        state["n"] += 1
        if i == fail_at and not state["fired"]:
            state["fired"] = True
            raise OSError(f"injected fault at {kind} #{i}")

    def _open(file, mode="r", *a, **k):
        if isinstance(mode, str) and any(c in mode for c in "wax+"):
            tick("open")
        return _real_open(file, mode, *a, **k)

    def _replace(*a, **k):
        tick("replace")
        return _real_replace(*a, **k)

    def _rename(*a, **k):
        tick("rename")
        return _real_rename(*a, **k)

    def _move(*a, **k):
        tick("move")
        return _real_move(*a, **k)

    builtins.open = _open
    io.open = _open
    os.replace = _replace
    os.rename = _rename
    shutil.move = _move

    code: object
    try:
        from pitstudio.runner import cli

        code = cli.main(argv)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 2
    except BaseException as e:
        code = f"exception:{type(e).__name__}:{e}"
    builtins.open, io.open = _real_open, _real_open
    sys.stdout.flush()
    print(
        "FAULT-RESULT "
        + json.dumps(
            {
                "ticks": state["n"],
                "fired": state["fired"],
                "code": code if isinstance(code, (int, str)) else str(code),
            }
        )
    )


if __name__ == "__main__":
    main()
