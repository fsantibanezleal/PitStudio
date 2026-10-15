# ruff: noqa: E501
"""Test support for spec 002 (runner) and spec 003 (console): a throw-away repository, store, lock folder, fake GPU
device and fake stages, plus helpers to run the command line and read what it wrote.

Nothing here implements behaviour of the code under test. It only builds inputs and reads outputs, using the
documented layouts (specs/002-runner/plan.md D3, D5, D6) and the standard library, PyYAML and `jsonschema`.

Assumed process-level contract (stated in every test file that depends on it, and in the red-phase report):
  * the command line is `pitstudio.runner.cli.main(argv: list[str]) -> int` (argv WITHOUT the program name; a usage
    error may be returned as 2 or raised as SystemExit(2)); the same entry runs as `python -m pitstudio.runner`;
  * environment variables: PITSTUDIO_REPO (repository root override, default: the checkout containing the package),
    PITSTUDIO_STORE, GPU_LOCK_DIR, PITSTUDIO_GPU_BACKEND=fake:<device file>, PYTHONPATH (inherited by stages);
  * with the fake backend the runner launches stages as `[sys.executable, "-m", <entry>, "--job", <job.json>]`
    (the "test launcher", FR-002-56) with the parent environment plus the PITSTUDIO_* variables of FR-002-24;
  * a stage writes `result.json` next to `job.json` in `output_dir` (`runs/<run_id>/tmp/<stage key>/<shard>/`);
  * the runner reads free disk space through `shutil.disk_usage(path)` and starts processes with
    `subprocess.Popen(...)` (module attribute lookups, so that tests can spy on them).
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections import namedtuple
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SUPPORT = Path(__file__).resolve().parent
SRC = ROOT / "src"
IS_WINDOWS = sys.platform == "win32"
GIB = 2**30

STAGE_ENV = {
    "s00_download": "pipeline", "s05_synthesize": "pipeline", "s10_preprocess": "pipeline",
    "s20_feature_extraction": "pipeline", "s30_train": "pipeline", "s40_infer": "pipeline", "s50_evaluate": "pipeline",
    "s60_export": "pipeline", "s62_accel": "accel", "s64_bench": "accel",
    "st10_terrain": "studio", "st20_pit_design": "studio", "st30_assets": "studio", "st40_compose": "studio",
    "st45_validate": "studio", "st50_physics": "studio", "st56_encode": "studio",
    "st52_rtx_render": "isaac", "st54_vehicles": "isaac", "st55_sdg": "isaac", "st57_rain_lidar": "isaac",
    "st53_sensors": "rtx", "st45b_kit_validate": "kit", "st58_kit_capture": "kit", "st58b_capture_splat": "external",
    "st59_reason_bench": "reason", "st59a_vqa": "reason", "st59b_plausibility": "reason", "st59c_captions": "reason",
    "st60_il_train": "isaaclab", "st61_il_mpm_eval": "isaaclab",
}  # fmt: skip
# plan.md D7: launch project, lock file and code roots per environment
ENV_PROJECT = {
    "studio": "studio", "isaac": "studio/isaac", "rtx": "studio/rtx", "isaaclab": "studio/isaaclab",
    "pipeline": "pipeline", "accel": "pipeline/accel", "kit": "studio", "reason": "studio", "external": "studio",
}  # fmt: skip
ENV_LOCK_ROOT = {
    "studio": "studio", "isaac": "studio/isaac", "rtx": "studio/rtx", "isaaclab": "studio/isaaclab",
    "pipeline": "pipeline", "accel": "pipeline/accel", "kit": "studio", "reason": "studio", "external": "studio",
}  # fmt: skip
ENV_CODE_ROOTS = {
    "studio": ["studio/src"], "isaac": ["studio/isaac/src"], "rtx": ["studio/rtx/src"],
    "isaaclab": ["studio/isaaclab/src"], "pipeline": ["pipeline/src"], "accel": ["pipeline/accel/src"],
    "kit": ["studio/src", "studio/kit"], "reason": ["studio/src", "studio/reason"], "external": ["studio/src"],
}  # fmt: skip
ALL_ENVS = ["studio", "isaac", "rtx", "isaaclab", "kit", "reason", "pipeline", "accel", "external"]
DEFAULT_TOOL = {
    "pipeline": "pitstudio", "accel": "pitstudio", "studio": "warp", "isaac": "isaac-sim-replicator", "rtx": "ovrtx",
    "isaaclab": "pitstudio", "kit": "pitstudio", "reason": "pitstudio", "external": "pitstudio",
}  # fmt: skip
DRIVER = "580.95.05"
Usage = namedtuple("Usage", "total used free")
_REAL_DISK_USAGE = shutil.disk_usage


# ----------------------------------------------------------------------------------------------------------------
# documents
# ----------------------------------------------------------------------------------------------------------------
def stage(
    id_: str,
    *,
    gpu: str = "none",
    vram: float | None = None,
    params: dict[str, Any] | None = None,
    files: tuple[str, ...] | list[str] = ("out.bin",),
    inputs: list[dict[str, Any]] | None = None,
    variant: str | None = None,
    timeout_s: int = 30,
    determinism: Any = "bitwise",
    requires: list[str] | None = None,
    retry: list[dict[str, Any]] | None = None,
    shardable: tuple[int, int] | None = None,
    tool: str | None = None,
    validator: str = "file",
    publish: bool = False,
    binaries: list[dict[str, str]] | None = None,
    disk: float = 0.001,
    entry: str = "ps_fake_stages.generic",
    env: str | None = None,
    outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A valid recipe stage (spec 001 data-model 3.2) running the fake stage program."""
    env = env or STAGE_ENV[id_]
    resources: dict[str, Any] = {"gpu": gpu, "disk_gib_est": disk, "cpu": 1}
    if gpu == "exclusive":
        resources["vram_gib_est"] = 1.0 if vram is None else vram
    elif vram is not None and gpu != "none":
        resources["vram_gib_est"] = vram
    doc: dict[str, Any] = {
        "id": id_, "env": env, "tool": tool or DEFAULT_TOOL[env], "entry": entry,
        "inputs": inputs or [],
        "params": {"mode": "ok", "files": list(files), **(params or {})},
        "resources": resources, "determinism": determinism, "timeout_s": timeout_s,
        "outputs": outputs or [{"path": f, "schema": validator, "publish": publish} for f in files],
    }  # fmt: skip
    if variant:
        doc["variant"] = variant
    if requires:
        doc["requires"] = requires
    if retry:
        doc["retry"] = {"oom_fallback": retry}
    if shardable:
        doc["shardable"] = {"shard_size": shardable[0], "total": shardable[1]}
    if binaries:
        doc["binaries"] = binaries
    return doc


