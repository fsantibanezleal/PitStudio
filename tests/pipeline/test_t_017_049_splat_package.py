"""T-017-049: splat packaging, pruning to the cap, hostile PLY / SPZ (pipeline; the badge and the route-only
loading are in
web/e2e/e2-splat-view.spec.ts).

Requirements: FR-017-41, FR-017-49, NFR-017-05.

Spec: specs/017-planning-survey/spec.md
- FR-017-41: the splat is packaged PLY -> SPZ with `@playcanvas/splat-transform` 3.9.0; if the SPZ exceeds 25 x
  10^6 bytes
  the lowest-opacity Gaussians are pruned until it fits, the count recorded; the E2 view shows it with the badge
  "captured
  (photogrammetry), not simulated";
- FR-017-49: if a PLY or SPZ file fails to parse, declares more than 10^7 Gaussians, or has non-finite attributes, the
  packaging stage rejects it and the splat view shows "Not run -- <reason>" (an em dash);
- NFR-017-05: splat asset <= 25 x 10^6 bytes, requested only on the splat route (never in the first view).
plan.md test strategy rows FR-017-41 / FR-017-49 (a fixture PLY above the cap (pruning count by hand); malformed
PLY / SPZ
files) and NFR-017-05 (file sizes; request log of the first view).

Oracles:
- the pruning count by hand against a fake `splat-transform` whose SPZ size is exactly 1,000 bytes per Gaussian (so
  the cap
  of 25,000,000 bytes holds 25,000 Gaussians): a PLY of 30,000 Gaussians needs at least 5,000 removed, and the
  removed ones
  must be those of lowest opacity (the fake records the PLY it was given; the opacity of every kept Gaussian is not
  below
  that of any removed one, by construction opacity logit = index / 1,000);
- the PLY format (header `element vertex N`, binary little-endian float32 properties; Gaussian-splat PLY files
  store the
  opacity as a logit) written by the test with `struct`;
- the SPZ container as documented by Niantic's `spz` project (UNVERIFIED here): a gzip stream whose first 16 bytes
  are the
  header magic 0x5053474E ("NGSP"), version (uint32), number of points (uint32), spherical-harmonics degree (uint8),
  fractional bits (uint8), flags (uint8), reserved (uint8), followed by 19 bytes per point at version 2 with no
  spherical harmonics (positions 9, alphas 1, colours 3, scales 3, rotations 3); a valid 5-point SPZ and hostile ones
  (not gzip, truncated gzip, wrong magic, a header declaring 10^7 + 1 points) built by the test;
- `thresholds.yaml` `survey.splat_bytes_max` = 25,000,000 (the proposed key approved by the maintainer).

Expected public API (module `pitstudio_pipeline.survey.splat`, `pipeline/` environment):
    SPLAT_BYTES_MAX = 25_000_000; MAX_GAUSSIANS = 10_000_000; SPLAT_TRANSFORM_VERSION = "3.9.0"
    class SplatRejected(Exception)           # `.reason`; the view label is f"Not run â€” {reason}"
    inspect_splat(path: Path) -> SplatInfo   # .n_gaussians, .kind ("ply" | "spz"); SplatRejected for a file that
    does not
        parse, declares more than MAX_GAUSSIANS Gaussians (checked on the header, before reading the body), or
        (PLY) has
        a non-finite x, y, z, opacity, scale or rotation value
    view_label(error: SplatRejected) -> str  # "Not run â€” <reason>"
    package_splat(ply: Path, out_spz: Path, *, transform: Sequence[str], cap_bytes: int = SPLAT_BYTES_MAX) ->
    PackageResult
        verifies `transform + ["--version"]` prints SPLAT_TRANSFORM_VERSION, inspects the PLY, runs
        `transform + [str(ply), str(out_spz)]`; while the SPZ is larger than the cap it removes the Gaussians of
        lowest
        opacity (at least the number the size ratio demands) and converts again; PackageResult: spz_path, bytes (<=
        cap),
        n_in, n_out, pruned (n_in - n_out); no pruning is done when the first SPZ fits. SplatRejected for a hostile
        PLY.
"""

from __future__ import annotations

import gzip
import json
import struct
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
import yaml
from pitstudio_pipeline.survey.splat import (
    MAX_GAUSSIANS,
    SPLAT_BYTES_MAX,
    SplatRejected,
    inspect_splat,
    package_splat,
    view_label,
)

ROOT = Path(__file__).resolve().parents[2]
EM_DASH = "â€”"
PROPS = ("x", "y", "z", "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3")


