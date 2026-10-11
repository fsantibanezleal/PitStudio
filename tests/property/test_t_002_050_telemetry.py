# ruff: noqa: E501, PT018
"""T-002-050: GPU telemetry sampling and summary (US-002-5).

Requirements: FR-002-30, FR-002-31, FR-002-32, P-002-08.

Expected API (module `pitstudio.runner.telemetry`, stated for the implementer):
  * `sample_loop(backend, path, hz, *, clock, should_stop, run_id, stage, shard=0, gpu=0) -> int`: appends one JSON line
    per sample to `path` (opened for append, flushed per line) while `should_stop()` is false, sleeping `1 / hz` seconds
    on `clock.sleep` between samples; `t_s` is `clock.monotonic()` minus its value at the first sample; each line has
    exactly the fields of contracts/events.schema.json#/$defs/telemetry_sample (mem_used_bytes = backend.vram_total_bytes
    - read("free_bytes"), mem_total_bytes = backend.vram_total_bytes, the other fields from `backend.read(<field>)`);
    a field whose read raises, or returns a non-finite, negative or beyond-the-schema-cap value, is stored `null`
    (energy_mj and the integer fields are written as integers); returns the number of samples;
  * `summarize(samples: list[dict], *, sample_hz: float) -> dict`: the telemetry summary of spec 001 data-model 2.4:
    `sample_hz`, `n_samples`, `gpu_busy_pct {mean, p50, p95}` (from util_pct), `mem_used_peak_bytes`,
    `power_w {mean, p95, max}`, `power_at_limit_frac` (share of samples with power_w >= 0.95 * power_limit_w),
    `energy_j` ((last - first energy_mj) / 1000), `sm_clock_mhz {mean, p5}`, `temp_c_max`, `clocks_event_frac
    {sw_power_cap 0x4, sw_thermal 0x20, hw_thermal 0x40, hw_slowdown 0x8, power_brake 0x80, idle 0x1}`,
    `nvenc_util_pct {mean, max}`, `pcie_replays_delta` (last - first), `unavailable {field: reason}`; percentiles are
    Hyndman-Fan type 7 (numpy's default linear method); only valid samples of a field are used; a field with no valid
    sample is `null` and named in `unavailable` with a reason (<= 120 characters) that contains the count of invalid
    samples; nothing is guessed or set to 0;
  * `thermal_flag(summary: dict) -> bool`: True iff clocks_event_frac.hw_thermal or .hw_slowdown is strictly above 0.05;
  * a GPU stage of a real run writes `runs/<run_id>/telemetry.jsonl` and a manifest `telemetry` summary built this way.
Oracles: hand calculation on fixed series (type-7 values worked out below), numpy.percentile (reference implementation of
type 7), the telemetry_sample schema, the spec's own example device, metamorphic relations (permutation, scaling,
translation, duplication of means/maxima/fractions, constant power energy). NOTE (red report): P-002-08(c) as written is
false for type-7 percentiles in general ([1, 2]: p95 = 1.95, duplicated [1, 1, 2, 2]: 2.0), so the duplication relation
is tested for means, maxima and fractions only.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import itertools

import runner_world as rw
import schemas
from runner_world import FakeClock, recipe, stage

EXAMPLE = json.loads(
    (rw.ROOT / "specs" / "002-runner" / "contracts" / "examples" / "profile.valid-fake-device.json").read_text(
        encoding="utf-8"
    )
)
RUN_ID = "20261004T120000Z-tele"
STAGE = {"id": "st50_physics", "variant": "dem"}
FIELDS = (
    "mem_used_bytes",
    "mem_total_bytes",
    "util_pct",
    "power_w",
    "power_limit_w",
    "temp_c",
    "sm_clock_mhz",
    "clocks_event_mask",
    "energy_mj",
    "nvenc_util_pct",
    "pcie_replays",
)
BITS = {
    "idle": 0x1,
    "sw_power_cap": 0x4,
    "hw_slowdown": 0x8,
    "sw_thermal": 0x20,
    "hw_thermal": 0x40,
    "power_brake": 0x80,
}


def mk(i: int = 0, **kw: Any) -> dict[str, Any]:
    base = {"t_s": float(i), "run_id": RUN_ID, "stage": STAGE, "shard": 0, "gpu": 0}
    base.update({f: None for f in FIELDS})
    base.update(kw)
    return base


def pct(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))  # method="linear" = Hyndman-Fan type 7


# ---- FR-002-30: the sampler --------------------------------------------------------------------------------------------------------
def run_loop(
    tmp: Path, device: dict[str, Any], hz: float, seconds: float, *, backend: Any = None, on_check: Any = None
) -> tuple[int, list[dict[str, Any]], Path]:
    from pitstudio.runner import gpu, telemetry

    clock = FakeClock(500.0)
    be = backend or gpu.load_backend(f"fake:{_write_device(tmp, device)}", clock=clock)
    path = tmp / "telemetry.jsonl"
    state = {"i": 0}

    def should_stop() -> bool:
        if on_check:
            on_check(path, state["i"])
        state["i"] += 1
        return clock.t - 500.0 >= seconds

    n = telemetry.sample_loop(
        be, path, hz, clock=clock, should_stop=should_stop, run_id=RUN_ID, stage=STAGE, shard=0, gpu=0
    )
    rows = [json.loads(ln, parse_constant=_no_constants) for ln in path.read_text(encoding="utf-8").splitlines()]
    return n, rows, path


def _no_constants(c: str) -> Any:
    raise ValueError(f"non-finite constant {c} in telemetry.jsonl")


def _write_device(tmp: Path, device: dict[str, Any]) -> Path:
    import yaml

    p = tmp / "device.yaml"
    p.write_text(yaml.safe_dump(device), encoding="utf-8")
    return p


@pytest.mark.req("FR-002-30")
@pytest.mark.parametrize(("hz", "seconds"), [(1, 10), (2, 10), (4, 10), (3, 7), (1.5, 20), (4, 0.5)])
def test_fr_002_30_sample_count_is_floor_t_times_hz_plus_minus_one(tmp_path: Path, hz: float, seconds: float) -> None:
    n, rows, _ = run_loop(tmp_path, EXAMPLE, hz, seconds)
    assert abs(n - math.floor(seconds * hz)) <= 1 and len(rows) == n
    ts = [r["t_s"] for r in rows]
    assert ts[0] == 0 and all(abs(b - a - 1 / hz) < 1e-9 for a, b in itertools.pairwise(ts))
    for r in rows:
        assert schemas.errors("events", r, "#/$defs/telemetry_sample") == [], r
        assert (r["run_id"], r["stage"], r["shard"], r["gpu"]) == (RUN_ID, STAGE, 0, 0)


@pytest.mark.req("FR-002-30")
def test_fr_002_30_each_line_is_flushed_as_it_is_written(tmp_path: Path) -> None:
    seen: list[int] = []

    def on_check(path: Path, i: int) -> None:
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        seen.append(len(lines))
        assert len(lines) == i, (
            f"before iteration {i} the file must already hold {i} complete lines, found {len(lines)}"
        )
        for ln in lines:
            json.loads(ln)

    n, rows, _ = run_loop(tmp_path, EXAMPLE, 2, 5, on_check=on_check)
    assert n == len(rows) == 10 and seen[0] == 0


@pytest.mark.req("FR-002-30")
def test_fr_002_30_fields_come_from_the_backend_at_the_sample_time(tmp_path: Path) -> None:
    _n, rows, _ = run_loop(tmp_path, EXAMPLE, 1, 130)
    first, at10, at60, at120 = rows[0], rows[10], rows[60], rows[120]
    # hand values from the example device (specs/002-runner/contracts/examples/profile.valid-fake-device.json)
    assert first["mem_used_bytes"] == 51539607552 - 49392123904 == 2147483648
    assert (
        first["mem_total_bytes"],
        first["util_pct"],
        first["power_w"],
        first["power_limit_w"],
        first["temp_c"],
        first["sm_clock_mhz"],
        first["clocks_event_mask"],
        first["energy_mj"],
        first["nvenc_util_pct"],
        first["pcie_replays"],
    ) == (51539607552, 0, 30, 300, 45, 1980, 1, 0, None, 0)
    assert (
        at10["mem_used_bytes"] == 51539607552 - 30064771072
        and at10["util_pct"] == 97
        and at10["power_w"] == 210
        and at10["clocks_event_mask"] == 0
    )
    assert at10["energy_mj"] == 300_000 and isinstance(at10["energy_mj"], int)
    assert at60["temp_c"] == 72 and at120["temp_c"] == 83
    assert rows[100]["clocks_event_mask"] == 4


class HostileBackend:
    """In-memory backend with readings the file format cannot express (FR-002-32)."""

    name, driver, vram_total_bytes = "Hostile GPU", "1.0", 1000

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values

    def read(self, field: str) -> Any:
        v = self.values[field]
        if isinstance(v, Exception):
            raise v
        return v


@pytest.mark.req("FR-002-32")
@pytest.mark.parametrize(
    ("label", "bad", "field"),
    [
        ("nan", float("nan"), "temp_c"),
        ("inf", float("inf"), "power_w"),
        ("-inf", float("-inf"), "util_pct"),
        ("negative", -1.0, "power_w"),
        ("negative-int", -5, "pcie_replays"),
        ("above-cap-temperature", 250.0, "temp_c"),
        ("above-cap-util", 100.5, "util_pct"),
        ("above-cap-power", 10001.0, "power_w"),
        ("above-cap-clock", 20001.0, "sm_clock_mhz"),
        ("mask-above-32-bits", 2**32, "clocks_event_mask"),
        ("raises", RuntimeError("NVML_ERROR_NOT_SUPPORTED"), "nvenc_util_pct"),
        ("raises-keyerror", KeyError("x"), "energy_mj"),
        ("none", None, "sm_clock_mhz"),
    ],
)
def test_fr_002_32_an_unsupported_failing_non_finite_negative_or_out_of_range_reading_is_null_never_zero(
    tmp_path: Path, label: str, bad: Any, field: str
) -> None:
    values = {
        "free_bytes": 400,
        "temp_c": 60.0,
        "power_w": 100.0,
        "power_limit_w": 200.0,
        "util_pct": 50.0,
        "sm_clock_mhz": 1500.0,
        "clocks_event_mask": 0,
        "energy_mj": 1000,
        "nvenc_util_pct": 5.0,
        "pcie_replays": 0,
    }
    values["free_bytes" if field == "mem_used_bytes" else field] = bad
    n, rows, _ = run_loop(tmp_path, EXAMPLE, 1, 3, backend=HostileBackend(values))
    assert n == 3
    for r in rows:
        assert r[field] is None, f"{label}: {field} must be null, got {r[field]!r}"
        assert schemas.errors("events", r, "#/$defs/telemetry_sample") == []
        others = {k: v for k, v in r.items() if k in FIELDS and k != field and k != "mem_used_bytes"}
        assert others["util_pct" if field != "util_pct" else "temp_c"] is not None, "other fields are unaffected"


@pytest.mark.req("FR-002-32")
def test_fr_002_32_an_unsupported_field_of_the_device_file_is_null_in_every_sample(tmp_path: Path) -> None:
    _, rows, _ = run_loop(tmp_path, EXAMPLE, 2, 4)
    assert all(r["nvenc_util_pct"] is None for r in rows)
    assert all(r["util_pct"] is not None for r in rows)


# ---- FR-002-31: the summary by hand ----------------------------------------------------------------------------------------------------
HAND = [
    mk(
        0,
        util_pct=10.0,
        power_w=100.0,
        power_limit_w=300.0,
        sm_clock_mhz=1980.0,
        temp_c=60.0,
        mem_used_bytes=1_000_000_000,
        clocks_event_mask=0x0,
        energy_mj=0,
        nvenc_util_pct=10.0,
        pcie_replays=3,
        mem_total_bytes=16_000_000_000,
    ),
    mk(
        1,
        util_pct=20.0,
        power_w=200.0,
        power_limit_w=300.0,
        sm_clock_mhz=1900.0,
        temp_c=65.0,
        mem_used_bytes=3_000_000_000,
        clocks_event_mask=0x4,
        energy_mj=100_000,
        nvenc_util_pct=20.0,
        pcie_replays=3,
        mem_total_bytes=16_000_000_000,
    ),
    mk(
        2,
        util_pct=30.0,
        power_w=300.0,
        power_limit_w=300.0,
        sm_clock_mhz=1800.0,
        temp_c=70.0,
        mem_used_bytes=2_000_000_000,
        clocks_event_mask=0x40,
        energy_mj=250_000,
        nvenc_util_pct=30.0,
        pcie_replays=4,
        mem_total_bytes=16_000_000_000,
    ),
    mk(
        3,
        util_pct=40.0,
        power_w=250.0,
        power_limit_w=300.0,
        sm_clock_mhz=1700.0,
        temp_c=80.0,
        mem_used_bytes=5_000_000_000,
        clocks_event_mask=0x41,
        energy_mj=400_000,
        nvenc_util_pct=40.0,
        pcie_replays=4,
        mem_total_bytes=16_000_000_000,
    ),
    mk(
        4,
        util_pct=100.0,
        power_w=150.0,
        power_limit_w=300.0,
        sm_clock_mhz=1500.0,
        temp_c=75.0,
        mem_used_bytes=4_000_000_000,
        clocks_event_mask=0x28,
        energy_mj=600_000,
        nvenc_util_pct=90.0,
        pcie_replays=10,
        mem_total_bytes=16_000_000_000,
    ),
]


@pytest.mark.req("FR-002-31")
def test_fr_002_31_summary_of_a_fixed_series_equals_the_hand_calculation() -> None:
    from pitstudio.runner import telemetry

    s = telemetry.summarize(HAND, sample_hz=2)
    assert s["sample_hz"] == 2 and s["n_samples"] == 5
    # util: mean 200/5 = 40; p50 = 30; p95 (type 7): 0.95 * 4 = 3.8 -> 40 + 0.8 * (100 - 40) = 88
    assert s["gpu_busy_pct"] == {
        "mean": pytest.approx(40.0, rel=1e-12),
        "p50": pytest.approx(30.0, rel=1e-12),
        "p95": pytest.approx(88.0, rel=1e-12),
    }
    # power: mean 1000/5 = 200, max 300, p95: sorted 100,150,200,250,300 -> 250 + 0.8 * 50 = 290
    assert s["power_w"] == {
        "mean": pytest.approx(200.0, rel=1e-12),
        "p95": pytest.approx(290.0, rel=1e-12),
        "max": 300.0,
    }
    assert s["power_at_limit_frac"] == pytest.approx(0.2), "only 300 W >= 0.95 * 300 W = 285 W"
    assert s["energy_j"] == pytest.approx(600.0, rel=1e-12), "(600,000 - 0) mJ / 1,000"
    # sm clock: mean 8880 / 5 = 1776; p5: sorted 1500,1700,1800,1900,1980 -> 0.05 * 4 = 0.2 -> 1500 + 0.2 * 200 = 1540
    assert s["sm_clock_mhz"] == {"mean": pytest.approx(1776.0, rel=1e-12), "p5": pytest.approx(1540.0, rel=1e-12)}
    assert s["temp_c_max"] == 80.0 and s["mem_used_peak_bytes"] == 5_000_000_000
    # masks: idle 0x1 in 0x41 (1/5); sw_power_cap 0x4 in 0x4 (1/5); hw_thermal 0x40 in 0x40, 0x41 (2/5);
    # hw_slowdown 0x8 and sw_thermal 0x20 both in 0x28 (1/5 each); power_brake 0x80 never
    assert s["clocks_event_frac"] == {
        "idle": 0.2,
        "sw_power_cap": 0.2,
        "hw_thermal": 0.4,
        "hw_slowdown": 0.2,
        "sw_thermal": 0.2,
        "power_brake": 0.0,
    }
    assert s["nvenc_util_pct"] == {"mean": pytest.approx(38.0, rel=1e-12), "max": 90.0}
    assert s["pcie_replays_delta"] == 7 and s["unavailable"] == {}
    assert telemetry.thermal_flag(s) is True
    assert schemas.errors("manifest", s, "#/$defs/telemetry_summary") == [], (
        "the summary is a valid manifest telemetry summary"
    )


@pytest.mark.req("FR-002-31")
def test_fr_002_31_summary_percentiles_agree_with_numpy_type_7_on_a_longer_series() -> None:
    from pitstudio.runner import telemetry

    rng = np.random.default_rng(20261004)
    util = [float(x) for x in rng.uniform(0, 100, 257).round(3)]
    clk = [float(x) for x in rng.uniform(900, 2100, 257).round(1)]
    samples = [mk(i, util_pct=util[i], sm_clock_mhz=clk[i]) for i in range(257)]
    s = telemetry.summarize(samples, sample_hz=4)
    assert s["gpu_busy_pct"]["p50"] == pytest.approx(pct(util, 50), rel=1e-12)
    assert s["gpu_busy_pct"]["p95"] == pytest.approx(pct(util, 95), rel=1e-12)
    assert s["sm_clock_mhz"]["p5"] == pytest.approx(pct(clk, 5), rel=1e-12)
    assert s["gpu_busy_pct"]["mean"] == pytest.approx(float(np.mean(util)), rel=1e-9)


@pytest.mark.req("FR-002-31")
@pytest.mark.parametrize(("hot", "flag"), [(0, False), (4, False), (5, False), (6, True)])
def test_fr_002_31_thermal_flag_needs_a_fraction_strictly_above_0_05(hot: int, flag: bool) -> None:
    from pitstudio.runner import telemetry

    for bit in (0x40, 0x8):
        samples = [mk(i, clocks_event_mask=bit if i < hot else 0, util_pct=50.0) for i in range(100)]
        s = telemetry.summarize(samples, sample_hz=1)
        assert telemetry.thermal_flag(s) is flag, f"{hot} of 100 samples with bit {bit:#x}"
    other = [mk(i, clocks_event_mask=0x20 | 0x4 | 0x80, util_pct=1.0) for i in range(100)]
    assert telemetry.thermal_flag(telemetry.summarize(other, sample_hz=1)) is False, (
        "only hw_thermal and hw_slowdown set the flag"
    )


# ---- FR-002-32: the summary with missing data ------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-32")
def test_fr_002_32_summary_uses_only_valid_samples_and_never_invents_zeros() -> None:
    from pitstudio.runner import telemetry

    samples = [
        mk(i, util_pct=v, power_w=p, power_limit_w=100.0, energy_mj=e)
        for i, (v, p, e) in enumerate(
            [(10.0, 50.0, 0), (None, None, None), (30.0, 100.0, 2000), (None, 90.0, None), (50.0, None, 5000)]
        )
    ]
    s = telemetry.summarize(samples, sample_hz=1)
    assert s["n_samples"] == 5
    assert s["gpu_busy_pct"]["mean"] == pytest.approx(30.0) and s["gpu_busy_pct"]["p50"] == pytest.approx(30.0)
    assert s["power_w"]["mean"] == pytest.approx(80.0) and s["power_w"]["max"] == 100.0
    # samples with both power and limit valid: 50, 100, 90 W against 0.95 * 100 W = 95 W -> only 100 W qualifies: 1/3
    assert s["power_at_limit_frac"] == pytest.approx(1 / 3)
    assert s["energy_j"] == pytest.approx(5.0), "(5000 - 0) mJ over the valid samples only"
    assert {"gpu_busy_pct", "power_w", "energy_j"}.isdisjoint(s["unavailable"]), (
        "fields with valid samples are not unavailable"
    )


@pytest.mark.req("FR-002-32")
@pytest.mark.parametrize(
    ("field", "summary_key"),
    [
        ("util_pct", "gpu_busy_pct"),
        ("power_w", "power_w"),
        ("sm_clock_mhz", "sm_clock_mhz"),
        ("temp_c", "temp_c_max"),
        ("mem_used_bytes", "mem_used_peak_bytes"),
        ("nvenc_util_pct", "nvenc_util_pct"),
        ("energy_mj", "energy_j"),
        ("pcie_replays", "pcie_replays_delta"),
        ("clocks_event_mask", "clocks_event_frac"),
    ],
)
def test_fr_002_32_a_field_with_no_valid_sample_is_null_and_named_in_unavailable_with_the_invalid_count(
    field: str, summary_key: str
) -> None:
    from pitstudio.runner import telemetry

    full = {
        "util_pct": 50.0,
        "power_w": 100.0,
        "power_limit_w": 200.0,
        "sm_clock_mhz": 1500.0,
        "temp_c": 60.0,
        "mem_used_bytes": 10,
        "nvenc_util_pct": 5.0,
        "energy_mj": 0,
        "pcie_replays": 0,
        "clocks_event_mask": 0,
    }
    samples = [
        mk(i, **{**full, field: None, "energy_mj": i * 1000 if field != "energy_mj" else None}) for i in range(7)
    ]
    s = telemetry.summarize(samples, sample_hz=1)
    assert s[summary_key] is None, f"{summary_key} must be null, not {s[summary_key]!r}"
    assert summary_key in s["unavailable"]
    reason = s["unavailable"][summary_key]
    assert isinstance(reason, str) and 0 < len(reason) <= 120 and "7" in reason, (
        f"the reason must carry the count of invalid samples: {reason!r}"
    )
    others = [k for k in ("gpu_busy_pct", "temp_c_max", "sm_clock_mhz") if k != summary_key]
    assert all(s[k] is not None for k in others), "other fields are summarised normally"


@pytest.mark.req("FR-002-32")
def test_fr_002_32_power_at_limit_is_unavailable_when_the_limit_is_never_known() -> None:
    from pitstudio.runner import telemetry

    s = telemetry.summarize([mk(i, power_w=100.0, power_limit_w=None) for i in range(4)], sample_hz=1)
    assert s["power_at_limit_frac"] is None and "power_at_limit_frac" in s["unavailable"]
    assert s["power_w"]["mean"] == 100.0


@pytest.mark.req("FR-002-32")
def test_fr_002_32_an_empty_series_summarises_to_nulls() -> None:
    from pitstudio.runner import telemetry

    s = telemetry.summarize([], sample_hz=2)
    assert s["n_samples"] == 0 and s["gpu_busy_pct"] is None and s["energy_j"] is None
    assert "gpu_busy_pct" in s["unavailable"]


# ---- P-002-08: metamorphic relations ----------------------------------------------------------------------------------------------------
series = st.lists(
    st.fixed_dictionaries(
        {
            "util": st.floats(0, 100, allow_nan=False),
            "power": st.floats(0, 600, allow_nan=False),
            "clock": st.floats(300, 2200, allow_nan=False),
            "temp": st.floats(20, 95, allow_nan=False),
            "mem": st.integers(0, 16_000_000_000),
            "mask": st.sampled_from([0, 1, 4, 8, 0x20, 0x40, 0x48, 0x41, 0x80, 0xFF]),
            "nvenc": st.floats(0, 100, allow_nan=False),
        }
    ),
    min_size=1,
    max_size=120,
)


def build(rows: list[dict[str, Any]], limit: float = 300.0) -> list[dict[str, Any]]:
    return [
        mk(
            i,
            util_pct=r["util"],
            power_w=r["power"],
            power_limit_w=limit,
            sm_clock_mhz=r["clock"],
            temp_c=r["temp"],
            mem_used_bytes=r["mem"],
            clocks_event_mask=r["mask"],
            nvenc_util_pct=r["nvenc"],
            energy_mj=i * 1000,
            pcie_replays=i,
        )
        for i, r in enumerate(rows)
    ]


def stats_of(s: dict[str, Any]) -> dict[str, Any]:
    return {
        k: s[k]
        for k in (
            "gpu_busy_pct",
            "power_w",
            "sm_clock_mhz",
            "temp_c_max",
            "mem_used_peak_bytes",
            "clocks_event_frac",
            "power_at_limit_frac",
            "nvenc_util_pct",
        )
    }


def close(a: Any, b: Any, rtol: float = 1e-9) -> bool:
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k], rtol) for k in a)
    if a is None or b is None:
        return a is b
    return math.isclose(float(a), float(b), rel_tol=rtol, abs_tol=1e-9)


@pytest.mark.req("P-002-08")
@settings(max_examples=100, deadline=None)
@given(rows=series, seed=st.integers(0, 2**32 - 1))
def test_p_002_08a_permuting_samples_leaves_means_percentiles_maxima_and_fractions_unchanged(
    rows: list[dict[str, Any]], seed: int
) -> None:
    from pitstudio.runner import telemetry

    samples = build(rows)
    shuffled = list(samples)
    np.random.default_rng(seed).shuffle(shuffled)
    a = telemetry.summarize(samples, sample_hz=2)
    b = telemetry.summarize(shuffled, sample_hz=2)
    assert close(stats_of(a), stats_of(b), 1e-9)
    for k in ("temp_c_max", "mem_used_peak_bytes", "clocks_event_frac", "power_at_limit_frac"):
        assert a[k] == b[k], f"{k} must be exactly equal"
    assert a["power_w"]["max"] == b["power_w"]["max"]
    assert a["gpu_busy_pct"]["p95"] == b["gpu_busy_pct"]["p95"] and a["gpu_busy_pct"]["p50"] == b["gpu_busy_pct"]["p50"]
    assert a["sm_clock_mhz"]["p5"] == b["sm_clock_mhz"]["p5"]


@pytest.mark.req("P-002-08")
@settings(max_examples=100, deadline=None)
@given(rows=series, c=st.sampled_from([0.5, 2.0, 3.0, 0.25, 10.0, 1.5, 0.1]))
def test_p_002_08b_scaling_power_and_limit_scales_power_statistics_and_keeps_the_limit_fraction(
    rows: list[dict[str, Any]], c: float
) -> None:
    from pitstudio.runner import telemetry

    limit = 300.0
    for r in rows:  # keep every sample at least 1e-9 (relative) away from the 0.95 * limit boundary
        assume(abs(r["power"] - 0.95 * limit) > 1e-6 * 0.95 * limit)
        assume(abs(r["power"] * c - 0.95 * limit * c) > 1e-6 * 0.95 * limit * c)
    base = build(rows, limit)
    scaled = [{**s, "power_w": s["power_w"] * c, "power_limit_w": limit * c} for s in base]
    a = telemetry.summarize(base, sample_hz=2)
    b = telemetry.summarize(scaled, sample_hz=2)
    for k in ("mean", "p95", "max"):
        assert math.isclose(b["power_w"][k], a["power_w"][k] * c, rel_tol=1e-9, abs_tol=1e-9), k
    assert a["power_at_limit_frac"] == b["power_at_limit_frac"]
    assert stats_of(a)["gpu_busy_pct"] == stats_of(b)["gpu_busy_pct"], "other fields are untouched"


@pytest.mark.req("P-002-08")
@settings(max_examples=100, deadline=None)
@given(rows=series)
def test_p_002_08c_duplicating_every_sample_leaves_means_maxima_and_fractions_unchanged(
    rows: list[dict[str, Any]],
) -> None:
    from pitstudio.runner import telemetry

    samples = build(rows)
    doubled = [dict(s, t_s=float(2 * i + k)) for i, s in enumerate(samples) for k in (0, 1)]
    a = telemetry.summarize(samples, sample_hz=2)
    b = telemetry.summarize(doubled, sample_hz=2)
    assert math.isclose(a["gpu_busy_pct"]["mean"], b["gpu_busy_pct"]["mean"], rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(a["power_w"]["mean"], b["power_w"]["mean"], rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(a["sm_clock_mhz"]["mean"], b["sm_clock_mhz"]["mean"], rel_tol=1e-9, abs_tol=1e-9)
    assert (
        a["power_w"]["max"] == b["power_w"]["max"]
        and a["temp_c_max"] == b["temp_c_max"]
        and a["mem_used_peak_bytes"] == b["mem_used_peak_bytes"]
    )
    assert a["clocks_event_frac"] == b["clocks_event_frac"] and a["power_at_limit_frac"] == b["power_at_limit_frac"]
    assert a["nvenc_util_pct"]["max"] == b["nvenc_util_pct"]["max"]


@pytest.mark.req("P-002-08")
@settings(max_examples=100, deadline=None)
@given(rows=series, shift=st.integers(1, 500))
def test_p_002_08e_translating_a_series_translates_its_mean_and_type_7_percentiles(
    rows: list[dict[str, Any]], shift: int
) -> None:
    from pitstudio.runner import telemetry

    base = build(rows)
    moved = [dict(s, sm_clock_mhz=s["sm_clock_mhz"] + shift) for s in base]
    a = telemetry.summarize(base, sample_hz=2)["sm_clock_mhz"]
    b = telemetry.summarize(moved, sample_hz=2)["sm_clock_mhz"]
    assert math.isclose(b["mean"], a["mean"] + shift, rel_tol=1e-9) and math.isclose(
        b["p5"], a["p5"] + shift, rel_tol=1e-9
    )


@pytest.mark.req("P-002-08")
@settings(max_examples=100, deadline=None)
@given(power=st.integers(1, 1000), seconds=st.integers(1, 600), hz=st.sampled_from([1, 2, 4]))
def test_p_002_08d_constant_power_over_t_seconds_gives_exactly_p_times_t_joules(
    power: int, seconds: int, hz: int
) -> None:
    from pitstudio.runner import telemetry

    n = seconds * hz + 1
    samples = [
        mk(i, t_s=i / hz, power_w=float(power), power_limit_w=1000.0, energy_mj=power * 1000 * i // hz)
        for i in range(n)
    ]
    assert all(power * 1000 * i % hz == 0 for i in range(n)), "integer millijoules"
    s = telemetry.summarize(samples, sample_hz=float(hz))
    assert s["energy_j"] == power * seconds, "exact, not approximate"
    assert s["power_w"]["mean"] == pytest.approx(power, rel=1e-12) and s["power_w"]["max"] == power


@pytest.mark.req("P-002-08")
@settings(max_examples=60, deadline=None)
@given(rows=series)
def test_p_002_08_summary_means_agree_with_numpy_on_random_series(rows: list[dict[str, Any]]) -> None:
    from pitstudio.runner import telemetry

    s = telemetry.summarize(build(rows), sample_hz=2)
    assert s["power_w"]["mean"] == pytest.approx(float(np.mean([r["power"] for r in rows])), rel=1e-9, abs=1e-9)
    assert s["gpu_busy_pct"]["p95"] == pytest.approx(pct([r["util"] for r in rows], 95), rel=1e-9, abs=1e-9)
    assert s["temp_c_max"] == max(r["temp"] for r in rows)
    assert s["n_samples"] == len(rows)


# ---- through a real run ----------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


@pytest.mark.req("FR-002-30")
@pytest.mark.req("FR-002-31")
def test_fr_002_31_a_gpu_stage_writes_telemetry_jsonl_and_a_manifest_summary_and_a_cpu_stage_none(world) -> None:
    world.write_recipe(
        recipe(
            "tele",
            [
                stage("st50_physics", gpu="exclusive", vram=2.0, params={"mode": "sleep", "sleep_s": 2.0}),
                stage("s10_preprocess"),
            ],
        )
    )
    assert world.run("tele").code == 0
    run_dir = world.last_run()
    lines = [json.loads(ln) for ln in (run_dir / "telemetry.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines and all(schemas.errors("events", ln, "#/$defs/telemetry_sample") == [] for ln in lines)
    assert {ln["stage"]["id"] for ln in lines} == {"st50_physics"} and {ln["run_id"] for ln in lines} == {run_dir.name}
    gpu_rec, cpu_rec = world.stage_record("st50_physics"), world.stage_record("s10_preprocess")
    tele = gpu_rec["telemetry"]
    assert cpu_rec["telemetry"] is None
    assert tele["sample_hz"] == 4 and tele["n_samples"] == len(
        [ln for ln in lines if ln["stage"]["id"] == "st50_physics"]
    )
    assert tele["n_samples"] >= 4, "a stage of at least 2 s sampled at 4 Hz"
    assert tele["power_w"]["mean"] == pytest.approx(100.0) and tele["gpu_busy_pct"]["mean"] == pytest.approx(50.0)
    assert tele["power_at_limit_frac"] == 0 and gpu_rec["thermal_flag"] is False
    assert tele["energy_j"] == pytest.approx(100.0 * (tele["n_samples"] - 1) / 4, rel=0.3), (
        "100 W constant power (100,000 mJ/s)"
    )
    assert schemas.errors("manifest", gpu_rec["telemetry"], "#/$defs/telemetry_summary") == []
