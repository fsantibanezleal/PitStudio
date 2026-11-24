"""T-017-101: the E1 run writes the nested-shell table, the pushbacks and the chart-series files of an oreblocks
deposit (pipeline environment).

Requirements: FR-017-14, FR-017-15, FR-017-16, FR-017-17, FR-017-51, NFR-017-06.

Spec: specs/017-planning-survey/spec.md section 3.2; plan.md data flow of E1 (`s05_synthesize` with `oreblocks`, then
the pit, the shells and the pushbacks); the chart-series contract (DC-020-05, contracts/chart-series.schema.json).

Oracles (none of them is the code under test):
- exhaustive enumeration of every closed subset of a 3 x 3 x 2 oreblocks deposit (18 blocks, 2^18 subsets) gives the
  maximum closure value at lambda = 1, written in the test from the deposit's own block values and precedence;
- the exact solver stamped by `oreblocks` (`twin.upit.pit_value`) on a 6 x 6 x 4 deposit, up to the cent rounding of
  each block (half a cent per pit block);
- the nesting, partition and prefix properties of the shells, read back from the written bitsets by an independent
  decoder (`numpy.unpackbits`);
- the chart-series JSON Schema (`jsonschema`), and the numbers of every chart recomputed from the written shell table.

Expected public API (module `pitstudio_pipeline.planning.e1_run`):
    run_e1(out_dir: Path, *, archetype: str, dims: tuple[int, int, int], seed: int, t_min_t: float,
           section_lambdas: Sequence[float], clock=time) -> dict
        writes `e1-shells.json` (the DC-017-03 shells, ultimate pit and pushbacks; units and schedule are not
        run), `charts/e1-*.json`
        (chart-series, case E1) and `e1-run.json` (inputs, versions, min-cut timing, oracle comparison); returns the
        content of `e1-run.json`.
"""

from __future__ import annotations

import base64
import itertools
import json
import time
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator
from pitstudio_pipeline.planning.e1_run import run_e1
from pitstudio_pipeline.planning.oreblocks_io import twin_instance
from pitstudio.planning.bev import to_cents

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts" / "chart-series.schema.json").read_text("utf-8"))
SHELLS_SCHEMA = json.loads((ROOT / "contracts" / "pit-shells.schema.json").read_text("utf-8"))
LAMBDAS = [0.2, 0.4, 0.6, 0.8, 1.0]


def _bits(text: str, n: int) -> np.ndarray:
    raw = np.frombuffer(base64.b64decode(text), dtype=np.uint8)
    return np.unpackbits(raw, bitorder="little")[:n].astype(bool)


@pytest.fixture(scope="module")
def run(tmp_path_factory) -> tuple[Path, dict]:
    out = tmp_path_factory.mktemp("e1")
    summary = run_e1(
        out, archetype="porphyry", dims=(6, 6, 4), seed=3, t_min_t=2.0e6, section_lambdas=LAMBDAS, clock=time
    )
    return out, summary


def _doc(out: Path) -> dict:
    return json.loads((out / "e1-shells.json").read_text("utf-8"))


@pytest.mark.req("FR-017-14")
def test_the_pit_value_at_lambda_1_equals_exhaustive_enumeration_on_an_18_block_deposit(tmp_path: Path) -> None:
    out = tmp_path / "tiny"
    run_e1(out, archetype="porphyry", dims=(3, 3, 2), seed=1, t_min_t=1.0e5, section_lambdas=[1.0], clock=time)
    inst = twin_instance("porphyry", (3, 3, 2), 1)
    cents = [int(c) for c in to_cents(np.asarray(inst.values))]
    pairs = [(int(i), int(j)) for i, j in inst.arcs]
    best = 0
    for bits in itertools.product((0, 1), repeat=len(cents)):
        chosen = {i for i, b in enumerate(bits) if b}
        if any(i in chosen and j not in chosen for i, j in pairs):
            continue
        best = max(best, sum(cents[i] for i in chosen))
    assert _doc(out)["ultimate_pit"]["value_cents"] == best
    assert best > 0  # the tiny deposit is a real one: a non-empty pit


@pytest.mark.req("FR-017-15")
def test_the_ultimate_pit_equals_the_stamped_oreblocks_optimum_to_the_cent_rounding(run) -> None:
    out, summary = run
    doc = _doc(out)
    count = doc["shells"][-1]["block_count"]
    assert (
        abs(doc["ultimate_pit"]["value_cents"] / 100.0 - summary["oracle"]["stamped_pit_value_usd"])
        <= 0.005 * count + 1e-6
    )
    assert summary["oracle"]["agrees"] is True


