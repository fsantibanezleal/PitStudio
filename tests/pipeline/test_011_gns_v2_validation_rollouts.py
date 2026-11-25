"""GNS v2: full-length rollouts of the validation geometries (FR-011-04 selection split, never the test split).

`s50_evaluate(..., split="val")` rolls the trained model out on the VALIDATION geometries for the whole reference
length and writes
`evaluation.validation.json` beside the run, with per geometry whether the rollout diverged, at which step, and how
many steps
the reference needed to reach rest. It never reads the test geometries and never writes the published test report.
The tiny
synthetic dataset and the trained one-epoch run are those of the stage smoke test (T-011 stages): accuracy is not
asserted, the
report layout and the split discipline are.
"""

from __future__ import annotations

import json

import pytest
from pitstudio_pipeline.surrogates.gns import stages
from test_t_011_stages_smoke import run_dir  # noqa: F401  (the module-scoped fixture: dataset, trained run directory)


@pytest.mark.req("FR-011-04")
def test_011_validation_rollouts_cover_validation_geometries_only_and_report_divergence(run_dir) -> None:  # noqa: F811
    dataset, out, _ = run_dir
    published = out / "evaluation.published.json"
    before = published.read_bytes() if published.exists() else None
    report = stages.s50_evaluate(dataset, out, device="cpu", env={}, split="val")
    assert report["split"] == "val"
    assert [g["geometry_id"] for g in report["geometries"]] == dataset.split["val"]
    rollouts = report["validation_rollouts"]
    assert [r["geometry_id"] for r in rollouts] == dataset.split["val"]
    for r in rollouts:
        assert set(r) >= {
            "geometry_id",
            "family",
            "diverged",
            "diverged_at_step",
            "reference_steps_to_rest",
            "diverged_before_rest",
        }
        assert r["reference_steps_to_rest"] >= 1
        assert r["diverged_before_rest"] == (r["diverged"] and r["diverged_at_step"] <= r["reference_steps_to_rest"])
    saved = json.loads((out / "evaluation.validation.json").read_text(encoding="utf-8"))
    assert saved["split"] == "val"
    assert (published.read_bytes() if published.exists() else None) == before  # the test report is not touched


@pytest.mark.req("FR-011-04")
def test_011_an_unknown_split_is_refused(run_dir) -> None:  # noqa: F811
    dataset, out, _ = run_dir
    with pytest.raises(ValueError, match="split"):
        stages.s50_evaluate(dataset, out, device="cpu", env={}, split="train")
