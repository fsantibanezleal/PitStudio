# ruff: noqa: E501
"""T-015-015: the BF16 reference (transformers) configuration and lock, and the "agreement gate not evaluable" degradation.

Requirements: FR-015-09, FR-015-10.

Spec: specs/015-vlm/spec.md
- FR-015-09: the BF16 reference runs the official revision with transformers in BF16 in the `pipeline/` environment (resolved and locked before
  feature code), and is used for the agreement gate (FR-015-14) and for native-video inputs of task B. Test strategy: "lock contains transformers;
  fake loader failure -> states; local BF16 load" (the real load is tests/gpu/test_t_015_070_reason_local.py).
- FR-015-10: if the BF16 reference cannot load or run on the reference GPU, the BF16 arm is recorded "not run" with the measured reason, and every
  Cosmos Q8_0 result is recorded "not run (agreement gate not evaluable)".
- plan.md T-015-002: the lock gains transformers (with Qwen3-VL support: transformers 4.57 or newer), `gguf` (for `convert_hf_to_gguf.py` at b11381) and
  `huggingface-hub`; SciPy and scikit-learn (test references) are already locked.

Oracle: the committed `pipeline/uv.lock` and `pipeline/pyproject.toml` parsed with the standard library (`tomllib`); a fake loader that raises the
errors a real load can raise (CUDA out of memory, a missing weight file, a driver error); the metrics contract (`contracts/vlm-metrics.schema.json`,
`jsonschema`) for the gate and the rows; the pinned revision of the pin file.

Expected API of the implementation (package `pitstudio_pipeline`), `pitstudio_pipeline.reason.bf16`:
- `reference_config(pins) -> dict`: `{"repository": "nvidia/Cosmos-Reason2-2B", "revision": <pinned 40 hex>, "dtype": "bfloat16", "library": "transformers",
  "local_files_only": True}` (the reference loads only the verified local snapshot, never a branch name).
- `attempt_bf16(loader) -> dict`: calls `loader()`; returns `{"status": "available", "model": <what loader returned>}`, or, if it raises any Exception
  (including MemoryError and OSError), `{"status": "not_run", "reason": <text>}` where the text names the exception class and message (the measured
  reason), is 1 to 300 characters and contains no newline.
- `degrade_for_missing_bf16(state, rows) -> (gate, rows)`: for a "not_run" state returns the metrics `gate` object with status "not_run", `agree`,
  `agreement` and `wilson95` None, `q8_0_path` "not_run" and a `reason`; every `cosmos-q8_0` row becomes `status` "not_run" with a reason containing
  "agreement gate not evaluable" and every metric None; every `cosmos-bf16` row becomes `status` "not_run" with the measured reason; other rows
  are unchanged. For an "available" state it returns `(None, rows)` unchanged.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

import _p015_pins_kit as kit
import pytest
from hypothesis import given
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from pitstudio_pipeline.reason import bf16

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))  # the schema helper lives in tests/unit
import _p015_contracts as contracts

ROOT = Path(__file__).resolve().parents[2]


def _locked() -> dict[str, str]:
    lock = tomllib.loads((ROOT / "pipeline" / "uv.lock").read_text(encoding="utf-8"))
    return {p["name"]: p["version"] for p in lock["package"]}


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


@pytest.mark.req("FR-015-09")
@pytest.mark.parametrize("name", ["transformers", "gguf", "huggingface-hub", "scipy", "scikit-learn", "torch"])
def test_the_pipeline_lock_contains_the_packages_of_the_reason_lane(name: str) -> None:
    assert name in _locked(), f"{name} is not resolved in pipeline/uv.lock"


@pytest.mark.req("FR-015-09")
def test_the_locked_transformers_supports_qwen3_vl() -> None:
    assert _version_tuple(_locked()["transformers"]) >= (4, 57)  # Qwen3-VL landed in transformers 4.57


@pytest.mark.req("FR-015-09")
@pytest.mark.parametrize("name", ["transformers", "gguf", "huggingface-hub"])
def test_the_pipeline_project_declares_the_reason_lane_dependencies(name: str) -> None:
    project = tomllib.loads((ROOT / "pipeline" / "pyproject.toml").read_text(encoding="utf-8"))
    deps = [
        re.split(r"[<>=!~ \[;]", d, maxsplit=1)[0].lower().replace("_", "-") for d in project["project"]["dependencies"]
    ]
    assert name in deps


@pytest.mark.req("FR-015-09")
def test_the_reference_runs_the_pinned_official_revision_in_bfloat16_with_transformers_from_the_local_snapshot(
    tmp_path: Path,
) -> None:
    pins = kit.build_env(tmp_path).pins
    cfg = bf16.reference_config(pins)
    assert cfg["repository"] == "nvidia/Cosmos-Reason2-2B"
    assert cfg["revision"] == pins["models"]["cosmos"]["revision"]
    assert cfg["revision"].startswith("9ce19a1")
    assert len(cfg["revision"]) == 40
    assert (cfg["dtype"], cfg["library"], cfg["local_files_only"]) == ("bfloat16", "transformers", True)


ERRORS = [
    RuntimeError("CUDA out of memory. Tried to allocate 1.20 GiB (GPU 0; 16.00 GiB total capacity)"),
    MemoryError("host memory exhausted"),
    OSError("model.safetensors: No such file or directory"),
    ValueError("unsupported dtype"),
    RuntimeError(
        "CUDA error: an illegal memory access was encountered\nCUDA kernel errors might be asynchronously reported"
    ),
    RuntimeError("x" * 5000),
    Exception(""),
]


@pytest.mark.req("FR-015-10")
@pytest.mark.parametrize(
    "err",
    ERRORS,
    ids=[
        "oom",
        "memory-error",
        "missing-file",
        "value-error",
        "illegal-access-multiline",
        "huge-message",
        "empty-message",
    ],
)
def test_a_loader_failure_gives_not_run_with_the_measured_reason(err: Exception) -> None:
    def loader():
        raise err

    s = bf16.attempt_bf16(loader)
    assert s["status"] == "not_run"
    reason = s["reason"]
    assert 1 <= len(reason) <= 300
    assert "\n" not in reason
    assert type(err).__name__ in reason
    first = str(err).splitlines()[0][:40] if str(err) else ""
    assert first in reason


@pytest.mark.req("FR-015-10")
def test_a_loader_that_works_gives_an_available_state_with_its_model() -> None:
    sentinel = object()
    s = bf16.attempt_bf16(lambda: sentinel)
    assert s == {"status": "available", "model": sentinel}


@pytest.mark.req("FR-015-10")
def test_keyboard_interrupt_is_not_swallowed() -> None:
    def loader():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        bf16.attempt_bf16(loader)


@pytest.mark.req("FR-015-10")
@given(st.text(max_size=2000))
def test_property_any_error_text_gives_a_valid_bounded_reason(text: str) -> None:
    def loader():
        raise RuntimeError(text)

    s = bf16.attempt_bf16(loader)
    assert s["status"] == "not_run"
    assert 1 <= len(s["reason"]) <= 300
    assert "\n" not in s["reason"]
    assert "\r" not in s["reason"]


def _row(arm: str, qtype: int, *, reasoning: bool = False) -> dict:
    est = {"value": 0.8, "lo": 0.75, "hi": 0.85}
    return {
        "arm": arm,
        "reasoning": reasoning,
        "type": qtype,
        "status": "measured",
        "n": 1000,
        "balanced_accuracy": est,
        "f1": est,
        "unparseable_rate": 0.01,
        "error_rate": 0.0,
        "auroc": None,
        "by_condition": [],
    }


def _errors(obj: dict, ref: str) -> list[str]:
    base = contracts.validator("vlm-metrics.schema.json").schema["$id"]
    v = Draft202012Validator({"$ref": base + ref}, registry=contracts._registry())
    return [e.message for e in v.iter_errors(obj)]


@pytest.mark.req("FR-015-10")
def test_without_the_bf16_reference_the_gate_is_not_run_and_every_q8_0_result_is_not_run() -> None:
    state = bf16.attempt_bf16(
        lambda: (_ for _ in ()).throw(RuntimeError("CUDA out of memory. Tried to allocate 3.1 GiB"))
    )
    rows = [
        _row("cosmos-q8_0", 1),
        _row("cosmos-q8_0", 3),
        _row("cosmos-q8_0", 1, reasoning=True),
        _row("cosmos-bf16", 1),
        _row("qwen-base", 1),
        _row("constant", 1),
    ]
    gate, out = bf16.degrade_for_missing_bf16(state, rows)
    assert gate["status"] == "not_run"
    assert (gate["agree"], gate["agreement"], gate["wilson95"], gate["q8_0_path"]) == (None, None, None, "not_run")
    assert gate["reason"]
    assert _errors(gate, "#/$defs/gate") == []
    assert len(out) == len(rows)
    for before, after in zip(rows, out, strict=True):
        if before["arm"] == "cosmos-q8_0":
            assert after["status"] == "not_run"
            assert "agreement gate not evaluable" in after["reason"]
        elif before["arm"] == "cosmos-bf16":
            assert after["status"] == "not_run"
            assert "out of memory" in after["reason"]
        else:
            assert after == before
            continue
        assert (after["arm"], after["type"], after["reasoning"]) == (before["arm"], before["type"], before["reasoning"])
        assert all(after[k] is None for k in ("balanced_accuracy", "f1", "auroc"))
        assert _errors(after, "#/$defs/row_a") == []


@pytest.mark.req("FR-015-10")
def test_with_the_bf16_reference_available_nothing_is_degraded() -> None:
    rows = [_row("cosmos-q8_0", 1), _row("cosmos-bf16", 1)]
    gate, out = bf16.degrade_for_missing_bf16({"status": "available", "model": object()}, rows)
    assert gate is None
    assert out == rows


@pytest.mark.req("FR-015-10")
def test_the_degraded_rows_survive_a_json_round_trip() -> None:
    state = {"status": "not_run", "reason": "RuntimeError: CUDA out of memory"}
    gate, out = bf16.degrade_for_missing_bf16(state, [_row("cosmos-q8_0", 2)])
    assert json.loads(json.dumps([gate, out])) == [gate, out]
