# ruff: noqa: E501, PT018
"""T-006-013: encoder records against spec 001's manifest schema, the encode report (DC-006-02), path scrubbing, local-only producers.

Requirements: FR-006-06, FR-006-14.

Spec: specs/006-media-telemetry/spec.md FR-006-06 (each video output in the stage result carries the encoder record of the
manifest contract: codec, profile, pix_fmt, width, height, fps, frames, duration_s, bitrate_kbps, vmaf {mean, p5, model},
source_frames_sha256, encoder {ffmpeg_version, build_sha256, nvenc_api, args}, encode_fps; arguments recorded verbatim except
that paths are reduced to file names; an encode report with, per variant, every tried setting with its VMAF mean, VMAF p5 and
bytes, the chosen setting, the pair total, the poster bytes and the relaxation or null) and FR-006-14 (frames from a
`local-only` producer: the encoder record, the encode report and the stage result contain encoder data only, never the
producer's render or capture time, frame rate or telemetry); contracts `contracts/encode-report.schema.json` and
`contracts/manifest.schema.json#/$defs/encoder`; plan.md "Design" (module `media.record`).

Oracle: (1) the spec's own contract example `specs/006-media-telemetry/contracts/examples/encode-report.valid.json` (its AV1 record
is the expected output of `build_encoder_record` for its own inputs: 9,100,000 bytes over 10 s is 7280.0 kbit/s; 300 frames in
300/210 s is 210.0 encode fps); (2) hand calculation for the fake encode below: 3 frames at 30 fps = 0.1 s, AV1 at cq 34 is 760,000
bytes = 760,000 x 8 / 0.1 / 1000 = 60,800.0 kbit/s, H.264 at cq 32 is 530,000 bytes = 42,400.0 kbit/s, pair 1,290,000 bytes,
the fake clock moves 3/200 s per AV1 encode and 3/400 s per H.264 encode so `encode_fps` is 200.0 and 400.0, the poster at
2000 x quality bytes fits 150,000 bytes at quality 75; (3) the JSON Schema 2020-12 validators of the two contracts
(`jsonschema`); (4) the argument lists the fake FFmpeg was actually given.

Expected API of the implementation (modules `pitstudio_studio.media.record` and `pitstudio_studio.media.encode`):
    record.scrub_args(args: Sequence[str]) -> list[str]
        every argument that is a path (it contains `/` or `\\`, or starts with a drive letter and a colon, and names a file) is reduced
        to its file name (the part after the last `/` or `\\`); every other argument is kept verbatim, in order.
    record.build_encoder_record(codec, *, width, height, fps, frames, file_bytes, vmaf_mean, vmaf_p5, source_frames_sha256,
                                ffmpeg_version, build_sha256, nvenc_api, args, encode_seconds) -> dict
        the encoder record of `manifest.schema.json#/$defs/encoder`: profile "main" for av1 and "high" for h264, pix_fmt "yuv420p",
        duration_s = frames / fps, bitrate_kbps = file_bytes x 8 / duration_s / 1000, vmaf {mean, p5, model "vmaf_v0.6.1"},
        encoder {ffmpeg_version, build_sha256, nvenc_api, args: scrub_args(args)}, encode_fps = frames / encode_seconds
        (null when encode_seconds is not a positive finite number).
    encode.run(job, *, runner=None, clock=None, env=None, driver_version=None) -> dict   the stage function of `st56_encode`
        (called by `pitstudio_stagekit.main`). `job` is a job spec (job.schema.json); `job["params"]` carries `frame_manifest` (the
        input name of the DC-006-01 manifest), `clip`, `publish`, optional `poster_frame` (default 0), optional `ranges`
        ({"av1": [lo, hi], "h264": [lo, hi]}, defaults [20, 50] and [15, 40]), optional `relaxation`, `pinned_ffmpeg_sha256` (the
        recipe's pinned `binaries` digest) and `nvenc_api` (from the pinned build entry, never probed). The frames are read from
        `<folder of the manifest file>/<manifest.directory>/<frame_pattern % index>`. `runner` runs FFmpeg (default
        `subprocess.run` looked up at call time; arguments are a list, never a shell), `clock` is `time.monotonic`, `env` the mapping
        that holds `PITSTUDIO_FFMPEG` and `PATH` (default `os.environ`), `driver_version` the NVML driver string (default read from NVML).
        The held-lock check reads `os.environ["PITSTUDIO_HELD_LOCKS"]` through `pitstudio_stagekit.require_lock("nvenc", 0)`.
        Writes `<clip>.av1.mp4`, `<clip>.h264.mp4`, `<clip>.webp` and `encode-report.json` into `job["output_dir"]` and returns
        {"outputs": [{"path": <file name>, "artefact": {"kind": "video" | "image" | "table", ..., "encoder": <record, video only>}}, ...],
         "throughput": {"value": <frames/s>, "unit": "frames/s"}, "message": <str>}. The report file is valid against
        `contracts/encode-report.schema.json`; each video output's `artefact.encoder` equals the report's variant `record`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_studio.media.record import build_encoder_record, scrub_args

EXAMPLE = json.loads((kit.SPEC / "contracts" / "examples" / "encode-report.valid.json").read_text(encoding="utf-8"))
ENCODER_KEYS = {
    "codec", "profile", "pix_fmt", "width", "height", "fps", "frames", "duration_s", "bitrate_kbps", "vmaf",
    "source_frames_sha256", "encoder", "encode_fps",
}  # fmt: skip


# ---------------------------------------------------------------------------------------------------------------------
# path scrubbing
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-06")
def test_paths_are_reduced_to_file_names_and_everything_else_is_verbatim():
    args = [
        "-hide_banner", "-framerate", "30", "-start_number", "0",
        "-i", "/home/user/runs/20261007/tmp/in/frames/frame_%05d.png",
        "-c:v", "av1_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "34", "-b:v", "0", "-g", "60",
        "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p",
        "-movflags", "+faststart",
        "C:\\Users\\someone\\scratch\\clip.av1.mp4",
    ]  # fmt: skip
    got = scrub_args(args)
    expected = list(args)
    expected[expected.index("/home/user/runs/20261007/tmp/in/frames/frame_%05d.png")] = "frame_%05d.png"
    expected[-1] = "clip.av1.mp4"
    assert got == expected


@pytest.mark.req("FR-006-06")
@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("/tmp/a/b/c.mp4", "c.mp4"),
        ("C:/data/runs/clip.h264.mp4", "clip.h264.mp4"),
        ("C:\\data\\runs\\clip.h264.mp4", "clip.h264.mp4"),
        ("\\\\server\\share\\x\\clip.webp", "clip.webp"),
        ("work/scratch/clip.av1.mp4", "clip.av1.mp4"),
        ("clip.av1.mp4", "clip.av1.mp4"),
    ],
)
def test_every_path_form_is_reduced(path, name):
    assert scrub_args(["-i", path]) == ["-i", name]


@pytest.mark.req("FR-006-06")
def test_scrub_args_does_not_mutate_its_input_and_keeps_empty_lists():
    args = ["-i", "/a/b.png"]
    before = list(args)
    scrub_args(args)
    assert args == before and scrub_args([]) == []


# ---------------------------------------------------------------------------------------------------------------------
# encoder record = the contract example
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-006-06")
@pytest.mark.parametrize("codec", ["av1", "h264"])
def test_encoder_record_reproduces_the_contract_example_from_its_inputs(codec):
    v = EXAMPLE["clips"][0]["variants"][codec]
    rec = v["record"]
    absolute = [
        "/work/frames/" + a if a.startswith("frame_") else ("C:\\out\\" + a if a.endswith(".mp4") else a)
        for a in rec["encoder"]["args"]
    ]
    got = build_encoder_record(
        codec,
        width=rec["width"],
        height=rec["height"],
        fps=rec["fps"],
        frames=rec["frames"],
        file_bytes=v["bytes"],
        vmaf_mean=rec["vmaf"]["mean"],
        vmaf_p5=rec["vmaf"]["p5"],
        source_frames_sha256=rec["source_frames_sha256"],
        ffmpeg_version=rec["encoder"]["ffmpeg_version"],
        build_sha256=rec["encoder"]["build_sha256"],
        nvenc_api=rec["encoder"]["nvenc_api"],
        args=absolute,
        encode_seconds=rec["frames"] / rec["encode_fps"],
    )
    assert set(got) == ENCODER_KEYS
    for k in ("codec", "profile", "pix_fmt", "width", "height", "fps", "frames", "source_frames_sha256"):
        assert got[k] == rec[k], k
    assert got["duration_s"] == pytest.approx(rec["duration_s"]) and got["bitrate_kbps"] == pytest.approx(
        rec["bitrate_kbps"]
    )
    assert got["encode_fps"] == pytest.approx(rec["encode_fps"])
    assert got["vmaf"] == {"mean": rec["vmaf"]["mean"], "p5": rec["vmaf"]["p5"], "model": "vmaf_v0.6.1"}
    assert got["encoder"] == rec["encoder"]  # arguments recorded verbatim, paths reduced to file names
    errors = list(kit.schema_validator("manifest", "encoder").iter_errors(got))
    assert not errors, [e.message for e in errors]


@pytest.mark.req("FR-006-06")
@pytest.mark.parametrize("seconds", [0, 0.0, -1.0, float("nan"), float("inf")])
def test_encode_fps_is_null_when_the_time_is_not_a_positive_finite_number(seconds):
    rec = build_encoder_record(
        "av1", width=1920, height=1080, fps=30, frames=300, file_bytes=9_100_000, vmaf_mean=93.1, vmaf_p5=86.9,
        source_frames_sha256="53acb42d840511b876b00493ba67d140d3a9c021e41ef17a7e3889180213883a",
        ffmpeg_version="n8.1", build_sha256="52196cdacdd6bccee18dc3fe8f15606a7503ff8818bfeacb9abdfecf4b6654e2",
        nvenc_api="13.0", args=["-i", "a.png"], encode_seconds=seconds,
    )  # fmt: skip
    assert rec["encode_fps"] is None
    assert not list(kit.schema_validator("manifest", "encoder").iter_errors(rec))


# ---------------------------------------------------------------------------------------------------------------------
# the whole stage on the fake FFmpeg (public producer)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def std(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    ctx = kit.prepare(tmp_path_factory.mktemp("std"), mp)
    result = ctx.run()
    report = json.loads((ctx.out / "encode-report.json").read_text(encoding="utf-8"))
    yield ctx, result, report
    mp.undo()


def video(result, suffix):
    return next(o for o in result["outputs"] if o["path"].endswith(suffix))


@pytest.mark.req("FR-006-06")
def test_the_encode_report_is_valid_and_matches_the_hand_calculation(std):
    ctx, _, report = std
    errors = list(kit.schema_validator("encode-report").iter_errors(report))
    assert not errors, [e.message for e in errors]
    assert report["run_id"] == kit.RUN_ID and report["stage"]["id"] == "st56_encode"
    clip = report["clips"][0]
    assert len(report["clips"]) == 1 and clip["clip"] == "fixture-clip"
    assert (
        clip["frames"] == 3
        and clip["fps"] == 30
        and clip["source_frames_sha256"] == ctx.seq.manifest["source_frames_sha256"]
    )
    av1, h264 = clip["variants"]["av1"], clip["variants"]["h264"]
    assert (av1["chosen_cq"], h264["chosen_cq"]) == (
        34,
        32,
    )  # largest cq with mean >= 93: 100 - 0.5 (cq - 20), 100 - 0.4 (cq - 15)
    assert (av1["bytes"], h264["bytes"]) == (760_000, 530_000) and clip["pair_bytes"] == 1_290_000
    assert av1["cq_range"] == {"min": 20, "max": 50} and h264["cq_range"] == {"min": 15, "max": 40}
    assert clip["relaxation"] is None
    for name, v in (("av1", av1), ("h264", h264)):
        assert 1 <= len(v["trials"]) <= 8
        for t in v["trials"]:  # every tried setting with its VMAF mean, p5 and bytes (hand curves)
            assert t["vmaf_mean"] == pytest.approx(kit.std_scores(3)(name, t["cq"])[0]) and t["bytes"] == kit.std_sizes(
                name, t["cq"]
            )
        assert v["sha256"] == hashlib.sha256((ctx.out / v["file"]).read_bytes()).hexdigest()
        assert v["bytes"] == (ctx.out / v["file"]).stat().st_size


@pytest.mark.req("FR-006-06")
def test_the_poster_is_the_largest_quality_that_fits_150000_bytes(std):
    ctx, _, report = std
    poster = report["clips"][0]["poster"]
    assert poster["file"] == "fixture-clip.webp" and poster["quality"] == 75 and poster["bytes"] == 150_000
    assert (poster["width"], poster["height"], poster["frame"]) == (1280, 720, 0)
    assert poster["sha256"] == hashlib.sha256((ctx.out / "fixture-clip.webp").read_bytes()).hexdigest()


@pytest.mark.req("FR-006-06")
def test_each_video_output_carries_the_hand_calculated_encoder_record(std):
    ctx, result, report = std
    for codec, suffix, cq, size, w, h, enc_fps in (
        ("av1", ".av1.mp4", 34, 760_000, 1920, 1080, 200.0),
        ("h264", ".h264.mp4", 32, 530_000, 1280, 720, 400.0),
    ):
        out = video(result, suffix)
        rec = out["artefact"]["encoder"]
        assert out["artefact"]["kind"] == "video"
        assert set(rec) == ENCODER_KEYS
        assert (rec["codec"], rec["pix_fmt"], rec["width"], rec["height"], rec["fps"], rec["frames"]) == (
            codec,
            "yuv420p",
            w,
            h,
            30,
            3,
        )
        assert rec["profile"] == ("main" if codec == "av1" else "high")
        assert rec["duration_s"] == pytest.approx(0.1) and rec["bitrate_kbps"] == pytest.approx(size * 8 / 0.1 / 1000)
        assert rec["encode_fps"] == pytest.approx(enc_fps, rel=1e-6)  # frames of the final settings / their encode time
        assert rec["vmaf"]["model"] == "vmaf_v0.6.1" and rec["vmaf"]["mean"] >= 93.0 and rec["vmaf"]["p5"] >= 85.0
        assert rec["source_frames_sha256"] == ctx.seq.manifest["source_frames_sha256"]
        e = rec["encoder"]
        assert (e["ffmpeg_version"], e["build_sha256"], e["nvenc_api"]) == ("n8.1", ctx.sha, "13.0")
        assert rec == report["clips"][0]["variants"][codec]["record"]  # identical to the one in the report
        assert not list(kit.schema_validator("manifest", "encoder").iter_errors(rec))
        # arguments verbatim (the last encode at the chosen cq) with paths reduced to file names
        final = [
            c
            for c in ctx.ff.calls
            if ctx.ff._classify(c) == "encode"
            and c[c.index("-cq") + 1] == str(cq)
            and ("av1_nvenc" in c) == (codec == "av1")
        ][-1]
        expected = [a.replace("\\", "/").rsplit("/", 1)[-1] if ("/" in a or "\\" in a) else a for a in final[1:]]
        assert e["args"] == expected
        assert all("/" not in a and "\\" not in a for a in e["args"])


@pytest.mark.req("FR-006-06")
def test_output_files_exist_and_the_report_is_listed(std):
    ctx, result, _ = std
    paths = {o["path"] for o in result["outputs"]}
    assert {"fixture-clip.av1.mp4", "fixture-clip.h264.mp4", "fixture-clip.webp", "encode-report.json"} <= paths
    for p in paths:
        assert (ctx.out / p).is_file()


@pytest.mark.req("FR-006-06")
def test_poster_frame_parameter_reaches_the_report(tmp_path, monkeypatch):
    ctx = kit.prepare(tmp_path, monkeypatch, params={"poster_frame": 2})
    ctx.run()
    report = json.loads((ctx.out / "encode-report.json").read_text(encoding="utf-8"))
    assert report["clips"][0]["poster"]["frame"] == 2


# ---------------------------------------------------------------------------------------------------------------------
# FR-006-14: local-only producers
# ---------------------------------------------------------------------------------------------------------------------
PRODUCER_EXTRAS = {
    "render_time_s": 987.654,
    "capture_time_s": 123.456,
    "render_fps": 7.25,
    "telemetry": {"gpu_util_pct": 91.5, "vram_gib": 17.25},
}


@pytest.mark.req("FR-006-14")
def test_local_only_producer_data_never_reaches_record_report_or_result(tmp_path, monkeypatch):
    ctx = kit.prepare(tmp_path, monkeypatch, performance="local-only", extra=PRODUCER_EXTRAS)
    result = ctx.run()
    report_text = (ctx.out / "encode-report.json").read_text(encoding="utf-8")
    blob = json.dumps(result) + report_text
    for needle in (
        "987.654",
        "123.456",
        "7.25",
        "91.5",
        "17.25",
        "render_time_s",
        "capture_time_s",
        "render_fps",
        "telemetry",
    ):
        assert needle not in blob, needle
    # encoder data only: the record keeps exactly the manifest encoder keys, the result only the stage-result keys
    for o in result["outputs"]:
        if "artefact" in o and "encoder" in o["artefact"]:
            assert set(o["artefact"]["encoder"]) == ENCODER_KEYS
    assert set(result) <= {"outputs", "throughput", "message", "observables", "checkpoint"}
    report = json.loads(report_text)
    assert set(report) <= {
        "$schema",
        "kind",
        "schema_version",
        "run_id",
        "stage",
        "vmaf_model",
        "targets",
        "clips",
        "fixture",
    }
    # the encoder's own throughput is still reported (FFmpeg and NVENC are not covered by the renderer's licence)
    assert result["throughput"]["unit"] == "frames/s" and result["throughput"]["value"] > 0
    assert video(result, ".av1.mp4")["artefact"]["encoder"]["encode_fps"] == pytest.approx(200.0, rel=1e-6)


@pytest.mark.req("FR-006-14")
def test_a_public_producer_run_has_the_same_fields_as_a_local_only_run(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    try:
        a = kit.prepare(tmp_path_factory.mktemp("pub"), mp, performance="public")
        ra = a.run()
        b = kit.prepare(tmp_path_factory.mktemp("loc"), mp, performance="local-only", extra=PRODUCER_EXTRAS)
        rb = b.run()
    finally:
        mp.undo()

    assert set(ra) == set(rb)
    assert [sorted(o) for o in ra["outputs"]] == [sorted(o) for o in rb["outputs"]]
    assert [sorted(o.get("artefact", {})) for o in ra["outputs"]] == [
        sorted(o.get("artefact", {})) for o in rb["outputs"]
    ]
