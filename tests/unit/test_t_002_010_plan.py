# ruff: noqa: E501, PT018
"""T-002-010: `studio plan` (US-002-1).

Requirements: FR-002-01, FR-002-02, FR-002-03, FR-002-06, NFR-002-02.

Expected API (stated for the implementer; names are assumptions where the spec is silent, see the red report):
  * `pitstudio.runner.cli.main(["plan", <recipe.yaml>, "--profile", <id>, ["--json"]]) -> int`;
  * `--json` prints ONE JSON document `{"recipe": id, "profile": id, "stages": [...]}`; each stage object has
    `key` ("id" or "id@variant"), `env`, `tool`, `lock` ("gpu0.compute" | "gpu0.nvenc" | null), `cache_key`
    (64 hex, or null while `pending`), `status` ("hit" | "miss" | "pending" | "env-disabled" | "does-not-fit"),
    `vram_gib_est`, `disk_gib_est` (numbers or null), `shards` (integer, 1 when not sharded);
  * stages are listed in the lexicographically smallest topological order (ties broken by key string);
  * the text form (no --json) prints one line per stage in the same order, each line starting with the key;
  * recipes and profiles are located through PITSTUDIO_REPO (the repository root), PITSTUDIO_STORE is the store;
  * `pitstudio.runner.queue.jobs()` lists the queued jobs of the store named by PITSTUDIO_STORE.
Oracles: hand-derived orders, a reference Kahn algorithm and edge-order check written here, hand calculation of
ceil(est * 2**30) + margin * 2**30 against the device size, hostile recipes built by hand.
"""

from __future__ import annotations

import heapq
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import GIB, recipe, stage, up


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


def key_of(s: dict[str, Any]) -> str:
    return s["id"] + (f"@{s['variant']}" if s.get("variant") else "")


def ref_order(stages: list[dict[str, Any]]) -> list[str]:
    """Reference: Kahn's algorithm with a min-heap on the key string (lexicographically smallest topological order)."""
    keys = {key_of(s) for s in stages}
    deps: dict[str, set[str]] = {key_of(s): set() for s in stages}
    for s in stages:
        for i in s["inputs"]:
            if "stage" in i:
                deps[key_of(s)].add(i["stage"] + (f"@{i['variant']}" if i.get("variant") else ""))
    assert all(d <= keys for d in deps.values())
    heap = [k for k, d in deps.items() if not d]
    heapq.heapify(heap)
    done: list[str] = []
    while heap:
        k = heapq.heappop(heap)
        done.append(k)
        for other, d in deps.items():
            if k in d:
                d.discard(k)
                if not d and other not in done and other not in heap:
                    heapq.heappush(heap, other)
    assert len(done) == len(keys)
    return done


def classic_recipe() -> dict[str, Any]:
    # written in a scrambled order on purpose; edges: s05<-s00, s10<-s00, s20<-s10+s05, s30<-s20, st20<-st10
    return recipe(
        "classic",
        [
            stage("st20_pit_design", inputs=[up("st10_terrain", "out.bin")]),
            stage("s30_train", inputs=[up("s20_feature_extraction", "out.bin")]),
            stage("s20_feature_extraction", inputs=[up("s10_preprocess", "out.bin"), up("s05_synthesize", "out.bin")]),
            stage("st10_terrain"),
            stage("s10_preprocess", inputs=[up("s00_download", "out.bin")]),
            stage("s05_synthesize", inputs=[up("s00_download", "out.bin")]),
            stage("s00_download"),
        ],
    )


# hand-derived: ready set {s00, st10} -> s00; {s05, s10, st10} -> s05; {s10, st10} -> s10; {s20, st10} -> s20 ('2' < 't');
# {s30, st10} -> s30 ('3' < 't'); {st10} -> st10; {st20} -> st20
CLASSIC_ORDER = [
    "s00_download",
    "s05_synthesize",
    "s10_preprocess",
    "s20_feature_extraction",
    "s30_train",
    "st10_terrain",
    "st20_pit_design",
]


