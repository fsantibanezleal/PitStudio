"""T-011-060 - FR-011-44: runner behaviour of training and calibration against the fake GPU backend (the CUDA smoke
    test is
tests/gpu/test_t_011_060_gpu_smoke.py, marked `gpu`, not part of this file).

Oracles (independent of the code under test; plan 011 test strategy FR-011-44: "the runner's fake GPU backend (lock
    held, hold file, OOM raised
twice); expected manifest records"):
- the fake GPU backend of this file: the held-lock environment variable of FR-002-62 (`PITSTUDIO_HELD_LOCKS`,
    sorted comma-separated lock names;
  `gpu<N>.compute` for device N), a hold file `gpu0.hold` in a temporary `GPU_LOCK_DIR`, and a scripted attempt
      function that raises a CUDA
  out-of-memory error ("CUDA out of memory. Tried to allocate ...", the message of torch.cuda.OutOfMemoryError) a
      chosen number of times;
- the declared fallbacks of FR-011-44 by hand: GNS and FNO training halve the batch at most twice (16 -> 8 -> 4:
    three attempts in all, a third
  out-of-memory error stops the stage), calibration halves the particle count once (4,000 -> 2,000: two attempts)
      and flags the trial;
  every fallback is recorded in the manifest as {"param", "from", "to", "reason": "oom"} in order;
- `error_class` values of the stage result (data-model 001, `error_class` enum): `oom`, `lock-not-held`, `hold`.

Expected public API:
  module `pitstudio.surrogate_runtime` (under `src/pitstudio/`, standard library only)
    LockNotHeldError, GpuHoldError, OomExhaustedError (Exception subclasses) with `error_class` "lock-not-held",
        "hold", "oom";
        OomExhaustedError also has `attempts` (int) and `params` (the parameters of the last attempt)
    require_gpu_lock(device, *, env) -> None
        device "cpu" -> nothing; "cuda" or "cuda:N" -> `gpu<N>.compute` (N = 0 for "cuda") must be in
            env["PITSTUDIO_HELD_LOCKS"], a sorted,
        comma-separated list of distinct lock names, else LockNotHeldError (also for an unset, empty or malformed value)
    check_hold(device, *, lock_dir) -> None      "cuda"/"cuda:0": GpuHoldError if `<lock_dir>/gpu0.hold` exists;
        "cpu": nothing
    is_cuda_oom(exc) -> bool                    True for torch.cuda.OutOfMemoryError (by class name) and for
        RuntimeError or MemoryError whose
                                                message contains "out of memory" (any case); False otherwise
    run_with_oom_fallback(kind, params, attempt, *, manifest) -> object
        kind in {"gns", "fno", "calibration"}; calls attempt(params_copy); on a CUDA out-of-memory error halves
            `batch_size` (gns, fno; at most 2
        halvings) or `particle_count` (calibration; at most 1 halving) and retries; records each halving in
            manifest["fallbacks"] and sets
        manifest["oom_fallback"] to True; raises OomExhaustedError when the allowance is used up or the value would
            fall below 1; any other
        exception propagates untouched, without a retry. The caller's params are not modified.
  module `pitstudio_studio.physics.calibration.driver`
    calibrate_with_oom_fallback(request, simulator_factory, *, manifest) -> dict
        simulator_factory(particle_count) -> simulator; runs `calibrate` with the declared fallback; the returned
            DC-011-04 document has
        `particle_count` equal to the count actually used and `oom_fallback` True when the count was halved (False
            otherwise).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _calib_fake import FakeDem, default_request  # noqa: E402
from pitstudio_studio.physics.calibration import driver  # noqa: E402

from pitstudio import surrogate_runtime as rt  # noqa: E402

OOM_MESSAGE = "CUDA out of memory. Tried to allocate 2.00 GiB (GPU 0; 15.99 GiB total capacity)"


class FakeOom(RuntimeError):
    """What the fake backend raises: a RuntimeError with the CUDA out-of-memory message."""


def scripted(fail_times: int):
    calls: list[dict] = []

    def attempt(params: dict):
        calls.append(dict(params))
        if len(calls) <= fail_times:
            raise FakeOom(OOM_MESSAGE)
        return {"trained_with": dict(params)}

    return attempt, calls


# ------------------------------------------------------------------ runner locks and the hold file


@pytest.mark.req("FR-011-44")
@pytest.mark.parametrize("device", ["cuda", "cuda:0"])
def test_a_gpu_stage_needs_gpu0_compute_in_the_held_locks(device: str) -> None:
    rt.require_gpu_lock(device, env={"PITSTUDIO_HELD_LOCKS": "gpu0.compute"})
    rt.require_gpu_lock(device, env={"PITSTUDIO_HELD_LOCKS": "gpu0.compute,gpu0.nvenc"})
    for held in ("", "gpu0.nvenc", "gpu1.compute"):
        with pytest.raises(rt.LockNotHeldError) as info:
            rt.require_gpu_lock(device, env={"PITSTUDIO_HELD_LOCKS": held})
        assert info.value.error_class == "lock-not-held"


@pytest.mark.req("FR-011-44")
def test_an_unset_variable_means_no_lock_is_held() -> None:
    with pytest.raises(rt.LockNotHeldError):
        rt.require_gpu_lock("cuda", env={})


@pytest.mark.req("FR-011-44")
@pytest.mark.parametrize(
    "malformed",
    [
        "GPU0.compute",
        "gpu0.compute,gpu0.compute",
        "gpu0.render",
        "x" * 65,
        "gpu0.compute,gpu0.nvenc,gpu1.compute,gpu1.nvenc,gpu2.compute",
    ],
    ids=["upper", "duplicate", "unknown-kind", "too-long-65", "five-entries"],  # the hostile values of FR-002-63
)
def test_a_malformed_held_locks_value_is_refused_like_no_lock(malformed: str) -> None:
    with pytest.raises(rt.LockNotHeldError):
        rt.require_gpu_lock("cuda", env={"PITSTUDIO_HELD_LOCKS": malformed})


@pytest.mark.req("FR-011-44")
def test_the_device_index_selects_the_lock() -> None:
    rt.require_gpu_lock("cuda:1", env={"PITSTUDIO_HELD_LOCKS": "gpu1.compute"})
    with pytest.raises(rt.LockNotHeldError):
        rt.require_gpu_lock("cuda:1", env={"PITSTUDIO_HELD_LOCKS": "gpu0.compute"})


@pytest.mark.req("FR-011-44")
def test_a_cpu_stage_needs_no_lock_and_ignores_the_hold_file(tmp_path: Path) -> None:
    rt.require_gpu_lock("cpu", env={})
    (tmp_path / "gpu0.hold").write_text("hold", encoding="utf-8")
    rt.check_hold("cpu", lock_dir=tmp_path)


@pytest.mark.req("FR-011-44")
@pytest.mark.parametrize("device", ["cuda", "cuda:0"])
def test_a_gpu_stage_is_refused_while_the_hold_file_exists(tmp_path: Path, device: str) -> None:
    rt.check_hold(device, lock_dir=tmp_path)  # no hold file: fine
    (tmp_path / "gpu0.hold").write_text("thermal", encoding="utf-8")
    with pytest.raises(rt.GpuHoldError) as info:
        rt.check_hold(device, lock_dir=tmp_path)
    assert info.value.error_class == "hold"


@pytest.mark.req("FR-011-44")
@pytest.mark.parametrize("device", ["gpu", "CUDA", "cuda:x", "cuda:-1", "", "tpu", "cuda:0;rm"])
def test_an_unknown_device_string_is_refused(device: str) -> None:
    with pytest.raises(ValueError, match="device"):
        rt.require_gpu_lock(device, env={"PITSTUDIO_HELD_LOCKS": "gpu0.compute"})


# ------------------------------------------------------------------ OOM classification and fallbacks


@pytest.mark.req("FR-011-44")
@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (RuntimeError("CUDA out of memory. Tried to allocate 20.00 MiB"), True),
        (RuntimeError("CUDA error: out of memory"), True),
        (MemoryError("Out Of Memory"), True),
        (FakeOom(OOM_MESSAGE), True),
        (RuntimeError("CUDA error: an illegal memory access was encountered"), False),
        (ValueError("out of memory"), False),
        (RuntimeError("shape mismatch"), False),
        (KeyboardInterrupt(), False),
    ],
)
def test_cuda_out_of_memory_is_recognised_and_other_errors_are_not(exc: BaseException, expected: bool) -> None:
    assert rt.is_cuda_oom(exc) is expected


@pytest.mark.req("FR-011-44")
@pytest.mark.parametrize("kind", ["gns", "fno"])
def test_training_halves_the_batch_after_each_out_of_memory_up_to_twice_and_records_it(kind: str) -> None:
    attempt, calls = scripted(2)
    manifest: dict = {}
    result = rt.run_with_oom_fallback(kind, {"batch_size": 16, "lr": 1e-3}, attempt, manifest=manifest)
    assert [c["batch_size"] for c in calls] == [16, 8, 4]
    assert all(c["lr"] == 1e-3 for c in calls)  # nothing else changes
    assert result == {"trained_with": {"batch_size": 4, "lr": 1e-3}}
    assert manifest["oom_fallback"] is True
    assert manifest["fallbacks"] == [
        {"param": "batch_size", "from": 16, "to": 8, "reason": "oom"},
        {"param": "batch_size", "from": 8, "to": 4, "reason": "oom"},
    ]


@pytest.mark.req("FR-011-44")
@pytest.mark.parametrize("kind", ["gns", "fno"])
def test_a_third_out_of_memory_error_stops_the_stage_with_class_oom(kind: str) -> None:
    attempt, calls = scripted(3)
    manifest: dict = {}
    with pytest.raises(rt.OomExhaustedError) as info:
        rt.run_with_oom_fallback(kind, {"batch_size": 16}, attempt, manifest=manifest)
    assert info.value.error_class == "oom"
    assert info.value.attempts == 3
    assert info.value.params["batch_size"] == 4
    assert [c["batch_size"] for c in calls] == [16, 8, 4]  # no fourth attempt
    assert len(manifest["fallbacks"]) == 2


@pytest.mark.req("FR-011-44")
def test_a_stage_without_out_of_memory_runs_once_and_records_no_fallback() -> None:
    attempt, calls = scripted(0)
    manifest: dict = {}
    rt.run_with_oom_fallback("gns", {"batch_size": 16}, attempt, manifest=manifest)
    assert len(calls) == 1
    assert manifest.get("fallbacks", []) == []
    assert manifest.get("oom_fallback", False) is False


@pytest.mark.req("FR-011-44")
def test_calibration_halves_the_particle_count_once() -> None:
    attempt, calls = scripted(1)
    manifest: dict = {}
    result = rt.run_with_oom_fallback("calibration", {"particle_count": 4000, "budget": 60}, attempt, manifest=manifest)
    assert [c["particle_count"] for c in calls] == [4000, 2000]
    assert result["trained_with"]["particle_count"] == 2000
    assert manifest["fallbacks"] == [{"param": "particle_count", "from": 4000, "to": 2000, "reason": "oom"}]
    assert manifest["oom_fallback"] is True


@pytest.mark.req("FR-011-44")
def test_a_second_calibration_out_of_memory_is_final() -> None:
    attempt, calls = scripted(2)
    with pytest.raises(rt.OomExhaustedError) as info:
        rt.run_with_oom_fallback("calibration", {"particle_count": 4000}, attempt, manifest={})
    assert info.value.attempts == 2
    assert [c["particle_count"] for c in calls] == [4000, 2000]


@pytest.mark.req("FR-011-44")
@pytest.mark.parametrize(
    ("kind", "param"), [("gns", "batch_size"), ("fno", "batch_size"), ("calibration", "particle_count")]
)
def test_a_value_that_cannot_be_halved_below_one_stops_at_once(kind: str, param: str) -> None:
    attempt, calls = scripted(1)
    with pytest.raises(rt.OomExhaustedError):
        rt.run_with_oom_fallback(kind, {param: 1}, attempt, manifest={})
    assert len(calls) == 1


@pytest.mark.req("FR-011-44")
def test_other_exceptions_propagate_untouched_without_a_retry() -> None:
    calls: list[int] = []

    def attempt(params: dict):
        calls.append(1)
        raise ValueError("bad config")

    manifest: dict = {}
    with pytest.raises(ValueError, match="bad config"):
        rt.run_with_oom_fallback("gns", {"batch_size": 16}, attempt, manifest=manifest)
    assert calls == [1]
    assert manifest.get("fallbacks", []) == []


@pytest.mark.req("FR-011-44")
def test_the_callers_parameters_are_not_modified() -> None:
    params = {"batch_size": 16, "lr": 1e-3}
    attempt, _ = scripted(2)
    rt.run_with_oom_fallback("gns", params, attempt, manifest={})
    assert params == {"batch_size": 16, "lr": 1e-3}


@pytest.mark.req("FR-011-44")
@pytest.mark.parametrize("kind", ["", "perception", "GNS", "calibrate"])
def test_an_unknown_stage_kind_is_refused(kind: str) -> None:
    with pytest.raises(ValueError, match="kind"):
        rt.run_with_oom_fallback(kind, {"batch_size": 16}, lambda p: None, manifest={})


@pytest.mark.req("FR-011-44")
@pytest.mark.parametrize(
    "params", [{}, {"batch_size": 0}, {"batch_size": -4}, {"batch_size": 2.5}, {"batch_size": "16"}]
)
def test_a_missing_or_invalid_halved_parameter_is_refused_before_the_first_attempt(params: dict) -> None:
    calls: list[int] = []
    with pytest.raises(ValueError, match="batch_size"):
        rt.run_with_oom_fallback("gns", params, lambda p: calls.append(1), manifest={})
    assert calls == []


# ------------------------------------------------------------------ calibration through the driver


class OomSim(FakeDem):
    """A simulator that runs out of device memory above `limit` particles."""

    def __init__(self, particle_count: int, limit: int) -> None:
        super().__init__(24.0, 20.0, sigma=0.05, particle_count=particle_count)
        self.limit = limit

    def _check(self) -> None:
        if self.particle_count > self.limit:
            raise FakeOom(OOM_MESSAGE)

    def theta(self, mu: float, seed: int) -> float:
        self._check()
        return super().theta(mu, seed)

    def theta_and_grad(self, mu: float, seed: int):
        self._check()
        return super().theta_and_grad(mu, seed)


def request(count: int) -> dict:
    return default_request(arm="cma-es", budget=16, particle_count=count)


@pytest.mark.req("FR-011-44")
def test_the_calibration_driver_halves_the_particle_count_once_and_flags_the_trial() -> None:
    made: list[OomSim] = []

    def factory(n: int) -> OomSim:
        made.append(OomSim(n, limit=3000))
        return made[-1]

    manifest: dict = {}
    doc = driver.calibrate_with_oom_fallback(request(4000), factory, manifest=manifest)
    assert [s.particle_count for s in made] == [4000, 2000]
    assert doc["particle_count"] == 2000
    assert doc["oom_fallback"] is True
    assert manifest["fallbacks"] == [{"param": "particle_count", "from": 4000, "to": 2000, "reason": "oom"}]


@pytest.mark.req("FR-011-44")
def test_the_calibration_driver_reports_no_fallback_when_memory_suffices() -> None:
    doc = driver.calibrate_with_oom_fallback(request(2000), lambda n: OomSim(n, limit=3000), manifest={})
    assert doc["particle_count"] == 2000
    assert doc["oom_fallback"] is False


@pytest.mark.req("FR-011-44")
def test_the_calibration_driver_stops_with_oom_when_the_halved_count_still_does_not_fit() -> None:
    with pytest.raises(rt.OomExhaustedError) as info:
        driver.calibrate_with_oom_fallback(request(4000), lambda n: OomSim(n, limit=1000), manifest={})
    assert info.value.error_class == "oom"
    assert info.value.attempts == 2
