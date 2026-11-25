"""T-011-093 - FR-011-47: tensor names and channel names of a surrogate I/O document must be unique.

Oracles (independent of the code under test; plan 011 test strategy FR-011-47): hand calculation from the spec text
    on the spec's
own examples: two tensors named `u` are rejected, distinct names are accepted. Base documents: the GNS example
(`surrogate-io.valid.json`, six inputs and one output) and the forecaster example
    (`surrogate-io.valid-forecaster.json`, one
input with two channels). Tensor names must be unique across inputs and outputs together (an ONNX graph cannot have
    an input
and an output of one name); channel names must be unique inside a tensor.

Expected public API (module `pitstudio.surrogate_io`, see T-011-092; the same loader serves the generated types'
    consumers):

    load_surrogate_io(source) -> dict      raises `SurrogateIoError` (error_class "surrogate-io-invalid") whose
        message names the
        repeated name, for a duplicate tensor name (inside inputs, inside outputs, or between an input and an
            output) and for a
        duplicate channel name inside one tensor.
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
GNS = json.loads((EX / "surrogate-io.valid.json").read_text(encoding="utf-8"))
FORECASTER = json.loads((EX / "surrogate-io.valid-forecaster.json").read_text(encoding="utf-8"))
FNO = json.loads((EX / "surrogate-io.valid-fno.json").read_text(encoding="utf-8"))


@pytest.mark.req("FR-011-47")
@pytest.mark.parametrize("doc", [GNS, FORECASTER, FNO], ids=["gns", "forecaster", "fno"])
def test_the_spec_examples_have_unique_names_and_load(doc: dict) -> None:
    assert load_surrogate_io(copy.deepcopy(doc))["model_id"] == doc["model_id"]


@pytest.mark.req("FR-011-47")
def test_two_inputs_with_the_same_name_are_rejected_naming_it() -> None:
    doc = copy.deepcopy(GNS)
    doc["inputs"][1]["name"] = doc["inputs"][0]["name"]  # two tensors named `positions`
    with pytest.raises(SurrogateIoError, match="positions") as info:
        load_surrogate_io(doc)
    assert info.value.error_class == "surrogate-io-invalid"


@pytest.mark.req("FR-011-47")
def test_two_tensors_named_u_are_rejected_and_distinct_names_are_accepted() -> None:
    doc = copy.deepcopy(GNS)
    doc["inputs"][0]["name"] = "u"
    doc["inputs"][1]["name"] = "u"
    with pytest.raises(SurrogateIoError, match=r"\bu\b"):
        load_surrogate_io(doc)
    doc["inputs"][1]["name"] = "v"
    assert [t["name"] for t in load_surrogate_io(doc)["inputs"][:2]] == ["u", "v"]


@pytest.mark.req("FR-011-47")
def test_an_output_named_like_an_input_is_rejected() -> None:
    doc = copy.deepcopy(GNS)
    doc["outputs"][0]["name"] = "bounds"
    with pytest.raises(SurrogateIoError, match="bounds") as info:
        load_surrogate_io(doc)
    assert info.value.error_class == "surrogate-io-invalid"


@pytest.mark.req("FR-011-47")
def test_two_outputs_with_the_same_name_are_rejected() -> None:
    doc = copy.deepcopy(GNS)
    second = copy.deepcopy(doc["outputs"][0])
    doc["outputs"].append(second)
    with pytest.raises(SurrogateIoError, match="acceleration"):
        load_surrogate_io(doc)


@pytest.mark.req("FR-011-47")
def test_two_channels_with_the_same_name_in_one_tensor_are_rejected_naming_it() -> None:
    doc = copy.deepcopy(FORECASTER)
    doc["inputs"][0]["channels"][1]["name"] = doc["inputs"][0]["channels"][0]["name"]  # inverse_velocity twice
    with pytest.raises(SurrogateIoError, match="inverse_velocity") as info:
        load_surrogate_io(doc)
    assert info.value.error_class == "surrogate-io-invalid"


@pytest.mark.req("FR-011-47")
def test_the_same_channel_name_in_two_different_tensors_is_allowed() -> None:
    doc = copy.deepcopy(FNO)
    # the FNO example's input channel `bed_elevation` may also name a channel of another tensor: channel names are
    #   per tensor
    extra = copy.deepcopy(doc["inputs"][0])
    extra["name"] = "fields_copy"
    doc["inputs"].append(extra)
    assert len(load_surrogate_io(doc)["inputs"]) == 2


@pytest.mark.req("FR-011-47")
def test_names_are_compared_exactly_so_a_name_differing_by_case_is_a_distinct_name() -> None:
    doc = copy.deepcopy(GNS)
    doc["inputs"][1]["name"] = "Positions"  # the schema's name pattern admits upper case; ONNX names are case-sensitive
    assert [t["name"] for t in load_surrogate_io(doc)["inputs"][:2]] == ["positions", "Positions"]


@pytest.mark.req("FR-011-47")
@pytest.mark.parametrize("name", ["pos itions", "positións", ""], ids=["space", "unicode", "empty"])
def test_malformed_tensor_names_are_rejected_with_the_same_error_class(name: str) -> None:
    doc = copy.deepcopy(GNS)
    doc["inputs"][1]["name"] = name
    with pytest.raises(SurrogateIoError) as info:
        load_surrogate_io(doc)
    assert info.value.error_class == "surrogate-io-invalid"
