# ruff: noqa: E501, PT018
"""T-008-015: classified retries with back-off, Range resume and 200 restart, idempotent cached re-run with no request.

Requirements: FR-008-12, P-008-02, NFR-008-02.

Spec: specs/008-data-pipeline/spec.md FR-008-12 (retry up to 5 times with back-offs of 1, 2, 4, 8 and 16 s; resume at the
received offset when the server answers 206, restart on 200; other 4xx fail at once), P-008-02, NFR-008-02.

Oracle: the uninterrupted transfer's bytes (the fixture payload itself) and its `hashlib` digest; the back-off sequence
1, 2, 4, 8, 16 written out in the test; a transport that raises on any request (NFR-008-02).

Expected API of the implementation: as in test_t_008_012 (`run_download(..., transport, sleep, now, env, ...)`). The
`sleep` callable receives each back-off delay in seconds (no sleep after the last attempt); a source that fails after the
last retry ends with `DownloadFailed` in `result.errors[id]`; its record has `status: unavailable`, `attempts` = number of
tries (1 + retries, at most 6). The first request is a plain GET; a retry after `n` received bytes sends
`Range: bytes=n-` (a restart from 0 may send no Range header or `bytes=0-`).
`pitstudio_pipeline.errors.DownloadFailed(Exception)`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import _p008_kit as kit
import httpx
import pytest
from pitstudio_pipeline.errors import DownloadFailed

# isort: split
from hypothesis import given, settings
from hypothesis import strategies as st

URL = "https://example.org/data/a.bin"
BACKOFFS = [1, 2, 4, 8, 16]
DATA = kit.payload(3000, 42)


def _entry(data: bytes = DATA):
    return [kit.entry("r", [kit.file_rec(URL, data)])]


def _fail(kind: object):
    return (lambda r: httpx.Response(kind, content=b"err")) if isinstance(kind, int) else kind


TRANSIENT = [
    httpx.ConnectError("refused"),
    httpx.ConnectTimeout("slow"),
    httpx.ReadTimeout("slow"),
    httpx.RemoteProtocolError("closed"),
    429,
    500,
    502,
    503,
    504,
]
TRANSIENT_IDS = [
    "connect-error",
    "connect-timeout",
    "read-timeout",
    "remote-protocol-error",
    "429",
    "500",
    "502",
    "503",
    "504",
]


@pytest.mark.req("FR-008-12")
@pytest.mark.parametrize("fail", TRANSIENT, ids=TRANSIENT_IDS)
def test_one_transient_failure_is_retried_after_one_second(fail: object, tmp_path: Path) -> None:
    sleeps = kit.Sleeps()
    net = kit.Net({URL: kit.Seq(_fail(fail), DATA)})
    result = kit.run(tmp_path, _entry(), net, sleep=sleeps)
    assert result.exit_status == 0, result.errors
    assert sleeps == [1]
    assert (tmp_path / "data" / "raw" / "r" / "a.bin").read_bytes() == DATA
    assert result.records[0]["attempts"] == 2 and len(net.requests) == 2


@pytest.mark.req("FR-008-12")
def test_five_retries_use_the_full_back_off_ladder_and_the_sixth_try_succeeds(tmp_path: Path) -> None:
    sleeps = kit.Sleeps()
    net = kit.Net({URL: kit.Seq(*[_fail(503)] * 5, DATA)})
    result = kit.run(tmp_path, _entry(), net, sleep=sleeps)
    assert result.exit_status == 0
    assert sleeps == BACKOFFS
    assert result.records[0]["attempts"] == 6 and len(net.requests) == 6


@pytest.mark.req("FR-008-12")
@pytest.mark.parametrize("fail", [httpx.ConnectError("x"), 500, 429], ids=["connect", "500", "429"])
def test_after_the_last_retry_the_source_fails_with_download_failed(fail: object, tmp_path: Path) -> None:
    sleeps = kit.Sleeps()
    net = kit.Net({URL: kit.Seq(_fail(fail))})  # the failure repeats forever
    result = kit.run(tmp_path, _entry(), net, sleep=sleeps)
    assert isinstance(result.errors["r"], DownloadFailed) and result.exit_status != 0
    assert sleeps == BACKOFFS, "five back-offs and no sleep after the last attempt"
    assert len(net.requests) == 6
    assert result.records[0]["status"] == "unavailable" and result.records[0]["attempts"] == 6
    assert kit.files_under(tmp_path / "data") == []


@pytest.mark.req("FR-008-12")
@pytest.mark.parametrize("code", [400, 401, 403, 404, 408, 410, 418, 451])
def test_other_4xx_fail_at_once_without_retry(code: int, tmp_path: Path) -> None:
    sleeps = kit.Sleeps()
    net = kit.Net({URL: kit.Seq(_fail(code))})
    result = kit.run(tmp_path, _entry(), net, sleep=sleeps)
    assert isinstance(result.errors["r"], DownloadFailed) and result.exit_status != 0
    assert len(net.requests) == 1 and sleeps == []
    assert result.records[0]["attempts"] == 1


# ------------------------------------------------------------------------------------------------ resume and restart
def _cut_then(first_bytes: int, second):
    def cut(r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(DATA))},
            stream=kit.CutStream(DATA[:first_bytes], httpx.ReadError("connection cut")),
        )

    return kit.Seq(cut, second)


@pytest.mark.req("FR-008-12")
def test_resume_from_the_received_offset_when_the_server_answers_206(tmp_path: Path) -> None:
    sleeps = kit.Sleeps()
    net = kit.Net({URL: _cut_then(1234, kit.range_server(DATA))})
    result = kit.run(tmp_path, _entry(), net, sleep=sleeps)
    assert result.exit_status == 0, result.errors
    assert net.requests[1].headers.get("range") == "bytes=1234-"
    assert (tmp_path / "data" / "raw" / "r" / "a.bin").read_bytes() == DATA
    assert result.records[0]["sha256"] == hashlib.sha256(DATA).hexdigest() and sleeps == [1]


@pytest.mark.req("FR-008-12")
def test_restart_when_the_server_answers_200_to_a_range_request(tmp_path: Path) -> None:
    net = kit.Net({URL: _cut_then(1234, kit.range_server(DATA, honour_range=False))})
    result = kit.run(tmp_path, _entry(), net)
    assert result.exit_status == 0, result.errors
    assert (tmp_path / "data" / "raw" / "r" / "a.bin").read_bytes() == DATA, "no duplicated prefix after a restart"
    assert result.records[0]["bytes"] == len(DATA)


@pytest.mark.req("FR-008-12")
def test_two_interruptions_resume_twice(tmp_path: Path) -> None:
    sleeps = kit.Sleeps()

    def second(r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            206,
            headers={
                "Content-Range": f"bytes 1000-{len(DATA) - 1}/{len(DATA)}",
                "Content-Length": str(len(DATA) - 1000),
            },
            stream=kit.CutStream(DATA[1000:2000], httpx.ReadError("cut again")),
        )

    net = kit.Net({URL: kit.Seq(_cut_then(1000, second).items[0], second, kit.range_server(DATA))})
    result = kit.run(tmp_path, _entry(), net, sleep=sleeps)
    assert result.exit_status == 0, result.errors
    assert [r.headers.get("range") for r in net.requests[1:]] == ["bytes=1000-", "bytes=2000-"]
    assert sleeps == [1, 2]
    assert (tmp_path / "data" / "raw" / "r" / "a.bin").read_bytes() == DATA


@pytest.mark.req("FR-008-12")
def test_a_misaligned_206_can_never_promote_corrupt_bytes(tmp_path: Path) -> None:
    def bad(r: httpx.Request) -> httpx.Response:
        return httpx.Response(206, content=DATA[:1500], headers={"Content-Range": f"bytes 0-1499/{len(DATA)}"})

    net = kit.Net({URL: _cut_then(1000, bad)})
    result = kit.run(tmp_path, _entry(), net)
    final = tmp_path / "data" / "raw" / "r" / "a.bin"
    if final.exists():  # the implementation noticed and restarted: then the bytes are right
        assert final.read_bytes() == DATA
    else:
        assert result.exit_status != 0 and "r" in result.errors


# ------------------------------------------------------------------------------------------------ P-008-02
@pytest.mark.req("P-008-02")
@settings(max_examples=40, deadline=None)
@given(offset=st.integers(min_value=0, max_value=len(DATA) - 1), honour=st.booleans())
def test_resumed_download_equals_the_uninterrupted_one(offset: int, honour: bool, tmp_path_factory) -> None:
    tmp = tmp_path_factory.mktemp("resume")
    net = kit.Net({URL: _cut_then(offset, kit.range_server(DATA, honour_range=honour))})
    result = kit.run(tmp, _entry(), net)
    assert result.exit_status == 0, result.errors
    got = (tmp / "data" / "raw" / "r" / "a.bin").read_bytes()
    assert got == DATA
    assert result.records[0]["sha256"] == hashlib.sha256(DATA).hexdigest()


# ------------------------------------------------------------------------------------------------ NFR-008-02
@pytest.mark.req("NFR-008-02")
def test_second_run_with_everything_cached_opens_no_connection_and_changes_no_file(tmp_path: Path) -> None:
    files = [(f"https://example.org/data/f{i}.bin", kit.payload(500 + 100 * i, 70 + i)) for i in range(3)]
    entries = [kit.entry(f"s{i}", [kit.file_rec(u, d)]) for i, (u, d) in enumerate(files)]
    first = kit.run(tmp_path, entries, kit.Net(dict(files)))
    assert first.exit_status == 0
    raw = tmp_path / "data" / "raw"
    before = kit.tree_digest(raw)
    mtimes = {p: p.stat().st_mtime_ns for p in kit.files_under(raw)}
    everything = kit.tree_digest(tmp_path / "data")

    net = kit.Net(forbid=True)
    second = kit.run(tmp_path, entries, net)
    assert net.requests == []
    assert second.exit_status == 0 and all(r["status"] == "verified" for r in second.records)
    assert kit.tree_digest(raw) == before
    assert {p: p.stat().st_mtime_ns for p in kit.files_under(raw)} == mtimes
    assert kit.tree_digest(tmp_path / "data") == everything
