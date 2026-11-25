# ruff: noqa: E501
"""T-015-010: verification of the pinned llama.cpp b11381 archives and executables, and the exit-code-2 refusal of every st59_* stage.

Requirements: FR-015-01, FR-015-02.

Spec: specs/015-vlm/spec.md
- FR-015-01: the reason lane runs llama.cpp build b11381 (Windows CUDA 13.4 x64 archive and its matching `cudart` archive), unpacked
  outside the repository, after verifying both archives and every executable it invokes against the SHA-256 values in
  `studio/reason/pins.json` (`contracts/reason-pins.schema.json`).
- FR-015-02: if a pinned archive or executable is missing or its SHA-256 differs from the pin, or the pin file is invalid, then every
  `st59_*` stage exits with code 2 before starting any process, naming the file.

Oracle: SHA-256 recomputed with `hashlib` on small fixture files (`_p015_pins_kit.build_env`); a tampered-file corpus (one appended byte,
truncation, empty file, missing file, directory in place of a file); the spec's hostile pin corpus
(`specs/015-vlm/contracts/examples/reason-pins.hostile-*.json`, each rejected by the schema); a fake process launcher that records every
call (the stage must not call it).

Expected API of the implementation (package `pitstudio_pipeline`, pipeline environment), `pitstudio_pipeline.reason.runtime`:
- `PinError(Exception)`: `exit_code == 2`, `file` (the name of the offending file: an archive or executable name, `pins.json` for the
  pin file, `runtime_dir` for a runtime folder inside the repository), `reason` (text); `str(error)` names the file.
- `load_pins(path) -> dict`: reads and validates the pin file against `contracts/reason-pins.schema.json`; PinError on an unreadable,
  non-JSON, empty or schema-invalid file.
- `verify_runtime(pins, *, archive_dir, runtime_dir, repo_root) -> VerifiedRuntime`: checks that both archives exist in `archive_dir` with
  the pinned SHA-256 (and byte count) and that every executable of `pins["llamacpp"]["executables"]` exists in `runtime_dir` with its pinned
  SHA-256; `runtime_dir` must lie outside `repo_root`. `VerifiedRuntime.build == "b11381"` and `.executable(name) -> Path`
  (KeyError for a name that is not pinned).
`pitstudio_pipeline.reason.stages`:
- `STAGES == ("st59_reason_bench", "st59a_vqa", "st59b_plausibility", "st59c_captions")`.
- `preflight(stage, *, pins_path, archive_dir, runtime_dir, repo_root) -> VerifiedRuntime` (the check every stage runs first; PinError on
  failure; ValueError for an unknown stage).
- `run_stage(stage, *, pins_path, archive_dir, runtime_dir, repo_root, launcher, **stage_args) -> int`: runs `preflight` before anything else;
  on PinError it writes the message (naming the file) to stderr, returns 2 and never calls `launcher` (a callable that would start a process).
"""

from __future__ import annotations

import json
from pathlib import Path

import _p015_pins_kit as kit
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pitstudio_pipeline.reason import runtime, stages

SPEC_EXAMPLES = Path(__file__).resolve().parents[2] / "specs" / "015-vlm" / "contracts" / "examples"
PINNED = [kit.BINARIES, kit.CUDART, *kit.EXECUTABLES]


@pytest.fixture
def env(tmp_path: Path) -> kit.Env:
    return kit.build_env(tmp_path)


def _verify(env: kit.Env):
    return runtime.verify_runtime(
        env.pins, archive_dir=env.archive_dir, runtime_dir=env.runtime_dir, repo_root=env.repo_root
    )


def _kwargs(env: kit.Env, launcher) -> dict:
    return {
        "pins_path": env.pins_path,
        "archive_dir": env.archive_dir,
        "runtime_dir": env.runtime_dir,
        "repo_root": env.repo_root,
        "launcher": launcher,
    }


@pytest.mark.req("FR-015-01")
def test_both_archives_and_every_executable_are_verified_against_the_pins(env: kit.Env) -> None:
    rt = _verify(env)
    assert rt.build == "b11381"
    for name in kit.EXECUTABLES:
        assert rt.executable(name) == env.runtime_dir / name
    with pytest.raises(KeyError):
        rt.executable("llama-evil.exe")


@pytest.mark.req("FR-015-01")
def test_the_pin_file_is_loaded_and_validated_against_the_schema(env: kit.Env) -> None:
    assert runtime.load_pins(env.pins_path) == env.pins
    valid = json.loads((SPEC_EXAMPLES / "reason-pins.valid.json").read_text(encoding="utf-8"))
    p = env.root / "valid-example.json"
    p.write_text(json.dumps(valid), encoding="utf-8")
    assert runtime.load_pins(p) == valid


@pytest.mark.req("FR-015-01")
def test_the_runtime_must_be_unpacked_outside_the_repository(env: kit.Env) -> None:
    inside = env.repo_root / "tools" / "llama"
    inside.mkdir(parents=True)
    for name in kit.EXECUTABLES:
        (inside / name).write_bytes(env.files[name].read_bytes())
    with pytest.raises(runtime.PinError) as exc:
        runtime.verify_runtime(env.pins, archive_dir=env.archive_dir, runtime_dir=inside, repo_root=env.repo_root)
    assert exc.value.exit_code == 2
    assert exc.value.file == "runtime_dir"
    assert "runtime_dir" in str(exc.value)


