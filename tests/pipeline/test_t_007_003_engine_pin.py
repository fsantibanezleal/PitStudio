# ruff: noqa: E501, PT018
"""T-007-003: engine pin file (version + module SHA-256 + callback-name map) and the guard that refuses on any mismatch.

Requirements: FR-007-02.

Spec: specs/007-haulage-dispatch/spec.md FR-007-02 (if the installed `minehaulsim` version, or the SHA-256 of any engine module the adapter's
seam depends on, differs from the adapter's engine pin file, the adapter refuses to run with `EngineVersionMismatch` naming every differing
item and writes no trace; the modules are `des/sim.py`, `des/engine.py`, `des/dispatch.py`, `des/failures.py`, `des/traversal.py`,
`des/resources.py`, `network/kinematics.py`, `network/routing.py`, `network/graph.py`, `equipment/catalog.py`), FR-007-09 (callbacks are mapped
to the canonical event kinds "by the pinned name map") and section 7 ("exact parity is version-bound": a new engine version re-bakes every
golden); plan.md ("Engine pin + seam", risks table: guarded by FR-007-02); `contracts/des-trace.schema.json` (`header.engine.pin_sha256`).

Oracle: `hashlib.sha256` over the installed engine files (the test computes the digests itself); the engine's own class `_Sim` for the callback
names (`inspect`-free: `hasattr`); the canonical vocabulary of the trace schema; hand-made tampered copies of the engine modules and of the pin file.

Expected API (module `pitstudio_pipeline.haulage.pin`; errors in `pitstudio_pipeline.haulage.errors`):
    errors.HaulError(Exception)                       base class of every typed error of this spec
    errors.EngineVersionMismatch(HaulError)           attribute `differences: list[tuple[str, str, str]]` of (item, pinned, installed), one per differing
                                                      item (`"version"` and each module path), `installed == "missing"` for an absent file; the message
                                                      names every item
    PIN_PATH: Path                                    the committed pin file `pipeline/src/pitstudio_pipeline/haulage/engine_pin.json`:
                                                      {"package": "minehaulsim", "version": "0.12.1", "modules": {<relative path>: <sha256>},
                                                       "callbacks": {<engine callback name>: <canonical event kind>}}
    load_pin(path=None) -> dict                       parsed pin file (default PIN_PATH)
    pin_sha256(path=None) -> str                      SHA-256 of the pin file's bytes (the `engine.pin_sha256` of every trace header)
    verify_engine(pin=None, *, package_root=None, installed_version=None) -> None
        compares `installed_version` (default: the installed package's `__version__`) and the SHA-256 of each pinned module under `package_root`
        (default: the installed package folder) with the pin (default: load_pin()); raises EngineVersionMismatch listing every difference
    adapter.run_shift(bundle_path, *, seed, dispatcher=None, profile=None, trace_path=None, pin_path=None) -> RunResult   (see test_t_007_013)
        calls verify_engine against `pin_path` before anything else; on a mismatch nothing is written to `trace_path`.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit as kit
from pitstudio_pipeline.haulage.errors import EngineVersionMismatch, HaulError
from pitstudio_pipeline.haulage.pin import PIN_PATH, load_pin, pin_sha256, verify_engine


def copy_engine(tmp: Path) -> Path:
    root = tmp / "engine"
    for rel in kit.PIN_MODULES:
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(kit.engine_root() / rel, dest)
    return root


# ---------------------------------------------------------------------------------------------------------------------
# the committed pin file against the installed engine (hashes computed here)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-02")
def test_the_pin_file_is_committed_and_names_the_locked_engine_version():
    assert PIN_PATH.is_file() and PIN_PATH.name == "engine_pin.json"
    pin = load_pin()
    assert pin["package"] == "minehaulsim" and pin["version"] == kit.ENGINE_VERSION == "0.12.1"


@pytest.mark.req("FR-007-02")
def test_the_pin_holds_exactly_the_ten_seam_modules_with_their_real_digests():
    pin = load_pin()
    assert sorted(pin["modules"]) == sorted(kit.PIN_MODULES)
    for rel in kit.PIN_MODULES:
        assert pin["modules"][rel] == kit.sha256_file(kit.engine_root() / rel), rel


@pytest.mark.req("FR-007-02")
def test_pin_sha256_is_the_digest_of_the_pin_files_bytes():
    assert pin_sha256() == kit.sha256_file(PIN_PATH)
    assert len(pin_sha256()) == 64


@pytest.mark.req("FR-007-02")
def test_the_callback_map_names_real_engine_callbacks_and_canonical_kinds():
    from minehaulsim.des import sim

    cb = load_pin()["callbacks"]
    assert cb and all(v in kit.KINDS for v in cb.values())
    core = {
        "_go_load": "arrive-loader",
        "_loaded": "load-end",
        "_depart_loaded": "depart-loaded",
        "_arrive_dump": "arrive-dump",
        "_dumped": "dump-end",
        "_dispatch_next": "dispatch",
        "_lhd_start": "lhd-start",
        "_lhd_dig": "lhd-dig",
        "_lhd_to_tip": "lhd-to-tip",
        "_lhd_at_tip": "lhd-at-tip",
        "_lhd_after_tip": "lhd-after-tip",
    }
    for name, kind in core.items():
        assert cb.get(name) == kind, name
        assert hasattr(sim._Sim, name), name  # the pinned name exists in the pinned engine


# ---------------------------------------------------------------------------------------------------------------------
# verify_engine
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-02")
def test_the_installed_engine_matches_its_pin():
    verify_engine()  # must not raise
    verify_engine(load_pin(), installed_version="0.12.1")


@pytest.mark.req("FR-007-02")
def test_a_different_version_is_refused_naming_the_version():
    with pytest.raises(EngineVersionMismatch) as ei:
        verify_engine(installed_version="0.12.2")
    e = ei.value
    assert isinstance(e, HaulError) and [d[0] for d in e.differences] == ["version"]
    assert e.differences[0][1:] == ("0.12.1", "0.12.2") and "version" in str(e)


@pytest.mark.req("FR-007-02")
def test_every_differing_module_and_the_version_are_named_together(tmp_path):
    root = copy_engine(tmp_path)
    for rel in ("des/sim.py", "network/routing.py"):
        with (root / rel).open("ab") as f:
            f.write(b"\n# tampered\n")
    (root / "equipment" / "catalog.py").unlink()  # a missing module is a difference too
    with pytest.raises(EngineVersionMismatch) as ei:
        verify_engine(package_root=root, installed_version="0.12.9")
    e = ei.value
    assert sorted(d[0] for d in e.differences) == sorted(
        ["version", "des/sim.py", "network/routing.py", "equipment/catalog.py"]
    )
    by = {d[0]: d for d in e.differences}
    assert by["equipment/catalog.py"][2] == "missing"
    assert by["des/sim.py"][1] == kit.sha256_file(kit.engine_root() / "des/sim.py") and by["des/sim.py"][
        2
    ] == kit.sha256_file(root / "des/sim.py")
    for item in ("version", "des/sim.py", "network/routing.py", "equipment/catalog.py"):
        assert item in str(e)
    assert "des/engine.py" not in str(e)  # unchanged modules are not reported


@pytest.mark.req("FR-007-02")
def test_one_flipped_byte_in_one_module_is_enough(tmp_path):
    root = copy_engine(tmp_path)
    p = root / "des" / "traversal.py"
    data = bytearray(p.read_bytes())
    data[len(data) // 2] ^= 0x01
    p.write_bytes(bytes(data))
    with pytest.raises(EngineVersionMismatch) as ei:
        verify_engine(package_root=root)
    assert [d[0] for d in ei.value.differences] == ["des/traversal.py"]


@pytest.mark.req("FR-007-02")
def test_an_altered_pin_hash_is_refused(tmp_path):
    pin = load_pin()
    pin["modules"]["des/dispatch.py"] = "0" * 64
    with pytest.raises(EngineVersionMismatch) as ei:
        verify_engine(pin)
    assert [d[0] for d in ei.value.differences] == ["des/dispatch.py"]


# ---------------------------------------------------------------------------------------------------------------------
# the adapter refuses and writes no trace
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-02")
def test_the_adapter_refuses_a_tampered_pin_and_writes_no_trace(tmp_path):
    from pitstudio_pipeline.haulage.adapter import run_shift

    pin = load_pin()
    pin["modules"]["des/sim.py"] = "f" * 64
    pin["version"] = "0.12.0"
    bad = tmp_path / "pin.json"
    bad.write_text(json.dumps(pin), encoding="utf-8")
    bundle = kit.write_bundle(tmp_path, kit.smoke_bundle())
    out = tmp_path / "trace.json"
    with pytest.raises(EngineVersionMismatch) as ei:
        run_shift(bundle, seed=42, trace_path=out, pin_path=bad)
    assert sorted(d[0] for d in ei.value.differences) == ["des/sim.py", "version"]
    assert not out.exists() and set(tmp_path.glob("*.json")) == {bad, bundle}  # nothing else was written either
