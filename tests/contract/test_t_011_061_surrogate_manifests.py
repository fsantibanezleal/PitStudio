"""T-011-061 - FR-011-45: manifests and the "calibrated synthetic" labels of every rollout, field, calibration
    dataset and surrogate artefact.

Oracles (independent of the code under test; plan 011 test strategy FR-011-45: "manifests against
    `contracts/manifest.schema.json`; label strings"):
- the manifest schema (`specs/001-contracts/contracts/manifest.schema.json`, draft of DC-000-01, reference
    implementation `jsonschema`): the
  record built for every kind validates against `$defs/artefact`, so producer tool, stage, inputs with SHA-256,
      lane and lane measurements are
  exactly the schema's;
- hashlib: `sha256` and `bytes` of the record equal those of the file computed here;
- the exact label string of FR-000-09 / FR-011-45, "calibrated synthetic — not validated against real data", for
    every kind, the literature repose
  targets being the only real-world anchor and not changing the label;
- the live gate of thresholds.yaml (`lane_gate`: LIVE iff, on T2, asset <= 25 MB, interaction <= 16 ms, run <= 1 s,
    trace <= 10 MB): a record that
  claims lane "live" while its measurements exceed one of them is refused (the lane is measured, not declared,
      FR-000-15 and FR-011-45);
- the producing tools of the spec text: Warp and Newton for the solver outputs, PyTorch for exports and cards, ONNX
    Runtime for the parity report.

Kind table used here (artefact kind of the manifest schema, producer tool, stage id, whether the lane is static):
  rollout-set          shard      warp | newton (by solver)   st50_physics  replay
  field-dataset        field      warp                         st50_physics  replay
  calibration-dataset  table      warp | newton (by solver)   st50_physics  static
  gns-onnx, fno-onnx   onnx       pytorch                      s60_export    live (measured)
  parity-report        table      onnxruntime                  s60_export    static
  model-card           model-card pytorch                      s50_evaluate  static

Expected public API (module `pitstudio.surrogate_manifests`, under `src/pitstudio/`):

    LABEL = "calibrated synthetic — not validated against real data"
    KINDS: tuple of the kind names above
    label_for(kind) -> str                      LABEL for every kind; ValueError for an unknown kind or a non-string
    artefact_record(kind, *, artefact_id, run_id, git_sha, file_path, rel_path, inputs, lane_measurements=None,
        solver=None, cases=()) -> dict
        a record valid against `$defs/artefact` of the manifest schema: producer {"tool", "stage": {"id"}} from the
            table, `path` = rel_path,
        `bytes` and `sha256` read from file_path, `inputs` as given (>= 1 entry, each {"id", "sha256", "kind"}),
            `lane` static for the static
        kinds, "replay" for the dataset kinds (rollout-set, field-dataset), and for the ONNX kinds "live" iff the
            T2 gate of `lane_measurements`
        holds, else "replay" (the lane is measured, not declared; `lane_measurements` is required for every
            non-static kind),
        `licence_class` "own", `spdx` "Apache-2.0",
        `asset_host` git (< 10 MiB) or release, `budget_class` onnx for ONNX and shards-clouds for shards and
            fields, own-code for the others.
        `solver` ("warp-dem" | "newton-mpm") is required for rollout-set and calibration-dataset. There is no
            `label` argument.
        Raises ValueError for an unknown kind, no inputs, a malformed digest, an absolute or `..` rel_path, a
            missing file, a malformed id.
    run_notes(records) -> list[str]            one note per record, "<artefact id>: <LABEL>", each <= 300
        characters, at most 20
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio import surrogate_manifests as sm  # noqa: E402

MANIFEST = json.loads(
    (ROOT / "specs" / "001-contracts" / "contracts" / "manifest.schema.json").read_text(encoding="utf-8")
)
ARTEFACT = jsonschema.Draft202012Validator(
    {"$schema": MANIFEST["$schema"], "$ref": "#/$defs/artefact", "$defs": MANIFEST["$defs"]}
)
LANE_GATE = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "lane_gate"
]
LABEL = "calibrated synthetic — not validated against real data"
RUN_ID = "20261011T120000Z-a3-surrogates"
GIT = "a" * 40
INPUT = {"id": "scene-a3", "sha256": "b" * 64, "kind": "artefact"}
MEASURED_LIVE = {
    "web_drivable": True,
    "max_asset_bytes": 3_145_728,
    "interaction_ms": 12.0,
    "run_ms_t2": 40.0,
    "trace_bytes": 2048,
    "measured": {"tier": "T2", "date": "2026-10-11", "browser": "Chromium 141"},
}
EXPECTED = {
    # kind: (artefact kind, tool, stage id, lane, budget class, needs solver)
    "rollout-set": (
        "shard",
        {"warp-dem": "warp", "newton-mpm": "newton"},
        "st50_physics",
        "replay",
        "shards-clouds",
        True,
    ),
    "field-dataset": ("field", "warp", "st50_physics", "replay", "shards-clouds", False),
    "calibration-dataset": (
        "table",
        {"warp-dem": "warp", "newton-mpm": "newton"},
        "st50_physics",
        "static",
        "own-code",
        True,
    ),
    "gns-onnx": ("onnx", "pytorch", "s60_export", "live", "onnx", False),
    "fno-onnx": ("onnx", "pytorch", "s60_export", "live", "onnx", False),
    "parity-report": ("table", "onnxruntime", "s60_export", "static", "own-code", False),
    "model-card": ("model-card", "pytorch", "s50_evaluate", "static", "own-code", False),
}


def build(tmp_path: Path, kind: str, *, solver: str | None = "warp-dem", measurements=None, **over):
    f = tmp_path / f"{kind}.bin"
    f.write_bytes(f"payload of {kind}".encode() * 100)
    needs_solver = EXPECTED[kind][5]
    kw = {
        "artefact_id": f"{kind}-a3",
        "run_id": RUN_ID,
        "git_sha": GIT,
        "file_path": f,
        "rel_path": f"data/{kind}.bin",
        "inputs": [copy.deepcopy(INPUT)],
        "cases": ("A3",),
    }
    if EXPECTED[kind][3] != "static":
        kw["lane_measurements"] = copy.deepcopy(MEASURED_LIVE) if measurements is None else measurements
    if needs_solver:
        kw["solver"] = solver
    kw.update(over)
    return sm.artefact_record(kind, **kw), f


def tool_of(kind: str, solver: str | None) -> str:
    t = EXPECTED[kind][1]
    return t[solver] if isinstance(t, dict) else t


# ------------------------------------------------------------------ the label


@pytest.mark.req("FR-011-45")
@pytest.mark.parametrize("kind", list(EXPECTED))
def test_every_kind_carries_the_calibrated_synthetic_label(kind: str) -> None:
    assert sm.label_for(kind) == LABEL
    assert sm.LABEL == LABEL


@pytest.mark.req("FR-011-45")
def test_the_kinds_are_exactly_the_documented_set() -> None:
    assert set(sm.KINDS) == set(EXPECTED)


@pytest.mark.req("FR-011-45")
@pytest.mark.parametrize("kind", ["", "checkpoint", "ROLLOUT-SET", "rollout_set", None, 3])
def test_an_unknown_kind_has_no_label(kind) -> None:
    with pytest.raises(ValueError, match=r"."):
        sm.label_for(kind)


@pytest.mark.req("FR-011-45")
def test_literature_calibrations_keep_the_same_label() -> None:
    # the literature repose targets are the only real-world anchor, and still carry the label (spec FR-011-45)
    assert sm.label_for("calibration-dataset") == LABEL


# ------------------------------------------------------------------ the records


@pytest.mark.req("FR-011-45")
@pytest.mark.parametrize("kind", list(EXPECTED))
def test_every_record_validates_against_the_manifest_schema(tmp_path: Path, kind: str) -> None:
    rec, _ = build(tmp_path, kind)
    assert [e.message for e in ARTEFACT.iter_errors(rec)] == []


@pytest.mark.req("FR-011-45")
@pytest.mark.parametrize("kind", list(EXPECTED))
def test_the_record_names_its_producing_tool_stage_lane_and_inputs(tmp_path: Path, kind: str) -> None:
    solver = "warp-dem"
    rec, _ = build(tmp_path, kind, solver=solver)
    akind, _, stage, lane, budget_class, _ = EXPECTED[kind]
    assert rec["kind"] == akind
    assert rec["producer"]["tool"] == tool_of(kind, solver)
    assert rec["producer"]["stage"]["id"] == stage
    assert rec["lane"] == lane
    assert rec["budget_class"] == budget_class
    assert rec["inputs"] == [INPUT]
    assert rec["run_id"] == RUN_ID
    assert rec["git_sha"] == GIT
    assert rec["licence_class"] == "own"
    assert rec["spdx"] == "Apache-2.0"
    assert rec["producer"]["tool"] in {"warp", "newton", "pytorch", "onnxruntime"}


@pytest.mark.req("FR-011-45")
@pytest.mark.parametrize("kind", ["rollout-set", "calibration-dataset"])
def test_newton_solver_outputs_name_newton_and_warp_outputs_name_warp(tmp_path: Path, kind: str) -> None:
    assert build(tmp_path, kind, solver="newton-mpm")[0]["producer"]["tool"] == "newton"
    assert build(tmp_path, kind, solver="warp-dem")[0]["producer"]["tool"] == "warp"


@pytest.mark.req("FR-011-45")
@pytest.mark.parametrize("kind", ["rollout-set", "calibration-dataset"])
@pytest.mark.parametrize("solver", [None, "", "chrono", "WARP-DEM"])
def test_a_solver_output_needs_a_known_solver(tmp_path: Path, kind: str, solver) -> None:
    with pytest.raises(ValueError, match="solver"):
        build(tmp_path, kind, solver=solver)


@pytest.mark.req("FR-011-45")
@pytest.mark.parametrize("kind", list(EXPECTED))
def test_digest_size_and_relative_path_come_from_the_file(tmp_path: Path, kind: str) -> None:
    rec, f = build(tmp_path, kind)
    assert rec["sha256"] == hashlib.sha256(f.read_bytes()).hexdigest()
    assert rec["bytes"] == f.stat().st_size
    assert rec["path"] == f"data/{kind}.bin"
    assert rec["id"] == f"{kind}-a3"
    assert rec["cases"] == ["A3"]


@pytest.mark.req("FR-011-45")
def test_the_live_lane_follows_the_measurements(tmp_path: Path) -> None:
    rec, _ = build(tmp_path, "gns-onnx")
    assert rec["lane"] == "live"
    assert rec["lane_measurements"] == MEASURED_LIVE
    slow = dict(MEASURED_LIVE, run_ms_t2=2500.0)  # over the 1 s gate: not live, but still a valid replay record
    rec2, _ = build(tmp_path, "fno-onnx", measurements=slow)
    assert rec2["lane"] == "replay"
    assert [e.message for e in ARTEFACT.iter_errors(rec2)] == []


@pytest.mark.req("FR-011-45")
@pytest.mark.parametrize(
    "field",
    ["max_asset_bytes", "interaction_ms", "run_ms_t2", "trace_bytes"],
)
def test_a_measurement_over_the_gate_can_never_give_the_live_lane(tmp_path: Path, field: str) -> None:
    over = {
        "max_asset_bytes": LANE_GATE["live_asset_mb_max"] * 1_000_000 + 1,
        "interaction_ms": LANE_GATE["interaction_ms_max"] + 0.5,
        "run_ms_t2": LANE_GATE["run_s_max"] * 1000 + 1.0,
        "trace_bytes": LANE_GATE["trace_mb_max"] * 1_000_000 + 1,
    }[field]
    rec, _ = build(tmp_path, "gns-onnx", measurements=dict(MEASURED_LIVE, **{field: over}))
    assert rec["lane"] != "live"


@pytest.mark.req("FR-011-45")
def test_a_non_static_kind_without_measurements_is_refused(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    with pytest.raises(ValueError, match=r"lane_measurements|measure"):
        sm.artefact_record(
            "gns-onnx",
            artefact_id="gns-x",
            run_id=RUN_ID,
            git_sha=GIT,
            file_path=f,
            rel_path="data/x.bin",
            inputs=[INPUT],
        )


@pytest.mark.req("FR-011-45")
def test_there_is_no_way_to_override_the_label(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        build(tmp_path, "model-card", label="validated against real data")


# ------------------------------------------------------------------ run notes


@pytest.mark.req("FR-011-45")
def test_run_notes_carry_the_label_for_every_artefact(tmp_path: Path) -> None:
    recs = [build(tmp_path, k)[0] for k in EXPECTED]
    notes = sm.run_notes(recs)
    assert len(notes) == len(recs) <= 20
    for rec, note in zip(recs, notes, strict=True):
        assert note == f"{rec['id']}: {LABEL}"
        assert len(note) <= 300
    assert notes == sm.run_notes(recs)


@pytest.mark.req("FR-011-45")
def test_run_notes_of_an_empty_list_is_empty() -> None:
    assert sm.run_notes([]) == []


# ------------------------------------------------------------------ hostile arguments


@pytest.mark.req("FR-011-45")
@pytest.mark.parametrize(
    ("over", "needle"),
    [
        ({"inputs": []}, "inputs"),
        ({"inputs": [{"id": "scene-a3", "sha256": "xyz", "kind": "artefact"}]}, "sha256"),
        ({"inputs": [{"id": "scene-a3", "sha256": "B" * 64, "kind": "artefact"}]}, "sha256"),
        ({"inputs": [{"id": "scene-a3", "sha256": "b" * 64, "kind": "blob"}]}, "kind"),
        ({"rel_path": "/etc/passwd"}, "rel_path"),
        ({"rel_path": "C:/data/x.bin"}, "rel_path"),
        ({"rel_path": "../x.bin"}, "rel_path"),
        ({"rel_path": "a/../../x.bin"}, "rel_path"),
        ({"rel_path": ""}, "rel_path"),
        ({"artefact_id": "Rollout Set"}, "artefact_id"),
        ({"artefact_id": "rollout-é"}, "artefact_id"),
        ({"artefact_id": ""}, "artefact_id"),
        ({"run_id": "run-1"}, "run_id"),
        ({"git_sha": "abc"}, "git_sha"),
    ],
)
def test_hostile_arguments_are_refused_naming_the_argument(tmp_path: Path, over: dict, needle: str) -> None:
    with pytest.raises(ValueError, match=needle):
        build(tmp_path, "field-dataset", **over)


@pytest.mark.req("FR-011-45")
def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="file"):
        build(tmp_path, "field-dataset", file_path=tmp_path / "absent.bin")


@pytest.mark.req("FR-011-45")
def test_an_unknown_kind_cannot_build_a_record(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    with pytest.raises(ValueError, match="kind"):
        sm.artefact_record(
            "checkpoint",
            artefact_id="x",
            run_id=RUN_ID,
            git_sha=GIT,
            file_path=f,
            rel_path="data/x.bin",
            inputs=[INPUT],
        )
