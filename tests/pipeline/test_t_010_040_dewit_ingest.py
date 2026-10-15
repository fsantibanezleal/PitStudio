"""T-010-040: de Wit ingestion (`s00_download` entry and `s10_preprocess`) and hostile archives.

Requirements: FR-010-13, FR-010-14.
Spec: specs/010-slope/spec.md section 3.2 (FR-010-13, FR-010-14) and section 7 ("Unknown de Wit inner format");
plan.md row FR-010-13/14 ("the size and MD5 published by the Zenodo record; fixture archives (a series CSV, a map
stack, a `..`
entry, a duplicated timestamp, no unit, no failure time) built by the test");
docs/data-contract/dataset-cards/dewit-slope-failure.md.
Runs in the `pipeline/` environment.

Expected API (module `pitstudio_pipeline.slope.dewit`):
- constants `EXPECTED_BYTES = 8_943_265` and `EXPECTED_MD5 = "3adeb6c853d2e87249b7d3549a2a00ca"` (Zenodo record
  15003054, `Data.zip`).
- `ingest(archive, *, expected_bytes=EXPECTED_BYTES, expected_md5=EXPECTED_MD5, out_dir=None) -> DewitSeries` with
  `.document` (a
  DC-010-02 `real-event` document: kind "real-event", synthetic False, event_id "dewit-2025-event", source_id
  "dewit-slope-failure", archive_bytes, archive_md5, archive_sha256 (the SHA-256 of the file, pinned at first download),
  archive_member, extraction "series-as-delivered" | "map-median-top-5pct", source_units {displacement, time}, t_0_h,
  t_f_h,
  t_f_source, snr_obs, sampling {n_samples, interval_h, regular}, attribution (verbatim), licence {spdx "CC-BY-4.0",
  licence_class "attribution"}, use "descriptive-evaluation-only", t_h (h), los_displacement_mm (mm)) and `.manifest`
  (a dict with
  archive_bytes, archive_md5, archive_sha256, archive_member, source_units, sampling_interval_h, t_0_h, t_f_h,
  t_f_source,
  attribution, snr_obs). With `out_dir` the derived series (`dewit-series.json`) and the manifest (`manifest.json`)
  are written and
  nothing else (the archive and its raw members are never copied).
  Supported inner layouts (the real layout is read at ingestion, spec section 7; these are the layouts the
  implementation must
  accept): (1) a CSV `*.csv` with header columns `time_<unit>` (s, min, h, d) and `displacement_<unit>` (mm, cm, m)
  and one
  metadata file `*.json` {"failure_time": number, "failure_time_unit": unit, "failure_time_source": {kind, citation,
  url},
  "attribution": text}; (2) a NumPy archive `*.npz` with `time_<unit>` (T,) and `displacement_<unit>` (T, H, W) maps
  and the same
  metadata, reduced to the per-epoch median over the pixels in the top 5 % of the final cumulative displacement.
- `DewitRejected(ValueError)` with `.reason` (a short sentence) and `.panel_text == "Not run \u2014 " + reason` (the
  C1 real-event
  panel text); no document and no TTF number come out of a rejected archive. Raised for: a size or MD5 that is not the
  pinned one
  (reason contains "checksum"), a member name that is an absolute path ("absolute path"), has a drive letter ("drive
  letter")
  or a `..` component ("..", the safety rules of FR-008-19), timestamps that are not strictly increasing
  ("timestamps"), a
  displacement column without a unit ("unit"), a metadata file without a failure time ("failure time"), a file that is
  not a zip
  or has no supported member ("archive").

Oracles: the pinned size and MD5 of the spec; `hashlib` for the digests; hand values of unit conversions (1 d = 24 h,
1 m = 1000
mm); the top-5 % median of a planted map by hand; the SNR estimator of the kit on the series between t_0 and t_f.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

import _slope_ttf_ref as k  # noqa: E402
from pitstudio_pipeline.slope import dewit  # noqa: E402

ATTRIBUTION = (
    "de Wit (2025). Data used for the study of time-lapse velocity variations during an open-pit mine slope "
    "failure using seismic noise interferometry. Zenodo. https://doi.org/10.5281/zenodo.15003054. "
    "Licensed under CC BY 4.0. \u00c9 \u00f1"
)
META = {
    "failure_time": 410.0,
    "failure_time_unit": "h",
    "failure_time_source": {
        "kind": "dataset-description",
        "citation": "Zenodo record 15003054, dataset description (illustrative value)",
        "url": "https://zenodo.org/records/15003054",
    },
    "attribution": ATTRIBUTION,
}


def _series(n=120, noise=0.05, seed=3):
    t = np.arange(n) * 3.0
    omega = 0.02 * t + 1e-5 * t**2.2 + noise * np.random.default_rng(seed).standard_normal(n)
    return t, omega


def _csv(t, omega, time_col="time_h", disp_col="displacement_mm") -> bytes:
    rows = [f"{time_col},{disp_col}", *[f"{float(a)!r},{float(b)!r}" for a, b in zip(t, omega, strict=True)]]
    return ("\n".join(rows) + "\n").encode()


def _zip(path: Path, members: dict[str, bytes]) -> tuple[Path, int, str]:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    raw = path.read_bytes()
    return path, len(raw), hashlib.md5(raw).hexdigest()


def _good(tmp_path: Path, **overrides):
    t, omega = _series()
    members = {"Data/radar_deformation.csv": _csv(t, omega), "Data/metadata.json": json.dumps(META).encode()}
    members.update(overrides)
    return _zip(tmp_path / "Data.zip", members), t, omega


def _ingest(path, size, md5, **kw):
    return dewit.ingest(path, expected_bytes=size, expected_md5=md5, **kw)


@pytest.mark.req("FR-010-13")
def test_the_pinned_size_and_md5_are_the_zenodo_values() -> None:
    assert dewit.EXPECTED_BYTES == 8_943_265
    assert dewit.EXPECTED_MD5 == "3adeb6c853d2e87249b7d3549a2a00ca"


@pytest.mark.req("FR-010-13")
def test_a_series_csv_is_extracted_as_delivered_with_units_t0_tf_digest_and_attribution(tmp_path: Path) -> None:
    (path, size, md5), t, omega = _good(tmp_path)
    res = _ingest(path, size, md5)
    doc = res.document
    assert (doc["kind"], doc["synthetic"], doc["event_id"], doc["source_id"]) == (
        "real-event",
        False,
        "dewit-2025-event",
        "dewit-slope-failure",
    )
    assert doc["extraction"] == "series-as-delivered"
    assert doc["archive_member"] == "Data/radar_deformation.csv"
    assert (doc["archive_bytes"], doc["archive_md5"]) == (size, md5)
    assert doc["archive_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert doc["source_units"] == {"displacement": "mm", "time": "h"}
    assert doc["t_h"] == pytest.approx(t.tolist())
    assert doc["los_displacement_mm"] == pytest.approx(omega.tolist())
    assert (doc["t_0_h"], doc["t_f_h"]) == (0.0, 410.0)
    assert doc["t_f_source"] == META["failure_time_source"]
    assert doc["attribution"] == ATTRIBUTION  # verbatim, unicode included
    assert doc["licence"] == {"spdx": "CC-BY-4.0", "licence_class": "attribution"}
    assert doc["use"] == "descriptive-evaluation-only"
    assert doc["sampling"] == {"n_samples": len(t), "interval_h": pytest.approx(3.0), "regular": True}
    keep = (t >= 0.0) & (t <= 410.0)
    assert doc["snr_obs"] == pytest.approx(k.snr_estimate(omega[keep])[0], rel=1e-9)  # FR-010-12 between t_0 and t_f
    m = res.manifest
    assert m["snr_obs"] == doc["snr_obs"]
    assert (m["archive_md5"], m["t_f_h"], m["attribution"]) == (md5, 410.0, ATTRIBUTION)
    assert m["sampling_interval_h"] == pytest.approx(3.0)
    assert m["source_units"] == {"displacement": "mm", "time": "h"}


@pytest.mark.req("FR-010-13")
def test_units_are_recorded_and_converted_days_to_hours_and_metres_to_millimetres(tmp_path: Path) -> None:
    t_d = np.arange(60) * 0.5  # days
    omega_m = 1e-3 * (1.0 + 0.2 * t_d)  # metres
    meta = {**META, "failure_time": 40.0, "failure_time_unit": "d"}
    members = {"d.csv": _csv(t_d, omega_m, "time_d", "displacement_m"), "meta.json": json.dumps(meta).encode()}
    path, size, md5 = _zip(tmp_path / "Data.zip", members)
    doc = _ingest(path, size, md5).document
    assert doc["source_units"] == {"displacement": "m", "time": "d"}
    assert doc["t_h"] == pytest.approx((t_d * 24.0).tolist(), rel=1e-12)
    assert doc["los_displacement_mm"] == pytest.approx((omega_m * 1000.0).tolist(), rel=1e-12)
    assert doc["t_f_h"] == pytest.approx(40.0 * 24.0)
    assert doc["sampling"]["interval_h"] == pytest.approx(12.0)


@pytest.mark.req("FR-010-13")
def test_irregular_sampling_is_recorded_as_such(tmp_path: Path) -> None:
    t = np.array([0.0, 1.0, 2.5, 3.0, 5.0, 6.0, 7.5, 8.0, 9.0, 10.5, 11.0, 12.0])
    omega = 0.1 * t
    path, size, md5 = _zip(
        tmp_path / "Data.zip", {"s.csv": _csv(t, omega), "m.json": json.dumps({**META, "failure_time": 15.0}).encode()}
    )
    doc = _ingest(path, size, md5).document
    assert doc["sampling"]["regular"] is False
    assert doc["sampling"]["n_samples"] == len(t)


@pytest.mark.req("FR-010-13")
def test_a_map_stack_is_reduced_to_the_median_of_the_top_five_percent_pixels(tmp_path: Path) -> None:
    h = w = 20  # 400 pixels: the top 5 % are the 20 pixels with the largest final cumulative displacement
    rank = np.random.default_rng(7).permutation(h * w).reshape(h, w)
    amp = 1.0 + 0.01 * rank  # amplitudes 1.00 .. 4.99; the top 20 are 4.80 .. 4.99, median (4.89 + 4.90) / 2 = 4.895
    t = np.arange(40) * 2.0
    g = (t / t[-1]) ** 2  # common time profile, zero at the first epoch, one at the last
    stack = g[:, None, None] * amp[None, :, :]
    buf = io.BytesIO()
    np.savez(buf, time_h=t, displacement_mm=stack)
    path, size, md5 = _zip(
        tmp_path / "Data.zip",
        {"maps.npz": buf.getvalue(), "meta.json": json.dumps({**META, "failure_time": 100.0}).encode()},
    )
    doc = _ingest(path, size, md5).document
    assert doc["extraction"] == "map-median-top-5pct"
    assert doc["archive_member"] == "maps.npz"
    assert doc["los_displacement_mm"] == pytest.approx((4.895 * g).tolist(), rel=1e-9, abs=1e-12)
    assert doc["t_h"] == pytest.approx(t.tolist())


@pytest.mark.req("FR-010-13")
def test_out_dir_receives_only_the_derived_series_and_the_manifest(tmp_path: Path) -> None:
    (path, size, md5), _, _ = _good(tmp_path)
    out = tmp_path / "derived"
    _ingest(path, size, md5, out_dir=out)
    assert sorted(p.name for p in out.iterdir()) == [
        "dewit-series.json",
        "manifest.json",
    ]  # no csv, no zip, no raw member
    written = json.loads((out / "dewit-series.json").read_text(encoding="utf-8"))
    assert written["attribution"] == ATTRIBUTION
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["archive_md5"] == md5


@pytest.mark.req("FR-010-13")
def test_only_the_pinned_archive_is_accepted_by_default(tmp_path: Path) -> None:
    (path, size, _), _, _ = _good(tmp_path)
    assert size != dewit.EXPECTED_BYTES
    with pytest.raises(dewit.DewitRejected) as exc:
        dewit.ingest(path)  # the fixture is not the 8,943,265-byte archive of the Zenodo record
    assert "checksum" in exc.value.reason.lower()


# ---------------------------------------------------------------------------------------------------------------------
# FR-010-14: hostile archives


def _bad_csv(mutate) -> bytes:
    t, omega = _series()
    return _csv(*mutate(t.copy(), omega.copy()))


HOSTILE = [
    ("md5-mismatch", lambda p: {}, {"expected_md5": "0" * 32}, "checksum"),
    ("size-mismatch", lambda p: {}, {"expected_bytes": 123}, "checksum"),
    ("absolute-path", lambda p: {"/etc/evil.csv": b"x"}, {}, "absolute"),
    ("drive-letter", lambda p: {"C:/evil.csv": b"x"}, {}, "drive"),
    ("dotdot", lambda p: {"Data/../../evil.csv": b"x"}, {}, ".."),
    (
        "duplicate-timestamps",
        lambda p: {
            "Data/radar_deformation.csv": _bad_csv(
                lambda t, o: (np.concatenate([t[:5], t[4:5], t[5:]]), np.concatenate([o[:5], o[4:5], o[5:]]))
            )
        },
        {},
        "timestamps",
    ),
    (
        "decreasing-timestamps",
        lambda p: {"Data/radar_deformation.csv": _bad_csv(lambda t, o: (t[::-1].copy(), o))},
        {},
        "timestamps",
    ),
    (
        "non-monotonic-timestamps",
        lambda p: {"Data/radar_deformation.csv": _bad_csv(lambda t, o: (np.where(np.arange(len(t)) == 50, 3.0, t), o))},
        {},
        "timestamps",
    ),
    (
        "no-displacement-unit",
        lambda p: {"Data/radar_deformation.csv": _csv(*_series(), "time_h", "displacement")},
        {},
        "unit",
    ),
    (
        "no-failure-time",
        lambda p: {
            "Data/metadata.json": json.dumps(
                {k: v for k, v in META.items() if not k.startswith("failure_time")}
            ).encode()
        },
        {},
        "failure time",
    ),
    (
        "failure-time-not-a-number",
        lambda p: {"Data/metadata.json": json.dumps({**META, "failure_time": "soon"}).encode()},
        {},
        "failure time",
    ),
    (
        "nan-displacement",
        lambda p: {
            "Data/radar_deformation.csv": _bad_csv(lambda t, o: (t, np.where(np.arange(len(o)) == 9, np.nan, o)))
        },
        {},
        "displacement",
    ),
]


@pytest.mark.req("FR-010-14")
@pytest.mark.parametrize(("name", "members", "kw", "word"), HOSTILE, ids=[h[0] for h in HOSTILE])
def test_a_hostile_archive_is_rejected_with_the_reason_and_the_not_run_panel_text(
    tmp_path, name, members, kw, word
) -> None:
    t, omega = _series()
    base = {"Data/radar_deformation.csv": _csv(t, omega), "Data/metadata.json": json.dumps(META).encode()}
    base.update(members(None))
    path, size, md5 = _zip(tmp_path / "Data.zip", base)
    args = {"expected_bytes": size, "expected_md5": md5, **kw}
    out = tmp_path / "derived"
    with pytest.raises(dewit.DewitRejected) as exc:
        dewit.ingest(path, out_dir=out, **args)
    err = exc.value
    assert word in err.reason.lower(), (name, err.reason)
    assert err.panel_text == f"Not run \u2014 {err.reason}"
    assert isinstance(err, ValueError)
    assert not out.exists() or list(out.iterdir()) == []  # no series and no TTF number leave a rejected archive


@pytest.mark.req("FR-010-14")
@pytest.mark.parametrize("payload", [b"", b"not a zip at all", b"PK\x03\x04" + b"\x00" * 10])
def test_a_file_that_is_not_a_zip_is_rejected(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "Data.zip"
    path.write_bytes(payload)
    md5 = hashlib.md5(payload).hexdigest()
    with pytest.raises(dewit.DewitRejected) as exc:
        dewit.ingest(path, expected_bytes=len(payload), expected_md5=md5)
    assert "archive" in exc.value.reason.lower()


@pytest.mark.req("FR-010-14")
def test_an_archive_without_a_supported_member_is_rejected(tmp_path: Path) -> None:
    path, size, md5 = _zip(
        tmp_path / "Data.zip", {"readme.txt": b"hello", "Data/metadata.json": json.dumps(META).encode()}
    )
    with pytest.raises(dewit.DewitRejected) as exc:
        _ingest(path, size, md5)
    assert "archive" in exc.value.reason.lower()
