# ruff: noqa: E501, PT018
"""T-002-041: the stage-side helper `pitstudio_stagekit` (standard library only).

Requirement: FR-002-26.

Expected API (module file `src/pitstudio/runner/stagekit/pitstudio_stagekit.py`, importable as `pitstudio_stagekit`
when that folder is on PYTHONPATH; stated for the implementer):
  * `main(stage_fn, argv=None) -> int`: parses `--job <path>` (default `sys.argv[1:]`), reads the job spec, opens an NVTX
    range named by the environment variable PITSTUDIO_NVTX_RANGE when an `nvtx` module is importable (closing it when
    the stage function returns or raises), calls `torch.cuda.set_per_process_memory_fraction(float(PITSTUDIO_VRAM_FRACTION))`
    before the stage function when PITSTUDIO_VRAM_FRACTION is set and `torch` is importable with `torch.cuda.is_available()`,
    calls `stage_fn(job: dict) -> dict | None` (a returned dict may hold `outputs`, `observables`, `throughput`,
    `checkpoint`, `message`), and ALWAYS writes `<job output_dir>/result.json` (valid against
    contracts/job.schema.json#/$defs/stage_result): a normal return is `succeeded` (exit code 0); an exception is
    `failed` with `error_class: unknown` (exit code 1) and a `message` of 1..300 characters; an exception that is a CUDA
    out-of-memory error (class named `OutOfMemoryError`, or a message containing `CUDA out of memory`) is
    `error_class: oom`;
  * an `nvtx` or `torch` that cannot be imported (missing, or raising on import) never breaks the stage;
  * the module imports only the standard library at module level and is valid Python 3.12 syntax.
Oracles: the stage-result schema (Python `jsonschema`), recording fake `nvtx` and `torch` modules put on the child's
PYTHONPATH, `ast` for the import rule, `python -I -S` for a clean-interpreter import.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
import schemas

KIT_DIR = rw.ROOT / "src" / "pitstudio" / "runner" / "stagekit"
KIT_FILE = KIT_DIR / "pitstudio_stagekit.py"
RUN_ID = "20261004T120000Z-kit"


# ---- the import rule ---------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-26")
def test_fr_002_26_module_imports_only_the_standard_library_and_is_python_312_syntax() -> None:
    assert KIT_FILE.is_file(), "src/pitstudio/runner/stagekit/pitstudio_stagekit.py does not exist"
    tree = ast.parse(KIT_FILE.read_text(encoding="utf-8"), feature_version=(3, 12))
    stdlib = set(sys.stdlib_module_names)
    for node in tree.body:  # module level: unconditional imports must be standard library
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative imports"
            names = [(node.module or "").split(".")[0]]
        else:
            continue
        assert set(names) <= stdlib | {"__future__"}, f"module-level import of a non-standard-library module: {names}"
    optional = {"nvtx", "torch"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            top = (
                (node.module or "").split(".")[0]
                if isinstance(node, ast.ImportFrom)
                else node.names[0].name.split(".")[0]
            )
            assert top in stdlib | optional | {"__future__"}, f"imports {top}"


@pytest.mark.req("FR-002-26")
def test_fr_002_26_module_imports_in_an_isolated_interpreter_with_no_site_packages() -> None:
    assert KIT_FILE.is_file()
    code = f"import sys; sys.path.insert(0, {str(KIT_DIR)!r}); import pitstudio_stagekit as k; print(callable(k.main))"
    r = subprocess.run([sys.executable, "-I", "-S", "-c", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "True", r.stderr


# ---- running a stage through the helper ----------------------------------------------------------------------------------------
NVTX = """
import os, json
def _log(kind, msg=None):
    with open(os.environ["PS_KIT_LOG"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"mod": "nvtx", "call": kind, "msg": msg}) + "\\n")
def start_range(message=None, color=None, domain=None, category=None):
    _log("open", message); return 7
def end_range(range_id=None):
    _log("close")
