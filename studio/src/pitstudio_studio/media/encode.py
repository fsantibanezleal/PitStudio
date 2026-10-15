"""`st56_encode`: the clip pair (AV1 1080p and H.264 720p) with its poster, encode report and encoder records.

Flow (plan.md "Design"): the `pynvvideocodec` publish refusal, the held-lock check, FFmpeg discovery and gates,
the frame checks, a VMAF-targeted constant-quality search per variant, the pair budget, the poster, the output
verification, the encoder records and the report. FFmpeg is always called with an argument list through `runner`
(default `subprocess.run`, looked up at call time), never through a shell. Everything is written under
`job["output_dir"]`; trial files live in `job["scratch_dir"]`.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from pitstudio_stagekit import NotRun, require_lock

from ..telemetry.nvtx import StepRanges
from ..telemetry.throughput import measure as measure_throughput
from . import ffmpeg as ff
from .errors import EncodeError, FramesInvalid, NotPublishable
from .frames import ValidatedSequence, validate_clip_name, validate_sequence
from .record import TARGETS, VMAF_MODEL, build_encoder_record
from .search import Measurement, choose_poster_quality, plan_clip
from .verify import PROCESS_TIMEOUT_S, verify_output
from .verify import Verification as Verification  # re-exported: the stage module carries the verification API
from .verify import check_box_order as check_box_order
from .verify import top_level_boxes as top_level_boxes
from .vmaf import aggregate_vmaf, parse_vmaf_log

SCHEMA_VERSION = "1.0"
VARIANTS = {  # codec -> (encoder, width, height, default constant-quality range)
    "av1": ("av1_nvenc", 1920, 1080, (20, 50)),
    "h264": ("h264_nvenc", 1280, 720, (15, 40)),
}
POSTER_SIZE = (1280, 720)


class EncodeFailed(EncodeError):
    error_class = "encode-failed"


# ---------------------------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------------------------
def _driver_version() -> str:
    try:
        import pynvml

        pynvml.nvmlInit()
        try:
            v = pynvml.nvmlSystemGetDriverVersion()
        finally:
            pynvml.nvmlShutdown()
        return v.decode() if isinstance(v, bytes) else str(v)
    except Exception:
        return "unknown"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _flag(value: object, where: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise FramesInvalid(f"{where} fixture flag must be true or false")
    return value


def _ranges(params: Mapping[str, object]) -> dict[str, tuple[int, int]]:
    given = params.get("ranges") or {}
    out = {}
    for codec, (_, _, _, default) in VARIANTS.items():
        pair = given.get(codec, default) if isinstance(given, dict) else default
        out[codec] = (pair[0], pair[1])
    return out


class _Stage:
    """The state shared by the encodes of one stage run."""

    def __init__(
        self, job: Mapping, seq: ValidatedSequence, manifest: Mapping, build: ff.FFmpegBuild, runner, clock
    ) -> None:
        self.job, self.seq, self.manifest, self.build, self.runner, self.clock = (
            job,
            seq,
            manifest,
            build,
            runner,
            clock,
        )
        self.clip = manifest["clip"]
        self.scratch = Path(job["scratch_dir"])
        self.out = Path(job["output_dir"])
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.pattern_path = seq.paths[0].parent / manifest["frame_pattern"]
        self.first_index = manifest.get("first_index", 0)
        self.made: list[Path] = []
        self.ranges = StepRanges()

    def run(self, argv: list[str], what: str, *, cwd: Path | None = None) -> subprocess.CompletedProcess:
        done = self.runner(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROCESS_TIMEOUT_S,
            check=False,
            **({"cwd": str(cwd)} if cwd else {}),
        )
        if done.returncode != 0:
            raise EncodeFailed(f"{what} exited with code {done.returncode}: {(done.stderr or '').strip()[-160:]}")
        return done

    def source_input(self) -> list[str]:
        return ["-framerate", str(self.seq.fps), "-start_number", str(self.first_index), "-i", str(self.pattern_path)]

    def encode_args(self, codec: str, cq: int, target: Path) -> list[str]:
        encoder, width, height, _ = VARIANTS[codec]
        return [
            str(self.build.path), "-hide_banner", "-y", *self.source_input(), "-frames:v", str(self.seq.frames),
            "-vf", f"scale={width}:{height}:flags=lanczos,format=yuv420p",
            "-c:v", encoder, "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", str(cq), "-b:v", "0",
            "-g", str(2 * self.seq.fps), "-movflags", "+faststart", str(target),
        ]  # fmt: skip

    def vmaf_args(self, codec: str, encoded: Path, log_name: str) -> list[str]:
        _, width, height, _ = VARIANTS[codec]
        graph = (
            f"[0:v]scale={width}:{height}:flags=lanczos,format=yuv420p[ref];[1:v]format=yuv420p[dist];"
            f"[dist][ref]libvmaf=model=version={VMAF_MODEL}:log_fmt=json:log_path={log_name}"
        )
        return [
            str(self.build.path), "-hide_banner", "-y", *self.source_input(), "-i", str(encoded),
            "-lavfi", graph, "-f", "null", "-",
        ]  # fmt: skip

    def variant(self, codec: str) -> tuple[Callable[[int], Measurement], dict[int, tuple[float, list[str]]]]:
        """A `measure(cq)` for the search and the per-cq (encode seconds, argument list) of its latest encode."""
        latest: dict[int, tuple[float, list[str]]] = {}
        log_name = f"vmaf.{codec}.json"

        def measure(cq: int) -> Measurement:
            target = self.scratch / f"{self.clip}.{codec}.cq{cq}.mp4"
            self.made.append(target)
            argv = self.encode_args(codec, cq, target)
            with self.ranges.step(f"{codec}/encode"):
                t0 = self.clock()
                self.run(argv, f"{codec} encode at cq {cq}")
                seconds = self.clock() - t0
            latest[cq] = (seconds, argv)
            log = self.scratch / log_name
            self.made.append(log)
            log.unlink(missing_ok=True)
            with self.ranges.step(f"{codec}/vmaf"):
                self.run(self.vmaf_args(codec, target, log_name), f"{codec} VMAF at cq {cq}", cwd=self.scratch)
            scores = parse_vmaf_log(log.read_text(encoding="utf-8"), expected_frames=self.seq.frames)
            mean, p5 = aggregate_vmaf(scores)
            return Measurement(mean, p5, target.stat().st_size)

        return measure, latest

    def poster(self, index: int) -> tuple[Path, int]:
        source = self.seq.paths[index]

        def size_at(quality: int) -> int:
            target = self.scratch / f"{self.clip}.q{quality}.webp"
            self.made.append(target)
            argv = [
                str(self.build.path), "-hide_banner", "-y", "-i", str(source), "-frames:v", "1",
                "-vf", f"scale={POSTER_SIZE[0]}:{POSTER_SIZE[1]}:flags=lanczos",
                "-c:v", "libwebp", "-quality", str(quality), str(target),
            ]  # fmt: skip
            self.run(argv, f"poster encode at quality {quality}")
            return target.stat().st_size

        with self.ranges.step("poster"):
            quality = choose_poster_quality(size_at)
        return self.scratch / f"{self.clip}.q{quality}.webp", quality


# ---------------------------------------------------------------------------------------------------------------------
# the stage
# ---------------------------------------------------------------------------------------------------------------------
def run(
    job: Mapping,
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
    clock: Callable[[], float] | None = None,
    env: Mapping[str, str] | None = None,
    driver_version: str | None = None,
) -> dict:
    params = job["params"]
    mode = params.get("encoder_mode", "ffmpeg")
    if mode not in ("ffmpeg", "pynvvideocodec"):
        raise ValueError(f"encoder_mode must be ffmpeg or pynvvideocodec, got {mode!r}")
    if mode == "pynvvideocodec" and params.get("publish") is True:
        raise NotPublishable("PyNvVideoCodec outputs are local previews and cannot be published")
    require_lock("nvenc", 0)
    if mode == "pynvvideocodec":
        raise NotRun(
            "the in-process PyNvVideoCodec preview encoder is not wired into this stage; use encoder_mode ffmpeg"
        )
    run_process = runner if runner is not None else subprocess.run
    clock = clock or time.monotonic
    environment = os.environ if env is None else env
    if "pinned_ffmpeg_sha256" not in params:
        raise ValueError("params.pinned_ffmpeg_sha256 (the recipe's pinned binaries digest) is required")
    build = ff.discover(
        env=environment,
        runner=run_process,
        pinned_sha256=params["pinned_ffmpeg_sha256"],
        driver_version=driver_version if driver_version is not None else _driver_version(),
        clock=None,
    )
    entry = next((i for i in job["inputs"] if i["name"] == params["frame_manifest"]), None)
    if entry is None:
        raise FramesInvalid(f"the job has no input named {params['frame_manifest']!r}")
    manifest_path = Path(entry["path"])
    if _sha256(manifest_path) != entry["sha256"]:
        raise FramesInvalid("the frame manifest differs from its recorded SHA-256")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixture = False
    validate_clip_name(params.get("clip", manifest.get("clip")))
    seq = validate_sequence(manifest, manifest_path.parent)
    if params.get("clip", manifest["clip"]) != manifest["clip"]:
        raise FramesInvalid("params.clip differs from the clip of the frame manifest")
    poster_index = params.get("poster_frame", 0)
    if isinstance(poster_index, bool) or not isinstance(poster_index, int) or not 0 <= poster_index < seq.frames:
        raise FramesInvalid(f"poster_frame must be an index in 0..{seq.frames - 1}")
    stage = _Stage(job, seq, manifest, build, run_process, clock)
    try:
        return _encode_clip(stage, params, poster_index, fixture)
    finally:
        for p in stage.made:
            p.unlink(missing_ok=True)


def _encode_clip(stage: _Stage, params: Mapping, poster_index: int, fixture: bool) -> dict:
    job, seq, build, out = stage.job, stage.seq, stage.build, stage.out
    measure_av1, latest_av1 = stage.variant("av1")
    measure_h264, latest_h264 = stage.variant("h264")
    ranges = _ranges(params)
    plan = plan_clip(
        measure_av1,
        measure_h264,
        av1_range=ranges["av1"],
        h264_range=ranges["h264"],
        relaxation=params.get("relaxation"),
    )
    variants: dict[str, dict] = {}
    outputs: list[dict] = []
    final_seconds = 0.0
    for codec, result, latest in (("av1", plan.av1, latest_av1), ("h264", plan.h264, latest_h264)):
        seconds, argv = latest[result.chosen_cq]
        final_seconds += seconds
        trial_file = stage.scratch / f"{stage.clip}.{codec}.cq{result.chosen_cq}.mp4"
        with stage.ranges.step(f"{codec}/verify"):
            verify_output(trial_file, ffmpeg=build.path, runner=stage.runner, source_frames=seq.frames, fps=seq.fps)
        final = out / f"{stage.clip}.{codec}.mp4"
        os.replace(trial_file, final)
        _, width, height, _ = VARIANTS[codec]
        record = build_encoder_record(
            codec, width=width, height=height, fps=seq.fps, frames=seq.frames, file_bytes=final.stat().st_size,
            vmaf_mean=result.final.vmaf_mean, vmaf_p5=result.final.vmaf_p5,
            source_frames_sha256=seq.source_frames_sha256, ffmpeg_version=build.version, build_sha256=build.sha256,
            nvenc_api=params.get("nvenc_api"), args=argv[1:], encode_seconds=seconds,
        )  # fmt: skip
        lo, hi = ranges[codec]
        variants[codec] = {
            "file": final.name,
            "bytes": final.stat().st_size,
            "sha256": _sha256(final),
            "cq_range": {"min": lo, "max": hi},
            "trials": [
                {"cq": t.cq, "vmaf_mean": t.vmaf_mean, "vmaf_p5": t.vmaf_p5, "bytes": t.bytes} for t in result.trials
            ],
            "chosen_cq": result.chosen_cq,
            "record": record,
        }
        entry: dict = {"path": final.name}
        if not fixture:
            entry["artefact"] = {
                "kind": "video",
                "media_type": "video/mp4",
                "budget_class": "videos",
                "encoder": record,
            }
        outputs.append(entry)
    poster_file, quality = stage.poster(poster_index)
    poster_final = out / f"{stage.clip}.webp"
    os.replace(poster_file, poster_final)
    poster = {
        "file": poster_final.name,
        "sha256": _sha256(poster_final),
        "bytes": poster_final.stat().st_size,
        "quality": quality,
        "width": POSTER_SIZE[0],
        "height": POSTER_SIZE[1],
        "frame": poster_index,
    }
    poster_entry: dict = {"path": poster_final.name}
    if not fixture:
        poster_entry["artefact"] = {"kind": "image", "media_type": "image/webp", "budget_class": "videos"}
    outputs.append(poster_entry)
    clip = {
        "clip": stage.clip,
        "source_frames_sha256": seq.source_frames_sha256,
        "frames": seq.frames,
        "fps": seq.fps,
        "variants": variants,
        "pair_bytes": plan.pair_bytes,
        "poster": poster,
        "relaxation": plan.relaxation,
    }
    report = {
        "kind": "encode-report",
        "schema_version": SCHEMA_VERSION,
        "run_id": job["run_id"],
        "stage": dict(job["stage"]),
        "vmaf_model": VMAF_MODEL,
        "targets": dict(TARGETS),
        "clips": [clip],
    }
    if fixture:
        report["fixture"] = True
        clip["fixture"] = True
    (out / "encode-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    outputs.append({"path": "encode-report.json"})
    throughput = measure_throughput("encode", 2 * seq.frames, final_seconds)
    result: dict = {"outputs": outputs}
    messages = []
    if throughput.throughput is not None:
        result["throughput"] = throughput.throughput
    else:
        messages.append(str(throughput.reason))
    if fixture:
        messages.insert(0, "fixture frames: encoded for tests, nothing is offered for publication")
    if messages:
        result["message"] = "; ".join(messages)[:300]
    return result
