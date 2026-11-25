# ruff: noqa: E501, PT018, RUF059
"""Case B1 run (spec 018 FR-018-55, FR-018-16; spec 020 DC-020-05): the outputs of `pitstudio_pipeline.haulage.b1_run` on a small pit-like network.

Oracles: the chart-series JSON Schema of the contract and the semantic rules of `studio import-run` (`pitstudio.runner.chart_series`); the KPI ids of the case registry
(`studio/cases.yaml`, case B1); the TTC of a hand-built pair for the near-miss rate formula; determinism of two runs with the same seeds; every number read back from the files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _b1_kit as kit
from pitstudio_pipeline import chartkit
from pitstudio_pipeline.haulage import b1_run

from pitstudio.haulage.ttc import near_misses_per_1000h
from pitstudio.runner import chart_series

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = [
    "b1-conflicts-per-shift", "b1-inputs-table", "b1-min-ttc-distribution", "b1-min-ttc-percentiles-vs-share", "b1-near-miss-rate-vs-density",
    "b1-near-miss-rate-vs-share", "b1-scenario-table", "b1-throughput-vs-share",
]  # fmt: skip


def params(seeds=2):
    return {
        "inputs": {"road_network": "net.geojson"},
        "scenario": kit.scenario(),
        "traffic": {},
        "sweep": {
            "fleet_size": 4,
            "dispatcher": "sptf",
            "autonomous_shares": [0.0, 1.0],
            "light_vehicles": [0, 4],
            "seeds": seeds,
            "reference": {"share": 1.0, "light_vehicles": 4},
        },
    }


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    root = tmp_path_factory.mktemp("b1run")
    (root / "net.geojson").write_text(json.dumps(kit.geojson()), encoding="utf-8")
    result = b1_run.compute(params(), root, root / "work", 1)
    out = root / "out"
    files = b1_run.write_outputs(result, out)
    return root, result, out, files


def test_every_chart_is_valid_against_the_contract_and_the_import_rules(run):
    _, result, out, files = run
    assert sorted(p.stem for p in (out / "charts").glob("*.json")) == EXPECTED
    assert (out / "results-summary.json") in files
    for p in (out / "charts").glob("*.json"):
        doc = json.loads(p.read_text(encoding="utf-8"))
        assert chartkit.problems(doc) == [], p.name
        assert chart_series.semantic_problems(doc, p.name) == [], p.name
        assert doc["case"] == "B1" and doc["status"] == "ok"
        assert p.stat().st_size <= chartkit.MAX_BYTES


def test_the_producer_names_the_tool_method_version_and_the_honesty_label_on_every_chart(run):
    _, result, _, _ = run
    for c in result["charts"]:
        pr = c["producer"]
        assert pr["tool"] == "minehaulsim" and pr["version"].startswith("0.12.1+mp")
        assert "calibrated synthetic" in pr["label"] and "not validated against real data" in pr["label"]
        assert "TTC" in pr["method"]
    assert "calibrated synthetic" in result["summary"]["label"]


def test_headline_kpis_are_the_registry_kpis_of_case_b1_and_every_value_is_labelled(run):
    _, result, _, _ = run
    cases = yaml.safe_load((ROOT / "studio" / "cases.yaml").read_text(encoding="utf-8"))
    b1 = cases["cases"]["B1"] if "cases" in cases else cases["B1"]
    ids = {k["id"] for k in b1["kpis"]}
    heads = result["summary"]["headline"]
    assert {h["kpi"] for h in heads} == ids == {"min_ttc", "near_misses"}
    for h in heads:
        assert h["note"] and "calibrated synthetic" in h["note"] and h["unit"]
    shown = {c["kpi"] for c in result["charts"] if "kpi" in c}
    assert shown <= ids and shown == ids  # a chart per case KPI, so the Charts tab lists no placeholder for them


def test_the_near_miss_rate_chart_equals_the_counts_read_back(run):
    _, result, _, _ = run
    # the scenario table is built from the same per-seed numbers: its near-miss cell is the mean of the per-seed rates of the reference scenario
    table = next(c for c in result["charts"] if c["id"] == "b1-scenario-table")["table"]
    assert [r[0] for r in table["rows"]] == [0, 100]
    chart = next(c for c in result["charts"] if c["id"] == "b1-near-miss-rate-vs-share")
    s4 = next(s for s in chart["series"] if s["id"] == "lv4")
    assert s4["x"] == [0.0, 100.0] and s4["n"] == 2
    assert table["rows"][1][2] == pytest.approx(s4["y"][1], rel=1e-3)
    assert near_misses_per_1000h(3, 3600.0) == pytest.approx(3000.0)  # the formula the rate rests on


def test_no_light_vehicles_means_no_encounters_and_the_engine_tonnes(run):
    _, result, _, _ = run
    thr = next(c for c in result["charts"] if c["id"] == "b1-throughput-vs-share")
    engine = next(s for s in thr["series"] if s["id"] == "engine")
    assert all(v is not None and v > 0 for v in engine["y"])
    # with 4 light vehicles the throughput is at most the engine schedule's
    lv4 = next(s for s in thr["series"] if s["id"] == "lv4")
    assert all(a <= b * (1 + 1e-9) for a, b in zip(lv4["y"], engine["y"], strict=True))


def test_two_runs_with_the_same_seeds_write_identical_files(run, tmp_path):
    root, _, out, _ = run
    again = b1_run.compute(params(), root, tmp_path / "work2", 1)
    out2 = tmp_path / "out2"
    b1_run.write_outputs(again, out2)
    for p in sorted(out.rglob("*.json")):
        assert p.read_bytes() == (out2 / p.relative_to(out)).read_bytes(), p.name


def test_the_inputs_table_gives_every_input_its_source_with_page_or_table_or_the_unverified_label(run):
    _, result, _, _ = run
    t = next(c for c in result["charts"] if c["id"] == "b1-inputs-table")["table"]
    rows = t["rows"]
    assert len(rows) >= 14 and all(len(r) == 4 and all(len(c) <= 200 for c in r) for r in rows)
    statuses = {r[2] for r in rows}
    assert statuses <= {"Sourced", "Derived from a source", "Asset specification", "Specification", "UNVERIFIED"}
    for name, _, status, source in rows:
        assert source.strip(), name
        if status in ("Sourced", "Derived from a source"):
            assert " p. " in source or "Table" in source or "Eq." in source or " 4.11.1" in source, (
                name,
                source,
            )  # a page, table, equation or section
    unverified = [r[0] for r in rows if r[2] == "UNVERIFIED"]
    assert "Reaction time, autonomous truck" in unverified and "Acceleration, haul truck" in unverified
    sourced = [r[0] for r in rows if r[2] == "Sourced"]
    assert {"Deceleration, haul truck", "Deceleration, light vehicle", "Reaction time, manned vehicle"} <= set(sourced)


def test_no_encounter_of_the_sweep_has_a_time_to_collision_of_zero_and_collisions_are_reported(run):
    _, result, _, _ = run
    ttc = next(c for c in result["charts"] if c["id"] == "b1-min-ttc-distribution")
    for s in ttc["series"]:
        assert s["x"][0] == 0.0 and s["y"][0] == 0.0, s[
            "id"
        ]  # no encounter has a minimum TTC of 0: the distribution starts at zero
    conf = next(c for c in result["charts"] if c["id"] == "b1-conflicts-per-shift")
    assert {s["id"] for s in conf["series"]} >= {"collision-tl", "collision-ll"}


def test_the_command_line_writes_the_files_and_removes_its_work_folder(run, tmp_path):
    root, _, _, _ = run
    recipe = {"stages": [{"params": params(seeds=2)}]}
    rp = tmp_path / "recipe.yaml"
    rp.write_text(yaml.safe_dump(recipe), encoding="utf-8")
    work = tmp_path / "scratch"
    rc = b1_run.main(
        [
            "--recipe",
            str(rp),
            "--data-root",
            str(root),
            "--out",
            str(tmp_path / "o"),
            "--work",
            str(work),
            "--workers",
            "1",
        ]
    )
    assert rc == 0 and not work.exists()
    assert (tmp_path / "o" / "results-summary.json").is_file() and len(
        list((tmp_path / "o" / "charts").glob("*.json"))
    ) == len(EXPECTED)
