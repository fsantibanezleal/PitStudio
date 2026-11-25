"""T-019-004: `tools/check_showcase.py`, the showcase honesty rules checked in CI.

Requirements: FR-019-33 (done needs an artefact), FR-019-43 (not-yet-run with an artefact), FR-019-34 (outputs only and
file guards), FR-019-35 (our scenes), FR-019-36 (local-only scrub), P-019-03 (honesty monotonicity), P-019-04
(local-only leak detection), FR-000-07, FR-000-08.

Spec: specs/019-web-studio/ (spec.md section 3.5, DC-019-03 honesty report; plan.md test strategy rows FR-019-33,
FR-019-34, FR-019-35, FR-019-36, FR-019-43, P-019-03, P-019-04).

Expected API of the implementation (module `tools/check_showcase.py`, imported through `sys.path`):
  Finding                 an object with attributes `check` (one of the six ids of DC-019-03: "done-needs-artefact",
                          "not-yet-run-has-artefact", "outputs-only", "our-scenes", "local-only-scrub",
                          "file-guards"), `subject` (tool id, artefact id, or the repository-relative POSIX path of
                          a file), `detail` (text naming the artefact / reason), `pointer` (JSON pointer of the field
                          for "local-only-scrub", otherwise None).
  check_done_needs_artefact(tools, artefacts) -> list[Finding]            FR-019-33
  check_not_yet_run_has_artefact(tools, artefacts) -> list[Finding]       FR-019-43 (detail names the artefact)
  check_outputs_only(tools, artefacts) -> list[Finding]                   FR-019-34, kinds outside the allowed set
  check_our_scenes(tools, artefacts) -> list[Finding]                     FR-019-35
  check_local_only_scrub(doc, file="run-card") -> list[Finding]           FR-019-36 on a run card or a published
                                                                          telemetry document
  check_file_guards(root: Path) -> list[Finding]                          FR-019-34 file guards over a tree
  `tools` is the list of registry entries (studio/tools.yaml, DC-001-03), `artefacts` the list of web-manifest
  artefact records (DC-000-01).
  CLI: `python tools/check_showcase.py --root DIR` reads DIR/studio/tools.yaml, DIR/web/public/assets/manifest.json,
  DIR/web/public/assets/runs/*/manifest.json and telemetry.json, runs the six checks and prints one line per finding
  "<check>: <subject>: <detail>"; exit 0 when clean, 1 with findings, 2 on a usage error or an unreadable file (message
  naming the file, never a traceback).

Choices fixed here by the test author (flagged in the red report): (a) a "numeric metric or telemetry value of a
local-only stage" is a number (not a bool) in the stage fields `wall_s`, `throughput`, `telemetry` and
`attempts[*].duration_s` of a run card, or under `points` of a published-telemetry stage; (b) the file-guard markers
are listed in MARKERS below (documented cache locations of CUDA, Warp, PyTorch extensions, Triton, Omniverse shaders;
the licence-header lines of the kit-app-template; `omniverse://`), matched on source and asset files and never on
`docs/`; (c) `check_our_scenes` follows `inputs[*]` entries of kind `artefact` through the artefact ids of the manifest.

Oracles: hand-built registries, manifests and run cards with known expected findings; for the properties, the expected
set is built by construction next to the generated input (no run of the tool under test).
"""

from __future__ import annotations

import copy
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "check_showcase.py"
sys.path.insert(0, str(ROOT / "tools"))

SHA = "a" * 64
ALLOWED_KINDS = {"image", "video", "point-cloud", "table", "text"}


def _mod():
    assert TOOL.is_file(), "tools/check_showcase.py exists (T-019-004)"
    import check_showcase

    return check_showcase


def tool(tid: str, status: str = "not-yet-run", licence_class: str = "own", **over) -> dict:
    base = {
        "id": tid,
        "name": tid,
        "category": "studio-tool",
        "envs": ["studio"],
        "version": {"own": True},
        "spdx": ["Apache-2.0"],
        "osi": True,
        "licence_class": licence_class,
        "ring": "Adopt",
        "lane": "replay",
        "performance": "public",
        "role": "a role",
        "cases": [],
        "produces": [],
        "status": status,
    }
    base.update(over)
    return base


