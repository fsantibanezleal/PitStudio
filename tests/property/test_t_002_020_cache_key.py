# ruff: noqa: E501, PT018
"""T-002-020: cache key and derived seed (US-002-3).

Requirements: FR-002-08, FR-002-09, P-002-01, P-002-02, P-002-03, P-002-05.

Expected API (module `pitstudio.runner.cache`, stated for the implementer):
  * `cache_key(*, stage: dict, code: str, lock: str, params: dict, seed: int, inputs: dict[str, str],
    binaries: dict[str, str], shard: dict | None) -> str`: lowercase hex SHA-256 of the RFC 8785 canonical JSON of
    `{"stage": stage, "code": code, "lock": lock, "params": params, "seed": seed, "inputs": inputs,
    "binaries": binaries, "shard": shard}`; `stage` is `{"id": ..., "variant": ...}` (the tests always pass a variant
    when they compare against a hand-computed digest; see the red report for the no-variant ambiguity);
  * `derive_seed(seed0: int, key: str, index: int) -> int` = int.from_bytes(SHA256(JCS([seed0, key, index]))[0:8],
    "big") & (2**63 - 1), with `key` the stage key string ("id" or "id@variant");
  * `code_digest(repo: Path, env: str) -> str`: SHA-256 of the RFC 8785 JSON list of [POSIX relative path, SHA-256 of
    bytes] for every regular file under the environment's code roots and under `src/pitstudio/runner/stagekit/`
    (plan.md D7), sorted by path, excluding `__pycache__/`, `.venv/`, `.pytest_cache/`, `*.egg-info/`,
    `node_modules/` and `*.pyc`;
  * `lock_digest(repo: Path, env: str) -> str`: SHA-256 of the bytes of the environment's lock file (plan.md D7);
  * `studio plan --json` rows of stages without upstream stages carry `cache_key` (see test_t_002_010_plan.py).
Oracles: the formula recomputed with `hashlib` over `json.dumps(sort_keys=True, separators=(",", ":"))`, which equals
RFC 8785 for integers, ASCII strings, booleans, null and nested objects (plan.md Test strategy); the two seed vectors
of FR-002-09; single-component mutations (the key MUST change); reformatted YAML renderings of one recipe.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import jcs_simple, recipe, stage

ORIG_PLATFORM = sys.platform
HEX = "0123456789abcdef"


def ref_key(
    stage_key: dict, code: str, lock: str, params: dict, seed: int, inputs: dict, binaries: dict, shard: dict | None
) -> str:
    obj = {
        "stage": stage_key,
        "code": code,
        "lock": lock,
        "params": params,
        "seed": seed,
        "inputs": inputs,
        "binaries": binaries,
        "shard": shard,
    }
    return hashlib.sha256(jcs_simple(obj)).hexdigest()


def ref_seed(seed0: int, key: str, i: int) -> int:
    return int.from_bytes(hashlib.sha256(jcs_simple([seed0, key, i])).digest()[:8], "big") & (2**63 - 1)


BASE = {
    "stage_key": {"id": "st50_physics", "variant": "dem"},
    "code": "a" * 64,
    "lock": "b" * 64,
    "params": {
        "solver": "dem",
        "counts": {"particles": 20000},
        "flags": {"on": True, "off": False},
        "tags": ["x", "y"],
        "none": None,
    },
    "seed": 2175241071291199046,
    "inputs": {"s00_download/raw/network.geojson": "c" * 64, "example-haul-network": "2" * 64},
    "binaries": {"ffmpeg": "9" * 64},
    "shard": {"index": 1, "size": 1000, "total": 20000},
}


def call(cache: Any, **over: Any) -> str:
    a = {**BASE, **over}
    return cache.cache_key(
        stage=a["stage_key"],
        code=a["code"],
        lock=a["lock"],
        params=a["params"],
        seed=a["seed"],
        inputs=a["inputs"],
        binaries=a["binaries"],
        shard=a["shard"],
    )


# ---- FR-002-08: the formula, by hand -----------------------------------------------------------------------------------
@pytest.mark.req("FR-002-08")
@pytest.mark.parametrize(
    "over",
    [
        {},
        {"shard": None},
        {"inputs": {}, "binaries": {}},
        {"params": {}, "shard": None, "inputs": {}, "binaries": {}},
        {"stage_key": {"id": "s00_download", "variant": "x1"}, "params": {"a": 1, "b": {"c": {"d": "e"}}}},
        {"seed": 0},
        {"seed": 2**63 - 1},
        {"params": {"unicode": "café", "quote": 'say "hi"', "neg": -7}},
    ],
    ids=["base", "unsharded", "no-inputs", "all-empty", "other-stage", "seed-0", "seed-max", "unicode-and-escapes"],
)
def test_fr_002_08_key_is_sha256_of_canonical_json_of_the_nine_components(over: dict[str, Any]) -> None:
    from pitstudio.runner import cache

    a = {**BASE, **over}
    expected = ref_key(
        a["stage_key"], a["code"], a["lock"], a["params"], a["seed"], a["inputs"], a["binaries"], a["shard"]
    )
    got = call(cache, **over)
    assert got == expected
    assert len(got) == 64 and got == got.lower() and set(got) <= set(HEX)


@pytest.mark.req("FR-002-08")
def test_fr_002_08_key_ignores_dict_insertion_order_and_inputs_are_a_mapping() -> None:
    from pitstudio.runner import cache

    shuffled = {
        "stage_key": {"variant": "dem", "id": "st50_physics"},
        "params": {
            "none": None,
            "tags": ["x", "y"],
            "flags": {"off": False, "on": True},
            "counts": {"particles": 20000},
            "solver": "dem",
        },
        "inputs": dict(reversed(list(BASE["inputs"].items()))),
    }
    assert call(cache, **shuffled) == call(cache)
    # list order inside a param value IS significant
    assert call(cache, params={**BASE["params"], "tags": ["y", "x"]}) != call(cache)


# ---- FR-002-09 / P-002-05: seeds ---------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-09")
def test_fr_002_09_the_two_published_seed_vectors() -> None:
    from pitstudio.runner import cache

    assert cache.derive_seed(20261004, "st50_physics", 0) == 2175241071291199046
    assert cache.derive_seed(20261004, "st50_physics", 1) == 3347990621277448462


@pytest.mark.req("FR-002-09")
@pytest.mark.parametrize(
    ("seed0", "key", "i"),
    [
        (0, "s00_download", 0),
        (2**63 - 1, "st50_physics@dem", 9999),
        (1, "st56_encode", 17),
        (20261004, "st50_physics@dem", 3),
        (42, "s64_bench@gpu-a", 0),
    ],
)
def test_fr_002_09_seed_equals_the_formula_for_variants_and_shards(seed0: int, key: str, i: int) -> None:
    from pitstudio.runner import cache

    got = cache.derive_seed(seed0, key, i)
    assert got == ref_seed(seed0, key, i)
    assert 0 <= got < 2**63


@pytest.mark.req("P-002-05")
@settings(max_examples=200, deadline=None)
@given(
    seed0=st.integers(0, 2**63 - 1),
    key=st.from_regex(r"[a-z][a-z0-9_]{1,31}(@[a-z0-9][a-z0-9-]{0,31})?", fullmatch=True),
    i=st.integers(0, 9999),
)
def test_p_002_05_seed_equals_the_formula(seed0: int, key: str, i: int) -> None:
    from pitstudio.runner import cache

    assert cache.derive_seed(seed0, key, i) == ref_seed(seed0, key, i)


@pytest.mark.req("P-002-05")
def test_p_002_05_no_collision_over_100000_distinct_key_shard_pairs() -> None:
    from pitstudio.runner import cache

    keys = [f"st50_physics@v{v:03d}" for v in range(100)] + [f"s10_preprocess@v{v:03d}" for v in range(100)]
    seeds = {cache.derive_seed(20261004, k, i) for k in keys for i in range(500)}
    assert len(seeds) == 200 * 500 == 100_000


# ---- P-002-01: determinism --------------------------------------------------------------------------------------------
SCRIPT = (
    "import json, sys\n"
    "from pitstudio.runner import cache\n"
    "a = json.loads(sys.argv[1])\n"
    "print(cache.cache_key(stage=a['stage_key'], code=a['code'], lock=a['lock'], params=a['params'], seed=a['seed'],"
    " inputs=a['inputs'], binaries=a['binaries'], shard=a['shard']))\n"
)


@pytest.mark.req("P-002-01")
def test_p_002_01_same_key_in_new_processes_under_other_cwd_store_host_user_and_hash_seed(tmp_path: Path) -> None:
    ref = ref_key(
        **{k: BASE[k] for k in ("code", "lock", "params", "seed", "inputs", "binaries", "shard")},
        stage_key=BASE["stage_key"],
    )
    outs = set()
    for n, hashseed in enumerate(("0", "1", "4242")):
        cwd = tmp_path / f"cwd{n}"
        cwd.mkdir()
        env = {
            **os.environ,
            "PYTHONPATH": str(rw.SRC),
            "PYTHONHASHSEED": hashseed,
            "PITSTUDIO_STORE": str(cwd / "store"),
            "COMPUTERNAME": f"host{n}",
            "HOSTNAME": f"host{n}",
            "USERNAME": f"user{n}",
            "USER": f"user{n}",
            "TZ": ("UTC", "Asia/Tokyo", "America/Santiago")[n],
        }
        r = subprocess.run(
            [sys.executable, "-c", SCRIPT, json.dumps(BASE)],
            capture_output=True,
            text=True,
            cwd=str(cwd),
            env=env,
            timeout=60,
        )
        assert r.returncode == 0, r.stderr
        outs.add(r.stdout.strip())
    assert outs == {ref}


@pytest.mark.req("P-002-01")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    params=st.dictionaries(
        st.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True),
        st.one_of(st.integers(-(10**6), 10**6), st.text("abcxyz", max_size=8), st.booleans(), st.none()),
        max_size=6,
    ),
    seed=st.integers(0, 2**63 - 1),
)
def test_p_002_01_key_is_stable_under_platform_and_cwd_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory, params: dict[str, Any], seed: int
) -> None:
    from pitstudio.runner import cache

    expected = ref_key(
        BASE["stage_key"], BASE["code"], BASE["lock"], params, seed, BASE["inputs"], BASE["binaries"], BASE["shard"]
    )
    first = call(cache, params=params, seed=seed)
    monkeypatch.chdir(tmp_path_factory.mktemp("elsewhere"))
    for plat in ("win32", "linux", "darwin"):
        monkeypatch.setattr(sys, "platform", plat)
        assert call(cache, params=params, seed=seed) == first == expected
    monkeypatch.setattr(sys, "platform", ORIG_PLATFORM)


# ---- P-002-02: single-component sensitivity ---------------------------------------------------------------------------
def flip(h: str, pos: int) -> str:
    c = HEX[(HEX.index(h[pos]) + 1) % 16]
    return h[:pos] + c + h[pos + 1 :]


MUTATIONS = {
    "param-value": lambda b: {"params": {**b["params"], "solver": "mpm"}},
    "param-nested-value": lambda b: {"params": {**b["params"], "counts": {"particles": 20001}}},
    "param-added": lambda b: {"params": {**b["params"], "extra": 0}},
    "param-removed": lambda b: {"params": {k: v for k, v in b["params"].items() if k != "none"}},
    "code": lambda b: {"code": flip(b["code"], 17)},
    "lock": lambda b: {"lock": flip(b["lock"], 63)},
    "seed": lambda b: {"seed": b["seed"] ^ 1},
    "input-digest": lambda b: {
        "inputs": {**b["inputs"], "example-haul-network": flip(b["inputs"]["example-haul-network"], 0)}
    },
    "input-added": lambda b: {"inputs": {**b["inputs"], "another": "d" * 64}},
    "binary-digest": lambda b: {"binaries": {"ffmpeg": flip(b["binaries"]["ffmpeg"], 31)}},
    "shard-index": lambda b: {"shard": {**b["shard"], "index": 2}},
    "shard-size": lambda b: {"shard": {**b["shard"], "size": 999}},
    "shard-total": lambda b: {"shard": {**b["shard"], "total": 20001}},
    "shard-removed": lambda b: {"shard": None},
    "variant": lambda b: {"stage_key": {"id": "st50_physics", "variant": "mpm"}},
    "stage-id": lambda b: {"stage_key": {"id": "st56_encode", "variant": "dem"}},
}


@pytest.mark.req("P-002-02")
def test_p_002_02_every_single_component_change_changes_the_key_and_all_keys_differ() -> None:
    from pitstudio.runner import cache

    base = call(cache)
    keys = {"base": base}
    for name, mut in MUTATIONS.items():
        keys[name] = call(cache, **mut(BASE))
        assert keys[name] != base, f"changing {name} did not change the cache key"
    assert len(set(keys.values())) == len(keys), "two different mutations collided"


@pytest.mark.req("P-002-02")
@settings(max_examples=100, deadline=None)
@given(name=st.sampled_from(sorted(MUTATIONS)), pos=st.integers(0, 63), seed=st.integers(0, 2**62))
def test_p_002_02_sensitivity_holds_for_random_bases(name: str, pos: int, seed: int) -> None:
    from pitstudio.runner import cache

    base = {**BASE, "seed": seed, "code": flip("a" * 64, pos)}
    mutated = {**base, **MUTATIONS[name](base)}
    assert call(cache, **base) != call(cache, **mutated)


def make_tree(root: Path) -> None:
    for rel, text in {
        "studio/src/pitstudio_studio/__init__.py": "x = 1\n",
        "studio/src/pitstudio_studio/stages/a.py": "def run():\n    return 1\n",
        "studio/src/pitstudio_studio/data.json": '{"k": 1}\n',
        "src/pitstudio/runner/stagekit/pitstudio_stagekit.py": "# stagekit\n",
        "pipeline/src/pitstudio_pipeline/__init__.py": "p = 2\n",
        "studio/uv.lock": "version = 1\n",
    }.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode())


def ref_code_digest(root: Path, roots: list[str]) -> str:
    excluded = ("__pycache__", ".venv", ".pytest_cache", "node_modules")
    entries = []
    for r in roots:
        for p in (root / r).rglob("*"):
            rel = p.relative_to(root).as_posix()
            parts = set(rel.split("/"))
            if (
                not p.is_file()
                or parts & set(excluded)
                or any(x.endswith(".egg-info") for x in parts)
                or rel.endswith(".pyc")
            ):
                continue
            entries.append([rel, hashlib.sha256(p.read_bytes()).hexdigest()])
    entries.sort(key=lambda e: e[0])
    return hashlib.sha256(jcs_simple(entries)).hexdigest()


@pytest.mark.req("FR-002-08")
@pytest.mark.req("P-002-02")
def test_fr_002_08_code_and_lock_digests_follow_plan_d7(tmp_path: Path) -> None:
    from pitstudio.runner import cache

    make_tree(tmp_path)
    expected = ref_code_digest(tmp_path, ["studio/src", "src/pitstudio/runner/stagekit"])
    assert cache.code_digest(tmp_path, "studio") == expected
    assert cache.lock_digest(tmp_path, "studio") == hashlib.sha256(b"version = 1\n").hexdigest()
    # kit launches through the studio project but also hashes studio/kit; reason hashes studio/reason; external only studio/src
    (tmp_path / "studio" / "kit").mkdir()
    (tmp_path / "studio" / "kit" / "app.kit").write_bytes(b"kit app\n")
    assert cache.code_digest(tmp_path, "kit") == ref_code_digest(
        tmp_path, ["studio/src", "studio/kit", "src/pitstudio/runner/stagekit"]
    )
    assert cache.code_digest(tmp_path, "external") == expected
    assert cache.code_digest(tmp_path, "pipeline") == ref_code_digest(
        tmp_path, ["pipeline/src", "src/pitstudio/runner/stagekit"]
    )
    assert cache.lock_digest(tmp_path, "kit") == cache.lock_digest(tmp_path, "studio")


@pytest.mark.req("P-002-02")
def test_p_002_02_one_changed_byte_in_one_code_file_or_the_stagekit_or_the_lock_changes_the_digests(
    tmp_path: Path,
) -> None:
    from pitstudio.runner import cache

    make_tree(tmp_path)
    base_code, base_lock = cache.code_digest(tmp_path, "studio"), cache.lock_digest(tmp_path, "studio")
    for rel in (
        "studio/src/pitstudio_studio/stages/a.py",
        "studio/src/pitstudio_studio/data.json",
        "src/pitstudio/runner/stagekit/pitstudio_stagekit.py",
    ):
        p = tmp_path / rel
        orig = p.read_bytes()
        p.write_bytes(orig[:-2] + bytes([orig[-2] ^ 1]) + orig[-1:])
        assert cache.code_digest(tmp_path, "studio") != base_code, rel
        p.write_bytes(orig)
        assert cache.code_digest(tmp_path, "studio") == base_code
    lock = tmp_path / "studio" / "uv.lock"
    lock.write_bytes(b"version = 2\n")
    assert cache.lock_digest(tmp_path, "studio") != base_lock
    assert cache.code_digest(tmp_path, "studio") == base_code, "the lock file is not part of the code digest"


@pytest.mark.req("FR-002-08")
def test_fr_002_08_code_digest_excludes_caches_and_is_independent_of_creation_order(tmp_path: Path) -> None:
    from pitstudio.runner import cache

    make_tree(tmp_path)
    base = cache.code_digest(tmp_path, "studio")
    for rel in (
        "studio/src/pitstudio_studio/__pycache__/a.cpython-314.pyc",
        "studio/src/pitstudio_studio/stages/__pycache__/x.txt",
        "studio/src/.venv/lib/site.py",
        "studio/src/.pytest_cache/v/x",
        "studio/src/pitstudio_studio.egg-info/PKG-INFO",
        "studio/src/node_modules/m/index.js",
        "studio/src/pitstudio_studio/stray.pyc",
    ):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"junk that must not matter")
    assert cache.code_digest(tmp_path, "studio") == base
    other = tmp_path.parent / (tmp_path.name + "-reordered")
    other.mkdir()
    for rel in reversed(
        [
            "studio/src/pitstudio_studio/__init__.py",
            "studio/src/pitstudio_studio/stages/a.py",
            "studio/src/pitstudio_studio/data.json",
            "src/pitstudio/runner/stagekit/pitstudio_stagekit.py",
        ]
    ):
        (other / rel).parent.mkdir(parents=True, exist_ok=True)
        (other / rel).write_bytes((tmp_path / rel).read_bytes())
    assert cache.code_digest(other, "studio") == base, "digest depends on content and relative path only"


# ---- P-002-03: syntax and order invariance (through the plan) ---------------------------------------------------------
SRC_A = "2" * 64
SRC_B = "3" * 64

TEXT_RENDERINGS = {
    "block": f"""id: syntax
