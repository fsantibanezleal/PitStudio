# ruff: noqa: E501
"""T-009-071 - FR-009-37, FR-009-38, NFR-009-01, NFR-009-02, NFR-009-06: live set, sizes, measured lanes, gallery budget.

Oracles (independent of the code under test; plan 009 test strategy rows FR-009-37 / FR-009-38, NFR rows):
- hand calculation: the allowed list of perception ONNX files in the web build is exactly {d-fine-n-fp16.onnx, d-fine-s-int8.onnx} (FR-009-37: D-FINE-N fp16 and D-FINE-S int8 static QDQ live; RF-DETR-Seg-N
  at every precision and D-FINE-S fp32 only as baked outputs); files of other models (a U-Net, a surrogate) are not perception files and are ignored; a third perception file, a missing one or a
  wrong precision is refused naming the file;
- boundary values of FR-009-38 and NFR-009-01/02 typed out from the spec and `specs/000-foundation/thresholds.yaml` (budgets.onnx_live_each_mb_max 25 MB = 25,000,000 bytes, lane_gate.run_s_max 1 s):
  size 25,000,000 B is live and 25,000,001 B is not; a T1 median of 299 ms and of 300 ms is live ("exceeds 300 ms" is strict), 301 ms is not; a T2 run of 1.0 s is live, 1.001 s is not; the web timing
  record needs >= 50 images and >= 5 warm-up runs (NFR-009-02);
- NFR-009-06: a gallery of 300 thumbnails is allowed, 301 is not, and the gallery is counted in the replay budget class `shards-clouds` (thresholds.yaml `replay_shards_and_clouds_mb_max`, FR-016-17);
- the shipping plan combines both rules by hand: with both live candidates inside their limits two ONNX files ship and every other variant (D-FINE-N fp32 / int8, D-FINE-S fp32 / fp16, RF-DETR-Seg-N x3)
  is baked only; a live candidate that exceeds a limit falls back to precompute (baked) with its reason.

Expected public API (module `pitstudio_pipeline.perception.export_hooks`, package under `pipeline/src/`; see tests/contract/test_t_009_070_onnx_signature.py for `initial_lane`):

    LIVE_ONNX_FILES: tuple[str, ...]        ("d-fine-n-fp16.onnx", "d-fine-s-int8.onnx")
    LaneError(Exception)                    .code: "live-set" | "gallery-too-large"; .files: tuple[str, ...]; str(error) contains the code and every file name
    check_web_perception_onnx(web_root: pathlib.Path) -> None
        Scans web_root recursively for `*.onnx` files whose base name starts with "d-fine-" or "rf-detr-"; the set of base names must equal LIVE_ONNX_FILES (each exactly once: a duplicate
        base name in two folders is an error). LaneError("live-set") names every unexpected and every missing file. Other `.onnx` files are ignored. A missing web_root raises FileNotFoundError.
    validate_timing_record(record: Mapping) -> None
        record = {"t1": {"median_ms": float, "images": int, "warmup_runs": int}, "t2": {"run_s": float}}: ValueError (message names the field: "median_ms", "images", "warmup_runs", "run_s", "t1", "t2")
        for a missing block, images < 50, warmup_runs < 5, a non-finite or negative time, or a non-int count (bool excluded).
    LaneDecision                            frozen dataclass: lane: "live" | "precompute"; reasons: tuple[str, ...] (each names "size", "t1" or "t2", or "not measured")
    decide_detector_lane(*, size_bytes: int, timing: Mapping | None) -> LaneDecision
        live iff size_bytes <= 25_000_000 and t1 median_ms <= 300 and t2 run_s <= 1.0; otherwise "precompute" with a reason per violated limit; timing None gives "precompute" with the reason
        "not measured". A timing record that fails validate_timing_record raises its ValueError; size_bytes must be an int >= 1 (ValueError naming "size_bytes").
    shipping_plan(variants: Sequence[Mapping]) -> dict
        variants: {"model": str, "precision": str, "size_bytes": int, "timing": Mapping | None} for any of the nine model x precision pairs. Returns {"onnx_files": [...], "baked_only": [...],
        "reasons": {"<model>-<precision>": [..]}}: a pair ships as an ONNX file only if it is one of LIVE_ONNX_FILES and decide_detector_lane says live; every other pair is baked only (lists sorted by name,
        names "<model>-<precision>.onnx" for onnx_files and "<model>-<precision>" for baked_only); `reasons` holds the decision reasons of a live candidate that fell back.
    gallery_budget(thumbnails: Sequence[Mapping]) -> dict
        thumbnails: {"path": str, "bytes": int}; returns {"count": n, "bytes": total, "budget_class": "shards-clouds"}; LaneError("gallery-too-large") for more than 300 thumbnails;
        ValueError (message names "thumbnails" or "bytes") for a non-mapping entry or a negative / non-int byte count.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.perception import export_hooks as hooks  # noqa: E402

LIVE = ("d-fine-n-fp16.onnx", "d-fine-s-int8.onnx")
MODELS = ("d-fine-n", "d-fine-s", "rf-detr-seg-n")
PRECISIONS = ("fp32", "fp16", "int8")


def _web(tmp_path: Path, names: list[str], folder: str = "models") -> Path:
    d = tmp_path / "web" / folder
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_bytes(b"onnx")
    return tmp_path / "web"


def _timing(median: float = 120.0, run_s: float = 0.4, images: int = 50, warmup: int = 5) -> dict:
    return {"t1": {"median_ms": median, "images": images, "warmup_runs": warmup}, "t2": {"run_s": run_s}}


# ---------------------------------------------------------------- FR-009-37


@pytest.mark.req("FR-009-37")
def test_the_live_set_is_the_two_named_files() -> None:
    assert tuple(hooks.LIVE_ONNX_FILES) == LIVE


@pytest.mark.req("FR-009-37")
def test_a_web_build_with_exactly_the_two_live_files_passes_and_other_models_are_ignored(tmp_path: Path) -> None:
    web = _web(tmp_path, [*LIVE, "unet-int8.onnx", "gns-surrogate-fp16.onnx"])
    assert hooks.check_web_perception_onnx(web) is None


@pytest.mark.req("FR-009-37")
@pytest.mark.parametrize(
    "extra",
    [
        "d-fine-s-fp32.onnx",
        "rf-detr-seg-n-fp16.onnx",
        "rf-detr-seg-n-fp32.onnx",
        "rf-detr-seg-n-int8.onnx",
        "d-fine-n-fp32.onnx",
        "d-fine-n-int8.onnx",
        "d-fine-s-fp16.onnx",
    ],
)
def test_a_third_perception_file_is_refused_by_name(tmp_path: Path, extra: str) -> None:
    web = _web(tmp_path, [*LIVE, extra])
    with pytest.raises(hooks.LaneError) as exc:
        hooks.check_web_perception_onnx(web)
    assert exc.value.code == "live-set"
    assert extra in exc.value.files
    assert extra in str(exc.value)
    assert "live-set" in str(exc.value)


@pytest.mark.req("FR-009-37")
@pytest.mark.parametrize("missing", LIVE)
def test_a_missing_live_file_is_refused_by_name(tmp_path: Path, missing: str) -> None:
    web = _web(tmp_path, [n for n in LIVE if n != missing])
    with pytest.raises(hooks.LaneError) as exc:
        hooks.check_web_perception_onnx(web)
    assert missing in exc.value.files


@pytest.mark.req("FR-009-37")
def test_every_unexpected_and_missing_file_is_listed_and_subfolders_are_scanned(tmp_path: Path) -> None:
    web = _web(tmp_path, ["d-fine-n-fp16.onnx", "rf-detr-seg-n-fp32.onnx"], folder="models")
    _web(tmp_path, ["d-fine-s-fp32.onnx"], folder="deep/er/dir")
    with pytest.raises(hooks.LaneError) as exc:
        hooks.check_web_perception_onnx(web)
    assert set(exc.value.files) == {"rf-detr-seg-n-fp32.onnx", "d-fine-s-fp32.onnx", "d-fine-s-int8.onnx"}


@pytest.mark.req("FR-009-37")
def test_a_live_file_present_twice_is_refused_and_an_empty_build_is_refused(tmp_path: Path) -> None:
    web = _web(tmp_path, list(LIVE))
    _web(tmp_path, ["d-fine-n-fp16.onnx"], folder="copy")
    with pytest.raises(hooks.LaneError) as exc:
        hooks.check_web_perception_onnx(web)
    assert "d-fine-n-fp16.onnx" in exc.value.files
    empty = tmp_path / "empty" / "web"
    empty.mkdir(parents=True)
    with pytest.raises(hooks.LaneError) as exc2:
        hooks.check_web_perception_onnx(empty)
    assert set(exc2.value.files) == set(LIVE)
    with pytest.raises(FileNotFoundError):
        hooks.check_web_perception_onnx(tmp_path / "absent")


# ---------------------------------------------------------------- NFR-009-02: the timing record


@pytest.mark.req("NFR-009-02")
def test_a_timing_record_with_50_images_and_5_warm_up_runs_is_valid() -> None:
    assert hooks.validate_timing_record(_timing(images=50, warmup=5)) is None
    assert hooks.validate_timing_record(_timing(images=500, warmup=20)) is None


@pytest.mark.req("NFR-009-02")
@pytest.mark.parametrize(
    ("record", "arg"),
    [
        (_timing(images=49), "images"),
        (_timing(warmup=4), "warmup_runs"),
        (_timing(median=float("nan")), "median_ms"),
        (_timing(median=-1.0), "median_ms"),
        (_timing(median=float("inf")), "median_ms"),
        (_timing(run_s=float("nan")), "run_s"),
        (_timing(run_s=-0.1), "run_s"),
        ({"t1": _timing()["t1"]}, "t2"),
        ({"t2": _timing()["t2"]}, "t1"),
        ({}, "t1"),
        ({"t1": _timing()["t1"], "t2": {}}, "run_s"),
        ({"t1": {**_timing()["t1"], "images": 50.5}, "t2": _timing()["t2"]}, "images"),
        ({"t1": {**_timing()["t1"], "images": True}, "t2": _timing()["t2"]}, "images"),
        ({"t1": {**_timing()["t1"], "median_ms": "120"}, "t2": _timing()["t2"]}, "median_ms"),
    ],
)
def test_a_hostile_timing_record_is_rejected_naming_the_field(record: dict, arg: str) -> None:
    with pytest.raises(ValueError, match=arg):
        hooks.validate_timing_record(record)


# ---------------------------------------------------------------- FR-009-38 and NFR-009-01


@pytest.mark.req("FR-009-38")
@pytest.mark.req("NFR-009-01")
@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (8_000_000, "live"),
        (10_000_000, "live"),
        (25_000_000, "live"),
        (25_000_001, "precompute"),
        (95_000_000, "precompute"),
    ],
)
def test_the_size_cap_is_25_million_bytes(size: int, expected: str) -> None:
    d = hooks.decide_detector_lane(size_bytes=size, timing=_timing())
    assert d.lane == expected
    assert (d.reasons == ()) == (expected == "live")
    if expected == "precompute":
        assert any("size" in r for r in d.reasons)


@pytest.mark.req("FR-009-38")
@pytest.mark.req("NFR-009-02")
@pytest.mark.parametrize(
    ("median", "expected"),
    [
        (10.0, "live"),
        (299.0, "live"),
        (300.0, "live"),
        (300.0001, "precompute"),
        (301.0, "precompute"),
        (2000.0, "precompute"),
    ],
)
def test_the_t1_median_cap_is_300_ms_and_exceeding_it_is_strict(median: float, expected: str) -> None:
    d = hooks.decide_detector_lane(size_bytes=9_000_000, timing=_timing(median=median))
    assert d.lane == expected
    if expected == "precompute":
        assert any("t1" in r for r in d.reasons)


@pytest.mark.req("FR-009-38")
@pytest.mark.req("NFR-009-02")
@pytest.mark.parametrize(
    ("run_s", "expected"), [(0.05, "live"), (1.0, "live"), (1.001, "precompute"), (30.0, "precompute")]
)
def test_the_t2_run_cap_is_one_second(run_s: float, expected: str) -> None:
    d = hooks.decide_detector_lane(size_bytes=9_000_000, timing=_timing(run_s=run_s))
    assert d.lane == expected
    if expected == "precompute":
        assert any("t2" in r for r in d.reasons)


@pytest.mark.req("FR-009-38")
def test_every_violated_limit_is_named_and_no_timing_means_precompute_not_measured() -> None:
    d = hooks.decide_detector_lane(size_bytes=26_000_000, timing=_timing(median=400.0, run_s=2.0))
    assert d.lane == "precompute"
    for word in ("size", "t1", "t2"):
        assert any(word in r for r in d.reasons), (word, d.reasons)
    none = hooks.decide_detector_lane(size_bytes=9_000_000, timing=None)
    assert none.lane == "precompute"
    assert any("not measured" in r for r in none.reasons)


@pytest.mark.req("FR-009-38")
@pytest.mark.parametrize("size", [0, -1, 1.5, "9", None, True])
def test_a_bad_size_is_rejected(size: object) -> None:
    with pytest.raises(ValueError, match="size_bytes"):
        hooks.decide_detector_lane(size_bytes=size, timing=_timing())  # type: ignore[arg-type]


@pytest.mark.req("FR-009-38")
def test_a_timing_record_that_fails_validation_is_not_trusted() -> None:
    with pytest.raises(ValueError, match="images"):
        hooks.decide_detector_lane(size_bytes=9_000_000, timing=_timing(images=10))


def _variants(over: dict | None = None) -> list[dict]:
    base = {
        (m, p): {"model": m, "precision": p, "size_bytes": 9_000_000, "timing": _timing()}
        for m in MODELS
        for p in PRECISIONS
    }
    for (m, p), patch in (over or {}).items():
        base[(m, p)] = {**base[(m, p)], **patch}
    return list(base.values())


@pytest.mark.req("FR-009-37")
@pytest.mark.req("FR-009-38")
def test_with_both_live_candidates_inside_their_limits_two_onnx_files_ship_and_everything_else_is_baked() -> None:
    plan = hooks.shipping_plan(_variants())
    assert plan["onnx_files"] == list(LIVE)
    assert plan["baked_only"] == sorted(f"{m}-{p}" for m in MODELS for p in PRECISIONS if f"{m}-{p}.onnx" not in LIVE)
    assert len(plan["baked_only"]) == 7
    assert plan["reasons"] == {}


@pytest.mark.req("FR-009-38")
@pytest.mark.parametrize(
    ("patch", "word"),
    [
        ({"size_bytes": 26_000_000}, "size"),
        ({"timing": _timing(median=350.0)}, "t1"),
        ({"timing": _timing(run_s=1.5)}, "t2"),
        ({"timing": None}, "not measured"),
    ],
)
def test_a_live_candidate_over_a_limit_falls_back_to_precompute_with_its_reason(patch: dict, word: str) -> None:
    plan = hooks.shipping_plan(_variants({("d-fine-s", "int8"): patch}))
    assert plan["onnx_files"] == ["d-fine-n-fp16.onnx"]
    assert "d-fine-s-int8" in plan["baked_only"]
    assert any(word in r for r in plan["reasons"]["d-fine-s-int8"])
    assert len(plan["baked_only"]) == 8


@pytest.mark.req("FR-009-37")
def test_a_fast_small_variant_that_is_not_in_the_live_set_is_still_baked_only() -> None:
    plan = hooks.shipping_plan(
        _variants({("rf-detr-seg-n", "fp16"): {"size_bytes": 1_000_000, "timing": _timing(median=5.0, run_s=0.01)}})
    )
    assert plan["onnx_files"] == list(LIVE)
    assert "rf-detr-seg-n-fp16" in plan["baked_only"]
    assert "rf-detr-seg-n-fp16" not in plan["reasons"]


@pytest.mark.req("FR-009-37")
@pytest.mark.parametrize(
    "variants",
    [
        None,
        "v",
        [None],
        [{"model": "d-fine-s"}],
        [{"model": "yolo", "precision": "fp32", "size_bytes": 1, "timing": None}],
    ],
)
def test_malformed_variant_lists_are_rejected(variants: object) -> None:
    with pytest.raises(ValueError, match=r"variants|model|precision|size_bytes"):
        hooks.shipping_plan(variants)  # type: ignore[arg-type]


# ---------------------------------------------------------------- NFR-009-06


def _thumbs(n: int, size: int = 20_000) -> list[dict]:
    return [{"path": f"gallery/{i:03d}.webp", "bytes": size} for i in range(n)]


@pytest.mark.req("NFR-009-06")
def test_a_gallery_of_300_thumbnails_is_allowed_and_counted_in_the_replay_budget_class() -> None:
    assert hooks.gallery_budget(_thumbs(300)) == {"count": 300, "bytes": 300 * 20_000, "budget_class": "shards-clouds"}
    assert hooks.gallery_budget([]) == {"count": 0, "bytes": 0, "budget_class": "shards-clouds"}


@pytest.mark.req("NFR-009-06")
def test_301_thumbnails_are_refused() -> None:
    with pytest.raises(hooks.LaneError) as exc:
        hooks.gallery_budget(_thumbs(301))
    assert exc.value.code == "gallery-too-large"
    assert "gallery-too-large" in str(exc.value)


@pytest.mark.req("NFR-009-06")
@pytest.mark.parametrize(
    "entries",
    [
        [None],
        ["a.webp"],
        [{"path": "a.webp"}],
        [{"path": "a.webp", "bytes": -1}],
        [{"path": "a.webp", "bytes": 1.5}],
        [{"path": "a.webp", "bytes": True}],
        None,
    ],
)
def test_malformed_thumbnail_entries_are_rejected(entries: object) -> None:
    with pytest.raises(ValueError, match=r"thumbnails|bytes"):
        hooks.gallery_budget(entries)  # type: ignore[arg-type]