def artefact(aid: str, tool_id: str, kind: str = "table", stage: str = "s30_train", inputs=None) -> dict:
    return {
        "id": aid,
        "run_id": "20261011T083000Z-a1",
        "git_sha": "0" * 40,
        "path": f"artefacts/{aid}.json",
        "bytes": 10,
        "sha256": SHA,
        "kind": kind,
        "producer": {"tool": tool_id, "stage": {"id": stage}},
        "inputs": inputs or [],
        "lane": "static",
        "licence_class": "own",
        "spdx": "Apache-2.0",
        "asset_host": "git",
        "budget_class": "own-code",
    }


def pairs(findings) -> set[tuple[str, str]]:
    return {(f.check, f.subject) for f in findings}


# --------------------------------------------------------------------------------------------------------------------
# FR-019-33, FR-019-43, P-019-03
# --------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-019-33")
def test_done_without_artefact_fails_naming_the_tool() -> None:
    m = _mod()
    found = m.check_done_needs_artefact([tool("warp", "done"), tool("newton", "done")], [artefact("a", "newton")])
    assert pairs(found) == {("done-needs-artefact", "warp")}


@pytest.mark.req("FR-019-33")
def test_done_with_an_artefact_passes_and_other_statuses_are_not_judged() -> None:
    m = _mod()
    tools = [
        tool("warp", "done"),
        tool("newton", "not-yet-run"),
        tool("cuopt", "evaluated-not-adopted", reason="x" * 30, docs_page="docs/frameworks/not-adopted-cuopt.md"),
    ]
    assert m.check_done_needs_artefact(tools, [artefact("a", "warp")]) == []


@pytest.mark.req("FR-019-33")
def test_empty_registry_and_empty_manifest_are_clean_and_unknown_producers_are_ignored() -> None:
    m = _mod()
    assert m.check_done_needs_artefact([], []) == []
    assert m.check_done_needs_artefact([], [artefact("a", "no-such-tool")]) == []
    assert pairs(m.check_done_needs_artefact([tool("warp", "done")], [artefact("a", "no-such-tool")])) == {
        ("done-needs-artefact", "warp")
    }


@pytest.mark.req("FR-019-33")
def test_unicode_and_long_tool_ids_are_reported_verbatim() -> None:
    m = _mod()
    found = m.check_done_needs_artefact([tool("hélice-中", "done")], [])
    assert pairs(found) == {("done-needs-artefact", "hélice-中")}


@pytest.mark.req("FR-019-43")
def test_not_yet_run_with_an_artefact_fails_naming_the_tool_and_the_artefact() -> None:
    m = _mod()
    found = m.check_not_yet_run_has_artefact(
        [tool("warp", "not-yet-run"), tool("newton", "not-yet-run")],
        [artefact("a1-granular", "warp"), artefact("a1-granular-2", "warp")],
    )
    assert pairs(found) == {("not-yet-run-has-artefact", "warp")}
    detail = " ".join(f.detail for f in found)
    assert "a1-granular" in detail


@pytest.mark.req("FR-019-43")
def test_not_yet_run_without_artefact_and_done_with_artefact_pass() -> None:
    m = _mod()
    tools = [tool("warp", "not-yet-run"), tool("newton", "done")]
    assert m.check_not_yet_run_has_artefact(tools, [artefact("a", "newton")]) == []


_STATUS = st.sampled_from(["not-yet-run", "done", "evaluated-not-adopted"])
_IDS = st.sampled_from(["t0", "t1", "t2", "t3", "t4", "t5"])


@st.composite
def _registry_and_manifest(draw):
    ids = draw(st.lists(_IDS, min_size=0, max_size=6, unique=True))
    tools = [tool(i, draw(_STATUS)) for i in ids]
    makers = draw(st.lists(st.sampled_from([*ids, "unknown"]), min_size=0, max_size=12))
    arts = [artefact(f"art-{n}", maker) for n, maker in enumerate(makers)]
    return tools, arts


