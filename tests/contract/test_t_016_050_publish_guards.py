"""T-016-050: table caption and comparability, table size, no GPU stages in CI (contract).

Requirements: FR-016-34, NFR-016-01, NFR-016-06.

Spec: specs/016-export-acceleration/spec.md
- FR-016-34: the table bake gives every published bench table the caption "measured on one RTX 5000 Ada Laptop GPU
  (power-limited), Windows 11, <date>, <commit SHA> -- not a general benchmark" (an em dash in the spec text), and
  comparisons in it are made only between records with the same enforced power limit and power source;
- NFR-016-01: the baked acceleration table is at most 200,000 bytes (CI budget check);
- NFR-016-06: `s62_accel` and `s64_bench` never run in CI; CI runs their logic against the fake GPU backend only (CI
  configuration check). plan.md: NFR-016-06 is a CI check: the workflow selects `-m "not gpu"` and never invokes
  `s62_accel` / `s64_bench` on hardware.

Oracles:
- the spec's own valid table `contracts/examples/accel-table.valid.json` (its caption, conditions and the three rows
  built from the three public bench-record examples) is the expected output of `bake_table`; the caption pattern is
  also the one of the draft schema; the em dash is written as the escape U+2014 in this file;
- the latency p50 of `bench-record.valid.json` (sustained, GPU compute: 3.248 ms) and a doubled copy (6.496 ms): the
  speed-up is 2.0 by hand;
- 200,000 bytes = the NFR threshold; hand-sized padding documents well away from the boundary (the serialisation
  layout is not specified, so no exact-boundary test is made);
- hand-written CI workflow fixtures (YAML) for the configuration check, and the repository's own workflows.

Expected public API (root environment):
module `pitstudio.accel.table`
    CAPTION_TEMPLATE = "measured on one RTX 5000 Ada Laptop GPU (power-limited), Windows 11, {date}, {sha} — not a
        general benchmark" (a single line, no line break)
    class NotComparable(ValueError)
    class TableTooLarge(ValueError)         # `.nbytes: int`
    bake_table(records: Sequence[Mapping], *, generated: str) -> dict
        the DC-016-05 document: schema_version "1.0", `generated`, git_sha (of the records), caption (date and SHA of
        the records), conditions {gpu_name, driver} (of the records' fingerprints), rows = rows_from_records(records).
        Raises ValueError when a record is not `performance == "public"`, or when the records disagree on date,
        git_sha, GPU name or driver, or when the list is empty.
    publishable(records: Sequence[Mapping]) -> list[dict]       # the `performance == "public"` records, input order
    speedup(baseline: Mapping, candidate: Mapping, *, regime: str = "sustained", scope: str = "gpu-compute",
            quantile: str = "p50") -> float
        baseline latency / candidate latency; raises NotComparable when the fingerprints' enforced power limits or
        power sources differ, or when a record has no latency numbers.
    serialise_table(doc: Mapping) -> bytes          # deterministic UTF-8 JSON as written to the web data folder
    check_table_size(doc: Mapping, *, max_bytes: int = 200_000) -> int      # returns the size; TableTooLarge above it
module `pitstudio.accel.guards`
    check_ci_workflows(workflows_dir: Path) -> list[str]
        reads every `*.yml` / `*.yaml`; a problem string naming file and job for: a step whose `run` text contains
        "pytest" but not "not gpu"; a step whose `run` text mentions "s62_accel" or "s64_bench" without "fake" (the fake
        GPU backend, `--gpu-backend fake:<device>`); a job whose `runs-on` mentions "gpu" or "self-hosted".
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pitstudio.accel.guards import check_ci_workflows
from pitstudio.accel.table import (
    CAPTION_TEMPLATE,
    NotComparable,
    TableTooLarge,
    bake_table,
    check_table_size,
    publishable,
    serialise_table,
    speedup,
)

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "016-export-acceleration" / "contracts" / "examples"
EM_DASH = "—"


def _load(name: str) -> dict:
    return json.loads((EX / name).read_text(encoding="utf-8"))


def _public_records() -> list[dict]:
    return [
        _load("bench-record.valid.json"),
        _load("bench-record.valid-rejected.json"),
        _load("bench-record.valid-not-run.json"),
    ]


def _validator():
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "contracts").glob("*.schema.json")}
    registry = Registry().with_resources([(s["$id"], Resource.from_contents(s)) for s in schemas.values()])
    return Draft202012Validator(schemas["accel-table.schema.json"], registry=registry)


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-34
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-34")
def test_the_caption_template_is_the_spec_sentence() -> None:
    assert CAPTION_TEMPLATE.format(date="2026-10-20", sha="01e2b86") == (
        f"measured on one RTX 5000 Ada Laptop GPU (power-limited), Windows 11, 2026-10-20, 01e2b86 {EM_DASH} "
        "not a general benchmark"
    )


@pytest.mark.req("FR-016-34")
def test_the_baked_table_is_the_spec_example_and_validates_against_dc_016_05() -> None:
    table = bake_table(_public_records(), generated="2026-10-21")
    assert table == _load("accel-table.valid.json")
    assert list(_validator().iter_errors(table)) == []
    sha = "01e2b86d09a37a1a3d9b5aaaedfc7028fd41e137"
    assert table["caption"] == (
        f"measured on one RTX 5000 Ada Laptop GPU (power-limited), Windows 11, 2026-10-20, {sha} {EM_DASH} "
        "not a general benchmark"
    )
    assert table["conditions"] == {"gpu_name": "NVIDIA RTX 5000 Ada Generation Laptop GPU", "driver": "581.42"}


@pytest.mark.req("FR-016-34")
def test_every_table_has_exactly_one_caption_so_mixed_runs_are_refused() -> None:
    a, b, c = _public_records()
    b["date"] = "2026-10-21"
    with pytest.raises(ValueError, match=r"date"):
        bake_table([a, b, c], generated="2026-10-22")
    b = _public_records()[1]
    b["git_sha"] = "f" * 40
    with pytest.raises(ValueError, match=r"git_sha"):
        bake_table([a, b, c], generated="2026-10-22")
    b = _public_records()[1]
    b["fingerprint"]["driver"] = "999.99"
    with pytest.raises(ValueError, match=r"driver"):
        bake_table([a, b, c], generated="2026-10-22")


@pytest.mark.req("FR-016-34")
def test_a_table_cannot_be_baked_from_a_local_only_record_or_from_nothing() -> None:
    with pytest.raises(ValueError, match=r"local-only"):
        bake_table([*_public_records(), _load("bench-record.valid-local-only.json")], generated="2026-10-21")
    with pytest.raises(ValueError, match=r"."):
        bake_table([], generated="2026-10-21")


@pytest.mark.req("FR-016-34")
def test_publishable_keeps_only_public_records_in_order() -> None:
    records = [
        _load("bench-record.valid.json"),
        _load("bench-record.valid-local-only.json"),
        _load("bench-record.valid-licence-changed.json"),
        _load("bench-record.valid-rejected.json"),
    ]
    kept = publishable(records)
    assert [(r["model"], r["backend"], r["status"]) for r in kept] == [
        ("d-fine-n", "tensorrt", "pass"),
        ("d-fine-s", "tensorrt", "rejected"),
    ]


@pytest.mark.req("FR-016-34")
def test_speedup_between_records_with_the_same_power_limit_and_source_is_the_latency_ratio() -> None:
    fast = _load("bench-record.valid.json")
    slow = copy.deepcopy(fast)
    for entry in slow["latency"]:
        for q in ("p50", "p90", "p95", "p99"):
            entry[q] = {k: 2 * v for k, v in entry[q].items()}
    assert speedup(slow, fast) == pytest.approx(2.0, rel=1e-12)  # 6.496 ms / 3.248 ms
    assert speedup(fast, fast) == 1.0
    assert speedup(slow, fast, regime="spaced", scope="end-to-end", quantile="p90") == pytest.approx(2.0, rel=1e-12)


@pytest.mark.req("FR-016-34")
def test_speedup_between_records_with_different_power_limits_or_sources_is_refused() -> None:
    a = _load("bench-record.valid.json")
    b = copy.deepcopy(a)
    b["fingerprint"]["power_limit_enforced_w"] = 90.0
    with pytest.raises(NotComparable) as info:
        speedup(a, b)
    assert "power" in str(info.value)
    c = copy.deepcopy(a)
    c["fingerprint"]["power_source"] = "battery"
    with pytest.raises(NotComparable):
        speedup(a, c)
    assert speedup(a, copy.deepcopy(a)) == 1.0


@pytest.mark.req("FR-016-34")
def test_speedup_with_a_record_that_has_no_latency_numbers_is_refused() -> None:
    with pytest.raises(NotComparable):
        speedup(_load("bench-record.valid.json"), _load("bench-record.valid-not-run.json"))


# ----------------------------------------------------------------------------------------------------------------------
# NFR-016-01
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("NFR-016-01")
def test_the_example_table_is_far_below_the_200000_byte_budget() -> None:
    table = _load("accel-table.valid.json")
    size = check_table_size(table)
    assert size == len(serialise_table(table))
    assert 1_000 < size < 200_000


@pytest.mark.req("NFR-016-01")
def test_a_table_of_a_hundred_example_rows_is_over_budget() -> None:
    table = _load("accel-table.valid.json")
    table["rows"] = [copy.deepcopy(table["rows"][0]) for _ in range(100)]  # about 3.3 KB per row
    assert len(serialise_table(table)) > 200_000
    with pytest.raises(TableTooLarge) as info:
        check_table_size(table)
    assert info.value.nbytes > 200_000


@pytest.mark.req("NFR-016-01")
def test_padding_documents_well_under_and_over_the_limit() -> None:
    assert check_table_size({"pad": "x" * 150_000}) > 150_000
    with pytest.raises(TableTooLarge):
        check_table_size({"pad": "x" * 250_000})
    with pytest.raises(TableTooLarge):
        check_table_size({"pad": "x" * 150_000}, max_bytes=100_000)


@pytest.mark.req("NFR-016-01")
def test_serialisation_is_deterministic_utf8_and_round_trips() -> None:
    table = _load("accel-table.valid.json")
    data = serialise_table(table)
    assert data == serialise_table(copy.deepcopy(table))
    assert json.loads(data.decode("utf-8")) == table
    assert EM_DASH.encode("utf-8") in data or b"\\u2014" in data


# ----------------------------------------------------------------------------------------------------------------------
# NFR-016-06
# ----------------------------------------------------------------------------------------------------------------------

GOOD_CI = """\
name: ci
on: [push]
jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - run: uv run pytest -m "not gpu" --cov=src
  runner-plan:
    runs-on: ubuntu-latest
    steps:
      - run: studio plan --gpu-backend fake:tests/fixtures/device.json --stage s64_bench
