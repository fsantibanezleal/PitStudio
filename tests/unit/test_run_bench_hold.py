"""The capability runner refuses to touch the GPU while a machine-wide hold file exists."""

from __future__ import annotations

import shutil
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "bench"))
import run_bench  # noqa: E402


@pytest.fixture
def lock_dir(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    d = ROOT / ".tmp" / "test-run-bench" / uuid.uuid4().hex
    d.mkdir(parents=True)
    monkeypatch.setenv("GPU_LOCK_DIR", str(d))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def no_gpu_libs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any import of the GPU telemetry or lock libraries fails the test: the hold must win before them."""
    for mod in ("pynvml", "filelock"):
        monkeypatch.setitem(sys.modules, mod, None)


def test_hold_file_stops_the_run_before_any_gpu_library(lock_dir: Path, no_gpu_libs: None, capsys) -> None:
    (lock_dir / "gpu0.hold").write_text("bugcheck under investigation\n", encoding="utf-8")
    assert run_bench.main(["run_bench.py", "warp_newton"]) == 4
    out = capsys.readouterr().out
    assert "bugcheck under investigation" in out
    assert "not starting" in out


def test_empty_hold_file_still_stops_the_run(lock_dir: Path, no_gpu_libs: None) -> None:
    (lock_dir / "gpu0.hold").write_text("", encoding="utf-8")
    assert run_bench.hold_reason() == "no reason given"
    assert run_bench.main(["run_bench.py"]) == 4


def test_no_hold_file_means_no_reason(lock_dir: Path) -> None:
    assert run_bench.hold_reason() is None


def test_unknown_probe_is_rejected_before_anything_else(lock_dir: Path, no_gpu_libs: None) -> None:
    with pytest.raises(SystemExit) as e:
        run_bench.main(["run_bench.py", "../../etc/passwd"])
    assert e.value.code == 2


def test_stress_probe_is_opt_in() -> None:
    assert "stress" in run_bench.PROBES
    assert "stress" in run_bench.OPT_IN