@pytest.mark.req("FR-015-02")
@pytest.mark.parametrize("name", PINNED)
@pytest.mark.parametrize("how", ["flipped-byte", "appended-byte", "truncated", "empty", "missing", "directory"])
def test_a_missing_or_altered_pinned_file_is_refused_naming_it(env: kit.Env, name: str, how: str) -> None:
    f = env.files[name]
    data = f.read_bytes()
    if how == "flipped-byte":
        f.write_bytes(data[:100] + bytes([data[100] ^ 1]) + data[101:])
    elif how == "appended-byte":
        f.write_bytes(data + b"\x00")
    elif how == "truncated":
        f.write_bytes(data[:-1])
    elif how == "empty":
        f.write_bytes(b"")
    elif how == "missing":
        f.unlink()
    else:
        f.unlink()
        f.mkdir()
    with pytest.raises(runtime.PinError) as exc:
        _verify(env)
    assert exc.value.exit_code == 2
    assert exc.value.file == name
    assert name in str(exc.value)


@pytest.mark.req("FR-015-02")
def test_an_executable_pinned_but_absent_from_the_runtime_folder_is_refused(env: kit.Env) -> None:
    extra = dict(env.pins["llamacpp"]["executables"])
    extra["llama-extra.exe"] = kit.sha256_hex(b"never unpacked")
    pins = json.loads(json.dumps(env.pins))
    pins["llamacpp"]["executables"] = extra
    with pytest.raises(runtime.PinError, match=r"llama-extra\.exe"):
        runtime.verify_runtime(pins, archive_dir=env.archive_dir, runtime_dir=env.runtime_dir, repo_root=env.repo_root)


@pytest.mark.req("FR-015-02")
@pytest.mark.parametrize("path", sorted(SPEC_EXAMPLES.glob("reason-pins.hostile-*.json")), ids=lambda p: p.stem)
def test_every_hostile_pin_file_of_the_spec_corpus_is_refused_naming_the_pin_file(env: kit.Env, path: Path) -> None:
    p = env.root / "hostile-pins.json"
    p.write_bytes(path.read_bytes())
    with pytest.raises(runtime.PinError) as exc:
        runtime.load_pins(p)
    assert exc.value.exit_code == 2
    assert "pins.json" in str(exc.value)


@pytest.mark.req("FR-015-02")
@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"{",
        b"null",
        b"[]",
        b'{"schema_version": "1.0"}',
        b"\xff\xfe\x00",
        b'{"a": NaN}',
        '{"llamacpp": "é"}'.encode(),
    ],
)
def test_an_unreadable_or_malformed_pin_file_is_refused(env: kit.Env, content: bytes) -> None:
    env.pins_path.write_bytes(content)
    with pytest.raises(runtime.PinError) as exc:
        runtime.load_pins(env.pins_path)
    assert exc.value.exit_code == 2


@pytest.mark.req("FR-015-02")
def test_a_missing_pin_file_and_a_pin_file_that_is_a_directory_are_refused(env: kit.Env) -> None:
    env.pins_path.unlink()
    with pytest.raises(runtime.PinError):
        runtime.load_pins(env.pins_path)
    env.pins_path.mkdir()
    with pytest.raises(runtime.PinError):
        runtime.load_pins(env.pins_path)


@pytest.mark.req("FR-015-02")
@pytest.mark.parametrize("stage", kit.STAGES)
@pytest.mark.parametrize("name", [kit.BINARIES, kit.CUDART, "llama-server.exe", "llama-quantize.exe"])
def test_every_stage_exits_with_code_2_naming_the_file_before_starting_any_process(
    env: kit.Env, capsys: pytest.CaptureFixture[str], stage: str, name: str
) -> None:
    f = env.files[name]
    f.write_bytes(f.read_bytes() + b"x")
    calls: list = []
    code = stages.run_stage(stage, **_kwargs(env, lambda *a, **k: calls.append((a, k))))
    assert code == 2
    assert calls == []
    assert name in capsys.readouterr().err


@pytest.mark.req("FR-015-02")
@pytest.mark.parametrize("stage", kit.STAGES)
def test_every_stage_refuses_an_invalid_pin_file_with_code_2_and_starts_nothing(
    env: kit.Env, capsys: pytest.CaptureFixture[str], stage: str
) -> None:
    env.pins_path.write_text("{ not json", encoding="utf-8")
    calls: list = []
    assert stages.run_stage(stage, **_kwargs(env, lambda *a, **k: calls.append(a))) == 2
    assert calls == []
    assert "pins.json" in capsys.readouterr().err


@pytest.mark.req("FR-015-02")
def test_the_stage_list_is_the_four_st59_stages_and_an_unknown_stage_is_refused(env: kit.Env) -> None:
    assert tuple(stages.STAGES) == kit.STAGES
    with pytest.raises(ValueError):  # noqa: PT011
        stages.preflight(
            "st59z_other",
            pins_path=env.pins_path,
            archive_dir=env.archive_dir,
            runtime_dir=env.runtime_dir,
            repo_root=env.repo_root,
        )


@pytest.mark.req("FR-015-01")
@pytest.mark.parametrize("stage", kit.STAGES)
def test_preflight_of_an_intact_environment_returns_the_verified_runtime_and_starts_nothing(
    env: kit.Env, stage: str
) -> None:
    rt = stages.preflight(
        stage,
        pins_path=env.pins_path,
        archive_dir=env.archive_dir,
        runtime_dir=env.runtime_dir,
        repo_root=env.repo_root,
    )
    assert rt.build == "b11381"


@pytest.mark.req("FR-015-02")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.sampled_from(PINNED), st.integers(0, 10_000), st.integers(1, 255))
def test_property_any_single_byte_change_in_any_pinned_file_is_refused_naming_that_file(
    env: kit.Env, name: str, offset: int, xor: int
) -> None:
    f = env.files[name]
    original = f.read_bytes()
    data = bytearray(original)
    data[offset % len(data)] ^= xor
    f.write_bytes(bytes(data))
    try:
        with pytest.raises(runtime.PinError) as exc:
            _verify(env)
        assert exc.value.file == name
    finally:
        f.write_bytes(original)