@pytest.mark.req("FR-002-01")
def test_fr_002_01_plan_json_lists_stages_in_deterministic_topological_order(world) -> None:
    doc = classic_recipe()
    world.write_recipe(doc)
    plan = world.plan_json("classic")
    keys = [s["key"] for s in plan["stages"]]
    assert keys == CLASSIC_ORDER
    assert keys == ref_order(doc["stages"])  # the reference implementation agrees with the hand derivation
    pos = {k: i for i, k in enumerate(keys)}
    for s in doc["stages"]:
        for i in s["inputs"]:
            assert pos[i["stage"]] < pos[s["id"]]
    assert plan["recipe"] == "classic" and plan["profile"] == "test-profile"
    by = {s["key"]: s for s in plan["stages"]}
    # roots have a cache key; everything downstream of a miss is pending (its inputs are not known yet)
    for root in ("s00_download", "st10_terrain"):
        assert by[root]["status"] == "miss"
        assert len(by[root]["cache_key"]) == 64 and set(by[root]["cache_key"]) <= set("0123456789abcdef")
    for k in ("s05_synthesize", "s10_preprocess", "s20_feature_extraction", "s30_train", "st20_pit_design"):
        assert by[k]["status"] == "pending" and by[k]["cache_key"] is None
    assert all(s["env"] in rw.ALL_ENVS and s["tool"] for s in plan["stages"])
    assert by["s00_download"]["env"] == "pipeline" and by["st10_terrain"]["env"] == "studio"


@pytest.mark.req("FR-002-01")
def test_fr_002_01_plan_row_content_lock_estimates_and_shards(world) -> None:
    doc = recipe(
        "rows",
        [
            stage("st50_physics", gpu="exclusive", vram=6.0, disk=4.0, variant="dem", shardable=(1000, 20000)),
            stage("st56_encode", gpu="nvenc", disk=0.5, inputs=[up("st50_physics", "out.bin", "dem")]),
            stage("s10_preprocess", disk=1.25),
        ],
    )
    world.write_recipe(doc)
    by = {s["key"]: s for s in world.plan_json("rows")["stages"]}
    phys = by["st50_physics@dem"]
    assert (phys["lock"], phys["vram_gib_est"], phys["disk_gib_est"], phys["shards"], phys["env"], phys["tool"]) == (
        "gpu0.compute",
        6.0,
        4.0,
        20,
        "studio",
        "warp",
    )
    enc = by["st56_encode"]
    assert enc["lock"] == "gpu0.nvenc" and enc["disk_gib_est"] == 0.5 and enc["shards"] == 1
    cpu = by["s10_preprocess"]
    assert cpu["lock"] is None and cpu["vram_gib_est"] is None and cpu["disk_gib_est"] == 1.25 and cpu["shards"] == 1
    assert set(by) == {"st50_physics@dem", "st56_encode", "s10_preprocess"}


@pytest.mark.req("FR-002-01")
def test_fr_002_01_plan_text_form_prints_one_line_per_stage_in_order(world) -> None:
    world.write_recipe(classic_recipe())
    r = world.cli("plan", str(world.recipes["classic"]), "--profile", "test-profile")
    assert r.code == 0, r.text
    idx = [r.out.index(k) for k in CLASSIC_ORDER]
    assert idx == sorted(idx)
    lines = [ln for ln in r.out.splitlines() if ln.strip()]
    for k in CLASSIC_ORDER:
        assert sum(1 for ln in lines if ln.lstrip().startswith(k)) == 1, f"one line starting with {k}"
    assert "pending" in r.out and "miss" in r.out


