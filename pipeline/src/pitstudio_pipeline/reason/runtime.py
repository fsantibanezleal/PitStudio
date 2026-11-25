"""Pin verification of the llama.cpp b11381 runtime (FR-015-01, FR-015-02).

The reason lane runs only binaries whose SHA-256 is pinned in `studio/reason/pins.json`
(`contracts/reason-pins.schema.json`): both release archives (kept outside the repository) and every executable the
lane invokes, unpacked outside the repository. A missing or altered file, or an invalid pin file, is a `PinError`
(exit code 2) that names the file; the stages check before they start any process.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitstudio.reason import _schemas
from pitstudio_pipeline.download.hashing import sha256_file

PINS_FILE = "pins.json"
SCHEMA = "reason-pins.schema.json"
BUILD = "b11381"
EXIT_CODE = 2


class PinError(Exception):
    """A pinned file is missing or differs from its pin, or the pin file is invalid; `file` names it."""

    exit_code = EXIT_CODE

    def __init__(self, file: str, reason: str) -> None:
        super().__init__(f"{file}: {reason}")
        self.file = file
        self.reason = reason


@dataclass(frozen=True)
class VerifiedRuntime:
    """A runtime whose archives and executables matched their pins."""

    build: str
    runtime_dir: Path
    executables: Mapping[str, Path]

    def executable(self, name: str) -> Path:
        """The path of a pinned executable (KeyError for a name that is not pinned)."""
        return self.executables[name]


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite JSON constant {name}")


def load_pins(path: Path | str) -> dict[str, Any]:
    """Read the pin file and validate it against the contract; any problem is a `PinError` naming `pins.json`."""
    try:
        text = Path(path).read_bytes().decode("utf-8")
        doc = json.loads(text, parse_constant=_reject_constant)
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise PinError(PINS_FILE, f"cannot read the pin file: {type(exc).__name__}") from None
    problems = _schemas.errors(doc, SCHEMA)
    if problems:
        shown = "; ".join(f"{_schemas.pointer(e)}: {e.message[:120]}" for e in problems[:5])
        raise PinError(PINS_FILE, f"invalid against {SCHEMA}: {shown}")
    if not isinstance(doc, dict):  # unreachable after the schema (type object), kept for the type checker
        raise PinError(PINS_FILE, "not a JSON object")
    return doc


def _check_file(path: Path, name: str, sha256: str, size: int | None = None) -> None:
    if not path.is_file():
        raise PinError(name, f"{path} is missing or is not a file")
    if size is not None and path.stat().st_size != size:
        raise PinError(name, f"{path} has {path.stat().st_size} bytes, the pin says {size}")
    if sha256_file(path) != sha256:
        raise PinError(name, f"{path} has a SHA-256 that differs from the pin")


def verify_runtime(
    pins: Mapping[str, Any], *, archive_dir: Path, runtime_dir: Path, repo_root: Path
) -> VerifiedRuntime:
    """Verify both archives in `archive_dir` and every pinned executable in `runtime_dir` (outside `repo_root`)."""
    llama = pins["llamacpp"]
    runtime_path, repo_path = Path(runtime_dir).resolve(), Path(repo_root).resolve()
    if runtime_path == repo_path or repo_path in runtime_path.parents:
        raise PinError("runtime_dir", f"{runtime_path} lies inside the repository; unpack the runtime outside it")
    for key in ("binaries", "cudart"):
        pin = llama["archives"][key]
        _check_file(Path(archive_dir) / pin["name"], pin["name"], pin["sha256"], pin["bytes"])
    executables = {}
    for name, digest in llama["executables"].items():
        _check_file(Path(runtime_dir) / name, name, digest)
        executables[name] = Path(runtime_dir) / name
    return VerifiedRuntime(llama["build"], Path(runtime_dir), executables)
