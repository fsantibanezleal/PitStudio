# ruff: noqa: E501
"""T-009-050 (unit half) - FR-009-31, P-009-11, SC-009-04: paired cluster-bootstrap DR ablation and its verdict.

Oracles (independent of the code under test):
- analytical (plan 009 test strategy row FR-009-31): a constant per-seed difference d gives the interval [d, d] (every resample has the difference d), and the verdict mapping of
  FR-000-05 typed out: "better" iff lower > 0, "worse" iff upper < 0, otherwise "no significant difference" (an interval that touches 0 is not significant);
- P-009-11 (spec 009 section 4): swapping the arms negates both bounds (same resample indices) and swaps better / worse; relisting the scenario seeds in any order leaves the interval
  unchanged; identical arms give [0, 0] and "no significant difference" (atol 1e-12);
- "identical resample indices for both arms" (FR-009-31): the two statistic callables record every resample they receive; the recorded sequences must be equal element by element;
- central-limit analytical check: for 100 clusters whose per-cluster difference is x_c, the percentile bootstrap interval of the mean difference has half-width close to
  1.96 s / sqrt(n) (s = population standard deviation of the x_c): within 15 % at B = 4,000 (the standard error of a bootstrap percentile is a few percent);
- the fraction fixture of `_p009_s50_kit` through `run_s50_evaluate`: D-FINE-S arm S detects every pit image (AP 1.0 per class), arm U detects the images of the even clusters only
  (10 of 20 clusters: recall 0.5, grid points 0.00 .. 0.50 = 51 / 101 per class), so d = 1 - 51/101 = 50/101 = 0.49505, verdict "better"; exchanging the arms gives -50/101 and "worse";
  identical arms give 0 and "no significant difference".

Expected public API (package `pitstudio_pipeline.perception`, under `pipeline/src/`):

module `ablation`
    verdict_of(lower: float, upper: float) -> str          "better" | "worse" | "no significant difference" (ValueError for NaN, or lower > upper)
    PairedResult                     frozen dataclass: difference: float, lower: float, upper: float, verdict: str, resamples: int, level: float,
                                     seed: int, bootstrap_record: dict (the `bootstrap` block of #/$defs/dr_ablation: {"resamples", "method": "paired-cluster-percentile",
                                     "cluster": "test-scenario-seed", "level", "identical_resample_indices": True, "seed"})
    paired_cluster_bootstrap(clusters: Sequence[int], stat_a: Callable[[Sequence[int]], float], stat_b: Callable[[Sequence[int]], float], *, resamples: int = 10000,
                             level: float = 0.95, seed: int) -> PairedResult
        `clusters` are the test scenario seeds (distinct ints, at least 2; they are sorted internally, so their listing order never matters). The point difference is
        stat_a(sorted clusters) - stat_b(sorted clusters). For each of `resamples` draws the cluster list is resampled with replacement (numpy default_rng(seed).integers over the
        sorted list, size n per draw) and BOTH statistics are called with the same resampled list (a list of cluster ids with multiplicity); the interval is the percentile interval
        [(1 - level) / 2, (1 + level) / 2] of stat_a(resample) - stat_b(resample); the verdict is verdict_of(lower, upper). Deterministic for a given seed.
        ValueError (message names the argument) for fewer than 2 or duplicated clusters ("clusters"), resamples < 1 or non-int ("resamples"), level outside (0, 1) ("level"),
        non-int seed ("seed"), non-callable statistics ("stat_a" / "stat_b"), a statistic returning a non-finite value ("stat").

module `s50_evaluate` (additions to tests/unit/test_t_009_033_support_determinism.py)
    run_s50_evaluate(spec) accepts spec["bootstrap"]["ablation_resamples"] (default 10000) and, when predictions for model "d-fine-s", precision "fp32" with BOTH arms "S" and "U" are given,
    sets result.report["dr_ablation"] = {"model": "d-fine-s", "precision": "fp32", "metric": "map50", "family": "pit", "arm_a": "S", "arm_b": "U", "difference": mAP50(S) - mAP50(U) on the pit
    family, "interval": {"lower", "upper"}, "bootstrap": bootstrap_record, "verdict", "training_runs_per_arm": 1, "test_seeds": number of pit clusters, "test_images": number of pit images},
    where the statistic is the pooled mAP50 (classes with >= min_support instances) of the resampled pit images, evaluated per arm on the SAME resample. Arms that do not list the
    same `image_ids` raise PredictionError("arms-mismatch") before any metric.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_s50_kit as k50  # noqa: E402
from pitstudio_pipeline.perception import ablation, evaluate, s50_evaluate  # noqa: E402

EXAMPLES = 100


def _mean_stat(values: dict[int, float]):
    return lambda clusters: float(np.mean([values[c] for c in clusters]))


# ---------------------------------------------------------------- verdict mapping


@pytest.mark.req("FR-009-31")
@pytest.mark.parametrize(
    ("lower", "upper", "verdict"),
    [
        (0.01, 0.05, "better"),
        (1e-12, 0.5, "better"),
        (-0.05, -0.01, "worse"),
        (-0.5, -1e-12, "worse"),
        (-0.01, 0.02, "no significant difference"),
        (0.0, 0.03, "no significant difference"),  # touching 0 is not significant
        (-0.03, 0.0, "no significant difference"),
        (0.0, 0.0, "no significant difference"),
    ],
)
def test_the_verdict_mapping_of_the_decision_rule(lower: float, upper: float, verdict: str) -> None:
    assert ablation.verdict_of(lower, upper) == verdict


@pytest.mark.req("FR-009-31")
@pytest.mark.parametrize(
    ("lower", "upper"), [(float("nan"), 0.1), (0.1, float("nan")), (0.2, 0.1), (float("inf"), float("inf"))]
)
def test_a_malformed_interval_has_no_verdict(lower: float, upper: float) -> None:
    with pytest.raises(ValueError, match=r"lower|upper|interval"):
        ablation.verdict_of(lower, upper)


# ---------------------------------------------------------------- the paired bootstrap


CLUSTERS = list(range(1000, 1030))


@pytest.mark.req("FR-009-31")
@pytest.mark.parametrize(("d", "verdict"), [(0.031, "better"), (-0.02, "worse"), (0.0, "no significant difference")])
def test_a_constant_per_seed_difference_gives_the_degenerate_interval(d: float, verdict: str) -> None:
    base = {c: 0.5 + 0.01 * (c % 7) for c in CLUSTERS}
    other = {c: v + d for c, v in base.items()}
    res = ablation.paired_cluster_bootstrap(CLUSTERS, _mean_stat(other), _mean_stat(base), resamples=300, seed=1)
    assert res.difference == pytest.approx(d, abs=1e-12)
    assert res.lower == pytest.approx(d, abs=1e-12)
    assert res.upper == pytest.approx(d, abs=1e-12)
    assert res.verdict == verdict


@pytest.mark.req("FR-009-31")
def test_both_arms_see_exactly_the_same_resamples() -> None:
    seen_a: list[tuple[int, ...]] = []
    seen_b: list[tuple[int, ...]] = []

    def a(clusters):
        seen_a.append(tuple(clusters))
        return float(len(set(clusters)))

    def b(clusters):
        seen_b.append(tuple(clusters))
        return 0.0

    ablation.paired_cluster_bootstrap(CLUSTERS, a, b, resamples=50, seed=3)
    assert len(seen_a) == len(seen_b) == 51  # the point estimate plus 50 resamples
    assert seen_a == seen_b
    assert seen_a[0] == tuple(sorted(CLUSTERS))  # the point estimate uses the sorted cluster list
    for r in seen_a[1:]:
        assert len(r) == len(CLUSTERS)  # resampled with replacement, same size
        assert set(r) <= set(CLUSTERS)
    assert any(len(set(r)) < len(CLUSTERS) for r in seen_a[1:])  # with replacement: repeats occur


@pytest.mark.req("FR-009-31")
def test_the_result_is_deterministic_for_a_seed_and_records_the_bootstrap_block() -> None:
    rng = np.random.default_rng(2)
    a = {c: float(rng.random()) for c in CLUSTERS}
    b = {c: float(rng.random()) for c in CLUSTERS}
    r1 = ablation.paired_cluster_bootstrap(CLUSTERS, _mean_stat(a), _mean_stat(b), resamples=200, seed=11)
    r2 = ablation.paired_cluster_bootstrap(CLUSTERS, _mean_stat(a), _mean_stat(b), resamples=200, seed=11)
    assert r1 == r2
    assert r1.bootstrap_record == {
        "resamples": 200,
        "method": "paired-cluster-percentile",
        "cluster": "test-scenario-seed",
        "level": 0.95,
        "identical_resample_indices": True,
        "seed": 11,
    }
    assert (r1.resamples, r1.level, r1.seed) == (200, 0.95, 11)
    default = ablation.paired_cluster_bootstrap(CLUSTERS, _mean_stat(a), _mean_stat(b), resamples=7, seed=1)
    assert default.bootstrap_record["resamples"] == 7


@pytest.mark.req("FR-009-31")
def test_the_default_number_of_resamples_is_ten_thousand() -> None:
    calls = []

    def stat(clusters):
        calls.append(1)
        return 0.0

    ablation.paired_cluster_bootstrap(CLUSTERS, stat, stat, seed=1)
    assert len(calls) == 2 * (10_000 + 1)


@pytest.mark.req("FR-009-31")
def test_the_interval_of_a_mean_difference_matches_the_central_limit_half_width() -> None:
    rng = np.random.default_rng(20261007)
    n = 100
    clusters = list(range(n))
    x = rng.normal(0.05, 0.1, size=n)
    stat_a = lambda cl: float(np.mean([x[c] for c in cl]))  # noqa: E731
    res = ablation.paired_cluster_bootstrap(clusters, stat_a, lambda cl: 0.0, resamples=4000, seed=5)
    half = 1.96 * float(x.std()) / np.sqrt(n)
    assert res.difference == pytest.approx(float(x.mean()), abs=1e-12)
    assert (res.upper - res.lower) / 2.0 == pytest.approx(half, rel=0.15)
    assert res.lower < res.difference < res.upper
    assert (res.lower + res.upper) / 2.0 == pytest.approx(float(x.mean()), abs=0.25 * half)


@pytest.mark.req("P-009-11")
@given(
    n=st.integers(10, 200),
    per=st.integers(1, 20),
    seed=st.integers(0, 2**32 - 1),
    shuffle_seed=st.integers(0, 2**32 - 1),
)
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_swapping_arms_negates_the_bounds_and_relisting_does_not_change_the_interval(
    n: int, per: int, seed: int, shuffle_seed: int
) -> None:
    rng = np.random.default_rng(seed)
    clusters = [int(c) for c in rng.choice(10**6, size=n, replace=False)]
    a = {c: float(rng.random(per).mean()) for c in clusters}  # mean of `per` per-image results of a seed
    b = {c: float(rng.random(per).mean()) for c in clusters}
    sa, sb = _mean_stat(a), _mean_stat(b)
    fwd = ablation.paired_cluster_bootstrap(clusters, sa, sb, resamples=60, seed=7)
    rev = ablation.paired_cluster_bootstrap(clusters, sb, sa, resamples=60, seed=7)
    assert rev.lower == pytest.approx(-fwd.upper, abs=1e-12)
    assert rev.upper == pytest.approx(-fwd.lower, abs=1e-12)
    assert rev.difference == pytest.approx(-fwd.difference, abs=1e-12)
    swap = {"better": "worse", "worse": "better", "no significant difference": "no significant difference"}
    assert rev.verdict == swap[fwd.verdict]
    shuffled = list(clusters)
    np.random.default_rng(shuffle_seed).shuffle(shuffled)
    again = ablation.paired_cluster_bootstrap(shuffled, sa, sb, resamples=60, seed=7)
    assert again.lower == pytest.approx(fwd.lower, abs=1e-12)
    assert again.upper == pytest.approx(fwd.upper, abs=1e-12)
    ident = ablation.paired_cluster_bootstrap(clusters, sa, sa, resamples=60, seed=7)
    assert (ident.lower, ident.upper, ident.difference) == (0.0, 0.0, 0.0)
    assert ident.verdict == "no significant difference"


@pytest.mark.req("FR-009-31")
@pytest.mark.parametrize(
    ("kwargs", "arg"),
    [
        ({"clusters": [1]}, "clusters"),
        ({"clusters": []}, "clusters"),
        ({"clusters": [1, 1, 2]}, "clusters"),
        ({"clusters": [1, "2"]}, "clusters"),
        ({"resamples": 0}, "resamples"),
        ({"resamples": 1.5}, "resamples"),
        ({"level": 0.0}, "level"),
        ({"level": 1.0}, "level"),
        ({"level": float("nan")}, "level"),
        ({"seed": "1"}, "seed"),
        ({"seed": True}, "seed"),
        ({"stat_a": None}, "stat_a"),
        ({"stat_b": 3}, "stat_b"),
        ({"stat_a": lambda c: float("nan")}, "stat"),
        ({"stat_b": lambda c: float("inf")}, "stat"),
    ],
)
def test_hostile_bootstrap_arguments_are_rejected_naming_the_argument(kwargs: dict, arg: str) -> None:
    args = {
        "clusters": [1, 2, 3],
        "stat_a": lambda c: 0.5,
        "stat_b": lambda c: 0.4,
        "resamples": 5,
        "level": 0.95,
        "seed": 1,
    } | kwargs
    with pytest.raises(ValueError, match=arg):
        ablation.paired_cluster_bootstrap(args.pop("clusters"), args.pop("stat_a"), args.pop("stat_b"), **args)


# ---------------------------------------------------------------- through s50_evaluate


def _spec(det_s, det_u, gt, family, cluster, *, ids_u=None):
    p_s = k50.prediction("d-fine-s", "fp32", "S", det_s, gt)
    p_u = k50.prediction("d-fine-s", "fp32", "U", det_u, gt)
    if ids_u is not None:
        p_u["image_ids"] = ids_u
    return k50.spec(
        gt, family, cluster, [p_s, p_u], bootstrap={"seed": 90210, "resamples": 6, "ablation_resamples": 40}
    )


def _even_cluster_images(cluster: dict[int, int]) -> set[int]:
    return {i for i, c in cluster.items() if (c - 1000) % 2 == 0}


@pytest.mark.req("FR-009-31")
def test_structured_dr_better_when_arm_u_misses_half_of_the_clusters() -> None:
    gt, family, cluster = k50.fraction_gt(200, 0, images_per_seed=10)  # 20 pit clusters
    all_images = set(range(1, 201))
    s = _spec(
        k50.perfect_detections(gt, all_images),
        k50.perfect_detections(gt, _even_cluster_images(cluster)),
        gt,
        family,
        cluster,
    )
    abl = s50_evaluate.run_s50_evaluate(s).report["dr_ablation"]
    assert (abl["model"], abl["precision"], abl["metric"], abl["family"], abl["arm_a"], abl["arm_b"]) == (
        "d-fine-s",
        "fp32",
        "map50",
        "pit",
        "S",
        "U",
    )
    assert abl["difference"] == pytest.approx(50 / 101, abs=1e-9)
    assert abl["interval"]["lower"] > 0.0
    assert abl["interval"]["lower"] <= abl["interval"]["upper"] <= 1.0
    assert abl["verdict"] == "better"
    assert abl["bootstrap"] == {
        "resamples": 40,
        "method": "paired-cluster-percentile",
        "cluster": "test-scenario-seed",
        "level": 0.95,
        "identical_resample_indices": True,
        "seed": abl["bootstrap"]["seed"],
    }
    assert (abl["training_runs_per_arm"], abl["test_seeds"], abl["test_images"]) == (1, 20, 200)


@pytest.mark.req("FR-009-31")
def test_exchanging_the_arms_gives_worse_and_identical_arms_give_no_significant_difference() -> None:
    gt, family, cluster = k50.fraction_gt(200, 0, images_per_seed=10)
    all_dets = k50.perfect_detections(gt, set(range(1, 201)))
    half_dets = k50.perfect_detections(gt, _even_cluster_images(cluster))
    worse = s50_evaluate.run_s50_evaluate(_spec(half_dets, all_dets, gt, family, cluster)).report["dr_ablation"]
    assert worse["difference"] == pytest.approx(-50 / 101, abs=1e-9)
    assert worse["interval"]["upper"] < 0.0
    assert worse["verdict"] == "worse"
    same = s50_evaluate.run_s50_evaluate(_spec(all_dets, copy.deepcopy(all_dets), gt, family, cluster)).report[
        "dr_ablation"
    ]
    assert same["difference"] == pytest.approx(0.0, abs=1e-12)
    assert same["interval"]["lower"] == pytest.approx(0.0, abs=1e-12)
    assert same["interval"]["upper"] == pytest.approx(0.0, abs=1e-12)
    assert same["verdict"] == "no significant difference"


@pytest.mark.req("FR-009-31")
def test_arms_listing_different_test_images_are_rejected_before_any_metric() -> None:
    gt, family, cluster = k50.fraction_gt(200, 0, images_per_seed=10)
    dets = k50.perfect_detections(gt, set(range(1, 201)))
    s = _spec(dets, copy.deepcopy(dets), gt, family, cluster, ids_u=list(range(1, 198)))
    with pytest.raises(evaluate.PredictionError) as exc:
        s50_evaluate.run_s50_evaluate(s)
    assert exc.value.code == "arms-mismatch"


@pytest.mark.req("FR-009-31")
def test_the_ablation_block_validates_against_the_dr_ablation_definition_apart_from_the_test_resample_count() -> None:
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "contracts" / "detection-eval.schema.json").read_text(encoding="utf-8"))
    gt, family, cluster = k50.fraction_gt(200, 0, images_per_seed=10)
    s = _spec(
        k50.perfect_detections(gt, set(range(1, 201))),
        k50.perfect_detections(gt, _even_cluster_images(cluster)),
        gt,
        family,
        cluster,
    )
    abl = s50_evaluate.run_s50_evaluate(s).report["dr_ablation"]
    errors = list(Draft202012Validator({"$ref": "#/$defs/dr_ablation", "$defs": schema["$defs"]}).iter_errors(abl))
    assert [
        e.message for e in errors if list(e.absolute_path) != ["bootstrap", "resamples"]
    ] == []  # B = 40 here, 10,000 in the product