@pytest.mark.req("P-019-03")
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=_registry_and_manifest(), extra=st.sampled_from(["t0", "t1", "t2", "t3", "t4", "t5", "unknown"]))
def test_p_019_03_adding_an_artefact_never_creates_a_done_needs_artefact_failure(data, extra) -> None:
    m = _mod()
    tools, arts = data
    before = pairs(m.check_done_needs_artefact(tools, arts))
    after = pairs(m.check_done_needs_artefact(tools, [*arts, artefact("extra", extra)]))
    assert after <= before
    # and the failing set is exactly the done tools without an artefact (hand definition)
    makers = {a["producer"]["tool"] for a in arts}
    assert before == {
        ("done-needs-artefact", t["id"]) for t in tools if t["status"] == "done" and t["id"] not in makers
    }


@pytest.mark.req("P-019-03")
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=_registry_and_manifest())
def test_p_019_03_removing_the_only_artefact_of_a_done_tool_makes_it_fail(data) -> None:
    m = _mod()
    tools, arts = data
    for t in tools:
        if t["status"] != "done":
            continue
        mine = [a for a in arts if a["producer"]["tool"] == t["id"]]
        if len(mine) == 1:
            rest = [a for a in arts if a is not mine[0]]
            assert ("done-needs-artefact", t["id"]) in pairs(m.check_done_needs_artefact(tools, rest))


@pytest.mark.req("P-019-03")
@settings(max_examples=100, deadline=None)
@given(data=_registry_and_manifest(), seed=st.integers(0, 10_000))
def test_p_019_03_the_result_does_not_depend_on_the_order_of_tools_and_artefacts(data, seed) -> None:
    m = _mod()
    tools, arts = data
    rng = random.Random(seed)
    t2, a2 = tools[:], arts[:]
    rng.shuffle(t2)
    rng.shuffle(a2)
    assert pairs(m.check_done_needs_artefact(tools, arts)) == pairs(m.check_done_needs_artefact(t2, a2))
    assert pairs(m.check_not_yet_run_has_artefact(tools, arts)) == pairs(m.check_not_yet_run_has_artefact(t2, a2))


# --------------------------------------------------------------------------------------------------------------------
# FR-019-34 outputs only, FR-019-35 our scenes
# --------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-019-34")
@pytest.mark.parametrize("kind", sorted(ALLOWED_KINDS))
def test_reference_only_tool_may_publish_the_allowed_kinds(kind: str) -> None:
    m = _mod()
    tools = [tool("ovrtx", "done", licence_class="reference-only")]
    assert m.check_outputs_only(tools, [artefact("a", "ovrtx", kind=kind)]) == []


@pytest.mark.req("FR-019-34")
@pytest.mark.parametrize(
    "kind", ["mesh", "tiles", "splat", "onnx", "shard", "field", "figure", "trace", "model-card", "telemetry", "usd"]
)
def test_reference_only_tool_with_any_other_kind_fails_naming_the_artefact(kind: str) -> None:
    m = _mod()
    tools = [tool("ovrtx", "done", licence_class="reference-only")]
    found = m.check_outputs_only(tools, [artefact("a-bad", "ovrtx", kind=kind)])
    assert pairs(found) == {("outputs-only", "a-bad")}
    assert "ovrtx" in found[0].detail


@pytest.mark.req("FR-019-34")
def test_other_licence_classes_may_publish_any_kind() -> None:
    m = _mod()
    tools = [tool("warp", "done", licence_class="attribution")]
    assert m.check_outputs_only(tools, [artefact("a", "warp", kind="shard"), artefact("b", "warp", kind="mesh")]) == []


