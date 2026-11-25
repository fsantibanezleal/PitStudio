"""T-001-020 · the recipe schema, the stage-environment binding, hostile recipe values and the job request.

Requirements: FR-001-21, FR-001-22, FR-001-23, FR-001-24.

Oracles: the field tables, bounds and enums of data-model 3.1-3.5 and the frozen stage table of 3.3 (transcribed in
``contract_support.STAGE_ENVS``); corpus fixtures with the expected pointer and keyword fixed by construction; python
``jsonschema`` as the reference validator; for the two limits no schema can state (shard count, canonical params size)
the hand-computed arithmetic of data-model 1.4 / 3.2 through ``pitstudio.contracts.validate``.

Expected API: ``contracts/recipe.schema.json`` (document at ``#``, job request at ``#/$defs/job_request``) and
``pitstudio.contracts.validate(document, "recipe")`` returning errors with ``pointer``/``keyword``/``message``.
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

JOB_T = "#/$defs/job_request"


def load(rel: str) -> Any:
    return json.loads((cs.FIXTURES / rel).read_text(encoding="utf-8"))


REC = load("recipe/valid/recipe.valid.json")
BENCH = load("recipe/valid/recipe.valid-bench.json")
JOB = load("recipe/valid/recipe.valid-job-request.json")


def pairs(doc: Any, target: str = "#") -> set[tuple[str, str]]:
    return cs.error_pairs("recipe", target, doc)


def ok(doc: Any, target: str = "#") -> bool:
    return cs.accepts("recipe", target, doc)


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
    return "/" + "/".join(str(p) for p in path) if path else ""


def assert_corpus(rule: str, minimum: int) -> None:
    items = [e for e in cs.schema_level(schema="recipe") if e["rule"] == rule and not e["valid"]]
    assert len(items) >= minimum, (rule, len(items))
    for e in items:
        got = pairs(cs.fixture_json(e), e["target"])
        assert (e["pointer"], e["keyword"]) in got, (e["file"], e["pointer"], e["keyword"], sorted(got)[:4])


def stage(i: int = 1) -> dict:
    return copy.deepcopy(REC["stages"][i])  # 1 = st50_physics (gpu exclusive, statistical, retry, shardable)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-21 · the recipe document
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-21")
def test_fr_001_21_valid_recipes_and_job_request_are_accepted() -> None:
    assert ok(REC)
    assert ok(BENCH)
    assert ok(JOB, JOB_T)
    assert ok({k: v for k, v in REC.items() if k != "$schema"})  # the editor hint is optional


@pytest.mark.req("FR-001-21")
@pytest.mark.parametrize("field", ["id", "case", "seed", "stages"])
def test_fr_001_21_required_recipe_fields(field: str) -> None:
    assert ("", "required") in pairs(delp(REC, [field]))


@pytest.mark.req("FR-001-21")
def test_fr_001_21_description_is_optional_and_bounded_and_case_accepts_bench() -> None:
    assert ok(delp(REC, ["description"]))
    assert ok(setp(REC, ["description"], "d" * 500))
    assert not ok(setp(REC, ["description"], "d" * 501))
    assert not ok(setp(REC, ["description"], 5))
    for good in [*cs.CASE_IDS, "bench"]:
        assert ok(setp(REC, ["case"], good)), good
    for bad in ("Z9", "a1", "A", "A10", "", "bench ", "Bench", None, 1):
        assert not ok(setp(REC, ["case"], bad)), bad


@pytest.mark.req("FR-001-21")
@pytest.mark.parametrize(("n", "expected"), [(0, False), (1, True), (64, True), (65, False)])
def test_fr_001_21_stage_count_is_1_to_64(n: int, expected: bool) -> None:
    stages = []
    ids = sorted(cs.STAGE_ENVS)
    for i in range(n):
        s = copy.deepcopy(REC["stages"][0])
        s["id"], s["env"] = ids[i % len(ids)], sorted(cs.STAGE_ENVS[ids[i % len(ids)]])[0]
        s["variant"] = f"v{i}"
        stages.append(s)
    assert ok(setp(REC, ["stages"], stages)) is expected


@pytest.mark.req("FR-001-21")
@pytest.mark.parametrize("field", ["profile", "machine", "hostname", "path", "cwd", "root", "home", "abs_path", "yaml"])
def test_fr_001_21_no_field_for_a_machine_profile_or_an_absolute_path(field: str) -> None:
    assert ("", "additionalProperties") in pairs(setp(REC, [field], "x"))
    assert ("/stages/0", "additionalProperties") in pairs(setp(REC, ["stages", 0, field], "x"))


@pytest.mark.req("FR-001-21")
@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({"id": "example-haul-network", "sha256": "a" * 64}, True),
        ({"stage": "s00_download"}, True),
        ({"stage": "st50_physics", "variant": "dem"}, True),
        ({"stage": "s00_download", "output": "raw/network.geojson"}, True),
        ({"stage": "st50_physics", "variant": "dem", "output": "physics/o.parquet"}, True),
        ({"id": "x", "sha256": "a" * 64, "stage": "s00_download"}, False),  # both forms mixed
        ({"id": "x"}, False),  # digest missing
        ({"sha256": "a" * 64}, False),
        ({"path": "raw/network.geojson"}, False),  # data is never referenced by a path
        ({"id": "a/b", "sha256": "a" * 64}, False),
        ({"id": "../x", "sha256": "a" * 64}, False),
        ({"id": "x", "sha256": "A" * 64}, False),
        ({"id": "x", "sha256": "a" * 64, "path": "x"}, False),
        ({"stage": "st99_magic"}, False),
        ({"stage": "s00_download", "output": "/abs"}, False),
        ({"stage": "s00_download", "output": "a/../b"}, False),
        ({"stage": "s00_download", "variant": "Bad"}, False),
        ({}, False),
        ("s00_download", False),
    ],
    ids=lambda v: json.dumps(v)[:50],
)
def test_fr_001_21_inputs_are_a_logical_id_with_a_digest_or_an_upstream_stage(item: Any, expected: bool) -> None:
    assert ok(setp(REC, ["stages", 0, "inputs"], [item])) is expected


@pytest.mark.req("FR-001-21")
def test_fr_001_21_at_most_32_inputs_and_inputs_may_be_empty() -> None:
    one = {"id": "x", "sha256": "a" * 64}
    assert ok(setp(REC, ["stages", 0, "inputs"], []))
    assert ok(setp(REC, ["stages", 0, "inputs"], [one] * 32))
    assert not ok(setp(REC, ["stages", 0, "inputs"], [one] * 33))
    assert ("/stages/0", "required") in pairs(delp(REC, ["stages", 0, "inputs"]))


STAGE_FIELDS_REQUIRED = ["id", "env", "tool", "entry", "inputs", "resources", "determinism", "timeout_s", "outputs"]


@pytest.mark.req("FR-001-21")
@pytest.mark.parametrize("field", STAGE_FIELDS_REQUIRED)
def test_fr_001_21_required_stage_fields(field: str) -> None:
    assert ("/stages/0", "required") in pairs(delp(REC, ["stages", 0, field]))


@pytest.mark.req("FR-001-21")
@pytest.mark.parametrize("field", ["variant", "params", "requires", "binaries", "retry", "shardable"])
def test_fr_001_21_optional_stage_fields(field: str) -> None:
    holders = [i for i, s in enumerate(REC["stages"]) if field in s]
    assert holders, field
    for i in holders:
        assert ok(delp(REC, ["stages", i, field]))


STAGE_BOUNDS: list[tuple[list[Any], list[Any], list[Any]]] = [
    (["variant"], ["a", "dem", "a" * 32, "0a"], ["", "A", "a" * 33, "a_b", "-a", "a b", "a/b"]),
    (["tool"], ["pitstudio", "nvenc-ffmpeg", "ab", "a" * 48], ["a", "", "A", "a" * 49, "a_b", "1a"]),
    (
        ["entry"],
        ["a", "pkg.mod", "a_b.c1", "_x", ".".join(["a"] * 8), "a" * 64, "pitstudio.stages.s00_download"],
        [
            "Pkg.Mod",
            "pkg/mod",
            "pkg.mod -c",
            "pkg..mod",
            ".pkg",
            "pkg.",
            "1pkg",
            "pkg-mod",
            "os; rm -rf /",
            "",
            ".".join(["a"] * 9),
            "a" * 65,
            "pkg.m\u00f3dulo",
            "pkg mod",
            "$(id)",
            "pkg.mod`x`",
            "--version",
            "pkg\\mod",
        ],
    ),
    (["timeout_s"], [1, 604800, 3600], [0, -1, 604801, 1.5, "3600", None, True]),
    (
        ["requires"],
        [[], ["warp_newton"], [f"p{i}" for i in range(16)]],
        [[f"p{i}" for i in range(17)], ["warp_newton", "warp_newton"], ["Warp"], ["a-b"], "warp_newton", [1]],
    ),
    (
        ["binaries"],
        [[], [{"id": "ffmpeg", "sha256": "a" * 64}], [{"id": f"b{i}x", "sha256": "a" * 64} for i in range(8)]],
        [
            [{"id": f"b{i}x", "sha256": "a" * 64} for i in range(9)],
            [{"id": "ffmpeg"}],
            [{"sha256": "a" * 64}],
            [{"id": "FFmpeg", "sha256": "a" * 64}],
            [{"id": "ffmpeg", "sha256": "a" * 63}],
            [{"id": "ffmpeg", "sha256": "a" * 64, "path": "/usr/bin/ffmpeg"}],
        ],
    ),
    (
        ["outputs"],
        [
            [{"path": "a/b.json", "schema": "json-file"}],
            [{"path": "a.json", "schema": "ab", "publish": True}],
            [{"path": f"o{i}.json", "schema": "json-file"} for i in range(64)],
        ],
        [
            [],
            [{"path": f"o{i}.json", "schema": "json-file"} for i in range(65)],
            [{"path": "a.json"}],
            [{"schema": "x-y"}],
            [{"path": "a.json", "schema": "JSON"}],
            [{"path": "a.json", "schema": "json-file", "publish": "yes"}],
            [{"path": "a.json", "schema": "json-file", "extra": 1}],
        ],
    ),
    (
        ["retry"],
        [{"oom_fallback": [{"counts": {"particles": 1}}]}, {"oom_fallback": [{"a": 1}] * 4}],
        [{"oom_fallback": []}, {"oom_fallback": [{"a": 1}] * 5}, {"oom_fallback": [{"A": 1}]}, {}, {"other": 1}],
    ),
    (
        ["shardable"],
        [{"shard_size": 1, "total": 1}, {"shard_size": 10_000_000, "total": 1_000_000_000}],
        [
            {"shard_size": 0, "total": 1},
            {"shard_size": 1, "total": 0},
            {"shard_size": 10_000_001, "total": 1},
            {"shard_size": 1, "total": 1_000_000_001},
            {"shard_size": 1},
            {"total": 1},
            {"shard_size": 1.5, "total": 3},
        ],
    ),
    (["resources", "vram_gib_est"], [0.001, 6.0, 256, 256.0], [0, -1, 256.001, 300, "6", None]),
    (["resources", "disk_gib_est"], [0, 4.0, 10000], [-0.1, 10000.1, "4"]),
    (["resources", "cpu"], [1, 256], [0, 257, 1.5, "2", None]),
    (["resources", "gpu"], ["exclusive", "nvenc"], ["shared", "Exclusive", "", None, True]),  # "none" + VRAM is invalid
]


@pytest.mark.req("FR-001-21")
@pytest.mark.parametrize(("path", "good", "bad"), STAGE_BOUNDS, ids=[ptr(b[0]) for b in STAGE_BOUNDS])
def test_fr_001_21_stage_field_bounds_of_data_model_3_2(path: list[Any], good: list[Any], bad: list[Any]) -> None:
    for v in good:
        got = pairs(setp(REC, ["stages", 1, *path], v))
        assert got == set(), (ptr(path), v, sorted(got)[:3])
    for v in bad:
        got = pairs(setp(REC, ["stages", 1, *path], v))
        assert any(p.startswith(ptr(["stages", 1, *path])) for p, _ in got), (ptr(path), v)


@pytest.mark.req("FR-001-21")
@pytest.mark.parametrize(
    ("det", "expected"),
    [
        ("bitwise", True),
        ({"class": "bitwise"}, True),
        ({"class": "statistical", "observables": {"repose_deg": {"rtol": 0.02, "atol": 0.5}}}, True),
        ({"class": "statistical", "observables": {"a": {"rtol": 0, "atol": 0}}}, True),
        ({"class": "statistical", "observables": {"a": {"rtol": 1, "atol": 1e9}}}, True),
        ({"class": "statistical", "observables": {f"o{i}": {"rtol": 0.1, "atol": 0.1} for i in range(32)}}, True),
        ({"class": "none", "reason": "r" * 10}, True),
        ({"class": "none", "reason": "r" * 300}, True),
        ("statistical", False),
        ("none", False),
        ("exact", False),
        ({"class": "statistical"}, False),
        ({"class": "statistical", "observables": {}}, False),
        ({"class": "statistical", "observables": {f"o{i}": {"rtol": 0.1, "atol": 0.1} for i in range(33)}}, False),
        ({"class": "statistical", "observables": {"a": {"rtol": 1.0001, "atol": 0}}}, False),
        ({"class": "statistical", "observables": {"a": {"rtol": -0.1, "atol": 0}}}, False),
        ({"class": "statistical", "observables": {"a": {"rtol": 0.1, "atol": -1}}}, False),
        ({"class": "statistical", "observables": {"a": {"rtol": 0.1}}}, False),
        ({"class": "statistical", "observables": {"a": {"rtol": "0.1", "atol": 0}}}, False),
        ({"class": "none"}, False),
        ({"class": "none", "reason": "r" * 9}, False),
        ({"class": "none", "reason": "r" * 301}, False),
        ({"class": "bitwise", "reason": "why not at all"}, False),
        ({"class": "bitwise", "observables": {"a": {"rtol": 0, "atol": 0}}}, False),
        ({"class": "weird"}, False),
        ({}, False),
        (None, False),
    ],
    ids=lambda v: json.dumps(v)[:60],
)
def test_fr_001_21_determinism_forms(det: Any, expected: bool) -> None:
    assert ok(setp(REC, ["stages", 1, "determinism"], det)) is expected


@pytest.mark.req("FR-001-21")
@pytest.mark.parametrize(
    ("resources", "expected"),
    [
        ({"gpu": "none"}, True),
        ({"gpu": "none", "cpu": 4, "disk_gib_est": 1.5}, True),
        ({"gpu": "exclusive", "vram_gib_est": 6.0}, True),
        ({"gpu": "nvenc"}, True),
        ({"gpu": "nvenc", "vram_gib_est": 2.0}, True),
        ({"gpu": "none", "vram_gib_est": 4}, False),
        ({"gpu": "none", "vram_gib_est": 0.5}, False),
        ({"gpu": "exclusive"}, False),
        ({"gpu": "exclusive", "vram_gib_est": 0}, False),
        ({"gpu": "exclusive", "vram_gib_est": 6.0, "node": "a"}, False),
        ({}, False),
        ({"vram_gib_est": 4}, False),
    ],
    ids=lambda v: json.dumps(v)[:60],
)
def test_fr_001_21_resource_consistency(resources: Any, expected: bool) -> None:
    assert ok(setp(REC, ["stages", 1, "resources"], resources)) is expected


@pytest.mark.req("FR-001-21")
def test_fr_001_21_params_limits_depth_keys_strings_arrays() -> None:
    base = ["stages", 1, "params"]
    assert ok(setp(REC, base, {}))
    assert ok(setp(REC, base, {"a": {"b": {"c": {"d": 1}}}}))  # depth 4 counting the params object
    assert not ok(setp(REC, base, {"a": {"b": {"c": {"d": {"e": 1}}}}}))
    assert ok(setp(REC, base, {f"k{i}": i for i in range(64)}))
    assert not ok(setp(REC, base, {f"k{i}": i for i in range(65)}))
    assert ok(setp(REC, base, {"s": "x" * 1024}))
    assert not ok(setp(REC, base, {"s": "x" * 1025}))
    assert ok(setp(REC, base, {"l": [0] * 1024}))
    assert not ok(setp(REC, base, {"l": [0] * 1025}))
    for bad_key in ("A", "1a", "a-b", "a b", "", "a" * 65, "\u00e9"):
        assert not ok(setp(REC, base, {bad_key: 1})), bad_key
    assert ok(setp(REC, base, {"a": [1, 2.5, "s", None, True]}))


@pytest.mark.req("FR-001-21")
def test_fr_001_21_corpus_unknown_field_fixtures() -> None:
    assert_corpus("FR-001-21", 2)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-22 · stage-to-environment binding (data-model 3.3), every stage id x every environment
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-22")
def test_fr_001_22_every_frozen_stage_id_accepts_exactly_its_environments() -> None:
    assert len(cs.STAGE_ENVS) == 31
    assert len(cs.RECIPE_ENVS) == 9
    wrong: list[tuple[str, str, bool]] = []
    for sid, allowed in cs.STAGE_ENVS.items():
        for env in cs.RECIPE_ENVS:
            s = copy.deepcopy(REC["stages"][0])
            s["id"], s["env"] = sid, env
            doc = setp(REC, ["stages"], [s])
            if ok(doc) is not (env in allowed):
                wrong.append((sid, env, env in allowed))
    assert wrong == []


@pytest.mark.req("FR-001-22")
def test_fr_001_22_the_error_names_the_env_pointer() -> None:
    s = copy.deepcopy(REC["stages"][0])
    s["id"], s["env"] = "st52_rtx_render", "studio"
    assert any(p == "/stages/0/env" for p, _ in pairs(setp(REC, ["stages"], [s])))


@pytest.mark.req("FR-001-22")
@pytest.mark.parametrize("env", ["docker", "Studio", "", "root", "web", "runner", None, 1])
def test_fr_001_22_unknown_environments_are_rejected_for_every_stage(env: Any) -> None:
    for sid in cs.STAGE_ENVS:
        s = copy.deepcopy(REC["stages"][0])
        s["id"], s["env"] = sid, env
        assert not ok(setp(REC, ["stages"], [s])), (sid, env)


@pytest.mark.req("FR-001-22")
def test_fr_001_22_the_binding_holds_for_the_second_instance_of_a_stage_with_a_variant() -> None:
    a, b = copy.deepcopy(REC["stages"][1]), copy.deepcopy(REC["stages"][1])
    a["variant"], b["variant"], b["env"] = "dem", "mpm", "isaac"
    assert any(p == "/stages/2/env" for p, _ in pairs(setp(REC, ["stages"], [REC["stages"][0], a, b])))


@pytest.mark.req("FR-001-22")
def test_fr_001_22_corpus_wrong_binding_fixture() -> None:
    assert_corpus("FR-001-22", 1)


# ----------------------------------------------------------------------------------------------------------------
# FR-001-23 · hostile values (data-model 3.4)
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-23")
@pytest.mark.parametrize(
    "sid", ["st99_magic", "S00_download", "s00_download ", "s00-download", "", "st56encode", "s00", None, 1]
)
def test_fr_001_23_unknown_stage_ids(sid: Any) -> None:
    assert any(p == "/stages/0/id" for p, _ in pairs(setp(REC, ["stages", 0, "id"], sid)))


@pytest.mark.req("FR-001-23")
@pytest.mark.parametrize(
    ("seed", "expected"),
    [
        (0, True),
        (1, True),
        (2**63 - 1, True),
        (-1, False),
        (2**63, False),
        (2**64, False),
        (1.5, False),
        (True, False),
        (False, False),
        ("42", False),
        (None, False),
        ([1], False),
    ],
)
def test_fr_001_23_seed_range_and_type(seed: Any, expected: bool) -> None:
    assert ok(setp(REC, ["seed"], seed)) is expected


@pytest.mark.req("FR-001-23")
@pytest.mark.parametrize(
    ("path", "hostile"),
    [
        (["stages", 0, "inputs", 0, "id"], ["../../etc/passwd", "a/b", "a\\b", "C:/x", "", "A", "a" * 65, "x y", ".."]),
        (
            ["stages", 0, "outputs", 0, "path"],
            [
                "/abs/x",
                "C:/x",
                "..\\x",
                "a/../b",
                "x.",
                "../x",
                "a//b",
                "./a",
                "a/",
                "",
                "a b",
                "~/x",
                "\u00e9.txt",
                "a\\b",
            ],
        ),
        (
            ["stages", 0, "inputs", 0, "sha256"],
            ["A" * 64, "a" * 63, "a" * 65, "sha256:" + "a" * 64, "g" * 64, "", " " + "a" * 63, "a" * 64 + "\n\n"],
        ),
        (["stages", 2, "binaries", 0, "sha256"], ["A" * 64, "a" * 63, "a" * 65, "sha256:" + "a" * 64]),
        (["stages", 0, "entry"], ["os; rm -rf /", "pkg.mod -c", "Pkg.Mod", "pkg/mod", "../x", "a b"]),
    ],
    ids=["input-id", "output-path", "input-sha256", "binary-sha256", "entry"],
)
def test_fr_001_23_unsafe_paths_ids_digests_and_entries(path: list[Any], hostile: list[Any]) -> None:
    assert ok(REC)
    for value in hostile:
        got = pairs(setp(REC, path, value))
        assert any(p == ptr(path) for p, _ in got), (ptr(path), value, sorted(got)[:3])


@pytest.mark.req("FR-001-23")
@pytest.mark.parametrize("case", ["Z9", "a1", "", "bench ", 3])
def test_fr_001_23_unknown_case(case: Any) -> None:
    assert any(p == "/case" for p, _ in pairs(setp(REC, ["case"], case)))


@pytest.mark.req("FR-001-23")
def test_fr_001_23_unknown_determinism_and_resource_kind() -> None:
    assert any(
        p.startswith("/stages/1/determinism") for p, _ in pairs(setp(REC, ["stages", 1, "determinism"], "exact"))
    )
    assert any(p == "/stages/0/resources/gpu" for p, _ in pairs(setp(REC, ["stages", 0, "resources", "gpu"], "shared")))


@pytest.mark.req("FR-001-23")
def test_fr_001_23_corpus_hostile_values() -> None:
    assert_corpus("FR-001-23", 36)


def v(doc: Any) -> list[Any]:
    from pitstudio.contracts import validate

    return validate(doc, "recipe")


def vptr(errors: list[Any]) -> list[str]:
    return [cs.get(e, "pointer") for e in errors]


@pytest.mark.req("FR-001-23")
@pytest.mark.parametrize(
    ("total", "size", "fails"),
    [
        (10_000, 1, False),
        (10_001, 1, True),
        (20_000, 2, False),
        (20_001, 2, True),
        (1_000_000_000, 100_000, False),
        (1_000_000_000, 99_999, True),
        (1, 10_000_000, False),
        (100, 7, False),
    ],
)
def test_fr_001_23_more_than_10000_shards_is_rejected_by_validate(total: int, size: int, fails: bool) -> None:
    shards = -(-total // size)  # ceiling division, the oracle: shards = ceil(total / shard_size)
    assert (shards > 10_000) is fails
    doc = setp(REC, ["stages", 1, "shardable"], {"shard_size": size, "total": total})
    errors = v(doc)
    flagged = [p for p in vptr(errors) if p.startswith("/stages/1/shardable")]
    assert bool(flagged) is fails, (total, size, vptr(errors))


def canonical_size(value: Any) -> int:
    return len(json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8"))


def params_of_size(target: int) -> dict:
    """64 keys whose strings (each <= 1024 characters) bring the canonical size to exactly ``target`` bytes."""
    p = {f"k{i:02d}": "" for i in range(64)}
    remaining = target - canonical_size(p)
    for key in p:
        n = min(1024, remaining)
        p[key] = "x" * n
        remaining -= n
    assert remaining == 0
    assert canonical_size(p) == target
    return p


@pytest.mark.req("FR-001-23")
@pytest.mark.parametrize(("target", "fails"), [(65_000, False), (65_536, False), (65_537, True), (66_000, True)])
def test_fr_001_23_params_canonical_size_cap_is_65536_bytes(target: int, fails: bool) -> None:
    params = params_of_size(target)
    doc = setp(REC, ["stages", 1, "params"], params)
    assert ok(doc), "within the schema's per-key limits: only the canonical size can reject it"
    flagged = [p for p in vptr(v(doc)) if p.startswith("/stages/1/params")]
    assert bool(flagged) is fails


@pytest.mark.req("FR-001-23")
def test_fr_001_23_validate_accepts_the_valid_recipes() -> None:
    assert v(REC) == []
    assert v(BENCH) == []


# ----------------------------------------------------------------------------------------------------------------
# FR-001-24 · job request (data-model 3.5)
# ----------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-001-24")
@pytest.mark.parametrize(
    "field",
    [
        "entry",
        "env",
        "params",
        "inputs",
        "resources",
        "determinism",
        "timeout_s",
        "outputs",
        "tool",
        "requires",
        "binaries",
        "retry",
        "shardable",
        "variant",
        "seed",
        "case",
        "id",
        "stages_inline",
        "description",
        "path",
        "yaml",
        "cwd",
    ],
)
def test_fr_001_24_stage_fields_and_inline_recipe_fields_are_unknown_fields_of_a_job_request(field: str) -> None:
    assert ("", "additionalProperties") in pairs(setp(JOB, [field], "x"), JOB_T)
    if field not in ("id", "variant"):  # the two fields of a stage key
        assert ("/stages/0", "additionalProperties") in pairs(setp(JOB, ["stages", 0, field], "x"), JOB_T)


@pytest.mark.req("FR-001-24")
def test_fr_001_24_an_inline_recipe_is_rejected() -> None:
    inline = setp(JOB, ["recipe"], REC)
    assert any(p == "/recipe" for p, _ in pairs(inline, JOB_T))
    assert not ok({**REC, "profile": "laptop"}, JOB_T)
    assert not ok(REC, JOB_T)


@pytest.mark.req("FR-001-24")
@pytest.mark.parametrize(
    ("recipe", "expected"),
    [
        ("a", True),
        ("a2-haulage", True),
        ("0a", True),
        ("a" * 64, True),
        ("", False),
        ("A2", False),
        ("a" * 65, False),
        ("a_b", False),
        ("a/b", False),
        ("../a", False),
        ("a.b", False),
        ("-a", False),
        ("a b", False),
        (None, False),
        (1, False),
        ("a;ls", False),
        ("a\u00e9", False),
    ],
)
def test_fr_001_24_recipe_id_pattern(recipe: Any, expected: bool) -> None:
    assert ok(setp(JOB, ["recipe"], recipe), JOB_T) is expected


@pytest.mark.req("FR-001-24")
@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("laptop-rtx5000ada", True),
        ("a", True),
        ("a" * 64, True),
        ("", False),
        ("Laptop", False),
        ("a" * 65, False),
        ("a_b", False),
        ("../p", False),
        (None, False),
    ],
)
def test_fr_001_24_profile_id_pattern(profile: Any, expected: bool) -> None:
    assert ok(setp(JOB, ["profile"], profile), JOB_T) is expected


@pytest.mark.req("FR-001-24")
def test_fr_001_24_required_fields_and_optional_ones() -> None:
    assert ("", "required") in pairs(delp(JOB, ["recipe"]), JOB_T)
    assert ("", "required") in pairs(delp(JOB, ["profile"]), JOB_T)
    for f in ("stages", "force", "rerun_check"):
        assert ok(delp(JOB, [f]), JOB_T)
    assert ok({"recipe": "a", "profile": "p"}, JOB_T)
    for f in ("force", "rerun_check"):
        for bad in ("yes", 1, 0, None, "true"):
            assert not ok(setp(JOB, [f], bad), JOB_T), (f, bad)


@pytest.mark.req("FR-001-24")
def test_fr_001_24_stage_selection_is_1_to_64_unique_stage_keys() -> None:
    def keys(n: int) -> list[dict]:
        return [{"id": "s00_download", "variant": f"v{i}"} for i in range(n)]

    assert ok(setp(JOB, ["stages"], keys(1)), JOB_T)
    assert ok(setp(JOB, ["stages"], keys(64)), JOB_T)
    assert ("/stages", "maxItems") in pairs(setp(JOB, ["stages"], keys(65)), JOB_T)
    assert ("/stages", "minItems") in pairs(setp(JOB, ["stages"], []), JOB_T)
    assert ("/stages", "uniqueItems") in pairs(
        setp(JOB, ["stages"], [{"id": "s00_download"}, {"id": "s00_download"}]), JOB_T
    )
    dup = [{"id": "st50_physics", "variant": "dem"}] * 2
    assert ("/stages", "uniqueItems") in pairs(setp(JOB, ["stages"], dup), JOB_T)
    same_id_other_variant = [{"id": "st50_physics", "variant": "dem"}, {"id": "st50_physics", "variant": "mpm"}]
    assert ok(setp(JOB, ["stages"], same_id_other_variant), JOB_T)
    assert ok(setp(JOB, ["stages"], [{"id": "st50_physics"}, {"id": "st50_physics", "variant": "dem"}]), JOB_T)
    for bad in (
        {"id": "st99_magic"},
        {"variant": "dem"},
        {"id": "s00_download", "variant": "Bad"},
        {"id": "s00_download", "variant": ""},
        "s00_download",
        None,
    ):
        assert not ok(setp(JOB, ["stages"], [bad]), JOB_T), bad
    assert not ok(setp(JOB, ["stages"], None), JOB_T)


@pytest.mark.req("FR-001-24")
def test_fr_001_24_corpus_job_request_fixtures() -> None:
    items = [e for e in cs.schema_level(schema="recipe") if e["kind"] == "job-request" and not e["valid"]]
    assert len(items) >= 12
    for e in items:
        assert (e["pointer"], e["keyword"]) in pairs(cs.fixture_json(e), JOB_T), e["file"]