@pytest.mark.req("FR-002-01")
@pytest.mark.req("NFR-002-02")
def test_nfr_002_02_plan_of_64_stages_with_10000_shards_is_fast(world) -> None:
    stages = [stage("st10_terrain", variant=f"v{i:02d}") for i in range(64)]
    for i in range(1, 64, 2):  # half of the stages form a chain, the rest are independent roots
        stages[i]["inputs"] = [up("st10_terrain", "out.bin", f"v{i - 1:02d}")]
    stages[10]["shardable"] = {"shard_size": 1, "total": 10000}
    world.write_recipe(recipe("big", stages))
    world.plan_json("big")  # warm-up: imports and caches are not part of the budget
    t0 = time.perf_counter()
    r = world.cli("plan", str(world.recipes["big"]), "--profile", "test-profile", "--json")
    elapsed = time.perf_counter() - t0
    assert r.code == 0, r.text
    plan = json.loads(r.out)
    assert len(plan["stages"]) == 64
    assert next(s for s in plan["stages"] if s["key"] == "st10_terrain@v10")["shards"] == 10000
    assert elapsed <= 5.0, f"plan took {elapsed:.2f} s (> 5 s)"


# ---- FR-002-02: plan touches no GPU library, lock, process or store file -----------------------------------------
@pytest.mark.req("FR-002-02")
def test_fr_002_02_plan_imports_no_gpu_binding_takes_no_lock_starts_no_process_and_writes_nothing(world) -> None:
    doc = recipe(
        "pure",
        [
            stage("st50_physics", gpu="exclusive", vram=2.0),
            stage("st56_encode", gpu="nvenc", inputs=[up("st50_physics", "out.bin")]),
        ],
    )
    world.write_recipe(doc)
    world.hold("a hold file must not stop planning")
    rw.block_modules(world.monkeypatch, "pynvml", "filelock")
    calls = rw.forbid_popen(world.monkeypatch)
    store_before, repo_before, locks_before = (
        world.snapshot_store(),
        world.snapshot_repo(),
        sorted(p.name for p in world.lock_dir.iterdir()),
    )
    r = world.cli("plan", str(world.recipes["pure"]), "--profile", "test-profile", "--json")
    assert r.code == 0, r.text
    assert calls == []
    assert world.snapshot_store() == store_before
    assert world.snapshot_repo() == repo_before
    assert sorted(p.name for p in world.lock_dir.iterdir()) == locks_before == ["gpu0.hold"]
    assert not any(n.endswith((".compute", ".nvenc")) for n in locks_before)


@pytest.mark.req("FR-002-02")
def test_fr_002_02_plan_works_without_a_store_directory_and_without_a_selected_backend(world) -> None:
    world.write_recipe(recipe("nostore", [stage("st50_physics", gpu="exclusive", vram=2.0)]))
    world.monkeypatch.delenv("PITSTUDIO_GPU_BACKEND")  # device capacity then comes from the profile's `gpus`
    rw.block_modules(world.monkeypatch, "pynvml", "filelock")
    import shutil

    shutil.rmtree(world.store)
    r = world.cli("plan", str(world.recipes["nostore"]), "--profile", "test-profile", "--json")
    assert r.code == 0, r.text
    assert not world.store.exists(), "plan must not create the store"
    assert json.loads(r.out)["stages"][0]["status"] == "miss"


# ---- FR-002-06: does-not-fit and env-disabled --------------------------------------------------------------------
@pytest.mark.req("FR-002-06")
@pytest.mark.parametrize(
    ("est_gib", "status"),
    [
        (46.5, "miss"),  # 46.5 * 2**30 + 1.5 * 2**30 = 48 * 2**30 = the device size: fits exactly
        (46.5000001, "does-not-fit"),  # one hair over: 1e-7 GiB = 107.4 bytes more than the 48 GiB the device offers
        (47.0, "does-not-fit"),
        (200.0, "does-not-fit"),
        (0.5, "miss"),
    ],
)
def test_fr_002_06_vram_estimate_plus_margin_against_the_largest_device(world, est_gib: float, status: str) -> None:
    world.write_recipe(recipe("fit", [stage("st50_physics", gpu="exclusive", vram=est_gib)]))
    # hand calculation of the rule, independent of the runner
    margin = 1.5
    import math

    needs = math.ceil(est_gib * GIB) + margin * GIB
    assert (needs > 48 * GIB) == (status == "does-not-fit")
    assert world.plan_json("fit")["stages"][0]["status"] == status