case: bench
seed: 7
stages:
  - id: s10_preprocess
    env: pipeline
    tool: pitstudio
    entry: ps_fake_stages.generic
    inputs:
      - {{id: src-a, sha256: "{SRC_A}"}}
      - {{id: src-b, sha256: "{SRC_B}"}}
    params:
      ratio: 4.50
      count: 3
      name: abc
      flags: {{a: true, b: false}}
      files: [out.bin]
      mode: ok
    resources: {{gpu: none, disk_gib_est: 0.001, cpu: 1}}
    determinism: bitwise
    timeout_s: 30
    outputs:
      - {{path: out.bin, schema: file}}
""",
    "flow-reordered-with-comments": f"""# a comment before everything
seed: 7   # trailing comment
case: bench
stages:
- {{outputs: [{{schema: file, path: out.bin}}], timeout_s: 30, determinism: bitwise, resources: {{cpu: 1, disk_gib_est: 0.001, gpu: none}},
   params: {{mode: ok, files: [out.bin], flags: {{b: false, a: true}}, name: abc, count: 3, ratio: 4.5}},
   inputs: [{{sha256: "{SRC_B}", id: src-b}}, {{sha256: "{SRC_A}", id: src-a}}],
   entry: ps_fake_stages.generic, tool: pitstudio, env: pipeline, id: s10_preprocess}}
