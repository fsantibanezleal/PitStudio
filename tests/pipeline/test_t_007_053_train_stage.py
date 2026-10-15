# ruff: noqa: E501, PT018
"""T-007-053 (CPU half): training stage: bitwise resume on CPU with the fake GPU backend, OOM fallback (halve B, at most twice, then stop), seed-leak guard, recipe budgets.

Requirements: FR-007-26, FR-007-27, FR-007-28, NFR-007-05.

Spec: specs/007-haulage-dispatch/spec.md FR-007-26 (where a CUDA device passes the runner's guards, `s30_train` trains M4 (parameter-shared MLP) and M5 (dense attention) with PPO under the `gpu0.compute` lock, checkpoints after every
iteration block and resumes a stopped run from its last checkpoint; on the CPU device with the fake GPU backend a resumed run is bitwise identical to an uninterrupted run), FR-007-27 (CUDA out-of-memory: apply the recipe's declared fallback (halve B,
at most twice) and record each fallback in the manifest; a third out-of-memory error stops the stage with the log tail), FR-007-28 (a training or validation seed in the pre-registered test-seed set refuses to start with `SeedLeak`, in `s30_train` and
`s50_evaluate`; the test seeds are the first 8 bytes of SHA-256("pitstudio/a1/test/" + i), shifted right by one bit, for i = 0 ... n - 1 with n >= 30, committed in the evaluation recipe before any training run), NFR-007-05 (the recipe stage declares
`resources.vram_gib_est` <= 4 and `timeout_s` <= 18,000 (5 GPU-hours)), spec 002 FR-002-63 (the stage helper's `require_lock`) and plan.md (checkpoint every iteration block, resume, OOM fallback, seed-leak guard).

Oracle: the seed derivation recomputed here with `hashlib` (big-endian reading of the first 8 bytes: the spec does not state the byte order, see the report); bit-for-bit comparison of every parameter tensor and metric of an uninterrupted run with a stopped-and-resumed
run (`torch.equal`); a fake backend that raises `torch.OutOfMemoryError` on demand and records lock acquisitions; hand-counted fallbacks (batch 8 -> 4 -> 2, a third error stops); the recipe schema `contracts/recipe.schema.json` and the numeric limits of the spec.

Expected API:
    module `pitstudio_pipeline.dispatch.seeds`:   preregistered_seeds(n: int = 30) -> list[int]  (n >= 30 else ValueError; the derivation above, each value in [0, 2^63));   check_seed_leak(train_seeds, val_seeds, tests) -> None  raises `SeedLeak` naming every
        offending seed and whether it is a training or validation seed
    module `pitstudio_pipeline.dispatch.train`:
        TrainConfig(arch: "m4" | "m5", bundle: dict, iterations: int, block_iters: int, batch: int, decisions_per_iter: int = 32, epochs: int = 1, lr: float = 3e-4, gamma: float = 0.99, lam: float = 0.95, clip: float = 0.2, seed: int = 0,
                    seed_pool: Sequence[int], val_seed_pool: Sequence[int] = (), test_seeds: Sequence[int] | None = None, dt_s: float = 10.0, device: str = "cpu", oom_fallbacks: int = 2)   (a dataclass; `test_seeds` None = the
                    pre-registered set `preregistered_seeds(30)`)
        train(config, *, out_dir: Path, backend=None, resume: bool = False, max_blocks: int | None = None) -> TrainResult
            `backend` (default: the real device) provides `device: str`, `lock() -> context manager` (held for the whole run, released also on error) and `check(iteration: int, batch: int) -> None`, called before each iteration, which may raise
            `torch.OutOfMemoryError`; first action: `check_seed_leak(config.seed_pool, config.val_seed_pool, tests)` (SeedLeak before any environment or model exists); for `device == "cuda"` the stage helper's `require_lock("compute", 0)` runs first
            (LockNotHeldError); training runs `iterations` PPO iterations in blocks of `block_iters`; after every block it writes `<out_dir>/checkpoints/block_<k>.pt` (k from 1: model, optimiser, every generator state, metrics so far) and rewrites
            `<out_dir>/train-manifest.json`; `max_blocks` stops cleanly after that many blocks of this call; `resume=True` continues from the last checkpoint of `out_dir` (the final state is bitwise the uninterrupted state).
            On `torch.OutOfMemoryError` from `check` the iteration is retried with half the batch (at most `oom_fallbacks` times in total) and `{"iteration", "from_batch", "to_batch", "reason": "oom"}` is appended to the manifest's `fallbacks`;
            one more error raises an exception whose type name is `OutOfMemoryError` and whose message contains "CUDA out of memory" and the last log lines, with attribute `log_tail: list[str]` (non-empty).
        TrainResult(model_state: dict[str, Tensor], metrics: list[dict], manifest: dict, blocks_done: int); manifest keys: arch, iterations, block_iters, batch_initial, batch_final, fallbacks, checkpoints (relative file names in order), fixture (bool, from the bundle)
"""

