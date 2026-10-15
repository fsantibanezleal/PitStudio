"""T-016-032: class budgets and size caps (unit, hostile).

Requirements: FR-016-17, FR-016-18, NFR-016-04, NFR-016-05.

Spec: specs/016-export-acceleration/spec.md
- FR-016-17: total the bytes of every budget class and fail the bake if any total exceeds its cap (section 7 Table B) or
  the site total exceeds 500 x 10^6 bytes, writing a budget report with each class total, cap and margin;
- FR-016-18: an artefact with no budget class or a class not in Table B fails the bake with the artefact's path;
- NFR-016-04: each live ONNX model <= 25 x 10^6 bytes, the ONNX class <= 80 x 10^6 bytes in total;
- NFR-016-05: every shard <= 10 x 10^6 bytes, every git-hosted file < 10,485,760 bytes, the in-git baked total <=
  100 x 10^6 bytes.
plan.md test strategy rows FR-016-17 (class totals against Table B; a 500,000,001-byte site), FR-016-18 (missing class;
class `misc`), NFR-016-04 / NFR-016-05 (sizes against the stated caps).

Oracles: Table B of the spec (1 MB = 10^6 bytes: videos 150, tiles-glb 95, shards-clouds 60, splats 25, onnx 80,
runtimes 55, own-code 10, studio-showcase 25; sum 500) and the matching `budgets.*` / `web.site_total_mb_max` keys of
`specs/000-foundation/thresholds.yaml`, read with PyYAML; margins are cap minus total by hand.

Expected public API (module `pitstudio.export.budgets`, root environment):
    CLASS_CAPS_BYTES: dict[str, int]          # the eight classes of Table B in bytes
    SITE_BYTES_MAX = 500_000_000
    class BudgetError(Exception)              # `.path: str | None` (offending artefact), `.report: BudgetReport | None`
    @dataclass BudgetReport
        classes: dict[str, dict]              # every class of Table B: {"total": int, "cap": int, "margin": int}
        site_total: int; site_cap: int; site_margin: int
        git_total: int                        # bytes of the files with host == "git"
        failures: list[dict]                  # {"scope": "class" | "site" | "live-onnx" | "shard" | "git-file" |
                                              #  "git-total", "name": str, "total": int, "cap": int}
        ok: bool                              # failures == []
    budget_report(files: Sequence[Mapping]) -> BudgetReport
        files: {"path": str, "bytes": int, "budget_class": str, optional "kind": str, "lane": str, "host": str}.
        Raises BudgetError (with `.path`) for a missing / empty / unknown `budget_class` or a `bytes` that is not a
        non-negative integer; never raises for an over-cap bake (it reports `failures`).
    enforce_budgets(files: Sequence[Mapping]) -> BudgetReport
        returns the report when ok; raises BudgetError with `.report` set when `failures` is not empty.
    Failure rules: class total > cap; sum of all files > SITE_BYTES_MAX; kind "onnx" with lane "live" and bytes >
    25_000_000; kind "shard" and bytes > 10_000_000; host "git" and bytes >= 10_485_760; sum of host "git" bytes >
    100_000_000.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pitstudio.export.budgets import (
    CLASS_CAPS_BYTES,
    SITE_BYTES_MAX,
    BudgetError,
    budget_report,
    enforce_budgets,
)

ROOT = Path(__file__).resolve().parents[2]
TH = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))
TABLE_B_MB = {
    "videos": 150,
    "tiles-glb": 95,
    "shards-clouds": 60,
    "splats": 25,
    "onnx": 80,
    "runtimes": 55,
    "own-code": 10,
    "studio-showcase": 25,
}


def _f(path: str, nbytes: int, cls: str, **extra: object) -> dict:
    return {"path": path, "bytes": nbytes, "budget_class": cls, **extra}


@pytest.mark.req("FR-016-17")
def test_class_caps_are_table_b_and_the_thresholds_keys() -> None:
    assert {k: v * 10**6 for k, v in TABLE_B_MB.items()} == CLASS_CAPS_BYTES
    b = TH["budgets"]
    assert b["videos_mb_max"] == 150
    assert b["tiles_and_glb_mb_max"] == 95
    assert b["replay_shards_and_clouds_mb_max"] == 60
    assert b["splats_mb_max"] == 25
    assert b["onnx_total_mb_max"] == 80
    assert b["runtimes_mb_max"] == 55
    assert b["own_js_wasm_fonts_mb_max"] == 10
    assert b["studio_showcase_mb_max"] == 25
    assert TH["web"]["site_total_mb_max"] == 500
    assert SITE_BYTES_MAX == 500_000_000
    assert sum(CLASS_CAPS_BYTES.values()) == SITE_BYTES_MAX


@pytest.mark.req("FR-016-17")
def test_report_lists_every_class_with_total_cap_and_margin_by_hand() -> None:
    files = [_f("a.onnx", 30_000_000, "onnx"), _f("b.onnx", 20_000_000, "onnx"), _f("v.mp4", 100_000_000, "videos")]
    report = budget_report(files)
    assert set(report.classes) == set(TABLE_B_MB)
    assert report.classes["onnx"] == {"total": 50_000_000, "cap": 80_000_000, "margin": 30_000_000}
    assert report.classes["videos"] == {"total": 100_000_000, "cap": 150_000_000, "margin": 50_000_000}
    assert report.classes["splats"] == {"total": 0, "cap": 25_000_000, "margin": 25_000_000}
    assert (report.site_total, report.site_cap, report.site_margin) == (150_000_000, 500_000_000, 350_000_000)
    assert report.failures == []
    assert report.ok is True


@pytest.mark.req("FR-016-17")
@pytest.mark.parametrize("cls", sorted(TABLE_B_MB))
def test_a_class_exactly_at_its_cap_passes_and_one_byte_over_fails(cls: str) -> None:
    cap = TABLE_B_MB[cls] * 10**6
    ok = budget_report([_f("a.bin", cap, cls)])
    assert ok.ok
    assert ok.classes[cls]["margin"] == 0
    over = budget_report([_f("a.bin", cap, cls), _f("b.bin", 1, cls)])
    assert not over.ok
    assert {"scope": "class", "name": cls, "total": cap + 1, "cap": cap} in over.failures
    assert over.classes[cls]["margin"] == -1  # the report still shows the numbers


@pytest.mark.req("FR-016-17")
def test_a_site_of_500_000_001_bytes_fails_on_the_site_total() -> None:
    files = [_f(f"{c}.bin", mb * 10**6, c) for c, mb in TABLE_B_MB.items()]  # every class exactly at its cap
    assert budget_report(files).ok
    report = budget_report([*files, _f("extra.onnx", 1, "onnx")])
    assert report.site_total == 500_000_001
    assert {"scope": "site", "name": "site", "total": 500_000_001, "cap": 500_000_000} in report.failures
    assert report.site_margin == -1


@pytest.mark.req("FR-016-17")
def test_enforce_returns_the_report_when_ok_and_raises_with_the_report_otherwise() -> None:
    assert enforce_budgets([_f("a.onnx", 1, "onnx")]).ok
    with pytest.raises(BudgetError) as info:
        enforce_budgets([_f("a.onnx", 80_000_001, "onnx")])
    assert info.value.report is not None
    assert info.value.report.classes["onnx"]["total"] == 80_000_001
    assert not info.value.report.ok


@pytest.mark.req("FR-016-17")
def test_an_empty_bake_passes_with_zero_totals() -> None:
    report = budget_report([])
    assert report.ok
    assert report.site_total == 0
    assert all(v["total"] == 0 for v in report.classes.values())


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-18: hostile classes
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-18")
@pytest.mark.parametrize(
    "cls", ["misc", "", "ONNX", "tiles_glb", "replay_shards_point_clouds", " onnx", "onnx ", "ónnx"]
)
def test_an_unknown_class_fails_the_bake_naming_the_artefact(cls: str) -> None:
    with pytest.raises(BudgetError) as info:
        budget_report([_f("ok.onnx", 1, "onnx"), _f("assets/odd/file.bin", 5, cls)])
    assert info.value.path == "assets/odd/file.bin"
    assert "assets/odd/file.bin" in str(info.value)


@pytest.mark.req("FR-016-18")
@pytest.mark.parametrize("missing", [None, "absent"])
def test_an_artefact_without_a_budget_class_fails_the_bake_naming_the_artefact(missing: object) -> None:
    entry = {"path": "assets/x/y.bin", "bytes": 5}
    if missing is None:
        entry["budget_class"] = None
    with pytest.raises(BudgetError) as info:
        enforce_budgets([entry])
    assert info.value.path == "assets/x/y.bin"


@pytest.mark.req("FR-016-18")
@pytest.mark.parametrize("bad", [-1, 1.5, float("nan"), float("inf"), True, "10", None])
def test_a_size_that_is_not_a_non_negative_integer_fails_naming_the_artefact(bad: object) -> None:
    with pytest.raises(BudgetError) as info:
        budget_report([_f("assets/z.bin", bad, "onnx")])  # type: ignore[arg-type]
    assert info.value.path == "assets/z.bin"


# ----------------------------------------------------------------------------------------------------------------------
# NFR-016-04 / NFR-016-05
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("NFR-016-04")
def test_each_live_onnx_model_is_at_most_25_million_bytes() -> None:
    ok = budget_report([_f("m.onnx", 25_000_000, "onnx", kind="onnx", lane="live")])
    assert ok.ok
    bad = budget_report([_f("m.onnx", 25_000_001, "onnx", kind="onnx", lane="live")])
    assert {"scope": "live-onnx", "name": "m.onnx", "total": 25_000_001, "cap": 25_000_000} in bad.failures
    # a non-live ONNX file may be larger (the class cap still applies)
    assert budget_report([_f("big.onnx", 40_000_000, "onnx", kind="onnx", lane="replay")]).ok


@pytest.mark.req("NFR-016-04")
def test_the_onnx_class_total_is_at_most_80_million_bytes() -> None:
    files = [_f(f"m{i}.onnx", 20_000_000, "onnx", kind="onnx", lane="live") for i in range(4)]
    assert budget_report(files).ok  # 80,000,000
    assert not budget_report([*files, _f("m4.onnx", 1, "onnx", kind="onnx", lane="replay")]).ok


@pytest.mark.req("NFR-016-05")
def test_every_shard_is_at_most_10_million_bytes() -> None:
    assert budget_report([_f("s.tar", 10_000_000, "shards-clouds", kind="shard")]).ok
    bad = budget_report([_f("s.tar", 10_000_001, "shards-clouds", kind="shard")])
    assert {"scope": "shard", "name": "s.tar", "total": 10_000_001, "cap": 10_000_000} in bad.failures


@pytest.mark.req("NFR-016-05")
def test_every_git_hosted_file_is_below_10485760_bytes() -> None:
    assert budget_report([_f("a.bin", 10_485_759, "own-code", host="git")]).failures == []
    bad = budget_report([_f("a.bin", 10_485_760, "videos", host="git")])
    assert [(f["scope"], f["name"], f["total"]) for f in bad.failures if f["scope"] == "git-file"] == [
        ("git-file", "a.bin", 10_485_760)
    ]
    # the same size is fine as a release asset
    assert budget_report([_f("a.bin", 10_485_760, "videos", host="release")]).ok


@pytest.mark.req("NFR-016-05")
def test_the_in_git_baked_total_is_at_most_100_million_bytes() -> None:
    files = [_f(f"g{i}.bin", 5_000_000, "onnx", host="git") for i in range(20)]  # exactly 100,000,000
    report = budget_report(files)
    assert report.git_total == 100_000_000
    assert report.failures == []
    bad = budget_report([*files, _f("one-more.bin", 1, "runtimes", host="git")])
    assert {"scope": "git-total", "name": "git", "total": 100_000_001, "cap": 100_000_000} in bad.failures
    # release-hosted bytes do not count toward the in-git total
    assert budget_report([*files, _f("r.bin", 20_000_000, "runtimes", host="release")]).git_total == 100_000_000
