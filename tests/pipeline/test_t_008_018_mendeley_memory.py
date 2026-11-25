# ruff: noqa: E501, PT018
"""T-008-018: peak memory of s00_download while hashing and extracting a very large archive (slow, local only).

Requirements: NFR-008-01.

Spec: specs/008-data-pipeline/spec.md NFR-008-01 (peak memory <= 1 GB resident while hashing and extracting the
4,230,116,058-byte Mendeley archive, measured by psutil sampling) and plan.md ("Real-archive tests run locally only").

Oracle: `psutil` resident-set sampling of the running process every 20 ms (reference measurement); the 1 GiB bound of the
spec (1,073,741,824 bytes); a digest computed with `hashlib` over the same bytes.

Two tests, both marked `slow` (CI runs `-m "not gpu and not slow"`):
1. a scaled model of the NFR: a 1.3 GiB stored zip of incompressible bytes is served by a streaming mocked transport,
   downloaded, verified and extracted by the stage; a reader that holds a whole file in memory would exceed 1 GiB;
2. the real archive, verified from the maintainer's cache (`PITSTUDIO_DATA/raw/mendeley-78ht3pjsr4/research-data.7z`);
   this test fails with a clear message where the archive is absent, which is why it is only collected with `-m slow`.

Expected API of the implementation: as in test_t_008_012 and test_t_008_017 (`run_download`, `extract_archive`).
"""

from __future__ import annotations

import os
import threading
import time
import zipfile
from pathlib import Path

import _p008_kit as kit
import httpx
import pytest
from pitstudio_pipeline.download import run_download

GIB = 1 << 30
SIZE = int(1.3 * GIB)
URL = "https://example.org/d/large.zip"


class _FileStream(httpx.SyncByteStream):
    def __init__(self, path: Path, chunk: int = 1 << 20) -> None:
        self.path, self.chunk = path, chunk

    def __iter__(self):
        with self.path.open("rb") as fh:
            while block := fh.read(self.chunk):
                yield block


class PeakRss:
    """Samples the resident set of this process in a thread (psutil, as NFR-008-01 prescribes)."""

    def __init__(self) -> None:
        import psutil

        self._proc = psutil.Process()
        self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, self._proc.memory_info().rss)
            time.sleep(0.02)

    def __enter__(self) -> PeakRss:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join()
        self.peak = max(self.peak, self._proc.memory_info().rss)


def _big_stored_zip(path: Path) -> int:
    rng_block = kit.payload(1 << 20, 99)
    with (
        zipfile.ZipFile(path, "w", zipfile.ZIP_STORED, allowZip64=True) as z,
        z.open("data/large.csv", "w", force_zip64=True) as w,
    ):
        for i in range(SIZE // len(rng_block)):
            w.write(rng_block[i % 251 :] + rng_block[: i % 251])  # varying block, same length
    return path.stat().st_size


@pytest.mark.slow
@pytest.mark.req("NFR-008-01")
def test_hash_and_extract_of_a_1_3_gib_archive_stay_within_1_gib_resident(tmp_path: Path) -> None:
    import hashlib

    src = tmp_path / "src" / "large.zip"
    src.parent.mkdir()
    size = _big_stored_zip(src)
    with src.open("rb") as fh:
        digest = hashlib.file_digest(fh, "sha256").hexdigest()
    f = kit.file_rec(URL, None, kind="archive", extract=["data/*.csv"], uncompressed_bytes=size)
    f["sha256"], f["bytes"] = digest, size
    net = kit.Net({URL: lambda r: httpx.Response(200, headers={"Content-Length": str(size)}, stream=_FileStream(src))})
    with PeakRss() as meter:
        result = kit.run(tmp_path, [kit.entry("big", [f])], net)
    assert result.exit_status == 0, result.errors
    extracted = tmp_path / "data" / "interim" / "big" / "data" / "large.csv"
    assert extracted.stat().st_size == (SIZE // (1 << 20)) * (1 << 20)
    assert meter.peak <= GIB, f"peak resident memory {meter.peak / GIB:.2f} GiB exceeds 1 GiB"


@pytest.mark.slow
@pytest.mark.req("NFR-008-01")
def test_real_mendeley_archive_is_verified_from_cache_within_1_gib_resident(tmp_path: Path) -> None:
    root = os.environ.get("PITSTUDIO_DATA")
    archive = Path(root) / "raw" / "mendeley-78ht3pjsr4" / "research-data.7z" if root else None
    if archive is None or not archive.is_file():
        pytest.fail(
            "the real archive is absent: set PITSTUDIO_DATA to the maintainer's data root (this test runs only with -m slow)"
        )
    f = kit.file_rec(
        "https://data.mendeley.com/public-files/datasets/78ht3pjsr4/files/research-data/file_downloaded",
        None,
        kind="archive",
        name="research-data.7z",
    )
    # published values of the dataset (spec 008 section 7): 4,230,116,058 bytes, publisher SHA-256
    f["sha256"], f["bytes"] = "7f4336a4fe1f83e3c828eed4c73e036d7694f94076b6f040e6211315693f402d", 4_230_116_058
    entry = kit.entry(
        "mendeley-78ht3pjsr4",
        [f],
        spdx="CC-BY-4.0",
        licence_class="attribution",
        redistribution="derived-only",
        attribution="Mendeley Data, dataset 78ht3pjsr4, CC BY 4.0",
    )
    reg = kit.write_registry(tmp_path / "cfg", [entry])
    net = kit.Net(forbid=True)
    with PeakRss() as meter:
        result = run_download(
            reg,
            Path(root),
            transport=net.transport,
            schema_path=kit.draft_schema_path("sources.schema.json"),
            env=kit.env_with(),
            now=kit.NOW,
            offline=True,
        )
    assert net.requests == [] and result.exit_status == 0, result.errors
    assert result.records[0]["status"] == "verified" and result.records[0]["bytes"] == 4_230_116_058
    assert meter.peak <= GIB  # extraction memory of the real archive is measured by the scaled test above
