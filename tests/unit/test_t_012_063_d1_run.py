"""T-012-063: the D1 run: design grids, TRTR charts and the results summary of the recipe parameters (unit, contract).

Requirements: FR-012-41, FR-012-29, FR-012-24, FR-012-38, DC-012-05, DC-020-05.

The recipe `studio/recipes/cases/d1.yaml` is the parameter source. The per-fold report is built with a stub U-Net that
returns the one-hot three-class truth (so the IoU and instance counts are known), over synthetic block labels; no real
image is read.

Oracles:
- hand calculations: powder factor K = Q / (B S H) with Q = rho_e pi d^2 L / 4 at the reference cell; the 30 CFR 816.67
  limits 1.25, 1.00 and 0.75 in/s (31.75, 25.4 and 19.05 mm/s) for D <= 300 ft, up to 5,000 ft and beyond;
- the DC-012-05 schema and the chart-series schema (`jsonschema`, `chartkit.problems`);
- the grids equal `build_design_grid` (tested in T-012-060) and the KPI units of cases.yaml (P80 in mm, PPV in mm/s).
"""
# ruff: noqa: PT018, RUF046

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml
from jsonschema import Draft202012Validator
from pitstudio_pipeline import chartkit
from pitstudio_pipeline.fragmentation import d1_run, fold_report
from pitstudio_pipeline.fragmentation.unet import IMAGENET_MEAN, IMAGENET_STD

ROOT = Path(__file__).resolve().parents[2]

# the revision of the minephys pin in pyproject.toml, so the test follows a pin bump instead of one hard-coded hash
PINNED_MINEPHYS = re.search(
    r'minephys = \{ git = "[^"]+", rev = "([0-9a-f]{40})" \}', (ROOT / "pyproject.toml").read_text(encoding="utf-8")
).group(1)[:7]
RECIPE = yaml.safe_load((ROOT / "studio/recipes/cases/d1.yaml").read_text(encoding="utf-8"))
STAGE = RECIPE["stages"][0]
GRID_SCHEMA = json.loads((ROOT / "contracts/d1-design-grid.schema.json").read_text(encoding="utf-8"))
INCH_MM = 25.4


def _blocks(n_side: int, size: int, gap: int = 4) -> np.ndarray:
    label = np.zeros((512, 512), dtype=np.uint8)
    k = 1
    for i in range(n_side):
        for j in range(n_side):
            y, x = 8 + i * (size + gap), 8 + j * (size + gap)
            label[y : y + size, x : x + size] = k
            k += 1
    return label