@pytest.mark.req("FR-017-16")
def test_the_shell_table_has_the_40_lambdas_and_the_shells_are_nested_by_the_written_bitsets(run) -> None:
    out, _ = run
    doc = _doc(out)
    n = doc["block_model"]["n_blocks"]
    assert [r["lambda"] for r in doc["shells"]] == [k / 40 for k in range(1, 41)]
    masks = [_bits(r["blocks"], n) for r in doc["shells"]]
    assert [int(m.sum()) for m in masks] == [r["block_count"] for r in doc["shells"]]
    for small, large in itertools.pairwise(masks):
        assert not np.any(small & ~large)
    assert doc["block_set_encoding"] == "bitset-lsb0-base64"


@pytest.mark.req("FR-017-17")
def test_the_pushbacks_partition_the_final_pit_and_every_prefix_is_a_shell(run) -> None:
    out, _ = run
    doc = _doc(out)
    n = doc["block_model"]["n_blocks"]
    masks = [_bits(r["blocks"], n) for r in doc["shells"]]
    union = np.zeros(n, dtype=bool)
    for pb in doc["pushbacks"]:
        part = _bits(pb["blocks"], n)
        assert not np.any(union & part)
        union |= part
        assert np.array_equal(union, masks[pb["shell"]])
    assert np.array_equal(union, masks[-1])


@pytest.mark.req("FR-017-51")
def test_the_document_carries_the_synthetic_label_the_block_model_digest_and_the_scheduler_status(run) -> None:
    out, summary = run
    doc = _doc(out)
    assert len(doc["block_model"]["sha256"]) == 64
    assert "synthetic" in summary["label"]
    assert summary["scheduler"]["status"] == "not-run"
    assert "units" not in doc
    assert "schedule" not in doc


@pytest.mark.req("FR-017-16")
def test_every_chart_validates_against_the_chart_series_contract_and_carries_its_producer(run) -> None:
    out, _ = run
    files = sorted((out / "charts").glob("e1-*.json"))
    assert {f.stem for f in files} == {
        "e1-value-vs-lambda",
        "e1-strip-ratio-vs-lambda",
        "e1-shell-table",
        "e1-pushbacks",
        "e1-sections",
    }
    for f in files:
        chart = json.loads(f.read_text("utf-8"))
        assert list(Draft202012Validator(SCHEMA).iter_errors(chart)) == [], f.name
        assert chart["case"] == "E1"
        assert chart["status"] == "ok"
        assert chart["producer"]["tool"]
        assert chart["producer"]["version"]
        assert "synthetic" in chart["producer"]["label"]


@pytest.mark.req("FR-017-16")
def test_the_charts_repeat_the_numbers_of_the_shell_table(run) -> None:
    out, _ = run
    doc = _doc(out)
    value = json.loads((out / "charts" / "e1-value-vs-lambda.json").read_text("utf-8"))
    strip = json.loads((out / "charts" / "e1-strip-ratio-vs-lambda.json").read_text("utf-8"))
    table = json.loads((out / "charts" / "e1-shell-table.json").read_text("utf-8"))
    assert value["series"][0]["x"] == [r["lambda"] for r in doc["shells"]]
    assert value["series"][0]["y"] == pytest.approx([r["value_cents"] / 1e8 for r in doc["shells"]], rel=1e-12)
    assert strip["series"][0]["y"] == [r["strip_ratio"] for r in doc["shells"]]
    assert len(table["table"]["rows"]) == 40
    assert [row[0] for row in table["table"]["rows"]] == [r["lambda"] for r in doc["shells"]]


@pytest.mark.req("FR-017-16")
def test_the_sections_are_nested_floors_one_polyline_per_requested_lambda(run) -> None:
    out, _ = run
    section = json.loads((out / "charts" / "e1-sections.json").read_text("utf-8"))["section"]
    shells = [p for p in section["polylines"] if p["role"] == "shell"]
    assert len(shells) == len(LAMBDAS)
    assert any(p["role"] == "ground" for p in section["polylines"])
    # a larger lambda never has a higher pit floor at the same column: the floor depth only grows
    floors = [{x: z for x, z in p["points"]} for p in shells]
    for small, large in itertools.pairwise(floors):
        for x, z in small.items():
            assert large.get(x, z) <= z + 1e-9


@pytest.mark.req("NFR-017-06")
def test_the_min_cut_wall_times_are_recorded_for_every_lambda(run) -> None:
    _, summary = run
    assert set(summary["timing"]["mincut_wall_s"]) == {
        f"twin-porphyry-6x6x4-s3-lambda-{k / 40:.3f}" for k in range(1, 41)
    }
    assert summary["timing"]["overruns"] == []


@pytest.mark.req("FR-017-22")
def test_the_shells_document_is_a_valid_dc_017_03_result_without_units_and_schedule(run) -> None:
    out, _ = run
    doc = _doc(out)
    assert list(Draft202012Validator(SHELLS_SCHEMA).iter_errors(doc)) == []
    assert "contract" not in doc
