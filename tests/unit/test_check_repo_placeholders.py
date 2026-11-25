"""tools/check_repo.py: a placeholder account in a fixture path is not a machine path; a real-looking one still is."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_repo  # noqa: E402

RX = check_repo.CHECKS["machine path"]
DRIVE = "C" + ":"  # the real-looking paths below are assembled so that this file never matches the rule itself
HOME = "/ho" + "me/"


@pytest.mark.parametrize(
    "line",
    [
        "/home/user/runs/20261007/tmp/in/frames/frame_%05d.png",
        "/home/alice/ps",
        "/home/u/repo/specs/014/contracts/examples/il-task.valid.json",
        DRIVE + "/Users/alice/ps",
        DRIVE + "\\Users\\Bob\\x",
    ],
)
def test_placeholder_accounts_do_not_trip_the_machine_path_check(line: str) -> None:
    assert RX.search(line)  # the raw rule still matches ...
    assert not check_repo.hits("machine path", RX, line)  # ... the placeholder allowance does not report it


@pytest.mark.parametrize(
    "line",
    [
        HOME + "carol/work/x",
        DRIVE + "/Users/dave.smith/Data",
        "see " + HOME + "user/a and " + HOME + "carol/b",
        "/c" + "/Users/erin/x",
    ],
)
def test_real_looking_accounts_still_trip_the_machine_path_check(line: str) -> None:
    assert check_repo.hits("machine path", RX, line)


def test_other_checks_are_unaffected_by_the_allowance() -> None:
    assert check_repo.hits("template residue", check_repo.CHECKS["template residue"], "{{" + "PROJECT_NAME}}")
    assert not check_repo.hits("template residue", check_repo.CHECKS["template residue"], "plain text")
