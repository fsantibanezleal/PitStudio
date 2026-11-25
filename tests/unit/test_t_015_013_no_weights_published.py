# ruff: noqa: E501
"""T-015-013: no model weight or conversion in git, in a release-asset upload list or in the Pages artefact; no reference-only artefact in a publish list.

Requirements: FR-015-06.

Spec: specs/015-vlm/spec.md FR-015-06 ("No model weight or conversion - files with the extensions `.gguf`, `.safetensors`, `.pt`, `.pth`, `.bin`
(weights), or a Hugging Face cache folder - shall be tracked in git, listed in a release-asset upload list or copied into the Pages artefact;
artefacts of licence class `reference-only` shall never appear in a publish list"); US-015-3 ("a planted GGUF in the tree is refused").
Licence classes: spec 001 FR-001-18 (total order public-domain < ... < display-only < reference-only).

Oracle: planted fixtures written by the test (file names with each forbidden extension in several spellings, nested folders, Hugging Face cache
layouts `models--<org>--<name>/snapshots/<sha>/...` and `.cache/huggingface/hub/...`, zip and tar members); benign names that merely resemble them;
a throwaway git repository created with `git init` in a temporary folder to exercise the tracked-file scan end to end; the real repository, which
must be clean (its tracked files at this commit contain none of the forbidden names).

Expected API of the implementation (package `pitstudio`, root environment), `pitstudio.reason.guards`:
- `Violation` with `path` (str, the offending path as given, or `archive!member` for an archive member) and `rule` in
  {"weight-extension", "hf-cache-folder", "reference-only", "archive-member"}.
- `scan_tracked_files(paths) -> list[Violation]`: `paths` are repository-relative POSIX paths; flags a final extension in
  {.gguf, .safetensors, .pt, .pth, .bin} (case-insensitive) and any path with a Hugging Face cache component (`models--*--*`, or `.cache/huggingface`).
- `scan_publish_list(entries) -> list[Violation]`: `entries` are paths or `{"path", "licence_class"}` dicts; as above plus every entry whose
  `licence_class` is "reference-only".
- `scan_directory(root) -> list[Violation]`: the same rules over every file below `root` (the Pages artefact folder), also over the member names
  of `.zip`, `.tar`, `.tar.gz` and `.tgz` archives (rule "archive-member").
- `check_repository(repo_root, *, ls_files=None) -> list[Violation]`: `scan_tracked_files` over the tracked files of the repository: the output of\n  `git ls-files` by default, or `ls_files(repo_root) -> list[str]` when given (tests inject a list; pytest temp folders cannot hold a git repository on\n  this platform because of their owner-only ACL).
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pitstudio.reason import guards

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN = [
    "models/cosmos/model-Q8_0.gguf",
    "model.gguf",
    "a/b/c/MODEL.GGUF",
    "x/y/model-00001-of-00002.safetensors",
    "weights.SafeTensors",
    "ckpt/last.pt",
    "ckpt/last.pth",
    "pytorch_model.bin",
    "data/blobs/model.bin",
    "mmproj-F16.gguf",
    "deep/" * 20 + "w.gguf",
    "name with spaces.gguf",
    "unicode-é中.safetensors",
]
HF_CACHE = [
    "models--nvidia--Cosmos-Reason2-2B/snapshots/9ce19a1/config.json",
    "cache/models--Qwen--Qwen3-VL-2B-Instruct/blobs/abc123",
    "home/.cache/huggingface/hub/token",
    ".cache/huggingface/x.json",
    "x/.cache/huggingface",
]
BENIGN = [
    "docs/models/cosmos-reason-2.md",
    "web/src/model.ts",
    "data/samples/x.json",
    "src/pitstudio/gguf_notes.md",
    "models.yaml",
    "weights.md",
    "tests/unit/test_gguf.py",
    "notgguf",
    "src/pt/x.py",
    "file.pth.md",
    "pytorch.bin.md",
    "docs/models--notes.md",
    "gguf/README.md",
    "safetensors-format.txt",
    "ckpt.pt.sha256",
    "huggingface-notes.md",
    "pipeline/src/pitstudio_pipeline/reason/hub.py",
    "",
]


@pytest.mark.req("FR-015-06")
@pytest.mark.parametrize("path", FORBIDDEN, ids=lambda p: p[-30:])
def test_a_tracked_file_with_a_weight_extension_is_a_violation(path: str) -> None:
    (v,) = guards.scan_tracked_files([path])
    assert (v.path, v.rule) == (path, "weight-extension")


@pytest.mark.req("FR-015-06")
@pytest.mark.parametrize("path", HF_CACHE, ids=lambda p: p[:40])
def test_a_tracked_path_inside_a_hugging_face_cache_folder_is_a_violation(path: str) -> None:
    vs = guards.scan_tracked_files([path])
    assert vs
    assert all(v.path == path for v in vs)
    assert {v.rule for v in vs} <= {"hf-cache-folder", "weight-extension"}
    assert "hf-cache-folder" in {v.rule for v in vs}


@pytest.mark.req("FR-015-06")
def test_benign_names_that_only_resemble_weights_are_not_violations() -> None:
    assert guards.scan_tracked_files(BENIGN) == []


@pytest.mark.req("FR-015-06")
def test_every_forbidden_path_in_a_mixed_list_is_reported_once_and_in_order() -> None:
    mixed = [BENIGN[0], FORBIDDEN[0], BENIGN[1], HF_CACHE[0], FORBIDDEN[3]]
    vs = guards.scan_tracked_files(mixed)
    assert [v.path for v in vs] == [FORBIDDEN[0], HF_CACHE[0], FORBIDDEN[3]]


@pytest.mark.req("FR-015-06")
def test_a_release_asset_upload_list_may_not_name_weights_or_hugging_face_caches() -> None:
    entries = [
        "dist/pitstudio-1.00.000.zip",
        "dist/manifest.json",
        {"path": "dist/data.parquet", "licence_class": "own"},
        {"path": "dist/model-Q8_0.gguf", "licence_class": "own"},
        "dist/models--nvidia--Cosmos-Reason2-2B/x",
    ]
    vs = guards.scan_publish_list(entries)
    assert [v.path for v in vs] == ["dist/model-Q8_0.gguf", "dist/models--nvidia--Cosmos-Reason2-2B/x"]


@pytest.mark.req("FR-015-06")
def test_an_artefact_of_licence_class_reference_only_never_appears_in_a_publish_list() -> None:
    entries = [
        {"path": "docs/cases/b1.md", "licence_class": "own"},
        {"path": "data/derived/table.parquet", "licence_class": "reference-only"},
        {"path": "web/records.json", "licence_class": "display-only"},
        {"path": "data/open.csv", "licence_class": "public-domain"},
    ]
    vs = guards.scan_publish_list(entries)
    assert [(v.path, v.rule) for v in vs] == [("data/derived/table.parquet", "reference-only")]


@pytest.mark.req("FR-015-06")
@pytest.mark.parametrize(
    "cls", ["public-domain", "open-no-attribution", "own", "attribution", "share-alike", "display-only"]
)
def test_only_the_reference_only_class_is_refused_by_class(cls: str) -> None:
    assert guards.scan_publish_list([{"path": "web/x.json", "licence_class": cls}]) == []


@pytest.mark.req("FR-015-06")
@pytest.mark.parametrize("bad", [None, 5, {"licence_class": "own"}, {"path": 3}, ["a"]])
def test_a_malformed_publish_entry_is_refused(bad: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        guards.scan_publish_list([bad])  # type: ignore[list-item]


@pytest.mark.req("FR-015-06")
def test_the_pages_artefact_scan_finds_planted_weights_at_any_depth(tmp_path: Path) -> None:
    clean = tmp_path / "site"
    (clean / "assets").mkdir(parents=True)
    (clean / "index.html").write_text("<html></html>", encoding="utf-8")
    (clean / "assets" / "app.js").write_text("export {}", encoding="utf-8")
    assert guards.scan_directory(clean) == []
    planted = clean / "assets" / "a" / "b" / "c"
    planted.mkdir(parents=True)
    (planted / "model-Q8_0.gguf").write_bytes(b"GGUF")
    (clean / "w.safetensors").write_bytes(b"{}")
    cache = clean / "models--nvidia--Cosmos-Reason2-2B" / "snapshots"
    cache.mkdir(parents=True)
    (cache / "config.json").write_text("{}", encoding="utf-8")
    vs = guards.scan_directory(clean)
    paths = {Path(v.path).name for v in vs}
    assert {"model-Q8_0.gguf", "w.safetensors", "config.json"} <= paths
    assert {v.rule for v in vs} >= {"weight-extension", "hf-cache-folder"}


@pytest.mark.req("FR-015-06")
def test_the_pages_artefact_scan_looks_inside_zip_and_tar_archives(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    with zipfile.ZipFile(site / "bundle.zip", "w") as z:
        z.writestr("readme.txt", "hi")
        z.writestr("deep/model.gguf", b"GGUF")
    for name, mode in (("bundle.tar", "w"), ("bundle.tar.gz", "w:gz"), ("bundle.tgz", "w:gz")):
        with tarfile.open(site / name, mode) as t:
            data = b"weights"
            info = tarfile.TarInfo("inner/pytorch_model.bin")
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    with zipfile.ZipFile(site / "clean.zip", "w") as z:
        z.writestr("a/b.txt", "ok")
    vs = guards.scan_directory(site)
    assert {v.rule for v in vs} == {"archive-member"}
    hit = sorted(Path(v.path.split("!")[0]).name for v in vs)
    assert hit == ["bundle.tar", "bundle.tar.gz", "bundle.tgz", "bundle.zip"]
    assert all("!" in v.path for v in vs)


@pytest.mark.req("FR-015-06")
def test_a_corrupt_archive_in_the_artefact_does_not_crash_the_scan(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "broken.zip").write_bytes(b"PK\x03\x04 not really a zip")
    (site / "empty.tar.gz").write_bytes(b"")
    assert isinstance(guards.scan_directory(site), list)


@pytest.mark.req("FR-015-06")
def test_the_scan_of_a_missing_or_file_root_is_refused(tmp_path: Path) -> None:
    with pytest.raises((ValueError, FileNotFoundError, NotADirectoryError)):
        guards.scan_directory(tmp_path / "absent")
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises((ValueError, NotADirectoryError)):
        guards.scan_directory(f)


@pytest.mark.req("FR-015-06")
def test_a_planted_gguf_among_the_tracked_files_of_a_repository_is_found() -> None:
    tracked = ["README.md", "models/cosmos-Q8_0.gguf", "src/app.py", "ignored-by-git-is-not-listed.txt"]
    vs = guards.check_repository(Path("."), ls_files=lambda _root: tracked)
    assert [(v.path, v.rule) for v in vs] == [("models/cosmos-Q8_0.gguf", "weight-extension")]


@pytest.mark.req("FR-015-06")
def test_the_repository_of_this_commit_tracks_no_weight_and_no_hugging_face_cache() -> None:
    assert guards.check_repository(ROOT) == []


_STEM = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=12)
_EXT = st.sampled_from(
    [
        ".gguf",
        ".GGUF",
        ".SafeTensors",
        ".safetensors",
        ".pt",
        ".pth",
        ".bin",
        ".txt",
        ".md",
        ".json",
        ".py",
        ".onnx",
        ".npz",
        ".parquet",
        ".gguf.json",
        ".bin.md",
        "",
    ]
)


@pytest.mark.req("FR-015-06")
@given(st.lists(_STEM, max_size=4), _STEM, _EXT)
def test_property_a_path_is_a_violation_if_and_only_if_its_final_extension_is_forbidden(
    folders: list[str], stem: str, ext: str
) -> None:
    path = "/".join([*folders, stem + ext])
    got = guards.scan_tracked_files([path])
    assert bool(got) == (ext.lower() in {".gguf", ".safetensors", ".pt", ".pth", ".bin"}), path
