"""CI check of the committed data (spec 008, FR-008-45 and NFR-008-03).

Usage:  python tools/check_data.py      (exit 1 on any finding)
Two rules, both on what git tracks:
- `data/samples/` holds only public-domain or CC0 crops and synthetic fixtures, each with a sample card
  `<file>.card.md` (YAML front matter with a non-empty `source` and a `licence`: LicenseRef-USGov-PD, CC0-1.0 or
  synthetic), each under 1 MB, and nothing from the Mendeley set (that set publishes metrics only);
- no tracked file under `data/raw/`, `data/external/`, `data/interim/`, `data/processed/` or `data/synthetic/`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_LICENCES = frozenset({"LicenseRef-USGov-PD", "CC0-1.0", "synthetic"})
DATA_ROOTS = ("raw", "external", "interim", "processed", "synthetic")
MAX_SAMPLE_BYTES = 1_000_000
_MENDELEY = re.compile(r"mendeley|78ht3pjsr4", re.IGNORECASE)
_FRONT = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.DOTALL)


def _card_problem(card: Path) -> str | None:
    """Why the sample card is unusable, or None; reads the front matter only."""
    try:
        text = card.read_text(encoding="utf-8").replace("\r\n", "\n")
    except OSError, UnicodeDecodeError:
        return "the sample card is unreadable"
    found = _FRONT.match(text)
    if found is None:
        return "the sample card has no YAML front matter"
    try:
        front = yaml.safe_load(found.group(1) + "\n")
    except yaml.YAMLError:
        return "the sample card front matter is not valid YAML"
    if not isinstance(front, dict):
        return "the sample card front matter is not a mapping"
    source, licence = front.get("source"), front.get("licence")
    if not isinstance(source, str) or not source.strip():
        return "the sample card names no source"
    if licence not in SAMPLE_LICENCES:
        return f"the sample card licence {licence!r} is not one of {', '.join(sorted(SAMPLE_LICENCES))}"
    if _MENDELEY.search(source):
        return "the sample card names the Mendeley set, which publishes metrics only"
    return None


def check_samples(samples_dir: Path | str) -> list[str]:
    """One message per problem of the samples folder, each naming the sample file (POSIX path inside the folder)."""
    base = Path(samples_dir)
    problems = []
    for path in sorted(p for p in base.rglob("*") if p.is_file()):
        rel = path.relative_to(base).as_posix()
        if rel == "README.md" or path.name.endswith(".card.md"):
            continue
        if _MENDELEY.search(path.name):
            problems.append(f"{rel}: a Mendeley image, mask or crop is not allowed in the samples")
        if path.stat().st_size >= MAX_SAMPLE_BYTES:
            problems.append(f"{rel}: {path.stat().st_size} bytes, a sample must be under 1 MB")
        card = path.with_name(path.name + ".card.md")
        if not card.is_file():
            problems.append(f"{rel}: no sample card {rel}.card.md")
            continue
        why = _card_problem(card)
        if why:
            problems.append(f"{rel}: {why}")
    return problems


def check_tracked(paths: list[str]) -> list[str]:
    """One message per tracked path under a git-ignored data root (separators of either kind)."""
    prefixes = tuple(f"data/{name}/" for name in DATA_ROOTS)
    return [
        f"{rel}: tracked file under a git-ignored data root (third-party data is never committed)"
        for rel in (p.replace("\\", "/") for p in paths)
        if rel.startswith(prefixes)
    ]


def main() -> int:
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout.splitlines()
    problems = check_tracked(tracked) + [f"data/samples/{m}" for m in check_samples(ROOT / "data" / "samples")]
    if problems:
        print(f"DATA CHECK FAIL ({len(problems)}):")
        for problem in problems:
            print(f"  [x] {problem}")
        return 1
    print("DATA CHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
