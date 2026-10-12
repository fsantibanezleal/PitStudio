# ruff: noqa: E501, PT018
"""T-006-020: FFmpeg discovery, version parse, executable digest, encoder/filter/option listing, the driver gate and the
`not_run` results with their reasons.

Requirements: FR-006-09, FR-006-10, FR-006-11.

Spec: specs/006-media-telemetry/spec.md FR-006-09 (resolve FFmpeg from `PITSTUDIO_FFMPEG`, else from `PATH`; parse the version from
the first line of `-version`; check the executable's SHA-256 against the recipe's pinned `binaries` digest; check that `av1_nvenc`,
`h264_nvenc`, the `libvmaf` filter, the `libwebp` encoder and every declared encoder option are listed by `-encoders`, `-filters`
and `-h encoder=<name>`; all within 10 s), FR-006-10 (not found: `not_run` within 2 s, reason `FFmpeg not found: set PITSTUDIO_FFMPEG
or put ffmpeg on PATH`, no output), FR-006-11 (major >= 9 and NVML driver < 610: reason `FFmpeg <version> needs NVIDIA driver >= 610
(found <driver>); use the pinned FFmpeg 8.1 build`; unparseable version, not the pinned executable, a missing encoder, filter or
declared option: `not_run` with the specific reason) and section 7 (NVENC SDK 13.1 headers, FFmpeg 9.x, need driver >= 610).

Oracle: hand-written FFmpeg outputs (`-version` first lines in the documented form `ffmpeg version <version> Copyright ...`, `-encoders`,
`-filters`, `-h encoder` listings) produced by the fake in tests/support/p006_kit.py; the executable SHA-256 by `hashlib`; the exact
reason strings of the spec; wall-clock bounds measured with `time.monotonic`.

Expected API of the implementation (module `pitstudio_studio.media.ffmpeg`):
    parse_version(first_line: str) -> tuple[str, int]
        from `ffmpeg version <token> ...` returns (version, major) where version is the leading `n?[0-9]+(\\.[0-9]+){0,3}` of the token
        (`n8.1-12-g1a2b3c4-2026` gives `n8.1`) and major its first integer; raises ValueError for anything else (no `ffmpeg version`
        prefix, a git-master token such as `N-123-gabc`, empty, `8.x`).
    FFmpegBuild(path: Path, version: str, major: int, sha256: str)       frozen dataclass; sha256 is the executable's SHA-256
    discover(*, env, runner, pinned_sha256, driver_version, required_options=None, clock=None) -> FFmpegBuild
        `env`: mapping with `PITSTUDIO_FFMPEG` and `PATH`; an empty `PITSTUDIO_FFMPEG` counts as unset; `PITSTUDIO_FFMPEG` wins over `PATH`;
        a path that does not name a file counts as not found. `runner(argv, **kwargs)` runs FFmpeg; every call passes `timeout=<seconds>`
        with the remaining part of the 10 s budget (a `subprocess.TimeoutExpired` becomes NotRun naming the timeout).
        `required_options` maps an encoder name to the option names it must list (whole tokens, `-<name>` in `-h encoder=<encoder>`);
        default: av1_nvenc and h264_nvenc {preset, rc, cq} (the encoder-specific options; generic options such as `b` and `g` are not listed by `-h encoder=`), libwebp {quality}.
        Order of checks: found (no process is launched when not found), `-version`, digest against `pinned_sha256`, driver gate, `-encoders`
        (av1_nvenc, h264_nvenc, libwebp as whole names), `-filters` (libvmaf), `-h encoder=<name>` per encoder with required options.
        Every failure raises `pitstudio_stagekit.NotRun(reason)`; the reason of the missing-FFmpeg and driver cases is the spec's exact text
        (`<version>` is the parsed version string, `<driver>` the driver string as given); the other reasons name the offending piece
        (the version line, `pinned`, the encoder, the filter, the option).
    encode.run(job, ...) applies `discover` first (after the held-lock check) and lets NotRun propagate (stage result `not_run`).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_studio.media.ffmpeg import FFmpegBuild, discover, parse_version

NOT_FOUND = "FFmpeg not found: set PITSTUDIO_FFMPEG or put ffmpeg on PATH"


def setup(tmp_path, **fake_kw):
    exe, sha = kit.install_exe(tmp_path / "bin")
    ff = kit.FakeFFmpeg(**fake_kw)
    return exe, sha, ff


def do_discover(exe, sha, ff, *, driver="582.78", env=None, **kw):
    return discover(
        env=env if env is not None else {"PITSTUDIO_FFMPEG": str(exe), "PATH": ""},
        runner=ff,
        pinned_sha256=sha,
        driver_version=driver,
        **kw,
    )


def not_run_reason(exe, sha, ff, **kw) -> str:
    from pitstudio_stagekit import NotRun

    with pytest.raises(NotRun) as ei:
        do_discover(exe, sha, ff, **kw)
    return str(ei.value)


# ---------------------------------------------------------------------------------------------------------------------
# version parse
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-09")
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("ffmpeg version n8.1 Copyright (c) 2000-2026 the FFmpeg developers", ("n8.1", 8)),
        ("ffmpeg version n8.1-12-g1a2b3c4-20261001 Copyright (c) 2000-2026 the FFmpeg developers", ("n8.1", 8)),
        ("ffmpeg version 8.1.1 Copyright (c) 2000-2026 the FFmpeg developers", ("8.1.1", 8)),
        ("ffmpeg version 9.0.2 Copyright (c) 2000-2026 the FFmpeg developers", ("9.0.2", 9)),
        ("ffmpeg version n10.2.3.4 Copyright", ("n10.2.3.4", 10)),
        ("ffmpeg version 7", ("7", 7)),
    ],
)
def test_parse_version_reads_the_token_after_ffmpeg_version(line, expected):
    assert parse_version(line) == expected


@pytest.mark.req("FR-006-11")
@pytest.mark.parametrize(
    "line",
    [
        "",
        "ffmpeg version",
        "ffmpeg version N-123456-gabcdef Copyright",  # a git master build has no release number
        "ffmpeg version 8.x Copyright",
        "ffmpeg version  Copyright (c) 2000-2026",
        "avconv version 8.1 Copyright",
        "some banner 8.1",
        "ffmpeg version \x00 ‮8.1",
    ],
)
def test_parse_version_rejects_everything_else(line):
    with pytest.raises(ValueError):  # noqa: PT011
        parse_version(line)


# ---------------------------------------------------------------------------------------------------------------------
# discovery (FR-006-09, FR-006-10)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-09")
def test_a_pinned_build_with_everything_listed_is_accepted(tmp_path):
    exe, sha, ff = setup(tmp_path)
    b = do_discover(exe, sha, ff)
    assert isinstance(b, FFmpegBuild) and b.path == exe and (b.version, b.major, b.sha256) == ("n8.1", 8, sha)
    assert {"version", "encoders", "filters", "options"} <= set(ff.kinds())
    assert ff.calls[0][0] == str(exe) and all(c[0] == str(exe) for c in ff.calls)


@pytest.mark.req("FR-006-09")
def test_every_process_call_carries_a_timeout_inside_the_10_second_budget(tmp_path):
    exe, sha, _ = setup(tmp_path)
    seen = []

    class Spy(kit.FakeFFmpeg):
        def __call__(self, argv, **kw):
            seen.append(kw.get("timeout"))
            return super().__call__(argv, **kw)

    do_discover(exe, sha, Spy())
    assert seen and all(isinstance(t, (int, float)) and 0 < t <= 10 for t in seen)


@pytest.mark.req("FR-006-09")
def test_a_hanging_ffmpeg_ends_as_not_run_naming_the_timeout(tmp_path):
    import subprocess

    from pitstudio_stagekit import NotRun

    exe, sha, _ = setup(tmp_path)

    def hang(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw.get("timeout", 10))

    with pytest.raises(NotRun) as ei:
        discover(
            env={"PITSTUDIO_FFMPEG": str(exe), "PATH": ""}, runner=hang, pinned_sha256=sha, driver_version="582.78"
        )
    assert "time" in str(ei.value).lower()


@pytest.mark.req("FR-006-09")
def test_pitstudio_ffmpeg_wins_over_path_and_path_is_the_fallback(tmp_path):
    exe1, sha1 = kit.install_exe(tmp_path / "one")
    exe2, sha2 = kit.install_exe(tmp_path / "two", content=b"another build")
    ff = kit.FakeFFmpeg()
    b = discover(
        env={"PITSTUDIO_FFMPEG": str(exe1), "PATH": str(exe2.parent)},
        runner=ff,
        pinned_sha256=sha1,
        driver_version="582.78",
    )
    assert b.path == exe1
    ff2 = kit.FakeFFmpeg()
    b2 = discover(env={"PATH": str(exe2.parent)}, runner=ff2, pinned_sha256=sha2, driver_version="582.78")
    assert Path(b2.path).resolve() == exe2.resolve() and b2.sha256 == sha2


@pytest.mark.req("FR-006-10")
@pytest.mark.parametrize(
    "env",
    [
        {"PATH": ""},
        {"PATH": "", "PITSTUDIO_FFMPEG": ""},
        {},
        {"PITSTUDIO_FFMPEG": "/no/such/dir/ffmpeg", "PATH": ""},
        {"PATH": "/no/such/dir:/also/missing"},
    ],
)
def test_missing_ffmpeg_is_not_run_with_the_exact_reason_within_2_seconds_and_launches_nothing(tmp_path, env):
    _, sha, ff = setup(tmp_path)
    t0 = time.monotonic()
    reason = not_run_reason(None, sha, ff, env=env)
    assert reason == NOT_FOUND
    assert time.monotonic() - t0 < 2.0
    assert ff.calls == []


@pytest.mark.req("FR-006-10")
def test_a_directory_named_ffmpeg_is_not_an_executable(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "ffmpeg").mkdir()
    _, sha, ff = setup(tmp_path / "x")
    assert (
        not_run_reason(None, sha, ff, env={"PITSTUDIO_FFMPEG": str(tmp_path / "bin" / "ffmpeg"), "PATH": ""})
        == NOT_FOUND
    )


@pytest.mark.req("FR-006-10")
def test_the_stage_ends_as_not_run_without_output_when_ffmpeg_is_missing(tmp_path, monkeypatch):
    import pitstudio_stagekit
    from pitstudio_studio.media.encode import run

    ctx = kit.prepare(tmp_path, monkeypatch)
    ctx.env = {"PATH": "", "PITSTUDIO_FFMPEG": ""}
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(ctx.job), encoding="utf-8")
    t0 = time.monotonic()
    rc = pitstudio_stagekit.main(
        lambda job: run(job, runner=ctx.ff, clock=ctx.clock, env=ctx.env, driver_version=ctx.driver),
        ["--job", str(job_path)],
    )
    doc = json.loads((ctx.out / "result.json").read_text(encoding="utf-8"))
    assert (
        rc == 0
        and doc["status"] == "not_run"
        and doc["reason"] == NOT_FOUND
        and doc["outputs"] == []
        and doc["error_class"] is None
    )
    assert sorted(p.name for p in ctx.out.iterdir()) == ["result.json"]  # no output
    assert time.monotonic() - t0 < 2.0 and ctx.ff.calls == []


# ---------------------------------------------------------------------------------------------------------------------
# the driver gate (FR-006-11)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-11")
def test_ffmpeg_9_with_driver_582_78_is_refused_with_the_exact_reason(tmp_path):
    exe, sha, ff = setup(tmp_path, version_line="9.0.2")
    reason = not_run_reason(exe, sha, ff, driver="582.78")
    assert reason == "FFmpeg 9.0.2 needs NVIDIA driver >= 610 (found 582.78); use the pinned FFmpeg 8.1 build"


@pytest.mark.req("FR-006-11")
@pytest.mark.parametrize("driver", ["610", "610.0", "615.12", "700.5.1", "1000.0"])
def test_ffmpeg_9_with_driver_610_or_newer_passes_the_gate(tmp_path, driver):
    exe, sha, ff = setup(tmp_path, version_line="9.0.2")
    b = do_discover(exe, sha, ff, driver=driver)
    assert b.major == 9 and b.version == "9.0.2"


@pytest.mark.req("FR-006-11")
@pytest.mark.parametrize("driver", ["609.99", "582.78", "570.133.07", "0", "99.9"])
def test_ffmpeg_9_below_610_is_refused(tmp_path, driver):
    exe, sha, ff = setup(tmp_path, version_line="9.1")
    assert (
        not_run_reason(exe, sha, ff, driver=driver)
        == f"FFmpeg 9.1 needs NVIDIA driver >= 610 (found {driver}); use the pinned FFmpeg 8.1 build"
    )


@pytest.mark.req("FR-006-11")
@pytest.mark.parametrize("driver", ["582.78", "0", "570.133.07"])
def test_ffmpeg_8_has_no_driver_gate(tmp_path, driver):
    exe, sha, ff = setup(tmp_path, version_line="n8.1")
    assert do_discover(exe, sha, ff, driver=driver).major == 8


@pytest.mark.req("FR-006-11")
@pytest.mark.parametrize("line", ["N-123456-gabcdef", "garbage", ""])
def test_an_unparseable_version_is_not_run_naming_the_version(tmp_path, line):
    exe, sha, ff = setup(tmp_path, version_line=line)
    reason = not_run_reason(exe, sha, ff)
    assert "version" in reason.lower() and 1 <= len(reason) <= 300


@pytest.mark.req("FR-006-11")
def test_an_executable_that_is_not_the_pinned_one_is_not_run(tmp_path):
    exe, _, ff = setup(tmp_path)
    other = "0" * 64
    reason = not_run_reason(exe, other, ff)
    assert "pinned" in reason.lower()
    assert ff.n_encodes() == 0


@pytest.mark.req("FR-006-11")
@pytest.mark.parametrize(
    ("missing", "kind"),
    [("av1_nvenc", "encoder"), ("h264_nvenc", "encoder"), ("libwebp", "encoder"), ("libvmaf", "filter")],
)
def test_a_missing_encoder_or_filter_is_not_run_naming_it(tmp_path, missing, kind):
    if kind == "encoder":
        kw = {"encoders": [e for e in kit.DEFAULT_ENCODERS if e != missing]}
    else:
        kw = {"filters": [f for f in kit.DEFAULT_FILTERS if f != missing]}
    exe, sha, ff = setup(tmp_path, **kw)
    assert missing in not_run_reason(exe, sha, ff)


@pytest.mark.req("FR-006-11")
def test_an_encoder_listed_only_by_a_longer_name_is_not_found(tmp_path):
    kw = {"encoders": ["av1_nvenc", "h264_nvenc", "libwebp_anim"]}  # `libwebp` itself is absent
    exe, sha, ff = setup(tmp_path, **kw)
    assert "libwebp" in not_run_reason(exe, sha, ff)


@pytest.mark.req("FR-006-11")
def test_a_missing_declared_option_is_not_run_naming_encoder_and_option(tmp_path):
    options = {k: [o for o in v if o != "tune"] for k, v in kit.DEFAULT_OPTIONS.items()}
    exe, sha, ff = setup(tmp_path, options=options)
    reason = not_run_reason(exe, sha, ff, required_options={"av1_nvenc": ["tune", "cq"]})
    assert "av1_nvenc" in reason and "tune" in reason


@pytest.mark.req("FR-006-11")
def test_an_option_matches_whole_tokens_only(tmp_path):
    options = dict(kit.DEFAULT_OPTIONS)
    options["av1_nvenc"] = ("preset", "rc", "cqx", "b", "g")  # `cqx` is not `cq`
    exe, sha, ff = setup(tmp_path, options=options)
    assert "cq" in not_run_reason(exe, sha, ff)


@pytest.mark.req("FR-006-09")
def test_declared_options_that_are_all_listed_pass(tmp_path):
    exe, sha, ff = setup(tmp_path)
    assert do_discover(exe, sha, ff, required_options={"av1_nvenc": ["tune", "cq"], "libwebp": ["quality"]}).major == 8


@pytest.mark.req("FR-006-11")
def test_the_stage_ends_as_not_run_when_ffmpeg_is_too_new_for_the_driver(tmp_path, monkeypatch):
    import pitstudio_stagekit
    from pitstudio_studio.media.encode import run

    ctx = kit.prepare(tmp_path, monkeypatch, version_line="9.0.2", driver="582.78")
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(ctx.job), encoding="utf-8")
    rc = pitstudio_stagekit.main(
        lambda job: run(job, runner=ctx.ff, clock=ctx.clock, env=ctx.env, driver_version=ctx.driver),
        ["--job", str(job_path)],
    )
    doc = json.loads((ctx.out / "result.json").read_text(encoding="utf-8"))
    assert rc == 0 and doc["status"] == "not_run"
    assert doc["reason"] == "FFmpeg 9.0.2 needs NVIDIA driver >= 610 (found 582.78); use the pinned FFmpeg 8.1 build"
    assert doc["outputs"] == [] and ctx.ff.n_encodes() == 0
