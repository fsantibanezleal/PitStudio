"""T-019-002: version resolution of the tool registry from `uv.lock` files, `web/pnpm-lock.yaml`, git-tag pins and
external-binary records (`tools/resolve_versions.py`).

Requirements: FR-019-09 (the Identity block shows the version resolved from the lock named in the registry and its
release date) and FR-019-10 (a registry version that differs from the resolved one, or a lock entry that cannot be
resolved, fails the build naming the tool).

Spec: specs/019-web-studio/ (spec.md FR-019-09, FR-019-10; plan.md test strategy row "FR-019-09, FR-019-10";
data-model 001 section 4.2 "Version references").

Expected API of the implementation (module `tools/resolve_versions.py`, imported through `sys.path`):
  Resolved                         dataclass-like with `.version` (str) and `.release_date` (ISO "YYYY-MM-DD" or None)
  VersionError(Exception)          with attribute `.tool` (the registry id) and a message that contains the id
  resolve_entry(entry: dict, root: Path) -> Resolved
  resolve_registry(root: Path) -> dict[str, Resolved]    reads root/studio/tools.yaml, raises VersionError naming the
                                                          first failing tool in registry order
  CLI: `python tools/resolve_versions.py --root DIR [--json]` prints one line "<tool id> <version> <release date|->"
  per tool (or a JSON object when --json), exit 0; exit 1 and the tool id on stderr when a tool fails; exit 2 on a
  usage error; never a traceback.

Resolution rules (data-model 001 section 4.2), as the test author reads them (assumptions flagged in the red report):
  * `{from_lock, package}`: uv lock files are TOML with `[[package]]` tables (names compared after PEP 503
    normalisation: lower case, runs of `-`, `_`, `.` collapsed to `-`); `web/pnpm-lock.yaml` (lockfile 9) gives the
    version of the direct dependency in `importers['.']`, else the only version in `packages`. A package present with
    two different versions and no direct entry is ambiguous and fails. The release date of a uv package is the date
    of the earliest `upload-time` of its sdist and wheels; pnpm packages carry none (None).
  * `{from_binary, release, sha256}`: the record `root/studio/external-binaries.yaml` (`binaries: [{id, release, sha256,
    date}]`); the release and the digest must equal the registry's; the date of the record is the release date.
  * `{from_git_tag, repository}`: the tag of the entry in `[tool.uv.sources]` (`git = <repository>`, `tag = <tag>`) of
    the `pyproject.toml` of one of the entry's environments must equal the registry's tag; release date None.
  * `{own: true}`: the first line of `root/VERSION` (a semantic version), release date None.
  Environment directories: root and runner "", studio "studio", isaac "studio/isaac", rtx "studio/rtx", isaaclab
  "studio/isaaclab", reason "studio/reason", kit "studio/kit", pipeline "pipeline", accel "pipeline/accel",
  web "web", external none.

Oracles: hand-written lock fixtures with known versions and dates; for the repository's own committed lock files, a
second, independent reading by regular expression over the raw text (not through a TOML or YAML parser).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "resolve_versions.py"
sys.path.insert(0, str(ROOT / "tools"))
SHA = "b" * 64


def _mod():
    assert TOOL.is_file(), "tools/resolve_versions.py exists (T-019-002)"
    import resolve_versions

    return resolve_versions


def uv_lock(*packages: tuple[str, str, list[str]]) -> str:
    out = ["version = 1", "revision = 3", 'requires-python = "==3.14.*"', ""]
    for name, version, times in packages:
        out += [
            "[[package]]",
            f'name = "{name}"',
            f'version = "{version}"',
            'source = { registry = "https://pypi.org/simple" }',
        ]
        if times:
            wheels = ", ".join(
                f'{{ url = "https://files.example/{name}-{version}-{i}.whl", '
                f'hash = "sha256:{SHA}", size = 1, upload-time = "{t}" }}'
                for i, t in enumerate(times)
            )
            out.append(f"wheels = [{wheels}]")
        out.append("")
    return "\n".join(out)


PNPM = """lockfileVersion: '9.0'
importers:
  .:
    dependencies:
      react:
        specifier: ^19.3.0
        version: 19.3.0
      '@xyflow/react':
        specifier: ^12.12.0
        version: 12.12.0(react-dom@19.3.0(react@19.3.0))(react@19.3.0)
    devDependencies:
      '@axe-core/playwright':
        specifier: ^4.13.0
        version: 4.13.0(playwright-core@1.63.0)