def _ply(
    path: Path, n: int, *, opacity: np.ndarray | None = None, bad: dict | None = None, declared: int | None = None
) -> Path:
    data = np.zeros((n, len(PROPS)), dtype="<f4")
    data[:, 0] = np.arange(n) * 0.01
    data[:, 3] = opacity if opacity is not None else np.arange(n) / 1000.0
    data[:, 4:7] = -3.0
    data[:, 7] = 1.0
    for (row, col), value in (bad or {}).items():
        data[row, PROPS.index(col)] = value
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {n if declared is None else declared}\n"
        + "".join(f"property float {p}\n" for p in PROPS)
        + "end_header\n"
    )
    path.write_bytes(header.encode() + data.tobytes())
    return path


def _spz(
    path: Path, *, n: int = 5, magic: int = 0x5053474E, declared: int | None = None, truncate: int | None = None
) -> Path:
    header = struct.pack("<IIIBBBB", magic, 2, n if declared is None else declared, 0, 12, 0, 0)
    body = bytes(19 * n)
    blob = gzip.compress(header + body)
    path.write_bytes(blob if truncate is None else blob[:truncate])
    return path


FAKE_TRANSFORM = textwrap.dedent(
    """
    import json, os, struct, sys
    log = os.environ["FAKE_SPLAT_LOG"]
    if sys.argv[1] == "--version":
        print("3.9.0")
        sys.exit(0)
    src, dst = sys.argv[1], sys.argv[2]
    raw = open(src, "rb").read()
    head, _, body = raw.partition(b"end_header\\n")
    n = int([l for l in head.decode().split("\\n") if l.startswith("element vertex")][0].split()[2])
    cols = 11
    opacity = [struct.unpack_from("<f", body, (i * cols + 3) * 4)[0] for i in range(n)]
    open(log, "a").write(json.dumps({"n": n, "min_opacity": min(opacity)}) + "\\n")
    open(dst, "wb").write(b"\\0" * (1000 * n))
    """
)


def _tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], Path]:
    script = tmp_path / "fake_splat_transform.py"
    script.write_text(FAKE_TRANSFORM, encoding="utf-8")
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("FAKE_SPLAT_LOG", str(log))
    return [sys.executable, str(script)], log


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-41 and NFR-017-05
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("NFR-017-05")
def test_the_cap_is_the_25_million_byte_threshold_key() -> None:
    thresholds = yaml.safe_load((ROOT / "specs/000-foundation/thresholds.yaml").read_text("utf-8"))
    assert thresholds["survey"]["splat_bytes_max"] == SPLAT_BYTES_MAX == 25_000_000


@pytest.mark.req("FR-017-41")
def test_a_splat_that_fits_is_converted_once_without_pruning(tmp_path: Path, monkeypatch) -> None:
    transform, log = _tool(tmp_path, monkeypatch)
    result = package_splat(_ply(tmp_path / "s.ply", 20_000), tmp_path / "s.spz", transform=transform)
    assert (result.n_in, result.n_out, result.pruned) == (20_000, 20_000, 0)
    assert result.bytes == 20_000_000 <= SPLAT_BYTES_MAX
    assert result.spz_path == tmp_path / "s.spz"
    assert len(log.read_text().splitlines()) == 1  # one conversion


@pytest.mark.req("FR-017-41")
def test_a_splat_over_the_cap_is_pruned_by_lowest_opacity_until_it_fits(tmp_path: Path, monkeypatch) -> None:
    transform, log = _tool(tmp_path, monkeypatch)
    result = package_splat(_ply(tmp_path / "s.ply", 30_000), tmp_path / "s.spz", transform=transform)
    assert result.n_in == 30_000
    assert result.bytes <= SPLAT_BYTES_MAX
    assert result.pruned >= 5_000  # 30,000 x 1,000 B = 30 MB: at least 5,000 Gaussians must go
    assert result.n_out == 30_000 - result.pruned
    assert result.n_out >= 25_500  # pruned only as far as needed (a small safety margin is allowed)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    final = calls[-1]
    assert final["n"] == result.n_out
    assert (
        final["min_opacity"] >= (result.pruned - 1) / 1000.0
    )  # the removed ones are the lowest-opacity (indices 0 ..)
    assert (tmp_path / "s.spz").stat().st_size == result.bytes


@pytest.mark.req("FR-017-41")
def test_pruning_keeps_the_highest_opacity_gaussians_whatever_their_order(tmp_path: Path, monkeypatch) -> None:
    transform, log = _tool(tmp_path, monkeypatch)
    opacity = np.random.default_rng(0).permutation(30_000) / 1000.0  # shuffled opacities 0.000 .. 29.999
    result = package_splat(_ply(tmp_path / "s.ply", 30_000, opacity=opacity), tmp_path / "s.spz", transform=transform)
    final = json.loads(log.read_text().splitlines()[-1])
    assert final["min_opacity"] >= (result.pruned - 1) / 1000.0


