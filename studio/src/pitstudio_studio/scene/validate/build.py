"""The validation stage `st45_validate`: validators, invariants, waivers and build twice (FR-004-34 .. 39)."""

from __future__ import annotations

import itertools
import json
import shutil
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitstudio_studio.scene import common
from pitstudio_studio.scene.common import SceneStageError, StageContext, StageRun
from pitstudio_studio.scene.validate.invariants import compute_invariants

VALIDATOR_IDS = ("usd-validation-nvidia", "simready-validate")
SIMREADY_PROFILE = "PitStudio-Scene"  # defined in studio/profiles: the SimReady features that concern a composed scene
PROTECTED_RULES = frozenset(
    {
        "UnitsInMetersChecker",
        "UpAxisZChecker",
        "AnchoredAssetPathsChecker",
        "PortableAssetPathChecker",
        "layer_units_axis",
        "class_label_coverage",
        "time_sampled_labels",
        "forbidden_paths",
    }
)  # FR-004-37: units, up axis, semantic labels and asset paths can never be waived
SELECTION_KEYS = ("pushback", "scenario", "time_of_day", "weather", "lod")
LOCK = Path(__file__).resolve().parents[4] / "uv.lock"
PROFILES = Path(__file__).resolve().parents[4] / "profiles"
Runner = Callable[[Path, Mapping[str, str]], list[dict[str, Any]]]


@dataclass
class ValidationOutcome:
    """The validated scene: report (DC-004-07), updated manifest, folder, error class and message, verdict."""

    report: dict[str, Any]
    manifest: dict[str, Any]
    scene_dir: Path
    error_class: str | None
    message: str
    passed: bool


def lock_version(package: str) -> str | None:
    """The version of `package` in `studio/uv.lock`, or None."""
    try:
        lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    except OSError, tomllib.TOMLDecodeError:
        return None
    return next((p["version"] for p in lock.get("package", []) if p["name"] == package), None)


# ----------------------------------------------------------------------------------------------------------------
# the two validators
# ----------------------------------------------------------------------------------------------------------------
def _staged(root: Path, selection: Mapping[str, str]) -> Any:
    from pxr import Usd

    stage = Usd.Stage.Open(str(root))
    world = stage.GetPrimAtPath("/World")
    for name, value in selection.items():
        world.GetVariantSet(name).SetVariantSelection(value)
    return stage


def _severity(value: Any) -> str:
    name = str(getattr(value, "name", value)).lower()
    if name in ("error", "failure"):
        return "error"
    if name == "warning":
        return "warning"
    return "info"


def _nvidia_runner(root: Path, selection: Mapping[str, str]) -> list[dict[str, Any]]:
    import usd_validation_nvidia as uvn  # imported at call time: a missing or crashing package is a "not run"

    engine = uvn.ValidationEngine()
    for rule in list(engine.rules):  # the SimReady tier registers its own rules in the same engine: keep this package's
        if not getattr(rule, "__module__", "").startswith("usd_validation_nvidia"):
            engine.disable_rule(rule)
    result = engine.validate(_staged(root, selection))
    out: list[dict[str, Any]] = []
    for issue in result.issues():
        at = getattr(issue, "at", None)
        path = str(getattr(at, "path", "") or "")
        rule = issue.rule
        out.append(
            {
                "rule": getattr(rule, "__name__", str(rule)),
                "severity": _severity(issue.severity),
                "prim": path.split(".", 1)[0] if path.startswith("/") else None,
                "message": str(issue.message),
            }
        )
    return out


def _simready_runner(root: Path, selection: Mapping[str, str]) -> list[dict[str, Any]]:
    import simready.foundation.tier_core as tier
    import simready.validate as sv  # imported at call time

    base = Path(tier.__file__).parent
    sv.initialize(
        rules_and_requirements_paths=[base / "capabilities"],
        features_paths=[base / "features"],
        profiles_paths=[base / "profiles", PROFILES],
    )
    try:
        result = sv.validate_stage(_staged(root, selection), profile_id=SIMREADY_PROFILE, asset_path=str(root))
        if result is None:
            raise RuntimeError(f"SimReady profile {SIMREADY_PROFILE} is not registered")
        out = []
        for feature, data in result.features_summary.items():
            if not data["passed"]:
                failing = str(data.get("failing requirements") or "")
                out.append(
                    {
                        "rule": feature,
                        "severity": "error",
                        "prim": None,
                        "message": f"feature failed: {failing or 'see report'}",
                    }
                )
        return out
    finally:
        sv.destroy()


