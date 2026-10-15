"""Run the studio-environment tests of specs 004, 005, 006 and 013 and fail when any of them is skipped (T-004-002).

Usage:  uv run --project studio --frozen python tools/studio_pytest.py [pytest arguments]
The tests live in the root `tests/` tree and need `pxr`, `rasterio`, `laspy` and friends, which only the studio
environment has; the root CI job skips such modules. This runner collects the test files of those specs, runs them
with `-m "not gpu and not slow"` (plus any extra arguments), and exits non-zero when pytest fails or when one of
those files reports a skipped test, so that a skip in the root job can never hide a missing run.
Exit:    0 all passed and none skipped, 1 a test failed or was skipped, 2 no test file found.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pending_red import load_pending  # noqa: E402
SPECS = ("004", "005", "006", "013")
MIXED_SPECS = ("013",)
STUDIO_MARKERS = ('"studio" / "src"', '"studio" / "rtx" / "src"', '"studio" / "isaac" / "src"')


def test_files() -> list[Path]:
    found: list[Path] = []
    pending = set(load_pending(ROOT))  # tasks without a green commit are not selected (specs/pending-red.txt)
    for spec in SPECS:
        files = sorted((ROOT / "tests").rglob(f"test_t_{spec}_*.py"))
        if spec in MIXED_SPECS:  # spec 013 also has root-environment tests: keep those that need a studio environment
            files = [f for f in files if any(m in f.read_text(encoding="utf-8") for m in STUDIO_MARKERS)]
        found.extend(f for f in files if f.relative_to(ROOT).as_posix() not in pending)
    return found


def skipped_in(report: Path) -> list[str]:
    tree = ET.parse(report)
    return [
        f"{case.get('classname')}::{case.get('name')}"
        for case in tree.iter("testcase")
        if case.find("skipped") is not None
    ]


def main(argv: list[str]) -> int:
    marker = "not gpu and not slow"
    rest = argv[1:]
    if rest[:1] == ["--marker"] and len(rest) >= 2:
        marker, rest = rest[1], rest[2:]
    files = test_files()
    if not files:
        print("no test file of specs 004, 005, 006 and 013 found")
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "junit.xml"
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            marker,
            f"--junitxml={report}",
            *rest,
            *(str(f) for f in files),
        ]
        code = subprocess.run(command, cwd=ROOT, check=False).returncode
        skipped = skipped_in(report) if report.is_file() else []
    for name in skipped:
        print(f"SKIPPED in the studio job: {name}")
    return 1 if code or skipped else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