def recipe(id_: str, stages: list[dict[str, Any]], *, seed: int = 20261004, case: str = "bench") -> dict[str, Any]:
    return {"id": id_, "case": case, "seed": seed, "description": "test recipe", "stages": stages}


def up(stage_id: str, output: str | None = None, variant: str | None = None) -> dict[str, Any]:
    """An input naming an upstream stage output."""
    d: dict[str, Any] = {"stage": stage_id}
    if variant:
        d["variant"] = variant
    if output:
        d["output"] = output
    return d


def profile_doc(**over: Any) -> dict[str, Any]:
    """A valid machine profile for the host OS (plan.md D4); `over` replaces top-level keys."""
    win = IS_WINDOWS
    doc: dict[str, Any] = {
        "id": "test-profile",
        "os": "windows" if win else "linux",
        "gpus": [{"index": 0, "vram_bytes": 48 * GIB, "power_class": "server"}],
        "store_default": "C:/ps" if win else "/srv/ps",
        "cpu_slots": 4,
        "envs_enabled": list(ALL_ENVS),
        "process_control": "job-object" if win else "process-group",
        "guards": {"vram_margin_gib": 1.5, "disk_margin_gib": 20, "max_start_temp_c": 80, "cooldown_wait_s": 20, "lock_wait_s": 2},
        "telemetry_hz": 4,
        "keep_awake": False,
    }  # fmt: skip
    doc.update(over)
    return doc


