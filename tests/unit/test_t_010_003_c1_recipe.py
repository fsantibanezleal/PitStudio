"""T-010-003: the C1 recipe carries the section 7 parameters as defaults and invalid C1 recipes are rejected before
any stage runs.

Requirement: FR-010-40 ("If the C1 recipe names an unknown method, model or stratum, a cut-off outside (0, 1),
duplicate cut-offs,
or a test seed range overlapping the training range, then `studio plan` shall reject it with a schema error before any
stage
runs").
Spec: specs/010-slope/spec.md section 3.4 (FR-010-39, FR-010-40) and the parameter table of section 7; plan.md rows
FR-010-40
("invalid recipes written in the test") and the recipe line of the component table (`studio/recipes/cases/c1.yaml`).

Expected API (module `pitstudio.slope.recipe`, root environment; `studio plan` calls `validate_recipe` while it
validates the
recipe, so the rejection happens before the DAG is built):
- `load_recipe(path) -> dict`: reads a recipe with the strict YAML loader of `pitstudio.contracts`, validates it against
  `contracts/recipe.schema.json` and with `validate_recipe`.
- `validate_recipe(recipe: dict) -> None`: raises `InvalidRecipeError(ValueError)` with `.pointer` (JSON pointer of
  the offending
  value, e.g. "/stages/3/params/cutoffs/1") and `.keyword` (the failing rule: "enum", "range", "uniqueItems",
  "overlap") for the
  C1-specific rules below; it does nothing for recipes of other cases.
- The file `studio/recipes/cases/c1.yaml` exists, is valid, has `case: C1` and these stage parameters (stage id ->
  params):
    s05_synthesize: alpha [1.7, 2.3], terminal_duration_h [24, 720], onset_velocity_mm_per_day [0.1, 10],
      steady_phase_fraction [0.1, 0.5], regressive_probability 0.2, regressive_velocity_reduction [0.3, 0.7],
      regressive_duration_fraction [0.05, 0.15], psi_deg [0, 60], n_samples 2000, ar1_rho 0.9,
      strata ["snr_obs", "half_snr_obs", "double_snr_obs", "snr_obs_atmospheric"],
      splits {train {start 0, count 20000}, validation {start 20000, count 1000}, test {start 21000, count_per_stratum
      500}};
    s30_train: context_length 128, block_mean_width 4, horizon_steps 64, max_blocks 4,
      quantiles [0.1, ..., 0.9], models ["tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned"];
    s40_infer: resample_points 512, velocity_window 9, iv_last_fraction 0.25, iv_min_points 10, bayes_draws 4000,
      horizon_cap_steps 1024, methods (all six);
    s50_evaluate: cutoffs [0.5, 0.8], alarm_grid {start 0.30, stop 0.99, step 0.01}, t_alarm_h 24, bootstrap_resamples
    10000,
      strata (the four observed ones), methods (all six), models (the four learned ones), radar_psi_deg [0, 45, 70],
      scan_interval_min 6.
  Methods: inverse_velocity, bayesian_ttf, tcn, patchtst, chronos_bolt_zero_shot, chronos_bolt_fine_tuned; strata:
  snr_obs,
  half_snr_obs, double_snr_obs, snr_obs_atmospheric (and the nominal_10 / nominal_30 / nominal_100 fallback strata).

Oracle: the section 7 table copied into the test; one hostile recipe per class of FR-010-40 built from the valid file
by changing
exactly one value; valid variations (other cut-offs, fewer strata) accepted.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio.slope import recipe as c1  # noqa: E402

from pitstudio.contracts import load_yaml, validate  # noqa: E402

PATH = ROOT / "studio" / "recipes" / "cases" / "c1.yaml"
METHODS = ["inverse_velocity", "bayesian_ttf", "tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned"]
MODELS = METHODS[2:]
STRATA = ["snr_obs", "half_snr_obs", "double_snr_obs", "snr_obs_atmospheric"]


def _stage(recipe: dict, stage_id: str) -> dict:
    return next(s for s in recipe["stages"] if s["id"] == stage_id)


def _recipe() -> dict:
    return copy.deepcopy(load_yaml(PATH))


@pytest.mark.req("FR-010-40")
def test_the_c1_recipe_exists_validates_against_the_schema_and_loads() -> None:
    doc = load_yaml(PATH)
    assert doc["case"] == "C1"
    assert validate(doc, "recipe") == []
    assert c1.load_recipe(PATH)["case"] == "C1"
    c1.validate_recipe(doc)


@pytest.mark.req("FR-010-40")
def test_the_section_7_parameters_are_the_recipe_defaults() -> None:
    r = _recipe()
    s05 = _stage(r, "s05_synthesize")["params"]
    assert s05["alpha"] == [1.7, 2.3]
    assert s05["terminal_duration_h"] == [24, 720]
    assert s05["onset_velocity_mm_per_day"] == [0.1, 10]
    assert s05["steady_phase_fraction"] == [0.1, 0.5]
    assert s05["regressive_probability"] == 0.2
    assert s05["regressive_velocity_reduction"] == [0.3, 0.7]
    assert s05["regressive_duration_fraction"] == [0.05, 0.15]
    assert s05["psi_deg"] == [0, 60]
    assert s05["n_samples"] == 2000
    assert s05["ar1_rho"] == 0.9
    assert s05["strata"] == STRATA
    assert s05["splits"] == {
        "train": {"start": 0, "count": 20000},
        "validation": {"start": 20000, "count": 1000},
        "test": {"start": 21000, "count_per_stratum": 500},
    }
    s30 = _stage(r, "s30_train")["params"]
    assert (s30["context_length"], s30["block_mean_width"], s30["horizon_steps"], s30["max_blocks"]) == (128, 4, 64, 4)
    assert s30["quantiles"] == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
    assert s30["models"] == MODELS
    s40 = _stage(r, "s40_infer")["params"]
    assert (s40["resample_points"], s40["velocity_window"], s40["iv_last_fraction"], s40["iv_min_points"]) == (
        512,
        9,
        0.25,
        10,
    )
    assert (s40["bayes_draws"], s40["horizon_cap_steps"]) == (4000, 1024)
    assert s40["methods"] == METHODS
    s50 = _stage(r, "s50_evaluate")["params"]
    assert s50["cutoffs"] == [0.5, 0.8]
    assert s50["alarm_grid"] == {"start": 0.30, "stop": 0.99, "step": 0.01}
    assert (s50["t_alarm_h"], s50["bootstrap_resamples"], s50["scan_interval_min"]) == (24, 10000, 6)
    assert s50["strata"] == STRATA
    assert s50["methods"] == METHODS
    assert s50["models"] == MODELS
    assert s50["radar_psi_deg"] == [0, 45, 70]


HOSTILE = [
    ("unknown-method", "s50_evaluate", "methods", lambda v: [*v, "xgboost"], "/params/methods/6", "enum"),
    ("unknown-method-in-infer", "s40_infer", "methods", lambda v: [*v[:-1], "arima"], "/params/methods/5", "enum"),
    ("unknown-model", "s50_evaluate", "models", lambda v: [*v, "lstm"], "/params/models/4", "enum"),
    ("unknown-model-in-train", "s30_train", "models", lambda v: ["gru", *v[1:]], "/params/models/0", "enum"),
    ("unknown-stratum", "s50_evaluate", "strata", lambda v: [*v, "snr_obs_extreme"], "/params/strata/4", "enum"),
    (
        "unknown-stratum-in-synthesis",
        "s05_synthesize",
        "strata",
        lambda v: ["night", *v[1:]],
        "/params/strata/0",
        "enum",
    ),
    ("cutoff-one", "s50_evaluate", "cutoffs", lambda v: [0.5, 1.0], "/params/cutoffs/1", "range"),
    ("cutoff-zero", "s50_evaluate", "cutoffs", lambda v: [0.0, 0.8], "/params/cutoffs/0", "range"),
    ("cutoff-above-one", "s50_evaluate", "cutoffs", lambda v: [0.5, 1.2], "/params/cutoffs/1", "range"),
    ("cutoff-negative", "s50_evaluate", "cutoffs", lambda v: [-0.1, 0.5], "/params/cutoffs/0", "range"),
    ("cutoff-nan", "s50_evaluate", "cutoffs", lambda v: [0.5, float("nan")], "/params/cutoffs/1", "range"),
    ("cutoffs-duplicate", "s50_evaluate", "cutoffs", lambda v: [0.5, 0.5], "/params/cutoffs", "uniqueItems"),
    (
        "cutoffs-duplicate-non-adjacent",
        "s50_evaluate",
        "cutoffs",
        lambda v: [0.8, 0.5, 0.8],
        "/params/cutoffs",
        "uniqueItems",
    ),
    (
        "test-seeds-inside-training",
        "s05_synthesize",
        "splits",
        lambda v: {**v, "test": {"start": 19000, "count_per_stratum": 500}},
        "/params/splits",
        "overlap",
    ),
    (
        "test-seeds-overlap-training-tail",
        "s05_synthesize",
        "splits",
        lambda v: {**v, "test": {"start": 19999, "count_per_stratum": 500}},
        "/params/splits",
        "overlap",
    ),
    (
        "validation-overlaps-training",
        "s05_synthesize",
        "splits",
        lambda v: {**v, "validation": {"start": 100, "count": 1000}},
        "/params/splits",
        "overlap",
    ),
    (
        "test-overlaps-validation",
        "s05_synthesize",
        "splits",
        lambda v: {**v, "test": {"start": 20500, "count_per_stratum": 500}},
        "/params/splits",
        "overlap",
    ),
]


@pytest.mark.req("FR-010-40")
@pytest.mark.parametrize(
    ("name", "stage_id", "key", "change", "pointer_tail", "keyword"), HOSTILE, ids=[h[0] for h in HOSTILE]
)
def test_an_invalid_c1_recipe_is_rejected_with_a_pointer_before_any_stage_runs(
    name, stage_id, key, change, pointer_tail, keyword
) -> None:
    r = _recipe()
    stage = _stage(r, stage_id)
    stage["params"][key] = change(stage["params"][key])
    index = r["stages"].index(stage)
    with pytest.raises(c1.InvalidRecipeError) as exc:
        c1.validate_recipe(r)
    assert exc.value.pointer.startswith(f"/stages/{index}{pointer_tail}"), (name, exc.value.pointer)
    assert exc.value.keyword == keyword
    assert isinstance(exc.value, ValueError)


@pytest.mark.req("FR-010-40")
def test_valid_variations_are_accepted() -> None:
    r = _recipe()
    _stage(r, "s50_evaluate")["params"]["cutoffs"] = [0.4, 0.6, 0.9]
    c1.validate_recipe(r)
    r = _recipe()
    for sid in ("s05_synthesize", "s50_evaluate"):
        _stage(r, sid)["params"]["strata"] = ["snr_obs"]
    c1.validate_recipe(r)
    r = _recipe()
    _stage(r, "s05_synthesize")["params"]["splits"]["test"]["start"] = 40000  # a disjoint test block
    c1.validate_recipe(r)
    r = _recipe()
    _stage(r, "s50_evaluate")["params"]["cutoffs"] = [0.01, 0.99]  # inside (0, 1)
    c1.validate_recipe(r)


@pytest.mark.req("FR-010-40")
def test_a_recipe_of_another_case_is_not_judged_by_the_c1_rules() -> None:
    other = {
        "case": "A2",
        "stages": [{"id": "s50_evaluate", "params": {"cutoffs": [2.0, 2.0], "methods": ["whatever"]}}],
    }
    c1.validate_recipe(other)  # not a C1 recipe: nothing to check here (spec 001 validates its shape)
