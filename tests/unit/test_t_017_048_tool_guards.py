"""T-017-048: tool verification and the "Not run" / "failed" paths (unit, fake tools, studio environment).

Requirements: FR-017-42, FR-017-43, FR-017-44, FR-017-45.

Spec: specs/017-planning-survey/spec.md
- FR-017-42: before every run the reconstruction stage verifies the COLMAP and Brush binaries against their pinned
  SHA-256
  and reads their versions, and records both in the manifest;
- FR-017-43: if Brush is missing, fails its checksum or its smoke run, the splat surface and the splat view show
  "Not run --
  <reason>" (an em dash) and E2 continues with the photogrammetric surface and DEM differencing;
- FR-017-44: if the RTX drone camera (ovrtx, scenario S2) is unavailable or its probe fails, every synthetic-flight
  result
  shows "Not run -- RTX camera unavailable" and the real Bingham volume is still produced;
- FR-017-45: if COLMAP registers fewer than 80 % of a flight's images or the alignment RMSE exceeds 5 x GSD, the
  flight is
  reported "reconstruction failed -- <reason>" with no volume, and counted.
plan.md test strategy rows FR-017-42 ... 45 (unit, fake tools): fake binaries with wrong SHA-256, failing smoke, 70 %
registration, large alignment RMSE; RTX probe stub.

Oracles:
- fake binaries written by the test (Python scripts run through `sys.executable`; a script prints its version or
  fails),
  whose SHA-256 is computed with `hashlib` over the file bytes;
- the boundaries by hand: 24 of 30 images registered is exactly 80 % (accepted), 23 of 30 is 76.7 % (failed), 70 %
  fails;
  GSD 2 cm/px gives a limit of 5 x 2 cm = 0.10 m on the alignment RMSE: 0.10 accepted, 0.1001 failed;
- the DC-017-04 schema for the shape of the not-run and failed rows (`status`, `reason`, `flight`, `seed`, no volume).

Expected public API (module `pitstudio_studio.survey.tools`, `studio/` environment):
    class ToolError(Exception)                    # `.reason`
    verify_tool(path: Path, *, pinned_sha256: str, expected_version: str, launcher: Sequence[str] = (),
                version_args: Sequence[str] = ("--version",), timeout_s: float = 30.0) -> dict
        returns {"path": str(path), "sha256": hex of the file, "version": the first output line} when the file
        exists, its
        SHA-256 equals the pin, `launcher + [path] + version_args` exits 0 and the output contains `expected_version`;
        raises ToolError with a reason containing "missing", "sha256", "smoke" (non-zero exit, timeout or wrong
        version)
        otherwise.
    verify_tools(*, colmap: Mapping, brush: Mapping) -> dict
        each mapping the keyword arguments of verify_tool; returns {"colmap": record, "brush": record}; the manifest
        fields. A failure of either raises ToolError naming the tool.
    splat_stage_outcome(brush: Mapping, *, flight: str, seed: int) -> dict
        {"status": "ok", "tool": record} when Brush verifies; else {"status": "not_run", "label": "Not run â€”
        <reason>", "reason": <reason>, "continue_with": ["photogrammetric", "dem-differencing"]}.
    rtx_flights_outcome(probe, flights: Sequence[tuple[str, int]]) -> dict
        `probe()` returns True when the RTX drone camera is available and may raise; not available (False or an
        exception)
        gives {"status": "not_run", "label": "Not run â€” RTX camera unavailable", "rows": [one DC-017-04 not_run
        volume
        per (flight, seed, method in photogrammetric, splat) with the reason "RTX camera unavailable"],
        "real_volume": "still-produced"}; available gives
        {"status": "ok", "rows": []}.
    check_reconstruction(*, flight: str, seed: int, method: str, n_registered: int, n_total: int,
                         alignment_rmse_m: float, gsd_cm_per_px: float) -> dict | None
        None when at least 80 % of the images registered and the RMSE is at most 5 x GSD (in metres); otherwise the
        DC-017-04 volume row {"id", "scope": "synthetic", "method", "status": "failed", "reason": "reconstruction
        failed
        â€” <cause>", "flight", "seed"} (no volume fields); ValueError for n_total <= 0 or n_registered > n_total.
    count_failed(rows: Sequence[Mapping]) -> int      # the number of rows with status "failed"
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from pitstudio_studio.survey.tools import (
    ToolError,
    check_reconstruction,
    count_failed,
    rtx_flights_outcome,
    splat_stage_outcome,
    verify_tool,
    verify_tools,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts" / "survey-volume.schema.json").read_text("utf-8"))
EM_DASH = "â€”"


def _script(tmp_path: Path, name: str, body: str) -> tuple[Path, str]:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


GOOD_COLMAP = 'import sys\nprint("COLMAP 4.2.1 (with CUDA)")\n'
GOOD_BRUSH = 'import sys\nprint("brush 0.3.0")\n'


def _tool(path: Path, sha: str, version: str) -> dict:
    return {"path": path, "pinned_sha256": sha, "expected_version": version, "launcher": [sys.executable]}


def _errors(rows: list[dict]) -> list:
    from jsonschema import Draft202012Validator

    return list(Draft202012Validator(SCHEMA).iter_errors({"schema_version": "1.0", "volumes": rows}))


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-42
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-42")
def test_a_verified_tool_returns_its_path_digest_and_version(tmp_path: Path) -> None:
    path, sha = _script(tmp_path, "colmap.py", GOOD_COLMAP)
    record = verify_tool(path, pinned_sha256=sha, expected_version="4.2.1", launcher=[sys.executable])
    assert record == {"path": str(path), "sha256": sha, "version": "COLMAP 4.2.1 (with CUDA)"}


@pytest.mark.req("FR-017-42")
def test_both_tools_are_recorded_for_the_manifest(tmp_path: Path) -> None:
    c, c_sha = _script(tmp_path, "colmap.py", GOOD_COLMAP)
    b, b_sha = _script(tmp_path, "brush.py", GOOD_BRUSH)
    record = verify_tools(colmap=_tool(c, c_sha, "4.2.1"), brush=_tool(b, b_sha, "0.3.0"))
    assert set(record) == {"colmap", "brush"}
    assert record["colmap"]["sha256"] == c_sha
    assert record["brush"]["version"] == "brush 0.3.0"


@pytest.mark.req("FR-017-42")
def test_a_wrong_digest_a_missing_file_and_a_wrong_version_are_refused_with_the_reason(tmp_path: Path) -> None:
    path, sha = _script(tmp_path, "colmap.py", GOOD_COLMAP)
    with pytest.raises(ToolError) as info:
        verify_tool(path, pinned_sha256="0" * 64, expected_version="4.2.1", launcher=[sys.executable])
    assert "sha256" in info.value.reason
    with pytest.raises(ToolError) as info:
        verify_tool(tmp_path / "absent.py", pinned_sha256=sha, expected_version="4.2.1", launcher=[sys.executable])
    assert "missing" in info.value.reason
    with pytest.raises(ToolError) as info:
        verify_tool(path, pinned_sha256=sha, expected_version="4.3.0", launcher=[sys.executable])
    assert "smoke" in info.value.reason or "version" in info.value.reason


@pytest.mark.req("FR-017-42")
def test_a_tool_that_fails_or_hangs_is_refused(tmp_path: Path) -> None:
    failing, sha = _script(tmp_path, "fail.py", "import sys\nsys.exit(3)\n")
    with pytest.raises(ToolError) as info:
        verify_tool(failing, pinned_sha256=sha, expected_version="x", launcher=[sys.executable])
    assert "smoke" in info.value.reason
    hanging, sha2 = _script(tmp_path, "hang.py", "import time\ntime.sleep(60)\n")
    with pytest.raises(ToolError) as info:
        verify_tool(hanging, pinned_sha256=sha2, expected_version="x", launcher=[sys.executable], timeout_s=1.0)
    assert "smoke" in info.value.reason or "timeout" in info.value.reason


@pytest.mark.req("FR-017-42")
def test_a_failure_of_either_tool_names_the_tool(tmp_path: Path) -> None:
    c, c_sha = _script(tmp_path, "colmap.py", GOOD_COLMAP)
    b, _ = _script(tmp_path, "brush.py", GOOD_BRUSH)
    with pytest.raises(ToolError) as info:
        verify_tools(colmap=_tool(c, c_sha, "4.2.1"), brush=_tool(b, "f" * 64, "0.3.0"))
    assert "brush" in info.value.reason.lower()


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-43
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-43")
def test_a_healthy_brush_gives_an_ok_stage_with_its_tool_record(tmp_path: Path) -> None:
    b, sha = _script(tmp_path, "brush.py", GOOD_BRUSH)
    out = splat_stage_outcome(_tool(b, sha, "0.3.0"), flight="f01", seed=0)
    assert out["status"] == "ok"
    assert out["tool"]["sha256"] == sha


@pytest.mark.req("FR-017-43")
@pytest.mark.parametrize("failure", ["missing", "checksum", "smoke"])
def test_brush_missing_failing_its_checksum_or_its_smoke_run_gives_not_run_and_the_survey_continues(
    tmp_path: Path, failure: str
) -> None:
    if failure == "missing":
        brush = _tool(tmp_path / "gone.py", "a" * 64, "0.3.0")
    elif failure == "checksum":
        path, _ = _script(tmp_path, "brush.py", GOOD_BRUSH)
        brush = _tool(path, "b" * 64, "0.3.0")
    else:
        path, sha = _script(tmp_path, "brush.py", "import sys\nsys.exit(1)\n")
        brush = _tool(path, sha, "0.3.0")
    out = splat_stage_outcome(brush, flight="f01", seed=0)
    assert out["status"] == "not_run"
    assert out["label"] == f"Not run {EM_DASH} {out['reason']}"
    assert out["reason"]
    assert out["continue_with"] == ["photogrammetric", "dem-differencing"]


@pytest.mark.req("FR-017-43")
def test_the_brush_not_run_reason_names_the_cause(tmp_path: Path) -> None:
    out = splat_stage_outcome(_tool(tmp_path / "gone.py", "a" * 64, "0.3.0"), flight="f01", seed=0)
    assert "Brush" in out["reason"]
    assert "missing" in out["reason"]
    path, _ = _script(tmp_path, "brush.py", GOOD_BRUSH)
    out = splat_stage_outcome(_tool(path, "b" * 64, "0.3.0"), flight="f01", seed=0)
    assert "sha256" in out["reason"]


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-44
# ----------------------------------------------------------------------------------------------------------------------

FLIGHTS = [(f"f{f:02d}", s) for f in range(1, 4) for s in range(3)]


@pytest.mark.req("FR-017-44")
@pytest.mark.parametrize("probe", [lambda: False, lambda: (_ for _ in ()).throw(RuntimeError("ovrtx failed"))])
def test_an_unavailable_or_failing_rtx_camera_gives_not_run_for_every_flight_and_keeps_the_real_volume(probe) -> None:
    out = rtx_flights_outcome(probe, FLIGHTS)
    assert out["status"] == "not_run"
    assert out["label"] == f"Not run {EM_DASH} RTX camera unavailable"
    assert out["real_volume"] == "still-produced"
    assert len(out["rows"]) == 2 * len(FLIGHTS)  # one row per flight, seed and method
    assert {(r["flight"], r["seed"]) for r in out["rows"]} == set(FLIGHTS)
    assert {r["method"] for r in out["rows"]} == {"photogrammetric", "splat"}
    assert all(r["status"] == "not_run" and r["reason"] == "RTX camera unavailable" for r in out["rows"])
    assert all("v_fill_m3" not in r for r in out["rows"])
    assert _errors(out["rows"]) == []


@pytest.mark.req("FR-017-44")
def test_an_available_rtx_camera_gives_no_not_run_rows() -> None:
    out = rtx_flights_outcome(lambda: True, FLIGHTS)
    assert out == {"status": "ok", "rows": []}


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-45
# ----------------------------------------------------------------------------------------------------------------------


def _check(n_registered: int, n_total: int = 30, rmse: float = 0.05, gsd: float = 2.0):
    return check_reconstruction(
        flight="f01", seed=1, method="photogrammetric", n_registered=n_registered, n_total=n_total,
        alignment_rmse_m=rmse, gsd_cm_per_px=gsd,
    )  # fmt: skip


@pytest.mark.req("FR-017-45")
def test_exactly_80_percent_registered_is_accepted_and_below_it_fails() -> None:
    assert _check(24) is None  # 24 / 30 = 80 %
    below = _check(23)
    assert below["status"] == "failed"
    assert below["reason"].startswith(f"reconstruction failed {EM_DASH} ")
    assert "regist" in below["reason"]
    assert _check(21)["status"] == "failed"  # 70 %


@pytest.mark.req("FR-017-45")
def test_an_alignment_rmse_above_5_gsd_fails_and_exactly_5_gsd_is_accepted() -> None:
    assert _check(30, rmse=0.10) is None  # 5 x 2 cm = 0.10 m
    assert _check(30, rmse=0.0999) is None
    over = _check(30, rmse=0.1001)
    assert over["status"] == "failed"
    assert "alignment" in over["reason"]
    assert _check(30, rmse=0.30, gsd=8.0) is None  # GSD 8 cm: limit 0.40 m


@pytest.mark.req("FR-017-45")
def test_a_failed_flight_row_has_no_volume_and_validates_against_dc_017_04() -> None:
    row = _check(10)
    assert row["id"] == "f01-s1-photogrammetric"
    assert (row["scope"], row["method"], row["flight"], row["seed"]) == ("synthetic", "photogrammetric", "f01", 1)
    assert not {"v_fill_m3", "v_cut_m3", "v_net_m3", "errors"} & set(row)
    assert _errors([row]) == []


@pytest.mark.req("FR-017-45")
def test_failed_flights_are_counted() -> None:
    rows = [_check(10), _check(30), _check(30, rmse=1.0), {"status": "not_run"}, {"status": "ok"}]
    rows = [r for r in rows if r is not None]
    assert count_failed(rows) == 2
    assert count_failed([]) == 0


@pytest.mark.req("FR-017-45")
@pytest.mark.parametrize(("n_reg", "n_total"), [(1, 0), (31, 30), (-1, 30), (5, -2)])
def test_hostile_counts_are_refused(n_reg: int, n_total: int) -> None:
    with pytest.raises(ValueError, match=r"."):
        _check(n_reg, n_total)