@pytest.mark.req("FR-002-06")
def test_fr_002_06_env_not_enabled_by_the_profile_is_env_disabled_not_an_error(world) -> None:
    prof = rw.profile_doc(id="ci-linux", envs_enabled=["studio", "pipeline"])
    world.write_profile(prof)
    world.write_recipe(
        recipe(
            "envs",
            [
                stage("s10_preprocess"),
                stage("st52_rtx_render", gpu="exclusive", vram=2.0),
                stage("st53_sensors", gpu="exclusive", vram=2.0),
            ],
        )
    )
    by = {s["key"]: s["status"] for s in world.plan_json("envs", "ci-linux")["stages"]}
    assert by == {"s10_preprocess": "miss", "st52_rtx_render": "env-disabled", "st53_sensors": "env-disabled"}


@pytest.mark.req("FR-002-06")
@pytest.mark.parametrize("case", ["does-not-fit", "env-disabled"])
def test_fr_002_06_run_refuses_such_a_stage_with_exit_5_before_taking_any_lock(world, case: str) -> None:
    if case == "does-not-fit":
        world.write_recipe(recipe("refuse", [stage("st50_physics", gpu="exclusive", vram=60.0)]))
        prof = "test-profile"
    else:
        world.write_profile(rw.profile_doc(id="no-isaac", envs_enabled=["studio", "pipeline"]))
        world.write_recipe(recipe("refuse", [stage("st52_rtx_render", gpu="exclusive", vram=2.0)]))
        prof = "no-isaac"
    spy = rw.PopenSpy(world.monkeypatch)
    r = world.cli("run", str(world.recipes["refuse"]), "--profile", prof)
    assert r.code == 5, r.text
    assert not any("ps_fake_stages" in " ".join(a) for a in spy.argv_lists()), "no stage process may start"
    assert world.ledger_rows() == []
    assert [p.name for p in world.lock_dir.iterdir()] == [], "no lock may be taken before refusing"


# ---- FR-002-03: hostile recipes -----------------------------------------------------------------------------------
def _bad(name: str, doc: dict[str, Any], offenders: list[str]) -> tuple[str, dict[str, Any], list[str]]:
    return name, doc, offenders


HOSTILE: list[tuple[str, dict[str, Any], list[str]]] = [
    _bad(
        "cycle",
        recipe(
            "h-cycle",
            [
                stage("s05_synthesize", inputs=[up("s10_preprocess", "out.bin")]),
                stage("s10_preprocess", inputs=[up("s05_synthesize", "out.bin")]),
                stage("s00_download"),
            ],
        ),
        ["s05_synthesize", "s10_preprocess"],
    ),
    _bad(
        "self-cycle",
        recipe("h-self", [stage("s10_preprocess", inputs=[up("s10_preprocess", "out.bin")])]),
        ["s10_preprocess"],
    ),
    _bad(
        "unknown stage reference",
        recipe("h-ref", [stage("s10_preprocess", inputs=[up("st10_terrain", "out.bin")])]),
        ["s10_preprocess"],
    ),
    _bad(
        "unknown output of a known stage",
        recipe("h-out", [stage("s00_download"), stage("s10_preprocess", inputs=[up("s00_download", "nope.bin")])]),
        ["s10_preprocess"],
    ),
    _bad(
        "duplicate stage keys", recipe("h-dup", [stage("s10_preprocess"), stage("s10_preprocess")]), ["s10_preprocess"]
    ),
    _bad(
        "oom fallback key absent from params",
        recipe(
            "h-oom",
            [stage("st50_physics", gpu="exclusive", vram=2.0, params={"particles": 100}, retry=[{"no_such_param": 1}])],
        ),
        ["st50_physics"],
    ),
    _bad(
        "requires probe unknown to run_bench",
        recipe("h-probe", [stage("st50_physics", gpu="exclusive", vram=2.0, requires=["no_such_probe"])]),
        ["st50_physics"],
    ),
    _bad(
        "tool absent from the registry",
        recipe("h-tool", [stage("s10_preprocess", tool="ghost-tool")]),
        ["s10_preprocess"],
    ),
    _bad(
        "unknown output validator",
        recipe("h-val", [stage("s10_preprocess", validator="bogus-validator")]),
        ["s10_preprocess"],
    ),
    _bad("10,001 shards", recipe("h-shards", [stage("st10_terrain", shardable=(1, 10001))]), ["st10_terrain"]),
    _bad(
        "several offenders are all named",
        recipe(
            "h-many",
            [
                stage("s10_preprocess", tool="ghost-tool"),
                stage("s20_feature_extraction", validator="bogus-validator"),
                stage("st10_terrain", shardable=(1, 10001)),
                stage("s00_download"),
            ],
        ),
        ["s10_preprocess", "s20_feature_extraction", "st10_terrain"],
    ),
]


