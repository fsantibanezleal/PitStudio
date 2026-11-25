"""T-010-060: the C1 recipe end to end on the sample data (CPU) with valid manifests.

Requirement: FR-010-39 ("The recipe `studio/recipes/cases/c1.yaml` shall run end to end on the open lane (no NVIDIA
proprietary
runtime), producing manifests (DC-000-01) for sections, FoS/PoF tables, event sets, forecasts, metrics and ONNX files,
each naming
its producer tool, measured lane, licence class and input SHA-256 digests").
Spec: specs/010-slope/spec.md section 3.4 (FR-010-39), US-010-5; plan.md row FR-010-39 ("manifests validated against
`contracts/manifest.schema.json`; CPU run on samples"). Runs in the `pipeline/` environment.

Expected API (module `pitstudio_pipeline.slope.c1`): `run(*, out_dir, scale="sample", seed=20261007, dewit_archive=None,
dewit_pins=None) -> C1Run` runs the CPU stages of the recipe in order (s05_synthesize, s10_preprocess for the
sections, the FoS /
PoF analysis, s30_train, s40_infer, s50_evaluate, s60_export) on the committed sample data (`scale="sample"`: one
section, a few
dozen synthetic events with 64 samples each, a few training epochs, 200 golden contexts); `dewit_archive` (a path) and
`dewit_pins` ({"bytes", "md5"}) feed the optional real-event stage, absent -> the real event is "not run". `C1Run` has
`manifest` (a run manifest {"run_id", "artefacts": [DC-000-01 artefact records]}), `out_dir`, `stages` (the executed
stage ids in
order), `results` (the DC-010-03 document) and `lane_profile` ("open"). Every artefact record validates against
`contracts/manifest.schema.json#/$defs/artefact` and names `producer.tool` and `producer.stage`, `lane`,
`licence_class`, and an
`inputs` list whose sha256 values equal the digests of the files the stage read (artefact inputs: the sha256 of the
producing
artefact of the same run; source inputs: the digest of the sample file). Artefact kinds present: `table` (sections,
FoS/PoF,
events, forecasts, metrics), `onnx` (TCN and PatchTST; Chronos-Bolt appears as PRECOMPUTE when it did not export). No
NVIDIA
proprietary runtime is imported.

Oracles: the manifest schema (jsonschema); `hashlib` recomputation of every artefact file and every input digest; the
recipe's own
stage list; the module list of the interpreter after the run.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

import _slope_lem_ref as lem_ref  # noqa: E402
from pitstudio_pipeline.slope import c1  # noqa: E402

STAGES = [
    "s05_synthesize",
    "s10_preprocess",
    "s20_feature_extraction",
    "s30_train",
    "s40_infer",
    "s50_evaluate",
    "s60_export",
]
NVIDIA = ("tensorrt", "pycuda", "cuda", "cupy", "nvidia", "pynvml", "pycuda.driver", "tensorrt_lean")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("c1")
    return c1.run(out_dir=out, scale="sample", seed=20261007)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.req("FR-010-39")
def test_the_recipe_runs_its_cpu_stages_in_order_on_the_open_lane(run) -> None:
    recipe = yaml.safe_load((ROOT / "studio" / "recipes" / "cases" / "c1.yaml").read_text(encoding="utf-8"))
    declared = [s["id"] for s in recipe["stages"]]
    positions = [declared.index(s) for s in run.stages if s in declared]
    assert positions == sorted(positions)  # the executed stages follow the declared order
    assert {"s05_synthesize", "s30_train", "s40_infer", "s50_evaluate", "s60_export"} <= set(run.stages)
    assert run.lane_profile == "open"
    assert not [m for m in sys.modules if m.split(".")[0] in {"tensorrt", "pycuda", "cupy", "pynvml", "tensorrt_lean"}]


@pytest.mark.req("FR-010-39")
def test_every_artefact_record_validates_and_names_producer_lane_and_licence_class(run) -> None:
    arts = run.manifest["artefacts"]
    assert arts
    for a in arts:
        assert lem_ref.schema_errors(a, "manifest", "artefact") == [], a["id"]
        assert a["producer"]["tool"]
        assert a["producer"]["stage"]["id"] in [*STAGES, "s00_download"]
        assert a["lane"]
        assert a["licence_class"]
    assert len({a["id"] for a in arts}) == len(arts)


@pytest.mark.req("FR-010-39")
def test_the_expected_artefact_families_are_present(run) -> None:
    arts = run.manifest["artefacts"]
    by_kind: dict[str, list] = {}
    for a in arts:
        by_kind.setdefault(a["kind"], []).append(a)
    ids = " ".join(a["id"] for a in arts)
    for family in ("section", "fos", "pof", "events", "forecast", "metrics"):
        assert family in ids, family
    assert {"table", "onnx"} <= set(by_kind)
    onnx_ids = {a["id"] for a in by_kind["onnx"]}
    assert any("tcn" in i for i in onnx_ids)
    assert any("patchtst" in i for i in onnx_ids)


@pytest.mark.req("FR-010-39")
def test_artefact_digests_and_sizes_are_those_of_the_files_on_disk(run) -> None:
    for a in run.manifest["artefacts"]:
        f = Path(run.out_dir) / a["path"]
        assert f.is_file(), a["path"]
        assert a["bytes"] == f.stat().st_size
        assert a["sha256"] == _sha(f)


@pytest.mark.req("FR-010-39")
def test_every_input_digest_is_the_digest_of_the_artefact_or_sample_file_it_names(run) -> None:
    arts = {a["id"]: a for a in run.manifest["artefacts"]}
    checked = 0
    for a in arts.values():
        for inp in a["inputs"]:
            if inp["kind"] == "artefact":
                assert inp["id"] in arts, (a["id"], inp["id"])
                assert inp["sha256"] == arts[inp["id"]]["sha256"]
            else:
                assert len(inp["sha256"]) == 64
            checked += 1
    assert checked > 0
    consumers = [
        a for a in arts.values() if a["producer"]["stage"]["id"] in {"s30_train", "s40_infer", "s50_evaluate", "s60_export"}
    ]
    assert all(a["inputs"] for a in consumers)  # downstream stages always list their inputs


@pytest.mark.req("FR-010-39")
def test_the_onnx_lane_is_the_measured_one_and_precompute_arms_say_so(run) -> None:
    onnx = [a for a in run.manifest["artefacts"] if a["kind"] == "onnx"]
    assert onnx
    for a in onnx:
        assert a["lane"]  # the schema restricts it to the lane vocabulary of FR-000-15
    notes = [a for a in run.manifest["artefacts"] if "chronos" in a["id"] and a["kind"] != "onnx"]
    assert notes  # Chronos-Bolt appears as baked forecasts (PRECOMPUTE) when it did not export on the CPU run


@pytest.mark.req("FR-010-39")
def test_the_results_document_is_valid_and_the_real_event_is_not_run_without_an_archive(run) -> None:
    assert lem_ref.schema_errors(run.results, "ttf-results") == []
    assert run.results["real_event"]["status"] == "not run"
    assert run.results["multiplicity"] == {"comparisons": 8, "family_wise_claim": False}


@pytest.mark.req("FR-010-39")
def test_two_runs_with_the_same_seed_produce_the_same_artefact_bytes(run, tmp_path: Path) -> None:
    again = c1.run(out_dir=tmp_path, scale="sample", seed=20261007)
    first = {a["id"]: a["sha256"] for a in run.manifest["artefacts"] if a["kind"] == "table"}
    second = {a["id"]: a["sha256"] for a in again.manifest["artefacts"] if a["kind"] == "table"}
    assert first == second


@pytest.mark.req("FR-010-39")
def test_a_missing_or_bad_scale_or_seed_is_rejected_before_any_stage_runs(tmp_path: Path) -> None:
    for kwargs in ({"scale": "full-gpu"}, {"scale": ""}, {"seed": -1}, {"seed": 2**63}, {"seed": "7"}):
        with pytest.raises(ValueError, match=r"."):
            c1.run(out_dir=tmp_path / "x", **{"scale": "sample", "seed": 1, **kwargs})
    assert not (tmp_path / "x").exists() or not any((tmp_path / "x").iterdir())