@pytest.mark.req("FR-017-41")
def test_the_transform_tool_must_be_version_3_9_0(tmp_path: Path, monkeypatch) -> None:
    script = tmp_path / "old.py"
    script.write_text('import sys\nprint("3.8.0")\n', encoding="utf-8")
    monkeypatch.setenv("FAKE_SPLAT_LOG", str(tmp_path / "log"))
    with pytest.raises(SplatRejected) as info:
        package_splat(_ply(tmp_path / "s.ply", 100), tmp_path / "s.spz", transform=[sys.executable, str(script)])
    assert "version" in info.value.reason


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-49
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-49")
def test_valid_ply_and_spz_files_are_inspected(tmp_path: Path) -> None:
    ply = inspect_splat(_ply(tmp_path / "a.ply", 7))
    assert (ply.n_gaussians, ply.kind) == (7, "ply")
    spz = inspect_splat(_spz(tmp_path / "a.spz", n=5))
    assert (spz.n_gaussians, spz.kind) == (5, "spz")


@pytest.mark.req("FR-017-49")
@pytest.mark.parametrize(
    "content",
    [b"", b"not a ply", b"ply\nformat ascii 1.0\nend_header\n", b"\x00" * 64],
    ids=["empty", "text", "no-vertex", "zeros"],
)
def test_a_ply_that_does_not_parse_is_rejected(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "bad.ply"
    path.write_bytes(content)
    with pytest.raises(SplatRejected) as info:
        inspect_splat(path)
    assert info.value.reason


@pytest.mark.req("FR-017-49")
def test_a_truncated_ply_body_is_rejected(tmp_path: Path) -> None:
    path = _ply(tmp_path / "t.ply", 100)
    path.write_bytes(path.read_bytes()[:-50])
    with pytest.raises(SplatRejected):
        inspect_splat(path)


@pytest.mark.req("FR-017-49")
def test_a_ply_declaring_more_than_10_million_gaussians_is_rejected_from_its_header(tmp_path: Path) -> None:
    assert MAX_GAUSSIANS == 10_000_000
    path = _ply(tmp_path / "big.ply", 3, declared=MAX_GAUSSIANS + 1)  # three rows of data, a header claiming 10^7 + 1
    with pytest.raises(SplatRejected) as info:
        inspect_splat(path)
    assert "10000000" in info.value.reason.replace(",", "").replace("_", "") or "10" in info.value.reason
    ok = _ply(tmp_path / "edge.ply", 3, declared=3)
    assert inspect_splat(ok).n_gaussians == 3


@pytest.mark.req("FR-017-49")
@pytest.mark.parametrize("column", ["x", "y", "z", "opacity", "scale_1", "rot_3"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_attribute_is_rejected(tmp_path: Path, column: str, value: float) -> None:
    path = _ply(tmp_path / "nan.ply", 50, bad={(17, column): value})
    with pytest.raises(SplatRejected) as info:
        inspect_splat(path)
    assert "finite" in info.value.reason


@pytest.mark.req("FR-017-49")
@pytest.mark.parametrize(
    ("kwargs", "word"),
    [
        ({"magic": 0x12345678}, "magic"),
        ({"declared": 10_000_001}, "10"),
        ({"truncate": 20}, "parse"),
    ],
    ids=["magic", "too-many", "truncated"],
)
def test_a_hostile_spz_is_rejected(tmp_path: Path, kwargs: dict, word: str) -> None:
    path = _spz(tmp_path / "bad.spz", **kwargs)
    with pytest.raises(SplatRejected) as info:
        inspect_splat(path)
    assert word in info.value.reason or "parse" in info.value.reason


@pytest.mark.req("FR-017-49")
def test_a_spz_that_is_not_gzip_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "plain.spz"
    path.write_bytes(b"NGSP" + bytes(64))
    with pytest.raises(SplatRejected):
        inspect_splat(path)


@pytest.mark.req("FR-017-49")
def test_the_view_label_is_not_run_an_em_dash_and_the_reason(tmp_path: Path) -> None:
    path = tmp_path / "bad.ply"
    path.write_bytes(b"garbage")
    with pytest.raises(SplatRejected) as info:
        inspect_splat(path)
    assert view_label(info.value) == f"Not run {EM_DASH} {info.value.reason}"


@pytest.mark.req("FR-017-49")
def test_packaging_rejects_a_hostile_ply_before_running_the_tool(tmp_path: Path, monkeypatch) -> None:
    transform, log = _tool(tmp_path, monkeypatch)
    with pytest.raises(SplatRejected):
        package_splat(
            _ply(tmp_path / "n.ply", 100, bad={(5, "x"): float("nan")}), tmp_path / "n.spz", transform=transform
        )
    assert not log.exists()  # the tool was never run
    assert not (tmp_path / "n.spz").exists()