@pytest.mark.req("FR-002-03")
@pytest.mark.parametrize(("name", "doc", "offenders"), HOSTILE, ids=[h[0] for h in HOSTILE])
@pytest.mark.parametrize("command", ["plan", "run"])
def test_fr_002_03_hostile_recipe_exits_2_names_every_offender_and_queues_nothing(
    world, name: str, doc: dict[str, Any], offenders: list[str], command: str
) -> None:
    world.write_recipe(doc)
    calls = rw.forbid_popen(world.monkeypatch)
    r = world.cli(command, str(world.recipes[doc["id"]]), "--profile", "test-profile")
    assert r.code == 2, f"{name}/{command}: exit {r.code}\n{r.text}"
    for o in offenders:
        assert o in r.text, f"{name}: the message must name {o}: {r.text!r}"
    assert calls == [] and world.ledger_rows() == []
    from pitstudio.runner import queue

    assert queue.jobs() == []
    assert not (world.store / "runs").exists() or list((world.store / "runs").iterdir()) == []


@pytest.mark.req("FR-002-03")
@pytest.mark.parametrize(
    "validator",
    ["file", "json", "jsonl", "contract-manifest", "contract-events", "stage-physics-observables", "stage-x1"],
)
def test_fr_002_03_runner_side_and_stage_side_validators_are_accepted(world, validator: str) -> None:
    world.write_recipe(recipe("val-ok", [stage("s10_preprocess", validator=validator)]))
    assert world.cli("plan", str(world.recipes["val-ok"]), "--profile", "test-profile").code == 0


@pytest.mark.req("FR-002-03")
def test_fr_002_03_exactly_10000_shards_is_accepted_and_known_probe_and_tool_pass(world) -> None:
    world.write_recipe(
        recipe(
            "edge-ok",
            [
                stage(
                    "st50_physics",
                    gpu="exclusive",
                    vram=2.0,
                    shardable=(3, 30000),
                    requires=["warp_newton", "nvenc"],
                    retry=[{"particles": 5}],
                    params={"particles": 9},
                )
            ],
        )
    )
    plan = world.plan_json("edge-ok")
    assert plan["stages"][0]["shards"] == 10000


@pytest.mark.req("FR-002-03")
@pytest.mark.parametrize(
    "body",
    [
        "",
        "﻿",
        "just a string",
        "stages: []\n",
        "id: x\n",
        "- 1\n- 2\n",
        "id: ‮evil\ncase: bench\nseed: 1\nstages: []\n",
        "\x00\x00",
    ],
    ids=["empty", "bom-only", "scalar", "no-stages", "partial", "list", "bidi-unicode", "nul-bytes"],
)
def test_fr_002_03_malformed_recipe_files_are_usage_errors_not_crashes(world, body: str) -> None:
    p = world.repo / "studio" / "recipes" / "cases" / "broken.yaml"
    p.write_text(body, encoding="utf-8")
    r = world.cli("plan", str(p), "--profile", "test-profile")
    assert r.code == 2, r.text
    assert "Traceback" not in r.text
