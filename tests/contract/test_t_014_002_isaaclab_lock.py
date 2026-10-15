# ruff: noqa: E501
"""T-014-002: lock check of `studio/isaaclab/uv.lock` and the performance marker derived from the lock.

Requirements: FR-014-01, FR-014-04, DC-014-06.

Spec: specs/014-robot-learning/spec.md FR-014-01: "`studio/isaaclab/uv.lock` shall pin the Isaac Lab packages to tag v3.0.0-EA at a commit beginning `ae37b02`, torch 2.11.0 and torchvision 0.26.0 from the cu128 index,
warp-lang 1.16.0, newton 1.5.2, mujoco and mujoco-warp 3.11.x and rsl-rl-lib 5.4.1, and every IL stage manifest shall report these versions read from the lock." FR-014-04: "IL stages shall import no Isaac Sim or Kit module,
the lock shall contain no `isaacsim*` package, and each IL stage manifest shall carry `performance: public` unless the lock contains a package covered by NVIDIA SLA 8.9 (`isaacsim*`, `omni*`, `ovrtx`, `ovstage`,
`ovphysx`), in which case it shall carry `local-only`." DC-014-06: run and asset manifests (spec 001).

Oracle: the lock file itself, parsed here with the standard library `tomllib` (reference parser) against the pinned list of the requirement; synthetic locks written by hand in the uv.lock layout (a `[[package]]` table
with `name`, `version`, `source`); the real lock read once by hand: its Isaac Lab packages are at `v3.0.0-EA#ae37b028...`, torch is `2.11.0+cu128` from `https://download.pytorch.org/whl/cu128`, and it holds `ovstage 0.1.1.355824`
(from pypi.nvidia.com), which is covered by SLA 8.9, so the derived marker of the real lock is `local-only` (the committed tool entry says `public`, which this test asks to be corrected).

Expected API of the implementation (module `pitstudio.robots.lock`, standard library only):
    parse_lock(source) -> LockInfo
        source: a pathlib.Path of a uv.lock file, or a str holding the text of one; LockInfo (frozen dataclass) has `packages`: dict name -> list of {"version", "source": {"git": ... | "registry": ... | ...}} entries; ValueError for text that is not TOML,
        has no [[package]] table, or has a package without name or version
    check_isaaclab_lock(lock) -> list[dict]
        problems sorted by (package, rule), each {"rule": "FR-014-01" | "FR-014-04", "package": <name>, "message": <text>}; empty when the lock satisfies the requirement. Rules: every package whose name starts with
        "isaaclab" has a git source whose URL carries the query item tag=v3.0.0-EA and a fragment beginning "ae37b02" (all of them the same commit); torch version "2.11.0+cu128" and torchvision "0.26.0+cu128", each
        from a registry URL ending in "/whl/cu128"; warp-lang 1.16.0; newton 1.5.2; mujoco and mujoco-warp versions starting "3.11."; rsl-rl-lib 5.4.1; a missing pinned package is a problem; any package named isaacsim*
        is a problem of rule FR-014-04.
    performance_marker(lock) -> "public" | "local-only"
        "local-only" when any package name matches isaacsim*, omni*, or equals ovrtx, ovstage or ovphysx (case-insensitive), else "public"
    lock_versions(lock) -> dict[str, str]
        versions read from the lock for the manifest: keys isaaclab, isaaclab_newton, isaaclab_tasks, isaaclab_rl, torch, torchvision, warp_lang, newton, mujoco, mujoco_warp, rsl_rl_lib (package names with "-" as "_")
    forbidden_imports(root) -> list[tuple[str, str]]
        (relative path, module) for every `import` / `from ... import` in the .py files under root whose top-level module is isaacsim, omni, carb, ovrtx, ovstage or
        ovphysx, found by parsing the source (ast), also when the import is inside a function; ValueError naming `root` when it is not a directory
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
import yaml
from pitstudio.robots.lock import (
    check_isaaclab_lock,
    forbidden_imports,
    lock_versions,
    parse_lock,
    performance_marker,
)

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "studio" / "isaaclab" / "uv.lock"
TAG = "v3.0.0-EA"
COMMIT = "ae37b028ea415c91ea2bc32609efcd759ed2b974"
ISAACLAB = [
    "isaaclab",
    "isaaclab-assets",
    "isaaclab-contrib",
    "isaaclab-newton",
    "isaaclab-ov",
    "isaaclab-physx",
    "isaaclab-rl",
    "isaaclab-tasks",
]
CU128 = "https://download.pytorch.org/whl/cu128"
PYPI = "https://pypi.org/simple"


def pkg(name, version, source):
    src = "{ " + ", ".join(f'{k} = "{v}"' for k, v in source.items()) + " }"
    return f'[[package]]\nname = "{name}"\nversion = "{version}"\nsource = {src}\n'


def good_packages(extra=(), commit=COMMIT, tag=TAG):
    out = [
        pkg(
            n,
            "1.0.0",
            {
                "git": f"https://github.com/isaac-sim/IsaacLab?subdirectory=source%2F{n.replace('-', '_')}&tag={tag}#{commit}"
            },
        )
        for n in ISAACLAB
    ]
    out += [
        pkg("torch", "2.11.0+cu128", {"registry": CU128}),
        pkg("torchvision", "0.26.0+cu128", {"registry": CU128}),
        pkg("warp-lang", "1.16.0", {"registry": "https://pypi.nvidia.com/"}),
        pkg("newton", "1.5.2", {"registry": PYPI}),
        pkg("mujoco", "3.11.0", {"registry": PYPI}),
        pkg("mujoco-warp", "3.11.2", {"registry": PYPI}),
        pkg("rsl-rl-lib", "5.4.1", {"registry": PYPI}),
        pkg("numpy", "2.5.3", {"registry": PYPI}),
    ]
    out += list(extra)
    return out


def lock_text(**kw) -> str:
    return 'version = 1\nrequires-python = "==3.12.*"\n\n' + "\n".join(good_packages(**kw))


def replace_pkg(text: str, name: str, new: str | None) -> str:
    blocks = text.split("[[package]]\n")
    head, rest = blocks[0], blocks[1:]
    out = [b for b in rest if not b.startswith(f'name = "{name}"\n')]
    if new is not None:
        out.append(new.removeprefix("[[package]]\n"))
    return head + "".join("[[package]]\n" + b for b in out)


# ------------------------------------------------------------------------------------------------ the real lock
@pytest.mark.req("FR-014-01")
def test_the_real_lock_satisfies_every_pin_of_the_requirement() -> None:
    assert check_isaaclab_lock(parse_lock(REAL)) == []


@pytest.mark.req("FR-014-01")
def test_the_real_lock_agrees_with_an_independent_tomllib_read() -> None:
    raw = tomllib.loads(REAL.read_text("utf-8"))
    by_name = {p["name"]: p for p in raw["package"]}
    info = parse_lock(REAL)
    for name in ("torch", "torchvision", "warp-lang", "newton", "mujoco", "mujoco-warp", "rsl-rl-lib", *ISAACLAB):
        assert info.packages[name][0]["version"] == by_name[name]["version"]
    assert by_name["torch"]["version"] == "2.11.0+cu128"
    assert by_name["isaaclab"]["source"]["git"].endswith(f"tag={TAG}#{COMMIT}")


@pytest.mark.req("FR-014-01")
def test_the_manifest_versions_are_read_from_the_lock() -> None:
    v = lock_versions(parse_lock(REAL))
    assert v["torch"] == "2.11.0+cu128"
    assert v["torchvision"] == "0.26.0+cu128"
    assert v["warp_lang"] == "1.16.0"
    assert v["newton"] == "1.5.2"
    assert v["mujoco"] == "3.11.0"
    assert v["mujoco_warp"] == "3.11.0"
    assert v["rsl_rl_lib"] == "5.4.1"
    assert v["isaaclab"] == "17.0.2"
    assert v["isaaclab_newton"] == "5.4.1"
    assert v["isaaclab_tasks"] == "18.0.1"
    assert v["isaaclab_rl"] == "0.16.3"
    assert set(v) == {
        "isaaclab",
        "isaaclab_newton",
        "isaaclab_tasks",
        "isaaclab_rl",
        "torch",
        "torchvision",
        "warp_lang",
        "newton",
        "mujoco",
        "mujoco_warp",
        "rsl_rl_lib",
    }


@pytest.mark.req("FR-014-01")
def test_the_committed_capability_report_carries_the_versions_of_the_lock() -> None:
    caps = json.loads((ROOT / "studio" / "capabilities.json").read_text("utf-8"))
    probe_versions = caps["probes"]["isaaclab"]["versions"]
    v = lock_versions(parse_lock(REAL))
    shared = set(probe_versions) & set(v)
    assert shared >= {"isaaclab", "torch", "warp_lang", "newton", "rsl_rl_lib"}
    for key in shared:
        assert probe_versions[key] == v[key], key


# ------------------------------------------------------------------------------------------------ synthetic locks
@pytest.mark.req("FR-014-01")
def test_the_synthetic_good_lock_passes() -> None:
    assert check_isaaclab_lock(parse_lock(lock_text())) == []


@pytest.mark.req("FR-014-01")
@pytest.mark.parametrize(
    ("mutation", "package"),
    [
        (lambda t: replace_pkg(t, "torch", pkg("torch", "2.10.0+cu128", {"registry": CU128})), "torch"),
        (lambda t: replace_pkg(t, "torch", pkg("torch", "2.11.0", {"registry": PYPI})), "torch"),  # CPU wheel from PyPI
        (
            lambda t: replace_pkg(
                t, "torch", pkg("torch", "2.11.0+cu128", {"registry": "https://download.pytorch.org/whl/cu126"})
            ),
            "torch",
        ),
        (
            lambda t: replace_pkg(t, "torchvision", pkg("torchvision", "0.25.0+cu128", {"registry": CU128})),
            "torchvision",
        ),
        (
            lambda t: replace_pkg(t, "torchvision", pkg("torchvision", "0.26.0+cu128", {"registry": PYPI})),
            "torchvision",
        ),
        (lambda t: replace_pkg(t, "warp-lang", pkg("warp-lang", "1.17.0", {"registry": PYPI})), "warp-lang"),
        (lambda t: replace_pkg(t, "newton", pkg("newton", "1.6.0", {"registry": PYPI})), "newton"),
        (lambda t: replace_pkg(t, "mujoco", pkg("mujoco", "3.12.0", {"registry": PYPI})), "mujoco"),
        (lambda t: replace_pkg(t, "mujoco-warp", pkg("mujoco-warp", "3.1.1", {"registry": PYPI})), "mujoco-warp"),
        (lambda t: replace_pkg(t, "rsl-rl-lib", pkg("rsl-rl-lib", "5.4.2", {"registry": PYPI})), "rsl-rl-lib"),
        (lambda t: replace_pkg(t, "rsl-rl-lib", None), "rsl-rl-lib"),  # a pinned package that is absent
        (lambda t: replace_pkg(t, "newton", None), "newton"),
        (lambda t: replace_pkg(t, "torch", None), "torch"),
    ],
    ids=[
        "torch-2.10",
        "torch-pypi-cpu",
        "torch-cu126",
        "tv-0.25",
        "tv-pypi",
        "warp-1.17",
        "newton-1.6",
        "mujoco-3.12",
        "mjwarp-3.1",
        "rsl-5.4.2",
        "rsl-missing",
        "newton-missing",
        "torch-missing",
    ],
)
def test_a_lock_that_breaks_a_pin_is_reported_naming_the_package(mutation, package) -> None:
    problems = check_isaaclab_lock(parse_lock(mutation(lock_text())))
    assert package in {p["package"] for p in problems}
    assert all(p["rule"] == "FR-014-01" for p in problems if p["package"] == package)
    assert all(p["message"] for p in problems)


@pytest.mark.req("FR-014-01")
def test_isaac_lab_packages_must_be_at_the_tag_and_the_commit_prefix() -> None:
    wrong_tag = check_isaaclab_lock(parse_lock(lock_text(tag="v2.3.0")))
    assert {p["package"] for p in wrong_tag} == set(ISAACLAB)
    wrong_commit = check_isaaclab_lock(parse_lock(lock_text(commit="bd37b028ea415c91ea2bc32609efcd759ed2b974")))
    assert {p["package"] for p in wrong_commit} == set(ISAACLAB)
    prefix_only = check_isaaclab_lock(parse_lock(lock_text(commit="ae37b02" + "0" * 33)))
    assert prefix_only == []  # the requirement fixes the prefix `ae37b02`, any commit that starts with it passes


@pytest.mark.req("FR-014-01")
def test_one_isaac_lab_package_at_another_commit_or_without_git_is_reported() -> None:
    text = lock_text()
    other = pkg(
        "isaaclab-rl",
        "0.16.3",
        {
            "git": f"https://github.com/isaac-sim/IsaacLab?subdirectory=source%2Fisaaclab_rl&tag={TAG}#ffffffffffffffffffffffffffffffffffffffff"
        },
    )
    problems = check_isaaclab_lock(parse_lock(replace_pkg(text, "isaaclab-rl", other)))
    assert [p["package"] for p in problems] == ["isaaclab-rl"]
    registry = pkg(
        "isaaclab-tasks", "18.0.1", {"registry": PYPI}
    )  # an Isaac Lab package from an index instead of the pinned git tag
    problems = check_isaaclab_lock(parse_lock(replace_pkg(text, "isaaclab-tasks", registry)))
    assert [p["package"] for p in problems] == ["isaaclab-tasks"]


@pytest.mark.req("FR-014-04")
@pytest.mark.parametrize("name", ["isaacsim", "isaacsim-core", "isaacsim-rl", "Isaacsim-App"])
def test_an_isaacsim_package_is_a_violation_of_the_no_isaac_sim_rule(name) -> None:
    text = lock_text(extra=[pkg(name, "5.1.0", {"registry": "https://pypi.nvidia.com/"})])
    problems = check_isaaclab_lock(parse_lock(text))
    assert [(p["package"], p["rule"]) for p in problems] == [(name, "FR-014-04")]


@pytest.mark.req("FR-014-04")
@pytest.mark.parametrize(
    ("extra", "marker"),
    [
        ([], "public"),
        ([("numpy-omni-helper", "1.0")], "public"),  # `omni*` is a prefix rule: the name must START with omni
        ([("ovrtx", "1.0")], "local-only"),
        ([("ovstage", "0.1.1")], "local-only"),
        ([("ovphysx", "2.0")], "local-only"),
        ([("omni-kit-ext", "1.0")], "local-only"),
        ([("omniverse-client", "1.0")], "local-only"),
        ([("isaacsim-core", "5.1.0")], "local-only"),
        ([("OVSTAGE", "0.1")], "local-only"),  # names compare case-insensitively
        ([("ovstage-lite", "1.0")], "public"),  # ovrtx, ovstage and ovphysx are exact names, not prefixes
        ([("isaaclab-ov", "2.2.0")], "public"),  # a name that merely contains `ov` is not covered
        ([("ovstagex", "1.0"), ("ovrtx2", "1.0")], "public"),
    ],
)
def test_the_performance_marker_follows_the_restricted_package_names(extra, marker) -> None:
    pkgs = [pkg(n, v, {"registry": "https://pypi.nvidia.com/"}) for n, v in extra]
    assert performance_marker(parse_lock(lock_text(extra=pkgs))) == marker


@pytest.mark.req("FR-014-04")
def test_the_real_lock_holds_ovstage_so_its_marker_is_local_only_and_the_tool_entry_must_say_so() -> None:
    lock = parse_lock(REAL)
    assert "ovstage" in lock.packages
    assert performance_marker(lock) == "local-only"
    tools = yaml.safe_load((ROOT / "studio" / "tools.yaml").read_text("utf-8"))["tools"]
    entry = next(t for t in tools if t["id"] == "isaac-lab")
    assert entry["performance"] == performance_marker(lock)


@pytest.mark.req("FR-014-04")
def test_the_real_lock_has_no_isaacsim_package() -> None:
    assert not [n for n in parse_lock(REAL).packages if n.lower().startswith("isaacsim")]
    assert [p for p in check_isaaclab_lock(parse_lock(REAL)) if p["rule"] == "FR-014-04"] == []


# ------------------------------------------------------------------------------------------------ hostile locks
@pytest.mark.req("FR-014-01")
@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n",
        "not = [valid toml",
        "version = 1\n",
        'version = 1\n[[package]]\nversion = "1"\n',
        'version = 1\n[[package]]\nname = "x"\n',
        "\x00\x01\x02",
        '[[package]]\nname = 3\nversion = "1"\n',
    ],
    ids=["empty", "blank", "bad-toml", "no-package", "no-name", "no-version", "binary", "name-not-str"],
)
def test_a_malformed_lock_raises_value_error(text) -> None:
    with pytest.raises(ValueError, match=r".+"):
        parse_lock(text)


@pytest.mark.req("FR-014-01")
def test_a_missing_lock_file_raises_value_error_naming_it(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"uv\.lock"):
        parse_lock(tmp_path / "uv.lock")


@pytest.mark.req("FR-014-01")
def test_unicode_package_names_do_not_break_the_check() -> None:
    text = lock_text(extra=[pkg("päckage-中文", "1.0", {"registry": PYPI})])
    assert check_isaaclab_lock(parse_lock(text)) == []
    assert performance_marker(parse_lock(text)) == "public"


@pytest.mark.req("FR-014-01")
def test_a_package_listed_twice_is_checked_on_every_entry() -> None:
    text = lock_text(extra=[pkg("torch", "2.9.0+cu128", {"registry": CU128})])
    assert "torch" in {p["package"] for p in check_isaaclab_lock(parse_lock(text))}


# ------------------------------------------------------------------------------------------------ no Isaac Sim import
@pytest.mark.req("FR-014-04")
def test_the_import_scan_finds_isaac_sim_and_kit_imports_including_nested_ones(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("import isaacsim\nimport numpy\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.py").write_text("from omni.kit.app import get_app\n", encoding="utf-8")
    (tmp_path / "pkg" / "c.py").write_text("def f():\n    import carb.settings as s\n    return s\n", encoding="utf-8")
    (tmp_path / "pkg" / "d.py").write_text(
        "from isaacsim.core.api import World as W\nimport ovstage, ovrtx\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "ok.py").write_text(
        "import isaaclab\nfrom isaaclab_tasks import x\nimport torch\nimport omnibus\n", encoding="utf-8"
    )
    found = forbidden_imports(tmp_path)
    assert sorted(found) == sorted(
        [
            ("pkg/a.py", "isaacsim"),
            ("pkg/b.py", "omni.kit.app"),
            ("pkg/c.py", "carb.settings"),
            ("pkg/d.py", "isaacsim.core.api"),
            ("pkg/d.py", "ovstage"),
            ("pkg/d.py", "ovrtx"),
        ]
    )


@pytest.mark.req("FR-014-04")
def test_the_import_scan_ignores_strings_and_comments_and_lookalike_names(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text(
        '# import isaacsim\nS = "import omni.kit"\n"""from carb import x"""\nimport isaaclab_assets_free\n',
        encoding="utf-8",
    )
    assert forbidden_imports(tmp_path) == []


@pytest.mark.req("FR-014-04")
def test_the_import_scan_of_the_task_code_of_this_repository_is_clean() -> None:
    for sub in ("studio/isaaclab/src", "src/pitstudio/robots"):
        folder = ROOT / sub
        if folder.is_dir():
            assert forbidden_imports(folder) == [], sub
    assert (ROOT / "studio/isaaclab/src").is_dir()


@pytest.mark.req("FR-014-04")
@pytest.mark.parametrize("bad", ["does-not-exist", "file.py"])
def test_the_import_scan_rejects_a_root_that_is_not_a_directory(bad, tmp_path: Path) -> None:
    (tmp_path / "file.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\broot\b"):
        forbidden_imports(tmp_path / bad)


@pytest.mark.req("FR-014-04")
def test_a_source_file_that_does_not_parse_is_reported_not_skipped(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"broken\.py"):
        forbidden_imports(tmp_path)
