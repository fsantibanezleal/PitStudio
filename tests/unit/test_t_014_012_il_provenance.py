# ruff: noqa: E501
"""T-014-012: repository scan of task code (SPDX headers, no copied Isaac Lab source markers, no NVIDIA or Isaac Lab asset references).

Requirements: NFR-014-05.

Spec: specs/014-robot-learning/spec.md NFR-014-05: "Provenance of task code: Apache-2.0 SPDX header on every file; no copied Isaac Lab source; no NVIDIA or Isaac Lab asset referenced by any task or recipe | CI repository scan".
Plan: "NFR-014-05 | unit | repository scan with a planted-violation fixture". Licence hygiene (plan): Isaac Lab is BSD-3 and its robot assets are NVIDIA-licensed, so the task code is written from scratch under Apache-2.0 and uses only
procedurally generated machines.

Oracle: planted-violation fixture trees written by hand (each file carries exactly the violations listed in the expected result, with 1-based line numbers counted in the fixture text) and the same scan over the real repository,
which must be clean once the task code exists.

Rules (the spec gives the intent, the details here are the test's reading, see the red report):
    spdx          a task-code file (.py, .ts, .tsx under the scan roots) has `SPDX-License-Identifier: Apache-2.0` as the whole identifier in a comment of its first 10 lines (a shebang may come first); an empty file,
                  another identifier (MIT, BSD-3-Clause, an `OR` expression) or a header after line 10 is a violation at line 1
    copied_source a task-code file contains an Isaac Lab licence marker: "Isaac Lab Project Developers", "Copyright (c) 2022", or the identifier BSD-3-Clause; reported at the line of the first marker
    asset         a task-code file or a recipe (.yaml, .yml under studio/recipes) references an NVIDIA or Isaac Lab asset: `isaaclab_assets`, `ISAAC_NUCLEUS_DIR`, `ISAACLAB_NUCLEUS_DIR`, `omniverse://`, `Isaac/IsaacLab`,
                  `nucleus`-server URLs (`/NVIDIA/`, `nvidia.com/...usd`); reported at the line of each match

Expected API of the implementation (module `pitstudio.robots.provenance`, standard library only):
    SCAN_ROOTS = ("studio/isaaclab/src", "src/pitstudio/robots", "pipeline/src/pitstudio_pipeline/evaluate", "web/src/engines/robots", "studio/recipes")
    Violation: frozen dataclass (path: str relative to the repository root in POSIX form, line: int, rule: str, text: str)
    scan_repository(repo_root) -> list[Violation]
        scans every file under the SCAN_ROOTS that exist below repo_root (a missing root is skipped), skipping __pycache__, node_modules and .venv folders; the .py, .ts and .tsx files get all three rules, the .yaml and .yml
        files of studio/recipes get the asset rule only; the result is sorted by (path, line, rule); ValueError naming `repo_root` when it is not a directory, and naming the file for a file that cannot be decoded as UTF-8
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pitstudio.robots.provenance import SCAN_ROOTS, Violation, scan_repository

ROOT = Path(__file__).resolve().parents[2]
HEADER = "# SPDX-License-Identifier: Apache-2.0\n"
TS_HEADER = "// SPDX-License-Identifier: Apache-2.0\n"


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def keys(violations) -> list[tuple[str, int, str]]:
    return [(v.path, v.line, v.rule) for v in violations]


@pytest.mark.req("NFR-014-05")
def test_the_scan_roots_are_the_task_code_folders() -> None:
    assert SCAN_ROOTS == (
        "studio/isaaclab/src", "src/pitstudio/robots", "pipeline/src/pitstudio_pipeline/evaluate", "web/src/engines/robots", "studio/recipes",
    )  # fmt: skip


@pytest.mark.req("NFR-014-05")
def test_a_clean_fixture_tree_has_no_violation(tmp_path: Path) -> None:
    write(tmp_path, "src/pitstudio/robots/fee.py", HEADER + '"""FEE."""\nimport math\n')
    write(tmp_path, "studio/isaaclab/src/pitstudio_isaaclab/__init__.py", "#!/usr/bin/env python3\n" + HEADER)
    write(tmp_path, "web/src/engines/robots/twin.ts", TS_HEADER + "export const x = 1;\n")
    write(tmp_path, "studio/recipes/cases/a2.yaml", "id: a2\nstages: []\n")
    assert scan_repository(tmp_path) == []


@pytest.mark.req("NFR-014-05")
def test_the_real_repository_task_code_is_clean() -> None:
    found = scan_repository(ROOT)
    assert found == [], "\n".join(f"{v.path}:{v.line} {v.rule} {v.text}" for v in found)


# ------------------------------------------------------------------------------------------------ SPDX
@pytest.mark.req("NFR-014-05")
@pytest.mark.parametrize(
    ("rel", "text"),
    [
        ("src/pitstudio/robots/a.py", '"""no header."""\nx = 1\n'),
        ("src/pitstudio/robots/empty.py", ""),
        ("src/pitstudio/robots/mit.py", "# SPDX-License-Identifier: MIT\nx = 1\n"),
        ("src/pitstudio/robots/bsd.py", "# SPDX-License-Identifier: Apache-2.0 OR MIT\nx = 1\n"),
        ("src/pitstudio/robots/late.py", "x = 1\n" * 10 + HEADER),
        ("src/pitstudio/robots/text.py", "# This file is Apache-2.0 licensed\nx = 1\n"),
        ("web/src/engines/robots/b.ts", "export const y = 2;\n"),
        ("web/src/engines/robots/c.tsx", "// SPDX-License-Identifier: GPL-3.0-only\nexport const z = 3;\n"),
        ("studio/isaaclab/src/pitstudio_isaaclab/tasks/d.py", "\n\n# no header here\n"),
    ],
)
def test_a_task_code_file_without_the_apache_header_is_a_violation_at_line_1(tmp_path: Path, rel, text) -> None:
    write(tmp_path, rel, text)
    assert keys(scan_repository(tmp_path)) == [(rel, 1, "spdx")]


@pytest.mark.req("NFR-014-05")
def test_the_header_may_sit_anywhere_in_the_first_ten_lines_and_after_a_shebang(tmp_path: Path) -> None:
    write(tmp_path, "src/pitstudio/robots/ok1.py", "#!/usr/bin/env python3\n# coding: utf-8\n\n" + HEADER + "x = 1\n")
    write(tmp_path, "src/pitstudio/robots/ok2.py", "x = 0\n" * 9 + HEADER)
    write(
        tmp_path,
        "src/pitstudio/robots/ok3.py",
        "# SPDX-FileCopyrightText: 2026 A\n# SPDX-License-Identifier: Apache-2.0\n",
    )
    assert scan_repository(tmp_path) == []


# ------------------------------------------------------------------------------------------------ copied source
@pytest.mark.req("NFR-014-05")
@pytest.mark.parametrize(
    ("body", "line"),
    [
        ("# Copyright (c) 2022-2026, The Isaac Lab Project Developers.\n", 2),
        ("x = 1\n# Copyright (c) 2022 NVIDIA\n", 3),
        ("x = 1\n# the Isaac Lab Project Developers wrote this\n", 3),
    ],
)
def test_isaac_lab_licence_markers_are_flagged_as_copied_source(tmp_path: Path, body, line) -> None:
    write(tmp_path, "src/pitstudio/robots/copied.py", HEADER + body)
    got = keys(scan_repository(tmp_path))
    assert ("src/pitstudio/robots/copied.py", line, "copied_source") in got


@pytest.mark.req("NFR-014-05")
def test_a_bsd_3_clause_identifier_is_copied_source_and_also_breaks_the_spdx_rule(tmp_path: Path) -> None:
    write(tmp_path, "studio/isaaclab/src/pitstudio_isaaclab/e.py", "# SPDX-License-Identifier: BSD-3-Clause\nx = 1\n")
    got = keys(scan_repository(tmp_path))
    assert ("studio/isaaclab/src/pitstudio_isaaclab/e.py", 1, "copied_source") in got
    assert ("studio/isaaclab/src/pitstudio_isaaclab/e.py", 1, "spdx") in got


@pytest.mark.req("NFR-014-05")
def test_a_comment_that_merely_mentions_isaac_lab_is_not_copied_source(tmp_path: Path) -> None:
    write(
        tmp_path,
        "src/pitstudio/robots/f.py",
        HEADER + "# Written for Isaac Lab 3.0 (BSD-3 licensed upstream); no upstream code is copied.\nx = 1\n",
    )
    assert [v for v in scan_repository(tmp_path) if v.rule == "copied_source"] == []


# ------------------------------------------------------------------------------------------------ assets
@pytest.mark.req("NFR-014-05")
@pytest.mark.parametrize(
    "snippet",
    [
        "from isaaclab_assets import ANYMAL_C_CFG\n",
        "import isaaclab_assets.robots.spot as spot\n",
        "usd_path = f'{ISAAC_NUCLEUS_DIR}/Robots/Franka/franka.usd'\n",
        "path = ISAACLAB_NUCLEUS_DIR + '/Robots'\n",
        "url = 'omniverse://localhost/NVIDIA/Assets/x.usd'\n",
        "root = 'Isaac/IsaacLab/Robots/Classic/Cartpole/cartpole.usd'\n",
        "u = 'https://nucleus.example.nvidia.com/NVIDIA/Assets/Isaac/5.1/x.usd'\n",
    ],
)
def test_nvidia_and_isaac_lab_asset_references_are_flagged_with_their_line(tmp_path: Path, snippet) -> None:
    write(tmp_path, "studio/isaaclab/src/pitstudio_isaaclab/g.py", HEADER + "import os\n" + snippet)
    assert set(keys(scan_repository(tmp_path))) == {
        ("studio/isaaclab/src/pitstudio_isaaclab/g.py", 3, "asset")
    }  # one or several matches on the line


@pytest.mark.req("NFR-014-05")
def test_a_recipe_that_references_an_asset_is_flagged_but_needs_no_spdx_header(tmp_path: Path) -> None:
    write(
        tmp_path,
        "studio/recipes/cases/a2.yaml",
        "stages:\n  - id: st60_il_train\n    params:\n      usd: Isaac/IsaacLab/Robots/Classic/Cartpole/cartpole.usd\n",
    )
    write(tmp_path, "studio/recipes/cases/clean.yml", "stages: []\n")
    assert keys(scan_repository(tmp_path)) == [("studio/recipes/cases/a2.yaml", 4, "asset")]


@pytest.mark.req("NFR-014-05")
def test_the_same_text_outside_the_scan_roots_is_not_scanned(tmp_path: Path) -> None:
    write(tmp_path, "docs/notes.py", "from isaaclab_assets import X\n")
    write(tmp_path, "tools/other.py", "# no header\nfrom isaaclab_assets import X\n")
    write(tmp_path, "src/pitstudio/contracts/x.py", "no header\n")
    assert scan_repository(tmp_path) == []


@pytest.mark.req("NFR-014-05")
def test_several_violations_are_all_reported_sorted_by_path_line_and_rule(tmp_path: Path) -> None:
    write(tmp_path, "src/pitstudio/robots/b.py", "from isaaclab_assets import A\n# Copyright (c) 2022 NVIDIA\n")
    write(tmp_path, "src/pitstudio/robots/a.py", HEADER + "x = ISAAC_NUCLEUS_DIR\n")
    got = keys(scan_repository(tmp_path))
    assert got == [
        ("src/pitstudio/robots/a.py", 2, "asset"),
        ("src/pitstudio/robots/b.py", 1, "asset"),
        ("src/pitstudio/robots/b.py", 1, "spdx"),
        ("src/pitstudio/robots/b.py", 2, "copied_source"),
    ]
    assert all(isinstance(v, Violation) and v.text for v in scan_repository(tmp_path))


@pytest.mark.req("NFR-014-05")
def test_cache_and_dependency_folders_are_skipped(tmp_path: Path) -> None:
    write(tmp_path, "src/pitstudio/robots/__pycache__/x.py", "from isaaclab_assets import X\n")
    write(tmp_path, "web/src/engines/robots/node_modules/pkg/index.ts", "export {};\n")
    write(tmp_path, "studio/isaaclab/src/.venv/lib/y.py", "no header\n")
    assert scan_repository(tmp_path) == []


# ------------------------------------------------------------------------------------------------ hostile input
@pytest.mark.req("NFR-014-05")
@pytest.mark.parametrize("bad", ["nothing-here", "a-file.txt"])
def test_a_repo_root_that_is_not_a_directory_raises_value_error_naming_it(tmp_path: Path, bad) -> None:
    (tmp_path / "a-file.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\brepo_root\b"):
        scan_repository(tmp_path / bad)


@pytest.mark.req("NFR-014-05")
def test_a_file_that_is_not_utf_8_is_reported_by_name(tmp_path: Path) -> None:
    p = tmp_path / "src" / "pitstudio" / "robots" / "bin.py"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"# SPDX-License-Identifier: Apache-2.0\n\xff\xfe\x00 garbage")
    with pytest.raises(ValueError, match=r"bin\.py"):
        scan_repository(tmp_path)


@pytest.mark.req("NFR-014-05")
def test_unicode_crlf_and_large_files_are_scanned(tmp_path: Path) -> None:
    write(tmp_path, "src/pitstudio/robots/u.py", HEADER + "# café 中文 \U0001f6a7\nx = 1\n")
    (tmp_path / "src/pitstudio/robots/crlf.py").write_bytes(
        b"# SPDX-License-Identifier: Apache-2.0\r\nx = 1\r\nfrom isaaclab_assets import Y\r\n"
    )
    big = HEADER + "x = 1\n" * 200_000 + "root = ISAAC_NUCLEUS_DIR\n"
    write(tmp_path, "src/pitstudio/robots/big.py", big)
    got = keys(scan_repository(tmp_path))
    assert ("src/pitstudio/robots/crlf.py", 3, "asset") in got
    assert ("src/pitstudio/robots/big.py", 200_002, "asset") in got
    assert not [g for g in got if g[0].endswith("u.py")]
