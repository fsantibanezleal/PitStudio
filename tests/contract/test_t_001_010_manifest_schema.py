"""T-001-010 · manifest kinds, artefact fields, asset hosts, local-only scrub, publication rules, encoder record.

Requirements: FR-001-10, FR-001-11, FR-001-12, FR-001-14, FR-001-16, FR-001-17.

Oracles: the normative field tables, bounds and enums of data-model 2.1-2.8 (hand-transcribed below); the conformance
corpus fixtures (verdict, pointer and keyword fixed by construction from the draft schema); python ``jsonschema`` as the
reference validator; for the checker rules (published artefact whose stage did not succeed; encoder duration versus
frames / fps) hand-built repository trees derived from the committed clean fixture repository.

Expected API: ``contracts/manifest.schema.json`` (T-001-001) and ``tools/check_contracts.py`` (T-001-030) as described
in ``contract_support``.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_support as cs

RUN_T = "#/$defs/run"
WEB_T = "#/$defs/web_index"


def load(rel: str) -> Any:
    return json.loads((cs.FIXTURES / rel).read_text(encoding="utf-8"))


RUN = load("manifest/valid/manifest.valid.json")
RUN_U = load("manifest/valid/manifest.valid-unpublished.json")
BASE_U = {**RUN, "published": False}  # the published example with the publication preconditions lifted
WEB = load("manifest/valid/manifest.valid-web-index.json")


def pairs(doc: Any, target: str = RUN_T) -> set[tuple[str, str]]:
    return cs.error_pairs("manifest", target, doc)


def ok(doc: Any, target: str = RUN_T) -> bool:
    return cs.accepts("manifest", target, doc)


def setp(doc: Any, path: list[Any], value: Any) -> Any:
    d = copy.deepcopy(doc)
    node = d
    for p in path[:-1]:
        node = node[p]
    node[path[-1]] = value
    return d


def delp(doc: Any, path: list[Any]) -> Any:
    d = copy.deepcopy(doc)
    node = d
    for p in path[:-1]:
        node = node[p]
    del node[path[-1]]
    return d


def ptr(path: list[Any]) -> str:
    return "/" + "/".join(str(p) for p in path)


def corpus_rule(rule: str) -> list[dict]:
    return [e for e in cs.schema_level(schema="manifest") if e["rule"] == rule and not e["valid"]]


def assert_corpus(rule: str, minimum: int) -> None:
    items = corpus_rule(rule)
    assert len(items) >= minimum, (rule, len(items))
    for e in items:
        got = pairs(cs.fixture_json(e), e["target"])
        assert (e["pointer"], e["keyword"]) in got, (e["file"], e["pointer"], e["keyword"], sorted(got)[:5])


# ----------------------------------------------------------------------------------------------------------------
# FR-001-10 · two document kinds, the field groups of data-model 2
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-10")
def test_fr_001_10_valid_examples_of_both_kinds_are_accepted_and_the_kind_discriminates() -> None:
    for doc, target in ((RUN, RUN_T), (RUN_U, RUN_T), (WEB, WEB_T)):
        assert ok(doc, target)
        assert ok(doc, "#")  # the root schema is the oneOf of both kinds
    assert not ok(setp(RUN, ["kind"], "web-index"), "#")
    assert not ok(setp(WEB, ["kind"], "run"), "#")
    assert not ok(delp(RUN, ["kind"]), "#")
    assert not ok(setp(RUN, ["kind"], "RUN"), "#")
    assert not ok({}, "#")


@pytest.mark.req("FR-001-10")
@pytest.mark.parametrize("good", ["1.0", "1.1", "1.12", "1.999"])
def test_fr_001_10_schema_version_accepts_1_x(good: str) -> None:
    assert ok(setp(RUN, ["schema_version"], good))
    assert ok(setp(WEB, ["schema_version"], good), WEB_T)


@pytest.mark.req("FR-001-10")
@pytest.mark.parametrize("bad", ["2.0", "1", "1.", "1.x", "01.0", "v1.0", "1.0.0", "", " 1.0", 1.0, 1, None])
def test_fr_001_10_schema_version_rejects_everything_else(bad: Any) -> None:
    assert not ok(setp(RUN, ["schema_version"], bad))
    assert not ok(setp(WEB, ["schema_version"], bad), WEB_T)


RUN_REQUIRED = [
    "kind",
    "schema_version",
    "run_id",
    "recipe",
    "git_sha",
    "git_dirty",
    "runner_version",
    "created",
    "profile",
    "seed",
    "published",
    "launcher",
    "gpu",
    "stages",
    "artefacts",
]
WEB_REQUIRED = ["kind", "schema_version", "generated", "git_sha", "runs", "artefacts"]
STAGE_REQUIRED = [
    "key",
    "tool",
    "env",
    "cache_key",
    "cache",
    "status",
    "exit_code",
    "error_class",
    "attempts",
    "params",
    "seed",
    "determinism",
    "performance",
    "telemetry",
    "thermal_flag",
    "inputs",
    "outputs",
]
STAGE_OPTIONAL = ["reason", "shards", "wall_s", "throughput", "log_tail"]


@pytest.mark.req("FR-001-10")
@pytest.mark.parametrize("field", RUN_REQUIRED)
def test_fr_001_10_every_run_field_of_data_model_2_1_is_required(field: str) -> None:
    got = pairs(delp(RUN_U, [field]))
    assert ("", "required") in got


@pytest.mark.req("FR-001-10")
@pytest.mark.parametrize("field", WEB_REQUIRED)
def test_fr_001_10_every_web_index_field_of_data_model_2_8_is_required(field: str) -> None:
    assert ("", "required") in pairs(delp(WEB, [field]), WEB_T)


@pytest.mark.req("FR-001-10")
@pytest.mark.parametrize("field", STAGE_REQUIRED)
def test_fr_001_10_every_stage_field_of_data_model_2_3_is_required(field: str) -> None:
    got = pairs(delp(RUN_U, ["stages", 0, field]))
    assert ("/stages/0", "required") in got


@pytest.mark.req("FR-001-10")
def test_fr_001_10_run_notes_and_stage_extras_are_optional_and_unknown_stage_fields_are_rejected() -> None:
    assert ok(delp(RUN, ["notes"]))
    assert ok(delp(RUN_U, ["stages", 0, "shards"]))
    assert ok(delp(RUN_U, ["stages", 0, "wall_s"]))
    assert ok(delp(RUN, ["stages", 0, "throughput"]))
    assert ok(delp(RUN, ["stages", 0, "wall_s"]))
    assert ("/stages/0", "additionalProperties") in pairs(setp(RUN, ["stages", 0, "host"], "box"))
    assert ("/stages/0/key", "additionalProperties") in pairs(setp(RUN, ["stages", 0, "key", "x"], 1))
    assert ("/recipe", "additionalProperties") in pairs(setp(RUN, ["recipe", "dir"], "x"))


# (path, accepted values, rejected values): bounds of data-model 2.1-2.4, taken from the tables
BOUNDS: list[tuple[list[Any], list[Any], list[Any]]] = [
    (["seed"], [0, 1, 2**63 - 1], [-1, 2**63, 1.5, "1", True, None]),
    (["git_dirty"], [True, False], ["false", 0, None]),
    (["launcher"], ["uv", "test"], ["docker", "", None]),
    (["runner_version"], ["0.1.0", "10.20.30"], ["0.1", "v0.1.0", "0.1.0-rc1", "", 1]),
    (["profile"], ["a", "laptop-rtx5000ada", "a" * 64], ["", "A", "a" * 65, "a_b", "a/b", "../x", "-a"]),
    (["gpu", "index"], [0, 15], [-1, 16, 0.5, "0", None]),
    (["gpu", "name"], ["x", "n" * 128], ["", "n" * 129, 1, None]),
    (["gpu", "driver"], ["582.78", "1.2.3"], ["582", "v582.78", "", "582.78a"]),
    (["gpu", "vram_total_bytes"], [0, 2**53 - 1], [-1, 2**53, 1.5, "1"]),
    (["gpu", "power_limit_enforced_w"], [0, 175.5, None], [-0.1, "175"]),
    (["stages", 0, "exit_code"], [0, -(2**31), 2**31 - 1, None], [-(2**31) - 1, 2**31, 1.5, "0"]),
    (["stages", 0, "seed"], [0, 2**63 - 1], [-1, 2**63]),
    (["stages", 0, "cache"], ["hit", "miss"], ["HIT", "", None]),
    (["stages", 0, "thermal_flag"], [True, False], ["no", None]),
    (["stages", 0, "performance"], ["public", "local-only"], ["private", None]),
    (
        ["stages", 0, "env", "name"],
        ["studio", "isaac", "rtx", "isaaclab", "kit", "reason", "pipeline", "accel", "external"],
        ["root", "web", "docker", ""],
    ),
    (["stages", 0, "env", "python"], ["3.12", "3.14.4", "3.9.123", None], ["2.7", "3", "3.14.4.1", "python3.14", ""]),
    (
        ["stages", 0, "shards"],
        [{"total": 1, "done": 0}, {"total": 10000, "done": 10000}],
        [{"total": 0, "done": 0}, {"total": 10001, "done": 0}, {"total": 1, "done": -1}, {"total": 1}, {"done": 0}],
    ),
    (["stages", 0, "attempts", 0, "n"], [1, 5], [0, 6, 1.5]),
    (["stages", 0, "attempts", 0, "duration_s"], [0, 12.5], [-0.001, "1"]),
    (["stages", 0, "determinism", "class"], ["bitwise", "statistical", "none"], ["exact", ""]),
    (["stages", 0, "determinism", "rerun_check"], ["pending", "pass", "fail", "not-applicable"], ["maybe", None]),
    (["stages", 0, "determinism", "max_deviation"], [0, 1e-9], [-1e-9, "0"]),
    (["stages", 0, "wall_s"], [0, 42.5], [-1, "42"]),
    (["stages", 0, "throughput", "value"], [0, 240.0], [-1, "240"]),
    (["stages", 0, "throughput", "unit"], ["f", "u" * 32], ["", "u" * 33]),
    (["stages", 0, "inputs"], [[]], ["x", {"id": "x"}]),
    (["stages", 0, "outputs", 0, "bytes"], [0, 5], [-1, 1.5, "5"]),
    (["stages", 0, "outputs", 0, "name"], ["a.bin", "a/b/c.bin"], ["/a", "../a", "a b", "C:/a", "a\\b", "a."]),
    (["notes"], [[], ["n" * 300], ["n"] * 20], [["n" * 301], ["n"] * 21, "note", [1]]),
]


@pytest.mark.req("FR-001-10")
@pytest.mark.parametrize(("path", "good", "bad"), BOUNDS, ids=[ptr(b[0]) for b in BOUNDS])
def test_fr_001_10_value_bounds_of_the_field_tables(path: list[Any], good: list[Any], bad: list[Any]) -> None:
    for v in good:
        assert ok(setp(BASE_U, path, v)), (ptr(path), v, sorted(pairs(setp(BASE_U, path, v)))[:3])
    for v in bad:
        got = pairs(setp(BASE_U, path, v))
        assert any(p.startswith(ptr(path)) or p == ptr(path[:-1]) for p, _ in got), (ptr(path), v, sorted(got)[:3])


TELEMETRY_BOUNDS: list[tuple[list[Any], list[Any], list[Any]]] = [
    (["sample_hz"], [1, 4, 2.5], [0.99, 4.01, 0, -1, "2"]),
    (["n_samples"], [0, 85], [-1, 1.5]),
    (["gpu_busy_pct", "mean"], [0, 100], [-0.1, 100.1]),
    (["gpu_busy_pct", "p95"], [0, 100], [-1, 101]),
    (["mem_used_peak_bytes"], [0, 2**53 - 1], [-1, 2**53]),
    (["power_w", "max"], [0, 103.2], [-1]),
    (["power_at_limit_frac"], [0, 0.5, 1], [-0.01, 1.01]),
    (["energy_j"], [0, 3034.5], [-1]),
    (["sm_clock_mhz", "p5"], [0, 1410], [-1]),
    (["temp_c_max"], [-100, 74, 200], [-100.1, 200.1]),
    (["clocks_event_frac", "sw_power_cap"], [0, 1], [-0.1, 1.1]),
    (["clocks_event_frac", "idle"], [0, 1], [-0.1, 1.1]),
    (["nvenc_util_pct", "max"], [0, 100], [-1, 100.5]),
    (["pcie_replays_delta"], [0, -3, 7], [1.5, "0"]),
]


@pytest.mark.req("FR-001-10")
@pytest.mark.parametrize(("path", "good", "bad"), TELEMETRY_BOUNDS, ids=[ptr(b[0]) for b in TELEMETRY_BOUNDS])
def test_fr_001_10_telemetry_summary_bounds_of_data_model_2_4(path: list[Any], good: list[Any], bad: list[Any]) -> None:
    full = ["stages", 0, "telemetry", *path]
    for v in good:
        assert ok(setp(RUN, full, v)), (ptr(full), v)
    for v in bad:
        assert any(p.startswith(ptr(full)) for p, _ in pairs(setp(RUN, full, v))), (ptr(full), v)


@pytest.mark.req("FR-001-10")
@pytest.mark.parametrize(
    "field",
    [
        "sample_hz",
        "n_samples",
        "gpu_busy_pct",
        "mem_used_peak_bytes",
        "power_w",
        "power_at_limit_frac",
        "energy_j",
        "sm_clock_mhz",
        "temp_c_max",
        "clocks_event_frac",
        "nvenc_util_pct",
        "pcie_replays_delta",
    ],
)
def test_fr_001_10_a_null_telemetry_field_must_be_named_in_unavailable_with_a_reason(field: str) -> None:
    unexplained = setp(RUN, ["stages", 0, "telemetry", field], None)
    assert not ok(unexplained)
    explained = setp(
        unexplained, ["stages", 0, "telemetry", "unavailable"], {field: "counter not exposed by the driver"}
    )
    assert ok(explained), sorted(pairs(explained))[:3]
    long_reason = setp(unexplained, ["stages", 0, "telemetry", "unavailable"], {field: "r" * 121})
    assert not ok(long_reason)
    assert not ok(setp(unexplained, ["stages", 0, "telemetry", "unavailable"], {field: ""}))


@pytest.mark.req("FR-001-10")
@pytest.mark.parametrize(
    ("status", "error_class", "ok_expected"),
    [(s, e, True) for s, e in (("succeeded", None), ("skipped", None))]
    + [(s, e, False) for s, e in (("succeeded", "oom"), ("skipped", "timeout"), ("not_run", "unknown"))]
    + [(s, "nonzero-exit", True) for s in ("failed", "cancelled", "blocked", "held", "interrupted", "env-disabled")]
    + [(s, None, False) for s in ("failed", "cancelled", "blocked", "held", "interrupted", "env-disabled")],
)
def test_fr_001_10_status_and_error_class_are_null_together_for_succeeded_skipped_not_run(
    status: str, error_class: str | None, ok_expected: bool
) -> None:
    doc = setp(setp(RUN, ["stages", 0, "status"], status), ["stages", 0, "error_class"], error_class)
    assert ok(doc) is ok_expected, (status, error_class, sorted(pairs(doc))[:3])


@pytest.mark.req("FR-001-10")
def test_fr_001_10_every_error_class_value_is_accepted_for_a_failed_stage_and_unknown_ones_are_not() -> None:
    classes = [
        "oom",
        "timeout",
        "warmup-timeout",
        "invalid-output",
        "invalid-result",
        "nonzero-exit",
        "guard",
        "lock-timeout",
        "lock-not-held",
        "cancelled",
        "interrupted",
        "hold",
        "unknown",
    ]
    for c in classes:
        doc = setp(setp(RUN, ["stages", 0, "status"], "failed"), ["stages", 0, "error_class"], c)
        assert ok(doc), c
    for bad in ("OOM", "crash", "", 1):
        doc = setp(setp(RUN, ["stages", 0, "status"], "failed"), ["stages", 0, "error_class"], bad)
        assert not ok(doc), bad


@pytest.mark.req("FR-001-10")
def test_fr_001_10_not_run_needs_a_reason_and_no_outputs_and_log_tail_only_on_failed_stages() -> None:
    base = setp(setp(RUN, ["stages", 0, "status"], "not_run"), ["stages", 0, "outputs"], [])
    assert not ok(base)  # reason missing
    with_reason = setp(base, ["stages", 0, "reason"], "Kit executable not installed")
    assert ok(with_reason)
    assert not ok(setp(with_reason, ["stages", 0, "outputs"], [{"name": "a", "sha256": "0" * 64, "bytes": 1}]))
    assert not ok(setp(with_reason, ["stages", 0, "reason"], ""))
    assert not ok(setp(with_reason, ["stages", 0, "reason"], "r" * 301))
    assert ok(setp(with_reason, ["stages", 0, "reason"], "r" * 300))
    skipped = setp(
        setp(RUN, ["stages", 0, "status"], "skipped"), ["stages", 0, "reason"], "upstream not run: st50_physics"
    )
    assert ok(setp(skipped, ["stages", 0, "error_class"], None))
    ok_succeeded = setp(RUN, ["stages", 0, "reason"], "why")
    assert not ok(ok_succeeded)  # a reason on a succeeded stage
    failed = setp(setp(RUN, ["stages", 0, "status"], "failed"), ["stages", 0, "error_class"], "oom")
    assert ok(setp(failed, ["stages", 0, "log_tail"], "x" * 4000))
    assert not ok(setp(failed, ["stages", 0, "log_tail"], "x" * 4001))
    assert not ok(setp(RUN, ["stages", 0, "log_tail"], "boom"))  # log tail on a succeeded stage


@pytest.mark.req("FR-001-10")
def test_fr_001_10_array_caps_stages_artefacts_inputs_outputs_attempts() -> None:
    stage = RUN_U["stages"][0]
    assert ok(setp(RUN_U, ["stages"], [stage] * 64))
    assert not ok(setp(RUN_U, ["stages"], [stage] * 65))
    inp = {"id": "a", "sha256": "0" * 64, "kind": "source"}
    assert ok(setp(RUN_U, ["stages", 0, "inputs"], [inp] * 32))
    assert not ok(setp(RUN_U, ["stages", 0, "inputs"], [inp] * 33))
    out = {"name": "a", "sha256": "0" * 64, "bytes": 1}
    assert ok(setp(RUN_U, ["stages", 0, "outputs"], [out] * 64))
    assert not ok(setp(RUN_U, ["stages", 0, "outputs"], [out] * 65))
    att = {"n": 1, "error_class": None}
    assert ok(setp(RUN_U, ["stages", 0, "attempts"], [att] * 5))
    assert not ok(setp(RUN_U, ["stages", 0, "attempts"], [att] * 6))
    assert not ok(setp(RUN_U, ["stages", 0, "attempts"], []))
    art = RUN["artefacts"][1]
    assert ok(setp(RUN, ["artefacts"], [art] * 2000))  # uniqueness of ids is a validate rule, not a schema rule
    assert not ok(setp(RUN, ["artefacts"], [art] * 2001))


@pytest.mark.req("FR-001-10")
def test_fr_001_10_params_are_bounded_in_depth_keys_strings_and_arrays() -> None:
    base = ["stages", 0, "params"]
    assert ok(setp(RUN, base, {"a": {"b": {"c": {"d": 1}}}}))  # depth 4: the params object and three nested objects
    assert not ok(setp(RUN, base, {"a": {"b": {"c": {"d": {"e": 1}}}}}))  # depth 5
    assert ok(setp(RUN, base, {f"k{i}": i for i in range(64)}))
    assert not ok(setp(RUN, base, {f"k{i}": i for i in range(65)}))
    assert ok(setp(RUN, base, {"s": "x" * 1024}))
    assert not ok(setp(RUN, base, {"s": "x" * 1025}))
    assert ok(setp(RUN, base, {"l": list(range(1024))}))
    assert not ok(setp(RUN, base, {"l": list(range(1025))}))
    for bad_key in ("A", "1a", "a-b", "a b", "", "a" * 65):
        assert not ok(setp(RUN, base, {bad_key: 1})), bad_key


@pytest.mark.req("FR-001-10")
def test_fr_001_10_corpus_manifest_fixtures() -> None:
    assert_corpus("FR-001-10", 15)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-11 · artefact record
# ----------------------------------------------------------------------------------------------------------------
ART_REQUIRED = [
    "id",
    "run_id",
    "git_sha",
    "path",
    "bytes",
    "sha256",
    "kind",
    "producer",
    "inputs",
    "lane",
    "licence_class",
    "spdx",
    "asset_host",
    "budget_class",
]
ARTEFACT_KINDS = [
    "video",
    "image",
    "figure",
    "point-cloud",
    "mesh",
    "tiles",
    "splat",
    "onnx",
    "table",
    "trace",
    "shard",
    "field",
    "text",
    "model-card",
    "telemetry",
    "usd",
]
STATIC_KINDS = {"image", "figure", "table", "text", "model-card", "usd"}  # data-model 2.6
BUDGET_CLASSES = ["videos", "tiles-glb", "shards-clouds", "splats", "onnx", "runtimes", "own-code", "studio-showcase"]
VIDEO_ART = RUN["artefacts"][0]
TABLE_ART = RUN["artefacts"][1]


def make_artefact(kind: str, *, with_encoder: bool | None = None) -> dict:
    """A consistent artefact of ``kind`` built by hand from data-model 2.5-2.7."""
    a = copy.deepcopy(VIDEO_ART)
    a["kind"] = kind
    if kind in STATIC_KINDS:
        a["lane"] = "static"
        a.pop("lane_measurements")
    want = (kind == "video") if with_encoder is None else with_encoder
    if not want:
        a.pop("encoder")
    return a


@pytest.mark.req("FR-001-11")
@pytest.mark.parametrize("field", ART_REQUIRED)
def test_fr_001_11_every_artefact_field_of_data_model_2_5_is_required(field: str) -> None:
    for doc, base, target in ((RUN, ["artefacts", 1], RUN_T), (WEB, ["artefacts", 1], WEB_T)):
        got = pairs(delp(doc, [*base, field]), target)
        assert (ptr(base), "required") in got, (field, sorted(got)[:3])


@pytest.mark.req("FR-001-11")
@pytest.mark.parametrize("cls", cs.LICENCE_ORDER)
def test_fr_001_11_attribution_is_required_unless_public_domain_open_no_attribution_or_own(cls: str) -> None:
    doc = setp(RUN, ["artefacts", 1, "licence_class"], cls)
    without = delp(doc, ["artefacts", 1, "attribution"]) if "attribution" in doc["artefacts"][1] else doc
    needs = cls not in cs.NO_ATTRIBUTION_CLASSES
    assert ok(without) is (not needs), cls
    with_text = setp(doc, ["artefacts", 1, "attribution"], "Data: Example Agency, CC BY 4.0.")
    assert ok(with_text), cls
    if needs:
        assert not ok(setp(doc, ["artefacts", 1, "attribution"], "")), cls
    assert not ok(setp(doc, ["artefacts", 1, "attribution"], "a" * 1001))
    assert ok(setp(doc, ["artefacts", 1, "attribution"], "a" * 1000))


@pytest.mark.req("FR-001-11")
def test_fr_001_11_unknown_licence_classes_spdx_ids_and_budget_classes_are_rejected() -> None:
    for bad in ("Own", "copyleft", "", "reference_only", None):
        assert not ok(setp(RUN, ["artefacts", 1, "licence_class"], bad)), bad
    for spdx in cs.SPDX_ALLOWLIST:
        assert ok(setp(RUN, ["artefacts", 1, "spdx"], spdx)), spdx
    for bad in ("GPL-3.0-only", "cc-by-4.0", "CC-BY-4.0 ", "LicenseRef-Foo", "", None):
        assert not ok(setp(RUN, ["artefacts", 1, "spdx"], bad)), bad
    for good in BUDGET_CLASSES:
        assert ok(setp(RUN, ["artefacts", 1, "budget_class"], good)), good
    for bad in ("video", "videos ", "", None, "Videos"):
        assert not ok(setp(RUN, ["artefacts", 1, "budget_class"], bad)), bad


@pytest.mark.req("FR-001-11")
@pytest.mark.parametrize("kind", ARTEFACT_KINDS)
def test_fr_001_11_every_artefact_kind_of_the_enum_is_accepted(kind: str) -> None:
    doc = setp(RUN, ["artefacts", 0], make_artefact(kind))
    assert ok(doc), (kind, sorted(pairs(doc))[:3])
    assert not ok(setp(RUN, ["artefacts", 0], make_artefact(kind + "x")))


@pytest.mark.req("FR-001-11")
def test_fr_001_11_artefact_scalar_bounds() -> None:
    art = ["artefacts", 0]
    for path, good, bad in (
        (["bytes"], [0, 5242880, 10_485_759], [-1, 2**53, 1.5, "5"]),  # artefact 0 is git-hosted
        (["id"], ["a", "a_b-c", "0" * 96], ["", "A", "a" * 97, "-a", "a b", "a/b"]),
        (["media_type"], ["video/mp4", "application/vnd.x+json"], ["video", "Video/mp4", "video/", "a/" + "b" * 65]),
        (["lane"], ["live", "replay"], ["precompute", "LIVE", ""]),
        (["cases"], [[], ["A1"], list(cs.CASE_IDS)], [["Z9"], ["A1", "A1"], ["a1"], [*cs.CASE_IDS, "A1"], "A1"]),
        (["inputs"], [[]], [[{"id": "x"}], "x"]),
    ):
        for v in good:
            assert ok(setp(RUN, [*art, *path], v)), (path, v)
        for v in bad:
            assert any(p.startswith(ptr([*art, *path])) for p, _ in pairs(setp(RUN, [*art, *path], v))), (path, v)


@pytest.mark.req("FR-001-11")
def test_fr_001_11_inputs_kinds_and_id_shapes() -> None:
    base = ["artefacts", 0, "inputs"]
    good = [
        {"id": "example-dataset", "sha256": "a" * 64, "kind": "source"},
        {"id": "a2-frames", "sha256": "a" * 64, "kind": "artefact"},
        {"id": "knowledge-row-12", "sha256": "a" * 64, "kind": "knowledge"},
    ]
    assert ok(setp(RUN, base, good))
    for bad_item in (
        {"id": "x", "sha256": "A" * 64, "kind": "source"},
        {"id": "x", "sha256": "a" * 64, "kind": "dataset"},
        {"id": "x", "sha256": "a" * 64},
        {"id": "x", "sha256": "a" * 64, "kind": "source", "extra": 1},
        {"id": "Has Space", "sha256": "a" * 64, "kind": "source"},
        {"id": "Has_Upper", "sha256": "a" * 64, "kind": "knowledge"},
    ):
        assert not ok(setp(RUN, base, [bad_item])), bad_item
    assert ok(setp(RUN, base, [{"id": "a" * 96, "sha256": "a" * 64, "kind": "artefact"}]))
    assert not ok(setp(RUN, base, [{"id": "a" * 65, "sha256": "a" * 64, "kind": "source"}]))  # slug <= 64


@pytest.mark.req("FR-001-11")
def test_fr_001_11_producer_names_a_tool_and_a_frozen_stage() -> None:
    base = ["artefacts", 0, "producer"]
    assert ok(setp(RUN, base, {"tool": "nvenc-ffmpeg", "stage": {"id": "st56_encode", "variant": "dem"}}))
    for bad in (
        {"tool": "NVENC", "stage": {"id": "st56_encode"}},
        {"tool": "n", "stage": {"id": "st56_encode"}},
        {"tool": "x" * 49, "stage": {"id": "st56_encode"}},
        {"tool": "nvenc-ffmpeg", "stage": {"id": "st99_magic"}},
        {"tool": "nvenc-ffmpeg", "stage": {"id": "st56_encode", "variant": "Bad"}},
        {"tool": "nvenc-ffmpeg"},
        {"stage": {"id": "st56_encode"}},
        {"tool": "nvenc-ffmpeg", "stage": {"id": "st56_encode"}, "extra": 1},
    ):
        assert not ok(setp(RUN, base, bad)), bad


@pytest.mark.req("FR-001-11")
def test_fr_001_11_corpus_manifest_fixtures() -> None:
    assert_corpus("FR-001-11", 2)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-12 · asset host rules
# ----------------------------------------------------------------------------------------------------------------
def host_doc(host: str, **kw: Any) -> dict:
    a = copy.deepcopy(TABLE_ART)
    a["asset_host"] = host
    a.update(kw)
    return setp(RUN, ["artefacts", 1], a)


@pytest.mark.req("FR-001-12")
@pytest.mark.parametrize(
    ("nbytes", "expected"),
    [(0, True), (10_485_759, True), (10_485_760, False), (10_485_761, False), (2**53 - 1, False)],
)
def test_fr_001_12_git_hosted_files_are_below_10_mib(nbytes: int, expected: bool) -> None:  # 10 MiB = 10,485,760 B
    assert ok(host_doc("git", bytes=nbytes)) is expected


@pytest.mark.req("FR-001-12")
@pytest.mark.parametrize("nbytes", [0, 10_485_760, 5 * 10**9, 2**53 - 1])
def test_fr_001_12_release_hosted_files_may_be_larger_and_need_a_tag_and_a_one_segment_path(nbytes: int) -> None:
    good = host_doc("release", bytes=nbytes, release_tag="assets-v1.00.001", path="a2-report.json")
    assert ok(good)
    assert not ok(host_doc("release", bytes=nbytes, path="a2-report.json"))  # no tag
    assert not ok(
        host_doc("release", bytes=nbytes, release_tag="assets-v1.00.001", path="assets/runs/x/a2-report.json")
    )


@pytest.mark.req("FR-001-12")
@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("assets-v1.00.001", True),
        ("assets-v0.01.000", True),
        ("assets-v12.34.567", True),
        ("assets-v100.99.999", True),
        ("assets-v1.0.001", False),
        ("assets-v1.000.001", False),
        ("assets-v1.00.01", False),
        ("assets-v1.00.0001", False),
        ("assets-v.00.001", False),
        ("assets-v1.00", False),
        ("v1.00.001", False),
        ("assets-v1.00.001-rc", False),
        ("Assets-v1.00.001", False),
        ("assets-v1.00.00a", False),
        ("", False),
    ],
)
def test_fr_001_12_release_tag_pattern_boundaries(tag: str, expected: bool) -> None:
    assert ok(host_doc("release", bytes=100, release_tag=tag, path="a.json")) is expected


@pytest.mark.req("FR-001-12")
def test_fr_001_12_git_host_with_a_release_tag_fails_and_unknown_hosts_fail() -> None:
    assert not ok(host_doc("git", release_tag="assets-v1.00.001"))
    assert not ok(host_doc("cdn"))
    assert not ok(host_doc("Git"))


@pytest.mark.req("FR-001-12")
def test_fr_001_12_web_index_applies_the_same_host_rules() -> None:
    assert not ok(setp(WEB, ["artefacts", 0, "release_tag"], None), WEB_T)
    assert not ok(delp(WEB, ["artefacts", 0, "release_tag"]), WEB_T)
    assert not ok(setp(WEB, ["artefacts", 1, "bytes"], 10_485_760), WEB_T)
    assert ok(setp(WEB, ["artefacts", 1, "bytes"], 10_485_759), WEB_T)


@pytest.mark.req("FR-001-12")
def test_fr_001_12_corpus_manifest_fixtures() -> None:
    assert_corpus("FR-001-12", 4)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-14 · published local-only stages are scrubbed
# ----------------------------------------------------------------------------------------------------------------
LOCAL = ["stages", 1]  # ovrtx, performance local-only, telemetry = the constant


def test_fixture_assumption_stage_1_is_the_local_only_stage() -> None:
    assert RUN["stages"][1]["performance"] == "local-only"
    assert RUN["stages"][1]["telemetry"] == cs.LOCAL_ONLY


@pytest.mark.req("FR-001-14")
def test_fr_001_14_published_local_only_stage_with_the_constant_is_valid() -> None:
    assert ok(RUN)


@pytest.mark.req("FR-001-14")
@pytest.mark.parametrize(
    "telemetry",
    [
        None,
        cs.LOCAL_ONLY + ".",
        cs.LOCAL_ONLY.upper(),
        "",
        "measured locally",
        {"sample_hz": 2},
        0,
        True,
        RUN["stages"][0]["telemetry"],
    ],
)
def test_fr_001_14_any_other_telemetry_of_a_published_local_only_stage_fails(telemetry: Any) -> None:
    got = pairs(setp(RUN, [*LOCAL, "telemetry"], telemetry))
    assert got, "must be rejected"
    assert any(p.startswith("/stages/1") for p, _ in got)


@pytest.mark.req("FR-001-14")
@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["wall_s"], 1.5),
        (["wall_s"], 0),
        (["throughput"], {"value": 1.0, "unit": "frames/s"}),
        (["attempts", 0, "duration_s"], 0.5),
        (["attempts", 0, "duration_s"], 0),
    ],
)
def test_fr_001_14_wall_time_throughput_and_attempt_durations_of_published_local_only_stages_fail(
    path: list[Any], value: Any
) -> None:
    doc = setp(RUN, [*LOCAL, *path], value)
    assert any(p.startswith("/stages/1") for p, _ in pairs(doc)), path


@pytest.mark.req("FR-001-14")
def test_fr_001_14_every_attempt_is_checked_not_only_the_first() -> None:
    attempts = [{"n": 1, "error_class": "oom"}, {"n": 2, "error_class": None, "duration_s": 3.0}]
    doc = setp(RUN, [*LOCAL, "attempts"], attempts)
    assert any(p.startswith("/stages/1/attempts/1") for p, _ in pairs(doc))


@pytest.mark.req("FR-001-14")
def test_fr_001_14_the_scrub_applies_to_published_runs_only() -> None:
    unpublished = setp(RUN, ["published"], False)
    unpublished = setp(unpublished, ["gpu"], None)
    stage = copy.deepcopy(unpublished["stages"][1])
    stage["wall_s"], stage["throughput"] = 9.5, {"value": 2.0, "unit": "frames/s"}
    stage["attempts"][0]["duration_s"] = 9.5
    stage["telemetry"] = copy.deepcopy(unpublished["stages"][0]["telemetry"])
    assert ok(setp(unpublished, [*LOCAL], stage))
    public_stage = setp(RUN, ["stages", 0, "wall_s"], 3.0)  # a public stage keeps its figures when published
    assert ok(public_stage)


@pytest.mark.req("FR-001-14")
def test_fr_001_14_published_runs_with_no_local_only_stage_are_unaffected() -> None:
    doc = copy.deepcopy(RUN)
    doc["stages"] = [doc["stages"][0]]
    assert ok(doc)


@pytest.mark.req("FR-001-14")
def test_fr_001_14_corpus_manifest_fixtures() -> None:
    assert_corpus("FR-001-14", 3)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-16 · publication preconditions
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-16")
def test_fr_001_16_schema_rules_dirty_test_launcher_fake_gpu() -> None:
    assert ("/git_dirty", "const") in pairs(setp(RUN, ["git_dirty"], True))
    assert ("/launcher", "const") in pairs(setp(RUN, ["launcher"], "test"))
    fake = setp(RUN, ["gpu", "backend"], "fake")
    assert any(p.startswith("/gpu") for p, _ in pairs(fake))
    assert ok(setp(RUN, ["gpu"], None))  # CPU-only published run
    assert ok(setp(RUN, ["gpu", "backend"], "nvml"))
    for key, value in (("git_dirty", True), ("launcher", "test")):
        assert ok(setp(setp(RUN, ["published"], False), [key], value))
    assert ok(setp(setp(RUN, ["published"], False), ["gpu", "backend"], "fake"))
    assert ok(RUN_U)  # the unpublished example uses all three


@pytest.mark.req("FR-001-16")
def test_fr_001_16_publishing_an_unpublished_run_trips_every_precondition_it_breaks() -> None:
    doc = setp(RUN_U, ["published"], True)
    got = {p for p, _ in pairs(doc)}
    assert "/git_dirty" in got
    assert "/launcher" in got
    assert any(p.startswith("/gpu") for p in got)


@pytest.mark.req("FR-001-16")
def test_fr_001_16_corpus_manifest_fixtures() -> None:
    assert_corpus("FR-001-16", 3)


def _run_manifest_path(root: Path) -> str:
    return next(p.relative_to(root).as_posix() for p in (root / "web/public/assets/runs").glob("*/manifest.json"))


@pytest.mark.req("FR-001-16")
@pytest.mark.parametrize(
    ("status", "error_class", "extra"),
    [
        ("failed", "nonzero-exit", {}),
        ("skipped", None, {"reason": "upstream not run: st50_physics"}),
        ("not_run", None, {"reason": "encoder missing", "outputs": []}),
        ("cancelled", "cancelled", {}),
        ("blocked", "guard", {}),
        ("held", "hold", {}),
        ("interrupted", "interrupted", {}),
        ("env-disabled", "unknown", {}),
    ],
)
def test_fr_001_16_published_artefact_of_a_stage_that_did_not_succeed_is_rejected(
    tmp_path: Path, status: str, error_class: str | None, extra: dict
) -> None:
    root = cs.clean_repo(tmp_path)
    rel = _run_manifest_path(root)

    def edit(doc: dict) -> None:
        st = doc["stages"][0]  # st56_encode produces artefact 0 (video)
        st["status"], st["error_class"] = status, error_class
        st.update(extra)
        if status != "succeeded":
            st["exit_code"] = 1

    cs.edit_json(root, rel, edit)
    res = cs.run_checker(root)
    assert res.code == 1
    hits = res.at("FR-001-16", "/artefacts/0")
    assert hits, res.findings
    assert all(len(f["message"]) <= 300 for f in hits)
    assert not res.at("FR-001-16", "/artefacts/1")  # produced by another, succeeded, stage


@pytest.mark.req("FR-001-16")
def test_fr_001_16_clean_published_run_passes_the_producer_status_rule(tmp_path: Path) -> None:
    res = cs.run_checker(cs.clean_repo(tmp_path))
    assert res.of("FR-001-16") == []


# ----------------------------------------------------------------------------------------------------------------
# FR-001-17 · encoder record
# ----------------------------------------------------------------------------------------------------------------
ENC = ["artefacts", 0, "encoder"]
ENCODER_REQUIRED = [
    "codec",
    "profile",
    "pix_fmt",
    "width",
    "height",
    "fps",
    "frames",
    "duration_s",
    "bitrate_kbps",
    "vmaf",
    "source_frames_sha256",
    "encoder",
    "encode_fps",
]


@pytest.mark.req("FR-001-17")
@pytest.mark.parametrize("kind", ARTEFACT_KINDS)
def test_fr_001_17_video_artefacts_carry_an_encoder_record_and_no_other_kind_does(kind: str) -> None:
    with_enc = setp(RUN, ["artefacts", 0], make_artefact(kind, with_encoder=True))
    without = setp(RUN, ["artefacts", 0], make_artefact(kind, with_encoder=False))
    assert ok(with_enc) is (kind == "video"), kind
    assert ok(without) is (kind != "video"), kind


@pytest.mark.req("FR-001-17")
@pytest.mark.parametrize("field", ENCODER_REQUIRED)
def test_fr_001_17_every_encoder_field_of_data_model_2_7_is_required(field: str) -> None:
    assert (ptr(ENC), "required") in pairs(delp(RUN, [*ENC, field]))


ENCODER_BOUNDS: list[tuple[list[Any], list[Any], list[Any]]] = [
    (["codec"], ["av1", "h264"], ["vp9", "AV1", "", None]),
    (["profile"], ["main", "p" * 32], ["", "p" * 33]),
    (["pix_fmt"], ["yuv420p", "nv12", "ab", "a" * 16], ["YUV420P", "a", "a" * 17, "yuv 420", "yuv-420"]),
    (["width"], [16, 1920, 8192], [15, 8193, 0, 19.5, "1920"]),
    (["height"], [16, 1080, 8192], [15, 8193, -1]),
    (["fps"], [0.5, 29.97, 30, 240], [0, -1, 240.1, "30"]),
    (["frames"], [1, 600], [0, -1, 1.5]),
    (["duration_s"], [0.001, 20.0], [0, -1]),
    (["bitrate_kbps"], [0.5, 2097.152], [0, -1]),
    (["vmaf", "mean"], [0, 100, 93.1], [-0.1, 100.1]),
    (["vmaf", "p5"], [0, 100], [-1, 101]),
    (["vmaf", "model"], ["m", "m" * 64], ["", "m" * 65]),
    (["source_frames_sha256"], ["a" * 64], ["A" * 64, "a" * 63]),
    (["encoder", "ffmpeg_version"], ["n7.1", "7.1.2", "n7.1.2.3", "7"], ["7.1.2.3.4", "v7", "n", "7.", "n7.x"]),
    (["encoder", "build_sha256"], ["a" * 64], ["a" * 65]),
    (["encoder", "nvenc_api"], ["13.0", None], ["13", "13.0.1", "v13.0", ""]),
    (["encoder", "args"], [[], ["-c:v"] * 32, ["a" * 200]], [["a" * 201], ["x"] * 65, "x", [1]]),
    (["encode_fps"], [0, 240.0, None], [-1, "1"]),
]


@pytest.mark.req("FR-001-17")
@pytest.mark.parametrize(("path", "good", "bad"), ENCODER_BOUNDS, ids=[ptr(b[0]) for b in ENCODER_BOUNDS])
def test_fr_001_17_encoder_field_bounds(path: list[Any], good: list[Any], bad: list[Any]) -> None:
    for v in good:
        assert ok(setp(RUN, [*ENC, *path], v)), (ptr(path), v, sorted(pairs(setp(RUN, [*ENC, *path], v)))[:3])
    for v in bad:
        got = pairs(setp(RUN, [*ENC, *path], v))
        assert any(p.startswith(ptr([*ENC, *path])) for p, _ in got), (ptr(path), v)


@pytest.mark.req("FR-001-17")
def test_fr_001_17_corpus_manifest_fixtures() -> None:
    assert_corpus("FR-001-17", 2)


def _set_encoder(root: Path, frames: int, fps: float, duration: float) -> None:
    def edit(doc: dict) -> None:
        enc = doc["artefacts"][0]["encoder"]
        enc["frames"], enc["fps"], enc["duration_s"] = frames, fps, duration

    cs.edit_json(root, "web/public/assets/manifest.json", edit)


@pytest.mark.req("FR-001-17")
@pytest.mark.parametrize(
    ("frames", "fps", "duration", "fails"),
    [
        (600, 30, 20.0, False),  # exact: 600 / 30 = 20
        (600, 30, 20.03, False),  # |0.03| <= 1/30 = 0.0333
        (600, 30, 19.97, False),
        (600, 30, 20.04, True),  # 0.04 > 0.0333
        (600, 30, 19.96, True),
        (100, 25, 4.039, False),  # 100 / 25 = 4, 1 / 25 = 0.04
        (100, 25, 3.961, False),
        (100, 25, 4.041, True),
        (100, 25, 3.959, True),
        (1, 240, 0.004, False),  # 1 / 240 = 0.004166..
        (1, 240, 0.0084, True),
        (1, 240, 0.0082, False),
        (24, 24, 5.0, True),  # 24 / 24 = 1 s but the record says 5 s
    ],
)
def test_fr_001_17_checker_compares_duration_with_frames_over_fps_within_one_frame(
    tmp_path: Path, frames: int, fps: float, duration: float, fails: bool
) -> None:
    root = cs.clean_repo(tmp_path)
    _set_encoder(root, frames, fps, duration)
    res = cs.run_checker(root)
    hits = res.at("FR-001-17", "/artefacts/0")
    assert bool(hits) is fails, (frames, fps, duration, res.findings)
    for f in hits:
        assert "a2-haul-clip" in f["message"] or f["pointer"].startswith("/artefacts/0")
        assert len(f["message"]) <= 300


@pytest.mark.req("FR-001-17")
def test_fr_001_17_checker_flags_the_doc_level_corpus_fixture(tmp_path: Path) -> None:
    root = cs.clean_repo(tmp_path)
    doc = cs.fixture_json(next(e for e in cs.entries(rule="FR-001-17") if "encoder-duration" in e["file"]))
    cs.write_file(root, _run_manifest_path(root), doc)  # same run id as the clean run: 25 s recorded, 600 / 30 = 20 s
    res = cs.run_checker(root)
    assert res.at("FR-001-17", "/artefacts/0/encoder")
