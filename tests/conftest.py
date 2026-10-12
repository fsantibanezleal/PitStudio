"""Collection by environment ownership (tests/envs.yaml): a run ignores the test files that another environment owns.

The running environment is named by PITSTUDIO_TEST_ENV (root, pipeline or studio; default root). Ownership is
explicit and complete: there is no skip, no xfail and no import guard involved. A file that cannot import in the
environment that owns it is a mistake in the map or in the lock, not something to hide.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
ENVS = ("root", "pipeline", "studio")


def load_owners() -> list[tuple[str, str]]:
    """(glob, owner) pairs of tests/envs.yaml in file order."""
    data = yaml.safe_load((Path(__file__).with_name("envs.yaml")).read_text(encoding="utf-8")) or {}
    return [(glob, owner) for owner, globs in data.items() for glob in globs]


def matches(relative: str, glob: str) -> bool:
    return fnmatch.fnmatchcase(relative, glob) or (glob.endswith("/**") and relative.startswith(glob[:-2]))


def owner_of(relative: str, owners: list[tuple[str, str]]) -> str:
    """The environment that owns the repository-relative POSIX path `relative` (root when nothing matches)."""
    return next((owner for glob, owner in owners if matches(relative, glob)), "root")


def running_env() -> str:
    env = os.environ.get("PITSTUDIO_TEST_ENV", "root")
    if env not in ENVS:
        raise RuntimeError(f"PITSTUDIO_TEST_ENV must be one of {ENVS}, got {env!r}")
    return env


_OWNERS = load_owners()


def pytest_ignore_collect(collection_path: Path, config) -> bool | None:
    if collection_path.suffix != ".py":
        return None
    try:
        relative = collection_path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return None
    return True if owner_of(relative, _OWNERS) != running_env() else None
