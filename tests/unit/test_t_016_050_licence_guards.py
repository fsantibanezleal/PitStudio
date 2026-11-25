"""T-016-050: engine and cache guard, licence-hash gate, local-only backends (unit, hostile).

Requirements: FR-016-22, FR-016-23, FR-016-33.

Spec: specs/016-export-acceleration/spec.md
- FR-016-22: the engine builder writes engines and timing caches only under the git-ignored run folder, and never
  commits, uploads or lists them in a release-asset list; CI fails on any `*.plan`, `*.engine`, `*.trt` or timing-cache
  file in git or in the Pages artefact;
- FR-016-23: if the SHA-256 of the `LICENSE.txt` of the installed `tensorrt-cu13-libs` differs from
  `c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4` or the file is missing, `s62_accel` and `s64_bench`
  mark every TensorRT result of that run `performance: local-only`, keep it out of committed and published files, and
  note "TensorRT licence text changed since review";
- FR-016-33: a bench record from TensorRT for RTX, or from any backend whose licence forbids publishing performance
  data, is `performance: local-only` and kept out of every committed or published file; CI fails on any such record
  outside the local run folder.
plan.md test strategy rows FR-016-22 (fixture repository containing `x.plan` -> guard fails), FR-016-23 (fake
distribution metadata with a different `LICENSE.txt` hash or none -> `local-only` and the note), FR-016-33 (a
TensorRT-for-RTX record outside the local folder -> guard fails).

Oracles:
- the spec's own bench-record examples: `bench-record.valid.json` (public, TensorRT 11.3, licence hash equal to the
  pinned one), `bench-record.valid-licence-changed.json` (the same record after the gate: `performance: local-only`, the
  shared constant "measured locally, not published (licence)" in place of every timing, throughput, energy, VRAM,
  thermal and camera-stream value, the observed licence hash, and the note) and `bench-record.valid-local-only.json`
  (the TensorRT-for-RTX record); the expected output of the gate is exactly those documents;
- the pinned licence hash literal of the spec (the preimage is not available, so the gate is also tested with an
  injected pinned digest of a known text: SHA-256 by `hashlib`);
- hand-built fixture trees for the guards.

Expected public API (root environment):
module `pitstudio.accel.licence`
    PINNED_TENSORRT_LICENCE_SHA256 = "c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4"
    LOCAL_ONLY_TEXT = "measured locally, not published (licence)"
    LICENCE_CHANGED_NOTE = "TensorRT licence text changed since review"
    read_installed_licence(dist) -> bytes | None
        `dist.files` is None or a list of objects with `.name` and `.read_binary()` (importlib.metadata PackagePath);
        returns the bytes of the file named exactly `LICENSE.txt`, or None when there is none.
    check_tensorrt_licence(text: bytes | None, *, pinned_sha256: str = PINNED_TENSORRT_LICENCE_SHA256) -> LicenceCheck
        LicenceCheck: ok (SHA-256 of `text` equals the pinned digest), sha256 (hex or None when missing), note (None
        when ok, else LICENCE_CHANGED_NOTE).
    apply_licence_policy(records: Sequence[Mapping], check: LicenceCheck, *,
                         restricted_backends: Collection[str] = ("tensorrt-rtx",)) -> list[dict]
        returns new records in the input order: a record of a restricted backend, and, when `check.ok` is false, a
        record of backend "tensorrt" or "ort-tensorrt" with status "pass" or "rejected", becomes local-only:
        `performance` "local-only"; `latency`, `throughput`, `joules_per_inference`, `energy_window_s`,
        `vram_peak_bytes`,
        `thermal_slowdown` and `camera_streams` replaced by LOCAL_ONLY_TEXT; `fingerprint.tensorrt_licence_sha256` is
        left as recorded; the note is appended to `notes` only for the licence-changed cause. Records of other
        backends, and records with status "not_run" or "build-failed" (no numbers), are returned unchanged.
module `pitstudio.accel.guards`
    class GuardError(Exception)
    find_forbidden_artefacts(paths: Iterable[str]) -> list[str]
        the paths (POSIX or Windows separators) whose file name ends with `.plan`, `.engine` or `.trt`
        (case-insensitive), or is a timing cache (the name contains both "timing" and "cache", case-insensitive);
        sorted, each once.
    scan_tree(root: Path) -> list[str]            # relative POSIX paths of the forbidden artefacts under root
    assert_under_run_folder(path: Path, run_dir: Path) -> None     # GuardError when `path` is not inside `run_dir`
    find_local_only_records(root: Path, *, local_dir: Path) -> list[Path]
        JSON files under `root`, outside `local_dir`, that hold a bench record (or a table row / list of them) with
        `performance == "local-only"`.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pitstudio.accel.guards import (
    GuardError,
    assert_under_run_folder,
    find_forbidden_artefacts,
    find_local_only_records,
    scan_tree,
)
from pitstudio.accel.licence import (
    LICENCE_CHANGED_NOTE,
    LOCAL_ONLY_TEXT,
    PINNED_TENSORRT_LICENCE_SHA256,
    apply_licence_policy,
    check_tensorrt_licence,
    read_installed_licence,
)

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "016-export-acceleration" / "contracts" / "examples"
CHANGED_HASH = "d67e2e944994496c8d8ec76eed0cf9f09679448d584b532bebf941852a37f5ed"


def _load(name: str) -> dict:
    return json.loads((EX / name).read_text(encoding="utf-8"))


class _File:
    def __init__(self, name: str, data: bytes) -> None:
        self.name, self._data = name, data

    def read_binary(self) -> bytes:
        return self._data


class _Dist:
    def __init__(self, files) -> None:
        self.files = files


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-22
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-22")
@pytest.mark.parametrize(
    "path",
    [
        "x.plan",
        "runs/20261020/engines/d-fine-n-fp16.engine",
        "a/b/c.trt",
        "UPPER.PLAN",
        "model.Engine",
        "runs\\r1\\engines\\m.trt",
        "timing.cache",
        "runs/r1/Timing-Cache.bin",
        "engines/d-fine.timing_cache",
        "trt_timingcache.dat",
    ],
)
def test_engine_and_timing_cache_files_are_forbidden(path: str) -> None:
    assert find_forbidden_artefacts(["ok/readme.md", path, "src/pitstudio/x.py"]) == [path]


@pytest.mark.req("FR-016-22")
@pytest.mark.parametrize(
    "path",
    [
        "plan.md",
        "docs/plan.md",
        "specs/016-export-acceleration/plan.md",
        "engine.py",
        "trt_notes.txt",
        "cache.json",
        "timing.json",
        "a/planet",
        "model.onnx",
        "my.plan.md",
        "engines.md",
    ],
)
def test_ordinary_files_are_not_flagged(path: str) -> None:
    assert find_forbidden_artefacts([path]) == []


@pytest.mark.req("FR-016-22")
def test_findings_are_sorted_and_unique() -> None:
    paths = ["z.plan", "a.engine", "a.engine", "m/b.trt"]
    assert find_forbidden_artefacts(paths) == ["a.engine", "m/b.trt", "z.plan"]


@pytest.mark.req("FR-016-22")
def test_a_fixture_repository_or_pages_artefact_containing_an_engine_is_found(tmp_path: Path) -> None:
    (tmp_path / "web" / "public" / "assets").mkdir(parents=True)
    (tmp_path / "web" / "public" / "assets" / "ok.json").write_text("{}", encoding="utf-8")
    (tmp_path / "x.plan").write_bytes(b"\x00")
    (tmp_path / "web" / "public" / "assets" / "model.trt").write_bytes(b"\x00")
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "timing.cache").write_bytes(b"\x00")
    assert scan_tree(tmp_path) == ["runs/timing.cache", "web/public/assets/model.trt", "x.plan"]


@pytest.mark.req("FR-016-22")
def test_a_clean_tree_has_no_findings(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "model.onnx").write_bytes(b"\x00")
    assert scan_tree(tmp_path) == []


@pytest.mark.req("FR-016-22")
def test_engines_and_caches_must_be_written_inside_the_run_folder(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "r1"
    run.mkdir(parents=True)
    assert assert_under_run_folder(run / "engines" / "m.engine", run) is None
    for outside in (tmp_path / "m.engine", run.parent / "other" / "m.engine", run / ".." / "m.engine"):
        with pytest.raises(GuardError):
            assert_under_run_folder(outside, run)


@pytest.mark.req("FR-016-22")
def test_a_path_through_a_link_that_leaves_the_run_folder_is_refused(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys

    run, outside = tmp_path / "run", tmp_path / "elsewhere"
    run.mkdir()
    outside.mkdir()
    try:
        os.symlink(outside, run / "link", target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        subprocess.run(["cmd", "/c", "mklink", "/J", str(run / "link"), str(outside)], check=True, capture_output=True)
    with pytest.raises(GuardError):
        assert_under_run_folder(run / "link" / "m.engine", run)


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-23
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-23")
def test_the_pinned_digest_and_the_note_are_the_spec_literals() -> None:
    assert PINNED_TENSORRT_LICENCE_SHA256 == "c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4"
    assert LICENCE_CHANGED_NOTE == "TensorRT licence text changed since review"
    assert LOCAL_ONLY_TEXT == "measured locally, not published (licence)"


@pytest.mark.req("FR-016-23")
def test_the_reviewed_text_passes_and_any_other_text_fails_with_the_note() -> None:
    reviewed = b"reviewed licence text\n"
    pinned = hashlib.sha256(reviewed).hexdigest()
    ok = check_tensorrt_licence(reviewed, pinned_sha256=pinned)
    assert (ok.ok, ok.sha256, ok.note) == (True, pinned, None)
    changed = check_tensorrt_licence(reviewed + b" ", pinned_sha256=pinned)
    assert changed.ok is False
    assert changed.sha256 == hashlib.sha256(reviewed + b" ").hexdigest()
    assert changed.note == "TensorRT licence text changed since review"


@pytest.mark.req("FR-016-23")
def test_a_missing_licence_file_fails_the_check() -> None:
    check = check_tensorrt_licence(None)
    assert check.ok is False
    assert check.sha256 is None
    assert check.note == "TensorRT licence text changed since review"


@pytest.mark.req("FR-016-23")
def test_a_text_that_is_not_the_pinned_one_fails_against_the_default_pin() -> None:
    assert check_tensorrt_licence(b"some other licence").ok is False
    assert check_tensorrt_licence(b"").ok is False


@pytest.mark.req("FR-016-23")
def test_the_installed_licence_is_read_from_the_distribution_files() -> None:
    dist = _Dist([_File("METADATA", b"m"), _File("LICENSE.txt", b"text"), _File("RECORD", b"r")])
    assert read_installed_licence(dist) == b"text"
    assert read_installed_licence(_Dist([_File("METADATA", b"m")])) is None
    assert read_installed_licence(_Dist(None)) is None
    assert read_installed_licence(_Dist([_File("LICENSE.txt.bak", b"x"), _File("license.TXT", b"x")])) is None


@pytest.mark.req("FR-016-23")
def test_a_changed_licence_turns_a_public_tensorrt_record_into_the_spec_local_only_example() -> None:
    record = _load("bench-record.valid.json")
    record["fingerprint"]["tensorrt_licence_sha256"] = CHANGED_HASH  # the digest observed on this run
    check = check_tensorrt_licence(b"changed text")
    (out,) = apply_licence_policy([record], check)
    assert out == _load("bench-record.valid-licence-changed.json")
    assert record["performance"] == "public"  # the input is not modified


@pytest.mark.req("FR-016-23")
def test_every_tensorrt_result_of_the_run_is_marked_including_the_onnx_runtime_provider_ones() -> None:
    base = _load("bench-record.valid.json")
    ort_trt = copy.deepcopy(base)
    ort_trt.update(backend="ort-tensorrt", tensorrt_version="10.14.1.48")
    rejected = _load("bench-record.valid-rejected.json")
    check = check_tensorrt_licence(None)
    out = apply_licence_policy([base, ort_trt, rejected], check)
    assert [r["performance"] for r in out] == ["local-only"] * 3
    assert all(r["latency"] == LOCAL_ONLY_TEXT for r in out)
    assert all(LICENCE_CHANGED_NOTE in r["notes"] for r in out)


@pytest.mark.req("FR-016-23")
def test_other_backends_and_cells_without_numbers_are_unchanged_by_the_licence_gate() -> None:
    cpu = _load("bench-record.valid.json")
    cpu.update(backend="ort-cpu", tensorrt_version=None)
    not_run = _load("bench-record.valid-not-run.json")  # ort-tensorrt, no numbers
    check = check_tensorrt_licence(None)
    assert apply_licence_policy([cpu, not_run], check) == [cpu, not_run]


@pytest.mark.req("FR-016-23")
def test_a_passing_licence_check_leaves_public_tensorrt_records_public() -> None:
    reviewed = b"reviewed"
    check = check_tensorrt_licence(reviewed, pinned_sha256=hashlib.sha256(reviewed).hexdigest())
    record = _load("bench-record.valid.json")
    assert apply_licence_policy([record], check) == [record]


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-33
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-33")
def test_a_tensorrt_for_rtx_record_becomes_the_spec_local_only_example_even_with_a_good_licence() -> None:
    record = _load("bench-record.valid.json")
    record.update(backend="tensorrt-rtx", tensorrt_version="1.2.0.54")
    reviewed = b"reviewed"
    check = check_tensorrt_licence(reviewed, pinned_sha256=hashlib.sha256(reviewed).hexdigest())
    (out,) = apply_licence_policy([record], check)
    assert out == _load("bench-record.valid-local-only.json")
    assert "notes" not in out  # not a licence-change case


@pytest.mark.req("FR-016-33")
def test_another_backend_whose_licence_forbids_publishing_is_local_only_when_named_as_restricted() -> None:
    record = _load("bench-record.valid.json")
    record.update(backend="ort-cuda", tensorrt_version=None)
    check = check_tensorrt_licence(None)
    (out,) = apply_licence_policy([record], check, restricted_backends={"ort-cuda"})
    assert out["performance"] == "local-only"
    assert out["latency"] == LOCAL_ONLY_TEXT


@pytest.mark.req("FR-016-33")
def test_ci_finds_local_only_records_outside_the_local_run_folder(tmp_path: Path) -> None:
    local = tmp_path / "runs" / "r1"
    local.mkdir(parents=True)
    rtx = _load("bench-record.valid-local-only.json")
    (local / "bench-rtx.json").write_text(json.dumps(rtx), encoding="utf-8")  # allowed: inside the local folder
    public = tmp_path / "web" / "public" / "assets"
    public.mkdir(parents=True)
    (public / "bench-rtx-leak.json").write_text(json.dumps(rtx), encoding="utf-8")  # a leak
    (public / "table-leak.json").write_text(json.dumps({"rows": [rtx]}), encoding="utf-8")  # a leaked table row
    (public / "ok.json").write_text(json.dumps(_load("bench-record.valid.json")), encoding="utf-8")
    (public / "not-json.txt").write_text("performance: local-only", encoding="utf-8")
    found = find_local_only_records(tmp_path, local_dir=local)
    assert sorted(p.name for p in found) == ["bench-rtx-leak.json", "table-leak.json"]


@pytest.mark.req("FR-016-33")
def test_ci_scan_tolerates_malformed_json_files(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "list.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert find_local_only_records(tmp_path, local_dir=tmp_path / "runs") == []