def device_doc(**series: Any) -> dict[str, Any]:
    """A valid fake device (profile.schema.json#/$defs/fake_device); `series` replaces whole series entries."""
    base: dict[str, Any] = {
        "free_bytes": 45 * GIB, "temp_c": 45, "power_w": 100, "power_limit_w": 300, "util_pct": 50,
        "sm_clock_mhz": 1980, "clocks_event_mask": 0, "energy_mj_per_s": 100000, "nvenc_util_pct": 10, "pcie_replays": 0,
    }  # fmt: skip
    base.update(series)
    return {
        "name": "Fake GPU 48GB",
        "driver": DRIVER,
        "vram_total_bytes": 48 * GIB,
        "init_error": False,
        "series": base,
    }


def tools_doc() -> dict[str, Any]:
    def tool(
        id_: str,
        env: str,
        pkg: str | None,
        lock: str,
        spdx: str,
        perf: str,
        lane: str,
        klass: str,
        cat: str = "studio-tool",
    ) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": id_, "name": id_, "category": cat, "envs": [env],
            "version": {"from_lock": lock, "package": pkg} if pkg else {"own": True},
            "spdx": [spdx], "osi": spdx == "Apache-2.0", "licence_class": klass, "ring": "Adopt", "lane": lane,
            "performance": perf, "role": f"test tool {id_}", "cases": [], "produces": ["table"],
            "status": "not-yet-run",
        }  # fmt: skip
        if cat == "studio-tool":
            d["docs_page"] = f"docs/frameworks/{id_}.md"
        return d

    return {
        "tools": [
            tool("pitstudio", "root", None, "uv.lock", "Apache-2.0", "public", "live", "own", cat="component"),
            tool("warp", "studio", "warp-lang", "studio/uv.lock", "Apache-2.0", "public", "replay", "attribution"),
            tool("nvenc-ffmpeg", "studio", "av", "studio/uv.lock", "LGPL-2.1-or-later", "public", "replay", "attribution"),
            tool("ovrtx", "rtx", "ovrtx", "studio/rtx/uv.lock", "LicenseRef-NvidiaProprietary", "local-only", "local-only", "reference-only"),
            tool("isaac-sim-replicator", "isaac", "isaacsim", "studio/isaac/uv.lock", "LicenseRef-NVIDIA-SLA", "local-only", "local-only", "reference-only"),
        ]
    }  # fmt: skip


LOCK_PACKAGES = {
    "studio": [("warp-lang", "1.17.0"), ("av", "14.0.1"), ("pydantic", "2.13.5")],
    "studio/isaac": [("isaacsim", "6.0.0")],
    "studio/rtx": [("ovrtx", "0.5.0")],
    "studio/isaaclab": [("isaaclab", "3.0.0")],
    "pipeline": [("torch", "2.14.1+cu130"), ("numpy", "2.5.3")],
    "pipeline/accel": [("tensorrt", "10.14.0")],
}


def uv_lock_text(root: str, extra: int = 0) -> str:
    pkgs = LOCK_PACKAGES.get(root, [("pydantic", "2.13.5")])
    body = "".join(f'[[package]]\nname = "{n}"\nversion = "{v}"\n\n' for n, v in pkgs)
    return f'version = 1\nrequires-python = "==3.14.*"\n# fixture {root} {extra}\n\n{body}'


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def capabilities_doc(driver: str = DRIVER, probes: dict[str, Any] | None = None) -> dict[str, Any]:
    probes = probes or {
        "warp_newton": {
            "status": "pass",
            "versions": {"python": "3.14.4", "warp": "1.17.0"},
            "metrics": {"saxpy_16M_x20_s": 0.0123},
        },
        "nvenc": {"status": "pass", "versions": {"python": "3.14.4"}, "metrics": {"encode_fps": 240.0}},
    }
    return {"generated": "2026-10-11", "gpu": "Fake GPU 48GB", "driver": driver, "probes": probes}