def push_range(message=None, color=None, domain=None, category=None):
    _log("open", message)
def pop_range(domain=None):
    _log("close")
class annotate:
    def __init__(self, message=None, color=None, domain=None, category=None): self.message = message
    def __enter__(self): _log("open", self.message); return self
    def __exit__(self, *a): _log("close"); return False
    def __call__(self, fn):
        def wrapper(*a, **k):
            with self: return fn(*a, **k)
        return wrapper
"""
TORCH_INIT = """
from . import cuda
"""
TORCH_CUDA = """
import os, json
class OutOfMemoryError(RuntimeError):
    pass
def is_available():
    return os.environ.get("PS_KIT_CUDA", "1") == "1"
def set_per_process_memory_fraction(fraction, device=None):
    with open(os.environ["PS_KIT_LOG"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"mod": "torch", "call": "fraction", "value": fraction, "device": device}) + "\\n")
"""
BROKEN_TORCH = "raise OSError('CUDA runtime is broken on this machine')\n"
STAGE_SCRIPT = """
import json, os, sys
import pitstudio_stagekit as kit

def log(kind):
    with open(os.environ["PS_KIT_LOG"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"mod": "stage", "call": kind}) + "\\n")

def stage(job):
    log("stage")
    how = os.environ.get("PS_KIT_HOW", "ok")
    if how == "ok":
        out = os.path.join(job["output_dir"], "result.bin")
        open(out, "wb").write(b"payload")
        return {"outputs": [{"path": "result.bin"}], "observables": {"x": 1.5}, "throughput": {"value": 12.5, "unit": "items/s"}, "checkpoint": True}
    if how == "none":
        return None
    if how == "raise":
        raise ValueError(os.environ.get("PS_KIT_MSG", "boom"))
    if how == "oom-class":
        import torch
        raise torch.cuda.OutOfMemoryError("allocation failed")
    if how == "oom-message":
        raise RuntimeError("CUDA out of memory. Tried to allocate 20.00 GiB (GPU 0; 15.99 GiB total capacity)")
    raise SystemExit(9)

