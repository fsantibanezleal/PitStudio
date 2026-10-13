"""T-011-021 - FR-011-16: the GNS speed report (measurements only, hardware and tier named).

Oracles (independent of the code under test; plan 011 test strategy FR-011-16: "contract of the speed block"): hand
    arithmetic on
injected step times. Steps per second is the reciprocal of the MEDIAN step time (the spec's NFR-011-02 uses the
    median of 100
steps), not of the mean:
  Python CPU   times (0.010, 0.020, 0.090) s  -> median 0.020 s -> 50 steps/s   (the mean 0.040 s would give 25)
  Python GPU   times (0.002, 0.002, 0.004) s  -> median 0.002 s -> 500 steps/s
  browser T1   times (0.030, 0.040, 0.050) s  -> median 0.040 s -> 25 steps/s
  browser T2   times (0.100, 0.120, 0.400) s  -> median 0.120 s -> 8.3333 steps/s
  solver       wall 0.5 s per step            -> 2 steps/s
The statement must be a measurement ("measured"), name every hardware and tier, carry each rate, and never use a
    comparative
claim ("faster", "better", "speed-up", ...).

Expected public API (module `pitstudio_pipeline.surrogates.gns.speed`, package under `pipeline/src/`):

    build_speed_report(*, geometry_id, particles, python_cpu, python_gpu, browser, solver) -> dict
        python_cpu: {"hardware": str, "step_times_s": [float, ...]}
        python_gpu: the same, or {"reason": str} when no GPU ran ("not run (no GPU)")
        browser: {"T1": {"hardware", "browser", "step_times_s"} | {"hardware", "browser", "reason"},  "T2": {...}}
            (tier keys T1 and T2)
        solver: {"hardware": str, "wall_s_per_step": float}
        Returns {"geometry_id", "particles",
                 "surrogate": {"python_cpu": {"hardware", "median_step_s", "steps_per_s"},
                               "python_gpu": {"hardware", "median_step_s", "steps_per_s"} | {"status": "not run",
                                   "reason": str},
                               "browser": {"T1": {"tier": "T1", "hardware", "browser", "median_step_s",
                                   "steps_per_s"} | {"tier", ..., "status": "not run", "reason"}, "T2": ...}},
                 "solver": {"hardware", "wall_s_per_step", "steps_per_s"},
                 "statement": str}
        Raises ValueError for an empty or non-finite or non-positive step-time list, a missing or empty hardware
            name, a tier key
        other than T1 and T2, a non-positive solver wall time, particles < 1, or an empty geometry id.
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.gns import speed  # noqa: E402

BASE = {
    "geometry_id": "g017",
    "particles": 2000,
    "python_cpu": {"hardware": "Test CPU 16c", "step_times_s": [0.010, 0.020, 0.090]},
    "python_gpu": {"hardware": "Test GPU 16 GiB", "step_times_s": [0.002, 0.002, 0.004]},
    "browser": {
        "T1": {"hardware": "Test GPU 16 GiB", "browser": "Chromium 141", "step_times_s": [0.030, 0.040, 0.050]},
        "T2": {"hardware": "Test iGPU", "browser": "Chromium 141", "step_times_s": [0.100, 0.120, 0.400]},
    },
    "solver": {"hardware": "Test GPU 16 GiB", "wall_s_per_step": 0.5},
}
FORBIDDEN = ["faster", "slower", "better", "worse", "speed-up", "speedup", "outperform", "improve", "superior", "beats"]


def build(**over) -> dict:
    kw = copy.deepcopy(BASE)
    kw.update(over)
    return speed.build_speed_report(**kw)


def numbers(text: str) -> list[float]:
    return [float(m) for m in re.findall(r"\d+(?:\.\d+)?", text)]


@pytest.mark.req("FR-011-16")
def test_steps_per_second_are_the_reciprocal_of_the_median_step_time() -> None:
    r = build()
    cpu = r["surrogate"]["python_cpu"]
    assert cpu["median_step_s"] == pytest.approx(0.020)
    assert cpu["steps_per_s"] == pytest.approx(50.0)  # not 25 (the mean)
    assert r["surrogate"]["python_gpu"]["steps_per_s"] == pytest.approx(500.0)
    assert r["surrogate"]["browser"]["T1"]["steps_per_s"] == pytest.approx(25.0)
    assert r["surrogate"]["browser"]["T2"]["steps_per_s"] == pytest.approx(1.0 / 0.120)
    assert r["solver"]["wall_s_per_step"] == pytest.approx(0.5)
    assert r["solver"]["steps_per_s"] == pytest.approx(2.0)


@pytest.mark.req("FR-011-16")
def test_hardware_and_tier_are_named_for_every_measurement() -> None:
    r = build()
    assert r["surrogate"]["python_cpu"]["hardware"] == "Test CPU 16c"
    assert r["surrogate"]["python_gpu"]["hardware"] == "Test GPU 16 GiB"
    assert r["solver"]["hardware"] == "Test GPU 16 GiB"
    t1, t2 = r["surrogate"]["browser"]["T1"], r["surrogate"]["browser"]["T2"]
    assert (t1["tier"], t2["tier"]) == ("T1", "T2")
    assert (t1["hardware"], t1["browser"]) == ("Test GPU 16 GiB", "Chromium 141")
    assert (t2["hardware"], t2["browser"]) == ("Test iGPU", "Chromium 141")
    assert (r["geometry_id"], r["particles"]) == ("g017", 2000)


@pytest.mark.req("FR-011-16")
def test_the_statement_is_a_measurement_with_every_rate_hardware_and_tier_and_no_comparative_claim() -> None:
    text = build()["statement"]
    low = text.lower()
    assert "measur" in low
    for word in FORBIDDEN:
        assert word not in low, word
    for name in ("Test CPU 16c", "Test GPU 16 GiB", "Test iGPU", "Chromium 141", "T1", "T2"):
        assert name in text
    found = numbers(text)
    for rate in (50.0, 500.0, 25.0, 8.33, 2.0):
        assert any(abs(x - rate) <= 0.01 * rate for x in found), rate


@pytest.mark.req("FR-011-16")
def test_a_missing_gpu_is_reported_not_run_with_its_reason_and_never_guessed() -> None:
    r = build(python_gpu={"reason": "no CUDA device"})
    gpu = r["surrogate"]["python_gpu"]
    assert gpu["status"] == "not run"
    assert gpu["reason"] == "no CUDA device"
    assert "steps_per_s" not in gpu
    assert "not run" in r["statement"].lower()
    assert "no CUDA device" in r["statement"]


@pytest.mark.req("FR-011-16")
def test_a_browser_tier_that_was_not_measured_is_reported_not_run() -> None:
    browser = copy.deepcopy(BASE["browser"])
    browser["T2"] = {"hardware": "Test iGPU", "browser": "Chromium 141", "reason": "WebGPU unavailable"}
    r = build(browser=browser)
    t2 = r["surrogate"]["browser"]["T2"]
    assert t2["status"] == "not run"
    assert t2["tier"] == "T2"
    assert t2["reason"] == "WebGPU unavailable"
    assert "steps_per_s" not in t2
    assert r["surrogate"]["browser"]["T1"]["steps_per_s"] == pytest.approx(25.0)


@pytest.mark.req("FR-011-16")
def test_the_median_of_an_even_count_is_the_mean_of_the_two_middle_values() -> None:
    r = build(python_cpu={"hardware": "Test CPU 16c", "step_times_s": [0.010, 0.020, 0.030, 0.100]})
    assert r["surrogate"]["python_cpu"]["median_step_s"] == pytest.approx(0.025)
    assert r["surrogate"]["python_cpu"]["steps_per_s"] == pytest.approx(40.0)


HOSTILE = [
    ("empty-times", {"python_cpu": {"hardware": "h", "step_times_s": []}}),
    ("zero-time", {"python_cpu": {"hardware": "h", "step_times_s": [0.01, 0.0, 0.02]}}),
    ("negative-time", {"python_cpu": {"hardware": "h", "step_times_s": [0.01, -0.02, 0.02]}}),
    ("nan-time", {"python_cpu": {"hardware": "h", "step_times_s": [0.01, float("nan"), 0.02]}}),
    ("inf-time", {"python_cpu": {"hardware": "h", "step_times_s": [0.01, float("inf"), 0.02]}}),
    ("no-hardware", {"python_cpu": {"step_times_s": [0.01, 0.02]}}),
    ("empty-hardware", {"python_cpu": {"hardware": "", "step_times_s": [0.01, 0.02]}}),
    ("blank-hardware", {"python_cpu": {"hardware": "   ", "step_times_s": [0.01, 0.02]}}),
    ("solver-zero", {"solver": {"hardware": "h", "wall_s_per_step": 0.0}}),
    ("solver-nan", {"solver": {"hardware": "h", "wall_s_per_step": float("nan")}}),
    ("solver-no-hardware", {"solver": {"wall_s_per_step": 0.5}}),
    ("particles-zero", {"particles": 0}),
    ("empty-geometry", {"geometry_id": ""}),
    ("tier-T3", {"browser": {"T1": BASE["browser"]["T1"], "T3": BASE["browser"]["T2"]}}),
    ("tier-missing", {"browser": {"T1": BASE["browser"]["T1"]}}),
    (
        "browser-tier-nan",
        {
            "browser": {
                "T1": {"hardware": "h", "browser": "b", "step_times_s": [float("nan")]},
                "T2": BASE["browser"]["T2"],
            }
        },
    ),
    ("gpu-neither", {"python_gpu": {}}),
]


@pytest.mark.req("FR-011-16")
@pytest.mark.parametrize(("label", "over"), HOSTILE, ids=[h[0] for h in HOSTILE])
def test_hostile_measurements_are_refused(label: str, over: dict) -> None:
    with pytest.raises(ValueError, match=r"."):
        build(**over)
