"""T-016-031: asset hosts and the release-asset list (unit, hostile, property).

Requirements: FR-016-14, FR-016-15, FR-016-16, P-016-10.

Spec: specs/016-export-acceleration/spec.md
- FR-016-14: a file is hosted in git if it is < 10,485,760 bytes (`contracts.git_file_bytes_max`) and the in-git baked
  total stays <= 100 x 10^6 bytes (`budgets.git_baked_assets_mb_max`); otherwise it is a release asset; when the in-git
  total would exceed 100 x 10^6 bytes, whole budget classes, largest total first, move into per-class release-asset
  archives until it does not;
- FR-016-15: the release-asset upload list (DC-016-02) holds every release-hosted file with its
  repository-relative POSIX path, bytes, SHA-256 and the tag `assets-vX.YY.ZZZ`, sorted by path;
- FR-016-16: a path that is absolute, contains `..`, a backslash or a drive letter, or resolves outside the bake
  root, a tag that does not match `^assets-v\\d+\\.\\d{2}\\.\\d{3}$`, or a file >= 2^31 bytes fails the list with
  the offending entry;
- P-016-10: the list and the host assignment are byte-identical for any order of the input files, and re-running the
  assignment on its own output changes nothing.
plan.md test strategy rows FR-016-14, FR-016-15, FR-016-16 (`/abs`, `a/../b`, `a\\b`, `C:x`, a symlink outside the
root, tag `assets-v1.2.3`, a size of 2^31), P-016-10. Note: plan row FR-016-14 still names the file sizes 9,999,999
and 10,000,000; the spec text (clarification "Integration 2026-10-07 (2)") replaced the 10 x 10^6 cap by
10,485,760 bytes, so the boundary pair used here is 10,485,759 / 10,485,760.

Oracles: the hand tables below (exact integer arithmetic), the thresholds of `specs/000-foundation/thresholds.yaml`
(`contracts.git_file_bytes_max` = 10,485,760; `budgets.git_baked_assets_mb_max`, 100 MB = 10^8 bytes), and the reference
JSON Schema validation of `contracts/release-assets.schema.json` (DC-016-02).

Expected public API (root environment):
module `pitstudio.export.hosts`
    GIT_FILE_BYTES_MAX = 10_485_760; GIT_BAKED_BYTES_MAX = 100_000_000
    assign_hosts(files: Sequence[Mapping]) -> HostPlan
        files: {"path": str, "bytes": int, "sha256": hex, "budget_class": str}; the input mappings may carry other keys
        (including "host" / "archive" from an earlier run, which are ignored).
        HostPlan.files: list of dicts, one per input file sorted by "path", each the input plus "host" ("git" |
        "release") and "archive" (None, or the name of its per-class archive); HostPlan.archives: list of
        {"name": f"{class}.tar", "class": class, "members": [paths sorted]} sorted by class; HostPlan.git_bytes: int
        (sum of the bytes of the git-hosted files). Plain `==` on `plan.files` and `plan.archives` is the identity used
        by P-016-10.
        Rule: a file with bytes >= GIT_FILE_BYTES_MAX is a release asset on its own; the remaining files are git
        candidates; while their total exceeds GIT_BAKED_BYTES_MAX, the budget class with the largest candidate total
        (ties: smaller class id first) is moved, whole, into its archive ("host" "release").
module `pitstudio.export.release_list`
    class ReleaseListError(Exception)     # `.entry`: the offending path / tag / digest value; the message contains it
    build_release_list(entries: Sequence[Mapping], *, tag: str, root: Path) -> dict
        entries: release-hosted files {"path", "bytes", "sha256"}; returns the DC-016-02 document
        {"schema_version": "1.0", "tag": tag, "entries": [{"path", "bytes", "sha256"} sorted by path]}; raises
        ReleaseListError for the FR-016-16 conditions (and for a malformed digest or non-integer / negative bytes).
    release_list_bytes(doc: Mapping) -> bytes
        deterministic UTF-8 serialisation of the document (equal documents give equal bytes; json.loads gives it back).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.export.hosts import GIT_BAKED_BYTES_MAX, GIT_FILE_BYTES_MAX, assign_hosts
from pitstudio.export.release_list import ReleaseListError, build_release_list, release_list_bytes

ROOT = Path(__file__).resolve().parents[2]
THRESHOLDS = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "contracts" / "release-assets.schema.json").read_text(encoding="utf-8"))
CLASSES = ["videos", "tiles-glb", "shards-clouds", "splats", "onnx", "runtimes", "own-code", "studio-showcase"]


def _sha(i: object) -> str:
    return hashlib.sha256(str(i).encode()).hexdigest()


def _file(path: str, nbytes: int, cls: str = "onnx") -> dict:
    return {"path": path, "bytes": nbytes, "sha256": _sha(path), "budget_class": cls}


def _hosts(plan) -> dict[str, str]:
    return {f["path"]: f["host"] for f in plan.files}


@pytest.mark.req("FR-016-14")
def test_thresholds_in_the_spec_match_the_constants_used_here() -> None:
    assert THRESHOLDS["contracts"]["git_file_bytes_max"] == GIT_FILE_BYTES_MAX == 10_485_760
    assert THRESHOLDS["budgets"]["git_baked_assets_mb_max"] * 10**6 == GIT_BAKED_BYTES_MAX == 100_000_000


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-14: hosts
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-14")
def test_the_single_file_threshold_is_10485760_bytes() -> None:
    plan = assign_hosts([_file("a/small.onnx", 10_485_759), _file("a/big.onnx", 10_485_760), _file("a/zero.bin", 0)])
    assert _hosts(plan) == {"a/small.onnx": "git", "a/big.onnx": "release", "a/zero.bin": "git"}
    assert plan.archives == []
    assert plan.git_bytes == 10_485_759


@pytest.mark.req("FR-016-14")
def test_in_git_total_of_exactly_100_million_bytes_stays_in_git() -> None:
    files = [_file(f"onnx/m{i}.onnx", 5_000_000, "onnx") for i in range(20)]  # 100,000,000
    plan = assign_hosts(files)
    assert set(_hosts(plan).values()) == {"git"}
    assert plan.git_bytes == GIT_BAKED_BYTES_MAX
    assert plan.archives == []


@pytest.mark.req("FR-016-14")
def test_one_byte_over_moves_the_largest_whole_class_into_its_archive() -> None:
    a = [_file(f"tiles/t{i}.glb", 6_000_000, "tiles-glb") for i in range(10)]  # 60,000,000
    b = [_file(f"onnx/m{i}.onnx", 10_000_000, "onnx") for i in range(4)] + [_file("onnx/tiny.onnx", 1, "onnx")]
    plan = assign_hosts(a + b)  # total 100,000,001
    hosts = _hosts(plan)
    assert {hosts[f["path"]] for f in a} == {"release"}
    assert {hosts[f["path"]] for f in b} == {"git"}
    assert plan.git_bytes == 40_000_001
    assert plan.archives == [
        {"name": "tiles-glb.tar", "class": "tiles-glb", "members": sorted(f["path"] for f in a)},
    ]
    assert {f["archive"] for f in plan.files if f["host"] == "release"} == {"tiles-glb.tar"}
    assert {f["archive"] for f in plan.files if f["host"] == "git"} == {None}


@pytest.mark.req("FR-016-14")
def test_classes_move_largest_total_first_until_the_in_git_total_fits() -> None:
    a = [_file(f"a/{i}.bin", 7_000_000, "videos") for i in range(10)]  # 70 MB
    b = [_file(f"b/{i}.bin", 6_000_000, "tiles-glb") for i in range(10)]  # 60 MB
    c = [_file(f"c/{i}.bin", 5_000_000, "splats") for i in range(10)]  # 50 MB; total 180 MB
    plan = assign_hosts(a + b + c)
    hosts = _hosts(plan)
    assert {hosts[f["path"]] for f in a} == {"release"}  # largest first: 180 - 70 = 110 > 100, so continue
    assert {hosts[f["path"]] for f in b} == {"release"}  # 110 - 60 = 50 <= 100, stop
    assert {hosts[f["path"]] for f in c} == {"git"}
    assert [x["class"] for x in plan.archives] == ["tiles-glb", "videos"]  # archives sorted by class id
    assert plan.git_bytes == 50_000_000


@pytest.mark.req("FR-016-14")
def test_files_already_release_hosted_by_size_do_not_count_toward_the_in_git_total() -> None:
    big = [_file(f"v/{i}.mp4", 30_000_000, "videos") for i in range(5)]  # 150 MB, each >= 10 MiB: release on their own
    small = [_file(f"o/{i}.onnx", 9_000_000, "onnx") for i in range(10)]  # 90 MB in git
    plan = assign_hosts(big + small)
    assert plan.archives == []  # the 90 MB candidate total fits; no class is moved
    assert {_hosts(plan)[f["path"]] for f in big} == {"release"}
    assert {f["archive"] for f in plan.files} == {None}
    assert plan.git_bytes == 90_000_000


@pytest.mark.req("FR-016-14")
def test_an_empty_input_gives_an_empty_plan() -> None:
    plan = assign_hosts([])
    assert plan.files == []
    assert plan.archives == []
    assert plan.git_bytes == 0


# ----------------------------------------------------------------------------------------------------------------------
# P-016-10: order invariance and idempotence
# ----------------------------------------------------------------------------------------------------------------------

file_sets = st.lists(st.tuples(st.integers(0, 30_000_000), st.sampled_from(CLASSES)), min_size=0, max_size=60).map(
    lambda xs: [_file(f"assets/{c}/f{i:03d}.bin", n, c) for i, (n, c) in enumerate(xs)]
)


@pytest.mark.req("P-016-10")
@settings(max_examples=200, deadline=None)
@given(files=file_sets, seed=st.integers(0, 10**6))
def test_host_assignment_is_independent_of_input_order_and_idempotent(files, seed):
    import random

    shuffled = list(files)
    random.Random(seed).shuffle(shuffled)
    first = assign_hosts(files)
    second = assign_hosts(shuffled)
    assert (first.files, first.archives, first.git_bytes) == (second.files, second.archives, second.git_bytes)
    again = assign_hosts(first.files)  # re-running on its own output
    assert (again.files, again.archives, again.git_bytes) == (first.files, first.archives, first.git_bytes)
    # the invariants of FR-016-14 hold on the result
    git = [f for f in first.files if f["host"] == "git"]
    assert all(f["bytes"] < GIT_FILE_BYTES_MAX for f in git)
    assert sum(f["bytes"] for f in git) == first.git_bytes <= GIT_BAKED_BYTES_MAX


@pytest.mark.req("P-016-10")
@settings(max_examples=200, deadline=None)
@given(
    paths=st.lists(
        st.from_regex(r"[a-z][a-z0-9]{0,8}(/[a-z][a-z0-9]{0,8}){0,3}\.bin", fullmatch=True),
        min_size=0,
        max_size=40,
        unique=True,
    ),
    seed=st.integers(0, 10**6),
)
def test_release_list_bytes_are_identical_for_any_order_of_the_entries(paths, seed, tmp_path_factory):
    import random

    root = tmp_path_factory.mktemp("bake")
    entries = [{"path": p, "bytes": 10 + i, "sha256": _sha(p)} for i, p in enumerate(paths)]
    shuffled = list(entries)
    random.Random(seed).shuffle(shuffled)
    a = release_list_bytes(build_release_list(entries, tag="assets-v1.00.001", root=root))
    b = release_list_bytes(build_release_list(shuffled, tag="assets-v1.00.001", root=root))
    assert a == b
    assert [e["path"] for e in json.loads(a)["entries"]] == sorted(paths)


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-15: the list
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-15")
def test_release_list_is_sorted_by_path_validates_against_dc_016_02_and_carries_the_tag(tmp_path: Path) -> None:
    from jsonschema import Draft202012Validator

    entries = [
        {"path": "assets/videos/b2-dust.mp4", "bytes": 23_456_789, "sha256": _sha("v")},
        {"path": "assets/models/d-fine-n-fp16.onnx", "bytes": 18_234_567, "sha256": _sha("m")},
        {"path": "assets/shards/a1-replay.tar", "bytes": 41_000_000, "sha256": _sha("s")},
    ]
    doc = build_release_list(entries, tag="assets-v1.00.001", root=tmp_path)
    assert doc["tag"] == "assets-v1.00.001"
    assert doc["schema_version"] == "1.0"
    assert [e["path"] for e in doc["entries"]] == [
        "assets/models/d-fine-n-fp16.onnx",
        "assets/shards/a1-replay.tar",
        "assets/videos/b2-dust.mp4",
    ]
    assert list(Draft202012Validator(SCHEMA).iter_errors(doc)) == []
    assert all(set(e) == {"path", "bytes", "sha256"} for e in doc["entries"])
    assert json.loads(release_list_bytes(doc)) == doc


@pytest.mark.req("FR-016-15")
def test_an_empty_release_list_is_valid(tmp_path: Path) -> None:
    from jsonschema import Draft202012Validator

    doc = build_release_list([], tag="assets-v0.01.000", root=tmp_path)
    assert doc["entries"] == []
    assert list(Draft202012Validator(SCHEMA).iter_errors(doc)) == []


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-16: hostile entries
# ----------------------------------------------------------------------------------------------------------------------


def _entry(path: str, nbytes: int = 100) -> dict:
    return {"path": path, "bytes": nbytes, "sha256": _sha(path)}


@pytest.mark.req("FR-016-16")
@pytest.mark.parametrize(
    "path",
    [
        "/abs/x.onnx",
        "a/../b.onnx",
        "../x.onnx",
        "a\\b.onnx",
        "C:x.onnx",
        "C:/x.onnx",
        "c:\\x.onnx",
        "./x.onnx",
        "a//b.onnx",
        "a/",
        "",
        "a/\x00b.onnx",
    ],
)
def test_unsafe_paths_fail_the_list_naming_the_entry(path: str, tmp_path: Path) -> None:
    with pytest.raises(ReleaseListError) as info:
        build_release_list([_entry("ok/file.onnx"), _entry(path)], tag="assets-v1.00.001", root=tmp_path)
    assert info.value.entry == path
    assert repr(path)[1:-1] in str(info.value) or path in str(info.value)


def _dir_link(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


@pytest.mark.req("FR-016-16")
def test_a_path_that_resolves_outside_the_bake_root_through_a_link_fails_the_list(tmp_path: Path) -> None:
    root = tmp_path / "bake"
    outside = tmp_path / "elsewhere"
    root.mkdir()
    outside.mkdir()
    (outside / "x.onnx").write_bytes(b"x")
    _dir_link(root / "link", outside)
    with pytest.raises(ReleaseListError) as info:
        build_release_list([_entry("link/x.onnx")], tag="assets-v1.00.001", root=root)
    assert info.value.entry == "link/x.onnx"


@pytest.mark.req("FR-016-16")
@pytest.mark.parametrize(
    "tag", ["assets-v1.2.3", "assets-v1.02.3", "assets-1.02.003", "v1.02.003", "assets-v1.02.0003"]
)
def test_a_tag_not_matching_the_pattern_fails_the_list(tag: str, tmp_path: Path) -> None:
    with pytest.raises(ReleaseListError) as info:
        build_release_list([_entry("a/b.onnx")], tag=tag, root=tmp_path)
    assert info.value.entry == tag


@pytest.mark.req("FR-016-16")
@pytest.mark.parametrize("tag", ["assets-v1.00.001", "assets-v10.99.999", "assets-v0.01.000"])
def test_tags_matching_the_pattern_are_accepted(tag: str, tmp_path: Path) -> None:
    assert build_release_list([_entry("a/b.onnx")], tag=tag, root=tmp_path)["tag"] == tag


@pytest.mark.req("FR-016-16")
def test_a_file_of_2_pow_31_bytes_fails_the_list_and_one_byte_less_passes(tmp_path: Path) -> None:
    ok = build_release_list([_entry("a/big.bin", 2**31 - 1)], tag="assets-v1.00.001", root=tmp_path)
    assert ok["entries"][0]["bytes"] == 2**31 - 1
    with pytest.raises(ReleaseListError) as info:
        build_release_list([_entry("a/huge.bin", 2**31)], tag="assets-v1.00.001", root=tmp_path)
    assert info.value.entry == "a/huge.bin"


@pytest.mark.req("FR-016-16")
@pytest.mark.parametrize(
    "bad",
    [
        {"bytes": -1},
        {"bytes": 1.5},
        {"bytes": True},
        {"bytes": "10"},
        {"sha256": "ABCDEF" + "0" * 58},
        {"sha256": "0" * 63},
        {"sha256": None},
    ],
)
def test_malformed_sizes_and_digests_fail_the_list(bad: dict, tmp_path: Path) -> None:
    entry = {**_entry("a/b.onnx"), **bad}
    with pytest.raises(ReleaseListError):
        build_release_list([entry], tag="assets-v1.00.001", root=tmp_path)