sys.exit(kit.main(stage))
"""


def write_job(tmp: Path) -> tuple[Path, Path]:
    out = tmp / "runs" / RUN_ID / "tmp" / "s10_preprocess" / "0"
    out.mkdir(parents=True)
    job = {
        "schema_version": "1.0", "run_id": RUN_ID, "stage": {"id": "s10_preprocess"}, "entry": "ps_kit_stage", "params": {}, "seed": 5,
        "shard": None, "inputs": [], "output_dir": out.as_posix(), "scratch_dir": (tmp / "scratch").as_posix(), "resume": False,
        "rerun": False, "profiling": False, "profile": {"id": "p", "cpu_slots": 1}, "vram_fraction": None, "nvtx_range": "pitstudio:s10_preprocess:0",
    }  # fmt: skip
    (tmp / "scratch").mkdir()
    path = out / "job.json"
    path.write_text(json.dumps(job), encoding="utf-8")
    assert schemas.errors("job", job, "#/$defs/job_spec") == [], "test fixture job spec must itself be valid"
    return path, out


def run_stage(
    tmp: Path,
    *,
    how: str = "ok",
    nvtx: str | None = NVTX,
    torch: str | None = "ok",
    env: dict[str, str] | None = None,
    extra_argv: list[str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, list[dict[str, Any]]]:
    mods = tmp / "mods"
    mods.mkdir()
    absent = (
        "raise ModuleNotFoundError(\"No module named '{}'\")\n"  # a blocker: the real package must never be imported
    )
    (mods / "nvtx.py").write_text(nvtx if nvtx is not None else absent.format("nvtx"), encoding="utf-8")
    if torch is not None:
        (mods / "torch").mkdir()
        (mods / "torch" / "__init__.py").write_text(TORCH_INIT if torch == "ok" else BROKEN_TORCH, encoding="utf-8")
        (mods / "torch" / "cuda.py").write_text(TORCH_CUDA, encoding="utf-8")
    else:
        (mods / "torch.py").write_text(absent.format("torch"), encoding="utf-8")
    script = tmp / "stage_script.py"
    script.write_text(STAGE_SCRIPT, encoding="utf-8")
    job, out = write_job(tmp)
    log = tmp / "kit.log"
    e = {k: v for k, v in os.environ.items() if k != "PITSTUDIO_VRAM_FRACTION"}
    e.update(
        {
            "PYTHONPATH": os.pathsep.join([str(KIT_DIR), str(mods)]),
            "PS_KIT_LOG": str(log),
            "PS_KIT_HOW": how,
            "PITSTUDIO_NVTX_RANGE": "pitstudio:s10_preprocess:0",
            **(env or {}),
        }
    )
    argv = [sys.executable, str(script), *(extra_argv if extra_argv is not None else ["--job", str(job)])]
    r = subprocess.run(argv, capture_output=True, text=True, env=e, timeout=60, cwd=str(tmp))
    assert "No module named 'pitstudio_stagekit'" not in r.stderr, (
        f"the stage helper does not exist yet: {r.stderr[-300:]}"
    )
    rows = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return r, out, rows


def result(out: Path) -> dict[str, Any]:
    doc = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert schemas.errors("job", doc, "#/$defs/stage_result") == [], doc
    return doc


@pytest.mark.req("FR-002-26")
def test_fr_002_26_success_writes_a_valid_result_and_wraps_the_stage_in_an_nvtx_range(tmp_path: Path) -> None:
    r, out, rows = run_stage(tmp_path, env={"PITSTUDIO_VRAM_FRACTION": "0.25"})
    assert r.returncode == 0, r.stderr
    doc = result(out)
    assert doc["status"] == "succeeded" and doc["error_class"] is None
    assert doc["outputs"] == [{"path": "result.bin"}] and doc["observables"] == {"x": 1.5}
    assert doc["throughput"] == {"value": 12.5, "unit": "items/s"} and doc["checkpoint"] is True
    kinds = [(x["mod"], x["call"]) for x in rows]
    opened = next(i for i, x in enumerate(rows) if x["mod"] == "nvtx" and x["call"] == "open")
    assert rows[opened]["msg"] == "pitstudio:s10_preprocess:0"
    stage_at = kinds.index(("stage", "stage"))
    closed = max(i for i, x in enumerate(rows) if x["mod"] == "nvtx" and x["call"] == "close")
    assert opened < stage_at < closed, f"NVTX range must wrap the stage function: {kinds}"


@pytest.mark.req("FR-002-26")
def test_fr_002_26_vram_fraction_is_applied_before_the_stage_when_torch_has_cuda(tmp_path: Path) -> None:
    r, _out, rows = run_stage(tmp_path, env={"PITSTUDIO_VRAM_FRACTION": "0.25"})
    assert r.returncode == 0, r.stderr
    kinds = [(x["mod"], x["call"]) for x in rows]
    assert ("torch", "fraction") in kinds
    assert next(x for x in rows if x["mod"] == "torch")["value"] == 0.25
    assert kinds.index(("torch", "fraction")) < kinds.index(("stage", "stage"))


@pytest.mark.req("FR-002-26")
@pytest.mark.parametrize(
    ("label", "kwargs", "env"),
    [
        ("no-fraction-variable", {}, {}),
        ("torch-without-cuda", {}, {"PITSTUDIO_VRAM_FRACTION": "0.5", "PS_KIT_CUDA": "0"}),
        ("torch-missing", {"torch": None}, {"PITSTUDIO_VRAM_FRACTION": "0.5"}),
    ],
)
def test_fr_002_26_no_memory_cap_without_a_fraction_or_a_cuda_torch(
    tmp_path: Path, label: str, kwargs: dict[str, Any], env: dict[str, str]
) -> None:
    r, out, rows = run_stage(tmp_path, env=env, **kwargs)
    assert r.returncode == 0, r.stderr
    assert not [x for x in rows if x["mod"] == "torch"], label
    assert result(out)["status"] == "succeeded"


@pytest.mark.req("FR-002-26")
@pytest.mark.parametrize(
    ("label", "kwargs"), [("nvtx-missing", {"nvtx": None}), ("torch-raises-on-import", {"torch": "broken"})]
)
def test_fr_002_26_missing_or_broken_optional_modules_never_break_the_stage(
    tmp_path: Path, label: str, kwargs: dict[str, Any]
) -> None:
    r, out, rows = run_stage(tmp_path, env={"PITSTUDIO_VRAM_FRACTION": "0.5"}, **kwargs)
    assert r.returncode == 0, f"{label}: {r.stderr}"
    assert result(out)["status"] == "succeeded"
    assert ("stage", "stage") in [(x["mod"], x["call"]) for x in rows]


@pytest.mark.req("FR-002-26")
def test_fr_002_26_an_exception_becomes_a_failed_result_with_a_bounded_message(tmp_path: Path) -> None:
    r, out, rows = run_stage(tmp_path, how="raise", env={"PS_KIT_MSG": "boom: bad input"})
    assert r.returncode == 1, r.stderr
    doc = result(out)
    assert (doc["status"], doc["error_class"]) == ("failed", "unknown")
    assert "boom: bad input" in doc["message"] and doc["outputs"] == []
    assert any(x["mod"] == "nvtx" and x["call"] == "close" for x in rows), "the NVTX range is closed on the error path"


@pytest.mark.req("FR-002-26")
@pytest.mark.parametrize(
    "msg",
    ["x" * 10_000, "line one\nline two é中", "\u0001\u0002\u007f", "A" * 301],
    ids=["huge", "multiline-unicode", "control-chars", "301-chars"],
)
def test_fr_002_26_hostile_exception_texts_still_give_a_schema_valid_result(tmp_path: Path, msg: str) -> None:
    r, out, _ = run_stage(tmp_path, how="raise", env={"PS_KIT_MSG": msg})
    assert r.returncode == 1, r.stderr
    doc = result(out)
    assert 1 <= len(doc["message"]) <= 300


@pytest.mark.req("FR-002-26")
def test_fr_002_26_an_exception_without_a_message_still_names_itself(tmp_path: Path) -> None:
    r, out, _ = run_stage(tmp_path, how="raise", env={"PS_KIT_MSG": ""})
    assert r.returncode == 1
    doc = result(out)
    assert "ValueError" in doc["message"]


@pytest.mark.req("FR-002-26")
@pytest.mark.parametrize("how", ["oom-class", "oom-message"])
def test_fr_002_26_a_cuda_out_of_memory_exception_is_error_class_oom(tmp_path: Path, how: str) -> None:
    r, out, _ = run_stage(tmp_path, how=how)
    assert r.returncode == 1, r.stderr
    doc = result(out)
    assert (doc["status"], doc["error_class"]) == ("failed", "oom")


@pytest.mark.req("FR-002-26")
def test_fr_002_26_returning_nothing_is_a_success_without_outputs(tmp_path: Path) -> None:
    r, out, _ = run_stage(tmp_path, how="none")
    assert r.returncode == 0, r.stderr
    doc = result(out)
    assert (doc["status"], doc["outputs"], doc["checkpoint"]) == ("succeeded", [], False)


@pytest.mark.req("FR-002-26")
@pytest.mark.parametrize(
    "argv",
    [[], ["--job"], ["--job", "/no/such/job.json"], ["--nonsense"]],
    ids=["no-args", "no-value", "missing-file", "unknown-option"],
)
def test_fr_002_26_bad_command_lines_exit_nonzero_without_a_stage_run(tmp_path: Path, argv: list[str]) -> None:
    r, _out, rows = run_stage(tmp_path, extra_argv=argv)
    assert r.returncode != 0
    assert ("stage", "stage") not in [(x["mod"], x["call"]) for x in rows]