"""


def _write_ci(tmp_path: Path, name: str, text: str) -> Path:
    d = tmp_path / "workflows"
    d.mkdir(exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")
    return d


@pytest.mark.req("NFR-016-06")
def test_a_workflow_that_selects_not_gpu_and_runs_the_stages_on_the_fake_backend_is_clean(tmp_path: Path) -> None:
    assert check_ci_workflows(_write_ci(tmp_path, "ci.yml", GOOD_CI)) == []


@pytest.mark.req("NFR-016-06")
def test_pytest_without_the_not_gpu_selection_is_a_problem(tmp_path: Path) -> None:
    bad = GOOD_CI.replace('pytest -m "not gpu"', "pytest tests")
    problems = check_ci_workflows(_write_ci(tmp_path, "ci.yml", bad))
    assert len(problems) == 1
    assert "ci.yml" in problems[0]
    assert "python" in problems[0]
    assert "gpu" in problems[0]


@pytest.mark.req("NFR-016-06")
@pytest.mark.parametrize("stage", ["s62_accel", "s64_bench"])
def test_running_an_accel_or_bench_stage_without_the_fake_backend_is_a_problem(tmp_path: Path, stage: str) -> None:
    bad = GOOD_CI.replace(
        "studio plan --gpu-backend fake:tests/fixtures/device.json --stage s64_bench",
        f"studio run recipes/bench.yaml --stage {stage}",
    )
    problems = check_ci_workflows(_write_ci(tmp_path, "ci.yml", bad))
    assert len(problems) == 1
    assert stage in problems[0]
    assert "runner-plan" in problems[0]


@pytest.mark.req("NFR-016-06")
@pytest.mark.parametrize("runs_on", ["[self-hosted, windows, gpu]", "self-hosted", "gpu-runner"])
def test_a_gpu_or_self_hosted_runner_is_a_problem(tmp_path: Path, runs_on: str) -> None:
    bad = GOOD_CI.replace(
        "runs-on: ubuntu-latest\n    steps:\n      - run: studio plan",
        f"runs-on: {runs_on}\n    steps:\n      - run: studio plan",
    )
    problems = check_ci_workflows(_write_ci(tmp_path, "ci.yml", bad))
    assert any("runner-plan" in p for p in problems)


@pytest.mark.req("NFR-016-06")
def test_every_workflow_file_of_the_directory_is_read_and_malformed_yaml_is_reported(tmp_path: Path) -> None:
    d = _write_ci(tmp_path, "a.yml", GOOD_CI)
    _write_ci(tmp_path, "b.yaml", GOOD_CI.replace('-m "not gpu"', ""))
    _write_ci(tmp_path, "c.yml", "jobs: [unclosed")
    problems = check_ci_workflows(d)
    assert any("b.yaml" in p for p in problems)
    assert any("c.yml" in p for p in problems)
    assert not any("a.yml" in p for p in problems)


@pytest.mark.req("NFR-016-06")
def test_the_repository_workflows_select_not_gpu_and_never_run_the_gpu_stages_on_hardware() -> None:
    assert check_ci_workflows(ROOT / ".github" / "workflows") == []
