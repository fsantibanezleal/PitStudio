# ruff: noqa: E501, PT018
"""T-008-014: oversize bodies and headers, insufficient disk, unsafe local names, insecure redirects, unsafe data root.

Requirements: FR-008-10, FR-008-11, FR-008-15.

Spec: specs/008-data-pipeline/spec.md FR-008-10, FR-008-11, FR-008-15.

Oracle: hand-built hostile transports (a body longer than the declared size, a `Content-Length` larger than the declared
size, redirects to non-HTTPS URLs) and hostile names written as percent-encoded URL segments; the 1.2 x (bytes +
uncompressed_bytes) free-space rule computed by hand (1.2 x 11,000 = 13,200; 1.2 x 1,000 = 1,200), tested one unit on
each side of the limit; a temporary fake repository tree for the data-root rule.

Expected API of the implementation:
- `run_download(..., free_disk=callable, ...)`: `free_disk(path) -> int` returns the free bytes at the target (default
  `shutil.disk_usage(path).free`).
- Per-source errors land in `result.errors[source_id]` (and `exit_status != 0`): `Oversize`, `InsufficientDisk`,
  `UnsafePath`, `InsecureRedirect` from `pitstudio_pipeline.errors`; no file of the source remains on disk (no final file,
  no `.part`, nothing in quarantine) for these four.
- `pitstudio_pipeline.paths.check_data_root(data_root, *, repo_root) -> pathlib.Path` returns the resolved root or raises
  `pitstudio_pipeline.errors.UnsafeDataRoot`; `run_download` calls it first (data root from the argument, else
  `env["PITSTUDIO_DATA"]`). A root is acceptable when it resolves outside the repository working tree (a directory with
  a `.git` entry) or inside one of `data/raw`, `data/external`, `data/interim`, `data/processed`, `data/synthetic`.
"""

from __future__ import annotations

from pathlib import Path

import _p008_kit as kit
import httpx
import pytest
from pitstudio_pipeline.download import run_download
from pitstudio_pipeline.errors import InsecureRedirect, InsufficientDisk, Oversize, UnsafeDataRoot, UnsafePath
from pitstudio_pipeline.paths import check_data_root

BASE = "https://example.org/d/"
CHUNK = 65_536


def _one(tmp_path: Path, url: str, data: bytes, route, **kw):
    net = kit.Net({url: route})
    result = kit.run(tmp_path, [kit.entry("h", [kit.file_rec(url, data)])], net, **kw)
    return result, net


# ------------------------------------------------------------------------------------------------ FR-008-10
@pytest.mark.req("FR-008-10")
def test_announced_content_length_above_the_declared_size_aborts_before_the_body(tmp_path: Path) -> None:
    declared = kit.payload(100_000, 1)
    stream = kit.CutStream(b"x" * (5 * (1 << 20)), chunk=CHUNK)
    route = lambda r: httpx.Response(200, headers={"Content-Length": str(5 * (1 << 20))}, stream=stream)  # noqa: E731
    result, _ = _one(tmp_path, BASE + "a.bin", declared, route)
    assert isinstance(result.errors["h"], Oversize) and result.exit_status != 0
    assert stream.yielded <= len(declared) + 2 * CHUNK, "the body must not be consumed past the declared size"
    assert kit.files_under(tmp_path / "data") == []


@pytest.mark.req("FR-008-10")
def test_body_longer_than_declared_without_a_length_header_is_aborted_and_deleted(tmp_path: Path) -> None:
    declared = kit.payload(100_000, 2)
    stream = kit.CutStream(declared + kit.payload(5 * (1 << 20), 3), chunk=CHUNK)
    route = lambda r: httpx.Response(200, stream=stream)  # noqa: E731
    result, _ = _one(tmp_path, BASE + "a.bin", declared, route)
    assert isinstance(result.errors["h"], Oversize)
    assert stream.yielded <= len(declared) + 2 * CHUNK
    assert kit.files_under(tmp_path / "data") == [], "the partial file is deleted"


