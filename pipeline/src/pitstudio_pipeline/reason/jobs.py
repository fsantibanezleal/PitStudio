"""The four `st59_*` stages as GPU queue jobs (spec 015, NFR-015-02).

    python -m pitstudio_pipeline.reason.jobs <stage> [--dry-run] [--out DIR]

Stages: `st59a_vqa` (task A: the Qwen3-VL control and the baselines first, the Cosmos arms when the weights exist),
`st59_reason_bench` (footprint bench, BF16 reference and the 500-query agreement gate: needs the Cosmos weights),
`st59b_plausibility` and `st59c_captions`.

Exit codes: 0 ok; 2 pin or provenance refusal; 3 BLOCKED, an input is missing (nothing is run, the reasons are printed);
4 no CUDA device; 5 the GPU is above the start temperature or the lock is taken; 6 the guard stopped the job.

A dry run runs on the CPU: it asserts CUDA, verifies the archives, and lists every missing input. A real run refuses
with exit code 3 before it touches the GPU when an input is missing; otherwise it takes the machine lock
`gpu0.compute`, refuses above 80 C and calls the in-run guard between queries; answers are cached in an append-only
file, so a stopped job resumes where it was.

Environment: `PITSTUDIO_DATA` (frames and runs, default `<data>/processed/...` as below), `PITSTUDIO_MODELS` (hub
snapshots, llama.cpp, GGUF files), `GPU_LOCK_DIR`, `HF_TOKEN` (optional: Cosmos only)."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitstudio.reason import captions, config, queries, stats, vqa
from pitstudio.reason.arms import constant_answer
from pitstudio.reason.frames import load_frame_state
from pitstudio_pipeline.download.hashing import sha256_file
from pitstudio_pipeline.reason import bf16, convert, hub, runtime
from pitstudio_pipeline.reason.jobobject import JobObject
from pitstudio_pipeline.reason.server import ServerDriver, error_rate, stage_failed

REPO = Path(__file__).resolve().parents[4]
STAGES = ("st59_reason_bench", "st59a_vqa", "st59b_plausibility", "st59c_captions")
EXIT_PIN, EXIT_BLOCKED, EXIT_NO_CUDA, EXIT_HOT = 2, 3, 4, 5
SEED = 20261015
MAX_START_C = 80
COSMOS_WAITING = "weights not available: licence acceptance pending"
LLAMA_ARCHIVE_DIR = ("hub", "github", "ggml-org", "llama.cpp", "b11381")


@dataclass(frozen=True)
class Paths:
    data: Path
    models: Path
    out: Path

    @property
    def archives(self) -> Path:
        return self.models.joinpath(*LLAMA_ARCHIVE_DIR)

    @property
    def runtime_dir(self) -> Path:
        return self.models / "llama.cpp" / "b11381"

    @property
    def converter(self) -> Path:
        return self.models / "llama.cpp" / "b11381-source" / "convert_hf_to_gguf.py"

    @property
    def frame_states(self) -> Path:
        return self.data / "processed" / "perception" / "frame_states"

    @property
    def image_root(self) -> Path:
        return self.data / "processed" / "perception"

    @property
    def detections(self) -> Path:
        return self.data / "processed" / "perception" / "detections"

    @property
    def pairs(self) -> Path:
        return self.data / "processed" / "reason" / "task_b" / "pairs.json"

    @property
    def granular_runs(self) -> Path:
        return self.data / "processed" / "physics" / "granular_runs"

    @property
    def renders(self) -> Path:
        return self.data / "processed" / "renders" / "st52_rtx_render"

    def snapshot(self, pins: Mapping[str, Any], which: str) -> Path:
        pin = pins["models"][which]
        org, name = pin["repository"].split("/")
        return self.models / "hub" / org / name / pin["revision"]


def paths_from_env(out: str | None, stage: str) -> Paths:
    try:
        data, models = Path(os.environ["PITSTUDIO_DATA"]), Path(os.environ["PITSTUDIO_MODELS"])
    except KeyError as exc:
        raise SystemExit(f"{stage}: set {exc.args[0]} (see the module docstring)") from None
    return Paths(data, models, Path(out) if out else data / "processed" / "reason" / stage)


# ---------------------------------------------------------------------------------------------------- inputs
def missing_inputs(stage: str, p: Paths, pins: Mapping[str, Any]) -> list[str]:
    """Why the stage cannot run: one line per missing input (empty: ready)."""
    missing: list[str] = []

    def need(path: Path, what: str, *, non_empty_dir: bool = False) -> None:
        ok = (path.is_dir() and any(path.iterdir())) if non_empty_dir else path.exists()
        if not ok:
            missing.append(f"{what}: {path} does not exist" + (" or is empty" if non_empty_dir else ""))

    for name in ("llama-b11381-bin-win-cuda-13.4-x64.zip", "cudart-llama-bin-win-cuda-13.4-x64.zip"):
        need(p.archives / name, "llama.cpp archive")
    need(p.archives / "llama.cpp-b11381-source.zip", "llama.cpp source archive (convert_hf_to_gguf.py)")
    needs_cosmos = stage == "st59_reason_bench"
    if stage == "st59a_vqa":
        need(p.frame_states, "spec 009 st55_sdg frame states (DC-015-01)", non_empty_dir=True)
        need(p.snapshot(pins, "qwen") / "model.safetensors", "Qwen3-VL-2B-Instruct snapshot")
    elif stage == "st59c_captions":
        need(p.frame_states, "spec 009 st55_sdg frame states and scene graphs", non_empty_dir=True)
        need(p.snapshot(pins, "qwen") / "model.safetensors", "Qwen3-VL-2B-Instruct snapshot")
    elif stage == "st59b_plausibility":
        need(p.granular_runs, "spec 005 granular runs", non_empty_dir=True)
        need(p.renders, "st52_rtx_render renders of the runs", non_empty_dir=True)
        need(p.pairs, "task-B pair index (DC-015-06) built from the runs")
        need(p.snapshot(pins, "qwen") / "model.safetensors", "Qwen3-VL-2B-Instruct snapshot")
    elif needs_cosmos:
        need(p.frame_states, "spec 009 st55_sdg frame states (the 500 gate queries come from them)", non_empty_dir=True)
    if needs_cosmos:
        need(p.snapshot(pins, "cosmos") / "model.safetensors", f"Cosmos-Reason2-2B snapshot ({COSMOS_WAITING})")
    return missing


def dry_run_path(stage: str, p: Paths) -> list[str]:
    """The CPU part of the real path, run by the dry run when every input is present: frame states are loaded and
    validated and (task A) the query set is built, so a data problem shows up before the GPU is taken."""
    lines: list[str] = []
    if stage in ("st59a_vqa", "st59c_captions", "st59_reason_bench"):
        frames = load_frames(p)
        lines.append(f"{len(frames)} frame states validated")
        if stage != "st59c_captions":
            build = queries.build_queries(frames, root=p.image_root, seed=SEED)
            lines.append(f"query set: {len(build.queries)} queries, shortfall per type {build.shortfall}")
            lines.append(f"rejected frames: {len(build.rejected)}")
    if stage == "st59b_plausibility":
        pairs = json.loads(p.pairs.read_text(encoding="utf-8"))["pairs"]
        lines.append(f"{len(pairs)} pairs in the index")
    return lines


def assert_cuda() -> str:
    """Name of CUDA device 0; SystemExit(4) when torch has no CUDA."""
    try:
        import torch

        if torch.cuda.is_available():
            return str(torch.cuda.get_device_name(0))
    except ImportError:
        pass
    raise SystemExit(EXIT_NO_CUDA)


# ----------------------------------------------------------------------------------------------- runtime setup
def _safe_extract(archive: Path, dest: Path, only: set[str] | None = None) -> None:
    root = dest.resolve()
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if target != root and root not in target.parents:
                raise runtime.PinError(archive.name, f"member {info.filename!r} leaves the target folder")
            if only is not None and Path(info.filename).name not in only:
                continue
            z.extract(info, dest)


def prepare_runtime(p: Paths, pins: Mapping[str, Any]) -> runtime.VerifiedRuntime:
    """Verify the archives, unpack them outside the repository, verify the executables and the converter script."""
    llama = pins["llamacpp"]
    for key in ("binaries", "cudart"):
        pin = llama["archives"][key]
        f = p.archives / pin["name"]
        if sha256_file(f) != pin["sha256"]:
            raise runtime.PinError(pin["name"], "SHA-256 differs from the pin")
        if not (p.runtime_dir / "llama-server.exe").is_file() or key == "cudart":
            _safe_extract(f, p.runtime_dir)
    src = p.archives / "llama.cpp-b11381-source.zip"
    if not p.converter.is_file():
        p.converter.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src) as z:
            names = [n for n in z.namelist() if n.endswith("/convert_hf_to_gguf.py") and n.count("/") == 1]
            if len(names) != 1:
                raise runtime.PinError("convert_hf_to_gguf.py", "not found once in the source archive")
            p.converter.write_bytes(z.read(names[0]))
        # the converter imports its sibling modules (gguf-py, conversion helpers) from the unpacked source tree
        with zipfile.ZipFile(src) as z:
            top = names[0].split("/")[0]
            for n in z.namelist():
                if n.startswith(f"{top}/gguf-py/") and not n.endswith("/"):
                    target = p.converter.parent / n[len(top) + 1 :]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(n))
    return runtime.verify_runtime(pins, archive_dir=p.archives, runtime_dir=p.runtime_dir, repo_root=REPO)


def _runner(argv: list[str]) -> int:
    env = {**os.environ, "PYTHONPATH": str(Path(argv[1]).parent / "gguf-py")} if len(argv) > 1 else None
    return subprocess.run(argv, env=env, check=False).returncode


def gguf_for(p: Paths, pins: Mapping[str, Any], rt: runtime.VerifiedRuntime, which: str) -> convert.ConversionResult:
    """Convert a verified snapshot to F16, mmproj and Q8_0 GGUF files under `<models>/gguf/<which>` (cached)."""
    out = p.models / "gguf" / which
    record = out / "conversion.json"
    if record.is_file():
        doc = json.loads(record.read_text(encoding="utf-8"))
        names = convert.STEMS
        paths = {k: out / v.format(which=which) for k, v in names.items()}
        if all(f.is_file() for f in paths.values()) and doc.get("revision") == pins["models"][which]["revision"]:
            return convert.ConversionResult(paths["f16"], paths["mmproj"], paths["q8_0"], {k: doc[k] for k in names})
    return convert.convert_model(
        p.snapshot(pins, which),
        out,
        runtime=rt,
        pins=pins,
        python=sys.executable,
        converter=p.converter,
        runner=_runner,
        repo_root=REPO,
        which=which,
    )


# ------------------------------------------------------------------------------------- cached, guarded driver
class CachedGuardedDriver:
    """Wraps a server driver: answers are cached by request hash in an append-only file (a stopped job resumes) and the
    GPU guard is called before every query that reaches the GPU."""

    def __init__(self, inner: ServerDriver, cache: Path, guard: Any) -> None:
        self.inner, self.guard = inner, guard
        self.cache = cache
        self.done: dict[str, dict[str, Any]] = {}
        if cache.is_file():
            for line in cache.read_text(encoding="utf-8").splitlines():
                with contextlib.suppress(ValueError, KeyError):  # a torn last line is ignored
                    row = json.loads(line)
                    self.done[row["key"]] = row
        cache.parent.mkdir(parents=True, exist_ok=True)
        self.handle = cache.open("a", encoding="utf-8")

    def ask(self, request: dict[str, Any]) -> Any:
        from pitstudio_pipeline.reason.server import QueryResult

        key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        if key in self.done:
            r = self.done[key]
            return QueryResult(r["status"], r["text"], r["top_logprobs"], r["attempts"], r.get("error"))
        if self.guard.check() == "cooldown":
            self.guard.cool_down()
        res = self.inner.ask(request)
        row = {
            "key": key,
            "status": res.status,
            "text": res.text,
            "top_logprobs": res.top_logprobs,
            "attempts": res.attempts,
            "error": res.error,
        }
        self.handle.write(json.dumps(row) + "\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.done[key] = row
        return res

    def close(self) -> None:
        self.handle.close()


@contextlib.contextmanager
def serving(p: Paths, pins: Mapping[str, Any], rt: runtime.VerifiedRuntime, which: str, guard: Any) -> Iterator[Any]:
    """A llama-server on the Q8_0 GGUF of `which` inside a job object, wrapped with the cache and the guard."""
    files = gguf_for(p, pins, rt, which)
    job = JobObject()
    driver = ServerDriver(
        [str(rt.executable("llama-server.exe"))],
        model=files.q8_0,
        mmproj=files.mmproj,
        job=job,
        extra_args=["--ctx-size", "16384", "-ngl", "99"],
    )
    wrapped = None
    try:
        driver.start()
        wrapped = CachedGuardedDriver(driver, p.out / f"{which}.answers.jsonl", guard)
        yield wrapped
    finally:
        if wrapped is not None:
            wrapped.close()
        driver.stop()
        job.close()


# ------------------------------------------------------------------------------------------------- stage bodies
def load_frames(p: Paths) -> list[dict[str, Any]]:
    return [load_frame_state(f, root=p.image_root) for f in sorted(p.frame_states.glob("*.json"))]


def body_vqa(p: Paths, pins: Mapping[str, Any], rt: runtime.VerifiedRuntime, guard: Any) -> int:
    """Task A: build the query set from the frame states, run the control and the baselines, Cosmos if available."""
    prompts = config.load_prompts(pins, REPO)
    frames = load_frames(p)
    build = queries.build_queries(frames, root=p.image_root, seed=SEED)
    p.out.mkdir(parents=True, exist_ok=True)
    doc = build.to_document()
    qpath = p.out / "queries.json"
    qpath.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (p.out / "queries.sha256").write_text(sha256_file(qpath) + "\n", encoding="utf-8")
    summary: dict[str, Any] = {
        "n_queries": len(build.queries),
        "shortfall_by_type": build.shortfall,
        "rejected_frames": len(build.rejected),
    }
    by_id = {f["frame_id"]: f for f in frames}
    states = hub.resolve_access(pins, env=os.environ, hub=hub.HfHub(os.environ.get("HF_TOKEN")), out_dir=p.out)
    summary["arms"] = {a: "planned" for a in hub.runnable_arms(states)}
    if states["cosmos"]["status"] != "available":
        summary["cosmos"] = {"status": "not_run", "reason": states["cosmos"].get("reason", COSMOS_WAITING)}
    errors: list[Any] = []
    with serving(p, pins, rt, "qwen", guard) as qwen:
        res = vqa.run_task_a(
            doc,
            by_id,
            driver=qwen,
            arm="qwen-base",
            prompts=prompts,
            out_dir=p.out / "qwen-base",
            source_path=qpath,
            repo_root=REPO,
            image_root=p.image_root,
        )
        summary["qwen-base"] = {"records": res["n_records"], "fixture": res["fixture"]}
        errors = list(qwen.done.values())
    summary["qwen_error_rate"] = error_rate(errors) if errors else None
    summary["stage_failed"] = stage_failed(errors) if errors else False
    const = [
        {
            "truth": q["truth"],
            "parsed": constant_answer(q["type"]),
            "condition": q["condition"],
            "type": q["type"],
        }
        for q in build.queries
    ]
    rows = []
    for t in sorted({r["type"] for r in const}):
        mine = [r for r in const if r["type"] == t]
        rows.append(stats.score_row(mine, arm="constant", qtype=t, seed=SEED))
    (p.out / "constant-rows.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    if p.detections.is_dir():
        summary["detector-rule"] = "inputs present: run the rule with the D-FINE detections of spec 009"
    else:
        summary["detector-rule"] = f"not_run: no detections in {p.detections}"
    (p.out / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n", encoding="utf-8")
    return 6 if summary["stage_failed"] else 0


def body_captions(p: Paths, pins: Mapping[str, Any], rt: runtime.VerifiedRuntime, guard: Any) -> int:
    """Task C: caption about 2,000 frames with the control, score against the scene graph, template baseline."""
    prompts = config.load_prompts(pins, REPO)
    vocab = captions.Vocabulary.from_file(REPO / "studio" / "reason" / "vocabulary.json")
    frames = load_frames(p)[:2000]
    p.out.mkdir(parents=True, exist_ok=True)
    records = []
    with serving(p, pins, rt, "qwen", guard) as qwen:
        for f in frames:
            req = vqa.build_request(prompts, {"type": 1}, f, image_root=p.image_root)
            req["messages"][1]["content"][1]["text"] = prompts["task_c_caption"]
            res = qwen.ask(req)
            if res.status == "ok":
                records.append({"caption": res.text or "", "frame": f})
    rows = [
        captions.score_captions(records, vocab, arm="qwen-base"),
        captions.score_captions(
            [{"caption": captions.template_caption(f, vocab), "frame": f} for f in frames],
            vocab,
            arm="template-caption",
        ),
    ]
    (p.out / "task_c_rows.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    return 0


def body_plausibility(p: Paths, pins: Mapping[str, Any], rt: runtime.VerifiedRuntime, guard: Any) -> int:
    """Task B with the control: both orders and single clips per pair; frames are the pre-extracted 4 fps PNG lists of
    each clip (`<clip folder>/frames/*.png`, written by the render stage)."""
    from pitstudio.reason import taskb

    prompts = config.load_prompts(pins, REPO)
    pairs = json.loads(p.pairs.read_text(encoding="utf-8"))["pairs"]
    p.out.mkdir(parents=True, exist_ok=True)
    recs = []
    with serving(p, pins, rt, "qwen", guard) as qwen:
        for pair in pairs:
            plan = taskb.request_plan(pair, arm="qwen-base")
            answers = {}
            for item in plan[:2]:
                content: list[dict[str, Any]] = []
                for clip_id in item["clips"]:
                    for idx in item["frames"][clip_id]:
                        png = p.renders / clip_id / "frames" / f"{idx:05d}.png"
                        content.append({"type": "image_url", "image_url": {"url": str(png)}})
                content.append({"type": "text", "text": prompts[item["prompt"]]})
                req = {
                    "messages": [{"role": "system", "content": prompts["system"]}, {"role": "user", "content": content}]
                }
                res = qwen.ask(req)
                from pitstudio.reason.parse import parse_answer

                answers[item["presentation"]] = parse_answer(res.text or "", reasoning=False)
            recs.append({"pair_id": pair["pair_id"], "corruption": pair["corruptions"][0], "answers": answers})
    row = taskb.score_task_b(recs, arm="qwen-base", input_mode="frame-list-approximation")
    (p.out / "task_b_rows.json").write_text(json.dumps([row], indent=1) + "\n", encoding="utf-8")
    return 0


def body_bench(p: Paths, pins: Mapping[str, Any], rt: runtime.VerifiedRuntime, guard: Any) -> int:
    """Footprint bench and agreement gate: needs the Cosmos weights (BF16 reference and Q8_0 conversion)."""
    from pitstudio.reason import bench

    gpu_name = assert_cuda()
    p.out.mkdir(parents=True, exist_ok=True)
    state = bf16.attempt_bf16(lambda: bf16.load_reference(str(p.snapshot(pins, "cosmos")), pins))
    gate, _ = bf16.degrade_for_missing_bf16(state, [])
    result = {"gpu": gpu_name, "bf16": {k: v for k, v in state.items() if k != "model"}, "gate": gate}
    if gate is None:
        result["note"] = "BF16 loaded; the timed bench and the 500-query comparison run from the reference harness"
    result["bench"] = bench.not_run_bench("bench harness not run in this invocation")
    (p.out / "bench.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return 0


BODIES = {
    "st59a_vqa": body_vqa,
    "st59c_captions": body_captions,
    "st59b_plausibility": body_plausibility,
    "st59_reason_bench": body_bench,
}


# ------------------------------------------------------------------------------------------------------- main
def _guard() -> Any:
    sys.path.insert(0, str(REPO / "studio" / "bench"))
    from gpu_guard import Guard  # type: ignore[import-not-found]

    return Guard()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pitstudio_pipeline.reason.jobs")
    ap.add_argument("stage", choices=STAGES)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    p = paths_from_env(args.out, args.stage)
    try:
        pins = runtime.load_pins(REPO / "studio" / "reason" / "pins.json")
        config.verify_prompt_hashes(pins, REPO)
    except (runtime.PinError, config.PromptHashMismatch) as err:
        print(f"{args.stage}: refused: {err}", file=sys.stderr)
        return EXIT_PIN
    device = assert_cuda()
    print(f"{args.stage}: CUDA device 0 is {device}")
    missing = missing_inputs(args.stage, p, pins)
    if args.dry_run:
        print(f"{args.stage}: dry run: pins and prompts verified")
        if not missing:
            for key in ("binaries", "cudart"):
                pin = pins["llamacpp"]["archives"][key]
                ok = sha256_file(p.archives / pin["name"]) == pin["sha256"]
                print(f"{args.stage}: archive {pin['name']}: {'matches its pin' if ok else 'DIFFERS FROM ITS PIN'}")
                if not ok:
                    return EXIT_PIN
    if missing:
        print(f"{args.stage}: BLOCKED, {len(missing)} input(s) missing:", file=sys.stderr)
        for line in missing:
            print(f"  - {line}", file=sys.stderr)
        return EXIT_BLOCKED
    if args.dry_run:
        for line in dry_run_path(args.stage, p):
            print(f"{args.stage}: {line}")
        print(f"{args.stage}: dry run ok, every input is present")
        return 0
    from filelock import FileLock, Timeout

    lock_dir = Path(os.environ.get("GPU_LOCK_DIR") or Path(os.environ.get("TEMP", ".")) / "gpu-locks")
    lock_dir.mkdir(parents=True, exist_ok=True)
    guard = _guard()
    if guard.read_temp() >= MAX_START_C:
        print(f"{args.stage}: GPU at {guard.read_temp()} C, above the start limit {MAX_START_C} C", file=sys.stderr)
        return EXIT_HOT
    try:
        with FileLock(lock_dir / "gpu0.compute", timeout=60):
            rt = prepare_runtime(p, pins)
            return BODIES[args.stage](p, pins, rt, guard)
    except Timeout:
        print(f"{args.stage}: the machine GPU lock gpu0.compute is taken", file=sys.stderr)
        return EXIT_HOT
    except (runtime.PinError, hub.ProvenanceError, convert.ConversionError) as err:
        print(f"{args.stage}: refused: {err}", file=sys.stderr)
        return EXIT_PIN


if __name__ == "__main__":
    raise SystemExit(main())