@pytest.mark.req("FR-019-35")
@pytest.mark.parametrize("kind", ["image", "video"])
def test_render_without_a_scene_composition_input_fails_naming_the_artefact(kind: str) -> None:
    m = _mod()
    tools = [tool("isaac-sim-replicator", "done", licence_class="reference-only")]
    arts = [artefact("render-1", "isaac-sim-replicator", kind=kind, stage="st55_sdg")]
    assert pairs(m.check_our_scenes(tools, arts)) == {("our-scenes", "render-1")}


@pytest.mark.req("FR-019-35")
def test_render_that_descends_from_the_scene_composition_stage_passes() -> None:
    m = _mod()
    tools = [tool("isaac-sim-replicator", "done", licence_class="reference-only"), tool("openusd", "done")]
    scene = artefact("pit-scene", "openusd", kind="table", stage="st40_compose")
    render = artefact(
        "render-1",
        "isaac-sim-replicator",
        kind="image",
        stage="st55_sdg",
        inputs=[{"id": "pit-scene", "sha256": SHA, "kind": "artefact"}],
    )
    assert m.check_our_scenes(tools, [scene, render]) == []


@pytest.mark.req("FR-019-35")
def test_a_source_or_knowledge_input_is_not_a_scene_and_unknown_inputs_do_not_count() -> None:
    m = _mod()
    tools = [tool("isaac-sim-replicator", "done", licence_class="reference-only")]
    render = artefact(
        "render-1",
        "isaac-sim-replicator",
        kind="image",
        stage="st55_sdg",
        inputs=[
            {"id": "usgs-3dep-bingham", "sha256": SHA, "kind": "source"},
            {"id": "not-in-manifest", "sha256": SHA, "kind": "artefact"},
        ],
    )
    assert pairs(m.check_our_scenes(tools, [render])) == {("our-scenes", "render-1")}


@pytest.mark.req("FR-019-35")
def test_only_images_and_videos_of_reference_only_tools_need_a_scene() -> None:
    m = _mod()
    tools = [tool("ovrtx", "done", licence_class="reference-only"), tool("warp", "done", licence_class="attribution")]
    arts = [
        artefact("pc", "ovrtx", kind="point-cloud", stage="st53_sensors"),
        artefact("tab", "ovrtx", kind="table", stage="st53_sensors"),
        artefact("warp-video", "warp", kind="video", stage="st50_physics"),
    ]
    assert m.check_our_scenes(tools, arts) == []


# --------------------------------------------------------------------------------------------------------------------
# FR-019-36, P-019-04: local-only scrub
# --------------------------------------------------------------------------------------------------------------------
def _stage(sid: str, performance: str = "public", **over) -> dict:
    base = {
        "key": {"id": sid},
        "tool": "pytorch",
        "cache": "miss",
        "status": "succeeded",
        "exit_code": 0,
        "error_class": None,
        "attempts": [{"n": 1, "error_class": None}],
        "performance": performance,
        "outputs": [],
        "inputs": [],
    }
    base.update(over)
    return base


def _card(*stages) -> dict:
    return {"kind": "run", "run_id": "20261011T083000Z-a1", "stages": list(stages)}


@pytest.mark.req("FR-019-36")
def test_the_valid_example_run_card_is_clean() -> None:
    m = _mod()
    card = json.loads((ROOT / "specs/001-contracts/contracts/examples/manifest.valid.json").read_text("utf-8"))
    assert m.check_local_only_scrub(card, file="runs/x/manifest.json") == []


@pytest.mark.req("FR-019-36")
def test_planted_numbers_in_a_local_only_stage_are_reported_by_pointer_and_file() -> None:
    m = _mod()
    card = _card(
        _stage("st53_sensors", "local-only", wall_s=12.5, throughput={"value": 3.0, "unit": "frames/s"}),
        _stage("s30_train", "public", wall_s=99.0, telemetry={"energy_j": 5.0}),
    )
    found = m.check_local_only_scrub(card, file="runs/r1/manifest.json")
    assert {f.pointer for f in found} == {"/stages/0/wall_s", "/stages/0/throughput/value"}
    assert {f.subject for f in found} == {"runs/r1/manifest.json"}
    assert {f.check for f in found} == {"local-only-scrub"}