RUN_BENCH_STUB = '''"""Stub of studio/bench/run_bench.py for runner tests: the names the runner reads (PROBES, OPT_IN, main)."""
import json, os
PROBES = {"warp_newton": ("studio", []), "nvenc": ("studio", []), "tensorrt": ("pipeline/accel", [])}
OPT_IN = set()

def main(argv):
    rec = os.environ.get("PS_BENCH_ARGV_FILE")
    if rec:
        with open(rec, "w", encoding="utf-8") as fh:
            json.dump(list(argv), fh)
    return int(os.environ.get("PS_BENCH_EXIT", "0"))
'''


# ----------------------------------------------------------------------------------------------------------------
# the world
# ----------------------------------------------------------------------------------------------------------------
@dataclass
class World:
    repo: Path
    store: Path
    lock_dir: Path
    device_file: Path
    ledger: Path
    base: Path
    profile_id: str = "test-profile"
    disk_free: int = 4096 * GIB
    recipes: dict[str, Path] = field(default_factory=dict)
    monkeypatch: Any = None

    # --- writing inputs -------------------------------------------------------------------------------------
    def write_recipe(self, doc: dict[str, Any], folder: str = "cases") -> Path:
        d = self.repo / "studio" / "recipes" / folder
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{doc['id']}.yaml"
        p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        self.recipes[doc["id"]] = p
        return p

    def write_profile(self, doc: dict[str, Any] | None = None, **over: Any) -> Path:
        d = self.repo / "studio" / "recipes" / "_profiles"
        d.mkdir(parents=True, exist_ok=True)
        doc = {**(doc or profile_doc()), **over}
        p = d / f"{doc['id']}.yaml"
        p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        return p

    def write_device(self, doc: dict[str, Any] | None = None, **series: Any) -> Path:
        doc = doc or device_doc(**series)
        self.device_file.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        return self.device_file

    def set_guards(self, **guards: Any) -> None:
        prof = profile_doc()
        prof["guards"] = {**prof["guards"], **guards}
        self.write_profile(prof)

    def hold(self, text: str = "maintenance") -> Path:
        p = self.lock_dir / "gpu0.hold"
        p.write_text(text, encoding="utf-8")
        return p

    def release_hold(self) -> None:
        p = self.lock_dir / "gpu0.hold"
        if p.is_dir() or p.is_symlink():
            shutil.rmtree(p, ignore_errors=True)
        with contextlib.suppress(FileNotFoundError):
            p.unlink()

    def commit(self) -> str:
        git(self.repo, "add", "-A")
        git(
            self.repo,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "fixture",
        )
        return git(self.repo, "rev-parse", "HEAD").strip()

    def set_free_disk(self, free: int) -> None:
        self.disk_free = free

    # --- running --------------------------------------------------------------------------------------------
    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(self.env_vars())
        return env

    def env_vars(self) -> dict[str, str]:
        return {
            "PITSTUDIO_REPO": str(self.repo),
            "PITSTUDIO_STORE": str(self.store),
            "GPU_LOCK_DIR": str(self.lock_dir),
            "PITSTUDIO_GPU_BACKEND": f"fake:{self.device_file}",
            "PS_FAKE_LEDGER": str(self.ledger),
            "PYTHONPATH": os.pathsep.join([str(SUPPORT), str(SRC), str(ROOT / "api")]),
        }

    def cli(self, *argv: str, capsys: Any = None) -> Result:
        """In-process `pitstudio.runner.cli.main(argv)`; usage errors raised as SystemExit are turned into codes."""
        from pitstudio.runner import cli  # first-party; absent until the runner exists

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(list(argv))
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 2)
        return Result(0 if code is None else int(code), out.getvalue(), err.getvalue())

    def sub(
        self, *argv: str, timeout: float = 120, env: dict[str, str] | None = None, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """`python -m pitstudio.runner <argv>` in a fresh process (own interpreter state)."""
        return subprocess.run(
            [sys.executable, "-m", "pitstudio.runner", *argv],
            capture_output=True, text=True, timeout=timeout, env=env or self.env(), cwd=str(cwd or self.base),
        )  # fmt: skip

    def plan_json(self, recipe_id: str, profile: str | None = None, *extra: str) -> dict[str, Any]:
        r = self.cli("plan", str(self.recipes[recipe_id]), "--profile", profile or self.profile_id, "--json", *extra)
        assert r.code == 0, f"plan exited {r.code}: {r.err or r.out}"
        return json.loads(r.out)

    def run(self, recipe_id: str, *extra: str, profile: str | None = None) -> Result:
        return self.cli("run", str(self.recipes[recipe_id]), "--profile", profile or self.profile_id, *extra)

    # --- reading outputs ------------------------------------------------------------------------------------
    def run_dirs(self) -> list[Path]:
        d = self.store / "runs"
        return sorted(p for p in d.iterdir() if p.is_dir()) if d.is_dir() else []

    def last_run(self) -> Path:
        runs = self.run_dirs()
        assert runs, "no run folder in the store"
        return runs[-1]

    def manifest(self, run_dir: Path | None = None) -> dict[str, Any]:
        return json.loads(((run_dir or self.last_run()) / "manifest.json").read_text(encoding="utf-8"))

    def events(self, run_dir: Path | None = None) -> list[dict[str, Any]]:
        p = (run_dir or self.last_run()) / "events.jsonl"
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    def stage_record(self, key: str, run_dir: Path | None = None) -> dict[str, Any]:
        m = self.manifest(run_dir)
        for s in m["stages"]:
            k = s["key"]["id"] + (f"@{s['key']['variant']}" if s["key"].get("variant") else "")
            if k == key:
                return s
        raise AssertionError(f"stage {key} not in manifest: {[s['key'] for s in m['stages']]}")

    def ledger_rows(self) -> list[dict[str, Any]]:
        if not self.ledger.is_file():
            return []
        return [json.loads(line) for line in self.ledger.read_text(encoding="utf-8").splitlines() if line.strip()]

    def starts(self) -> list[dict[str, Any]]:
        return [r for r in self.ledger_rows() if r["event"] == "start"]

    def snapshot_repo(self) -> dict[str, str]:
        return tree_digest(self.repo)

    def snapshot_store(self) -> dict[str, str]:
        return tree_digest(self.store)


@dataclass
class Result:
    code: int
    out: str
    err: str

    @property
    def text(self) -> str:
        return self.out + self.err


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return r.stdout


def tree_digest(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if rel.startswith(".git/") or rel == ".git":
            continue
        if p.is_file() and not p.is_symlink():
            out[rel] = sha256_bytes(p.read_bytes())
        elif p.is_dir():
            out[rel + "/"] = ""
    return out


def short_dir(prefix: str = "pst") -> Path:
    """A short directory for the store (the runner refuses Windows store paths over 64 characters, FR-002-42)."""
    base = Path(os.environ.get("PITSTUDIO_TEST_TMP") or tempfile.gettempdir())
    d = base / f"{prefix}{uuid.uuid4().hex[:8]}"
    d.mkdir(parents=True)
    return d


_TEMPLATE: list[Path] = []


def _template_repo() -> Path:
    """Build once per process (and commit with git) the repository skeleton every world copies."""
    if _TEMPLATE:
        return _TEMPLATE[0]
    import atexit

    tpl = short_dir("tpl") / "repo"
    repo = tpl
    for root in set(ENV_LOCK_ROOT.values()):
        (repo / root).mkdir(parents=True, exist_ok=True)
        (repo / root / "uv.lock").write_text(uv_lock_text(root), encoding="utf-8", newline="\n")
    for roots in ENV_CODE_ROOTS.values():
        for r in roots:
            (repo / r).mkdir(parents=True, exist_ok=True)
            (repo / r / "__init__.py").write_text(f"# code root {r}\n", encoding="utf-8", newline="\n")
    (repo / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    # the stage helper folder is part of every code digest (plan.md D7): the same bytes as the real checkout when it
    # exists, so a runner that reads the helper from its own package and one that reads it from the repository agree
    kit = repo / "src" / "pitstudio" / "runner" / "stagekit"
    real_kit = ROOT / "src" / "pitstudio" / "runner" / "stagekit"
    if real_kit.is_dir():
        shutil.copytree(real_kit, kit, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        kit.mkdir(parents=True)
        (kit / "pitstudio_stagekit.py").write_text("# stand-in for the stage helper\n", encoding="utf-8", newline="\n")
    (repo / "studio" / "bench").mkdir(parents=True, exist_ok=True)
    (repo / "studio" / "bench" / "run_bench.py").write_text(RUN_BENCH_STUB, encoding="utf-8", newline="\n")
    (repo / "studio" / "tools.yaml").write_text(
        yaml.safe_dump(tools_doc(), sort_keys=False), encoding="utf-8", newline="\n"
    )
    (repo / "studio" / "capabilities.json").write_text(json.dumps(capabilities_doc()), encoding="utf-8", newline="\n")
    (repo / "web" / "public" / "assets").mkdir(parents=True, exist_ok=True)
    (repo / "web" / "public" / "assets" / "manifest.json").write_text(
        json.dumps({"kind": "web-index", "schema_version": "1.0", "generated": "2026-10-11", "git_sha": "0" * 40, "runs": [], "artefacts": []}),
        encoding="utf-8", newline="\n",
    )  # fmt: skip
    (repo / "models" / "cards").mkdir(parents=True, exist_ok=True)
    (repo / "models" / "cards" / ".gitkeep").write_text("", encoding="utf-8")
    (repo / "studio" / "recipes" / "cases").mkdir(parents=True, exist_ok=True)
    (repo / "studio" / "recipes" / "cases" / ".gitkeep").write_text("", encoding="utf-8")
    git(repo, "init", "-q", "--template=")
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "template")
    _TEMPLATE.append(repo)
    atexit.register(shutil.rmtree, tpl.parent, ignore_errors=True)
    return repo


def make_world(
    monkeypatch: Any,
    tmp_path: Path,
    *,
    recipes: list[dict[str, Any]] | None = None,
    profile: dict[str, Any] | None = None,
    device: dict[str, Any] | None = None,
    fake_disk: bool = True,
    capabilities: dict[str, Any] | None = None,
    commit: bool = False,
) -> World:
    """Build the throw-away repository, store, lock folder and fake device, and point the environment at them."""
    repo = tmp_path / "repo"
    base = tmp_path / "base"
    base.mkdir()
    store = short_dir("pst")
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    shutil.copytree(_template_repo(), repo)
    if capabilities is not None:
        (repo / "studio" / "capabilities.json").write_text(json.dumps(capabilities), encoding="utf-8", newline="\n")
    w = World(
        repo=repo,
        store=store,
        lock_dir=lock_dir,
        device_file=base / "device.yaml",
        ledger=base / "ledger.jsonl",
        base=base,
    )
    prof = profile or profile_doc()
    w.profile_id = prof["id"]
    w.write_profile(prof)
    w.write_device(device or device_doc())
    for r in recipes or []:
        w.write_recipe(r)
    if commit:
        w.commit()
    for k, v in w.env_vars().items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("PITSTUDIO_GPU_LOCK", raising=False)
    if fake_disk:
        real = _REAL_DISK_USAGE

        def fake_usage(path: Any) -> Usage:
            u = real(path)
            return Usage(max(u.total, w.disk_free), u.used, w.disk_free)

        monkeypatch.setattr(shutil, "disk_usage", fake_usage)
    w.monkeypatch = monkeypatch
    return w


def cleanup_world(w: World) -> None:
    shutil.rmtree(w.store, ignore_errors=True)


# ----------------------------------------------------------------------------------------------------------------
# fakes and oracles shared by tests
# ----------------------------------------------------------------------------------------------------------------
class FakeClock:
    """Deterministic clock: `sleep` advances time and records the request; API expected by the runner: monotonic(), sleep(s)."""

    def __init__(self, t0: float = 0.0) -> None:
        self.t = float(t0)
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def time(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(float(seconds))
        self.t += float(seconds)


class PopenSpy:
    """Replaces `subprocess.Popen`: records (args, kwargs) and delegates to the real class."""

    def __init__(self, monkeypatch: Any) -> None:
        self.calls: list[tuple[Any, dict[str, Any]]] = []
        self.real = subprocess.Popen
        spy = self

        class _Popen(spy.real):  # type: ignore[misc, name-defined]
            def __init__(self, args: Any, *a: Any, **kw: Any) -> None:
                spy.calls.append((args, kw))
                super().__init__(args, *a, **kw)

        monkeypatch.setattr(subprocess, "Popen", _Popen)

    def argv_lists(self) -> list[list[str]]:
        return [list(map(str, a)) if isinstance(a, (list, tuple)) else [str(a)] for a, _ in self.calls]


def forbid_popen(monkeypatch: Any) -> list[Any]:
    calls: list[Any] = []

    class _Boom:
        def __init__(self, *a: Any, **kw: Any) -> None:
            calls.append((a, kw))
            raise AssertionError("a process was started")

    monkeypatch.setattr(subprocess, "Popen", _Boom)
    return calls


def block_modules(monkeypatch: Any, *names: str) -> None:
    """Any import of these modules fails (sys.modules entry None), as in tests/unit/test_run_bench_hold.py."""
    for n in names:
        monkeypatch.setitem(sys.modules, n, None)


def cas_violations(store: Path) -> list[str]:
    """P-002-06 oracle: every cas file's name equals the SHA-256 of its content; every index entry references objects."""
    bad: list[str] = []
    cas = store / "cas" / "sha256"
    present: set[str] = set()
    if cas.is_dir():
        for f in cas.rglob("*"):
            if f.is_file():
                present.add(f.name)
                if sha256_bytes(f.read_bytes()) != f.name:
                    bad.append(f"object {f.name} does not hash to its name")
                if f.parent.name != f.name[:2]:
                    bad.append(f"object {f.name} in the wrong fan-out folder {f.parent.name}")
    idx = store / "index"
    if idx.is_dir():
        for f in idx.rglob("*.json"):
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                bad.append(f"index entry {f.name} is not valid JSON")
                continue
            bad.extend(
                f"index entry {f.name} references missing object {o['sha256']}"
                for o in doc.get("outputs", [])
                if o["sha256"] not in present
            )
    return bad


def jcs_simple(obj: Any) -> bytes:
    """RFC 8785 for integers, ASCII strings, booleans, null and nested objects/arrays of them (equal to sorted compact JSON)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def wait_until(pred: Any, timeout: float = 10.0, step: float = 0.02, proc: Any = None) -> bool:
    """Poll `pred` until true or `timeout`; with `proc` (a Popen), stop waiting as soon as that process has exited."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        if proc is not None and proc.poll() is not None:
            break
        time.sleep(step)
    return bool(pred())
