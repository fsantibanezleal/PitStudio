"""Where things live: the repository root, the contracts folders and the data-root safety rule (FR-008-15)."""

from __future__ import annotations

from pathlib import Path

from pitstudio_pipeline.errors import UnsafeDataRoot

IGNORED_DATA_FOLDERS = ("raw", "external", "interim", "processed", "synthetic")  # git-ignored, see .gitignore


def find_repo_root(start: Path | None = None) -> Path:
    """The working tree that holds `start` (default: this package): the nearest parent with a `.git` entry.

    A worktree has a `.git` file, a clone a `.git` folder; both count.
    """
    here = (start if start is not None else Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / ".git").exists():
            return parent
    return Path(__file__).resolve().parents[3]


def check_data_root(data_root: Path | str, *, repo_root: Path | str | None = None) -> Path:
    """Return the resolved data root, or raise `UnsafeDataRoot` (FR-008-15).

    A root is acceptable when it resolves outside the repository working tree, or inside one of `data/raw`,
    `data/external`, `data/interim`, `data/processed`, `data/synthetic` (children included). Any other path in the
    working tree, `<repo>/data` itself included, is refused: a stage must never write where git could track the result.
    """
    root = Path(data_root).resolve()
    repo = (Path(repo_root) if repo_root is not None else find_repo_root()).resolve()
    if root != repo and repo not in root.parents:
        return root
    data = repo / "data"
    for folder in IGNORED_DATA_FOLDERS:
        allowed = data / folder
        if root == allowed or allowed in root.parents:
            return root
    raise UnsafeDataRoot(
        f"the data root {root.name!r} is inside the repository working tree but outside the git-ignored data folders "
        f"({', '.join('data/' + f for f in IGNORED_DATA_FOLDERS)})"
    )


def default_data_root(repo_root: Path | str | None = None) -> Path:
    """`<repo>/data`: the default root when no argument and no PITSTUDIO_DATA name one (spec 008 section 7)."""
    return (Path(repo_root) if repo_root is not None else find_repo_root()).resolve() / "data"


def resolve_data_root(
    data_root: Path | str | None, env: dict[str, str] | None, repo_root: Path | str | None = None
) -> Path:
    """Root from the argument, else `env["PITSTUDIO_DATA"]`, else the repository default; explicit roots are checked."""
    if data_root is None:
        configured = (env or {}).get("PITSTUDIO_DATA")
        if configured:
            return check_data_root(configured, repo_root=repo_root)
        return default_data_root(repo_root)
    return check_data_root(data_root, repo_root=repo_root)
