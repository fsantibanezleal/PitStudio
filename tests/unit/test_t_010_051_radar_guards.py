"""T-010-051: hostile radar configurations are rejected before anything is projected.

Requirement: FR-010-37 ("If the radar position is within 1e-6 m of a pixel, lambda or Delta t_scan is <= 0 or
non-finite, the
pixel set is empty or larger than 10^6, or a facet normal has zero length, then the builder shall raise
`InvalidRadarConfigError` before projecting").
Spec: specs/010-slope/spec.md section 3.4; plan.md row FR-010-37 ("invalid configurations written in the test").

Expected API (module `pitstudio.slope.radar`, see T-010-050): `InvalidRadarConfigError(ValueError)` with `.field`
naming the input
(e.g. "radar/wavelength_mm", "radar/scan_interval_min", "pixels", "pixels/0/position_m", "dip_vectors/0");
`build_radar_series(..., sink=None)` validates the whole configuration first (the `len` of `pixels` is read before the
pixels are
iterated, so a huge pixel set is rejected without touching it) and calls `sink(PixelSeries)` per finished pixel;
`wall_displacement_field(...)` raises for a dip vector of zero length (or non-finite). `project_los` is never called
for a
rejected configuration.

Oracle: one case per class of the spec written in the test; valid controls at the limits (a radar 2e-6 m from a pixel, a
wavelength of 1 mm above the guard of FR-010-42) prove each mutation, not the baseline, is rejected.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pitstudio.slope import radar

T = 0.1 * np.arange(6)
DISP = np.column_stack([0.05 * np.arange(6), np.zeros(6), np.zeros(6)])


def _pixel(pid=1, x=100.0):
    return {"pixel_id": pid, "position_m": [x, 0.0, 0.0], "displacement_mm": DISP.copy()}


def _radar(**kw):
    return {"position_m": [0.0, 0.0, 0.0], "wavelength_mm": 17.4, "scan_interval_min": 6.0, **kw}


def _build(**kw):
    args = {
        "event_id": "voight-test-snr-obs-000001",
        "t_h": T,
        "radar": _radar(),
        "pixels": [_pixel()],
        "snr": None,
        "run_seed": 1,
    }
    args.update(kw)
    produced: list = []
    return radar.build_radar_series(sink=produced.append, **args), produced


class _HugeSet:
    """A pixel set of 1,000,001 entries that must not be iterated."""

    def __len__(self) -> int:
        return 1_000_001

    def __iter__(self):
        raise AssertionError("the pixel set was iterated before its size was checked")


class _Spy:
    def __init__(self, monkeypatch) -> None:
        self.calls = 0
        original = radar.project_los

        def spy(*a, **k):
            self.calls += 1
            return original(*a, **k)

        monkeypatch.setattr(radar, "project_los", spy)


@pytest.mark.req("FR-010-37")
@pytest.mark.parametrize(
    ("name", "kwargs", "field"),
    [
        ("radar-on-the-pixel", {"pixels": [_pixel(x=0.0)]}, "pixels/0"),
        ("radar-5e-7-m-from-the-pixel", {"pixels": [{**_pixel(), "position_m": [5e-7, 0.0, 0.0]}]}, "pixels/0"),
        ("radar-on-the-second-pixel", {"pixels": [_pixel(1), _pixel(2, x=0.0)]}, "pixels/1"),
        ("wavelength-zero", {"radar": _radar(wavelength_mm=0.0)}, "radar/wavelength_mm"),
        ("wavelength-negative", {"radar": _radar(wavelength_mm=-17.4)}, "radar/wavelength_mm"),
        ("wavelength-nan", {"radar": _radar(wavelength_mm=float("nan"))}, "radar/wavelength_mm"),
        ("wavelength-inf", {"radar": _radar(wavelength_mm=float("inf"))}, "radar/wavelength_mm"),
        ("scan-interval-zero", {"radar": _radar(scan_interval_min=0.0)}, "radar/scan_interval_min"),
        ("scan-interval-negative", {"radar": _radar(scan_interval_min=-6.0)}, "radar/scan_interval_min"),
        ("scan-interval-nan", {"radar": _radar(scan_interval_min=float("nan"))}, "radar/scan_interval_min"),
        ("scan-interval-inf", {"radar": _radar(scan_interval_min=float("inf"))}, "radar/scan_interval_min"),
        ("pixel-set-empty", {"pixels": []}, "pixels"),
        ("pixel-set-too-large", {"pixels": _HugeSet()}, "pixels"),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_hostile_configuration_raises_before_projecting(monkeypatch, name, kwargs, field) -> None:
    spy = _Spy(monkeypatch)
    sink: list = []
    args = {
        "event_id": "voight-test-snr-obs-000001",
        "t_h": T,
        "radar": _radar(),
        "pixels": [_pixel()],
        "snr": None,
        "run_seed": 1,
    }
    args.update(kwargs)
    with pytest.raises(radar.InvalidRadarConfigError) as exc:
        radar.build_radar_series(sink=sink.append, **args)
    assert exc.value.field.startswith(field), (name, exc.value.field)
    assert isinstance(exc.value, ValueError)
    assert spy.calls == 0
    assert sink == []


@pytest.mark.req("FR-010-37")
@pytest.mark.parametrize(
    "dip",
    [
        [[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
        [[1.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
        [[float("nan"), 0.0, 1.0], [0.0, 0.0, 1.0]],
    ],
)
def test_a_facet_normal_of_zero_length_is_rejected(dip) -> None:
    pix = np.array([[0.0, 0.0, 0.0], [30.0, 0.0, 0.0]])
    with pytest.raises(radar.InvalidRadarConfigError) as exc:
        radar.wall_displacement_field(np.array([0.0, 1.0]), pix, np.zeros(3), np.array(dip))
    assert exc.value.field.startswith("dip_vectors/")


@pytest.mark.req("FR-010-37")
def test_the_limits_that_are_valid_are_accepted() -> None:
    out, produced = _build(
        pixels=[{**_pixel(), "position_m": [2e-6, 0.0, 0.0]}]
    )  # 2e-6 m from the radar: above the 1e-6 guard
    assert len(out) == 1
    assert len(produced) == 1
    out, _ = _build(radar=_radar(wavelength_mm=1.5, scan_interval_min=1e-3))
    assert len(out) == 1
    out, _ = _build(pixels=[_pixel(i, x=50.0 + i) for i in range(1, 4)])
    assert set(out) == {1, 2, 3}