@pytest.mark.req("FR-019-36")
def test_telemetry_attempt_durations_and_nested_numbers_of_a_local_only_stage_are_reported() -> None:
    m = _mod()
    card = _card(
        _stage(
            "st45b_kit_validate",
            "local-only",
            attempts=[{"n": 1, "error_class": "oom", "duration_s": 4.0}, {"n": 2, "error_class": None}],
            telemetry={"gpu_busy_pct": {"mean": 61.2, "p50": 63.0, "p95": 88.5}, "energy_j": 3034.5, "sample_hz": 2},
        )
    )
    got = {f.pointer for f in m.check_local_only_scrub(card, file="f")}
    assert got == {
        "/stages/0/attempts/0/duration_s",
        "/stages/0/telemetry/gpu_busy_pct/mean",
        "/stages/0/telemetry/gpu_busy_pct/p50",
        "/stages/0/telemetry/gpu_busy_pct/p95",
        "/stages/0/telemetry/energy_j",
        "/stages/0/telemetry/sample_hz",
    }


@pytest.mark.req("FR-019-36")
def test_the_licence_sentence_and_booleans_and_null_are_not_numbers() -> None:
    m = _mod()
    card = _card(
        _stage(
            "st53_sensors",
            "local-only",
            telemetry="measured locally, not published (licence)",
            thermal_flag=False,
            wall_s=None,
        )
    )
    assert m.check_local_only_scrub(card, file="f") == []


@pytest.mark.req("FR-019-36")
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0, 0, 1e308])
def test_non_finite_and_extreme_numbers_in_a_local_only_stage_are_still_reported(value: float) -> None:
    m = _mod()
    card = _card(_stage("st53_sensors", "local-only", wall_s=value))
    assert [f.pointer for f in m.check_local_only_scrub(card, file="f")] == ["/stages/0/wall_s"]


@pytest.mark.req("FR-019-36")
def test_published_telemetry_of_a_local_only_stage_must_hold_no_points() -> None:
    m = _mod()
    doc = {
        "run_id": "r",
        "stages": [
            {"key": {"id": "st50_physics"}, "performance": "public", "bucket_s": 2.0, "points": [{"t_s": 0.0}]},
            {
                "key": {"id": "st53_sensors"},
                "performance": "local-only",
                "bucket_s": 2.0,
                "points": [{"t_s": 0.0, "util_pct": 10.0, "power_w": None}],
            },
        ],
    }
    got = {f.pointer for f in m.check_local_only_scrub(doc, file="runs/r/telemetry.json")}
    assert got == {"/stages/1/points/0/t_s", "/stages/1/points/0/util_pct"}


@pytest.mark.req("FR-019-36")
def test_malformed_documents_do_not_raise() -> None:
    m = _mod()
    for doc in (
        {},
        {"stages": None},
        {"stages": "x"},
        {"stages": [None, 3, "a"]},
        {"stages": [{"performance": "local-only"}]},
    ):
        assert m.check_local_only_scrub(doc, file="f") == []


_NUM = st.one_of(
    st.integers(-(10**6), 10**6),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.sampled_from([float("nan"), float("inf")]),
)


@st.composite
def _cards_with_plants(draw):
    """A run card and, by construction, the set of pointers of the numbers planted in local-only stages."""
    stages, planted = [], set()
    for i in range(draw(st.integers(0, 6))):
        local = draw(st.booleans())
        stage = _stage(f"s{i}", "local-only" if local else "public")
        if draw(st.booleans()):
            stage["wall_s"] = draw(_NUM)
            if local:
                planted.add(f"/stages/{i}/wall_s")
        if draw(st.booleans()):
            stage["throughput"] = {"value": draw(_NUM), "unit": "x/s"}
            if local:
                planted.add(f"/stages/{i}/throughput/value")
        if draw(st.booleans()):
            keys = draw(st.lists(st.sampled_from(["energy_j", "temp_c_max", "n_samples", "sample_hz"]), unique=True))
            stage["telemetry"] = {k: draw(_NUM) for k in keys}
            if local:
                planted.update(f"/stages/{i}/telemetry/{k}" for k in keys)
        if draw(st.booleans()):
            stage["attempts"] = [{"n": 1, "error_class": None, "duration_s": draw(_NUM)}]
            if local:
                planted.add(f"/stages/{i}/attempts/0/duration_s")
        stages.append(stage)
    return _card(*stages), planted


