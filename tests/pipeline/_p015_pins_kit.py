# ruff: noqa: E501
"""Shared fixtures of the spec 015 pipeline-lane acceptance tests (package `pitstudio_pipeline.reason`).

This module holds no test. It is imported by `tests/pipeline/test_t_015_0NN_*.py` and is locked with the first of them. It builds,
under a temporary folder, a complete fake environment of the reason lane that follows `contracts/reason-pins.schema.json`:

- `archive_dir`: the two llama.cpp b11381 archives (names fixed by the schema) with small deterministic contents;
- `runtime_dir`: the unpacked executables (`llama-server.exe`, `llama-quantize.exe`, `llama-mtmd-cli.exe`), outside `repo_root`;
- `repo_root/studio/reason/prompts/*.txt`: the ten committed prompts, and `repo_root/studio/reason/pins.json`;
- `hub`: a fake Hugging Face hub (`FakeHub`) serving the two pinned repositories at their pinned revisions, with the file bytes
  whose SHA-256 values are in the pins; every digest here is computed with `hashlib` in this file, never by the code under test.

Everything is built from the standard library only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

COSMOS_REPO = "nvidia/Cosmos-Reason2-2B"
QWEN_REPO = "Qwen/Qwen3-VL-2B-Instruct"
COSMOS_REV = "9ce19a1" + "0123456789abcdef0123456789abcdef0"  # 7 + 33 hex characters
QWEN_REV = "89644892e4d85e24eaac8bacfd4f463576704203"
BINARIES = "llama-b11381-bin-win-cuda-13.4-x64.zip"
CUDART = "cudart-llama-bin-win-cuda-13.4-x64.zip"
EXECUTABLES = ("llama-server.exe", "llama-quantize.exe", "llama-mtmd-cli.exe")
PROMPT_NAMES = ["system", *[f"task_a_type_{i}" for i in range(1, 7)], "task_b_pair", "task_b_single", "task_c_caption"]
STAGES = ("st59_reason_bench", "st59a_vqa", "st59b_plausibility", "st59c_captions")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def payload(tag: str, n: int = 2048) -> bytes:
    """Deterministic pseudo-random bytes derived from a tag."""
    out = bytearray()
    i = 0
    while len(out) < n:
        out += hashlib.sha256(f"{tag}|{i}".encode()).digest()
        i += 1
    return bytes(out[:n])


MODEL_FILES = {
    COSMOS_REPO: {
        "config.json": payload("cosmos-config", 300),
        "model.safetensors": payload("cosmos-weights", 4096),
        "tokenizer.json": payload("cosmos-tok", 700),
    },
    QWEN_REPO: {"config.json": payload("qwen-config", 280), "model.safetensors": payload("qwen-weights", 3072)},
}
REVISIONS = {COSMOS_REPO: COSMOS_REV, QWEN_REPO: QWEN_REV}


@dataclass
class FakeHub:
    """A fake hub: `files[(repo, revision)][name] -> bytes`. `calls` records every request as (repo, revision, name);
    `status` maps a repository to an HTTP status (401 or 403 make every request for it fail)."""

    files: dict = field(default_factory=dict)
    status: dict = field(default_factory=dict)
    calls: list = field(default_factory=list)

    def fetch(self, repo: str, revision: str, name: str) -> bytes:
        self.calls.append((repo, revision, name))
        code = self.status.get(repo)
        if code:
            raise PermissionError(code)
        try:
            return self.files[(repo, revision)][name]
        except KeyError as e:
            raise FileNotFoundError(f"{repo}@{revision}:{name}") from e


def default_hub() -> FakeHub:
    return FakeHub(files={(r, REVISIONS[r]): dict(f) for r, f in MODEL_FILES.items()})


@dataclass
class Env:
    root: Path
    repo_root: Path
    archive_dir: Path
    runtime_dir: Path
    pins_path: Path
    pins: dict
    files: dict  # name -> Path of every pinned archive and executable


def build_env(tmp: Path, *, prompts: dict[str, str] | None = None) -> Env:
    repo_root = tmp / "repo"
    archive_dir = tmp / "outside" / "archives"
    runtime_dir = tmp / "outside" / "llama-b11381"
    for d in (repo_root / "studio" / "reason" / "prompts", archive_dir, runtime_dir):
        d.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    arch = {}
    for key, name in (("binaries", BINARIES), ("cudart", CUDART)):
        data = payload(name, 1500)
        p = archive_dir / name
        p.write_bytes(data)
        files[name] = p
        arch[key] = {
            "name": name,
            "url": f"https://github.com/ggml-org/llama.cpp/releases/download/b11381/{name}",
            "bytes": len(data),
            "sha256": sha256_hex(data),
        }
    exes = {}
    for name in EXECUTABLES:
        data = payload(name, 900)
        p = runtime_dir / name
        p.write_bytes(data)
        files[name] = p
        exes[name] = sha256_hex(data)
    prompt_pins = {}
    for n in PROMPT_NAMES:
        text = (prompts or {}).get(n, f"Committed prompt {n}. Reply inside <answer></answer>.\n")
        fp = repo_root / "studio" / "reason" / "prompts" / f"{n.replace('_', '-')}.txt"
        fp.write_bytes(text.encode("utf-8"))
        prompt_pins[n] = {"path": f"studio/reason/prompts/{fp.name}", "sha256": sha256_hex(text.encode("utf-8"))}
    converter = payload("convert_hf_to_gguf.py", 500)
    pins = {
        "schema_version": "1.0",
        "llamacpp": {
            "build": "b11381",
            "archives": arch,
            "executables": exes,
            "converter": {"source_tag": "b11381", "path": "convert_hf_to_gguf.py", "sha256": sha256_hex(converter)},
        },
        "models": {
            "cosmos": {
                "repository": COSMOS_REPO,
                "revision": COSMOS_REV,
                "files": {n: {"sha256": sha256_hex(b), "bytes": len(b)} for n, b in MODEL_FILES[COSMOS_REPO].items()},
            },
            "qwen": {
                "repository": QWEN_REPO,
                "revision": QWEN_REV,
                "files": {n: {"sha256": sha256_hex(b), "bytes": len(b)} for n, b in MODEL_FILES[QWEN_REPO].items()},
            },
        },
        "prompts": prompt_pins,
    }
    pins_path = repo_root / "studio" / "reason" / "pins.json"
    pins_path.write_text(json.dumps(pins, indent=2), encoding="utf-8")
    return Env(tmp, repo_root, archive_dir, runtime_dir, pins_path, pins, files)


def write_pins(env: Env, pins: dict) -> None:
    env.pins_path.write_text(json.dumps(pins, indent=2), encoding="utf-8")
