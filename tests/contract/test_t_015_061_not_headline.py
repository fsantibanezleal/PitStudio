# ruff: noqa: E501
"""T-015-061: the headline-KPI exclusion check: no metric produced by the Cosmos tool in the headline KPI set.

Requirements: FR-015-42, SC-015-04.

Spec: specs/015-vlm/spec.md FR-015-42 ("No metric produced by the Cosmos tool shall be in the headline KPI set (Explore KPIs and case KPI tiles); a CI check over the
KPI registry and the manifests shall fail otherwise"); SC-015-04 ("Role: never a headline KPI", measured by the FR-015-42 check). The KPI registry is
`studio/cases.yaml` (DC-018-01, spec 018): each case has `kpis` with `id` and `headline: true | false`; the Explore view and the case tiles show the headline ones.

Oracle: the metric names the Cosmos tool produces, read from the metrics contract itself (`contracts/vlm-metrics.schema.json`: the property names of the task-A,
task-B and task-C rows and of the gate), so the test does not depend on the implementation's list; hand-built registries with known offending and permitted KPIs;
the real registry of this repository, which must be clean. The "manifests" half of the CI check is not specified further by the spec (reported as an ambiguity):
this test covers the registry.

Expected API of the implementation (package `pitstudio`, root environment), `pitstudio.reason.guards`:
- `cosmos_metric_ids() -> frozenset[str]`: the ids of the metrics the Cosmos tool produces: at least the property names of the `row_a`, `row_b`, `row_c`, `gate`
  and `bench_path` objects of the metrics contract that carry a measured quantity (see `MEASURED` below).
- `check_not_headline(registry) -> list[Violation]`: for every case of the registry and every KPI with `headline: true` whose `id` is a Cosmos metric id, or
  begins with `cosmos_` or `vlm_`, one `Violation(path="<case>:<kpi id>", rule="cosmos-metric-is-headline")`. KPIs with `headline: false` are allowed. ValueError for a
  registry without a `cases` mapping or a case whose `kpis` is not a list or a KPI without `id`.
- `check_registry_file(path) -> list[Violation]`: loads the YAML registry and applies `check_not_headline`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pitstudio.reason import guards

ROOT = Path(__file__).resolve().parents[2]
MEASURED = {
    "balanced_accuracy",
    "f1",
    "auroc",
    "unparseable_rate",
    "error_rate",
    "accuracy",
    "position_bias",
    "single_clip_auroc",
    "detection_rate",
    "chair_i",
    "chair_s",
    "recall",
    "no_object_rate",
    "condition_ba",
    "agreement",
    "vram_peak_bytes",
    "prefill_tokens_per_s",
    "decode_tokens_per_s",
    "wall_s_per_query",
}


def _kpi(kid: str, headline: bool) -> dict:
    return {
        "id": kid,
        "name": {"en": kid, "es": kid},
        "unit": "1",
        "orientation": "higher-is-better",
        "headline": headline,
    }


def _registry(**cases: list[dict]) -> dict:
    return {"schema_version": "1.0", "cases": {c: {"category": "B", "kpis": k} for c, k in cases.items()}}


@pytest.mark.req("FR-015-42")
def test_the_cosmos_metric_ids_cover_every_measured_quantity_of_the_metrics_contract() -> None:
    schema = json.loads((ROOT / "contracts" / "vlm-metrics.schema.json").read_text(encoding="utf-8"))
    defs = schema["$defs"]
    present: set[str] = set()
    for name in ("row_a", "row_b", "row_c", "gate", "bench_path"):
        present |= set(defs[name]["properties"])
    expected = MEASURED & present
    assert {"balanced_accuracy", "chair_i", "agreement", "accuracy", "recall"} <= expected  # the oracle itself is sane
    ids = guards.cosmos_metric_ids()
    assert isinstance(ids, frozenset)
    assert expected <= ids, sorted(expected - ids)


@pytest.mark.req("FR-015-42")
@pytest.mark.parametrize(
    "kid", [*sorted(MEASURED), "cosmos_balanced_accuracy", "cosmos_q8_0_f1", "vlm_agreement", "vlm_anything"]
)
def test_a_cosmos_metric_as_a_headline_kpi_fails_the_check_naming_case_and_kpi(kid: str) -> None:
    vs = guards.check_not_headline(_registry(B1=[_kpi("min_ttc", True), _kpi(kid, True)]))
    assert [(v.path, v.rule) for v in vs] == [(f"B1:{kid}", "cosmos-metric-is-headline")]


@pytest.mark.req("FR-015-42")
def test_the_same_metrics_are_allowed_as_non_headline_kpis() -> None:
    reg = _registry(
        B1=[_kpi("min_ttc", True), _kpi("cosmos_balanced_accuracy", False), _kpi("chair_i", False)],
        B2=[_kpi("map50_synthetic", True)],
    )
    assert guards.check_not_headline(reg) == []


@pytest.mark.req("FR-015-42")
def test_every_offending_kpi_of_every_case_is_reported_in_registry_order() -> None:
    reg = _registry(
        B1=[_kpi("cosmos_f1", True), _kpi("near_misses", True)],
        B2=[_kpi("chair_s", True), _kpi("map50_synthetic", True), _kpi("vlm_x", True)],
        A1=[_kpi("tph", True)],
    )
    assert [v.path for v in guards.check_not_headline(reg)] == ["B1:cosmos_f1", "B2:chair_s", "B2:vlm_x"]


@pytest.mark.req("FR-015-42")
@pytest.mark.parametrize(
    "kid", ["min_ttc", "near_misses", "map50_synthetic", "crusher_oversize", "tonnes_per_hour", "queue_length"]
)
def test_ordinary_kpis_whose_names_only_resemble_cosmos_metrics_are_not_flagged(kid: str) -> None:
    assert guards.check_not_headline(_registry(B1=[_kpi(kid, True)])) == []


@pytest.mark.req("FR-015-42")
@pytest.mark.parametrize(
    "registry",
    [
        pytest.param({}, id="no-cases"),
        pytest.param({"cases": []}, id="cases-not-a-mapping"),
        pytest.param({"cases": {"B1": {"kpis": "min_ttc"}}}, id="kpis-not-a-list"),
        pytest.param({"cases": {"B1": {"kpis": [{"headline": True}]}}}, id="kpi-without-id"),
        pytest.param({"cases": {"B1": {"kpis": [None]}}}, id="kpi-not-a-mapping"),
        pytest.param(None, id="registry-none"),
    ],
)
def test_a_malformed_registry_is_refused(registry: object) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        guards.check_not_headline(registry)  # type: ignore[arg-type]


@pytest.mark.req("SC-015-04")
def test_the_real_case_registry_has_no_cosmos_metric_among_its_headline_kpis() -> None:
    assert guards.check_registry_file(ROOT / "studio" / "cases.yaml") == []


@pytest.mark.req("SC-015-04")
def test_a_copy_of_the_real_registry_with_a_cosmos_headline_kpi_is_caught(tmp_path: Path) -> None:
    import yaml

    reg = yaml.safe_load((ROOT / "studio" / "cases.yaml").read_text(encoding="utf-8"))
    reg["cases"]["B1"]["kpis"].append(_kpi("cosmos_balanced_accuracy", True))
    p = tmp_path / "cases.yaml"
    p.write_text(yaml.safe_dump(reg, allow_unicode=True), encoding="utf-8")
    vs = guards.check_registry_file(p)
    assert [v.path for v in vs] == ["B1:cosmos_balanced_accuracy"]
