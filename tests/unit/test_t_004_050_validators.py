# ruff: noqa: E501, PT018
"""T-004-050: validators run and recorded; waivers; an unavailable validator gives `incomplete` and `validation-incomplete`.

Requirements: FR-004-34, FR-004-37, FR-004-38.

Oracle: a fixture layer with one known validator error (an incorrect `extent`, flagged by the NVIDIA rule
`ExtentsChecker`) must fail and the clean fixture must pass (plan.md "FR-004-34"); validator versions are read from
`studio/uv.lock` with `tomllib`; waivers: a hand-written list with an allowed and forbidden rule (plan.md "FR-004-37");
validators replaced by fakes whose import fails or whose first use crashes (plan.md "FR-004-38"); the report is validated
with the DC-004-07 draft schema and the manifest with DC-004-02.

Expected API (package `pitstudio_studio.scene.validate`, studio environment):
- `validate.validate_scene(spec, build_scene, work_dir, *, runners=None, write=True) -> ValidationOutcome`.
  `build_scene(out_dir)` builds the scene into the (fresh) folder it is given and returns the `compose.SceneBuild`; it is
  called twice, into `work_dir/build1` and `work_dir/build2` (FR-004-36, test_t_004_052). The first build is validated:
  `usd-validation-nvidia` and `simready-validate` run on its root stage once per variant selection of the manifest (one
  selection per `lod` name, the other sets at their default); each result becomes `{rule, severity ("error", "warning",
  "info"), prim (path or None), message (scrubbed, at most 300 characters), waived}`; the invariants of FR-004-35 are
  computed (test_t_004_051) and the determinism block is filled. `runners` optionally replaces the real validators:
  `{validator id: callable(root_layer_path, selection_dict) -> list of result dicts}`.
- `ValidationOutcome`: `report` (DC-004-07 dict), `manifest` (the first build's manifest with `validation` set to
  `{"status": "complete" | "incomplete", "report": {"path": "validation/scene-validation-report.json", "sha256": ...}}`),
  `scene_dir` (the validated first build), `error_class` (None, or `"validation-incomplete"`), `passed` (bool). With
  `write=True` the report is written to `<scene_dir>/validation/scene-validation-report.json` and the manifest rewritten.
- A validator that cannot be imported, or crashes on first use, is recorded `{"status": "not_run", "reason": ..., "version":
  <lock version or None>, "results": []}`; the report status is `incomplete`, `passed` false, and `error_class` is
  `"validation-incomplete"`. An `error` result that is not waived makes `passed` false.
- A waiver (`spec["validation"]["waivers"]`: `{rule, reason}`) marks the matching results `waived: true`, lists the
  waiver in `report["waivers"]`, and does not fail the scene. A waiver of a rule about units, up axis, semantic labels or
  asset paths (`UnitsInMetersChecker`, `UpAxisZChecker`, `AnchoredAssetPathsChecker`, `PortableAssetPathChecker`,
  `layer_units_axis`, `class_label_coverage`, `time_sampled_labels`, `forbidden_paths`) raises
  `common.SceneStageError("waiver-forbidden")` naming the rule, before any validator runs.
- The two validator packages (`usd_validation_nvidia`, `simready`) are imported inside `validate_scene` at call time, never
  at module import, so that a `None` entry in `sys.modules` (import failure) or a stand-in module is honoured.
- `validate.run(job)` (the stage entry) reports a non-None `error_class` as the stage failure message prefix
  (`"validation-incomplete: ..."`), so that no stage depending on the validated scene runs.
"""

from __future__ import annotations

import copy
import itertools
import json
import sys
import tomllib
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import common, compose, validate  # noqa: E402


def _lock_versions() -> dict[str, str]:
    lock = tomllib.loads((ROOT / "studio" / "uv.lock").read_text(encoding="utf-8"))
    return {p["name"]: p["version"] for p in lock["package"]}


def _spec() -> dict:
    spec = kit.scene_spec()
    spec["variants"] = {
        "pushback": ["pb0"],
        "scenario": ["baseline"],
        "time_of_day": ["noon"],
        "weather": ["clear"],
        "lod": ["lod0", "lod1", "lod2"],
    }
    return spec