def _three_class(label: np.ndarray) -> np.ndarray:
    padded = np.pad(label, 1)
    differs = np.zeros(label.shape, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                differs |= padded[1 + dy : 1 + dy + 512, 1 + dx : 1 + dx + 512] != label
    out = np.zeros(label.shape, dtype=np.uint8)
    out[label > 0] = 1
    out[(label > 0) & differs] = 2
    return out


class _Oracle(torch.nn.Module):
    def __init__(self, labels: np.ndarray) -> None:
        super().__init__()
        self.targets = [_three_class(lab) for lab in labels]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = []
        for sample in x:
            index = int(round(float(sample[0, 0, 0] * IMAGENET_STD[0] + IMAGENET_MEAN[0]) * 255.0))
            out.append(
                torch.nn.functional.one_hot(torch.from_numpy(self.targets[index]).long(), 3).permute(2, 0, 1).float()
                * 20.0
            )
        return torch.stack(out)


@pytest.fixture(scope="module")
def design() -> dict:
    return d1_run.design_outputs(STAGE["params"])


@pytest.fixture(scope="module")
def report(tmp_path_factory) -> dict:
    labels = np.stack([_blocks(3 + i % 3, 20 + 4 * (i % 2)) for i in range(6)])
    images = np.stack([np.full((512, 512, 3), i, dtype=np.uint8) for i in range(6)])
    run = tmp_path_factory.mktemp("run")
    for fold, files in enumerate(([1, 2, 3], [4, 5, 6])):
        d = run / f"fold{fold}"
        d.mkdir()
        (d / "result.json").write_text(
            json.dumps(
                {
                    "fold": fold,
                    "n_train": 3,
                    "n_val": 1,
                    "n_test": 3,
                    "test_fg_iou_mean": 1.0,
                    "test_fg_iou_per_file": {str(f): 1.0 for f in files},
                }
            ),
            encoding="utf-8",
        )
        (d / "metrics.jsonl").write_text(
            '{"epoch": 1, "loss": 1.0, "val_fg_iou": 0.9}\n{"epoch": 2, "loss": 0.8, "val_fg_iou": 0.95}\n',
            encoding="utf-8",
        )
    (run / "summary.json").write_text(
        json.dumps({"arm": "TRTR", "folds": [1.0, 1.0], "mean": 1.0, "std": 0.0, "min": 1.0}), encoding="utf-8"
    )
    return fold_report.build_report(run, images, labels, loader=lambda _p: _Oracle(labels))


@pytest.mark.req("FR-012-41")
def test_the_three_grids_validate_and_follow_the_recipe_axes(design) -> None:
    for name, doc in design["grids"].items():
        assert list(Draft202012Validator(GRID_SCHEMA).iter_errors(doc)) == [], name
        assert [a["input"] for a in doc["axes"]] == list(STAGE["params"][f"grid_{name}"])
        assert doc["kuzram_variant"] == "cunningham2005" and doc["case_id"] == "D1"
    assert len(design["grids"]["fragmentation"]["points"]) == 8 * 8 * 3


@pytest.mark.req("FR-012-41")
def test_the_design_charts_are_valid_and_carry_producer_and_label(design) -> None:
    ids = [c["id"] for c in design["charts"]]
    assert ids == ["d1-p80-map", "d1-oversize-map", "d1-powder-factor-map", "d1-ppv-curves", "d1-flyrock-curves"]
    for chart in design["charts"]:
        assert chartkit.problems(chart) == [], chart["id"]
        assert chart["producer"]["tool"] == "minephys" and f"+g{PINNED_MINEPHYS}" in chart["producer"]["version"]
        assert "UNVERIFIED" in chart["producer"]["label"] and "not validated" in chart["producer"]["label"]


@pytest.mark.req("FR-012-41")
def test_the_p80_map_cell_at_the_reference_design_is_the_grid_x80_in_mm(design) -> None:
    chart = next(c for c in design["charts"] if c["id"] == "d1-p80-map")
    r = chart["raster"]
    ref = STAGE["params"]["reference_design"]
    xs = STAGE["params"]["grid_fragmentation"]["burden_m"]
    ys = STAGE["params"]["grid_fragmentation"]["spacing_m"]
    col, row = (
        xs.index(ref["burden_m"]),
        len(ys) - 1 - ys.index(ref["spacing_m"]),
    )  # first row is the top (largest spacing)
    point = next(
        p
        for p in design["grids"]["fragmentation"]["points"]
        if p["inputs"] == {"burden_m": 6.0, "spacing_m": 7.0, "charge_length_m": 7.2}
    )
    assert r["values"][row * r["nx"] + col] == pytest.approx(point["x80_m"] * 1000.0, rel=1e-12)
    assert (r["nx"], r["ny"]) == (8, 8)
    assert (
        r["colour"]["unit"] == "mm"
        and r["colour"]["vmin"] <= min(r["values"])
        and r["colour"]["vmax"] >= max(r["values"])
    )
    assert chart["markers"][0]["x"] == 6.0 and chart["markers"][0]["y"] == 7.0
    assert design["reference"]["x80_m"] == point["x80_m"]


@pytest.mark.req("FR-012-41")
def test_the_powder_factor_map_equals_the_hand_calculation(design) -> None:
    chart = next(c for c in design["charts"] if c["id"] == "d1-powder-factor-map")
    f = STAGE["params"]["fixed_inputs"]
    q = f["explosive_density_kg_per_m3"] * math.pi / 4 * f["hole_diameter_m"] ** 2 * 7.2
    xs, ys = STAGE["params"]["grid_fragmentation"]["burden_m"], STAGE["params"]["grid_fragmentation"]["spacing_m"]
    r = chart["raster"]
    for ci, b in enumerate(xs):
        for ri, s in enumerate(reversed(ys)):
            assert r["values"][ri * r["nx"] + ci] == pytest.approx(q / (b * s * f["bench_height_m"]), rel=1e-12)


@pytest.mark.req("FR-012-41")
def test_the_ppv_chart_has_one_series_per_charge_and_the_regulatory_limit_in_mm_per_s(design) -> None:
    chart = next(c for c in design["charts"] if c["id"] == "d1-ppv-curves")
    charges = STAGE["params"]["grid_vibration"]["charge_per_delay_kg"]
    assert len(chart["series"]) == len(charges) + 1
    f = STAGE["params"]["fixed_inputs"]
    ref = next(s for s in chart["series"] if s["id"] == "charge-150-kg")
    d = STAGE["params"]["grid_vibration"]["distance_m"]
    assert ref["y"][d.index(300)] == pytest.approx(
        f["k_site_m_per_s"] * (300 / math.sqrt(150)) ** -f["beta"] * 1000.0, rel=1e-12
    )
    limit = next(s for s in chart["series"] if s["id"].startswith("limit"))
    for dist, y in zip(limit["x"], limit["y"], strict=True):
        feet = dist / 0.3048
        want = 1.25 if feet <= 300 else (1.0 if feet <= 5000 else 0.75)
        assert y == pytest.approx(want * INCH_MM, rel=1e-12), dist


@pytest.mark.req("FR-012-41")
def test_the_flyrock_chart_has_one_series_per_fragment_size_and_grows_with_the_speed(design) -> None:
    chart = next(c for c in design["charts"] if c["id"] == "d1-flyrock-curves")
    assert len(chart["series"]) == len(STAGE["params"]["grid_flyrock"]["fragment_diameter_m"])
    for s in chart["series"]:
        assert all(b > a for a, b in zip(s["y"], s["y"][1:], strict=False))


@pytest.mark.req("FR-012-29")
def test_the_fold_charts_are_valid_and_carry_the_size_basis_and_the_attribution(report) -> None:
    out = d1_run.fold_outputs(report)
    ids = [c["id"] for c in out["charts"]]
    assert ids == ["d1-fold-iou", "d1-psd-pooled", "d1-psd-per-fold", "d1-training-curves", "d1-fold-table"]
    for chart in out["charts"]:
        assert chartkit.problems(chart) == [], chart["id"]
        assert chart["producer"]["label"] == d1_run.TRTR_LABEL
        if chart["id"] != "d1-fold-iou":
            assert "Mendeley" in json.dumps(
                chart["caption"]
            )  # FR-012-38: attribution verbatim next to every derived metric
    psd = next(c for c in out["charts"] if c["id"] == "d1-psd-pooled")
    assert "px" in psd["x_axis"]["unit"] and "pixels" in psd["caption"]["en"] and "not recorded" in psd["caption"]["en"]
    assert [m["id"] for m in psd["markers"]] == ["gt-p50", "gt-p80", "unet-p50", "unet-p80"]
    bars = next(c for c in out["charts"] if c["id"] == "d1-fold-iou")
    assert [c["id"] for c in bars["categories"]] == ["fold-0", "fold-1"] and bars["series"][1]["y"] == [1.0, 1.0]
    table = next(c for c in out["charts"] if c["id"] == "d1-fold-table")
    assert table["table"]["rows"][-1][0] == "all folds" and len(table["table"]["rows"]) == 3


@pytest.mark.req("FR-012-38")
def test_no_published_value_is_an_array_or_an_image_and_the_summary_has_the_kpis_in_case_units(design, report) -> None:
    summary = d1_run.summary_document(design, report)
    head = {h["kpi"]: h for h in summary["headline"] if "kpi" in h}
    assert set(head) == {"p80", "oversize", "ppv", "flyrock_radius"}
    assert head["p80"]["unit"] == "mm" and head["ppv"]["unit"] == "mm/s"
    assert head["p80"]["value"] == pytest.approx(design["reference"]["x80_m"] * 1000.0, abs=5e-5)
    assert head["ppv"]["value"] == pytest.approx(design["reference"]["ppv_m_per_s"] * 1000.0, abs=5e-5)
    assert summary["extra"]["device"] == "cpu" and "pixels" in summary["extra"]["size_basis_image"]
    assert "UNVERIFIED" in summary["extra"]["iou_reproduction"]["cause"]
    json.dumps(summary, allow_nan=False)
