"""T-019-093: the generated studio index is capped at 1,000,000 bytes, in the loader, in the CI size check and in the
cap table.

Requirements: FR-019-47 (hostile-input class found by the G5 review; NFR-019-03 gives the number).

Spec: specs/019-web-studio/ (spec.md FR-019-47 and NFR-019-03, plan.md test strategy row "FR-019-47", tasks.md
T-019-093); the cap table is data-model 001 section 1.4 (FR-001-05).

Expected API of the implementation (module `tools/check_studio.py`, the same module as T-019-092; flagged in the red
report because the spec names no Python module for the CI size check):
  INDEX_CAP_BYTES == 1_000_000
  check_index_size(path: Path, root: Path | None = None) -> list[Finding]
                                                     Finding.check == "studio-index-too-large"; Finding.subject is the
                                                     POSIX path of `path` relative to `root` (the path itself when
                                                     `root` is None); Finding.detail names the size in bytes
  CLI: `python tools/check_studio.py --root DIR` also checks DIR/web/public/studio/index.json when it exists (a
  missing file is not an error: nothing was generated yet); exit 1 and the line
  "studio-index-too-large: <relative path>: <size>" when the file has more than 1,000,000 bytes.
The web loader half is `web/src/studio/t_019_093_index_loader.test.ts`. The doc half: the cap table of data-model 001
section 1.4 lists `web/public/studio/index.json` with 1,000,000.

Oracle: byte arithmetic (the cap is 1,000,000; the boundary files hold 1,000,000 and 1,000,001 bytes; bytes, not
characters, are counted: a two-byte character such as U+00E9 weighs 2).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "check_studio.py"
sys.path.insert(0, str(ROOT / "tools"))
CAP = 1_000_000


def _mod():
    assert TOOL.is_file(), "tools/check_studio.py exists (T-019-092 / T-019-093)"
    import check_studio

    return check_studio


def _file(tmp_path: Path, size: int, name: str = "index.json") -> Path:
    p = tmp_path / name
    # a valid JSON document padded with trailing whitespace to the exact size
    body = b'{"schema_version": "1.0"}'
    p.write_bytes(body + b" " * (size - len(body)))
    assert p.stat().st_size == size
    return p


@pytest.mark.req("FR-019-47")
def test_the_cap_is_one_million_bytes() -> None:
    assert _mod().INDEX_CAP_BYTES == CAP


@pytest.mark.req("FR-019-47")
def test_a_file_of_exactly_the_cap_is_accepted(tmp_path: Path) -> None:
    assert _mod().check_index_size(_file(tmp_path, CAP)) == []


@pytest.mark.req("FR-019-47")
def test_a_file_one_byte_over_the_cap_is_rejected_naming_the_file_and_the_size(tmp_path: Path) -> None:
    found = _mod().check_index_size(_file(tmp_path, CAP + 1))
    assert [f.check for f in found] == ["studio-index-too-large"]
    assert "index.json" in found[0].subject
    assert str(CAP + 1) in found[0].detail


@pytest.mark.req("FR-019-47")
@pytest.mark.parametrize("size", [25, 26, 999_999, 500_000])
def test_smaller_files_are_accepted(tmp_path: Path, size: int) -> None:
    assert _mod().check_index_size(_file(tmp_path, size)) == []


@pytest.mark.req("FR-019-47")
def test_an_empty_file_is_not_a_size_violation(tmp_path: Path) -> None:
    p = tmp_path / "index.json"
    p.write_bytes(b"")
    assert _mod().check_index_size(p) == []


@pytest.mark.req("FR-019-47")
def test_bytes_not_characters_are_counted(tmp_path: Path) -> None:
    m = _mod()
    over = tmp_path / "over.json"
    over.write_bytes(b'"' + "é".encode() * 499_999 + b'"' + b"  ")  # 1 + 999,998 + 1 + 2 = 1,000,002 bytes
    assert over.stat().st_size == CAP + 2
    assert [f.check for f in m.check_index_size(over)] == ["studio-index-too-large"]
    exact = tmp_path / "exact.json"
    exact.write_bytes(b'"' + "é".encode() * 499_999 + b'"')  # 1,000,000 bytes, only 500,001 characters
    assert exact.stat().st_size == CAP
    assert m.check_index_size(exact) == []


@pytest.mark.req("FR-019-47")
def test_a_missing_path_raises_a_clear_error_not_a_size_finding(tmp_path: Path) -> None:
    with pytest.raises((FileNotFoundError, OSError)):
        _mod().check_index_size(tmp_path / "no-such.json")


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    assert TOOL.is_file(), "tools/check_studio.py exists (T-019-092 / T-019-093)"
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=120, check=False)


def _root_with_index(tmp_path: Path, size: int | None) -> Path:
    (tmp_path / "studio").mkdir(parents=True)
    (tmp_path / "studio" / "toolmap.yaml").write_text("bands: []\nedges: []\n", encoding="utf-8")
    (tmp_path / "studio" / "tools.yaml").write_text("tools: []\n", encoding="utf-8")
    if size is not None:
        (tmp_path / "web" / "public" / "studio").mkdir(parents=True)
        _file(tmp_path / "web" / "public" / "studio", size)
    return tmp_path


@pytest.mark.req("FR-019-47")
def test_cli_rejects_an_oversized_index_and_names_the_relative_path(tmp_path: Path) -> None:
    done = _cli("--root", str(_root_with_index(tmp_path, CAP + 1)))
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"studio-index-too-large: web/public/studio/index.json: {CAP + 1}" in done.stdout
    assert "Traceback" not in done.stderr


@pytest.mark.req("FR-019-47")
def test_cli_accepts_an_index_at_the_cap_and_a_missing_index(tmp_path: Path) -> None:
    assert _cli("--root", str(_root_with_index(tmp_path / "a", CAP))).returncode == 0
    assert _cli("--root", str(_root_with_index(tmp_path / "b", None))).returncode == 0


@pytest.mark.req("FR-019-47")
def test_the_cap_table_of_the_contracts_lists_the_studio_index() -> None:
    text = (ROOT / "specs" / "001-contracts" / "data-model.md").read_text(encoding="utf-8")
    section = text.split("### 1.4 Size caps", 1)[1].split("###", 1)[0]
    rows = [ln for ln in section.splitlines() if ln.startswith("|") and "web/public/studio/index.json" in ln]
    assert len(rows) == 1, "one row for the generated studio index"
    cells = [c.strip() for c in rows[0].strip("|").split("|")]
    assert re.fullmatch(r"1,000,000", cells[1])
