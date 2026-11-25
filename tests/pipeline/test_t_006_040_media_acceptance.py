# ruff: noqa: E501, PT018
"""T-006-040: acceptance on the published runs (data-and-models phase): encode time, VMAF and budgets per clip, throughput and
encoder records present.

Requirements: NFR-006-01, SC-006-01, SC-006-02.

Spec: specs/006-media-telemetry/spec.md section 5 (NFR-006-01: encode time of one clip pair (30 s, 1080p30) including the VMAF search <= 5 min
on the reference machine, measured by the run manifest's `wall_s`; SC-006-01: every published clip pair meets the VMAF targets (mean >= 93,
5th percentile >= 85) or carries a recorded relaxation, and the 25 MB pair budget, 100 % of clips; SC-006-02: every published run of a studio
GPU stage carries a throughput, and every published encode carries encoder records for both variants and an `nvenc_util_pct` summary or its
"unavailable" reason, 100 %) and spec 002 (the published run manifest is `web/public/assets/runs/<run_id>/manifest.json`, FR-002-48, DC-002-03).

Oracle: the published run manifests themselves, read with `json` and checked by the numeric thresholds of the spec; no code under test is used.
This acceptance test is red until the data-and-models phase publishes the first encode runs: it asserts that such runs exist.

Expected layout: `web/public/assets/runs/<run_id>/manifest.json` (a run manifest of `contracts/manifest.schema.json`), and the run's encode
report `web/public/assets/runs/<run_id>/encode-report.json` (DC-006-02) next to it. Stages are `manifest["stages"]` (each with `key.id`,
`status`, `wall_s`, `throughput`, `telemetry`); video artefacts are `manifest["artefacts"]` entries of kind `video` with their `encoder` record.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "web" / "public" / "assets" / "runs"
GPU_STAGES = {"st50_physics", "st56_encode"}
PAIR_MAX = 25_000_000


def published_runs() -> list[tuple[Path, dict]]:
    if not RUNS.is_dir():
        return []
    out = []
    for m in sorted(RUNS.glob("*/manifest.json")):
        doc = json.loads(m.read_text(encoding="utf-8"))
        if doc.get("kind") == "run":
            out.append((m.parent, doc))
    return out


def encode_stages(doc: dict) -> list[dict]:
    return [s for s in doc["stages"] if s["key"]["id"] == "st56_encode" and s["status"] == "succeeded"]


def encode_runs() -> list[tuple[Path, dict]]:
    return [(d, doc) for d, doc in published_runs() if encode_stages(doc)]


def videos(doc: dict) -> list[dict]:
    return [a for a in doc["artefacts"] if a["kind"] == "video"]


@pytest.mark.req("SC-006-01")
def test_the_data_phase_has_published_at_least_one_encode_run():
    runs = encode_runs()
    assert runs, (
        f"no published run under {RUNS.relative_to(ROOT)} contains a succeeded st56_encode stage (data-and-models phase)"
    )


@pytest.mark.req("NFR-006-01")
def test_every_published_encode_stage_took_at_most_five_minutes_per_30_seconds_of_video():
    runs = encode_runs()
    assert runs, "no published encode run"
    for d, doc in runs:
        durations = [a["encoder"]["duration_s"] for a in videos(doc)]
        longest = max(durations, default=30.0)
        budget = 300.0 * max(1.0, longest / 30.0)  # 5 min for a 30 s clip pair; proportionally more for longer clips
        for s in encode_stages(doc):
            assert s["wall_s"] <= budget, f"{d.name}: st56_encode wall_s {s['wall_s']} > {budget}"


@pytest.mark.req("SC-006-01")
def test_every_published_clip_meets_the_vmaf_targets_or_records_a_relaxation():
    runs = encode_runs()
    assert runs, "no published encode run"
    for d, doc in runs:
        report = json.loads((d / "encode-report.json").read_text(encoding="utf-8"))
        relaxed = {c["clip"] for c in report["clips"] if c["relaxation"] is not None}
        for a in videos(doc):
            clip = Path(a["path"]).name.split(".")[0]
            v = a["encoder"]["vmaf"]
            assert v["model"] == "vmaf_v0.6.1"
            if clip in relaxed:
                assert v["mean"] >= 80.0, f"{d.name}/{a['path']}: relaxed mean VMAF below the floor of 80"
            else:
                assert v["mean"] >= 93.0 and v["p5"] >= 85.0, (
                    f"{d.name}/{a['path']}: VMAF {v} misses 93/85 and no relaxation is recorded"
                )


@pytest.mark.req("SC-006-01")
def test_every_published_clip_pair_fits_25_million_bytes():
    runs = encode_runs()
    assert runs, "no published encode run"
    for d, doc in runs:
        per_clip: dict[str, int] = {}
        for a in videos(doc):
            clip = Path(a["path"]).name.split(".")[0]
            per_clip[clip] = per_clip.get(clip, 0) + a["bytes"]
        assert per_clip and all(total <= PAIR_MAX for total in per_clip.values()), f"{d.name}: {per_clip}"


@pytest.mark.req("SC-006-02")
def test_every_published_clip_has_an_encoder_record_for_both_variants():
    runs = encode_runs()
    assert runs, "no published encode run"
    for d, doc in runs:
        codecs: dict[str, set[str]] = {}
        for a in videos(doc):
            clip = Path(a["path"]).name.split(".")[0]
            assert "encoder" in a, f"{d.name}/{a['path']}: no encoder record"
            codecs.setdefault(clip, set()).add(a["encoder"]["codec"])
        assert codecs and all(c == {"av1", "h264"} for c in codecs.values()), f"{d.name}: {codecs}"


@pytest.mark.req("SC-006-02")
def test_every_published_gpu_stage_carries_a_throughput():
    runs = [(d, doc) for d, doc in published_runs() if any(s["key"]["id"] in GPU_STAGES for s in doc["stages"])]
    assert runs, "no published run of a studio GPU stage"
    for d, doc in runs:
        for s in doc["stages"]:
            if s["key"]["id"] in GPU_STAGES and s["status"] == "succeeded":
                t = s.get("throughput")
                assert (
                    t
                    and t["value"] > 0
                    and t["unit"] in {"particle-steps/s", "cell-steps/s", "vehicle-steps/s", "frames/s"}
                ), f"{d.name}/{s['key']}: {t}"


@pytest.mark.req("SC-006-02")
def test_every_published_encode_carries_nvenc_utilisation_or_the_reason_it_is_unavailable():
    runs = encode_runs()
    assert runs, "no published encode run"
    for d, doc in runs:
        for s in encode_stages(doc):
            tel = s["telemetry"]
            assert isinstance(tel, dict), f"{d.name}: st56_encode without a telemetry summary"
            if tel.get("nvenc_util_pct") is None:
                assert tel.get("unavailable", {}).get("nvenc_util_pct"), (
                    f"{d.name}: nvenc_util_pct is null without a stated reason"
                )