from __future__ import annotations

import hashlib
import itertools
import json
import sys
from pathlib import Path

import pytest
import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_env as hand
import p007_kit as kit
from pitstudio_pipeline.dispatch import env as env_module
from pitstudio_pipeline.dispatch.seeds import check_seed_leak
from pitstudio_pipeline.dispatch.seeds import test_seeds as preregistered_seeds
from pitstudio_pipeline.dispatch.train import TrainConfig, train
from pitstudio_pipeline.haulage.errors import SeedLeak


def derive(i: int) -> int:
    return int.from_bytes(hashlib.sha256(f"pitstudio/a1/test/{i}".encode()).digest()[:8], "big") >> 1


class FakeBackend:
    """A fake GPU backend on the CPU device: records lock use and raises out-of-memory errors at the scripted iterations."""

    def __init__(self, oom_at=()):
        self.device, self.events, self.oom_at, self.calls = "cpu", [], list(oom_at), []

    def lock(self):
        import contextlib

        @contextlib.contextmanager
        def cm():
            self.events.append("acquire")
            try:
                yield
            finally:
                self.events.append("release")

        return cm()

    def check(self, iteration, batch):
        self.calls.append((iteration, batch))
        if self.oom_at and self.oom_at[0] == len(self.calls):
            self.oom_at.pop(0)
            raise torch.OutOfMemoryError("CUDA out of memory (fake)")


def cfg(arch="m4", **kw):
    base = {
        "arch": arch, "bundle": hand.family_bundle(3, horizon_s=1800.0), "iterations": 6, "block_iters": 2, "batch": 8, "decisions_per_iter": 8, "seed": 5,
        "seed_pool": list(range(100, 140)), "val_seed_pool": list(range(900, 910)), "dt_s": 10.0,
    }  # fmt: skip
    base.update(kw)
    return TrainConfig(**base)


def same_state(a, b):
    return a.keys() == b.keys() and all(torch.equal(a[k], b[k]) for k in a)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-28: the test seeds and the guard
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-28")
def test_the_test_seeds_are_the_shifted_first_eight_bytes_of_the_sha256_of_the_index_string():
    got = preregistered_seeds(30)
    assert got == [derive(i) for i in range(30)]
    assert len(set(got)) == 30 and all(0 <= s < 2**63 for s in got)
    assert preregistered_seeds(50)[:30] == got  # a longer list extends the first one


@pytest.mark.req("FR-007-28")
@pytest.mark.parametrize("n", [0, 1, 29, -1, 30.5, None, "30"])
def test_fewer_than_30_test_seeds_or_a_non_integer_count_is_rejected(n):
    with pytest.raises((ValueError, TypeError)):
        preregistered_seeds(n)


@pytest.mark.req("FR-007-28")
def test_the_guard_names_every_leaked_seed_and_where_it_was_used():
    tests = preregistered_seeds(30)
    check_seed_leak([1, 2, 3], [4, 5], tests)  # disjoint: fine
    with pytest.raises(SeedLeak) as ei:
        check_seed_leak([1, tests[3], 3], [tests[7], 5], tests)
    msg = str(ei.value)
    assert str(tests[3]) in msg and str(tests[7]) in msg and "train" in msg.lower() and "val" in msg.lower()


