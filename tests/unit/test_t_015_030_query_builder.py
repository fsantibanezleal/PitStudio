# ruff: noqa: E501, PT018
"""T-015-030: task-A query builder: balance, one query per (frame, type), condition shares, fixed seed.

Requirements: FR-015-16 (and the gate and reasoning subset flags of DC-015-02 that FR-015-14 and FR-015-24 rely on).

Spec: specs/015-vlm/spec.md FR-015-16 ("1,080 queries per type (6,480 in total), at most one per (frame, type); types 1, 2,
4, 5 and 6 with exactly 540 yes and 540 no; type 3 with exactly 270 per class {0, 1, 2, >= 3}; every condition with >= 20 %
of the queries of each type; with a fixed seed"); FR-015-14 (gate subset: 500 binary queries, 100 per binary type, 50 yes and
50 no, conditions stratified); FR-015-24 (a stratified 300-query reasoning-on subset); DC-015-02
(`contracts/vlm-queries.schema.json`, `gate_subset` is never true for type 3).

Oracle: counting on a synthetic frame pool whose ground truth is a closed-form function of the frame index (so the expected
counts are known by construction, plan.md test strategy "counting on a synthetic frame pool"); the arithmetic 6 x 1,080 =
6,480, 1,080 / 2 = 540, 1,080 / 4 = 270, 20 % of 1,080 = 216; the JSON Schema of the contract (reference implementation
`jsonschema`).

Expected API of the implementation (package `pitstudio`, root environment):
- `pitstudio.reason.queries.build_queries(frames, *, root, seed, per_type=1080, subsets=True, truth_fn=None) -> QueryBuild` (see
  test_t_015_033_frame_state_hostile.py for the shared contract; `subsets=False` leaves the subset flags False and is used with a small
  `per_type`); `truth_fn(frame, qtype) -> label | None` replaces the
  module's own ground truth (None = not askable); frames whose `case` is not "B2" are never drawn.
- `QueryBuild.queries`: list of dicts with the DC-015-02 fields (`query_id`, `frame_id`, `frame_state_sha256` = SHA-256 of
  the canonical JSON of the frame state, `type`, `condition`, `location`, `truth`, `gate_subset`, `reasoning_subset`);
  `QueryBuild.to_document() -> dict` is the whole query set (`schema_version` "1.0", `seed`, `source_run_id`, `queries`).
- The query order is deterministic for a seed; two runs with the same inputs give equal documents.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import _p015_contracts as contracts
import _p015_kit as kit
import pytest
from pitstudio.reason.queries import build_queries

CONDS = ["day", "night", "dust", "rain"]
LOCS = ["haul_road", "bench", "loading_area"]
N_FRAMES = 5000
PER_TYPE = 1080


def _idx(frame: dict) -> int:
    return int(frame["frame_id"].split("-f")[1])


def truth_fn(frame: dict, qtype: int) -> str | None:
    """Closed-form truth by construction: unaskable when (i + t) % 11 == 0; yes on even (i // 4 + t); type 3 cycles 0..3+."""
    i = _idx(frame)
    if (i + qtype) % 11 == 0:
        return None
    q = i // 4 + qtype
    if qtype == 3:
        return ["0", "1", "2", "3+"][q % 4]
    return "yes" if q % 2 == 0 else "no"


def _frames(n: int = N_FRAMES) -> list[dict]:
    return [
        kit.frame_state(
            [kit.truck(100.0, 0.0), kit.person(110.0, 5.0)],
            frame_id=f"b2-pit-s{i // 100:04d}-f{i:05d}",
            condition=CONDS[i % 4],
            location=LOCS[i % 3],
        )
        for i in range(n)
    ]


_STATE: dict = {}


@pytest.fixture(scope="module", autouse=True)
def _root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    r = tmp_path_factory.mktemp("p015_030")
    kit.write_frame_files(r)
    _STATE["root"] = r
    _STATE["builds"] = {}
    _STATE["frames"] = (
        _frames()
    )  # built once: the prim ids of the kit objects come from a counter, so a second build would differ
    return r


def _build(seed: int):
    if seed not in _STATE["builds"]:
        _STATE["builds"][seed] = build_queries(
            _STATE["frames"], root=_STATE["root"], seed=seed, per_type=PER_TYPE, truth_fn=truth_fn
        )
    return _STATE["builds"][seed]


def _by_type(res) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {t: [] for t in range(1, 7)}
    for q in res.queries:
        out[q["type"]].append(q)
    return out


@pytest.mark.req("FR-015-16")
def test_there_are_1080_queries_per_type_and_6480_in_total() -> None:
    res = _build(7)
    assert len(res.queries) == 6 * 1080 == 6480
    assert {t: len(v) for t, v in _by_type(res).items()} == dict.fromkeys(range(1, 7), 1080)


@pytest.mark.req("FR-015-16")
@pytest.mark.parametrize("qtype", [1, 2, 4, 5, 6])
def test_binary_types_have_exactly_540_yes_and_540_no(qtype: int) -> None:
    c = Counter(q["truth"] for q in _by_type(_build(7))[qtype])
    assert c == {"yes": 540, "no": 540}


@pytest.mark.req("FR-015-16")
def test_type_3_has_exactly_270_per_class() -> None:
    c = Counter(q["truth"] for q in _by_type(_build(7))[3])
    assert c == {"0": 270, "1": 270, "2": 270, "3+": 270}


@pytest.mark.req("FR-015-16")
@pytest.mark.parametrize("qtype", range(1, 7))
def test_every_condition_holds_at_least_20_percent_of_each_type(qtype: int) -> None:
    c = Counter(q["condition"] for q in _by_type(_build(7))[qtype])
    assert set(c) == set(CONDS)
    assert all(v >= 0.2 * 1080 for v in c.values()), c  # 0.2 * 1080 = 216


@pytest.mark.req("FR-015-16")
def test_at_most_one_query_per_frame_and_type_and_ids_are_unique() -> None:
    res = _build(7)
    pairs = Counter((q["frame_id"], q["type"]) for q in res.queries)
    assert max(pairs.values()) == 1
    assert len({q["query_id"] for q in res.queries}) == len(res.queries)


@pytest.mark.req("FR-015-16")
def test_every_query_carries_the_exact_truth_and_the_frame_attributes_and_never_a_not_askable_frame() -> None:
    frames = {f["frame_id"]: f for f in _STATE["frames"]}
    for q in _build(7).queries:
        f = frames[q["frame_id"]]
        assert truth_fn(f, q["type"]) == q["truth"]  # not None: an unaskable frame is never used
        assert (q["condition"], q["location"]) == (f["condition"], f["location"])
        assert q["frame_state_sha256"] == kit.canonical_sha256(f)


@pytest.mark.req("FR-015-16")
def test_the_same_seed_gives_the_same_query_set_and_another_seed_a_different_one() -> None:
    a, c = _build(7), _build(8)
    b = build_queries(
        list(_STATE["frames"]), root=_STATE["root"], seed=7, per_type=PER_TYPE, truth_fn=truth_fn
    )  # a second, independent run
    assert a.to_document() == b.to_document()
    assert a.to_document()["seed"] == 7
    assert {q["query_id"] for q in a.queries} != {q["query_id"] for q in c.queries} or [
        q["frame_id"] for q in a.queries
    ] != [q["frame_id"] for q in c.queries]
    # the balance holds for every seed
    assert Counter(q["truth"] for q in _by_type(c)[1]) == {"yes": 540, "no": 540}


@pytest.mark.req("FR-015-16")
def test_the_query_set_document_satisfies_the_contract_schema() -> None:
    assert contracts.errors(_build(7).to_document(), "vlm-queries.schema.json") == []


@pytest.mark.req("FR-015-16")
def test_only_frames_of_the_b2_scenes_are_drawn() -> None:
    frames = _frames(400)
    other = _frames(400)
    for i, f in enumerate(other):
        f["case"] = "A1"
        f["frame_id"] = f"a1-pit-s0001-f{i + 90000:05d}"
    res = build_queries([*frames, *other], root=_STATE["root"], seed=3, per_type=4, subsets=False, truth_fn=truth_fn)
    assert res.queries
    assert all(q["frame_id"].startswith("b2-") for q in res.queries)


@pytest.mark.req("FR-015-16")
def test_the_gate_subset_is_500_binary_queries_100_per_type_with_50_yes_and_50_no() -> None:
    gate = [q for q in _build(7).queries if q["gate_subset"]]
    assert len(gate) == 500
    assert all(q["type"] != 3 for q in gate)
    for t in (1, 2, 4, 5, 6):
        sub = [q for q in gate if q["type"] == t]
        assert Counter(q["truth"] for q in sub) == {"yes": 50, "no": 50}
        cond = Counter(q["condition"] for q in sub)
        assert set(cond) == set(CONDS) and min(cond.values()) >= 20, cond  # conditions stratified (>= 20 % of the 100)


@pytest.mark.req("FR-015-16")
def test_the_reasoning_subset_is_300_queries_with_50_per_type() -> None:
    sub = [q for q in _build(7).queries if q["reasoning_subset"]]
    assert len(sub) == 300
    assert Counter(q["type"] for q in sub) == dict.fromkeys(range(1, 7), 50)
