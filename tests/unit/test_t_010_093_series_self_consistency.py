"""T-010-093: displacement-series self-consistency (array lengths, n_samples, t_0 < t_f).

Requirement: FR-010-44 ("If a displacement series has arrays whose lengths differ from each other or from `n_samples`,
or
`t_0` not before `t_f`, then the series loader shall reject it with error class `series-inconsistent` naming the
field").
Spec: specs/010-slope/spec.md section 3.4 (G5 hostile-input classes); plan.md row FR-010-44.

Expected API (module `pitstudio.slope.series`, standard library only):
- `InvalidSeriesError(ValueError)`: `error_class == "series-inconsistent"`, `field` (JSON pointer of the offending
  field).
- `parse_series(document) -> Series` and `load_series(path) -> Series`: accept every kind of DC-010-02 (synthetic-event,
  real-event, radar-pixel; a radar-map has no arrays of samples) and raise InvalidSeriesError for an inconsistent one.
  A document
  that is invalid for another reason (unknown kind, a schema violation) raises ValueError.
  Checked: `t_h`, `los_displacement_mm` (and `measured_los_displacement_mm`, `wrap_flags` of a radar pixel) have one
  length
  and, where `sampling.n_samples` exists, that length; `t_0_h < t_f_h` where both exist.

Oracle: hand calculation on the contract examples of the spec (`specs/010-slope/contracts/examples/*.valid*.json`): one
element removed or added, n_samples changed, t_0 set equal to or above t_f; the valid documents are accepted.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio.slope import series  # noqa: E402

EXAMPLES = ROOT / "specs" / "010-slope" / "contracts" / "examples"


def _doc(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def _mutated(name: str, fn) -> dict:
    doc = copy.deepcopy(_doc(name))
    fn(doc)
    return doc


SYN, REAL, PIX = (
    "displacement-series.valid.json",
    "displacement-series.valid-real.json",
    "displacement-series.valid-radar-pixel.json",
)

CASES = [
    ("syn-los-short", SYN, lambda d: d["los_displacement_mm"].pop(), ("/los_displacement_mm", "/t_h")),
    ("syn-t-long", SYN, lambda d: d["t_h"].append(999.0), ("/t_h", "/los_displacement_mm")),
    ("syn-n-samples", SYN, lambda d: d["sampling"].update(n_samples=65), "/sampling/n_samples"),
    (
        "syn-both-arrays-differ-from-n",
        SYN,
        lambda d: (d["t_h"].pop(), d["los_displacement_mm"].pop()),
        "/sampling/n_samples",
    ),
    ("syn-t0-equals-tf", SYN, lambda d: d.update(t_0_h=240.0), "/t_0_h"),
    ("syn-t0-after-tf", SYN, lambda d: d.update(t_0_h=300.0), "/t_0_h"),
    ("real-los-short", REAL, lambda d: d["los_displacement_mm"].pop(), ("/los_displacement_mm", "/t_h")),
    ("real-t-long", REAL, lambda d: d["t_h"].append(400.0), ("/t_h", "/los_displacement_mm")),
    ("real-n-samples", REAL, lambda d: d["sampling"].update(n_samples=9), "/sampling/n_samples"),
    ("real-t0-equals-tf", REAL, lambda d: d.update(t_0_h=410.0), "/t_0_h"),
    ("pixel-wrap-short", PIX, lambda d: d["wrap_flags"].pop(), ("/wrap_flags", "/t_h", "/los_displacement_mm")),
    (
        "pixel-measured-long",
        PIX,
        lambda d: d["measured_los_displacement_mm"].append(2.0),
        ("/measured_los_displacement_mm", "/t_h", "/los_displacement_mm"),
    ),
    ("pixel-los-short", PIX, lambda d: d["los_displacement_mm"].pop(), ("/los_displacement_mm", "/t_h")),
]


@pytest.mark.req("FR-010-44")
@pytest.mark.parametrize(("name", "base", "mutate", "field"), CASES, ids=[c[0] for c in CASES])
def test_an_inconsistent_series_is_rejected_with_error_class_series_inconsistent_naming_the_field(
    name, base, mutate, field
) -> None:
    doc = _mutated(base, mutate)
    with pytest.raises(series.InvalidSeriesError) as exc:
        series.parse_series(doc)
    assert exc.value.error_class == "series-inconsistent"
    fields = (field,) if isinstance(field, str) else field  # for two arrays that differ either may be named
    assert any(exc.value.field.startswith(f) for f in fields), (name, exc.value.field)
    assert exc.value.field.rsplit("/", 1)[-1] in str(exc.value)
    assert isinstance(exc.value, ValueError)


@pytest.mark.req("FR-010-44")
@pytest.mark.parametrize("name", [SYN, REAL, PIX])
def test_the_valid_examples_are_accepted(name) -> None:
    assert series.parse_series(_doc(name)) is not None


@pytest.mark.req("FR-010-44")
def test_the_hand_case_of_the_plan_lengths_3_and_4_with_n_samples_3_and_t0_equal_tf() -> None:
    doc = _doc(REAL)
    doc["t_h"], doc["los_displacement_mm"] = [0.0, 1.0, 2.0], [0.0, 1.0, 2.0, 3.0]
    doc["sampling"] = {"n_samples": 3, "interval_h": 1.0, "regular": True}
    with pytest.raises(series.InvalidSeriesError) as exc:
        series.parse_series(doc)
    assert exc.value.error_class == "series-inconsistent"
    doc["los_displacement_mm"] = [0.0, 1.0, 2.0]
    doc["t_0_h"] = doc["t_f_h"]
    with pytest.raises(series.InvalidSeriesError) as exc:
        series.parse_series(doc)
    assert exc.value.field.startswith("/t_0_h")


@pytest.mark.req("FR-010-44")
def test_the_loader_reads_a_file_and_other_invalid_documents_raise_value_error(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_doc(SYN)), encoding="utf-8")
    assert series.load_series(good) is not None
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_mutated(SYN, lambda d: d["los_displacement_mm"].pop())), encoding="utf-8")
    with pytest.raises(series.InvalidSeriesError):
        series.load_series(bad)
    for payload in ('{"kind": "unknown"}', "[]", "", '{"kind": "synthetic-event"'):
        path = tmp_path / "x.json"
        path.write_text(payload, encoding="utf-8")
        with pytest.raises(ValueError, match=r"."):
            series.load_series(path)
