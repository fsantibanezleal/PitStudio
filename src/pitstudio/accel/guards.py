"""Engine, cache and local-only guards, and the CI configuration check (FR-016-22, FR-016-33, NFR-016-06)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml


class GuardError(Exception):
    """A write or a published file that breaks an engine, cache or licence rule."""


_ENGINE_SUFFIXES = (".plan", ".engine", ".trt")


def _name(path: str) -> str:
    return PureWindowsPath(path).name if "\\" in path else PurePosixPath(path).name


def _forbidden(path: str) -> bool:
    name = _name(path).lower()
    return name.endswith(_ENGINE_SUFFIXES) or ("timing" in name and "cache" in name)


def find_forbidden_artefacts(paths: Iterable[str]) -> list[str]:
    """Engine plans and timing caches among `paths` (POSIX or Windows separators), sorted, each once."""
    return sorted({p for p in paths if _forbidden(p)})


def scan_tree(root: Path) -> list[str]:
    """Relative POSIX paths of the forbidden artefacts under `root`."""
    found = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
    return find_forbidden_artefacts(found)


def assert_under_run_folder(path: Path, run_dir: Path) -> None:
    """Engines and timing caches are written only inside the run folder (links are resolved)."""
    if not Path(path).resolve().is_relative_to(Path(run_dir).resolve()):
        raise GuardError(f"{path} is outside the run folder {run_dir}")


def _holds_local_only(node: Any) -> bool:
    if isinstance(node, dict):
        return node.get("performance") == "local-only" or any(_holds_local_only(v) for v in node.values())
    if isinstance(node, list):
        return any(_holds_local_only(v) for v in node)
    return False


def find_local_only_records(root: Path, *, local_dir: Path) -> list[Path]:
    """JSON files under `root`, outside `local_dir`, that hold a record with `performance == "local-only"`."""
    local = Path(local_dir).resolve()
    found: list[Path] = []
    for path in sorted(Path(root).rglob("*.json")):
        if path.resolve().is_relative_to(local):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if _holds_local_only(data):
            found.append(path)
    return found


def check_ci_workflows(workflows_dir: Path) -> list[str]:
    """Problems of the CI configuration: GPU stages and GPU tests never run on hardware in CI (NFR-016-06)."""
    problems: list[str] = []
    files = sorted([*Path(workflows_dir).glob("*.yml"), *Path(workflows_dir).glob("*.yaml")])
    for file in files:
        try:
            doc = yaml.safe_load(file.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            problems.append(f"{file.name}: unreadable workflow ({type(exc).__name__})")
            continue
        jobs = doc.get("jobs") if isinstance(doc, dict) else None
        if not isinstance(jobs, dict):
            problems.append(f"{file.name}: no jobs mapping")
            continue
        for job, body in jobs.items():
            if not isinstance(body, dict):
                continue
            runs_on = str(body.get("runs-on", "")).lower()
            if "gpu" in runs_on or "self-hosted" in runs_on:
                problems.append(f"{file.name} job {job}: runs on a GPU or self-hosted runner ({body.get('runs-on')})")
            for step in body.get("steps") or []:
                run = str(step.get("run", "")) if isinstance(step, dict) else ""
                if "pytest" in run and "not gpu" not in run:
                    problems.append(f"{file.name} job {job}: pytest without the `not gpu` selection")
                for stage in ("s62_accel", "s64_bench"):
                    if stage in run and "fake" not in run:
                        problems.append(f"{file.name} job {job}: {stage} without the fake GPU backend")
    return problems