def _shuffle_keys(obj, rng: random.Random):
    if isinstance(obj, dict):
        items = [(k, _shuffle_keys(v, rng)) for k, v in obj.items()]
        rng.shuffle(items)
        return dict(items)
    if isinstance(obj, list):
        return [_shuffle_keys(v, rng) for v in obj]
    return obj


@pytest.mark.req("P-019-04")
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=_cards_with_plants(), seed=st.integers(0, 10_000))
def test_p_019_04_reports_exactly_the_planted_fields_and_is_invariant_to_key_order(data, seed) -> None:
    m = _mod()
    card, planted = data
    got = m.check_local_only_scrub(card, file="f")
    assert {f.pointer for f in got} == planted
    assert len(got) == len(planted), "each planted field is reported once"
    shuffled = _shuffle_keys(copy.deepcopy(card), random.Random(seed))
    assert {f.pointer for f in m.check_local_only_scrub(shuffled, file="f")} == planted


# --------------------------------------------------------------------------------------------------------------------
# FR-019-34 file guards
# --------------------------------------------------------------------------------------------------------------------
HEADER_SPDX = "# SPDX-License-Identifier: LicenseRef-NvidiaProprietary\n"
HEADER_TEXT = (
    "# NVIDIA CORPORATION and its licensors retain all intellectual property and proprietary rights in and to this\n"
    "# software, related documentation and any modifications thereto.\n"
)
MARKERS: dict[str, tuple[str, bytes]] = {
    "engine": ("models/pit.engine", b"\x00"),
    "plan": ("models/pit.plan", b"\x00"),
    "trt": ("models/pit.trt", b"\x00"),
    "gguf": ("models/reason.gguf", b"GGUF"),
    "cuda-cache": (".nv/ComputeCache/ab/cd01.bin", b"\x00"),
    "torch-extension": ("build/torch_extensions/py314_cu130/ext/ext.so", b"\x00"),
    "warp-cache": ("cache/warp/1.9.0/bin/kernel.so", b"\x00"),
    "triton-cache": (".triton/cache/abc/kernel.ptx", b"\x00"),
    "omniverse-shader-cache": ("ov/cache/shadercache/x.bin", b"\x00"),
    "header-spdx": ("studio/kit/app.py", (HEADER_SPDX + "print('x')\n").encode()),
    "header-text": ("studio/kit/other.py", (HEADER_TEXT + "print('x')\n").encode()),
    "omniverse-url-json": ("web/public/assets/scene.json", b'{"ref": "omniverse://localhost/Projects/pit.usd"}'),
    "omniverse-url-kit": ("studio/kit/app.kit", b'[dependencies]\n"x" = {url = "omniverse://host/path"}\n'),
}


def _write(root: Path, rel: str, data: bytes) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


@pytest.mark.req("FR-019-34")
@pytest.mark.parametrize("name", sorted(MARKERS))
def test_each_guarded_file_is_found_and_named(tmp_path: Path, name: str) -> None:
    m = _mod()
    rel, data = MARKERS[name]
    _write(tmp_path, rel, data)
    _write(tmp_path, "README.md", b"clean\n")
    got = m.check_file_guards(tmp_path)
    assert pairs(got) == {("file-guards", rel)}


@pytest.mark.req("FR-019-34")
def test_a_tree_with_every_marker_reports_each_file_once(tmp_path: Path) -> None:
    m = _mod()
    for rel, data in MARKERS.values():
        _write(tmp_path, rel, data)
    got = m.check_file_guards(tmp_path)
    assert sorted(f.subject for f in got) == sorted(rel for rel, _ in MARKERS.values())


