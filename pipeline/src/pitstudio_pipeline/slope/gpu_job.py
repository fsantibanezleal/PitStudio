"""The C1 forecaster GPU job: TCN, PatchTST and Chronos-Bolt (zero-shot and fine-tuned), at most 2 GPU-h in total
(NFR-010-06).

One queue job (see the GPU queue protocol): takes the machine lock ``gpu0.compute`` and the in-run thermal guard through
the shared ``GpuSession`` of the GNS job, refuses to start above 80 C, saves atomic per-arm checkpoints (resumable: exit
5 after a guard stop, put the script back in ``jobs``), halves the batch on a CUDA out-of-memory error at most twice,
uses bf16 autocast for PatchTST and Chronos-Bolt, and records the measured GPU hours of every arm in its manifest.

Data: seeded Voight events (``pitstudio.slope.events``) at the nominal SNR 30 (the observed SNR is unavailable: the de
Wit archive states no failure time, FR-010-17), training pairs from the training split only (FR-010-15);
hyper-parameters (the learning rate) are chosen on the validation split only. Evaluation on the three nominal test
strata by ``s50.evaluate``.
``--dry-run`` asserts ``torch.cuda.is_available()`` and runs a tiny CPU version of the whole pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

from pitstudio.slope import budget, events, runtime
from pitstudio_pipeline.slope import chronos, data, export, infer, models, s50, train
from pitstudio_pipeline.surrogates.gns import run_train as gns_job

ARMS = ("tcn", "patchtst", "chronos_bolt_fine_tuned")
EXIT_STOPPED = 5
SIZES = {
    "full": {
        "train": 20_000,
        "validation": 1_000,
        "test": 500,
        "n_samples": 2000,
        "cutoffs": 8,
        "epochs": 6,
        "batch": 256,
    },
    "dry": {"train": 24, "validation": 6, "test": 3, "n_samples": 256, "cutoffs": 4, "epochs": 1, "batch": 32},
}
LEARNING_RATES = (1e-3, 3e-3)


def _config(size: dict[str, int]) -> dict[str, Any]:
    cfg = events.default_config(None)
    cfg["n_samples"] = size["n_samples"]
    cfg["splits"] = {
        "train": {"start": 0, "count": size["train"]},
        "validation": {"start": 1_000_000, "count": size["validation"]},
        "test": {"start": 2_000_000, "count_per_stratum": size["test"]},
    }
    return cfg


def _pairs(
    split_seeds: list[int], cfg: dict[str, Any], split: str, cutoffs: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    ctx, tgt = [], []
    grid = data.TRAIN_CUTOFFS
    for seed in split_seeds:
        doc = events.synthesize_event(
            seed, stratum="nominal_30", snr_obs=None, n_samples=cfg["n_samples"], split=split, config=cfg
        )
        pick = rng.choice(len(grid), size=min(cutoffs, len(grid)), replace=False)
        c, t = data.training_pairs([doc], [grid[i] for i in pick], split)
        ctx.append(c)
        tgt.append(t)
    return np.concatenate(ctx), np.concatenate(tgt)


def _fit(
    net: torch.nn.Module,
    arm: str,
    ctx: np.ndarray,
    tgt: np.ndarray,
    lr: float,
    epochs: int,
    batch: int,
    device: str,
    session: Any,
    ckpt: Path | None,
    seed: int,
) -> list[float]:
    """Pinball training with a per-step guard check and an atomic per-epoch checkpoint (resumable)."""
    torch.manual_seed(seed)
    net.to(device).train()
    x, y = torch.as_tensor(ctx), torch.as_tensor(tgt)
    opt = torch.optim.AdamW(net.parameters(), lr=lr)
    history: list[float] = []
    start = 0
    if ckpt is not None and ckpt.exists():
        state = torch.load(ckpt, map_location=device)
        net.load_state_dict(state["model"])
        opt.load_state_dict(state["opt"])
        history, start = state["history"], state["epoch"]
    amp = runtime.autocast_dtype(arm if arm in runtime.ARMS else "tcn", device) == "bfloat16"
    gen = torch.Generator().manual_seed(seed)
    for epoch in range(start, epochs):
        gen.manual_seed(seed + epoch)
        order = torch.randperm(len(x), generator=gen)
        total, count = 0.0, 0
        for lo in range(0, len(x), batch):
            idx = order[lo : lo + batch]
            xb, yb = x[idx].to(device), y[idx].to(device)
            opt.zero_grad()
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=amp and device.startswith("cuda")):
                loss = net.loss(xb, yb) if hasattr(net, "loss") else train.pinball_loss(net(xb).float(), yb)
            loss.backward()
            opt.step()
            total += float(loss) * len(idx)
            count += len(idx)
            if session.step() == "cooldown":
                _save(ckpt, net, opt, history, epoch)
                session.cool_down()
        history.append(total / count)
        _save(ckpt, net, opt, history, epoch + 1)
    net.eval()
    return history


def _save(ckpt: Path | None, net: torch.nn.Module, opt: Any, history: list[float], epoch: int) -> None:
    if ckpt is None:
        return
    gns_job.atomic_save({"model": net.state_dict(), "opt": opt.state_dict(), "history": history, "epoch": epoch}, ckpt)


def _validation_loss(net: torch.nn.Module, ctx: np.ndarray, tgt: np.ndarray, device: str) -> float:
    net.eval().to(device)
    with torch.no_grad():
        x, y = torch.as_tensor(ctx).to(device), torch.as_tensor(tgt).to(device)
        out = net.loss(x, y) if hasattr(net, "loss") else train.pinball_loss(net(x).float(), y)
    return float(out)


def run(args: argparse.Namespace) -> int:
    size = SIZES["dry" if args.dry_run else "full"]
    cuda = args.device == "cuda" and not args.dry_run
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = _config(size)
    events.validate_config(cfg)
    splits = events.make_splits(cfg)
    rng = np.random.default_rng(args.seed)
    data_file = out / "pairs.npz"
    if data_file.exists():
        z = np.load(data_file)
        tr_c, tr_t, va_c, va_t = z["tr_c"], z["tr_t"], z["va_c"], z["va_t"]
    else:
        tr_c, tr_t = _pairs(splits["train"], cfg, "train", size["cutoffs"], rng)
        va_c, va_t = _pairs(splits["validation"], cfg, "validation", size["cutoffs"], rng)
        np.savez(data_file, tr_c=tr_c, tr_t=tr_t, va_c=va_c, va_t=va_t)
    print(f"[job] pairs: train {len(tr_c)}, validation {len(va_c)}", flush=True)

    session = gns_job.GpuSession(
        Path(args.lock_dir), cuda=cuda, guard_module=gns_job.find_guard_module() if cuda else None
    )
    session.acquire()
    device = "cuda" if cuda else "cpu"
    manifests: list[dict[str, Any]] = []
    trained: dict[str, torch.nn.Module] = {}
    try:
        for arm in ARMS:
            done = out / f"{arm}.done.json"
            if done.exists():
                manifests.append(json.loads(done.read_text(encoding="utf-8")))
                state = torch.load(out / f"{arm}.pt", map_location="cpu")
                trained[arm] = _build(arm, args.weights_dir, state["model"])
                continue
            if arm == "chronos_bolt_fine_tuned" and not chronos.availability(args.weights_dir)["available"]:
                note = {
                    "arm": arm,
                    "run": False,
                    "reason": chronos.not_run_reason("fine-tuned", chronos.availability(args.weights_dir)),
                }
                manifests.append(note)
                continue
            started = time.monotonic()
            gpu_before = session.gpu_s + (time.time() - session._since if cuda else 0.0)

            def attempt(params: dict[str, Any], arm: str = arm) -> tuple[torch.nn.Module, float, list[float]]:
                best_lr, best = LEARNING_RATES[0], float("inf")
                for lr in LEARNING_RATES:  # hyper-parameter choice on the validation split only
                    probe = _build(arm, args.weights_dir, None)
                    _fit(
                        probe,
                        arm,
                        tr_c[: 4 * params["batch_size"]],
                        tr_t[: 4 * params["batch_size"]],
                        lr,
                        1,
                        params["batch_size"],
                        device,
                        session,
                        None,
                        args.seed,
                    )
                    score = _validation_loss(probe, va_c, va_t, device)
                    if score < best:
                        best_lr, best = lr, score
                net = _build(arm, args.weights_dir, None)
                hist = _fit(
                    net,
                    arm,
                    tr_c,
                    tr_t,
                    best_lr,
                    size["epochs"],
                    params["batch_size"],
                    device,
                    session,
                    out / f"{arm}.pt",
                    args.seed,
                )
                return net, best_lr, hist

            manifest: dict[str, Any] = {"arm": arm}
            net, lr, history = runtime.run_with_oom_fallback({"batch_size": size["batch"]}, attempt, manifest=manifest)
            net.cpu().eval()
            trained[arm] = net
            gpu_after = session.gpu_s + (time.time() - session._since if cuda else 0.0)
            seconds = time.monotonic() - started
            manifest.update(
                learning_rate=lr,
                history=history,
                validation_pinball=_validation_loss(net, va_c, va_t, "cpu"),
                gpu_hours=budget.gpu_hours_record(
                    arm, gpu_after - gpu_before if cuda else seconds, device="cuda" if cuda else "cpu"
                ),
            )
            torch.save({"model": net.state_dict()}, out / f"{arm}.pt")
            done.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            manifests.append(manifest)
    except Exception as exc:
        if exc.__class__.__name__ == "GuardStop":
            print(f"[job] guard stop: {exc}; checkpoints saved, put the script back in jobs to resume", flush=True)
            session.release()
            return EXIT_STOPPED
        raise
    finally:
        session.release()

    # evaluation on the nominal test strata (CPU), all methods on identical windows
    forecasters: dict[str, Any] = {arm: infer.TorchForecaster(m) for arm, m in trained.items()}
    av = chronos.availability(args.weights_dir)
    if av["available"]:
        forecasters["chronos_bolt_zero_shot"] = infer.TorchForecaster(
            chronos.build_arm("zero-shot", weights_dir=args.weights_dir).eval()
        )
    test_docs = [
        events.synthesize_event(
            seed, stratum=stratum, snr_obs=None, n_samples=cfg["n_samples"], split="test", config=cfg
        )
        for stratum, seeds in splits["test"].items()
        for seed in seeds
    ]
    predictions = data.predict_events(test_docs, forecasters, seed=args.seed)
    result = s50.evaluate(
        run_id="20261012T000000Z-c1-gpu",
        snr_basis="nominal",
        snr_obs=None,
        predictions=predictions,
        seeds={"acceptance": args.seed, "comparison": args.seed + 1},
    )
    s50.write_result(result, out / "ttf-results.json")
    total = budget.budget_report([m["gpu_hours"] for m in manifests if "gpu_hours" in m])
    (out / "training-manifest.json").write_text(
        json.dumps({"arms": manifests, "budget": total}, indent=2), encoding="utf-8"
    )
    golden = va_c[np.random.default_rng(args.seed).choice(len(va_c), size=200, replace=len(va_c) < 200)].copy()
    jobs = {arm: {"model": m, "contexts": golden} for arm, m in trained.items()}
    report = export.export_all(jobs, out_dir=out / "onnx", windows={}, cutoffs=[0.5, 0.8])
    (out / "export-report.json").write_text(
        json.dumps({"arms": report.arms, "notes": report.model_card_notes}, indent=2), encoding="utf-8"
    )
    print(f"[job] done: GPU hours {total['total_gpu_hours']:.3f} of {budget.BUDGET_GPU_HOURS}", flush=True)
    return 0


def _build(arm: str, weights_dir: str | None, state: dict[str, Any] | None) -> torch.nn.Module:
    net = (
        chronos.build_arm("fine-tuned", weights_dir=weights_dir)
        if arm == "chronos_bolt_fine_tuned"
        else models.build_model(arm, seed=0)
    )
    if state is not None:
        net.load_state_dict(state)
    return net


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lock-dir", default=os.environ.get("GPU_LOCK_DIR", "gpu-locks"))
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--seed", type=int, default=20261012)
    ap.add_argument("--weights-dir", default=os.environ.get(chronos.WEIGHTS_ENV))
    ap.add_argument(
        "--dry-run", action="store_true", help="assert CUDA, then run a tiny CPU version into a temporary folder"
    )
    args = ap.parse_args(argv)
    if args.dry_run:
        print("[dry-run] torch", torch.__version__, "cuda available", torch.cuda.is_available(), flush=True)
        assert torch.cuda.is_available(), (
            "a GPU job needs the CUDA build of torch: uv sync --extra cu130 --all-groups --locked in pipeline/"
        )
        args.out = tempfile.mkdtemp(prefix="c1-gpu-dry-", dir=os.environ.get("TMP"))
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
