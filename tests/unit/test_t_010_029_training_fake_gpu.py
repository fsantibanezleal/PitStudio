"""T-010-029: forecaster training under the runner against the fake GPU backend (the CUDA smoke test is
tests/gpu/test_t_010_029_training_smoke.py, marked `gpu`, not part of this file).

Requirement: FR-010-33 ("Where a CUDA GPU is available, forecaster training shall run only through the runner under
`gpu0.compute`, honour `gpu0.hold`, use bf16 autocast for PatchTST and Chronos-Bolt, and on out-of-memory apply the
declared
fallback (batch halved, at most twice) recorded in the manifest; without a GPU it shall train on the CPU and record
that. These
behaviours shall be verified against the fake GPU backend").
Spec: specs/010-slope/spec.md section 3.3; plan.md row FR-010-33 ("the runner's fake GPU backend raising OOM twice;
expected manifest
records written in the test"); constitution principle 12 (the runner owns the GPU); spec 011's helper of the same shape
(`pitstudio.surrogate_runtime`, T-011-060), which the implementation may share.

Expected API (module `pitstudio.slope.runtime`, standard library only):
- `LockNotHeldError`, `GpuHoldError`, `OomExhaustedError` (Exception subclasses): `error_class` "lock-not-held",
  "hold", "oom";
  `OomExhaustedError` also has `attempts` and `params`.
- `require_gpu_lock(device, *, env)`: device "cpu" -> nothing; "cuda" or "cuda:N" -> `gpu<N>.compute` must be in
  `env["PITSTUDIO_HELD_LOCKS"] ` (sorted, comma-separated, distinct names of the form gpu<N>.compute / gpu<N>.nvenc,
  at most 4, each
  at most 64 characters); an unset, empty or malformed value or an unknown device string raises LockNotHeldError /
  ValueError.
- `check_hold(device, *, lock_dir)`: for "cuda"/"cuda:0" GpuHoldError when `<lock_dir>/gpu0.hold` exists; "cpu":
  nothing.
- `is_cuda_oom(exc) -> bool`: True for `torch.cuda.OutOfMemoryError` (by class name) and for a RuntimeError or
  MemoryError whose
  message contains "out of memory" (any case).
- `run_with_oom_fallback(params, attempt, *, manifest) -> object`: calls `attempt(params_copy)`; on a CUDA
  out-of-memory error halves
  `batch_size` (16 -> 8 -> 4: at most two halvings, three attempts), records each halving in `manifest["fallbacks"]`
  as {"param":
  "batch_size", "from", "to", "reason": "oom"} and sets `manifest["oom_fallback"] = True`; a third out-of-memory error
  raises
  OomExhaustedError (a batch below 1 too); any other exception propagates untouched without a retry; the caller's
  params are not
  modified.
- `autocast_dtype(arm, device) -> str | None`: "bfloat16" for the arms patchtst, chronos_bolt_zero_shot and
  chronos_bolt_fine_tuned on a CUDA
  device; None for tcn and for every arm on the CPU. ValueError for an unknown arm or device.
- `resolve_device(*, cuda_available, env, lock_dir) -> {"device", "note"}`: no CUDA device -> {"device": "cpu",
  "note": "no CUDA
  device: trained on the CPU"}; CUDA available -> the lock check then the hold check, then {"device": "cuda", "note":
  None}.

Oracles: the fake backend of this file (held-lock variable, hold file in a temporary directory, a scripted attempt
function that
raises the CUDA out-of-memory message a chosen number of times) and the declared fallbacks by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pitstudio.slope import runtime as rt

OOM = "CUDA out of memory. Tried to allocate 2.00 GiB (GPU 0; 15.99 GiB total capacity)"


class FakeOom(RuntimeError):
    pass


def scripted(fail_times: int):
    calls: list[dict] = []

    def attempt(params: dict):
        calls.append(dict(params))
        if len(calls) <= fail_times:
            raise FakeOom(OOM)
        return {"trained_with": dict(params)}

    return attempt, calls


@pytest.mark.req("FR-010-33")
@pytest.mark.parametrize("device", ["cuda", "cuda:0"])
def test_a_gpu_training_needs_gpu0_compute_in_the_held_locks(device) -> None:
    rt.require_gpu_lock(device, env={"PITSTUDIO_HELD_LOCKS": "gpu0.compute"})
    rt.require_gpu_lock(device, env={"PITSTUDIO_HELD_LOCKS": "gpu0.compute,gpu0.nvenc"})
    for held in ("", "gpu0.nvenc", "gpu1.compute"):
        with pytest.raises(rt.LockNotHeldError) as info:
            rt.require_gpu_lock(device, env={"PITSTUDIO_HELD_LOCKS": held})
        assert info.value.error_class == "lock-not-held"
    with pytest.raises(rt.LockNotHeldError):
        rt.require_gpu_lock(device, env={})


@pytest.mark.req("FR-010-33")
@pytest.mark.parametrize("malformed", ["GPU0.compute", "gpu0.compute,gpu0.compute", "gpu0.render", "x" * 65])
def test_a_malformed_held_locks_value_is_refused_like_no_lock(malformed) -> None:
    with pytest.raises(rt.LockNotHeldError):
        rt.require_gpu_lock("cuda", env={"PITSTUDIO_HELD_LOCKS": malformed})


@pytest.mark.req("FR-010-33")
def test_the_device_index_selects_the_lock_and_cpu_needs_none(tmp_path: Path) -> None:
    rt.require_gpu_lock("cuda:1", env={"PITSTUDIO_HELD_LOCKS": "gpu1.compute"})
    with pytest.raises(rt.LockNotHeldError):
        rt.require_gpu_lock("cuda:1", env={"PITSTUDIO_HELD_LOCKS": "gpu0.compute"})
    rt.require_gpu_lock("cpu", env={})
    (tmp_path / "gpu0.hold").write_text("hold", encoding="utf-8")
    rt.check_hold("cpu", lock_dir=tmp_path)  # the hold file is about the GPU only


@pytest.mark.req("FR-010-33")
@pytest.mark.parametrize("device", ["gpu", "CUDA", "cuda:x", "cuda:-1", "", "tpu", "cuda:0;rm"])
def test_an_unknown_device_string_is_refused(device) -> None:
    with pytest.raises((ValueError, rt.LockNotHeldError)):
        rt.require_gpu_lock(device, env={"PITSTUDIO_HELD_LOCKS": "gpu0.compute"})


@pytest.mark.req("FR-010-33")
@pytest.mark.parametrize("device", ["cuda", "cuda:0"])
def test_a_gpu_training_is_refused_while_the_hold_file_exists(tmp_path: Path, device) -> None:
    rt.check_hold(device, lock_dir=tmp_path)
    (tmp_path / "gpu0.hold").write_text("thermal", encoding="utf-8")
    with pytest.raises(rt.GpuHoldError) as info:
        rt.check_hold(device, lock_dir=tmp_path)
    assert info.value.error_class == "hold"


@pytest.mark.req("FR-010-33")
def test_cuda_out_of_memory_errors_are_recognised_by_class_name_or_message() -> None:
    class OutOfMemoryError(RuntimeError):  # the name of torch.cuda.OutOfMemoryError
        pass

    assert rt.is_cuda_oom(OutOfMemoryError("anything"))
    assert rt.is_cuda_oom(RuntimeError(OOM))
    assert rt.is_cuda_oom(MemoryError("Out Of Memory"))
    assert not rt.is_cuda_oom(RuntimeError("cuDNN error"))
    assert not rt.is_cuda_oom(ValueError("out of memory"))
    assert not rt.is_cuda_oom(KeyboardInterrupt())


@pytest.mark.req("FR-010-33")
def test_no_oom_means_one_attempt_and_no_fallback_record() -> None:
    attempt, calls = scripted(0)
    manifest: dict = {}
    out = rt.run_with_oom_fallback({"batch_size": 16, "lr": 1e-3}, attempt, manifest=manifest)
    assert out == {"trained_with": {"batch_size": 16, "lr": 1e-3}}
    assert len(calls) == 1
    assert manifest.get("fallbacks", []) == []
    assert not manifest.get("oom_fallback", False)


@pytest.mark.req("FR-010-33")
def test_oom_twice_halves_the_batch_twice_and_records_both_halvings_in_order() -> None:
    attempt, calls = scripted(2)
    manifest: dict = {}
    params = {"batch_size": 16, "lr": 1e-3}
    out = rt.run_with_oom_fallback(params, attempt, manifest=manifest)
    assert [c["batch_size"] for c in calls] == [16, 8, 4]
    assert out == {"trained_with": {"batch_size": 4, "lr": 1e-3}}
    assert manifest["fallbacks"] == [
        {"param": "batch_size", "from": 16, "to": 8, "reason": "oom"},
        {"param": "batch_size", "from": 8, "to": 4, "reason": "oom"},
    ]
    assert manifest["oom_fallback"] is True
    assert params == {"batch_size": 16, "lr": 1e-3}  # the caller's dict is untouched


@pytest.mark.req("FR-010-33")
def test_a_third_oom_stops_the_stage_with_error_class_oom() -> None:
    attempt, calls = scripted(3)
    manifest: dict = {}
    with pytest.raises(rt.OomExhaustedError) as info:
        rt.run_with_oom_fallback({"batch_size": 16}, attempt, manifest=manifest)
    assert info.value.error_class == "oom"
    assert info.value.attempts == 3
    assert info.value.params["batch_size"] == 4
    assert len(calls) == 3
    assert len(manifest["fallbacks"]) == 2


@pytest.mark.req("FR-010-33")
def test_a_batch_that_cannot_be_halved_exhausts_the_allowance() -> None:
    attempt, calls = scripted(5)
    with pytest.raises(rt.OomExhaustedError):
        rt.run_with_oom_fallback({"batch_size": 1}, attempt, manifest={})
    assert len(calls) == 1


@pytest.mark.req("FR-010-33")
def test_another_error_propagates_untouched_without_a_retry() -> None:
    calls: list[int] = []

    def attempt(params):
        calls.append(1)
        raise ValueError("bad shape")

    manifest: dict = {}
    with pytest.raises(ValueError, match="bad shape"):
        rt.run_with_oom_fallback({"batch_size": 16}, attempt, manifest=manifest)
    assert calls == [1]
    assert manifest.get("fallbacks", []) == []


@pytest.mark.req("FR-010-33")
@pytest.mark.parametrize(
    ("arm", "device", "expected"),
    [
        ("patchtst", "cuda", "bfloat16"),
        ("chronos_bolt_zero_shot", "cuda", "bfloat16"),
        ("chronos_bolt_fine_tuned", "cuda:0", "bfloat16"),
        ("tcn", "cuda", None),
        ("patchtst", "cpu", None),
        ("chronos_bolt_fine_tuned", "cpu", None),
        ("tcn", "cpu", None),
    ],
)
def test_bf16_autocast_is_used_for_patchtst_and_chronos_bolt_on_cuda_only(arm, device, expected) -> None:
    assert rt.autocast_dtype(arm, device) == expected


@pytest.mark.req("FR-010-33")
@pytest.mark.parametrize(("arm", "device"), [("lstm", "cuda"), ("tcn", "tpu"), ("", "cpu")])
def test_autocast_rejects_an_unknown_arm_or_device(arm, device) -> None:
    with pytest.raises(ValueError, match=r"."):
        rt.autocast_dtype(arm, device)


@pytest.mark.req("FR-010-33")
def test_without_a_cuda_device_training_falls_back_to_the_cpu_and_says_so(tmp_path: Path) -> None:
    choice = rt.resolve_device(cuda_available=False, env={}, lock_dir=tmp_path)
    assert choice == {"device": "cpu", "note": "no CUDA device: trained on the CPU"}
    (tmp_path / "gpu0.hold").write_text("hold", encoding="utf-8")
    assert (
        rt.resolve_device(cuda_available=False, env={}, lock_dir=tmp_path)["device"] == "cpu"
    )  # the hold is about the GPU


@pytest.mark.req("FR-010-33")
def test_with_a_cuda_device_the_runner_lock_and_the_hold_file_decide(tmp_path: Path) -> None:
    held = {"PITSTUDIO_HELD_LOCKS": "gpu0.compute"}
    assert rt.resolve_device(cuda_available=True, env=held, lock_dir=tmp_path) == {"device": "cuda", "note": None}
    with pytest.raises(rt.LockNotHeldError):
        rt.resolve_device(cuda_available=True, env={}, lock_dir=tmp_path)
    (tmp_path / "gpu0.hold").write_text("hold", encoding="utf-8")
    with pytest.raises(rt.GpuHoldError):
        rt.resolve_device(cuda_available=True, env=held, lock_dir=tmp_path)