@pytest.mark.req("FR-007-28")
@pytest.mark.parametrize("where", ["seed_pool", "val_seed_pool"])
def test_training_refuses_to_start_on_a_leaked_seed_before_any_environment_exists(tmp_path, monkeypatch, where):
    def boom(*a, **k):
        raise AssertionError("an environment was built")

    monkeypatch.setattr(env_module.VectorEnv, "__init__", boom)
    leaked = preregistered_seeds(30)[11]
    kw = {where: [*cfg().seed_pool, leaked]} if where == "seed_pool" else {where: [leaked]}
    with pytest.raises(SeedLeak):
        train(cfg(**kw), out_dir=tmp_path, backend=FakeBackend())
    assert not list(tmp_path.glob("**/*.pt"))


@pytest.mark.req("FR-007-28")
def test_a_custom_test_seed_set_is_honoured(tmp_path):
    with pytest.raises(SeedLeak):
        train(cfg(test_seeds=[105]), out_dir=tmp_path, backend=FakeBackend())  # 105 is in the training pool


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-26: checkpoints, resume, lock
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-26")
@pytest.mark.parametrize("arch", ["m4", "m5"])
def test_a_run_is_deterministic_and_writes_one_checkpoint_per_block_and_a_manifest(tmp_path, arch):
    a = train(cfg(arch), out_dir=tmp_path / "a", backend=FakeBackend())
    b = train(cfg(arch), out_dir=tmp_path / "b", backend=FakeBackend())
    assert same_state(a.model_state, b.model_state) and a.metrics == b.metrics
    assert a.blocks_done == 3 and len(a.metrics) == 6
    assert sorted(p.name for p in (tmp_path / "a" / "checkpoints").glob("*.pt")) == [
        "block_1.pt",
        "block_2.pt",
        "block_3.pt",
    ]
    m = json.loads((tmp_path / "a" / "train-manifest.json").read_text(encoding="utf-8"))
    assert (m["arch"], m["iterations"], m["block_iters"], m["batch_initial"], m["batch_final"], m["fallbacks"]) == (
        arch,
        6,
        2,
        8,
        8,
        [],
    )
    assert (
        m["checkpoints"] == ["checkpoints/block_1.pt", "checkpoints/block_2.pt", "checkpoints/block_3.pt"]
        and m["fixture"] is False
    )


@pytest.mark.req("FR-007-26")
@pytest.mark.parametrize("arch", ["m4", "m5"])
@pytest.mark.parametrize("stop_after", [1, 2])
def test_a_resumed_run_is_bitwise_identical_to_an_uninterrupted_run(tmp_path, arch, stop_after):
    full = train(cfg(arch), out_dir=tmp_path / "full", backend=FakeBackend())
    part = train(cfg(arch), out_dir=tmp_path / "part", backend=FakeBackend(), max_blocks=stop_after)
    assert part.blocks_done == stop_after and len(list((tmp_path / "part" / "checkpoints").glob("*.pt"))) == stop_after
    rest = train(cfg(arch), out_dir=tmp_path / "part", backend=FakeBackend(), resume=True)
    assert rest.blocks_done == 3 and same_state(
        rest.model_state, full.model_state
    )  # every parameter tensor, bit for bit
    assert rest.metrics == full.metrics  # and every logged metric, also those of the first part
    for k in (1, 2, 3):
        a = torch.load(tmp_path / "full" / "checkpoints" / f"block_{k}.pt", weights_only=False)
        b = torch.load(tmp_path / "part" / "checkpoints" / f"block_{k}.pt", weights_only=False)
        assert same_state(a["model"], b["model"]), k


@pytest.mark.req("FR-007-26")
def test_resuming_a_finished_run_changes_nothing(tmp_path):
    first = train(cfg(), out_dir=tmp_path, backend=FakeBackend())
    again = train(cfg(), out_dir=tmp_path, backend=FakeBackend(), resume=True)
    assert again.blocks_done == 3 and same_state(first.model_state, again.model_state)