packages:
  react@19.3.0:
    resolution: {integrity: sha512-aaa}
  react@18.0.0:
    resolution: {integrity: sha512-bbb}
  '@xyflow/react@12.12.0':
    resolution: {integrity: sha512-ccc}
  '@axe-core/playwright@4.13.0':
    resolution: {integrity: sha512-ddd}
  axe-core@4.13.0:
    resolution: {integrity: sha512-eee}
  tslib@1.0.0:
    resolution: {integrity: sha512-fff}
  tslib@2.8.1:
    resolution: {integrity: sha512-ggg}
  left-pad@1.3.0:
    resolution: {integrity: sha512-hhh}
snapshots:
  react@19.3.0: {}
"""


def entry(tid: str, version: dict, envs: list[str] | None = None) -> dict:
    return {
        "id": tid,
        "name": tid,
        "category": "studio-tool",
        "envs": envs or ["studio"],
        "version": version,
        "spdx": ["Apache-2.0"],
        "osi": True,
        "licence_class": "attribution",
        "ring": "Adopt",
        "lane": "replay",
        "performance": "public",
        "role": "r",
        "cases": [],
        "produces": [],
        "status": "not-yet-run",
        "docs_page": f"docs/frameworks/{tid}.md",
    }


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def repo(root: Path, entries: list[dict]) -> Path:
    write(root, "studio/tools.yaml", yaml.safe_dump({"tools": entries}, sort_keys=False))
    return root


@pytest.fixture
def fx(tmp_path: Path) -> Path:
    write(
        tmp_path,
        "studio/uv.lock",
        uv_lock(
            ("warp-lang", "1.9.0", ["2025-09-10T10:11:12.123456Z", "2025-09-09T08:00:00Z"]),
            ("pyyaml", "6.0.3", ["2025-09-25T19:50:00Z"]),
            ("ruamel-yaml", "0.18.15", []),
            ("dual", "1.0.0", ["2025-01-01T00:00:00Z"]),
            ("dual", "2.0.0", ["2025-02-01T00:00:00Z"]),
        ),
    )
    write(tmp_path, "pipeline/uv.lock", uv_lock(("torch", "2.11.0+cu130", ["2026-03-01T00:00:00Z"])))
    write(tmp_path, "web/pnpm-lock.yaml", PNPM)
    write(
        tmp_path,
        "studio/external-binaries.yaml",
        yaml.safe_dump({"binaries": [{"id": "ffmpeg-lgpl", "release": "n8.1", "sha256": SHA, "date": "2026-09-20"}]}),
    )
    write(
        tmp_path,
        "studio/pyproject.toml",
        '[project]\nname = "studio"\nversion = "0"\n\n[tool.uv.sources]\n'
        'cuopt = { git = "https://github.com/NVIDIA/cuopt", tag = "v25.08.00" }\n',
    )
    write(tmp_path, "VERSION", "0.4.2\nsecond line is ignored\n")
    return tmp_path


# --------------------------------------------------------------------------------------------------------------------
# FR-019-09: resolution
# --------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-019-09")
def test_uv_lock_package_is_resolved_with_its_earliest_upload_date(fx: Path) -> None:
    got = _mod().resolve_entry(entry("warp", {"from_lock": "studio/uv.lock", "package": "warp-lang"}), fx)
    assert got.version == "1.9.0"
    assert got.release_date == "2025-09-09"


@pytest.mark.req("FR-019-09")
@pytest.mark.parametrize(
    ("package", "version"),
    [("PyYAML", "6.0.3"), ("pyyaml", "6.0.3"), ("ruamel.yaml", "0.18.15"), ("Ruamel_Yaml", "0.18.15")],
)
def test_package_names_are_compared_after_pep_503_normalisation(fx: Path, package: str, version: str) -> None:
    got = _mod().resolve_entry(entry("t", {"from_lock": "studio/uv.lock", "package": package}), fx)
    assert got.version == version


@pytest.mark.req("FR-019-09")
def test_a_package_without_upload_times_has_no_release_date_and_a_local_version_suffix_is_kept(fx: Path) -> None:
    m = _mod()
    assert (
        m.resolve_entry(entry("r", {"from_lock": "studio/uv.lock", "package": "ruamel-yaml"}), fx).release_date is None
    )
    got = m.resolve_entry(entry("torch", {"from_lock": "pipeline/uv.lock", "package": "torch"}, ["pipeline"]), fx)
    assert (got.version, got.release_date) == ("2.11.0+cu130", "2026-03-01")


@pytest.mark.req("FR-019-09")
@pytest.mark.parametrize(
    ("package", "version"),
    [("react", "19.3.0"), ("@xyflow/react", "12.12.0"), ("@axe-core/playwright", "4.13.0"), ("axe-core", "4.13.0")],
)
def test_pnpm_lock_gives_the_direct_dependency_version_without_peer_suffix(
    fx: Path, package: str, version: str
) -> None:
    got = _mod().resolve_entry(entry("t", {"from_lock": "web/pnpm-lock.yaml", "package": package}, ["web"]), fx)
    assert got.version == version
    assert got.release_date is None


@pytest.mark.req("FR-019-09")
def test_pnpm_package_known_by_one_version_only_resolves_without_an_importer_entry(fx: Path) -> None:
    got = _mod().resolve_entry(entry("t", {"from_lock": "web/pnpm-lock.yaml", "package": "left-pad"}, ["web"]), fx)
    assert got.version == "1.3.0"


@pytest.mark.req("FR-019-09")
def test_pinned_binary_resolves_to_its_release_and_record_date(fx: Path) -> None:
    ref = {"from_binary": "ffmpeg-lgpl", "release": "n8.1", "sha256": SHA}
    got = _mod().resolve_entry(entry("nvenc-ffmpeg", ref, ["external"]), fx)
    assert (got.version, got.release_date) == ("n8.1", "2026-09-20")


@pytest.mark.req("FR-019-09")
def test_git_tag_resolves_when_the_environment_pins_the_same_tag(fx: Path) -> None:
    ref = {"from_git_tag": "v25.08.00", "repository": "https://github.com/NVIDIA/cuopt"}
    got = _mod().resolve_entry(entry("cuopt", ref, ["studio"]), fx)
    assert (got.version, got.release_date) == ("v25.08.00", None)


@pytest.mark.req("FR-019-09")
def test_own_version_is_the_first_line_of_version_file(fx: Path) -> None:
    got = _mod().resolve_entry(entry("pitstudio", {"own": True}, ["root"]), fx)
    assert (got.version, got.release_date) == ("0.4.2", None)


@pytest.mark.req("FR-019-09")
def test_the_repository_committed_locks_agree_with_an_independent_regex_reading() -> None:
    m = _mod()
    # pnpm: the direct dependency `react` of the committed web lock, read from the raw text of the importers section
    lock = (ROOT / "web" / "pnpm-lock.yaml").read_text(encoding="utf-8")
    direct = re.search(r"^ {6}react:\n {8}specifier: [^\n]+\n {8}version: (\d[^\s(]*)", lock, re.MULTILINE)
    assert direct is not None
    got = m.resolve_entry(entry("t", {"from_lock": "web/pnpm-lock.yaml", "package": "react"}, ["web"]), ROOT)
    assert got.version == direct.group(1)
    # uv: `pytest` of the committed root lock, read from the raw text
    uv = (ROOT / "uv.lock").read_text(encoding="utf-8")
    one = re.search(r'^name = "pytest"\nversion = "([^"]+)"', uv, re.MULTILINE)
    assert one is not None
    got = m.resolve_entry(entry("t", {"from_lock": "uv.lock", "package": "pytest"}, ["root"]), ROOT)
    assert got.version == one.group(1)


@pytest.mark.req("FR-019-09")
def test_resolve_registry_returns_every_tool_in_registry_order(fx: Path) -> None:
    repo(
        fx,
        [
            entry("warp", {"from_lock": "studio/uv.lock", "package": "warp-lang"}),
            entry("pitstudio", {"own": True}, ["root"]),
            entry("nvenc-ffmpeg", {"from_binary": "ffmpeg-lgpl", "release": "n8.1", "sha256": SHA}, ["external"]),
        ],
    )
    got = _mod().resolve_registry(fx)
    assert list(got) == ["warp", "pitstudio", "nvenc-ffmpeg"]
    assert [v.version for v in got.values()] == ["1.9.0", "0.4.2", "n8.1"]


# --------------------------------------------------------------------------------------------------------------------
# FR-019-10: failures name the tool
# --------------------------------------------------------------------------------------------------------------------
def _fails(fx: Path, ref: dict, envs: list[str] | None = None, tid: str = "the-tool") -> None:
    m = _mod()
    with pytest.raises(m.VersionError) as info:
        m.resolve_entry(entry(tid, ref, envs), fx)
    assert info.value.tool == tid
    assert tid in str(info.value)


@pytest.mark.req("FR-019-10")
def test_a_package_missing_from_the_lock_fails_naming_the_tool(fx: Path) -> None:
    _fails(fx, {"from_lock": "studio/uv.lock", "package": "no-such-package"})
    _fails(fx, {"from_lock": "web/pnpm-lock.yaml", "package": "no-such-package"}, ["web"])


@pytest.mark.req("FR-019-10")
def test_a_missing_or_malformed_lock_file_fails_naming_the_tool(fx: Path) -> None:
    _fails(fx, {"from_lock": "studio/isaac/uv.lock", "package": "x"}, ["isaac"], tid="isaac-lab")
    write(fx, "studio/uv.lock", "this is = = not toml [[")
    _fails(fx, {"from_lock": "studio/uv.lock", "package": "warp-lang"})
    write(fx, "web/pnpm-lock.yaml", "{ unbalanced: [")
    _fails(fx, {"from_lock": "web/pnpm-lock.yaml", "package": "react"}, ["web"])
    write(fx, "web/pnpm-lock.yaml", "")
    _fails(fx, {"from_lock": "web/pnpm-lock.yaml", "package": "react"}, ["web"])


@pytest.mark.req("FR-019-10")
def test_a_package_with_two_versions_and_no_direct_entry_is_ambiguous(fx: Path) -> None:
    _fails(fx, {"from_lock": "studio/uv.lock", "package": "dual"})
    _fails(fx, {"from_lock": "web/pnpm-lock.yaml", "package": "tslib"}, ["web"])


@pytest.mark.req("FR-019-10")
@pytest.mark.parametrize(
    "ref",
    [
        {"from_binary": "ffmpeg-lgpl", "release": "n8.0", "sha256": SHA},
        {"from_binary": "ffmpeg-lgpl", "release": "n8.1", "sha256": "c" * 64},
        {"from_binary": "unknown-binary", "release": "n8.1", "sha256": SHA},
    ],
    ids=["release-differs", "digest-differs", "no-record"],
)
def test_a_pinned_binary_that_differs_from_its_record_fails_naming_the_tool(fx: Path, ref: dict) -> None:
    _fails(fx, ref, ["external"], tid="nvenc-ffmpeg")


@pytest.mark.req("FR-019-10")
def test_a_missing_binary_record_file_fails(fx: Path) -> None:
    (fx / "studio" / "external-binaries.yaml").unlink()
    _fails(fx, {"from_binary": "ffmpeg-lgpl", "release": "n8.1", "sha256": SHA}, ["external"], tid="nvenc-ffmpeg")


@pytest.mark.req("FR-019-10")
@pytest.mark.parametrize(
    ("tag", "repository"),
    [
        ("v25.08.01", "https://github.com/NVIDIA/cuopt"),
        ("v25.08.00", "https://github.com/example/other"),
    ],
    ids=["tag-differs", "repository-not-pinned"],
)
def test_a_git_tag_that_the_environment_does_not_pin_fails_naming_the_tool(fx: Path, tag: str, repository: str) -> None:
    _fails(fx, {"from_git_tag": tag, "repository": repository}, ["studio"], tid="cuopt")


@pytest.mark.req("FR-019-10")
@pytest.mark.parametrize(
    "content", [None, "", "not a version\n", "1.2\n", "\n"], ids=["missing", "empty", "text", "two-part", "blank"]
)
def test_own_version_needs_a_semantic_version_file(fx: Path, content: str | None) -> None:
    if content is None:
        (fx / "VERSION").unlink()
    else:
        (fx / "VERSION").write_text(content, encoding="utf-8")
    _fails(fx, {"own": True}, ["root"], tid="pitstudio")


@pytest.mark.req("FR-019-10")
def test_a_literal_version_string_is_refused(fx: Path) -> None:
    m = _mod()
    for bad in ("1.2.3", {"version": "1.2.3"}, {}, None, {"from_lock": "../../etc/passwd", "package": "x"}):
        with pytest.raises(m.VersionError):
            m.resolve_entry(entry("lit", bad), fx)  # type: ignore[arg-type]


@pytest.mark.req("FR-019-10")
def test_resolve_registry_names_the_first_failing_tool_and_hostile_ids_are_quoted_verbatim(fx: Path) -> None:
    repo(
        fx,
        [
            entry("good", {"from_lock": "studio/uv.lock", "package": "warp-lang"}),
            entry("bad-one", {"from_lock": "studio/uv.lock", "package": "missing"}),
            entry("bad-two", {"from_lock": "studio/uv.lock", "package": "also-missing"}),
        ],
    )
    m = _mod()
    with pytest.raises(m.VersionError) as info:
        m.resolve_registry(fx)
    assert info.value.tool == "bad-one"


# --------------------------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------------------------
def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    assert TOOL.is_file(), "tools/resolve_versions.py exists (T-019-002)"
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=120, check=False)


@pytest.mark.req("FR-019-09")
def test_cli_prints_one_line_per_tool_and_json_on_request(fx: Path) -> None:
    repo(
        fx,
        [
            entry("warp", {"from_lock": "studio/uv.lock", "package": "warp-lang"}),
            entry("pitstudio", {"own": True}, ["root"]),
        ],
    )
    plain = _cli("--root", str(fx))
    assert plain.returncode == 0, plain.stderr
    assert plain.stdout.splitlines() == ["warp 1.9.0 2025-09-09", "pitstudio 0.4.2 -"]
    js = _cli("--root", str(fx), "--json")
    assert js.returncode == 0
    assert json.loads(js.stdout) == {
        "warp": {"version": "1.9.0", "release_date": "2025-09-09"},
        "pitstudio": {"version": "0.4.2", "release_date": None},
    }


@pytest.mark.req("FR-019-10")
def test_cli_failure_exits_one_and_names_the_tool(fx: Path) -> None:
    repo(fx, [entry("warp", {"from_lock": "studio/uv.lock", "package": "missing-pkg"})])
    done = _cli("--root", str(fx))
    assert done.returncode == 1
    assert "warp" in done.stderr
    assert "Traceback" not in done.stderr


@pytest.mark.req("FR-019-10")
def test_cli_usage_and_unreadable_registry_exit_two(tmp_path: Path) -> None:
    assert _cli("--bogus").returncode == 2
    missing = _cli("--root", str(tmp_path / "nowhere"))
    assert missing.returncode == 2
    assert "Traceback" not in missing.stderr
    write(tmp_path, "studio/tools.yaml", "tools: [ {")
    broken = _cli("--root", str(tmp_path))
    assert broken.returncode == 2
    assert "tools.yaml" in broken.stderr
    assert "Traceback" not in broken.stderr
