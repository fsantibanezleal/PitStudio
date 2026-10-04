"""Scaffold invariants: the core package imports and the release version has the X.YY.ZZZ form."""

import re
from pathlib import Path

import pitstudio

ROOT = Path(__file__).resolve().parents[2]


def test_core_package_imports() -> None:
    assert pitstudio.__all__ == []


def test_version_file_format() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d{2}\.\d{3}", version), version