@pytest.mark.req("FR-019-34")
def test_docs_prose_quoting_the_header_or_a_url_is_not_a_violation(tmp_path: Path) -> None:
    m = _mod()
    _write(
        tmp_path,
        "docs/studio/owner-acts-and-licences.md",
        (
            "The template files start with:\n\n" + HEADER_SPDX + HEADER_TEXT + "\nand open omniverse://localhost/x\n"
        ).encode(),
    )
    assert m.check_file_guards(tmp_path) == []


@pytest.mark.req("FR-019-34")
def test_the_registry_may_name_the_proprietary_spdx_id_without_being_a_header(tmp_path: Path) -> None:
    m = _mod()
    _write(tmp_path, "studio/tools.yaml", b"tools:\n  - id: ovrtx\n    spdx: [LicenseRef-NvidiaProprietary]\n")
    _write(tmp_path, "web/public/assets/manifest.json", b'{"spdx": "LicenseRef-NvidiaProprietary"}')
    assert m.check_file_guards(tmp_path) == []


@pytest.mark.req("FR-019-34")
def test_a_clean_tree_and_an_empty_tree_pass(tmp_path: Path) -> None:
    m = _mod()
    assert m.check_file_guards(tmp_path) == []
    _write(tmp_path, "src/app.py", b"print('hello')\n")
    _write(tmp_path, "web/public/assets/runs/r/manifest.json", b"{}")
    assert m.check_file_guards(tmp_path) == []


@pytest.mark.req("FR-019-34")
def test_binary_files_and_unicode_names_do_not_crash_the_scan(tmp_path: Path) -> None:
    m = _mod()
    _write(tmp_path, "assets/é中.bin", bytes(range(256)) * 40)
    _write(tmp_path, "assets/é中/model.engine", b"\x00")
    got = m.check_file_guards(tmp_path)
    assert [f.subject for f in got] == ["assets/é中/model.engine"]


@pytest.mark.req("FR-019-34")
def test_a_directory_named_like_an_engine_is_not_a_file(tmp_path: Path) -> None:
    m = _mod()
    (tmp_path / "models" / "pit.engine").mkdir(parents=True)
    assert m.check_file_guards(tmp_path) == []


# --------------------------------------------------------------------------------------------------------------------
# CLI end to end (all six checks, exit codes, no traceback)
# --------------------------------------------------------------------------------------------------------------------
def _repo(tmp_path: Path, tools: list[dict], artefacts: list[dict], cards: dict[str, dict] | None = None) -> Path:
    (tmp_path / "studio").mkdir(parents=True)
    (tmp_path / "studio" / "tools.yaml").write_text(yaml.safe_dump({"tools": tools}, sort_keys=False), encoding="utf-8")
    assets = tmp_path / "web" / "public" / "assets"
    assets.mkdir(parents=True)
    index = {
        "kind": "web-index",
        "schema_version": "1.0",
        "generated": "2026-10-11",
        "git_sha": "0" * 40,
        "runs": [],
        "artefacts": artefacts,
    }
    (assets / "manifest.json").write_text(json.dumps(index), encoding="utf-8")
    for run_id, card in (cards or {}).items():
        d = assets / "runs" / run_id
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps(card), encoding="utf-8")
    return tmp_path


