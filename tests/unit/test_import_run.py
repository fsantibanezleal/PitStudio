# ruff: noqa: PT018
"""`studio import-run`: a finished GPU-queue job recorded as a run with honest provenance (decision of the main session,
2026-11-22, delegation brief publish-cases-2026-11-22). Oracles: the run manifest contract, the digests of the files
the test wrote, the label the brief fixes. The publish path of spec 002 is then applied to the imported run.
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
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitstudio.runner import cli
from pitstudio.runner.recipe import first_errors

ROOT = Path(__file__).resolve().parents[2]
LABEL = "produced by the GPU queue, outside the runner"
JOB = "33-demo-job"
SCRIPT = "#!/bin/bash\necho job\n"
LOG = "[job] done: GPU hours 0.374 of 2.0\n"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git(repo: Path, *a: str) -> None:
    r = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr


class World:
    def __init__(self, tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.repo, self.store, self.queue, self.src = tmp / "repo", tmp / "store", tmp / "queue", tmp / "src"
        for d in (
            self.repo / "studio" / "recipes" / "cases",
            self.repo / "web" / "public" / "assets",
            self.queue / "done",
            self.src / "sub",
        ):
            d.mkdir(parents=True)
        shutil.copy(ROOT / "studio" / "tools.yaml", self.repo / "studio" / "tools.yaml")
        (self.repo / "studio" / "recipes" / "cases" / "c1.yaml").write_text("id: c1-slope\n", encoding="utf-8")
        index = {
            "kind": "web-index",
            "schema_version": "1.0",
            "generated": "2026-11-22",
            "git_sha": "a" * 40,
            "runs": [],
            "artefacts": [],
        }
        (self.repo / "web" / "public" / "assets" / "manifest.json").write_text(json.dumps(index), encoding="utf-8")
        git(self.repo, "init", "-q")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")
        self.result = {"metric": 0.5, "budget": {"total_gpu_hours": 0.374}}
        self.model = b"onnx-bytes" * 100
        (self.src / "result.json").write_text(json.dumps(self.result), encoding="utf-8")
        (self.src / "sub" / "model.onnx").write_bytes(self.model)
        (self.src / "sub" / "private.json").write_text('{"latency_ms": 7.5}', encoding="utf-8")
        (self.queue / "done" / f"{JOB}.sh").write_text(SCRIPT, encoding="utf-8", newline="\n")
        log = self.queue / f"{JOB}.log"
        log.write_text(LOG, encoding="utf-8", newline="\n")
        os.utime(log, (1_795_000_000, 1_795_000_000))  # 2026-11-18T11:06:40Z
        (self.queue / "queue.log").write_text(
            f"[queue 09:00:00] start {JOB}\n[queue 10:26:40] done {JOB}\n", encoding="utf-8", newline="\n"
        )
        monkeypatch.setenv("PITSTUDIO_REPO", str(self.repo))
        monkeypatch.setenv("PITSTUDIO_STORE", str(self.store))
        monkeypatch.setenv("PITSTUDIO_GPU_QUEUE", str(self.queue))
        self.tmp = tmp

    def doc(self) -> dict:
        common = {"licence_class": "own", "spdx": "Apache-2.0"}
        return {
            "job": JOB,
            "case": "C1",
            "recipe": "cases/c1.yaml",
            "slug": "c1-demo",
            "seed": 7,
            "label": "calibrated synthetic, not validated against real data",
            "gpu_hours": {"file": "result.json", "path": ["budget", "total_gpu_hours"]},
            "stages": [
                {
                    "id": "s30_train",
                    "tool": "pytorch",
                    "determinism": "none",
                    "outputs": [
                        {
                            "name": "result.json",
                            "from": "result.json",
                            "kind": "table",
                            "budget_class": "studio-showcase",
                            "publish": True,
                            "required_fields": ["metric"],
                            **common,
                        },
                        {
                            "name": "model.onnx",
                            "from": "sub/model.onnx",
                            "kind": "onnx",
                            "budget_class": "onnx",
                            "publish": False,
                            **common,
                        },
                        {
                            "name": "trt-latency.json",
                            "from": "sub/private.json",
                            "kind": "table",
                            "budget_class": "studio-showcase",
                            "publish": True,
                            "local_only": True,
                            **common,
                        },
                    ],
                }
            ],
        }

    def run(self, spec: dict | None = None) -> tuple[int, str]:
        p = self.tmp / "spec.json"
        p.write_text(json.dumps(spec or self.doc()), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["import-run", JOB, "--from", str(self.src), "--spec", str(p)])
        return code, err.getvalue()

    def runs(self) -> list[Path]:
        return sorted((self.store / "runs").glob("*")) if (self.store / "runs").is_dir() else []


def short(p: Path) -> Path:
    """The 8.3 form of a Windows path: the store root may not exceed 64 characters and a scratch folder can."""
    if sys.platform != "win32":
        return p
    import ctypes

    buf = ctypes.create_unicode_buffer(512)
    return Path(buf.value) if ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, 512) else p


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    # a plain folder, not tmp_path or mkdtemp: git cannot enter the owner-only folders those make on Windows
    tmp = Path(tempfile.gettempdir()) / f"ir-{uuid.uuid4().hex[:6]}"
    tmp.mkdir()
    tmp = short(tmp)
    try:
        for k, v in (("GIT_CONFIG_COUNT", "1"), ("GIT_CONFIG_KEY_0", "safe.directory"), ("GIT_CONFIG_VALUE_0", "*")):
            monkeypatch.setenv(k, v)  # the folder may be owned by the elevated account that made it
        yield World(tmp, monkeypatch)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def manifest_of(w: World) -> dict:
    (run,) = w.runs()
    return json.loads((run / "manifest.json").read_text(encoding="utf-8"))


def test_import_run_complete_job_records_a_valid_run_with_provenance(world: World) -> None:
    code, err = world.run()
    assert code == 0, err
    m = manifest_of(world)
    assert first_errors("manifest", m, "#/$defs/run", n=3) == []
    assert m["run_id"].startswith("20261118T110640Z-c1-demo")
    assert m["published"] is False and m["git_dirty"] is False
    notes = " | ".join(m["notes"])
    assert LABEL in notes
    assert JOB in notes and "script sha256 " + sha(SCRIPT.encode()) in notes
    assert "log sha256 " + sha(LOG.encode()) in notes
    assert "GPU-hours 0.374" in notes and "partial" not in notes
    (stage,) = m["stages"]
    assert stage["key"] == {"id": "s30_train"} and stage["status"] == "succeeded" and stage["tool"] == "pytorch"
    assert stage["attempts"][0]["duration_s"] == pytest.approx(5200)
    names = {o["name"]: o for o in stage["outputs"]}
    assert names["result.json"]["sha256"] == sha(json.dumps(world.result).encode())
    assert names["model.onnx"]["sha256"] == sha(world.model)
    events = [json.loads(x) for x in (world.runs()[0] / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["type"] for e in events] == ["run-started", "run-finished"]
    obj = world.store / "cas" / "sha256" / names["model.onnx"]["sha256"][:2] / names["model.onnx"]["sha256"]
    assert obj.read_bytes() == world.model


def test_import_run_missing_field_and_missing_script_label_the_run_partial(world: World) -> None:
    (world.src / "result.json").write_text(json.dumps({"budget": {"total_gpu_hours": 0.4}}), encoding="utf-8")
    (world.queue / "done" / f"{JOB}.sh").unlink()
    code, err = world.run()
    assert code == 0, err
    m = manifest_of(world)
    assert first_errors("manifest", m, "#/$defs/run", n=3) == []
    notes = " | ".join(m["notes"])
    assert "partial" in notes
    assert "result.json lacks field metric: marked missing" in notes
    assert "script missing" in notes
    assert json.loads((world.runs()[0] / "import.json").read_text(encoding="utf-8"))["partial"] is True


def test_import_run_digest_mismatch_is_refused_and_writes_nothing(world: World) -> None:
    spec = world.doc()
    spec["stages"][0]["outputs"][1]["sha256"] = "0" * 64
    code, err = world.run(spec)
    assert code == 2 and "digest" in err and "model.onnx" in err
    assert world.runs() == [] and not (world.store / "cas").exists()


def test_import_run_unknown_job_or_missing_output_is_a_usage_error(world: World) -> None:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["import-run", "99-no-such-job", "--from", str(world.src)])
    assert code == 2 and "99-no-such-job" in err.getvalue()
    (world.src / "sub" / "model.onnx").unlink()
    code, err = world.run()
    assert code == 2 and "model.onnx" in err


def test_import_run_publish_keeps_local_only_outputs_out_and_digests_match(world: World) -> None:
    from pitstudio.runner import publish

    assert world.run()[0] == 0
    run_id = world.runs()[0].name
    publish.publish(world.store, world.repo, run_id, None)
    repo = world.repo
    pub = json.loads((repo / "web/public/assets/runs" / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert pub["published"] is True
    assert [a["path"].rsplit("/", 1)[-1] for a in pub["artefacts"]] == ["result.json"]
    art = pub["artefacts"][0]
    assert art["producer"] == {"tool": "pytorch", "stage": {"id": "s30_train"}} and art["cases"] == ["C1"]
    assert sha((repo / "web" / "public" / art["path"]).read_bytes()) == art["sha256"]
    assert sorted(p.name for p in (repo / "web" / "public" / "assets" / run_id).iterdir()) == ["result.json"]
    assert LABEL in " ".join(pub["notes"])
    idx = json.loads((repo / "web/public/assets/manifest.json").read_text(encoding="utf-8"))
    assert [r["run_id"] for r in idx["runs"]] == [run_id]


def test_import_run_publish_refuses_a_machine_path_in_a_published_file(world: World) -> None:
    from pitstudio.runner import publish
    from pitstudio.runner.recipe import Usage

    (world.src / "result.json").write_text(json.dumps({"metric": 1, "p": "C:\\Users\\x\\f"}), encoding="utf-8")
    assert world.run()[0] == 0
    run_id = world.runs()[0].name
    with pytest.raises(Usage, match="absolute path"):
        publish.publish(world.store, world.repo, run_id, None)
    assert not (world.repo / "web" / "public" / "assets" / run_id).exists()


def test_import_run_is_listed_in_usage(world: World) -> None:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main([])
    assert code == 2 and "import-run" in err.getvalue()
