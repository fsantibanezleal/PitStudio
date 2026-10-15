# ruff: noqa: E501
"""Shared test kit of spec 006 (media and telemetry): fakes for FFmpeg, NVTX, the clock, held locks and frame fixtures.

This is test support, not a test. It is locked together with the first test file that uses it (T-006-010 and the files
after it import it with `sys.path.insert(0, <repo>/tests/support)`). Spec: specs/006-media-telemetry/plan.md, "Design"
(fakes) and "Test strategy". Nothing here imports the code under test; the fakes follow the documented behaviour of the
tools they replace:

* PNG files are written byte by byte (signature, IHDR, IDAT through `zlib`, IEND, CRC-32 by `zlib.crc32`), following the
  PNG specification (ISO/IEC 15948), never through an image library.
* `FakeFFmpeg` is the `runner` seam of the stage: a callable `runner(argv, **kwargs) -> subprocess.CompletedProcess` with
  decoded `str` output. It answers `-version`, `-encoders`, `-filters`, `-h encoder=<name>` and the encode, poster, VMAF and
  decode invocations the plan describes (plan.md "Key decisions"): NVENC constant quality is `-cq <int>` with
  `-rc vbr -b:v 0`; the poster is the `libwebp` encoder with `-quality <q>` (or `-q:v`); the VMAF run uses a filter graph
  with `libvmaf=...:log_fmt=json:log_path=<file>` and the encoded file as an `-i` input, and the per-frame scores are read
  from libvmaf's JSON log (`{"frames": [{"frameNum": i, "metrics": {"vmaf": s}}, ...]}`, the format libvmaf writes); the
  output check is a null-muxer decode (`-f null`) whose machine-readable progress comes from `-progress pipe:1`
  (`frame=<n>` and `out_time_us=<t>` lines, FFmpeg documentation of `-progress`). MP4 files written by the fake are real
  ISO base media box sequences (ISO/IEC 14496-12): `ftyp`, then `moov` before `mdat` when `-movflags +faststart` is on the
  command line and `mdat` before `moov` otherwise.
* `FakeClock` is the `clock` seam (a `time.monotonic` stand-in); the fake FFmpeg advances it by frames / rate seconds
  for every encode so that `encode_fps` has a hand-calculable value.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import types
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (
    ROOT / "studio" / "src",
    ROOT / "src" / "pitstudio" / "runner" / "stagekit",
):  # studio lane + stage helper (spec 002)
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

SPEC = ROOT / "specs" / "006-media-telemetry"

# Constants of spec 006 (section 3.1 and thresholds.yaml `media.*`).
VMAF_MEAN_MIN = 93.0
VMAF_P5_MIN = 85.0
VMAF_RELAXED_MEAN_FLOOR = 80.0
PAIR_BYTES_MAX = 25_000_000
POSTER_BYTES_MAX = 150_000
VMAF_MODEL = "vmaf_v0.6.1"
RUN_ID = "20261007T133000Z-c2-replay"
NVENC_LOCK = "gpu0.nvenc"


# --------------------------------------------------------------------------------------------------------------------
# PNG frames and frame manifests
# --------------------------------------------------------------------------------------------------------------------
def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png_bytes(
    width: int, height: int, *, depth: int = 8, rgb: tuple[int, int, int] = (0, 0, 0), stripe: int = 0
) -> bytes:
    """A valid truecolour PNG (colour type 2) whose pixels are all `rgb`, except the first `stripe` pixels of row 0 (set to white).

    `rgb` components are 0..255; for depth 16 each is replicated into both bytes (v * 257).
    """
    px = bytes(rgb) if depth == 8 else b"".join(struct.pack(">H", c * 257) for c in rgb)
    row = b"\x00" + px * width
    raw = row * height
    if stripe:
        white = b"\xff" * (len(px) // 3) * 3 if depth == 8 else b"\xff\xff" * 3
        raw = b"\x00" + white * stripe + px * (width - stripe) + raw[len(row) :]
    ihdr = struct.pack(">IIBBBBB", width, height, depth, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(raw, 1)) + _chunk(b"IEND", b"")


def frames_digest(per_frame_hex: Sequence[str]) -> str:
    """SHA-256 of the ordered list of per-frame SHA-256 digests: the raw 32-byte digests concatenated in frame order.

    The spec does not state the serialisation (see the report); this is the reading the tests fix.
    """
    return hashlib.sha256(b"".join(bytes.fromhex(h) for h in per_frame_hex)).hexdigest()


def write_sequence(
    folder: Path,
    n: int,
    *,
    width: int = 1920,
    height: int = 1080,
    depth: int = 8,
    pattern: str = "frame_%05d.png",
    first_index: int = 0,
) -> list[Path]:
    """Write `n` distinct frames (frame k has colour (k*7 % 256, 40 + k % 200, 90)) and return their paths in order."""
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for k in range(n):
        p = folder / (pattern % (first_index + k))
        p.write_bytes(png_bytes(width, height, depth=depth, rgb=((k * 7) % 256, 40 + k % 200, 90)))
        out.append(p)
    return out


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frame_manifest(
    frames: Sequence[Path],
    *,
    clip: str = "fixture-clip",
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    bit_depth: int = 8,
    pattern: str = "frame_%05d.png",
    first_index: int = 0,
    directory: str | None = "frames",
    performance: str = "public",
    tool: str = "warp",
    stage: str = "st50_physics",
    extra: Mapping[str, object] | None = None,
) -> dict:
    """A DC-006-01 frame manifest for `frames` (digests computed here, by `hashlib`)."""
    per = [file_sha256(p) for p in frames]
    doc: dict = {
        "kind": "frame-manifest",
        "schema_version": "1.0",
        "clip": clip,
        "producer": {"tool": tool, "stage": {"id": stage}},
        "performance": performance,
        "fps": fps,
        "frames": len(frames),
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "colour_space": "srgb",
        "format": "png",
        "frame_pattern": pattern,
        "first_index": first_index,
        "source_frames_sha256": frames_digest(per),
        "frame_sha256": per,
    }
    if directory is not None:
        doc["directory"] = directory
    doc.update(extra or {})
    return doc


class Sequence3:
    """A frame sequence on disk under `<root>/in/` with its manifest `<root>/in/manifest.json` (the stage's input folder)."""

    def __init__(
        self,
        root: Path,
        n: int = 3,
        *,
        fps: int = 30,
        clip: str = "fixture-clip",
        performance: str = "public",
        extra: Mapping[str, object] | None = None,
        width: int = 1920,
        height: int = 1080,
        depth: int = 8,
        pattern: str = "frame_%05d.png",
        first_index: int = 0,
    ) -> None:
        self.root = root
        self.input_dir = root / "in"
        self.frames = write_sequence(
            self.input_dir / "frames",
            n,
            width=width,
            height=height,
            depth=depth,
            pattern=pattern,
            first_index=first_index,
        )
        self.manifest = frame_manifest(
            self.frames,
            clip=clip,
            fps=fps,
            width=width,
            height=height,
            bit_depth=depth,
            pattern=pattern,
            first_index=first_index,
            performance=performance,
            extra=extra,
        )
        self.manifest_path = self.input_dir / "manifest.json"
        self.write_manifest()

    def write_manifest(self) -> None:
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")


def make_job(
    root: Path,
    seq: Sequence3,
    *,
    params: Mapping[str, object] | None = None,
    profiling: bool = False,
    stage: str = "st56_encode",
) -> dict:
    """A job spec (job.schema.json `job_spec`) for the stage with the frame manifest as its only input."""
    out = root / "runs" / RUN_ID / "tmp" / stage / "0"
    out.mkdir(parents=True, exist_ok=True)
    scratch = root / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    base_params = {
        "frame_manifest": "st50_physics/frames/manifest.json",
        "clip": seq.manifest["clip"],
        "publish": False,
    }
    base_params.update(params or {})
    return {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "stage": {"id": stage},
        "entry": "pitstudio_studio.media.encode",
        "params": base_params,
        "seed": 0,
        "shard": None,
        "inputs": [
            {
                "name": "st50_physics/frames/manifest.json",
                "path": str(seq.manifest_path),
                "sha256": file_sha256(seq.manifest_path),
            }
        ],
        "output_dir": str(out),
        "scratch_dir": str(scratch),
        "resume": False,
        "rerun": False,
        "profiling": profiling,
        "profile": {"id": "local", "cpu_slots": 4},
        "vram_fraction": None,
        "nvtx_range": "st56_encode/0",
    }


# --------------------------------------------------------------------------------------------------------------------
# Clock, locks, executables
# --------------------------------------------------------------------------------------------------------------------
class FakeClock:
    """Monotonic clock stand-in; time moves only when told to."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = float(start)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def install_exe(folder: Path, content: bytes = b"fake-ffmpeg-n8.1-build", name: str = "ffmpeg") -> tuple[Path, str]:
    """A stand-in executable file (the fake runner never executes it) and its SHA-256 computed by `hashlib`."""
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / (name + (".exe" if os.name == "nt" else ""))
    p.write_bytes(content)
    if os.name != "nt":
        p.chmod(0o755)
    return p, hashlib.sha256(content).hexdigest()


def held_env(value: str | None) -> dict[str, str]:
    """An environment mapping with `PITSTUDIO_HELD_LOCKS` set to `value` (absent when None)."""
    return {} if value is None else {"PITSTUDIO_HELD_LOCKS": value}


# --------------------------------------------------------------------------------------------------------------------
# FakeFFmpeg
# --------------------------------------------------------------------------------------------------------------------
DEFAULT_ENCODERS = ("av1_nvenc", "h264_nvenc", "libwebp", "libx264", "png")
DEFAULT_FILTERS = ("libvmaf", "scale", "format")
DEFAULT_OPTIONS = {
    "av1_nvenc": ("preset", "tune", "rc", "cq", "b", "g", "bf", "rc-lookahead"),
    "h264_nvenc": ("preset", "tune", "rc", "cq", "profile", "g", "bf", "rc-lookahead"),
    "libwebp": ("quality", "compression_level", "preset"),
}


def mp4_bytes(total: int, *, moov_first: bool) -> bytes:
    """A syntactically valid top-level box sequence of exactly `total` bytes: ftyp, then moov and mdat in the stated order."""
    ftyp = struct.pack(">I4s4sI4s4s", 24, b"ftyp", b"isom", 512, b"isom", b"iso2")
    moov = struct.pack(">I4s", 128, b"moov") + b"\x00" * 120
    mdat_len = total - len(ftyp) - len(moov)
    if mdat_len < 8:
        raise ValueError("size too small for an MP4 skeleton")
    mdat = struct.pack(">I4s", mdat_len, b"mdat") + b"\x00" * (mdat_len - 8)
    return ftyp + (moov + mdat if moov_first else mdat + moov)


class FakeFFmpeg:
    """Programmable FFmpeg stand-in; `calls` records every argument list it was given."""

    def __init__(
        self,
        *,
        clock: FakeClock | None = None,
        version_line: str = "n8.1",
        encoders: Iterable[str] = DEFAULT_ENCODERS,
        filters: Iterable[str] = DEFAULT_FILTERS,
        options: Mapping[str, Iterable[str]] | None = None,
        frames: int = 3,
        fps: int = 30,
        scores: Callable[[str, int], Sequence[float]] | None = None,
        sizes: Callable[[str, int], int] | None = None,
        poster_sizes: Callable[[int], int] | None = None,
        rates: Mapping[str, float] | None = None,
        faststart_honoured: bool = True,
        decode_overrides: Mapping[str, Mapping[str, object]] | None = None,
    ) -> None:
        self.clock = clock or FakeClock()
        self.version_line = version_line
        self.encoders = tuple(encoders)
        self.filters = tuple(filters)
        self.options = {k: tuple(v) for k, v in (options or DEFAULT_OPTIONS).items()}
        self.frames = frames
        self.fps = fps
        self.scores = scores or (lambda codec, cq: [100.0 - 0.5 * cq] * self.frames)
        self.sizes = sizes or (lambda codec, cq: 1_000_000 - 10_000 * cq)
        self.poster_sizes = poster_sizes or (lambda q: 2000 * q)
        self.rates = dict(rates or {"av1": 200.0, "h264": 400.0})
        self.faststart_honoured = faststart_honoured
        self.decode_overrides = {k: dict(v) for k, v in (decode_overrides or {}).items()}
        self.calls: list[list[str]] = []
        self.produced: dict[Path, dict] = {}

    # ---- helpers ----------------------------------------------------------------------------------------------
    @staticmethod
    def _arg(argv: Sequence[str], flag: str) -> str | None:
        for i, a in enumerate(argv[:-1]):
            if a == flag:
                return argv[i + 1]
        return None

    def _done(self, argv: Sequence[str], out: str = "", err: str = "", rc: int = 0) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(list(argv), rc, out, err)

    def kinds(self) -> list[str]:
        """The classes of the calls so far: version, encoders, filters, options, encode, poster, vmaf, decode, other."""
        return [self._classify(c) for c in self.calls]

    def _classify(self, argv: Sequence[str]) -> str:
        a = list(argv)
        if "-version" in a:
            return "version"
        if "-encoders" in a:
            return "encoders"
        if "-filters" in a:
            return "filters"
        if "-h" in a and any(x.startswith("encoder=") for x in a):
            return "options"
        if any("libvmaf" in x for x in a):
            return "vmaf"
        if self._arg(a, "-f") == "null":
            return "decode"
        codec = self._arg(a, "-c:v") or self._arg(a, "-vcodec")
        if codec in ("av1_nvenc", "h264_nvenc"):
            return "encode"
        if codec == "libwebp":
            return "poster"
        return "other"

    def n_encodes(self) -> int:
        return sum(1 for k in self.kinds() if k == "encode")

    # ---- the runner seam ----------------------------------------------------------------------------------------
    def __call__(self, argv: Sequence[str], **kw: object) -> subprocess.CompletedProcess:
        assert isinstance(argv, (list, tuple)), "FFmpeg must be called with an argument list, never a string"
        assert not kw.get("shell"), "FFmpeg must never be called through a shell"
        self.calls.append([str(x) for x in argv])
        a = [str(x) for x in argv]
        cwd = Path(str(kw["cwd"])) if kw.get("cwd") else None
        kind = self._classify(a)
        if kind == "version":
            return self._done(
                a,
                f"ffmpeg version {self.version_line} Copyright (c) 2000-2026 the FFmpeg developers\nbuilt with gcc 14\n",
            )
        if kind == "encoders":
            lines = "".join(f" V....D {n:<18} fake encoder (codec {n})\n" for n in self.encoders)
            return self._done(a, "Encoders:\n V..... = Video\n ------\n" + lines)
        if kind == "filters":
            lines = "".join(f" ... {n:<18} V->V       fake filter\n" for n in self.filters)
            return self._done(a, "Filters:\n  T.. = Timeline support\n ------\n" + lines)
        if kind == "options":
            name = next(x for x in a if x.startswith("encoder="))[len("encoder=") :]
            if name not in self.encoders:
                return self._done(a, "", f"Codec '{name}' is not recognized by FFmpeg.\n", 1)
            opts = "".join(f"  -{o:<16} <int>        E..V....... option {o}\n" for o in self.options.get(name, ()))
            return self._done(a, f"Encoder {name} [fake]:\n{name} AVOptions:\n{opts}")
        out_path = Path(a[-1])
        if cwd and not out_path.is_absolute():
            out_path = cwd / out_path
        if kind in ("encode", "poster"):
            return self._encode(a, kind, out_path)
        if kind == "vmaf":
            return self._vmaf(a, cwd)
        if kind == "decode":
            return self._decode(a, cwd)
        return self._done(a, "", f"fake ffmpeg: unrecognised invocation {a!r}\n", 1)

    def _encode(self, a: list[str], kind: str, out_path: Path) -> subprocess.CompletedProcess:
        if not out_path.parent.is_dir():
            return self._done(a, "", f"Could not open file {out_path}\n", 1)
        if kind == "poster":
            q = self._arg(a, "-quality") or self._arg(a, "-q:v")
            if q is None:
                return self._done(a, "", "fake ffmpeg: poster without -quality\n", 1)
            size = self.poster_sizes(int(float(q)))
            out_path.write_bytes(b"RIFF" + struct.pack("<I", size - 8) + b"WEBP" + b"\x00" * (size - 12))
            self.produced[out_path.resolve()] = {"kind": "poster", "quality": int(float(q)), "size": size}
            return self._done(a)
        codec = "av1" if self._arg(a, "-c:v") == "av1_nvenc" else "h264"
        cq = self._arg(a, "-cq")
        if cq is None:
            return self._done(a, "", "fake ffmpeg: NVENC constant quality needs -cq\n", 1)
        size = int(self.sizes(codec, int(cq)))
        moov_first = self.faststart_honoured and "+faststart" in (self._arg(a, "-movflags") or "")
        out_path.write_bytes(mp4_bytes(size, moov_first=moov_first))
        self.produced[out_path.resolve()] = {"kind": "video", "codec": codec, "cq": int(cq), "size": size}
        self.clock.advance(self.frames / self.rates[codec])
        return self._done(a)

    def _find_produced(self, a: Sequence[str], cwd: Path | None) -> tuple[Path, dict] | None:
        for x in a:
            p = Path(x)
            if cwd and not p.is_absolute():
                p = cwd / p
            try:
                rp = p.resolve()
            except OSError:
                continue
            if rp in self.produced and self.produced[rp]["kind"] == "video":
                return rp, self.produced[rp]
        return None

    def _vmaf(self, a: list[str], cwd: Path | None) -> subprocess.CompletedProcess:
        found = self._find_produced(a, cwd)
        graph = " ".join(a)
        m = re.search(r"log_path=(?:'([^']*)'|([^:,;\[\]\s]+(?:\\:[^:,;\[\]\s]+)*))", graph)
        if not found or not m:
            return self._done(a, "", "fake ffmpeg: VMAF run without a produced input or log_path\n", 1)
        log = (m.group(1) or m.group(2)).replace("\\:", ":")
        log_path = Path(log)
        if cwd and not log_path.is_absolute():
            log_path = cwd / log_path
        info = found[1]
        per_frame = list(self.scores(info["codec"], info["cq"]))
        doc = {
            "version": "3.0.0",
            "frames": [{"frameNum": i, "metrics": {"vmaf": float(s)}} for i, s in enumerate(per_frame)],
            "pooled_metrics": {"vmaf": {"mean": sum(per_frame) / len(per_frame)}},
        }
        log_path.write_text(json.dumps(doc), encoding="utf-8")
        return self._done(a)

    def _decode(self, a: list[str], cwd: Path | None) -> subprocess.CompletedProcess:
        name = next((Path(x).name for x in a if x.lower().endswith(".mp4")), "")
        ov = next((v for k, v in self.decode_overrides.items() if name.endswith(k)), {})
        n = int(ov.get("frames", self.frames))
        t_s = float(ov.get("out_time_s", self.frames / self.fps))
        out = f"frame={n}\nfps=0.00\nout_time_us={round(t_s * 1_000_000)}\nprogress=end\n"
        return self._done(a, out, str(ov.get("stderr", "")), int(ov.get("returncode", 0)))


def schema_validator(stem: str, defs: str | None = None):
    """A Draft 2020-12 validator for `contracts/<stem>.schema.json` (or one of its `$defs`), with every contract registered by `$id`."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    reg = Registry()
    for f in (ROOT / "contracts").glob("*.schema.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        reg = reg.with_resource(d["$id"], Resource.from_contents(d))
    root = json.loads((ROOT / "contracts" / f"{stem}.schema.json").read_text(encoding="utf-8"))
    schema = root if defs is None else {"$ref": f"{root['$id']}#/$defs/{defs}"}
    return Draft202012Validator(schema, registry=reg)


def std_scores(frames: int) -> Callable[[str, int], Sequence[float]]:
    """Hand-calculable VMAF curves with constant per-frame scores: AV1 100 - 0.5 (cq - 20), H.264 100 - 0.4 (cq - 15).

    Targets (mean >= 93 and p5 >= 85, equal to the mean here) are met up to cq 34 for AV1 (93.0) and cq 32 for H.264 (93.2).
    """
    return lambda codec, cq: [(100.0 - 0.5 * (cq - 20)) if codec == "av1" else (100.0 - 0.4 * (cq - 15))] * frames


def std_sizes(codec: str, cq: int) -> int:
    """Bytes: AV1 900,000 - 10,000 (cq - 20) (760,000 at cq 34), H.264 700,000 - 10,000 (cq - 15) (530,000 at cq 32)."""
    return 900_000 - 10_000 * (cq - 20) if codec == "av1" else 700_000 - 10_000 * (cq - 15)


class Ctx:
    """A ready-to-run stage environment: job, fake FFmpeg, fake clock, FFmpeg `env`, pinned digest and driver version."""

    def __init__(
        self, job: dict, ff: FakeFFmpeg, clock: FakeClock, env: dict, seq: Sequence3, sha: str, driver: str
    ) -> None:
        self.job, self.ff, self.clock, self.env, self.seq, self.sha, self.driver = job, ff, clock, env, seq, sha, driver

    def run(self, **override: object) -> dict:
        from pitstudio_studio.media.encode import run  # first-party module under test

        kw: dict = {"runner": self.ff, "clock": self.clock, "env": self.env, "driver_version": self.driver}
        kw.update(override)
        return run(self.job, **kw)

    @property
    def out(self) -> Path:
        return Path(self.job["output_dir"])


def prepare(
    tmp_path: Path,
    monkeypatch: object,
    *,
    n: int = 3,
    fps: int = 30,
    performance: str = "public",
    extra: Mapping[str, object] | None = None,
    fake_kw: Mapping[str, object] | None = None,
    params: Mapping[str, object] | None = None,
    held: str | None = NVENC_LOCK,
    driver: str = "582.78",
    version_line: str = "n8.1",
    clip: str = "fixture-clip",
) -> Ctx:
    """Build a sequence, a fake FFmpeg with the `std_*` curves, a job and the environment (`monkeypatch` is pytest's)."""
    seq = Sequence3(tmp_path, n, fps=fps, performance=performance, extra=extra, clip=clip)
    clock = FakeClock()
    exe, sha = install_exe(tmp_path / "bin")
    kw: dict = {
        "clock": clock,
        "frames": n,
        "fps": fps,
        "scores": std_scores(n),
        "sizes": std_sizes,
        "version_line": version_line,
    }
    kw.update(fake_kw or {})
    ff = FakeFFmpeg(**kw)
    if held is None:
        monkeypatch.delenv("PITSTUDIO_HELD_LOCKS", raising=False)  # type: ignore[attr-defined]
    else:
        monkeypatch.setenv("PITSTUDIO_HELD_LOCKS", held)  # type: ignore[attr-defined]
    p = {"pinned_ffmpeg_sha256": sha, "nvenc_api": "13.0"}
    p.update(params or {})
    job = make_job(tmp_path, seq, params=p)
    return Ctx(job, ff, clock, {"PITSTUDIO_FFMPEG": str(exe), "PATH": ""}, seq, sha, driver)


# --------------------------------------------------------------------------------------------------------------------
# NVTX and Warp fakes (FR-006-17, FR-006-20)
# --------------------------------------------------------------------------------------------------------------------
class FakeNVTX:
    """A fake `nvtx` module: records ('push'|'pop', name) in `events`; start_range/end_range are recorded too."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self._open: dict[int, str] = {}
        self._n = 0

    def push_range(self, message: str = "", *args: object, **kwargs: object) -> None:
        self.events.append(("push", message))

    def pop_range(self, *args: object, **kwargs: object) -> None:
        self.events.append(("pop", ""))

    def start_range(self, message: str = "", *args: object, **kwargs: object) -> int:
        self._n += 1
        self._open[self._n] = message
        self.events.append(("push", message))
        return self._n

    def end_range(self, rng: int) -> None:
        self.events.append(("pop", self._open.pop(rng)))

    def annotate(self, message: str = "", *args: object, **kwargs: object):
        """`nvtx.annotate(message)`: usable as a context manager (and a decorator) that pushes on entry and pops on exit."""
        import contextlib

        @contextlib.contextmanager
        def _cm():
            self.push_range(message)
            try:
                yield
            finally:
                self.pop_range()

        return _cm()

    def as_module(self) -> types.ModuleType:
        m = types.ModuleType("nvtx")
        for name in ("push_range", "pop_range", "start_range", "end_range", "annotate"):
            setattr(m, name, getattr(self, name))
        return m

    def balanced(self) -> bool:
        depth = 0
        for kind, _ in self.events:
            depth += 1 if kind == "push" else -1
            if depth < 0:
                return False
        return depth == 0

    def stack_trace(self) -> list[str]:
        """The sequence of open range names after each event, as 'a/b/c' strings ('' when empty), for nesting checks."""
        stack: list[str] = []
        out: list[str] = []
        for kind, name in self.events:
            if kind == "push":
                stack.append(name)
            else:
                stack.pop()
            out.append("/".join(stack))
        return out


def box_types(data: bytes) -> list[tuple[str, int]]:
    """Top-level ISO base media boxes of `data` as (type, size) by the 32-bit size / 4-byte type header (ISO/IEC 14496-12)."""
    out, pos = [], 0
    while pos + 8 <= len(data):
        size, kind = struct.unpack(">I4s", data[pos : pos + 8])
        out.append((kind.decode("latin-1"), size))
        if size < 8:
            break
        pos += size
    return out
