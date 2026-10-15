# ruff: noqa: E501, PT018
"""T-002-052: `studio publish` and published telemetry (US-002-5).

Requirements: FR-002-48, FR-002-49, FR-002-50.

Expected behaviour (stated for the implementer; assumptions marked A are listed in the red report):
  * `studio publish <run_id> [--release-tag <tag>]` turns a finished, clean, NVML/uv run into static web files:
      - `web/public/assets/runs/<run_id>/manifest.json`: `published: true`, valid against the manifest schema, local-only
        stages scrubbed (`telemetry` = the LOCAL_ONLY constant, no `wall_s`, `throughput`, `attempts[].duration_s`),
        `log_tail` removed, no absolute path or machine identity;
      - each output marked `publish: true` in the recipe: < 10 MiB (10,485,760 B) is copied below
        `web/public/assets/<run_id>/` (`asset_host: git`), larger goes to `$PITSTUDIO_STORE/publish/<release tag>/<file>`
        (`asset_host: release`, needs a well-formed `--release-tag assets-vN.NN.NNN`);
      - the artefact records are added to `web/public/assets/manifest.json` (the web index): `lane` from the lane gate
        (live iff web_drivable and max_asset_bytes <= 25,000,000 and (interaction_ms <= 16 or run_ms_t2 <= 1,000) and
        (trace_bytes null or <= 10,000,000); static kinds are `static`), licence class = the lattice maximum of `own` and
        the classes of the producing stage's source inputs (public-domain / open-no-attribution / own -> `own`), `spdx` and
        `attribution` by plan.md D3; the run is listed in the index `runs`;
      - `web/public/assets/runs/<run_id>/telemetry.json` (published_telemetry): public stages only; the run is pinned
        (`runs/<run_id>/PINNED`);
  * A: the producing stage's manifest `inputs` give an artefact's inputs; the facts the stage reported for an output
    (kind, media_type, budget_class, cases, lane_measurements, encoder) are read from the run's records;
  * every refusal exits 2 naming the reason and changes no file of the repository.
  * `pitstudio.runner.publish.downsample(samples, *, max_points=2000) -> {"bucket_s": float, "points": [published_point]}`
    and `published_telemetry(run_id, stages: list[{"key": stage_key, "samples": list[telemetry_sample]}], *, max_points=2000,
    max_bytes=204800) -> dict` (valid against events.schema.json#/$defs/published_telemetry): equal-time buckets (mean of
    util, power and clock; max of temperature and memory; bitwise OR of clock-event masks), the bucket count halved
    deterministically until <= max_points points per stage and the JSON text is <= max_bytes.
Oracles: hand-built runs (tests/support/publish_world.py), the lane gate and the licence table of plan.md D3 applied by
hand, the manifest/events/sources schemas, privacy patterns of spec 001 data-model 1.5, a hand-aggregated bucket example.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import publish_world as pw
import runner_world as rw
import schemas

RUN = pw.RUN_ID
TAG = "assets-v1.00.001"
DRIVE = re.compile(r"[A-Za-z]:[\\/]")
POSIX = re.compile(r"(^|[\s\"'=(,:])/(home|Users|root|tmp|var|mnt|media|opt|srv|private|run)/")


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


def files(root: Path) -> dict[str, str]:
    return {k: v for k, v in rw.tree_digest(root).items() if not k.endswith("/")}


def published(world: rw.World) -> dict[str, Any]:
    return json.loads(
        (world.repo / "web" / "public" / "assets" / "runs" / RUN / "manifest.json").read_text(encoding="utf-8")
    )


def index(world: rw.World) -> dict[str, Any]:
    return json.loads((world.repo / "web" / "public" / "assets" / "manifest.json").read_text(encoding="utf-8"))


def artefact(world: rw.World, suffix: str) -> dict[str, Any]:
    (a,) = [x for x in index(world)["artefacts"] if x["path"].endswith(suffix)]
    return a


# ---- FR-002-48: the happy path -------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-48")
def test_fr_002_48_publish_writes_exactly_the_documented_files_and_validates_everything(world) -> None:
    b = pw.build_run(world, clip_inputs=["src-by"])
    before = files(world.repo)
    r = world.cli("publish", RUN)
    assert r.code == 0, r.text
    after = files(world.repo)
    added = set(after) - set(before)
    changed = {k for k in before if after.get(k) != before[k]}
    assert changed == {"web/public/assets/manifest.json"}, changed
    clip, table = artefact(world, "clip.mp4"), artefact(world, "summary.json")
    expected_added = {
        f"web/public/assets/runs/{RUN}/manifest.json",
        f"web/public/assets/runs/{RUN}/telemetry.json",
        f"web/public/{clip['path']}",
        f"web/public/{table['path']}",
    }
    assert added == expected_added, added ^ expected_added
    # the copies are the promoted bytes
    assert (world.repo / "web" / "public" / clip["path"]).read_bytes() == b.expected_files["media/clip.mp4"]
    assert (world.repo / "web" / "public" / table["path"]).read_bytes() == b.expected_files["tables/summary.json"]
    assert clip["path"].startswith(f"assets/{RUN}/") and table["path"].startswith(f"assets/{RUN}/")
    assert clip["sha256"] == pw.sha(b.expected_files["media/clip.mp4"]) and clip["bytes"] == len(
        b.expected_files["media/clip.mp4"]
    )
    assert (clip["asset_host"], clip["kind"], clip["budget_class"], clip["media_type"], clip["cases"]) == (
        "git",
        "video",
        "videos",
        "video/mp4",
        ["A2"],
    )
    assert "release_tag" not in clip and clip["run_id"] == RUN and clip["git_sha"] == b.git_sha
    assert (
        clip["producer"] == {"tool": "nvenc-ffmpeg", "stage": {"id": "st56_encode"}}
        and clip["encoder"]["codec"] == "av1"
    )
    # pinned, indexed and valid
    assert (world.store / "runs" / RUN / "PINNED").exists()
    idx = index(world)
    assert schemas.errors("manifest", idx, "#") == []
    assert [x["run_id"] for x in idx["runs"]] == [RUN]
    pub_path = world.repo / "web" / "public" / "assets" / "runs" / RUN / "manifest.json"
    assert (
        idx["runs"][0]["sha256"] == pw.sha(pub_path.read_bytes())
        and idx["runs"][0]["manifest"] == f"{RUN}/manifest.json"
    )
    assert schemas.errors("manifest", published(world), "#/$defs/run") == []
    tele = json.loads(
        (world.repo / "web" / "public" / "assets" / "runs" / RUN / "telemetry.json").read_text(encoding="utf-8")
    )
    assert schemas.errors("events", tele, "#/$defs/published_telemetry") == []


@pytest.mark.req("FR-002-48")
def test_fr_002_48_published_manifest_scrubs_local_only_stages_logs_and_machine_details(world) -> None:
    pw.build_run(world, sensor_status="failed")
    assert world.cli("publish", RUN).code == 0
    m = published(world)
    assert (
        m["published"] is True and m["git_dirty"] is False and m["launcher"] == "uv" and m["gpu"]["backend"] == "nvml"
    )
    by = {s["key"]["id"]: s for s in m["stages"]}
    local = by["st53_sensors"]
    assert local["performance"] == "local-only" and local["telemetry"] == pw.LOCAL_ONLY
    assert "wall_s" not in local and "throughput" not in local and all("duration_s" not in a for a in local["attempts"])
    assert "log_tail" not in local, "log_tail is removed from the published manifest"
    pub = by["st50_physics"]
    assert (
        pub["performance"] == "public"
        and isinstance(pub["telemetry"], dict)
        and pub["wall_s"] == 42.5
        and pub["throughput"]["value"] == 240.0
    )
    text = json.dumps(m)
    import getpass
    import socket

    assert not DRIVE.search(text) and not POSIX.search(text) and "\\\\" not in text
    for ident in (socket.gethostname(), getpass.getuser(), str(world.repo), str(world.store)):
        assert len(ident) < 3 or ident.lower() not in text.lower()


@pytest.mark.req("FR-002-48")
def test_fr_002_48_published_telemetry_covers_public_stages_only(world) -> None:
    pw.build_run(world)
    assert world.cli("publish", RUN).code == 0
    tele = json.loads(
        (world.repo / "web" / "public" / "assets" / "runs" / RUN / "telemetry.json").read_text(encoding="utf-8")
    )
    assert tele["run_id"] == RUN
    assert [s["key"]["id"] for s in tele["stages"]] == ["st50_physics"], (
        "the local-only stage (st53_sensors) has no published metric"
    )
    (st,) = tele["stages"]
    assert st["performance"] == "public" and 0 < len(st["points"]) <= 2000 and st["bucket_s"] > 0
    blob = (world.repo / "web" / "public" / "assets" / "runs" / RUN / "telemetry.json").read_bytes()
    assert len(blob) <= 204_800


# ---- release-hosted outputs ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-48")
@pytest.mark.parametrize(("size", "host"), [(10_485_759, "git"), (10_485_760, "release"), (12_000_000, "release")])
def test_fr_002_48_the_10_mib_boundary_selects_the_asset_host(world, size: int, host: str) -> None:
    b = pw.build_run(world, clip_bytes=size)
    args = ["publish", RUN] + (["--release-tag", TAG] if host == "release" else [])
    r = world.cli(*args)
    assert r.code == 0, r.text
    clip = artefact(world, "clip.mp4")
    assert clip["asset_host"] == host and clip["bytes"] == size
    if host == "release":
        assert clip["release_tag"] == TAG and "/" not in clip["path"]
        staged = world.store / "publish" / TAG / clip["path"]
        assert staged.read_bytes() == b.expected_files["media/clip.mp4"], (
            "the release asset waits in the store's publish folder"
        )
        assert not any(k.endswith(clip["path"]) for k in files(world.repo)), (
            "nothing of 10 MiB or more enters the repository"
        )
    else:
        assert "release_tag" not in clip and (world.repo / "web" / "public" / clip["path"]).stat().st_size == size


# ---- licence fields (plan.md D3) ------------------------------------------------------------------------------------------------------------------
LICENCE_CASES = [
    ("no-inputs", [], False, "own", "CC-BY-4.0", None),
    ("open-no-attribution-input", ["src-cc0"], False, "own", "CC-BY-4.0", None),
    ("attribution-input", ["src-by"], False, "attribution", "CC-BY-4.0", "Data (c) Example Org, CC BY 4.0."),
    (
        "two-attribution-inputs-joined",
        ["src-by", "src-by2"],
        False,
        "attribution",
        "CC-BY-4.0",
        "Data (c) Example Org, CC BY 4.0.; Second dataset (c) Another Org, CC BY 4.0.",
    ),
    (
        "same-attribution-twice-is-deduplicated",
        ["src-by", "src-by"],
        False,
        "attribution",
        "CC-BY-4.0",
        "Data (c) Example Org, CC BY 4.0.",
    ),
    (
        "share-alike-input",
        ["src-sa"],
        False,
        "share-alike",
        "CC-BY-SA-4.0",
        "Share-alike data (c) Other Org, CC BY-SA 4.0.",
    ),
    ("onnx-own", [], True, "own", "Apache-2.0", None),
    ("onnx-with-attribution-input", ["src-by"], True, "attribution", "Apache-2.0", "Data (c) Example Org, CC BY 4.0."),
]


@pytest.mark.req("FR-002-48")
@pytest.mark.parametrize(
    ("label", "inputs", "onnx", "klass", "spdx", "attribution"), LICENCE_CASES, ids=[c[0] for c in LICENCE_CASES]
)
def test_fr_002_48_licence_class_spdx_and_attribution_follow_the_lattice_and_the_d3_table(
    world, label: str, inputs: list[str], onnx: bool, klass: str, spdx: str, attribution: str | None
) -> None:
    pw.build_run(world, clip_inputs=inputs, onnx=onnx)
    r = world.cli("publish", RUN)
    assert r.code == 0, f"{label}: {r.text}"
    for suffix in ("clip.mp4", "summary.json"):
        a = artefact(world, suffix)
        want_spdx = (
            "CC-BY-4.0" if suffix == "summary.json" and spdx == "Apache-2.0" else spdx
        )  # only the onnx kind switches to Apache-2.0
        assert (a["licence_class"], a["spdx"]) == (klass, want_spdx), (label, suffix, a["licence_class"], a["spdx"])
        if attribution:
            assert a["attribution"] == attribution, (label, suffix)
        else:
            assert "attribution" not in a or a["attribution"]
    assert schemas.errors("manifest", index(world), "#") == []


# ---- lane (measured, not declared) ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-48")
def test_fr_002_48_lane_is_computed_by_the_gate_from_the_measurements(world) -> None:
    pw.build_run(world, clip_bytes=5_242_880)
    assert world.cli("publish", RUN).code == 0
    clip, table = artefact(world, "clip.mp4"), artefact(world, "summary.json")
    assert clip["lane"] == "replay", "web drivable and small, but no interaction or run time measured: not live"
    assert table["lane"] == "static" and "lane_measurements" not in table
    assert clip["lane_measurements"]["max_asset_bytes"] == 5_242_880


@pytest.mark.req("FR-002-48")
def test_fr_002_48_an_onnx_with_a_measured_interaction_under_16_ms_is_live(world) -> None:
    pw.build_run(world, onnx=True, clip_bytes=5_242_880)
    assert world.cli("publish", RUN).code == 0
    a = artefact(world, "clip.mp4")
    assert (a["kind"], a["lane"], a["budget_class"]) == ("onnx", "live", "onnx")


# ---- FR-002-49: refusals ---------------------------------------------------------------------------------------------------------------------------------
def refuse(world: rw.World, *argv: str) -> str:
    repo_before, pins_before = world.snapshot_repo(), sorted(p.name for p in (world.store / "runs").rglob("PINNED"))
    r = world.cli("publish", *argv)
    assert r.code == 2, r.text
    assert len([ln for ln in r.text.splitlines() if ln.strip()]) <= 4 and "Traceback" not in r.text
    assert world.snapshot_repo() == repo_before, "a refused publish must change no repository file"
    assert sorted(p.name for p in (world.store / "runs").rglob("PINNED")) == pins_before
    return r.text.lower()


@pytest.mark.req("FR-002-49")
def test_fr_002_49_unknown_and_malformed_run_ids(world) -> None:
    pw.build_run(world)
    assert "20250101t000000z-nope" in refuse(world, "20250101T000000Z-nope")
    for bad in ("../../etc", "", "x" * 100, RUN + "\n", "20261007T120000Z-PUB", "a/b"):
        refuse(world, bad)


@pytest.mark.req("FR-002-49")
@pytest.mark.parametrize(
    ("label", "build", "reason"),
    [
        ("not-finished", {"finished": False}, ("finish", "complete")),
        ("dirty-tree", {"git_dirty": True}, ("dirty", "uncommitted")),
        ("fake-backend", {"backend": "fake"}, ("fake",)),
        ("test-launcher", {"launcher": "test"}, ("launcher",)),
        ("output-of-a-failed-stage", {"encode_status": "failed"}, ("succeed", "failed", "status")),
        ("unpinned-source", {"clip_inputs": ["src-by"], "pinned_sources": False}, ("pin", "sha256", "digest")),
        (
            "privacy-violation-spec-001-check",
            {"notes": ["built in C:\\Users\\someone\\secret"]},
            ("path", "privacy", "absolute"),
        ),
    ],
)
def test_fr_002_49_every_refusal_exits_2_names_the_reason_and_leaves_the_repository_unchanged(
    world, label: str, build: dict[str, Any], reason: tuple[str, ...]
) -> None:
    pw.build_run(world, **build)
    text = refuse(world, RUN)
    assert any(r in text for r in reason), f"{label}: the message must name the reason (one of {reason}): {text!r}"


@pytest.mark.req("FR-002-49")
@pytest.mark.parametrize(
    "tag",
    [
        None,
        "",
        "v1.0.0",
        "assets-v1",
        "assets-v1.0.1",
        "assets-v1.00.0001",
        "assets-v1.00.001\n",
        "ASSETS-v1.00.001",
        "assets-v1.00.001/../x",
    ],
)
def test_fr_002_49_a_release_asset_needs_a_well_formed_release_tag(world, tag: str | None) -> None:
    pw.build_run(world, clip_bytes=10_485_760)
    argv = [RUN] + ([] if tag is None else ["--release-tag", tag])
    text = refuse(world, *argv)
    assert "tag" in text


@pytest.mark.req("FR-002-49")
def test_fr_002_49_a_valid_release_tag_is_accepted_but_unneeded_tags_are_harmless(world) -> None:
    pw.build_run(world, clip_bytes=1000)
    assert world.cli("publish", RUN, "--release-tag", TAG).code == 0


# ---- FR-002-50: telemetry downsampling -----------------------------------------------------------------------------------------------------------------
def sample(i: int, **kw: Any) -> dict[str, Any]:
    base = {
        "t_s": float(i),
        "run_id": RUN,
        "stage": {"id": "st50_physics"},
        "shard": 0,
        "gpu": 0,
        "mem_used_bytes": 1000,
        "mem_total_bytes": 16000,
        "util_pct": 0.0,
        "power_w": 0.0,
        "power_limit_w": 100.0,
        "temp_c": 40.0,
        "sm_clock_mhz": 1000.0,
        "clocks_event_mask": 0,
        "energy_mj": 0,
        "nvenc_util_pct": None,
        "pcie_replays": 0,
    }
    base.update(kw)
    return base


@pytest.mark.req("FR-002-50")
def test_fr_002_50_buckets_aggregate_mean_max_and_bitwise_or_by_hand() -> None:
    from pitstudio.runner import publish

    rows = [
        sample(
            0,
            util_pct=10.0,
            power_w=100.0,
            sm_clock_mhz=1000.0,
            temp_c=60.0,
            mem_used_bytes=1000,
            clocks_event_mask=0x1,
        ),
        sample(
            1,
            util_pct=30.0,
            power_w=200.0,
            sm_clock_mhz=1200.0,
            temp_c=65.0,
            mem_used_bytes=3000,
            clocks_event_mask=0x4,
        ),
        sample(
            2,
            util_pct=50.0,
            power_w=300.0,
            sm_clock_mhz=1400.0,
            temp_c=70.0,
            mem_used_bytes=2000,
            clocks_event_mask=0x40,
        ),
        sample(
            3,
            util_pct=70.0,
            power_w=100.0,
            sm_clock_mhz=1600.0,
            temp_c=62.0,
            mem_used_bytes=5000,
            clocks_event_mask=0x40,
        ),
        sample(
            4,
            util_pct=90.0,
            power_w=500.0,
            sm_clock_mhz=1800.0,
            temp_c=80.0,
            mem_used_bytes=4000,
            clocks_event_mask=0x0,
        ),
        sample(
            5,
            util_pct=100.0,
            power_w=300.0,
            sm_clock_mhz=2000.0,
            temp_c=75.0,
            mem_used_bytes=4500,
            clocks_event_mask=0x8,
        ),
        sample(
            6, util_pct=0.0, power_w=0.0, sm_clock_mhz=800.0, temp_c=30.0, mem_used_bytes=100, clocks_event_mask=0x0
        ),
        sample(
            7, util_pct=20.0, power_w=40.0, sm_clock_mhz=1000.0, temp_c=35.0, mem_used_bytes=200, clocks_event_mask=0x20
        ),
    ]
    out = publish.downsample(rows, max_points=4)
    pts = out["points"]
    assert len(pts) == 4 and out["bucket_s"] > 0
    # buckets {0,1} {2,3} {4,5} {6,7}: mean of utilisation, power and clock; max of temperature and memory; OR of masks
    assert [p["util_pct"] for p in pts] == [
        pytest.approx(20.0),
        pytest.approx(60.0),
        pytest.approx(95.0),
        pytest.approx(10.0),
    ]
    assert [p["power_w"] for p in pts] == [
        pytest.approx(150.0),
        pytest.approx(200.0),
        pytest.approx(400.0),
        pytest.approx(20.0),
    ]
    assert [p["sm_clock_mhz"] for p in pts] == [
        pytest.approx(1100.0),
        pytest.approx(1500.0),
        pytest.approx(1900.0),
        pytest.approx(900.0),
    ]
    assert [p["temp_c"] for p in pts] == [65.0, 70.0, 80.0, 35.0]
    assert [p["mem_used_bytes"] for p in pts] == [3000, 5000, 4500, 200]
    assert [p["clocks_event_mask"] for p in pts] == [0x5, 0x40, 0x8, 0x20]
    ts = [p["t_s"] for p in pts]
    assert ts == sorted(ts) and len(set(ts)) == 4


@pytest.mark.req("FR-002-50")
def test_fr_002_50_4001_samples_fit_in_2000_points_deterministically_and_keep_the_extremes() -> None:
    from pitstudio.runner import publish

    rows = [
        sample(
            i / 2,
            util_pct=float(i % 100),
            temp_c=40.0 + (i % 37),
            mem_used_bytes=1000 + i,
            clocks_event_mask=1 << (i % 8),
            power_w=float(i % 250),
        )
        for i in range(4001)
    ]
    a = publish.downsample(rows, max_points=2000)
    b = publish.downsample(list(rows), max_points=2000)
    assert a == b, "deterministic"
    assert 1 <= len(a["points"]) <= 2000
    assert max(p["temp_c"] for p in a["points"]) == max(r["temp_c"] for r in rows)
    assert max(p["mem_used_bytes"] for p in a["points"]) == max(r["mem_used_bytes"] for r in rows)
    or_all = 0
    for r in rows:
        or_all |= r["clocks_event_mask"]
    got = 0
    for p in a["points"]:
        got |= p["clocks_event_mask"]
    assert got == or_all == 0xFF, "bitwise OR of every mask survives"
    assert all(0 <= p["util_pct"] <= 100 for p in a["points"])
    assert (
        abs(sum(p["util_pct"] for p in a["points"]) / len(a["points"]) - sum(r["util_pct"] for r in rows) / len(rows))
        < 2.0
    )


@pytest.mark.req("FR-002-50")
@pytest.mark.parametrize("n", [0, 1, 2, 1999, 2000, 2001])
def test_fr_002_50_short_series_are_not_inflated(n: int) -> None:
    from pitstudio.runner import publish

    out = publish.downsample([sample(i, util_pct=float(i % 100)) for i in range(n)], max_points=2000)
    assert len(out["points"]) <= max(n, 0) and len(out["points"]) <= 2000
    if n in (1, 2, 1999, 2000):
        assert len(out["points"]) >= 1 and sum(1 for _ in out["points"]) <= n


@pytest.mark.req("FR-002-50")
def test_fr_002_50_a_run_with_many_stages_stays_within_200_kb_by_halving_the_bucket_count() -> None:
    from pitstudio.runner import publish

    stages = []
    for k in range(64):
        key = {"id": "st10_terrain", "variant": f"v{k:02d}"}
        stages.append(
            {
                "key": key,
                "samples": [
                    sample(i / 2, stage=key, util_pct=float(i % 100), power_w=50.0 + (i % 40), temp_c=40.0 + (i % 30))
                    for i in range(3000)
                ],
            }
        )
    doc = publish.published_telemetry(RUN, stages, max_points=2000, max_bytes=204_800)
    assert schemas.errors("events", doc, "#/$defs/published_telemetry") == []
    text = json.dumps(doc, separators=(",", ":"))
    assert len(text.encode()) <= 204_800, f"{len(text.encode())} bytes"
    assert len(doc["stages"]) == 64 and all(1 <= len(s["points"]) <= 2000 for s in doc["stages"])
    assert doc == publish.published_telemetry(RUN, stages, max_points=2000, max_bytes=204_800), "deterministic"
    assert all(s["performance"] == "public" for s in doc["stages"])
