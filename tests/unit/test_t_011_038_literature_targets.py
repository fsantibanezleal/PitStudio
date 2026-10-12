"""T-011-038 - FR-011-28: literature-target calibrations (UNVERIFIED propagation, provenance, no coverage claim).

Oracles (independent of the code under test; plan 011 test strategy FR-011-28):
- the draft DC-011-04 schema (`specs/011-surrogates/contracts/calibration-result.schema.json`) with the reference
  implementation `jsonschema`: a literature-target document must carry material, knowledge_row and verification in its
  target and must not carry `truth` or `covers_truth` on any parameter (no coverage claim);
- the provenance record of the DC-011-01 draft schema (`granular-rollout.schema.json`, `$defs/material_value`:
    value, source,
  ref, verification): the published calibrated friction must validate against it with source "calibration" (the GNS
  rollout metadata and the DEM and MPM-evaluation inputs consume that shape);
- knowledge-table fixture rows written here (the `minephys` tables are not read by the test): crushed gravel at 38 deg
  and dry sand at 34 deg, with one VERIFIED and one UNVERIFIED status, on the fake simulator theta = 24 + 20 mu
  (exact optima 0.7 and 0.5).

Expected public API (module `pitstudio_studio.physics.calibration.driver`; error class
`pitstudio.calibration.errors.InvalidCalibrationError`):

    REQUIRED_LITERATURE_MATERIALS = ("crushed-gravel", "dry-sand")
    calibrate_literature_targets(rows, simulator_factory, *, arm="cma-es", budget=60, seed_base=100_000) -> list[dict]
        rows: knowledge-table repose targets, dicts with material (slug), knowledge_row (id), theta_deg (float),
        verification ("verified" | "UNVERIFIED"); simulator_factory(row) -> simulator (the protocol of
            tests/_calib_fake.py,
        particle_count 20,000). One DC-011-04 document per row, kind "literature-target", full-scale particle_count
            20000,
        target = {theta_deg, material, knowledge_row, verification}, no truth and no coverage fields, distinct slug
            trial ids
        and disjoint seeds. At least the two required materials must be present.
    publish_calibrated_set(results) -> dict
        {"materials": {material: {"sliding_friction": <material_value record>}}}; the record is
        {"value": mu_hat, "source": "calibration", "ref": trial_id, "verification": <the target's status>}.
    Hostile rows (theta_deg outside [5, 60] or non-finite, a material or knowledge_row that is not a valid
        identifier, an
    unknown verification status, a duplicated material, a missing required material, no rows) raise
        InvalidCalibrationError
    naming the offending field before any simulation.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _calib_fake import FakeDem  # noqa: E402
from pitstudio_studio.physics.calibration import driver  # noqa: E402

from pitstudio.calibration.errors import InvalidCalibrationError  # noqa: E402

CONTRACTS = ROOT / "specs" / "011-surrogates" / "contracts"
RESULT = jsonschema.Draft202012Validator(
    json.loads((CONTRACTS / "calibration-result.schema.json").read_text(encoding="utf-8"))
)
ROLLOUT = json.loads((CONTRACTS / "granular-rollout.schema.json").read_text(encoding="utf-8"))
MATERIAL_VALUE = jsonschema.Draft202012Validator(
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/material_value",
        "$defs": ROLLOUT["$defs"],
    }
)
ROWS = [
    {
        "material": "crushed-gravel",
        "knowledge_row": "granular.repose_crushed_gravel",
        "theta_deg": 38.0,
        "verification": "UNVERIFIED",
    },
    {
        "material": "dry-sand",
        "knowledge_row": "granular.repose_dry_sand",
        "theta_deg": 34.0,
        "verification": "verified",
    },
]
CREATED: list[FakeDem] = []


def factory(row: dict) -> FakeDem:
    fake = FakeDem(24.0, 20.0, sigma=0.05, particle_count=20000)
    CREATED.append(fake)
    return fake


def run(arm: str = "cma-es", rows=None) -> list[dict]:
    return driver.calibrate_literature_targets(
        copy.deepcopy(ROWS if rows is None else rows), factory, arm=arm, budget=24
    )


@pytest.fixture(scope="module")
def results() -> list[dict]:
    return run()


def walk_keys(obj) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            out |= walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= walk_keys(v)
    return out


@pytest.mark.req("FR-011-28")
@pytest.mark.parametrize("arm", ["cma-es", "gradient"])
def test_every_row_gives_a_valid_literature_document_at_full_scale(arm: str) -> None:
    docs = run(arm)
    assert len(docs) == 2
    for doc, row in zip(docs, ROWS, strict=True):
        assert [e.message for e in RESULT.iter_errors(doc)] == []
        assert doc["kind"] == "literature-target"
        assert doc["arm"] == arm
        assert doc["particle_count"] == 20000
        assert doc["target"]["material"] == row["material"]
        assert doc["target"]["knowledge_row"] == row["knowledge_row"]
        assert doc["target"]["theta_deg"] == row["theta_deg"]
    assert len({d["trial_id"] for d in docs}) == 2


@pytest.mark.req("FR-011-28")
def test_the_target_verification_status_is_reported_unchanged(results) -> None:
    assert [d["target"]["verification"] for d in results] == ["UNVERIFIED", "verified"]


@pytest.mark.req("FR-011-28")
def test_no_coverage_claim_is_made_for_a_literature_target(results) -> None:
    for doc in results:
        assert "truth" not in walk_keys(doc["parameters"])
        assert "covers_truth" not in walk_keys(doc["parameters"])
        assert doc["parameters"][0]["interval"]["level"] == 0.95  # the interval itself is still reported
        assert "coverage" not in walk_keys(doc)


@pytest.mark.req("FR-011-28")
def test_the_estimates_come_with_their_interval_near_the_fake_optima(results) -> None:
    for doc, mu_star in zip(results, (0.7, 0.5), strict=True):
        p = doc["parameters"][0]
        assert abs(p["estimate"] - mu_star) < 0.15  # a 24-simulation budget on the noise-free fake
        assert p["bounds"] == [0.1, 1.0]


@pytest.mark.req("FR-011-28")
def test_the_published_set_has_provenance_and_propagates_unverified(results) -> None:
    published = driver.publish_calibrated_set(results)
    assert set(published["materials"]) == {"crushed-gravel", "dry-sand"}
    for doc in results:
        rec = published["materials"][doc["target"]["material"]]["sliding_friction"]
        assert [e.message for e in MATERIAL_VALUE.iter_errors(rec)] == []  # the DC-011-01 material_value shape
        assert rec["source"] == "calibration"
        assert rec["ref"] == doc["trial_id"]
        assert rec["value"] == pytest.approx(doc["parameters"][0]["estimate"], rel=1e-12)
    assert published["materials"]["crushed-gravel"]["sliding_friction"]["verification"] == "UNVERIFIED"
    assert "coverage" not in walk_keys(published)


@pytest.mark.req("FR-011-28")
def test_seeds_of_different_rows_do_not_overlap(results) -> None:
    every = [s for d in results for role in d["seeds"].values() for s in role]
    assert len(every) == len(set(every))


@pytest.mark.req("FR-011-28")
def test_an_unverified_target_is_still_calibrated_and_never_silently_upgraded() -> None:
    rows = [dict(r, verification="UNVERIFIED") for r in ROWS]
    docs = run(rows=rows)
    published = driver.publish_calibrated_set(docs)
    assert all(d["target"]["verification"] == "UNVERIFIED" for d in docs)
    assert all(m["sliding_friction"]["verification"] == "UNVERIFIED" for m in published["materials"].values())


@pytest.mark.req("FR-011-28")
def test_extra_materials_beyond_the_required_two_are_accepted() -> None:
    rows = [
        *ROWS,
        {
            "material": "wet-clay",
            "knowledge_row": "granular.repose_wet_clay",
            "theta_deg": 30.0,
            "verification": "UNVERIFIED",
        },
    ]
    assert len(run(rows=rows)) == 3


# ------------------------------------------------------------------ hostile rows


def mutated(index: int, **changes) -> list[dict]:
    rows = copy.deepcopy(ROWS)
    rows[index].update(changes)
    return rows


HOSTILE = [
    (mutated(0, theta_deg=4.9), "theta_deg"),
    (mutated(0, theta_deg=60.1), "theta_deg"),
    (mutated(1, theta_deg=float("nan")), "theta_deg"),
    (mutated(1, theta_deg=float("inf")), "theta_deg"),
    (mutated(0, material="grava triturada"), "material"),
    (mutated(0, material="Gravel"), "material"),
    (mutated(0, material="grava-ñandú"), "material"),
    (mutated(0, material=""), "material"),
    (mutated(1, knowledge_row="bad row"), "knowledge_row"),
    (mutated(1, knowledge_row=""), "knowledge_row"),
    (mutated(0, verification="probably"), "verification"),
    (mutated(1, verification=None), "verification"),
    ([ROWS[0], dict(ROWS[0])], "duplicate"),
    ([ROWS[0]], "dry-sand"),
    ([ROWS[1]], "crushed-gravel"),
    ([], "rows"),
]


@pytest.mark.req("FR-011-28")
@pytest.mark.parametrize(("rows", "needle"), HOSTILE, ids=[f"{i}-{n}" for i, (_, n) in enumerate(HOSTILE)])
def test_hostile_rows_are_refused_naming_the_field_before_any_simulation(rows: list[dict], needle: str) -> None:
    CREATED.clear()
    with pytest.raises(InvalidCalibrationError, match=needle):
        driver.calibrate_literature_targets(rows, factory, arm="cma-es", budget=24)
    assert all(f.forward_calls == [] and f.grad_calls == [] for f in CREATED)
