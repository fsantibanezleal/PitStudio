# ruff: noqa: E501
"""T-013-018: clean-room repository scan (SPDX headers, NVIDIA notices, NVIDIA asset references) and the adapter line budget.

Requirements: FR-013-33, NFR-013-04.

Oracle: a text scan of the repository (plan.md "FR-013-33": repository scan over `studio/rtx/` and the isaac sensor backend,
with a planted-violation fixture proving the scanner sees each violation); the forbidden notices are the three strings of the
spec; "lines of code" of the `ovrtx` backend module is counted with `tokenize` (lines holding at least one token other than
comments, blank lines and docstrings' own string-only lines are not counted separately: a physical line counts when it carries
a NAME, NUMBER, OP or non-docstring STRING token).

Expected files (the lane of spec 013): every `.py` under `studio/rtx/src/pitstudio_rtx/` and
`studio/isaac/src/pitstudio_isaac/sensor_backend.py` starts (within its first 5 lines) with `# SPDX-License-Identifier:
Apache-2.0` and carries none of "This software contains source code provided by NVIDIA Corporation", "NVIDIA CORPORATION &
AFFILIATES. All rights reserved" or `LicenseRef-NvidiaProprietary` in its first 30 lines; no sensor recipe under
`studio/recipes/` and no `.usd*` scene text under `studio/` references an NVIDIA sensor or scene asset (`omniverse://`, an
`nvidia` path segment, `NVIDIA/Assets`, `Isaac/Sensors`); `studio/rtx/src/pitstudio_rtx/backends/ovrtx_backend.py` has at most
400 lines of code.
"""

from __future__ import annotations

import io
import re
import sys
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RTX_SRC = ROOT / "studio" / "rtx" / "src" / "pitstudio_rtx"
ISAAC_BACKEND = ROOT / "studio" / "isaac" / "src" / "pitstudio_isaac" / "sensor_backend.py"
OVRTX_BACKEND = RTX_SRC / "backends" / "ovrtx_backend.py"
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))

SPDX = re.compile(r"^#\s*SPDX-License-Identifier:\s*Apache-2\.0\s*$")
NOTICES = (
    "This software contains source code provided by NVIDIA Corporation",
    "NVIDIA CORPORATION & AFFILIATES. All rights reserved",
    "LicenseRef-NvidiaProprietary",
)
ASSET_REFERENCE = re.compile(
    r"omniverse://|nvidia/assets|isaac/sensors|/nvidia/|nvidia_sensor|NVIDIA/Assets", re.IGNORECASE
)


def source_files() -> list[Path]:
    files = sorted(RTX_SRC.rglob("*.py")) if RTX_SRC.is_dir() else []
    return files + ([ISAAC_BACKEND] if ISAAC_BACKEND.is_file() else [])


def header_violations(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    problems = []
    if not any(SPDX.match(line) for line in lines[:5]):
        problems.append("missing SPDX-License-Identifier: Apache-2.0 header")
    head = "\n".join(lines[:30])
    problems += [f"forbidden notice: {n}" for n in NOTICES if n.lower() in head.lower()]
    return problems


def lines_of_code(path: Path) -> int:
    code_lines: set[int] = set()
    prev_significant = None
    for tok in tokenize.generate_tokens(io.StringIO(path.read_text(encoding="utf-8")).readline):
        if tok.type in (
            tokenize.COMMENT,
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENDMARKER,
        ):
            continue
        is_docstring = tok.type == tokenize.STRING and (
            prev_significant is None or prev_significant in (":", "<start>")
        )
        if not is_docstring:
            code_lines.update(range(tok.start[0], tok.end[0] + 1))
        prev_significant = tok.string if tok.type == tokenize.OP else "<start>" if tok.type == tokenize.STRING else "x"
    return len(code_lines)


@pytest.mark.req("FR-013-33")
def test_every_lane_source_file_has_the_apache_header_and_no_nvidia_notice() -> None:
    files = source_files()
    names = {p.name for p in files}
    assert {
        "backend.py",
        "lane.py",
        "shards.py",
        "rerun.py",
        "fake.py",
        "ovrtx_backend.py",
        "sensor_backend.py",
    } <= names
    report = {str(p.relative_to(ROOT)): header_violations(p) for p in files if header_violations(p)}
    assert report == {}


@pytest.mark.req("FR-013-33")
def test_no_recipe_or_scene_of_the_lane_references_an_nvidia_asset() -> None:
    folder = ROOT / "studio"
    texts = [p for pattern in ("recipes/**/*.yaml", "**/*.usda") for p in folder.glob(pattern)]
    offenders = {
        str(p.relative_to(ROOT)): m.group(0)
        for p in texts
        if (m := ASSET_REFERENCE.search(p.read_text(encoding="utf-8", errors="replace")))
    }
    assert offenders == {}
    assert len(source_files()) >= 7  # the scan above is only meaningful once the lane files exist


@pytest.mark.req("FR-013-33")
def test_the_scanner_catches_each_planted_violation(tmp_path: Path) -> None:
    clean = tmp_path / "clean.py"
    clean.write_text('# SPDX-License-Identifier: Apache-2.0\n"""ok"""\n', encoding="utf-8")
    assert header_violations(clean) == []
    no_header = tmp_path / "a.py"
    no_header.write_text('"""doc"""\nx = 1\n', encoding="utf-8")
    assert header_violations(no_header) == ["missing SPDX-License-Identifier: Apache-2.0 header"]
    for notice in NOTICES:
        planted = tmp_path / "b.py"
        planted.write_text(f"# SPDX-License-Identifier: Apache-2.0\n# {notice}\n", encoding="utf-8")
        assert header_violations(planted) == [f"forbidden notice: {notice}"]
    wrong = tmp_path / "c.py"
    wrong.write_text("# SPDX-License-Identifier: LicenseRef-NvidiaProprietary\n", encoding="utf-8")
    assert len(header_violations(wrong)) == 2  # not Apache-2.0, and the proprietary identifier
    assert ASSET_REFERENCE.search("sensor: omniverse://localhost/NVIDIA/Assets/Sensors/x.usd")


@pytest.mark.req("NFR-013-04")
def test_the_ovrtx_adapter_is_a_thin_module_of_at_most_400_lines_of_code() -> None:
    assert OVRTX_BACKEND.is_file()
    assert 0 < lines_of_code(OVRTX_BACKEND) <= 400


@pytest.mark.req("NFR-013-04")
def test_the_line_counter_ignores_comments_blank_lines_and_docstrings(tmp_path: Path) -> None:
    sample = tmp_path / "s.py"
    sample.write_text(
        '"""module docstring\nspanning lines"""\n# comment\n\nx = 1\n\ndef f(a,\n      b):\n    """doc"""\n    return a + b\n',
        encoding="utf-8",
    )
    assert lines_of_code(sample) == 4  # `x = 1`, the two lines of the signature and `return a + b`