@pytest.mark.req("FR-008-10")
def test_one_byte_too_many_is_oversize(tmp_path: Path) -> None:
    declared = kit.payload(4096, 4)
    route = lambda r: httpx.Response(200, stream=kit.CutStream(declared + b"\0"))  # noqa: E731
    result, _ = _one(tmp_path, BASE + "a.bin", declared, route)
    assert isinstance(result.errors["h"], Oversize)
    assert kit.files_under(tmp_path / "data") == []


@pytest.mark.req("FR-008-10")
@pytest.mark.parametrize(
    ("free", "refused"),
    [(13_199, True), (13_201, False), (0, True), (10**15, False)],
)
def test_free_space_rule_with_uncompressed_size(free: int, refused: bool, tmp_path: Path) -> None:
    data = kit.payload(1000, 5)
    f = kit.file_rec(BASE + "arc.zip", data, kind="archive", uncompressed_bytes=10_000)
    net = kit.Net({BASE + "arc.zip": data})
    result = kit.run(tmp_path, [kit.entry("h", [f])], net, free_disk=lambda path: free)
    if refused:
        assert isinstance(result.errors["h"], InsufficientDisk) and result.exit_status != 0
        assert net.requests == [], "the file must not even be requested"
        assert kit.files_under(tmp_path / "data") == []
    else:
        assert result.exit_status == 0 and "h" not in result.errors


@pytest.mark.req("FR-008-10")
@pytest.mark.parametrize(("free", "refused"), [(1_199, True), (1_201, False)])
def test_free_space_rule_without_uncompressed_size(free: int, refused: bool, tmp_path: Path) -> None:
    data = kit.payload(1000, 6)
    net = kit.Net({BASE + "a.bin": data})
    result = kit.run(tmp_path, [kit.entry("h", [kit.file_rec(BASE + "a.bin", data)])], net, free_disk=lambda p: free)
    assert (isinstance(result.errors.get("h"), InsufficientDisk)) is refused


# ------------------------------------------------------------------------------------------------ FR-008-11
UNSAFE_SEGMENTS = {
    "dotdot": "%2E%2E",
    "encoded-slash": "a%2Fb.bin",
    "encoded-backslash": "a%5Cb.bin",
    "double-encoded-dots": "%2e%2e%2f%2e%2e%2fetc",
    "drive-letter": "C%3Aevil.bin",
    "nul": "a%00b.bin",
    "newline": "a%0Ab.bin",
    "unit-separator": "a%1Fb.bin",
    "delete": "a%7Fb.bin",
    "con": "CON",
    "prn-lower": "prn",
    "aux": "AUX",
    "nul-device": "NUL",
    "com1": "COM1",
    "lpt9-lower": "lpt9",
    "too-long": "a" * 197 + ".bin",  # 201 characters
}


@pytest.mark.req("FR-008-11")
@pytest.mark.parametrize("seg", list(UNSAFE_SEGMENTS.values()), ids=list(UNSAFE_SEGMENTS))
def test_unsafe_local_names_are_rejected_before_anything_is_written(seg: str, tmp_path: Path) -> None:
    url = BASE + seg
    data = kit.payload(64, 7)
    result, _ = _one(tmp_path, url, data, data)
    assert isinstance(result.errors["h"], UnsafePath) and result.exit_status != 0
    assert kit.files_under(tmp_path / "data") == []
    assert not (tmp_path / "evil.bin").exists() and not (tmp_path / "etc").exists()


@pytest.mark.req("FR-008-11")
@pytest.mark.parametrize("seg", ["a.bin", "a" * 196 + ".bin", "tile_01-v2.1.laz", "COM10", "console", "nullable.bin"])
def test_safe_names_are_accepted_including_the_200_character_limit(seg: str, tmp_path: Path) -> None:
    assert len(seg) <= 200
    url = BASE + seg
    data = kit.payload(64, 8)
    result, _ = _one(tmp_path, url, data, data)
    assert result.exit_status == 0, result.errors
    assert (tmp_path / "data" / "raw" / "h" / seg).read_bytes() == data


