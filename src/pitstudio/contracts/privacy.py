"""Privacy scan of contract strings (FR-001-15, FR-001-59, data-model 1.5).

A string leaks when it holds an absolute path or the host name, user name or home directory of the machine that runs
the check. The scrubbed forms ``<repo>/...`` and ``~/...`` are allowed.
"""

from __future__ import annotations

import getpass
import os
import re
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ABSOLUTE_PATH_RULES = (
    re.compile(r"[A-Za-z]:[\\/]"),
    re.compile(r"\\\\[A-Za-z0-9._$-]+\\"),
    re.compile(r"""(^|[\s"'=(,:])/(home|Users|root|tmp|var|mnt|media|opt|srv|private|run)/"""),
    re.compile(r"file:/"),
)
MIN_IDENTITY_CHARS = 3
_IDENTITY_ENV = ("USER", "USERNAME", "LOGNAME", "LNAME", "HOME", "USERPROFILE")


def has_absolute_path(text: str) -> bool:
    return any(rule.search(text) for rule in ABSOLUTE_PATH_RULES)


def scrub_paths(text: str) -> str:
    """Replace every absolute-path-looking token of ``text`` with ``<path>``."""
    for rule in ABSOLUTE_PATH_RULES:
        text = re.sub(rf"(?:{rule.pattern})\S*", "<path>", text)
    return text


def machine_identity() -> list[str]:
    """Host name, user name and home directory of this process, lower-cased, at least three characters each."""
    values: list[str] = [socket.gethostname()]
    values.extend(os.environ.get(name, "") for name in _IDENTITY_ENV)
    for getter in (getpass.getuser, lambda: str(Path.home())):
        try:
            values.append(getter())
        except KeyError, OSError, RuntimeError:
            continue
    out: list[str] = []
    for value in values:
        for form in {value, value.replace("\\", "/"), value.replace("/", "\\")}:
            form = form.strip().lower()
            if len(form) >= MIN_IDENTITY_CHARS and form not in out:
                out.append(form)
    return out


def leaks(text: str, identity: list[str] | None = None) -> str | None:
    """Why ``text`` leaks (``absolute path`` or ``machine identity``), or None when it is clean."""
    if has_absolute_path(text):
        return "absolute path"
    lowered = text.lower()
    if any(item in lowered for item in (machine_identity() if identity is None else identity)):
        return "machine identity (host, user or home directory)"
    return None


def iter_strings(value: Any, pointer: str = "") -> Iterator[tuple[str, str]]:
    """Every string value of a document with its JSON pointer (object keys are not scanned)."""
    stack: list[tuple[Any, str]] = [(value, pointer)]
    while stack:
        node, at = stack.pop()
        if isinstance(node, str):
            yield at, node
        elif isinstance(node, dict):
            for key, child in node.items():
                stack.append((child, at + "/" + str(key).replace("~", "~0").replace("/", "~1")))
        elif isinstance(node, list):
            for index, child in enumerate(node):
                stack.append((child, f"{at}/{index}"))
