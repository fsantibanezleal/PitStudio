"""The lane's own GGUF conversion of the verified Cosmos snapshot (FR-015-05, P-015-12, FR-015-06).

`convert_model` runs `convert_hf_to_gguf.py` of the llama.cpp source at tag b11381 for the F16 text model and, with
`--mmproj`, for the F16 vision projector, then `llama-quantize` b11381 for Q8_0 from the text model, and records the
SHA-256 of every output. Before any command it verifies the snapshot against the Cosmos pins, the converter script
against its pin and that the output folder lies outside the repository (conversions are never tracked in git).
A second conversion of the same inputs with the same tools gives identical digests (checked locally on the real model by
the gpu test of T-015-070).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitstudio_pipeline.download.hashing import sha256_file
from pitstudio_pipeline.reason.hub import verify_snapshot
from pitstudio_pipeline.reason.runtime import PinError, VerifiedRuntime

Q8_BLOCK_WEIGHTS, Q8_BLOCK_BYTES = 32, 34
STEMS = {"f16": "{which}-f16.gguf", "mmproj": "mmproj-{which}-f16.gguf", "q8_0": "{which}-q8_0.gguf"}


class ConversionError(Exception):
    """A conversion step failed or a precondition does not hold; `step` is f16, mmproj, q8_0 or inputs."""

    def __init__(self, step: str, reason: str) -> None:
        super().__init__(f"conversion step {step}: {reason}")
        self.step = step
        self.reason = reason


@dataclass(frozen=True)
class ConversionResult:
    f16: Path
    mmproj: Path
    q8_0: Path
    sha256: Mapping[str, str]


def q8_0_tensor_bytes(n_weights: int) -> int:
    """Bytes of a Q8_0 tensor: blocks of 32 weights take 34 bytes (an fp16 scale and 32 int8 values)."""
    if not isinstance(n_weights, int) or n_weights < 0 or n_weights % Q8_BLOCK_WEIGHTS:
        raise ValueError(f"a Q8_0 tensor holds a whole number of {Q8_BLOCK_WEIGHTS}-weight blocks, got {n_weights!r}")
    return n_weights // Q8_BLOCK_WEIGHTS * Q8_BLOCK_BYTES


def _inside(path: Path, root: Path) -> bool:
    p, r = Path(path).resolve(), Path(root).resolve()
    return p == r or r in p.parents


def convert_model(
    snapshot: Path,
    out_dir: Path,
    *,
    runtime: VerifiedRuntime,
    pins: Mapping[str, Any],
    python: str | Path,
    converter: Path,
    runner: Callable[[Sequence[str]], int],
    repo_root: Path,
    which: str = "cosmos",
) -> ConversionResult:
    """Convert and quantise; see the module docstring for the order and the checks."""
    if _inside(out_dir, repo_root):
        raise ConversionError("inputs", f"the output folder {out_dir} lies inside the repository")
    verify_snapshot(snapshot, pins, which)
    pin = pins["llamacpp"]["converter"]
    if not Path(converter).is_file() or sha256_file(converter) != pin["sha256"]:
        raise PinError(pin["path"], f"{converter} is missing or differs from the pinned converter script")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {k: out / v.format(which=which) for k, v in STEMS.items()}
    base = [str(python), str(converter), str(snapshot), "--outtype", "f16"]
    steps = [
        ("f16", [*base, "--outfile", str(paths["f16"])]),
        ("mmproj", [*base, "--outfile", str(paths["mmproj"]), "--mmproj"]),
        ("q8_0", [str(runtime.executable("llama-quantize.exe")), str(paths["f16"]), str(paths["q8_0"]), "Q8_0"]),
    ]
    for step, argv in steps:
        try:
            code = runner(argv)
        except OSError as exc:
            raise ConversionError(step, f"could not run the tool: {exc.strerror}") from exc
        if code != 0:
            raise ConversionError(step, f"the tool exited with code {code}")
        if not paths[step].is_file():
            raise ConversionError(step, f"the tool wrote no {paths[step].name}")
    digests = {k: sha256_file(p) for k, p in paths.items()}
    record = {
        **digests,
        "llama_cpp_build": runtime.build,
        "converter_sha256": pin["sha256"],
        "model": which,
        "revision": pins["models"][which]["revision"],
    }
    (out / "conversion.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return ConversionResult(paths["f16"], paths["mmproj"], paths["q8_0"], digests)
