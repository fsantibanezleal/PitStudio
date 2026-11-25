# ruff: noqa: E501
"""T-015-060: published answer records, the stratified sample independent of correctness, the optional real probe with Cohen's kappa, the text budget.

Requirements: FR-015-40, FR-015-45, NFR-015-03.

Spec: specs/015-vlm/spec.md
- FR-015-40: each published record (`contracts/vlm-record.schema.json`) holds the frame asset ids, the question, the full model output, the parsed answer, the
  ground truth, a correct/incorrect flag and its provenance (model id and full revision, quantisation, GGUF SHA-256, llama.cpp build and archive SHA-256, sampling
  parameters and seed, date, GPU and driver); Cosmos records carry licence class `display-only`; the published records are a stratified random sample (by type and
  condition, fixed seed, selection independent of correctness), with the full set kept locally.
- FR-015-45: where the optional real probe exists (<= 200 licence-clean images, two labellers), the applicable task-A types are scored on it and reported in aggregate
  only, with Cohen's kappa between the labellers; otherwise the real-image result reads "not measured".
- NFR-015-03: baked text per case (B1, B2, A3) < 1 MB (CI budget check).
- spec section 8: the record `sample` object (`method` "stratified-random", `strata`, `seed`, `n_full`, `n_published`, `selection_uses_correctness: false`).

Oracle: the record schema (`jsonschema`) and the spec's valid example (`examples/vlm-record.valid.json`) for the provenance shape; selection independence shown by
flipping every correctness flag and requiring the same selection; hand calculation of Cohen's kappa on a 2 x 2 table (40 yes/yes, 40 no/no, 10 yes/no, 10 no/yes:
observed agreement 0.8, expected agreement 0.5 x 0.5 + 0.5 x 0.5 = 0.5, kappa = (0.8 - 0.5) / (1 - 0.5) = 0.6; cross-checked with scikit-learn in
tests/pipeline/test_t_015_060_kappa_parity.py); byte counts of the canonical JSON of generated documents.

Expected API of the implementation (package `pitstudio`, root environment), `pitstudio.reason.records`:
- `sample_records(records, *, seed, per_cell) -> list[dict]`: stratifies task-A records by (`question_type`, `condition`) (any other task by `task`, then `corruption` for
  task B, then `condition` for task C), keeps `min(per_cell, available)` records of each cell chosen uniformly at random with a generator seeded by `seed`, from the
  records' ids and strata only (never their `correct`, `parsed`, `truth` or `output`), and returns them in a stable order (by `record_id`).
- `build_record_document(records, *, case, git_sha, generated, seed, n_full) -> dict`: the `vlm-record` document (notices, `sample`, `records`); ValueError when a Cosmos-arm
  record is not `display-only` or another arm's is not `own`, or when `n_full` is below the number of records.
- `text_bytes(doc) -> int` (UTF-8 bytes of the compact JSON text, sorted keys); `check_text_budget(doc, limit_bytes=1_000_000) -> None` (ValueError when the document is
  not smaller than the limit).
- `cohen_kappa(a, b) -> float`; `real_probe_not_measured() -> dict` (the contract's `real_probe` with status "not_measured", 0 images, kappa None, no rows);
  `real_probe_measured(labels_a, labels_b, rows) -> dict` (status "measured", `n_images` = number of labelled images, `cohen_kappa`, the aggregate `row_a` rows; ValueError for 0
  or more than 200 images, labellers of different length, or a row that is not for a task-A type).
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from pitstudio.reason import records as rec

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))  # the shared kit lives in tests/unit
import _p015_contracts as contracts
import _p015_kit as kit

CONDS = ["day", "night", "dust", "rain"]
GIT = "01e2b86d09a37a1a3d9b5aaaedfc7028fd41e137"


def _prov(quant: str = "q8_0", model: str = "nvidia/Cosmos-Reason2-2B") -> dict:
    ex = json.loads((kit.SPEC015 / "contracts" / "examples" / "vlm-record.valid.json").read_text(encoding="utf-8"))
    p = json.loads(json.dumps(ex["records"][0]["provenance"]))
    if model.startswith("Qwen"):
        p.update({"model": model, "revision": "89644892e4d85e24eaac8bacfd4f463576704203"})
    if quant == "bf16":
        p.update(
            {
                "quantisation": "bf16",
                "gguf_sha256": None,
                "llamacpp_build": None,
                "llamacpp_archive_sha256": None,
                "transformers_version": "5.1.0",
            }
        )
    return p


def _record(i: int, qtype: int, cond: str, *, correct: bool, arm: str = "cosmos-q8_0") -> dict:
    truth = "no" if qtype != 3 else "1"
    parsed = truth if correct else ("yes" if qtype != 3 else "2")
    cosmos = arm.startswith("cosmos")
    return {
        "task": "A",
        "record_id": f"rec-a-{i:05d}",
        "query_id": f"a-q{i:05d}",
        "arm": arm,
        "frames": [f"b2-pit-s0001-f{i:05d}"],
        "question_type": qtype,
        "condition": cond,
        "question": "Is a person within 30 m of a haul truck?" if qtype == 1 else "A hazard question.",
        "output": f"<answer>{parsed}</answer>",
        "parsed": parsed,
        "truth": truth,
        "correct": correct,
        "licence_class": "display-only" if cosmos else "own",
        "provenance": _prov(
            "bf16" if arm == "cosmos-bf16" else "q8_0",
            "Qwen/Qwen3-VL-2B-Instruct" if arm == "qwen-base" else "nvidia/Cosmos-Reason2-2B",
        )
        if cosmos or arm == "qwen-base"
        else None,
    }


def _pool(per_cell: int = 60, *, flip: bool = False) -> list[dict]:
    out = []
    i = 0
    for t in range(1, 7):
        for c in CONDS:
            for k in range(per_cell):
                i += 1
                ok = (k % 2 == 0) != flip  # half of every cell is correct (the other half when flipped)
                out.append(_record(i, t, c, correct=ok))
    return out


def _doc_errors(doc: dict) -> list[str]:
    return [e.message for e in contracts.validator("vlm-record.schema.json").iter_errors(doc)]


# ------------------------------------------------------------------------------------------------ the sample
@pytest.mark.req("FR-015-40")
def test_the_sample_takes_per_cell_records_from_every_type_and_condition_cell() -> None:
    pool = _pool(60)
    out = rec.sample_records(pool, seed=20261015, per_cell=5)
    assert len(out) == 6 * 4 * 5
    cells: dict = {}
    for r in out:
        cells.setdefault((r["question_type"], r["condition"]), []).append(r["record_id"])
    assert {k: len(v) for k, v in cells.items()} == {(t, c): 5 for t in range(1, 7) for c in CONDS}
    assert len({r["record_id"] for r in out}) == len(out)
    assert {r["record_id"] for r in out} <= {r["record_id"] for r in pool}
    assert [r["record_id"] for r in out] == sorted(r["record_id"] for r in out)  # stable order


@pytest.mark.req("FR-015-40")
def test_a_small_cell_is_kept_whole() -> None:
    pool = _pool(3)
    assert len(rec.sample_records(pool, seed=1, per_cell=5)) == len(pool)


@pytest.mark.req("FR-015-40")
def test_the_sample_is_deterministic_for_a_seed_and_differs_between_seeds() -> None:
    pool = _pool(60)
    a = rec.sample_records(pool, seed=7, per_cell=5)
    assert a == rec.sample_records(list(pool), seed=7, per_cell=5)
    assert {r["record_id"] for r in a} != {r["record_id"] for r in rec.sample_records(pool, seed=8, per_cell=5)}
    shuffled = list(pool)
    random.Random(3).shuffle(shuffled)
    assert [r["record_id"] for r in rec.sample_records(shuffled, seed=7, per_cell=5)] == [
        r["record_id"] for r in a
    ]  # the input order does not matter


@pytest.mark.req("FR-015-40")
def test_the_selection_does_not_depend_on_correctness() -> None:
    """Flipping every correctness flag (and the parsed answers with it) leaves the selected record ids unchanged."""
    a = {r["record_id"] for r in rec.sample_records(_pool(60), seed=11, per_cell=7)}
    b = {r["record_id"] for r in rec.sample_records(_pool(60, flip=True), seed=11, per_cell=7)}
    assert a == b
    all_right = [
        {**r, "correct": True, "parsed": r["truth"], "output": f"<answer>{r['truth']}</answer>"} for r in _pool(60)
    ]
    all_wrong = [{**r, "correct": False} for r in _pool(60)]
    assert {r["record_id"] for r in rec.sample_records(all_right, seed=11, per_cell=7)} == a
    assert {r["record_id"] for r in rec.sample_records(all_wrong, seed=11, per_cell=7)} == a


@pytest.mark.req("FR-015-40")
def test_the_sample_keeps_wrong_answers_in_their_population_share() -> None:
    pool = _pool(60)  # half right, half wrong in every cell
    out = rec.sample_records(pool, seed=20261015, per_cell=30)
    wrong = sum(1 for r in out if not r["correct"]) / len(out)
    assert abs(wrong - 0.5) < 0.1  # 720 records: standard deviation 0.019, so 5 sigma
    assert 0 < wrong < 1  # wrong answers are published as well as right ones


@pytest.mark.req("FR-015-40")
@settings(max_examples=40, deadline=None)
@given(st.integers(0, 2**32), st.integers(1, 12))
def test_property_every_seed_gives_the_exact_cell_counts_and_the_same_selection_for_flipped_correctness(
    seed: int, per_cell: int
) -> None:
    a = rec.sample_records(_pool(15), seed=seed, per_cell=per_cell)
    b = rec.sample_records(_pool(15, flip=True), seed=seed, per_cell=per_cell)
    assert [r["record_id"] for r in a] == [r["record_id"] for r in b]
    assert len(a) == 24 * min(per_cell, 15)


@pytest.mark.req("FR-015-40")
@pytest.mark.parametrize("bad", [0, -1, 1.5, None])
def test_a_non_positive_cell_size_is_refused(bad: object) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        rec.sample_records(_pool(3), seed=1, per_cell=bad)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------------------------ the document
@pytest.mark.req("FR-015-40")
def test_the_document_follows_the_record_schema_and_declares_the_sampling() -> None:
    pool = _pool(60)
    sample = rec.sample_records(pool, seed=20261015, per_cell=2)
    doc = rec.build_record_document(
        sample, case="B1", git_sha=GIT, generated="2026-10-15", seed=20261015, n_full=len(pool)
    )
    assert _doc_errors(doc) == []
    assert doc["notices"] == {"cosmos": "Built on NVIDIA Cosmos", "honesty": "Zero-shot 2B VLM; not a safety system."}
    s = doc["sample"]
    assert (s["method"], s["seed"], s["n_full"], s["n_published"], s["selection_uses_correctness"]) == (
        "stratified-random",
        20261015,
        len(pool),
        len(sample),
        False,
    )
    assert doc["records"] == sample
    assert all(r["licence_class"] == "display-only" for r in doc["records"])  # Cosmos records


@pytest.mark.req("FR-015-40")
def test_every_record_carries_its_provenance_and_the_full_output() -> None:
    doc = rec.build_record_document(
        rec.sample_records(_pool(5), seed=1, per_cell=1),
        case="B1",
        git_sha=GIT,
        generated="2026-10-15",
        seed=1,
        n_full=120,
    )
    for r in doc["records"]:
        p = r["provenance"]
        assert p["model"] == "nvidia/Cosmos-Reason2-2B"
        assert p["revision"].startswith("9ce19a1")
        assert len(p["revision"]) == 40
        assert {
            "quantisation",
            "gguf_sha256",
            "llamacpp_build",
            "llamacpp_archive_sha256",
            "sampling",
            "date",
            "gpu",
        } <= set(p)
        assert r["output"].startswith("<answer>")
        assert r["frames"]
        assert r["truth"]
        assert isinstance(r["correct"], bool)


@pytest.mark.req("FR-015-40")
def test_the_non_cosmos_arms_are_own_and_a_wrong_licence_class_is_refused() -> None:
    ok = [
        _record(1, 1, "day", correct=True),
        _record(2, 1, "day", correct=False, arm="constant"),
        _record(3, 1, "night", correct=True, arm="qwen-base"),
    ]
    doc = rec.build_record_document(ok, case="B1", git_sha=GIT, generated="2026-10-15", seed=1, n_full=3)
    assert _doc_errors(doc) == []
    assert {r["arm"]: r["licence_class"] for r in doc["records"]} == {
        "cosmos-q8_0": "display-only",
        "constant": "own",
        "qwen-base": "own",
    }
    for arm, wrong in (
        ("cosmos-q8_0", "own"),
        ("cosmos-bf16", "own"),
        ("qwen-base", "display-only"),
        ("constant", "display-only"),
    ):
        r = {**_record(1, 1, "day", correct=True, arm=arm), "licence_class": wrong}
        with pytest.raises(ValueError):  # noqa: PT011
            rec.build_record_document([r], case="B1", git_sha=GIT, generated="2026-10-15", seed=1, n_full=1)


@pytest.mark.req("FR-015-40")
def test_n_full_cannot_be_smaller_than_the_published_count() -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        rec.build_record_document(_pool(2), case="B1", git_sha=GIT, generated="2026-10-15", seed=1, n_full=3)


@pytest.mark.req("FR-015-40")
def test_the_spec_example_document_has_the_shape_the_builder_produces() -> None:
    ex = json.loads((kit.SPEC015 / "contracts" / "examples" / "vlm-record.valid.json").read_text(encoding="utf-8"))
    assert _doc_errors(ex) == []
    assert set(ex) == set(
        rec.build_record_document(
            [_record(1, 1, "day", correct=True)], case="B1", git_sha=GIT, generated="2026-10-15", seed=1, n_full=1
        )
    )


# ------------------------------------------------------------------------------------------------ the text budget
@pytest.mark.req("NFR-015-03")
def test_the_text_size_is_the_utf8_length_of_the_compact_json() -> None:
    doc = {"a": "é中", "b": [1, 2, 3]}
    assert rec.text_bytes(doc) == len(
        json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )


@pytest.mark.req("NFR-015-03")
def test_a_case_document_under_1_mb_passes_and_one_over_it_fails() -> None:
    small = rec.build_record_document(
        rec.sample_records(_pool(60), seed=1, per_cell=5),
        case="B1",
        git_sha=GIT,
        generated="2026-10-15",
        seed=1,
        n_full=1440,
    )
    assert 0 < rec.text_bytes(small) < 1_000_000
    rec.check_text_budget(small)
    big_records = [{**_record(i, 1 + i % 6, CONDS[i % 4], correct=True), "output": "x" * 30_000} for i in range(60)]
    big = rec.build_record_document(big_records, case="B1", git_sha=GIT, generated="2026-10-15", seed=1, n_full=60)
    assert rec.text_bytes(big) > 1_800_000
    with pytest.raises(ValueError):  # noqa: PT011
        rec.check_text_budget(big)
    rec.check_text_budget(big, limit_bytes=10_000_000)


@pytest.mark.req("NFR-015-03")
@pytest.mark.parametrize("limit", [0, -1, 1.5, None])
def test_a_non_positive_budget_is_refused(limit: object) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        rec.check_text_budget({"a": 1}, limit_bytes=limit)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------------------------ the optional real probe
@pytest.mark.req("FR-015-45")
def test_cohen_kappa_hand_calculation_is_0_6() -> None:
    a = ["yes"] * 40 + ["no"] * 40 + ["yes"] * 10 + ["no"] * 10
    b = ["yes"] * 40 + ["no"] * 40 + ["no"] * 10 + ["yes"] * 10
    assert rec.cohen_kappa(a, b) == pytest.approx(0.6, abs=1e-12)
    assert rec.cohen_kappa(a, a) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.req("FR-015-45")
@settings(max_examples=100, deadline=None)
@given(
    st.lists(
        st.tuples(st.sampled_from(["yes", "no", "3+"]), st.sampled_from(["yes", "no", "3+"])), min_size=2, max_size=200
    )
)
def test_property_cohen_kappa_equals_the_definition(pairs: list) -> None:
    a, b = [x for x, _ in pairs], [y for _, y in pairs]
    pe = sum((a.count(c) / len(a)) * (b.count(c) / len(b)) for c in {"yes", "no", "3+"})
    if abs(1 - pe) < 1e-12:
        return  # kappa is undefined when both labellers always use one category
    assert rec.cohen_kappa(a, b) == pytest.approx(kit.cohen_kappa(a, b), abs=1e-12)


@pytest.mark.req("FR-015-45")
@pytest.mark.parametrize("a_b", [([], []), (["yes"], ["yes", "no"]), (["yes", "no"], ["yes"])])
def test_kappa_refuses_empty_or_unequal_labellings(a_b: tuple) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        rec.cohen_kappa(*a_b)


def _probe_error(obj: dict) -> list[str]:
    base = contracts.validator("vlm-metrics.schema.json").schema["$id"]
    return [
        e.message
        for e in Draft202012Validator(
            {"$ref": base + "#/$defs/real_probe"}, registry=contracts._registry()
        ).iter_errors(obj)
    ]


@pytest.mark.req("FR-015-45")
def test_without_the_probe_the_real_image_result_reads_not_measured() -> None:
    p = rec.real_probe_not_measured()
    assert p == {"status": "not_measured", "n_images": 0, "cohen_kappa": None, "rows": []}
    assert _probe_error(p) == []


def _row(arm: str, qtype: int) -> dict:
    est = {"value": 0.7, "lo": 0.6, "hi": 0.8}
    return {
        "arm": arm,
        "reasoning": False,
        "type": qtype,
        "status": "measured",
        "n": 120,
        "balanced_accuracy": est,
        "f1": est,
        "unparseable_rate": 0.0,
        "error_rate": 0.0,
        "auroc": None,
        "by_condition": [],
    }


@pytest.mark.req("FR-015-45")
def test_with_the_probe_the_result_is_aggregate_only_with_the_kappa_between_the_labellers() -> None:
    a = ["yes"] * 40 + ["no"] * 40 + ["yes"] * 10 + ["no"] * 10
    b = ["yes"] * 40 + ["no"] * 40 + ["no"] * 10 + ["yes"] * 10
    p = rec.real_probe_measured(a, b, [_row("cosmos-q8_0", 1), _row("qwen-base", 1)])
    assert (p["status"], p["n_images"]) == ("measured", 100)
    assert p["cohen_kappa"] == pytest.approx(0.6, abs=1e-12)
    assert set(p) == {"status", "n_images", "cohen_kappa", "rows"}  # no per-image content
    assert [r["arm"] for r in p["rows"]] == ["cosmos-q8_0", "qwen-base"]
    assert _probe_error(p) == []


@pytest.mark.req("FR-015-45")
@pytest.mark.parametrize("n", [0, 201, 1000])
def test_the_probe_holds_between_1_and_200_images(n: int) -> None:
    labels = ["yes", "no"] * (n // 2) + ["yes"] * (n % 2)
    with pytest.raises(ValueError):  # noqa: PT011
        rec.real_probe_measured(labels, labels, [])


@pytest.mark.req("FR-015-45")
def test_a_probe_of_200_images_is_accepted_and_a_mismatched_labelling_is_refused() -> None:
    a = ["yes", "no"] * 100
    b = ["yes", "yes", "no", "no"] * 50
    assert rec.real_probe_measured(a, b, [])["n_images"] == 200
    with pytest.raises(ValueError):  # noqa: PT011
        rec.real_probe_measured(a, b[:-1], [])
    bad_row = {**_row("cosmos-q8_0", 1), "type": 9}
    with pytest.raises(ValueError):  # noqa: PT011
        rec.real_probe_measured(a, b, [bad_row])
