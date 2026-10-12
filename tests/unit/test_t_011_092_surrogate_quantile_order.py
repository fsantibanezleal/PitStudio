"""T-011-092 - FR-011-46: quantile levels of a surrogate input or output must increase strictly inside (0, 1).

Oracles (independent of the code under test; plan 011 test strategy FR-011-46): hand calculation from the spec
    text, base
document = the spec's own forecaster example (`surrogate-io.valid-forecaster.json`, nine levels 0.1 ... 0.9 on axis 1):
  [0.1, 0.5, 0.5]   repeated level                -> rejected
  [0.5, 0.1]        decreasing                    -> rejected
  [0.0, 0.5]        0 is not inside (0, 1)        -> rejected
  [0.1, 0.5, 0.9]   strictly increasing in (0, 1) -> accepted
plus the further hand cases below (1.0, negative, NaN, unsorted, descending, a single level).
Each document keeps shape[quantile_axis] equal to the number of levels, so that only the order or range rule is at
    stake.

Expected public API (module `pitstudio.surrogate_io`, under `src/pitstudio/`):

    load_surrogate_io(source) -> dict
        source: a dict (a DC-011-02 document) or a path (str or Path) to its JSON file; returns the validated document.
        Raises `pitstudio.surrogate_io.SurrogateIoError` with `error_class == "surrogate-io-invalid"` and a message
            that names the
        offending field, e.g. "outputs[0].quantiles", for a quantile list that is not strictly increasing inside
            (0, 1), and
        (same class) for every other violation of the schema or of the checker rules of the corpus index.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio.surrogate_io import SurrogateIoError, load_surrogate_io  # noqa: E402

EX = ROOT / "specs" / "011-surrogates" / "contracts" / "examples"
FORECASTER = json.loads((EX / "surrogate-io.valid-forecaster.json").read_text(encoding="utf-8"))
NAN = float("nan")


def with_levels(levels: list[float], *, where: str = "outputs") -> dict:
    doc = copy.deepcopy(FORECASTER)
    out = doc["outputs"][0]
    out["quantiles"] = list(levels)
    out["shape"][out["quantile_axis"]] = len(levels)
    if where == "inputs":  # the same tensor offered as a second input under another name
        extra = copy.deepcopy(out)
        extra["name"] = "quantile_context"
        doc["inputs"].append(extra)
        doc["outputs"][0]["quantiles"] = [0.1, 0.5, 0.9]
        doc["outputs"][0]["shape"][doc["outputs"][0]["quantile_axis"]] = 3
    return doc


@pytest.mark.req("FR-011-46")
@pytest.mark.parametrize(
    "levels",
    [[0.1, 0.5, 0.9], [0.01, 0.99], [0.5], [0.05, 0.25, 0.5, 0.75, 0.95], [1e-9, 1.0 - 1e-9]],
    ids=["three", "tails", "single", "five", "extreme-but-inside"],
)
def test_strictly_increasing_levels_inside_zero_one_are_accepted(levels: list[float]) -> None:
    doc = load_surrogate_io(with_levels(levels))
    assert doc["outputs"][0]["quantiles"] == levels


@pytest.mark.req("FR-011-46")
@pytest.mark.parametrize(
    "levels",
    [
        [0.1, 0.5, 0.5],
        [0.5, 0.1],
        [0.0, 0.5],
        [0.5, 1.0],
        [-0.1, 0.5],
        [0.2, NAN],
        [0.1, 0.9, 0.5],
        [0.9, 0.7, 0.5, 0.3, 0.1],
        [0.5, 0.5],
        [1.5],
        [0.3, 0.3, 0.3],
    ],
    ids=[
        "repeated-last",
        "decreasing",
        "zero",
        "one",
        "negative",
        "nan",
        "unsorted",
        "descending",
        "pair-equal",
        "above-one",
        "triple-equal",
    ],
)
def test_levels_that_are_not_strictly_increasing_inside_zero_one_are_rejected_naming_the_field(
    levels: list[float],
) -> None:
    with pytest.raises(SurrogateIoError, match="quantiles") as info:
        load_surrogate_io(with_levels(levels))
    assert info.value.error_class == "surrogate-io-invalid"


@pytest.mark.req("FR-011-46")
@pytest.mark.parametrize("levels", [[0.1, 0.5, 0.5], [0.5, 0.1], [0.0, 0.5]])
def test_a_bad_level_list_on_an_input_tensor_is_rejected_too(levels: list[float]) -> None:
    with pytest.raises(SurrogateIoError, match="inputs") as info:
        load_surrogate_io(with_levels(levels, where="inputs"))
    assert info.value.error_class == "surrogate-io-invalid"
    assert "quantiles" in str(info.value)


@pytest.mark.req("FR-011-46")
def test_the_unmodified_spec_example_loads_from_a_dict_and_from_a_path() -> None:
    assert load_surrogate_io(copy.deepcopy(FORECASTER))["model_id"] == "tcn-c1"
    assert (
        load_surrogate_io(EX / "surrogate-io.valid-forecaster.json")["outputs"][0]["quantiles"]
        == FORECASTER["outputs"][0]["quantiles"]
    )
    assert load_surrogate_io(str(EX / "surrogate-io.valid-forecaster.json"))["engine"] == "forecasters"


@pytest.mark.req("FR-011-46")
@pytest.mark.parametrize("text", ["", "{", "[]", "null", "\x00"], ids=["empty", "open", "list", "null", "binary"])
def test_a_malformed_file_is_a_surrogate_io_error_not_a_crash(tmp_path: Path, text: str) -> None:
    path = tmp_path / "io.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SurrogateIoError) as info:
        load_surrogate_io(path)
    assert info.value.error_class == "surrogate-io-invalid"


@pytest.mark.req("FR-011-46")
def test_a_missing_file_is_a_surrogate_io_error(tmp_path: Path) -> None:
    with pytest.raises(SurrogateIoError):
        load_surrogate_io(tmp_path / "absent.json")


@pytest.mark.req("FR-011-46")
def test_the_loader_does_not_mutate_its_argument() -> None:
    doc = with_levels([0.1, 0.5, 0.9])
    before = copy.deepcopy(doc)
    load_surrogate_io(doc)
    assert doc == before