def _cli(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    assert TOOL.is_file(), "tools/check_showcase.py exists (T-019-004)"
    return subprocess.run(
        [sys.executable, str(TOOL), "--root", str(root), *extra],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.req("FR-019-33")
@pytest.mark.req("FR-019-43")
@pytest.mark.req("FR-019-36")
def test_cli_clean_repo_exits_zero(tmp_path: Path) -> None:
    root = _repo(tmp_path, [tool("warp", "done"), tool("newton")], [artefact("a", "warp")])
    done = _cli(root)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Traceback" not in done.stderr


@pytest.mark.req("FR-019-33")
@pytest.mark.req("FR-019-43")
@pytest.mark.req("FR-019-34")
@pytest.mark.req("FR-019-35")
@pytest.mark.req("FR-019-36")
def test_cli_each_planted_violation_fails_with_its_check_and_subject(tmp_path: Path) -> None:
    tools = [
        tool("warp", "done"),  # done, no artefact
        tool("newton", "not-yet-run"),  # not-yet-run, has artefact
        tool("ovrtx", "done", licence_class="reference-only"),
        tool("isaac-sim-replicator", "done", licence_class="reference-only"),
    ]
    arts = [
        artefact("newton-out", "newton"),
        artefact("ovrtx-mesh", "ovrtx", kind="mesh", stage="st53_sensors"),
        artefact("isaac-render", "isaac-sim-replicator", kind="image", stage="st55_sdg"),
    ]
    card = _card(_stage("st53_sensors", "local-only", wall_s=3.0))
    root = _repo(tmp_path, tools, arts, {"20261011T083000Z-a1": card})
    _write(root, "models/pit.engine", b"\x00")
    done = _cli(root)
    assert done.returncode == 1, done.stdout + done.stderr
    out = done.stdout
    for needle in (
        "done-needs-artefact: warp",
        "not-yet-run-has-artefact: newton",
        "outputs-only: ovrtx-mesh",
        "our-scenes: isaac-render",
        "local-only-scrub: web/public/assets/runs/20261011T083000Z-a1/manifest.json",
        "file-guards: models/pit.engine",
    ):
        assert needle in out, (needle, out)
    assert "Traceback" not in done.stderr


@pytest.mark.req("FR-019-36")
def test_cli_scans_published_telemetry_files(tmp_path: Path) -> None:
    root = _repo(tmp_path, [tool("ovrtx", "not-yet-run", licence_class="reference-only")], [])
    runs = root / "web/public/assets/runs/r1"
    runs.mkdir(parents=True)
    (runs / "telemetry.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "stages": [
                    {"key": {"id": "s"}, "performance": "local-only", "bucket_s": 2.0, "points": [{"t_s": 0.0}]}
                ],
            }
        ),
        encoding="utf-8",
    )
    done = _cli(root)
    assert done.returncode == 1
    assert "web/public/assets/runs/r1/telemetry.json" in done.stdout
    assert "/stages/0/points/0/t_s" in done.stdout


@pytest.mark.req("FR-019-33")
@pytest.mark.parametrize("breakage", ["manifest", "tools", "card"])
def test_cli_unreadable_input_exits_two_naming_the_file(tmp_path: Path, breakage: str) -> None:
    root = _repo(tmp_path, [tool("warp")], [], {"r1": _card()})
    victim = {
        "manifest": root / "web/public/assets/manifest.json",
        "tools": root / "studio/tools.yaml",
        "card": root / "web/public/assets/runs/r1/manifest.json",
    }[breakage]
    victim.write_text("{ not json ::: \x00", encoding="utf-8")
    done = _cli(root)
    assert done.returncode == 2, done.stdout + done.stderr
    assert victim.name in done.stderr + done.stdout
    assert "Traceback" not in done.stderr


@pytest.mark.req("FR-019-33")
def test_cli_usage_errors_exit_two(tmp_path: Path) -> None:
    assert TOOL.is_file(), "tools/check_showcase.py exists (T-019-004)"
    bad = subprocess.run(
        [sys.executable, str(TOOL), "--no-such-flag"], capture_output=True, text=True, timeout=60, check=False
    )
    assert bad.returncode == 2
    missing = _cli(tmp_path / "nowhere")
    assert missing.returncode == 2
    assert "Traceback" not in missing.stderr


@pytest.mark.req("FR-019-33")
def test_cli_with_no_published_runs_and_an_empty_manifest_is_clean(tmp_path: Path) -> None:
    root = _repo(tmp_path, [tool("warp")], [])
    assert _cli(root).returncode == 0
