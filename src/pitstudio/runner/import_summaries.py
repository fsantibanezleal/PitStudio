"""Derived outputs of `studio import-run`: small published summaries and results bundles computed from the files of a
finished job (never from memory). A builder reads the job's `--from` folder and returns the bytes of the derived file;
a source it needs but cannot find raises `Missing`, which the import reports as a usage error naming the file.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path


class Missing(Exception):
    """A file or field the builder needs is absent."""


BUILDERS: dict[str, Callable[[Path], dict]] = {}


def build(name: str, src: Path) -> bytes:
    if name not in BUILDERS:
        raise Missing(f"unknown builder {name}")
    return (json.dumps(BUILDERS[name](src), indent=1, sort_keys=True) + "\n").encode("utf-8")