def _builder(spec: dict, tmp: Path, mutate=None):
    counter = itertools.count()

    def build(out_dir: Path):
        up = kit.fixture_upstream(tmp / f"up{next(counter)}")
        result = compose.compose_scene(spec, up, out_dir)
        if mutate:
            mutate(out_dir)
        return result

    return build


def _ok(runner_results=()):
    return lambda root, selection: [dict(r) for r in runner_results]


FAKE_ERROR = {"rule": "FakeRule", "severity": "error", "prim": "/World/Design", "message": "a deliberate fake error"}


@pytest.mark.req("FR-004-34")
def test_clean_fixture_passes_with_both_real_validators_recorded(tmp_path: Path) -> None:
    spec = _spec()
    out = validate.validate_scene(spec, _builder(spec, tmp_path), tmp_path / "work")
    report = out.report
    assert kit.schema_errors("scene-validation-report.schema.json", report) == []
    assert report["status"] == "complete" and report["passed"] is True and out.passed and out.error_class is None
    lock = _lock_versions()
    got = {v["id"]: v for v in report["validators"]}
    assert sorted(got) == ["simready-validate", "usd-validation-nvidia"]  # versions read from studio/uv.lock
    assert got["usd-validation-nvidia"]["version"] == lock["usd-validation-nvidia"]
    assert got["simready-validate"]["version"] == lock["simready-validate"]
    assert all(v["status"] == "ran" for v in got.values())
    assert [s["lod"] for s in report["selections"]] == ["lod0", "lod1", "lod2"]
    assert all(r["severity"] != "error" for v in got.values() for r in v["results"])


@pytest.mark.req("FR-004-34")
def test_a_known_validator_error_fails_the_scene(tmp_path: Path) -> None:
    from pxr import Usd, UsdGeom

    def break_extent(scene_dir: Path) -> None:
        stage = Usd.Stage.Open(str(scene_dir / "layers" / "design.usda"))
        UsdGeom.Mesh(stage.GetPrimAtPath("/World/Design/Bench_00")).GetExtentAttr().Set([(0, 0, 0), (1, 1, 1)])
        stage.GetRootLayer().Save()

    spec = _spec()
    out = validate.validate_scene(spec, _builder(spec, tmp_path, break_extent), tmp_path / "work")
    assert out.passed is False and out.report["passed"] is False
    nvidia = next(v for v in out.report["validators"] if v["id"] == "usd-validation-nvidia")
    errors = [r for r in nvidia["results"] if r["severity"] == "error"]
    assert any("extent" in r["rule"].lower() and r["prim"] == "/World/Design/Bench_00" for r in errors), nvidia[
        "results"
    ]
    assert all(1 <= len(r["message"]) <= 300 for r in nvidia["results"])
    assert kit.schema_errors("scene-validation-report.schema.json", out.report) == []


@pytest.mark.req("FR-004-34")
def test_report_and_manifest_are_written_with_the_report_digest(tmp_path: Path) -> None:
    spec = _spec()
    out = validate.validate_scene(spec, _builder(spec, tmp_path), tmp_path / "work")
    scene = Path(out.scene_dir)
    path = scene / "validation" / "scene-validation-report.json"
    assert json.loads(path.read_text(encoding="utf-8")) == out.report
    manifest = json.loads((scene / "scene.manifest.json").read_text(encoding="utf-8"))
    assert manifest == out.manifest and kit.schema_errors("scene-manifest.schema.json", manifest) == []
    assert manifest["validation"] == {
        "status": "complete",
        "report": {"path": "validation/scene-validation-report.json", "sha256": kit.sha256_file(path)},
    }


@pytest.mark.req("FR-004-34")
def test_results_of_every_validator_and_selection_are_recorded_and_errors_fail(tmp_path: Path) -> None:
    spec = _spec()
    calls: list[tuple[str, str]] = []

    def runner(vid: str):
        def run(root: Path, selection: dict) -> list[dict]:
            calls.append((vid, selection["lod"]))
            return [dict(FAKE_ERROR)] if vid == "simready-validate" and selection["lod"] == "lod1" else []

        return run

    runners = {
        "usd-validation-nvidia": runner("usd-validation-nvidia"),
        "simready-validate": runner("simready-validate"),
    }
    out = validate.validate_scene(spec, _builder(spec, tmp_path), tmp_path / "work", runners=runners)
    assert sorted(calls) == sorted((v, lod) for v in runners for lod in ("lod0", "lod1", "lod2"))  # every selection
    simready = next(v for v in out.report["validators"] if v["id"] == "simready-validate")
    assert [r["rule"] for r in simready["results"]] == ["FakeRule"] and out.passed is False


