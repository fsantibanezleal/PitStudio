# ruff: noqa: E501, PT018, PT011
"""T-013-010: `SensorBackend` protocol, factory and fake backend; import-graph scan of the lane and of the post-models.

Requirements: FR-013-01, FR-013-02.

Oracle: a static import-graph scan with `ast` (no NVIDIA runtime module is imported outside the two backend modules; the
open post-models import only the standard library, numpy and minephys) and protocol conformance of the `fake` backend
(plan.md "FR-013-01", "FR-013-02").

Expected API (first-party packages `pitstudio_rtx` in `studio/rtx/src`, `pitstudio_isaac` in `studio/isaac/src` and
`pitstudio.sensors` in `src`):
- `pitstudio_rtx.backend` (pure Python, standard library only): `SensorBackend`, a `typing.Protocol` (runtime checkable) with
  exactly the four operations `describe`, `open`, `step`, `close`; `BackendInfo` (dataclass: `name`, `versions` dict,
  `capabilities` dict); `RuntimeIsolationError`; `create_backend(name, **kwargs) -> SensorBackend` for `"ovrtx"`, `"isaac"`,
  `"fake"` (an unknown name raises `ValueError`).
- `pitstudio_rtx.backends.fake.FakeBackend(script=None, *, versions=None, warmup_frames=0, name="fake")`: a scripted backend.
  `script(sensor: dict, step_index: int) -> dict` returns the output dict of one sensor for the `step_index`-th call of
  `step` (0-based, warm-up included). Its `describe()` returns `BackendInfo(name=name, versions=..., capabilities={"warmup_frames":
  warmup_frames, ...})`; it counts `open_calls`, `step_calls` and `close_calls`. Without a script it returns clean frames.
- Source files: `studio/rtx/src/pitstudio_rtx/{backend.py, lane.py, shards.py, rerun.py, backends/fake.py,
  backends/ovrtx_backend.py}` and `studio/isaac/src/pitstudio_isaac/sensor_backend.py` exist; no `ovrtx`, `ovstage`, `ovphysx`,
  `isaacsim`, `omni` or `carb` import (statement, `importlib.import_module` or `__import__` call) appears in any other file of
  `src/pitstudio`, `studio/rtx/src` or `studio/isaac/src`.
- `src/pitstudio/sensors/{dust.py, beamhash.py, camera.py, metrics.py, quantise.py}` import only the standard library, numpy,
  minephys and `pitstudio`; the lane package holds no post-model module (no file named dust, haze, exposure, camera,
  metrics or quantise).
"""

from __future__ import annotations

import ast
import sys
import typing
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "rtx" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import sensor_kit as kit  # noqa: E402
from pitstudio_rtx import backend as backend_mod  # noqa: E402
from pitstudio_rtx.backends import fake  # noqa: E402

RTX = ROOT / "studio" / "rtx" / "src" / "pitstudio_rtx"
ISAAC = ROOT / "studio" / "isaac" / "src" / "pitstudio_isaac"
SENSORS = ROOT / "src" / "pitstudio" / "sensors"
NVIDIA = {"ovrtx", "ovstage", "ovphysx", "isaacsim", "omni", "carb"}
BACKEND_FILES = {RTX / "backends" / "ovrtx_backend.py", ISAAC / "sensor_backend.py"}


def _imports(path: Path) -> set[str]:
    """Top-level module names imported by `path`, including `import_module("x")` and `__import__("x")` string calls."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            fn = node.func
            called = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if called in {"import_module", "__import__"} and node.args and isinstance(node.args[0], ast.Constant):
                names.add(str(node.args[0].value).split(".")[0])
    return names


@pytest.mark.req("FR-013-01")
def test_the_protocol_has_exactly_the_four_operations() -> None:
    assert typing.get_protocol_members(backend_mod.SensorBackend) == frozenset({"describe", "open", "step", "close"})
    info = fake.FakeBackend().describe()
    assert isinstance(info, backend_mod.BackendInfo)
    assert info.name == "fake" and isinstance(info.versions, dict) and isinstance(info.capabilities, dict)


@pytest.mark.req("FR-013-01")
def test_the_fake_backend_conforms_and_counts_its_calls() -> None:
    be = fake.FakeBackend()
    assert isinstance(be, backend_mod.SensorBackend)
    sensors = [{"kind": "lidar", "id": "rotary-64"}]
    session = be.open("stage.usda", sensors)
    out = be.step(session, {"frame": 0})
    assert isinstance(out, dict) and set(out) == {"rotary-64"}  # FrameOutputs: sensor id -> output dict
    assert out["rotary-64"]["kind"] == "lidar" and int(out["rotary-64"]["valid_count"]) > 0
    be.close(session)
    assert (be.open_calls, be.step_calls, be.close_calls) == (1, 1, 1)


@pytest.mark.req("FR-013-01")
def test_the_factory_builds_the_fake_backend_and_rejects_unknown_names() -> None:
    assert isinstance(backend_mod.create_backend("fake"), fake.FakeBackend)
    for bad in ("", "OVRTX", "vendor", "ovrtx ", "../ovrtx"):
        with pytest.raises(ValueError):
            backend_mod.create_backend(bad)


@pytest.mark.req("FR-013-01")
def test_the_lane_files_exist_and_no_nvidia_runtime_is_imported_outside_the_backends() -> None:
    expected = [
        RTX / "backend.py",
        RTX / "lane.py",
        RTX / "shards.py",
        RTX / "rerun.py",
        RTX / "backends" / "fake.py",
        RTX / "backends" / "ovrtx_backend.py",
        ISAAC / "sensor_backend.py",
    ]
    assert [p for p in expected if not p.is_file()] == []
    offenders = {}
    for folder in (ROOT / "src" / "pitstudio", RTX.parent, ISAAC.parent):
        for path in sorted(folder.rglob("*.py")):
            if path in BACKEND_FILES:
                continue
            bad = _imports(path) & NVIDIA
            if bad:
                offenders[str(path.relative_to(ROOT))] = sorted(bad)
    assert offenders == {}


@pytest.mark.req("FR-013-01")
def test_the_scan_catches_a_planted_violation(tmp_path: Path) -> None:
    planted = tmp_path / "x.py"
    planted.write_text(
        "import importlib\nimportlib.import_module('ovrtx.api')\nfrom carb import settings\n", encoding="utf-8"
    )
    assert _imports(planted) & NVIDIA == {"ovrtx", "carb"}  # the scanner used by this test sees both forms


@pytest.mark.req("FR-013-02")
def test_the_post_models_use_only_the_standard_library_numpy_and_minephys() -> None:
    expected = ["dust.py", "beamhash.py", "camera.py", "metrics.py", "quantise.py"]
    assert [n for n in expected if not (SENSORS / n).is_file()] == []
    allowed = set(sys.stdlib_module_names) | {"numpy", "minephys", "pitstudio", "__future__"}
    for name in expected:
        extra = _imports(SENSORS / name) - allowed
        assert extra == set(), (name, sorted(extra))


@pytest.mark.req("FR-013-02")
def test_the_lane_package_holds_no_post_model() -> None:
    names = {p.stem for p in RTX.rglob("*.py")} | {p.stem for p in ISAAC.rglob("*.py")}
    assert names.isdisjoint({"dust", "haze", "exposure", "camera", "metrics", "quantise", "beamhash"})
    assert kit.ROOT == ROOT  # the kit and this test agree on the repository root
