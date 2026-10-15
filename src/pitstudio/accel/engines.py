"""Engine builds for s62_accel behind a backend protocol (FR-016-20, FR-016-21, FR-016-03, FR-016-10).

The real TensorRT adapter implements `build(...)` (see `pipeline/accel/build_engines.py`); the loop, the guards, the
builder configuration record and the error scrubbing here are pure Python and tested against a fake backend.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pitstudio.accel.guards import assert_under_run_folder
from pitstudio.export.variant_rules import check_variant_request

_SEG = r"[^\\/\s:*?\"<>|()']+"
_WINDOWS_PATH = re.compile(rf"(?<![\w])[A-Za-z]:[\\/](?:{_SEG}(?: {_SEG})*[\\/])*{_SEG}")
_UNC_PATH = re.compile(rf"\\\\{_SEG}(?:[\\/](?:{_SEG}(?: {_SEG})*(?=[\\/])|{_SEG}))+")
_POSIX_PATH = re.compile(r"(?<![\w/.:])/(?:[^/\s()'\"]+/)*[^/\s()'\"]+")


def scrub_error(text: str) -> str:
    """Replace absolute Windows, UNC and POSIX file-system paths by `<path>`; other text is unchanged."""
    text = _UNC_PATH.sub("<path>", text)
    text = _WINDOWS_PATH.sub("<path>", text)
    return _POSIX_PATH.sub("<path>", text)


@dataclass(frozen=True)
class CudaEnv:
    env: dict[str, str]
    dll_dirs: list[Path]


def configure_cuda_env(env: Mapping[str, str], runtime_dir: Path) -> CudaEnv:
    """A copy of `env` that points CUDA_PATH and the DLL search path at the CUDA 13 runtime wheel."""
    runtime_dir = Path(runtime_dir)
    candidates = [runtime_dir / "bin" / "x86_64", runtime_dir / "bin", runtime_dir]
    dirs = [d for d in candidates if d.is_dir()] or [runtime_dir]
    out = dict(env)
    out["CUDA_PATH"] = str(runtime_dir)
    out["PATH"] = os.pathsep.join([*(str(d) for d in dirs), env.get("PATH", "")]).rstrip(os.pathsep)
    return CudaEnv(out, dirs)


class Clock(Protocol):
    def monotonic(self) -> float: ...


class Backend(Protocol):
    version: str

    def build(self, onnx_path: Path, *, precision: str, profile: dict, flags: dict, out_path: Path) -> None: ...


@dataclass
class EngineRecord:
    model: str
    precision: str
    status: str
    tensorrt_version: str
    engine_path: Path | None
    engine_sha256: str | None
    builder_config: dict[str, Any] | None
    build_time_s: float
    error: str | None
    extra: dict[str, Any] = field(default_factory=dict)


def _profile(batch_sizes: Sequence[int]) -> dict[str, int]:
    ordered = sorted(batch_sizes)
    return {"min": ordered[0], "opt": ordered[len(ordered) // 2], "max": ordered[-1]}


def build_engines(
    variants: Sequence[Mapping[str, Any]],
    backend: Backend,
    *,
    run_dir: Path,
    clock: Clock,
    onnx_guard: Callable[[Path], None],
) -> list[EngineRecord]:
    """Build one strongly typed engine per variant; refusals and hostile ONNX files stop before any build."""
    run_dir = Path(run_dir)
    for v in variants:
        cfg = v["config"]
        check_variant_request(v["precision"], opset=cfg.get("opset", 0), gemm_heavy=cfg.get("gemm_heavy", False))
        onnx_guard(Path(v["onnx"]))
    records: list[EngineRecord] = []
    for v in variants:
        onnx_path = Path(v["onnx"])
        name = f"{v['model']}-{v['precision']}"
        out_path = run_dir / "engines" / f"{name}.engine"
        cache = run_dir / "timing-caches" / f"{name}.timing-cache"
        assert_under_run_folder(out_path, run_dir)
        assert_under_run_folder(cache, run_dir)
        profile = _profile(v["batch_sizes"])
        flags = {"strongly_typed": True, "tf32": False, "timing_cache": str(cache)}
        config = {
            "strongly_typed": True,
            "tf32": False,
            "profile": profile,
            "precision": v["precision"],
            "onnx_sha256": hashlib.sha256(onnx_path.read_bytes()).hexdigest(),
        }
        start = clock.monotonic()
        try:
            backend.build(onnx_path, precision=v["precision"], profile=profile, flags=flags, out_path=out_path)
        except Exception as exc:
            out_path.unlink(missing_ok=True)
            records.append(
                EngineRecord(
                    v["model"],
                    v["precision"],
                    "build-failed",
                    backend.version,
                    None,
                    None,
                    config,
                    clock.monotonic() - start,
                    scrub_error(str(exc)),
                )
            )
            continue
        elapsed = clock.monotonic() - start
        digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
        records.append(
            EngineRecord(v["model"], v["precision"], "built", backend.version, out_path, digest, config, elapsed, None)
        )
    return records