id: syntax
""",
    "block-spaced": f"""id:   syntax
case:   bench
seed:   7
stages:
-   id: s10_preprocess
    env: pipeline
    tool: pitstudio
    entry: ps_fake_stages.generic
    inputs:
    - sha256: "{SRC_B}"
      id: src-b
    - sha256: "{SRC_A}"
      id: src-a
    params:
        mode: ok
        files:
        - out.bin
        count: 3
        name: abc
        flags:
            b: false
            a: true
        ratio: 4.5000
    resources:
        gpu: none
        cpu: 1
        disk_gib_est: 0.0010
    determinism: bitwise
    timeout_s: 30
    outputs:
    - path: out.bin
      schema: file
""",
}


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


def root_key(world: rw.World, text: str) -> str:
    p = world.repo / "studio" / "recipes" / "cases" / "syntax.yaml"
    p.write_text(text, encoding="utf-8")
    world.recipes["syntax"] = p
    plan = world.plan_json("syntax")
    return plan["stages"][0]["cache_key"]


@pytest.mark.req("P-002-03")
def test_p_002_03_comments_key_order_flow_style_input_order_and_number_spelling_do_not_change_the_key(world) -> None:
    keys = {name: root_key(world, text) for name, text in TEXT_RENDERINGS.items()}
    assert len(set(keys.values())) == 1, keys
    assert keys["block"] is not None and len(keys["block"]) == 64
    changed = TEXT_RENDERINGS["block"].replace("ratio: 4.50", "ratio: 4.6")
    assert root_key(world, changed) != keys["block"], "a real parameter change must change the key"
    changed_src = TEXT_RENDERINGS["block"].replace(SRC_A, "4" * 64)
    assert root_key(world, changed_src) != keys["block"], "a source digest change must change the key"


@st.composite
def param_dicts(draw: st.DrawFn) -> dict[str, Any]:
    scalar = st.one_of(
        st.integers(-1000, 1000), st.text("abcxyz", max_size=6), st.booleans(), st.sampled_from([0.5, 1.25, 2.0, 4.5])
    )
    base = draw(
        st.dictionaries(
            st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True),
            st.one_of(scalar, st.dictionaries(st.from_regex(r"[a-z]{1,5}", fullmatch=True), scalar, max_size=3)),
            min_size=1,
            max_size=5,
        )
    )
    base.pop("mode", None)
    base.pop("files", None)
    return base


@pytest.mark.req("P-002-03")
@settings(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))
@given(
    params=param_dicts(),
    style=st.sampled_from(["block", "flow", "sorted", "json"]),
    swap=st.booleans(),
    comment=st.booleans(),
)
def test_p_002_03_any_rendering_of_one_recipe_gives_the_same_key(
    world, params: dict[str, Any], style: str, swap: bool, comment: bool
) -> None:
    sources = [{"id": "src-a", "sha256": SRC_A}, {"id": "src-b", "sha256": SRC_B}]
    st_doc = stage("s10_preprocess", params=params, inputs=sources)
    doc = recipe("syntax", [st_doc], seed=7)
    ref = root_key(world, yaml.safe_dump(doc, sort_keys=False))
    doc2 = recipe(
        "syntax", [stage("s10_preprocess", params=params, inputs=list(reversed(sources)) if swap else sources)], seed=7
    )
    if style == "block":
        text = yaml.safe_dump(doc2, sort_keys=False)
    elif style == "flow":
        text = yaml.safe_dump(doc2, default_flow_style=True, width=10_000)
    elif style == "sorted":
        text = yaml.safe_dump(doc2, sort_keys=True)
    else:
        text = json.dumps(doc2, indent=2)
    if comment and style != "json":
        text = "# generated rendering\n" + text.replace("\n", "  # c\n", 1)
    assert root_key(world, text) == ref
