# ruff: noqa: E501
"""Engine pin file and the guard that refuses on any mismatch (FR-007-02).

The pin holds the engine version, the SHA-256 of every engine module the adapter's seam depends on, and the map from the
engine's callback names to the canonical event kinds of `contracts/des-trace.schema.json` (FR-007-09). A new engine version
or any changed module re-bakes every golden: refresh the file with `python -m pitstudio_pipeline.haulage.pin --write` and
review the diff.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from .errors import EngineVersionMismatch

PIN_PATH = Path(__file__).with_name("engine_pin.json")
PACKAGE = "minehaulsim"
MODULES = (
    "des/sim.py",
    "des/engine.py",
    "des/dispatch.py",
    "des/failures.py",
    "des/traversal.py",
    "des/resources.py",
    "network/kinematics.py",
    "network/routing.py",
    "network/graph.py",
    "equipment/catalog.py",
)  # FR-007-02
CALLBACKS = {
    "_go_load": "arrive-loader",
    "_loaded": "load-end",
    "_depart_loaded": "depart-loaded",
    "_arrive_dump": "arrive-dump",
    "_dumped": "dump-end",
    "_dispatch_next": "dispatch",
    "start_loading": "loader-repair-end",
    "leave": "segment-exit",
    "_release_then": "junction-cross-end",
    "probe": "zone-probe",
    "bin_dump": "bin-dump",
    "_lhd_start": "lhd-start",
    "_lhd_dig": "lhd-dig",
    "_lhd_to_tip": "lhd-to-tip",
    "_lhd_at_tip": "lhd-at-tip",
    "_lhd_after_tip": "lhd-after-tip",
}


def _installed_root() -> Path:
    import minehaulsim

    return Path(minehaulsim.__file__).parent


def _installed_version() -> str:
    import minehaulsim

    return str(minehaulsim.__version__)


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def build_pin(package_root: Path | None = None, version: str | None = None) -> dict:
    """The pin of the installed engine (used to re-bake the file, never at run time)."""
    root = package_root or _installed_root()
    return {
        "package": PACKAGE,
        "version": version or _installed_version(),
        "modules": {rel: _sha256(root / rel) for rel in MODULES},
        "callbacks": dict(CALLBACKS),
    }


def load_pin(path: Path | None = None) -> dict:
    """The parsed pin file (default: the committed one)."""
    return json.loads(Path(path or PIN_PATH).read_text(encoding="utf-8"))


def pin_sha256(path: Path | None = None) -> str:
    """SHA-256 of the pin file's bytes: the `engine.pin_sha256` of every trace header."""
    return hashlib.sha256(Path(path or PIN_PATH).read_bytes()).hexdigest()


def verify_engine(
    pin: dict | None = None, *, package_root: Path | None = None, installed_version: str | None = None
) -> None:
    """Raise EngineVersionMismatch naming every differing item (version, then each module path), else return."""
    pin = pin if pin is not None else load_pin()
    root = package_root or _installed_root()
    version = installed_version if installed_version is not None else _installed_version()
    diffs: list[tuple[str, str, str]] = []
    if version != pin["version"]:
        diffs.append(("version", pin["version"], version))
    for rel, pinned in pin["modules"].items():
        got = _sha256(root / rel)
        if got != pinned:
            diffs.append((rel, pinned, got if got is not None else "missing"))
    if diffs:
        raise EngineVersionMismatch(diffs)


if __name__ == "__main__":
    if sys.argv[1:] == ["--write"]:
        PIN_PATH.write_text(json.dumps(build_pin(), indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {PIN_PATH}")
    else:
        verify_engine()
        print("engine matches its pin")
