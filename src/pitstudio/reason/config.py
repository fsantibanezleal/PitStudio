"""Committed prompts, decoding settings and lane-configuration validation (FR-015-24, FR-015-25, FR-015-44).

- The ten prompts of the lane (system prompt, six task-A templates, two task-B templates, the task-C caption
  prompt) live in `studio/reason/prompts/` and are pinned by SHA-256 in `studio/reason/pins.json`; the hashes are
  checked at every load.
- No prompt may ask the model to ignore or bypass its safety behaviour.
- Decoding is greedy (temperature 0, top-k 1) with one fixed seed, native image resolution and at most 64 new
  tokens with reasoning off, 4,096 with reasoning on.
- A lane configuration naming an unknown arm, task or question type, a temperature other than 0, a non-positive
  token limit, an image side above 4,096 px or an input outside the stage's declared inputs is refused with exit
  code 2.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PROMPT_NAMES = (
    "system",
    "task_a_type_1",
    "task_a_type_2",
    "task_a_type_3",
    "task_a_type_4",
    "task_a_type_5",
    "task_a_type_6",
    "task_b_pair",
    "task_b_single",
    "task_c_caption",
)
PROMPT_PATH = re.compile(r"studio/reason/prompts/[a-z0-9][a-z0-9_-]{0,62}\.txt")
SEED = 20261015
MAX_NEW_TOKENS_OFF = 64
MAX_NEW_TOKENS_ON = 4096
MAX_IMAGE_SIDE_PX = 4096
ARMS = ("cosmos-q8_0", "cosmos-bf16", "qwen-base", "detector-rule", "constant")
TASKS = ("A", "B", "C")
QUESTION_TYPES = (1, 2, 3, 4, 5, 6)
CONFIG_KEYS = (
    "arms",
    "tasks",
    "question_types",
    "temperature",
    "max_new_tokens",
    "image_max_side_px",
    "inputs",
)
EXIT_CODE = 2


class PromptHashMismatch(ValueError):
    """A pinned prompt is missing, differs from its pin or sits outside the prompt folder."""

    def __init__(self, name: str, path: str, detail: str) -> None:
        super().__init__(f"prompt {name!r} ({path}): {detail}")
        self.name = name
        self.path = path


class PromptRejected(ValueError):
    """A prompt holds a phrase that asks the model to ignore or bypass its safety behaviour (FR-015-44)."""

    def __init__(self, name: str, found: list[str]) -> None:
        super().__init__(f"prompt {name!r} contains safety-bypass wording: {', '.join(found)}")
        self.name = name
        self.found = found


class LaneConfigError(ValueError):
    """A lane configuration is refused; the stage exits with code 2 and names `field`."""

    exit_code = EXIT_CODE

    def __init__(self, field: str, detail: str) -> None:
        super().__init__(f"lane configuration field {field!r}: {detail}")
        self.field = field


# ------------------------------------------------------------------------------------------------------ prompts
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_pinned(pins: Mapping[str, Any], root: Path, name: str) -> bytes:
    try:
        pin = pins["prompts"][name]
        path, digest = pin["path"], pin["sha256"]
    except (KeyError, TypeError) as exc:
        raise PromptHashMismatch(name, "<unpinned>", "no pin for this prompt") from exc
    if not isinstance(path, str) or not PROMPT_PATH.fullmatch(path):
        raise PromptHashMismatch(name, str(path), "the path must be studio/reason/prompts/<name>.txt")
    try:
        data = (Path(root) / path).read_bytes()
    except OSError as exc:
        raise PromptHashMismatch(name, path, f"cannot read the file: {exc.strerror}") from exc
    if _sha256(data) != digest:
        raise PromptHashMismatch(name, path, "SHA-256 differs from the pin")
    return data


def verify_prompt_hashes(pins: Mapping[str, Any], root: Path) -> None:
    """Raise `PromptHashMismatch` unless every one of the ten prompts exists under `root` and matches its pin."""
    for name in PROMPT_NAMES:
        _read_pinned(pins, root, name)


_BYPASS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore or override instructions",
        re.compile(
            r"\b(?:ignore|disregard|forget|override)\b[^.!?\n]{0,40}?\b(?:instructions?|rules|guidelines|"
            r"guardrails?|safety|polic(?:y|ies)|restrictions?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "bypass safety",
        re.compile(
            r"\bbypass(?:ing)?\b[^.!?\n]{0,40}?\b(?:safety|guardrails?|filters?|restrictions?|polic(?:y|ies)|rules)\b",
            re.IGNORECASE,
        ),
    ),
    ("developer mode", re.compile(r"\bdeveloper\s+mode\b", re.IGNORECASE)),
    ("jailbreak", re.compile(r"\bjailbreak\w*", re.IGNORECASE)),
    ("do anything now", re.compile(r"\bdo\s+anything\s+now\b", re.IGNORECASE)),
    ("uncensored or unfiltered", re.compile(r"\b(?:un-?censored|un-?filtered)\b", re.IGNORECASE)),
    (
        "no restrictions",
        re.compile(
            r"\b(?:no|without(?:\s+any)?)\s+(?:safety\s+)?(?:restrictions?|guardrails?|filters?|rules|guidelines)\b",
            re.IGNORECASE,
        ),
    ),
)


def check_prompt_text(text: str) -> list[str]:
    """The safety-bypass wordings found in a text (case- and whitespace-insensitive); empty means acceptable."""
    squeezed = " ".join(text.split())
    return [label for label, pattern in _BYPASS if pattern.search(squeezed)]


def load_prompts(pins: Mapping[str, Any], root: Path) -> dict[str, str]:
    """Verify every pinned prompt (on every call) and return the texts; a prompt with bypass wording is refused."""
    texts = {}
    for name in PROMPT_NAMES:
        text = _read_pinned(pins, root, name).decode("utf-8")
        found = check_prompt_text(text)
        if found:
            raise PromptRejected(name, found)
        texts[name] = text
    return texts


def load_committed_prompts() -> dict[str, str]:
    """The prompts of this repository (`studio/reason/pins.json` and `studio/reason/prompts/`), verified."""
    pins = json.loads((ROOT / "studio" / "reason" / "pins.json").read_text(encoding="utf-8"))
    return load_prompts(pins, ROOT)


def decoding_settings(reasoning: bool) -> dict[str, Any]:
    """Greedy decoding at native image resolution; the seed is the same for every call."""
    return {
        "temperature": 0,
        "top_k": 1,
        "seed": SEED,
        "max_new_tokens": MAX_NEW_TOKENS_ON if reasoning else MAX_NEW_TOKENS_OFF,
        "reasoning": bool(reasoning),
        "image_resolution": "native",
    }


# ----------------------------------------------------------------------------------------- lane configuration
def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _enum_list(cfg: Mapping[str, Any], key: str, allowed: Sequence[Any], kind: type) -> None:
    value = cfg[key]
    if not isinstance(value, list) or len(value) == 0:
        raise LaneConfigError(key, f"must be a non-empty list of {allowed}")
    for item in value:
        if not isinstance(item, kind) or isinstance(item, bool) or item not in allowed:
            raise LaneConfigError(key, f"unknown value {item!r}; allowed: {allowed}")


_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9._-]+")


def _plain_parts(path: Any) -> tuple[str, ...] | None:
    """Components of a plain relative POSIX path (letters, digits, dot, dash, underscore; no `.` or `..`), else None."""
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path or ":" in path:
        return None
    parts = tuple(path.split("/"))
    if any(not _SAFE_COMPONENT.fullmatch(p) or p in (".", "..") for p in parts):
        return None
    return parts


def _check_inputs(inputs: Any, declared: Sequence[str]) -> None:
    if not isinstance(inputs, list):
        raise LaneConfigError("inputs", "must be a list of relative paths")
    folders = [_plain_parts(d) for d in declared]
    for path in inputs:
        parts = _plain_parts(path)
        if parts is None:
            raise LaneConfigError("inputs", f"{path!r} is not a plain relative path (URLs and traversal are refused)")
        if not any(f is not None and len(parts) > len(f) and parts[: len(f)] == f for f in folders):
            raise LaneConfigError("inputs", f"{path!r} is outside the declared inputs {list(declared)}")


def validate_lane_config(cfg: Any, *, declared_inputs: Sequence[str]) -> None:
    """Raise `LaneConfigError` (exit code 2, naming the field) for any value the lane must not run with."""
    if not isinstance(cfg, Mapping):
        raise LaneConfigError("config", "must be a mapping")
    for key in CONFIG_KEYS:
        if key not in cfg:
            raise LaneConfigError(key, "is missing")
    for key in cfg:
        if key not in CONFIG_KEYS:
            raise LaneConfigError(str(key), "is not a lane configuration key")
    _enum_list(cfg, "arms", ARMS, str)
    _enum_list(cfg, "tasks", TASKS, str)
    _enum_list(cfg, "question_types", QUESTION_TYPES, int)
    temperature = cfg["temperature"]
    if (
        not isinstance(temperature, int | float)
        or isinstance(temperature, bool)
        or not math.isfinite(temperature)
        or temperature != 0
    ):
        raise LaneConfigError("temperature", f"must be 0 for a scored arm, got {temperature!r}")
    tokens = cfg["max_new_tokens"]
    if not _is_int(tokens) or tokens <= 0:
        raise LaneConfigError("max_new_tokens", f"must be a positive integer, got {tokens!r}")
    side = cfg["image_max_side_px"]
    if not _is_int(side) or not 0 < side <= MAX_IMAGE_SIDE_PX:
        raise LaneConfigError("image_max_side_px", f"must be an integer in 1..{MAX_IMAGE_SIDE_PX}, got {side!r}")
    _check_inputs(cfg["inputs"], declared_inputs)
