# ruff: noqa: E501
"""T-009-072 - FR-009-39: reduced-precision variants that fail the mAP50 change or the robustness criterion are rejected and not shipped.

Oracles (independent of the code under test; plan 009 test strategy row FR-009-39):
- hand calculation: a change of mAP50 of 1.2 percentage points (0.800 -> 0.788) is rejected; 0.95 pp (0.800 -> 0.7905) is accepted; a gain of 1.2 pp (0.788 -> 0.800 as variant) is rejected too ("changes ... by more
  than 1 pp", an absolute change in either direction; the exact boundary 1.00 pp is not tested because 0.01 is not representable in binary floating point);
- hand calculation: with a clean score of 1.0, a score of 0.89 under dust at severity 2 is a relative drop of 100 (1.0 - 0.89) / 1.0 = 11 % > 10 and is rejected (SC-009-03); 0.91 is 9 % and passes; severities 3-5
  do not count (SC-009-03 covers s = 1 and 2);
- the rejection text carries the numbers: the reason of the rejected-input row of DC-009-05 (`#/$defs/rejected_input`, reason <= 300 characters) contains "1.2" and "pp" for the first case and "11", "dust" and "2" for the second;
- a rejected variant does not ship: it is in neither `onnx_files` nor `baked_only` of the shipping plan and is listed under `rejected`.

Expected public API (module `pitstudio_pipeline.perception.export_hooks`, package under `pipeline/src/`; extends tests/contract/test_t_009_071_live_lane.py):

    VariantVerdict                   frozen dataclass: model: str, precision: str, status: "accepted" | "rejected", reasons: tuple[str, ...] (each starts with "delta-map50" or "sc-009-03"),
                                     numbers: dict[str, float] (always "delta_pp" = 100 * |map50_variant - map50_fp32|; "worst_delta_rel_pct" = the largest delta_rel over the SC-009-03 points when
                                     there are any)
    judge_variant(*, model: str, precision: str, map50_fp32: float, map50_variant: float, corruption_points: Sequence[Mapping]) -> VariantVerdict
        precision must be "fp16" or "int8" and model "d-fine-n" or "d-fine-s" (ValueError naming the argument otherwise); scores finite and in [0, 1] ("map50_fp32" / "map50_variant");
        corruption_points are rows {"corruption": "dust" | "night" | "rain", "severity": 1..5, "m_clean": float, "m_corrupted": float} of the variant ("corruption_points": ValueError for a malformed row).
        Rejected when delta_pp > 1.0 ("delta-map50"), or when for some corruption in {dust, night, rain} and severity in {1, 2} the relative drop 100 (m_clean - m_corrupted) / m_clean exceeds 10 ("sc-009-03");
        both reasons are listed when both fail. A variant whose SC-009-03 points are missing is judged on delta_pp alone.
    rejected_input_row(verdict: VariantVerdict, path: str) -> dict
        {"input": path, "reason": text of at most 300 characters carrying the numbers}: valid for #/$defs/rejected_input; ValueError for an accepted verdict or a path that is not a safe relative path.
    shipping_plan(variants: Sequence[Mapping]) -> dict       (tests/contract/test_t_009_071_live_lane.py) with the optional variant key "accepted": bool (default True): a variant with accepted False is not
                                     shipped at all (no onnx file, no baked entry) and its "<model>-<precision>" name is listed in the result's "rejected" list (sorted; [] when none).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.perception import export_hooks as hooks  # noqa: E402


def _points(**override: float) -> list[dict]:
    """The 6 SC-009-03 points (dust, night, rain x severity 1, 2) with a clean score of 1.0 and a 5 % drop, optionally overridden per (corruption, severity) key like dust_2=0.89."""
    return [
        {"corruption": c, "severity": s, "m_clean": 1.0, "m_corrupted": override.get(f"{c}_{s}", 0.95)}
        for c in ("dust", "night", "rain")
        for s in (1, 2)
    ]


def _judge(**kw) -> hooks.VariantVerdict:
    args = {
        "model": "d-fine-s",
        "precision": "int8",
        "map50_fp32": 0.800,
        "map50_variant": 0.7995,
        "corruption_points": _points(),
    } | kw
    return hooks.judge_variant(**args)


# ---------------------------------------------------------------- the mAP50 change


@pytest.mark.req("FR-009-39")
def test_a_variant_within_one_point_of_fp32_and_robust_is_accepted() -> None:
    v = _judge()
    assert v.status == "accepted"
    assert v.reasons == ()
    assert v.numbers["delta_pp"] == pytest.approx(0.05, abs=1e-9)
    assert v.numbers["worst_delta_rel_pct"] == pytest.approx(5.0, abs=1e-9)
    assert (v.model, v.precision) == ("d-fine-s", "int8")


@pytest.mark.req("FR-009-39")
@pytest.mark.parametrize(
    ("variant", "delta"), [(0.788, 1.2), (0.812, 1.2), (0.7895, 1.05), (0.8105, 1.05), (0.7, 10.0)]
)
def test_a_change_of_more_than_one_point_in_either_direction_is_rejected(variant: float, delta: float) -> None:
    v = _judge(map50_variant=variant)
    assert v.status == "rejected"
    assert len(v.reasons) == 1
    assert v.reasons[0].startswith("delta-map50")
    assert v.numbers["delta_pp"] == pytest.approx(delta, abs=1e-9)


@pytest.mark.req("FR-009-39")
@pytest.mark.parametrize("variant", [0.7905, 0.8095, 0.8, 0.8001])
def test_a_change_below_one_point_is_accepted(variant: float) -> None:
    assert _judge(map50_variant=variant).status == "accepted"


# ---------------------------------------------------------------- SC-009-03 on the variant's own score


@pytest.mark.req("FR-009-39")
def test_a_relative_drop_of_eleven_percent_at_severity_two_is_rejected() -> None:
    v = _judge(corruption_points=_points(dust_2=0.89))
    assert v.status == "rejected"
    assert len(v.reasons) == 1
    assert v.reasons[0].startswith("sc-009-03")
    assert v.numbers["worst_delta_rel_pct"] == pytest.approx(11.0, abs=1e-9)


@pytest.mark.req("FR-009-39")
@pytest.mark.parametrize("key", ["dust_1", "dust_2", "night_1", "night_2", "rain_1", "rain_2"])
def test_every_corruption_and_both_severities_count(key: str) -> None:
    assert _judge(corruption_points=_points(**{key: 0.89})).status == "rejected"
    assert _judge(corruption_points=_points(**{key: 0.91})).status == "accepted"


@pytest.mark.req("FR-009-39")
def test_severities_three_to_five_are_outside_the_criterion_and_missing_points_are_not_judged() -> None:
    far = [
        *_points(),
        {"corruption": "dust", "severity": 4, "m_clean": 1.0, "m_corrupted": 0.2},
        {"corruption": "rain", "severity": 5, "m_clean": 1.0, "m_corrupted": 0.0},
    ]
    assert _judge(corruption_points=far).status == "accepted"
    assert _judge(corruption_points=[]).status == "accepted"


@pytest.mark.req("FR-009-39")
def test_both_failures_give_both_reasons() -> None:
    v = _judge(map50_variant=0.788, corruption_points=_points(rain_1=0.80))
    assert v.status == "rejected"
    assert {r.split(":")[0].split(" ")[0] for r in v.reasons} == {"delta-map50", "sc-009-03"}
    assert v.numbers["delta_pp"] == pytest.approx(1.2, abs=1e-9)
    assert v.numbers["worst_delta_rel_pct"] == pytest.approx(20.0, abs=1e-9)


@pytest.mark.req("FR-009-39")
@pytest.mark.parametrize(
    ("kwargs", "arg"),
    [
        ({"precision": "fp32"}, "precision"),
        ({"precision": "fp64"}, "precision"),
        ({"model": "rf-detr-seg-n"}, "model"),
        ({"model": "yolo"}, "model"),
        ({"map50_fp32": float("nan")}, "map50_fp32"),
        ({"map50_fp32": 1.5}, "map50_fp32"),
        ({"map50_variant": -0.1}, "map50_variant"),
        ({"map50_variant": float("inf")}, "map50_variant"),
        (
            {"corruption_points": [{"corruption": "fog", "severity": 1, "m_clean": 1.0, "m_corrupted": 0.9}]},
            "corruption_points",
        ),
        (
            {"corruption_points": [{"corruption": "dust", "severity": 1, "m_clean": 0.0, "m_corrupted": 0.0}]},
            "corruption_points",
        ),
        (
            {"corruption_points": [{"corruption": "dust", "severity": 1, "m_clean": 1.0, "m_corrupted": float("nan")}]},
            "corruption_points",
        ),
        ({"corruption_points": [None]}, "corruption_points"),
        ({"corruption_points": "points"}, "corruption_points"),
    ],
)
def test_hostile_inputs_are_rejected_naming_the_argument(kwargs: dict, arg: str) -> None:
    with pytest.raises(ValueError, match=arg):
        _judge(**kwargs)


# ---------------------------------------------------------------- the report row and the shipping plan


def _rejected_input_validator():
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "contracts" / "detection-eval.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator({"$ref": "#/$defs/rejected_input", "$defs": schema["$defs"]})


@pytest.mark.req("FR-009-39")
def test_the_rejected_row_names_the_path_and_carries_the_numbers_of_a_map_change() -> None:
    row = hooks.rejected_input_row(_judge(map50_variant=0.788), "models/d-fine-s-int8.onnx")
    assert row["input"] == "models/d-fine-s-int8.onnx"
    assert "1.2" in row["reason"]
    assert "pp" in row["reason"]
    assert len(row["reason"]) <= 300
    assert list(_rejected_input_validator().iter_errors(row)) == []


@pytest.mark.req("FR-009-39")
def test_the_rejected_row_names_corruption_severity_and_the_drop_of_a_robustness_failure() -> None:
    row = hooks.rejected_input_row(_judge(corruption_points=_points(dust_2=0.89)), "models/d-fine-s-int8.onnx")
    for word in ("11", "dust", "2"):
        assert word in row["reason"]
    assert list(_rejected_input_validator().iter_errors(row)) == []


@pytest.mark.req("FR-009-39")
@pytest.mark.parametrize("path", ["", "/abs/x.onnx", "../x.onnx", "C:/x.onnx", "a\\b.onnx"])
def test_the_rejected_row_refuses_an_unsafe_path_and_an_accepted_verdict(path: str) -> None:
    with pytest.raises(ValueError, match="path"):
        hooks.rejected_input_row(_judge(map50_variant=0.788), path)
    with pytest.raises(ValueError, match="verdict"):
        hooks.rejected_input_row(_judge(), "models/ok.onnx")


def _variants(accepted_int8: bool) -> list[dict]:
    t = {"t1": {"median_ms": 100.0, "images": 50, "warmup_runs": 5}, "t2": {"run_s": 0.2}}
    out = []
    for m in ("d-fine-n", "d-fine-s", "rf-detr-seg-n"):
        for p in ("fp32", "fp16", "int8"):
            v = {"model": m, "precision": p, "size_bytes": 9_000_000, "timing": t}
            if (m, p) == ("d-fine-s", "int8"):
                v["accepted"] = accepted_int8
            out.append(v)
    return out


@pytest.mark.req("FR-009-39")
def test_a_rejected_variant_is_not_shipped_and_is_listed_as_rejected() -> None:
    plan = hooks.shipping_plan(_variants(accepted_int8=False))
    assert plan["onnx_files"] == ["d-fine-n-fp16.onnx"]
    assert "d-fine-s-int8" not in plan["baked_only"]
    assert plan["rejected"] == ["d-fine-s-int8"]
    assert (
        len(plan["baked_only"]) == 7
    )  # the other 7 non-live variants of 9, the live D-FINE-N fp16 ships as ONNX, the rejected one is gone


@pytest.mark.req("FR-009-39")
def test_with_every_variant_accepted_nothing_is_rejected() -> None:
    plan = hooks.shipping_plan(_variants(accepted_int8=True))
    assert plan["rejected"] == []
    assert plan["onnx_files"] == ["d-fine-n-fp16.onnx", "d-fine-s-int8.onnx"]