@pytest.mark.req("FR-007-26")
def test_resume_without_a_checkpoint_starts_from_the_beginning(tmp_path):
    a = train(cfg(), out_dir=tmp_path / "a", backend=FakeBackend(), resume=True)
    b = train(cfg(), out_dir=tmp_path / "b", backend=FakeBackend())
    assert same_state(a.model_state, b.model_state)


@pytest.mark.req("FR-007-26")
def test_the_lock_is_held_for_the_whole_run_and_released_also_on_error(tmp_path):
    be = FakeBackend()
    train(cfg(iterations=2), out_dir=tmp_path / "ok", backend=be)
    assert be.events == ["acquire", "release"]
    be2 = FakeBackend(oom_at=[1, 2, 3])
    with pytest.raises(Exception, match="CUDA out of memory"):
        train(cfg(iterations=2), out_dir=tmp_path / "bad", backend=be2)
    assert be2.events == ["acquire", "release"]


@pytest.mark.req("FR-007-26")
@pytest.mark.parametrize("held", [None, "", "gpu0.nvenc", "gpu1.compute", "gpu0.compute,gpu0.compute"])
def test_a_cuda_run_without_the_compute_lock_raises_lock_not_held_before_touching_cuda(tmp_path, monkeypatch, held):
    from pitstudio_stagekit import LockNotHeldError

    if held is None:
        monkeypatch.delenv("PITSTUDIO_HELD_LOCKS", raising=False)
    else:
        monkeypatch.setenv("PITSTUDIO_HELD_LOCKS", held)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: (_ for _ in ()).throw(AssertionError("CUDA was probed")))
    with pytest.raises(LockNotHeldError):
        train(cfg(device="cuda"), out_dir=tmp_path)


@pytest.mark.req("FR-007-26")
@pytest.mark.parametrize(
    "bad",
    [
        {"iterations": 0},
        {"iterations": -1},
        {"block_iters": 0},
        {"batch": 0},
        {"batch": -2},
        {"arch": "m6"},
        {"lr": float("nan")},
        {"gamma": 1.5},
        {"lam": 0.0},
        {"block_iters": 7},
    ],
)
def test_invalid_configurations_are_rejected_before_any_work(tmp_path, bad):
    with pytest.raises(ValueError):  # noqa: PT011
        train(cfg(**bad), out_dir=tmp_path, backend=FakeBackend())
    assert not list(tmp_path.glob("**/*"))


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-27: out-of-memory fallback
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-27")
def test_one_out_of_memory_error_halves_the_batch_and_is_recorded(tmp_path):
    be = FakeBackend(oom_at=[3])  # the third `check` call fails: iteration 3 (index 2)
    r = train(cfg(), out_dir=tmp_path, backend=be)
    m = r.manifest
    assert m["batch_initial"] == 8 and m["batch_final"] == 4
    assert m["fallbacks"] == [{"iteration": 3, "from_batch": 8, "to_batch": 4, "reason": "oom"}]
    assert r.blocks_done == 3 and len(r.metrics) == 6
    assert [c for c in be.calls if c[0] <= 3 and c[1] == 8] and all(
        b == 4 for it, b in be.calls if it >= 4
    )  # the retry and everything after run with half the batch
    assert json.loads((tmp_path / "train-manifest.json").read_text(encoding="utf-8"))["fallbacks"] == m["fallbacks"]


@pytest.mark.req("FR-007-27")
def test_two_fallbacks_are_allowed_and_recorded_in_order(tmp_path):
    be = FakeBackend(oom_at=[2, 3])  # a retry that fails again falls back once more
    r = train(cfg(), out_dir=tmp_path, backend=be)
    assert [(f["from_batch"], f["to_batch"]) for f in r.manifest["fallbacks"]] == [(8, 4), (4, 2)] and r.manifest[
        "batch_final"
    ] == 2
    assert r.blocks_done == 3