@pytest.mark.req("FR-008-11")
@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("target", ["http://example.org/x.bin", "ftp://example.org/x.bin", "file:///etc/passwd"])
def test_redirect_to_a_non_https_url_is_rejected(code: int, target: str, tmp_path: Path) -> None:
    data = kit.payload(64, 9)
    route = lambda r: httpx.Response(code, headers={"Location": target})  # noqa: E731
    result, net = _one(tmp_path, BASE + "a.bin", data, route)
    assert isinstance(result.errors["h"], InsecureRedirect) and result.exit_status != 0
    assert kit.files_under(tmp_path / "data") == []
    assert all(u.startswith("https://") for u in net.urls), "the insecure target must never be requested"


@pytest.mark.req("FR-008-11")
def test_https_chain_that_ends_on_http_is_rejected_and_relative_https_redirect_is_followed(tmp_path: Path) -> None:
    data = kit.payload(64, 10)
    net = kit.Net(
        {
            BASE + "a.bin": lambda r: httpx.Response(
                302, headers={"Location": "/other/a.bin"}
            ),  # relative: stays HTTPS
            "https://example.org/other/a.bin": lambda r: httpx.Response(
                302, headers={"Location": "http://example.org/z"}
            ),
        }
    )
    result = kit.run(tmp_path, [kit.entry("h", [kit.file_rec(BASE + "a.bin", data)])], net)
    assert isinstance(result.errors["h"], InsecureRedirect)
    good = kit.Net(
        {
            BASE + "a.bin": lambda r: httpx.Response(302, headers={"Location": "/other/a.bin"}),
            "https://example.org/other/a.bin": data,
        }
    )
    ok = kit.run(tmp_path / "second", [kit.entry("h", [kit.file_rec(BASE + "a.bin", data)])], good)
    assert ok.exit_status == 0 and ok.records[0]["final_url"] == "https://example.org/other/a.bin"


# ------------------------------------------------------------------------------------------------ FR-008-15
@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = kit.make_repo(tmp_path)
    (r / "src").mkdir()
    return r


@pytest.mark.req("FR-008-15")
@pytest.mark.parametrize(
    "rel",
    [".", "data", "data/samples", "data/splits", "data/cards", "src", "data/raw/../samples", "data/rawish", "newdir"],
)
def test_data_root_inside_the_repository_but_outside_the_ignored_folders_is_refused(rel: str, repo: Path) -> None:
    with pytest.raises(UnsafeDataRoot):
        check_data_root(repo / rel, repo_root=repo)


@pytest.mark.req("FR-008-15")
@pytest.mark.parametrize(
    "rel",
    [
        "data/raw",
        "data/raw/sub",
        "data/external",
        "data/interim",
        "data/processed/x/y",
        "data/synthetic",
        "data/raw/not/yet/there",
    ],
)
def test_data_root_inside_an_ignored_data_folder_is_accepted(rel: str, repo: Path) -> None:
    assert Path(check_data_root(repo / rel, repo_root=repo)) == (repo / rel).resolve()


@pytest.mark.req("FR-008-15")
def test_data_root_outside_the_repository_is_accepted_even_with_a_similar_prefix(tmp_path: Path, repo: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    sibling = tmp_path / (repo.name + "2")  # string-prefix of the repository path, but a different directory
    sibling.mkdir()
    for p in (elsewhere, sibling):
        assert Path(check_data_root(p, repo_root=repo)) == p.resolve()


@pytest.mark.req("FR-008-15")
def test_run_download_refuses_an_unsafe_root_from_the_argument_and_from_the_environment(
    repo: Path, tmp_path: Path
) -> None:
    data = kit.payload(32, 11)
    reg = kit.write_registry(tmp_path / "cfg", [kit.entry("u", [kit.file_rec(BASE + "a.bin", data)])])
    schema = kit.draft_schema_path("sources.schema.json")
    for kwargs in (
        {"data_root": repo / "data"},
        {"data_root": None, "env": kit.env_with(PITSTUDIO_DATA=str(repo / "src"))},
    ):
        net = kit.Net({BASE + "a.bin": data}, forbid=True)
        kwargs.setdefault("env", kit.env_with())
        with pytest.raises(UnsafeDataRoot):
            run_download(
                reg, kwargs.pop("data_root"), transport=net.transport, repo_root=repo, schema_path=schema, **kwargs
            )
        assert net.requests == []
    assert kit.files_under(repo / "data") == []
