# ruff: noqa: E501, PT018
"""T-013-011: runtime-isolation check before renderer construction.

Requirements: FR-013-03.

Oracle: hand-built `sys.modules` states (plan.md "FR-013-03"): Kit modules present means the `ovrtx` backend request raises
`RuntimeIsolationError` before any renderer object exists; an `ovrtx` module present means the `isaac` request raises. The
stand-in runtime modules raise `AssertionError` on any attribute access, so a renderer touched before the check fails the
test with a different exception.

Expected API: `pitstudio_rtx.backend.check_runtime_isolation(requested, modules=sys.modules)` implements the rule on a module
table (a mapping of loaded module names; it never imports anything) and `create_backend(name, **kwargs)` (test_t_013_010)
calls it first:
- `"ovrtx"`: `RuntimeIsolationError` when any loaded module name equals or starts with `omni.kit`, `isaacsim` or `carb`
  (followed by a dot);
- `"isaac"`: `RuntimeIsolationError` when `ovrtx` (or an `ovrtx.` submodule) is loaded;
- `"fake"`: never refused;
and raises before it imports or touches the runtime it was asked for. The error message names the conflicting modules.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "rtx" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
from pitstudio_rtx import backend as backend_mod  # noqa: E402


class Untouchable(types.ModuleType):
    """A runtime module stand-in: any use of it (attribute access) is an error."""

    def __getattr__(self, name: str):
        raise AssertionError(f"the runtime module {self.__name__} was touched ({name})")


def _load(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    for name in names:
        monkeypatch.setitem(sys.modules, name, Untouchable(name))


KIT_MODULES = [
    "omni.kit",
    "omni.kit.app",
    "omni.kit.commands",
    "isaacsim",
    "isaacsim.core.api",
    "carb",
    "carb.settings",
]


@pytest.mark.req("FR-013-03")
@pytest.mark.parametrize("module", KIT_MODULES)
def test_ovrtx_is_refused_when_a_kit_isaac_or_carb_module_is_loaded(
    monkeypatch: pytest.MonkeyPatch, module: str
) -> None:
    _load(monkeypatch, "ovrtx", module)  # the ovrtx stand-in proves nothing was constructed or imported first
    with pytest.raises(backend_mod.RuntimeIsolationError) as exc:
        backend_mod.create_backend("ovrtx")
    assert module in str(exc.value)


@pytest.mark.req("FR-013-03")
@pytest.mark.parametrize("module", ["ovrtx", "ovrtx.api"])
def test_isaac_is_refused_when_ovrtx_is_loaded(monkeypatch: pytest.MonkeyPatch, module: str) -> None:
    _load(monkeypatch, "isaacsim", module)
    with pytest.raises(backend_mod.RuntimeIsolationError) as exc:
        backend_mod.create_backend("isaac")
    assert "ovrtx" in str(exc.value)


@pytest.mark.req("FR-013-03")
def test_the_error_is_a_runtime_error_raised_for_every_kit_module_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    _load(monkeypatch, "ovrtx", "omni.kit.app", "carb")
    with pytest.raises(backend_mod.RuntimeIsolationError) as exc:
        backend_mod.create_backend("ovrtx")
    assert isinstance(exc.value, RuntimeError)
    assert "omni.kit.app" in str(exc.value) and "carb" in str(exc.value)


@pytest.mark.req("FR-013-03")
def test_the_fake_backend_and_unrelated_modules_are_never_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _load(monkeypatch, "ovrtx", "omni.kit.app", "isaacsim", "carb")
    assert backend_mod.create_backend("fake") is not None  # no renderer, so no conflict
    backend_mod.check_runtime_isolation("fake")
    # look-alike module names and a clean process do not trigger the rule (checked on a module table, no import)
    lookalikes = {n: types.ModuleType(n) for n in ("omnikit", "omni", "omni.usd", "ovrtx_tools", "numpy")}
    backend_mod.check_runtime_isolation("ovrtx", modules=lookalikes)
    backend_mod.check_runtime_isolation("isaac", modules=lookalikes)
    backend_mod.check_runtime_isolation("ovrtx", modules={})
    backend_mod.check_runtime_isolation("isaac", modules={})


@pytest.mark.req("FR-013-03")
@pytest.mark.parametrize(
    ("requested", "present", "conflict"),
    [
        ("ovrtx", "omni.kit", "omni.kit"),
        ("ovrtx", "isaacsim.core", "isaacsim.core"),
        ("ovrtx", "carb.settings", "carb.settings"),
        ("isaac", "ovrtx", "ovrtx"),
        ("isaac", "ovrtx.sub.module", "ovrtx.sub.module"),
    ],
)
def test_the_isolation_check_works_on_any_module_table(requested: str, present: str, conflict: str) -> None:
    with pytest.raises(backend_mod.RuntimeIsolationError) as exc:
        backend_mod.check_runtime_isolation(requested, modules={present: types.ModuleType(present), "numpy": None})
    assert conflict in str(exc.value)