@pytest.mark.req("FR-004-37")
def test_a_waived_rule_is_listed_with_its_reason_and_does_not_fail_the_scene(tmp_path: Path) -> None:
    spec = _spec()
    spec["validation"] = {"waivers": [{"rule": "FakeRule", "reason": "known harmless difference on the fixture"}]}
    runners = {"usd-validation-nvidia": _ok([FAKE_ERROR]), "simready-validate": _ok()}
    out = validate.validate_scene(spec, _builder(spec, tmp_path), tmp_path / "work", runners=runners)
    assert out.report["waivers"] == [{"rule": "FakeRule", "reason": "known harmless difference on the fixture"}]
    results = next(v for v in out.report["validators"] if v["id"] == "usd-validation-nvidia")["results"]
    assert results and all(r["waived"] is True for r in results)
    assert out.passed is True and out.report["passed"] is True
    other = copy.deepcopy(spec)
    other["validation"] = {"waivers": [{"rule": "OtherRule", "reason": "a waiver for another rule entirely"}]}
    out2 = validate.validate_scene(other, _builder(other, tmp_path / "b"), tmp_path / "work2", runners=runners)
    assert out2.passed is False and out2.report["waivers"][0]["rule"] == "OtherRule"  # FakeRule is not waived


@pytest.mark.req("FR-004-37")
@pytest.mark.parametrize(
    "rule",
    [
        "UnitsInMetersChecker",
        "UpAxisZChecker",
        "AnchoredAssetPathsChecker",
        "PortableAssetPathChecker",
        "layer_units_axis",
        "class_label_coverage",
        "time_sampled_labels",
        "forbidden_paths",
    ],
)
def test_waiving_a_units_axis_label_or_path_rule_is_forbidden(tmp_path: Path, rule: str) -> None:
    spec = _spec()
    spec["validation"] = {"waivers": [{"rule": rule, "reason": "an attempt to silence a protected rule"}]}
    calls: list[str] = []
    runners = {"usd-validation-nvidia": lambda r, s: calls.append("x") or [], "simready-validate": _ok()}
    with pytest.raises(common.SceneStageError) as exc:
        validate.validate_scene(spec, _builder(spec, tmp_path), tmp_path / "work", runners=runners)
    assert exc.value.error_class == "waiver-forbidden" and str(exc.value).startswith("waiver-forbidden: ")
    assert rule in str(exc.value) and calls == []  # rejected before any validator ran


class _CrashingModule(types.ModuleType):
    """A stand-in validator module that imports fine and crashes on the first attribute access."""

    def __getattr__(self, name: str):
        raise RuntimeError("the validator crashed on first use")


@pytest.mark.req("FR-004-38")
@pytest.mark.parametrize("module", ["usd_validation_nvidia", "simready"])
@pytest.mark.parametrize("failure", ["import-error", "crash"])
def test_an_unavailable_validator_makes_the_validation_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: str, failure: str
) -> None:
    # a None entry in sys.modules makes `import <module>` raise ImportError; the crashing stand-in raises on first use
    monkeypatch.setitem(sys.modules, module, _CrashingModule("fake_validator") if failure == "crash" else None)
    spec = _spec()
    out = validate.validate_scene(spec, _builder(spec, tmp_path), tmp_path / "work")
    vid = "usd-validation-nvidia" if module == "usd_validation_nvidia" else "simready-validate"
    broken = next(v for v in out.report["validators"] if v["id"] == vid)
    assert broken["status"] == "not_run" and broken["results"] == [] and broken["reason"].strip()
    assert out.report["status"] == "incomplete" and out.report["passed"] is False and out.passed is False
    assert out.error_class == "validation-incomplete"
    assert out.manifest["validation"]["status"] == "incomplete"
    assert kit.schema_errors("scene-validation-report.schema.json", out.report) == []
    assert kit.schema_errors("scene-manifest.schema.json", out.manifest) == []
    assert "\n" not in broken["reason"] and kit.machine_identifiers()[0] not in broken["reason"]
    assert out.error_class == "validation-incomplete"  # the stage helper turns this into the stage failure message