DEFAULT_RUNNERS: dict[str, Runner] = {"usd-validation-nvidia": _nvidia_runner, "simready-validate": _simready_runner}
PACKAGES = {"usd-validation-nvidia": "usd-validation-nvidia", "simready-validate": "simready-validate"}


def _clean(result: Mapping[str, Any], waived_rules: set[str]) -> dict[str, Any]:
    message = common.scrub(str(result.get("message") or "(no message)")).replace("\n", " ")[:300] or "(no message)"
    prim = result.get("prim")
    return {
        "rule": str(result["rule"])[:128],
        "severity": result.get("severity", "info"),
        "prim": prim if isinstance(prim, str) and prim.startswith("/") else None,
        "message": message,
        "waived": str(result["rule"]) in waived_rules,
    }


def _run_validators(
    root: Path, selections: list[dict[str, str]], runners: Mapping[str, Runner] | None, waived_rules: set[str]
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for vid in VALIDATOR_IDS:
        runner = (runners or {}).get(vid) or DEFAULT_RUNNERS[vid]
        record: dict[str, Any] = {"id": vid, "version": lock_version(PACKAGES[vid]), "status": "ran", "results": []}
        try:
            for selection in selections:
                record["results"].extend(_clean(r, waived_rules) for r in runner(root, selection))
        except Exception as error:  # an unavailable or crashing validator is "not run", never a pass
            reason = common.scrub(f"{type(error).__name__}: {error}").replace("\n", " ").strip()
            record = {
                "id": vid,
                "version": record["version"],
                "status": "not_run",
                "reason": reason[:300] or "the validator could not run",
                "results": [],
            }
        runs.append(record)
    return runs


# ----------------------------------------------------------------------------------------------------------------
# build twice
# ----------------------------------------------------------------------------------------------------------------
def _text_of(path: Path, fmt: str) -> str:
    from pxr import Sdf

    if fmt == "usda":
        return path.read_text(encoding="utf-8")
    return str(Sdf.Layer.FindOrOpen(str(path)).ExportToString())


def _first_difference(a: str, b: str) -> dict[str, Any]:
    for number, (x, y) in enumerate(itertools.zip_longest(a.splitlines(), b.splitlines(), fillvalue=""), start=1):
        if x != y:
            return {"line": number, "first": x[:300], "second": y[:300]}
    return {"line": 1, "first": a[:300], "second": b[:300]}


def _determinism(first: Path, second: Path, entries: list[dict[str, Any]]) -> dict[str, Any]:
    layers = []
    for entry in entries:
        fmt = entry["format"]
        text1, text2 = _text_of(first / entry["path"], fmt), _text_of(second / entry["path"], fmt)
        h1, h2 = common.sha256_bytes(text1.encode("utf-8")), common.sha256_bytes(text2.encode("utf-8"))
        if fmt == "usda":
            h1, h2 = common.sha256_file(first / entry["path"]), common.sha256_file(second / entry["path"])
        item: dict[str, Any] = {
            "role": entry["role"],
            "path": entry["path"],
            "format": fmt,
            "method": "bytes" if fmt == "usda" else "flattened-text",
            "first_sha256": h1,
            "second_sha256": h2,
            "equal": h1 == h2,
        }
        if h1 != h2:
            item["first_difference"] = _first_difference(text1, text2)
        layers.append(item)
    pairs = sorted((layer["role"], layer["first_sha256"]) for layer in layers)
    stage_hash = common.sha256_bytes(json.dumps([[r, h] for r, h in pairs], separators=(",", ":")).encode("utf-8"))
    return {
        "class": "bitwise",
        "layers": layers,
        "identical": all(layer["equal"] for layer in layers),
        "stage_hash": stage_hash,
    }


def _selections(spec: Mapping[str, Any]) -> list[dict[str, str]]:
    base = {name: spec["variants"][name][0] for name in SELECTION_KEYS}
    return [{**base, "lod": lod} for lod in spec["variants"]["lod"]]


def validate_scene(
    spec: Mapping[str, Any],
    build_scene: Callable[[Path], Any],
    work_dir: Path | str,
    *,
    runners: Mapping[str, Runner] | None = None,
    write: bool = True,
) -> ValidationOutcome:
    """Validate a scene: waivers, validators per variant selection, invariants and the build-twice comparison.

    `build_scene(out_dir)` builds the scene into the fresh folder it is given and returns the `SceneBuild`; it runs
    twice
    (`work_dir/build1`, `work_dir/build2`). A protected rule cannot be waived (`waiver-forbidden`, before any
    validator runs); a validator that cannot run makes the validation `incomplete`; any layer difference between the two
    builds is `nondeterministic`.
    """
    waivers = list((spec.get("validation") or {}).get("waivers", []))
    for waiver in waivers:
        if waiver["rule"] in PROTECTED_RULES:
            raise SceneStageError(
                "waiver-forbidden",
                f"the rule {waiver['rule']} (units, up axis, labels or asset paths) cannot be waived",
            )
    work = Path(work_dir)
    first_dir, second_dir = work / "build1", work / "build2"
    first = build_scene(first_dir)
    second = build_scene(second_dir)
    del second
    manifest = json.loads(json.dumps(first.manifest))
    waived_rules = {w["rule"] for w in waivers}
    validators = _run_validators(first.root, _selections(spec), runners, waived_rules)
    invariants = compute_invariants(first_dir, spec)
    determinism = _determinism(first_dir, second_dir, manifest["layers"])
    incomplete = any(v["status"] == "not_run" for v in validators)
    failed_results = [r for v in validators for r in v["results"] if r["severity"] == "error" and not r["waived"]]
    passed = (
        not incomplete
        and not failed_results
        and all(inv["passed"] for inv in invariants.values())
        and determinism["identical"]
    )
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "kind": "scene-validation-report",
        "case": spec["case"],
        "manifest_id": manifest["manifest_id"],
        "params_sha256": manifest["params_sha256"],
        "status": "incomplete" if incomplete else "complete",
        "passed": bool(passed),
        "validators": validators,
        "selections": _selections(spec),
        "invariants": invariants,
        "waivers": [dict(w) for w in waivers],
        "determinism": determinism,
        "fixture": bool(manifest.get("fixture", False)),
    }
    error_class: str | None = None
    message = "validation passed" if passed else "validation failed"
    if incomplete:
        broken = next(v for v in validators if v["status"] == "not_run")
        error_class = "validation-incomplete"
        message = f"validation-incomplete: {broken['id']} not run ({broken['reason']})"
    elif not determinism["identical"]:
        error_class = "nondeterministic"
        differing = [layer for layer in determinism["layers"] if not layer["equal"]]
        names = ", ".join(layer["path"] for layer in differing)
        diff = differing[0]["first_difference"]
        message = (
            f"nondeterministic: {names} differ between the two builds; "
            f"first differing line {diff['line']} of {differing[0]['path']}"
        )
    elif failed_results:
        message = (
            f"validation failed: {len(failed_results)} unwaived error result(s), first {failed_results[0]['rule']}"
        )
    elif not passed:
        failing = [name for name, inv in invariants.items() if not inv["passed"]]
        message = f"validation failed: invariant(s) {', '.join(failing)}"
    report_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    manifest["validation"] = {
        "status": "incomplete" if incomplete else "complete",
        "report": {
            "path": "validation/scene-validation-report.json",
            "sha256": common.sha256_bytes(report_text.encode("utf-8")),
        },
    }
    if write:
        target = first_dir / "validation" / "scene-validation-report.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report_text, encoding="utf-8", newline="\n")
        (first_dir / "scene.manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
    return ValidationOutcome(report, manifest, first_dir, error_class, common.scrub(message)[:300], bool(passed))


# ----------------------------------------------------------------------------------------------------------------
# stage
# ----------------------------------------------------------------------------------------------------------------
def _body(ctx: StageContext) -> str:
    from pitstudio_studio.scene.compose.build import compose_scene, upstream_from_results

    roots = common.job_roots()
    if not roots:
        raise SceneStageError("input-path", "no store or data root is configured for the job inputs")
    upstream = upstream_from_results(ctx.inputs, roots)
    spec = ctx.params
    scratch = ctx.work / "_builds"
    outcome = validate_scene(spec, lambda out: compose_scene(spec, upstream, out), scratch)
    if outcome.error_class:
        raise SceneStageError(outcome.error_class, outcome.message.split(": ", 1)[-1])
    if not outcome.passed:
        raise SceneStageError("validation-failed", outcome.message.removeprefix("validation failed: "))
    shutil.copytree(outcome.scene_dir, ctx.work / "scene")
    shutil.rmtree(scratch)
    return f"scene validated, stage hash {outcome.report['determinism']['stage_hash'][:12]}"


def run(job: Mapping[str, Any]) -> StageRun:
    """The stage entry `pitstudio_studio.scene.validate`: job spec in, stage result out (see `common.run_stage`)."""
    return common.run_stage(job, _body)