@pytest.mark.req("FR-007-27")
def test_a_third_out_of_memory_error_stops_the_stage_with_the_log_tail(tmp_path):
    be = FakeBackend(oom_at=[2, 3, 4])
    with pytest.raises(Exception, match="CUDA out of memory") as ei:
        train(cfg(), out_dir=tmp_path, backend=be)
    e = ei.value
    assert (
        type(e).__name__ == "OutOfMemoryError" and e.log_tail and all(isinstance(x, str) for x in e.log_tail)
    )  # the stage helper maps this name to error_class oom
    m = json.loads((tmp_path / "train-manifest.json").read_text(encoding="utf-8"))
    assert len(m["fallbacks"]) == 2  # the two allowed fallbacks are on record, the third error was fatal


@pytest.mark.req("FR-007-27")
def test_the_fallback_budget_is_the_configured_number(tmp_path):
    with pytest.raises(Exception, match="CUDA out of memory"):
        train(
            cfg(oom_fallbacks=1), out_dir=tmp_path, backend=FakeBackend(oom_at=[2, 3])
        )  # one allowed, the second error is fatal
    r = train(cfg(oom_fallbacks=0, iterations=2), out_dir=tmp_path / "none", backend=FakeBackend())
    assert r.manifest["fallbacks"] == []


@pytest.mark.req("FR-007-27")
def test_a_batch_of_one_cannot_be_halved_further(tmp_path):
    with pytest.raises(Exception, match="CUDA out of memory"):
        train(cfg(batch=1), out_dir=tmp_path, backend=FakeBackend(oom_at=[1]))


# ---------------------------------------------------------------------------------------------------------------------
# fixtures and the recipe budget
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-46")
def test_a_fixture_bundle_marks_the_manifest_and_every_checkpoint(tmp_path):
    b = hand.family_bundle(3, horizon_s=1800.0)
    b["fixture"] = True
    r = train(cfg(bundle=b, iterations=2), out_dir=tmp_path, backend=FakeBackend())
    assert r.manifest["fixture"] is True
    assert torch.load(tmp_path / "checkpoints" / "block_1.pt", weights_only=False)["fixture"] is True


def a1_train_stages() -> list[dict]:
    path = kit.ROOT / "studio" / "recipes" / "cases" / "a1.yaml"
    assert path.is_file(), "the A1 recipe studio/recipes/cases/a1.yaml does not exist yet"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [s for s in doc["stages"] if s["id"] == "s30_train"]


@pytest.mark.req("NFR-007-05")
def test_the_a1_recipe_declares_both_training_stages_within_the_budget():
    stages = a1_train_stages()
    assert {s.get("params", {}).get("arch") for s in stages} >= {"m4", "m5"}
    for s in stages:
        r = s["resources"]
        assert r["gpu"] == "exclusive" and 0 < r["vram_gib_est"] <= 4 and 0 < s["timeout_s"] <= 18_000, s.get("params")


@pytest.mark.req("NFR-007-05")
def test_the_a1_recipe_is_valid_against_the_recipe_schema_and_commits_the_test_seeds():
    path = kit.ROOT / "studio" / "recipes" / "cases" / "a1.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = list(kit.schema_validator("recipe").iter_errors(doc))
    assert not errors, [e.message for e in errors][:3]
    text = path.read_text(encoding="utf-8")
    assert all(str(s) in text for s in preregistered_seeds(30)), (
        "the 30 pre-registered test seeds are not all committed in the recipe"
    )  # FR-007-28: committed before any training run


@pytest.mark.req("FR-007-27")
def test_the_a1_recipe_declares_the_halving_fallback_at_most_twice_for_each_training_stage():
    for s in a1_train_stages():
        steps = s["retry"]["oom_fallback"]
        assert 1 <= len(steps) <= 2, s.get("params")  # at most twice
        key = next(k for k in s["params"] if "batch" in k)  # the batch-size parameter
        sizes = [s["params"][key], *(step[key] for step in steps)]
        assert all(b == a // 2 for a, b in itertools.pairwise(sizes)), sizes  # each fallback halves B
