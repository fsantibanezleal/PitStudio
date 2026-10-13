# ruff: noqa: E501, PT018
"""T-003-013: artefact streaming (US-003-1).

Requirement: FR-003-13.

Expected behaviour (stated for the implementer): `GET /runs/{run_id}/artefacts/{artefact_id}` for an artefact listed in that run's
manifest streams the stored object (`$PITSTUDIO_STORE/cas/sha256/<aa>/<sha256 of the artefact record>`) with `Content-Type` from the
record's `media_type` (else `application/octet-stream`), `Content-Length`, `X-Content-Type-Options: nosniff`, the first byte within 2 s;
`Range: bytes=a-b` (also open-ended `a-` and suffix `-n`) is answered 206 with `Content-Range: bytes a-b/<total>`; an unsatisfiable range
is 416 with `Content-Range: bytes */<total>` (RFC 9110 section 14); an artefact that is not listed, or whose object is missing, is a 404
problem.
Oracles: the 300,000-byte fixture object (a known byte pattern, tests/support/console_world.py CLIP), RFC 9110 range arithmetic done by
hand, wall-clock bound for the first byte.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import console_world as cw
import publish_world as pw
import runner_world as rw

TOTAL = len(cw.CLIP)
URL = f"/runs/{cw.RUN_ID}/artefacts/a2-clip"


@pytest.fixture
def cons(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    c = cw.make_console_world(monkeypatch, tmp_path)
    yield c
    rw.cleanup_world(c.w)


@pytest.mark.req("FR-003-13")
def test_fr_003_13_a_listed_artefact_is_streamed_with_its_type_length_and_nosniff(cons) -> None:
    r = cons.client.get(URL)
    assert r.status == 200, r.text[:200]
    assert r.body == cw.CLIP
    assert r.header("content-type") == "video/mp4"
    assert r.header("content-length") == str(TOTAL)
    assert r.header("x-content-type-options") == "nosniff"


@pytest.mark.req("FR-003-13")
def test_fr_003_13_an_artefact_without_a_media_type_is_octet_stream(cons) -> None:
    r = cons.client.get(f"/runs/{cw.RUN_ID}/artefacts/a2-notes")
    assert r.status == 200 and r.body == cw.NOTES
    assert r.header("content-type") == "application/octet-stream"
    assert r.header("content-length") == str(len(cw.NOTES)) and r.header("x-content-type-options") == "nosniff"


@pytest.mark.req("FR-003-13")
def test_fr_003_13_the_first_byte_arrives_within_2_seconds(cons) -> None:
    t0 = time.monotonic()
    s = cons.client.stream(URL)
    try:
        s.wait_headers(2.0)
        assert s.status == 200
        while not s.raw and time.monotonic() - t0 < 2.0:
            s._pump(0.01)
        assert s.raw, "no body byte within 2 s"
        assert time.monotonic() - t0 < 2.0
        while not s.ended.is_set() and time.monotonic() - t0 < 20:
            s._pump(0.05)
        assert s.raw == cw.CLIP
    finally:
        s.close(2)


@pytest.mark.req("FR-003-13")
@pytest.mark.parametrize(
    ("header", "first", "last"),
    [
        ("bytes=0-99", 0, 99),
        ("bytes=100-199", 100, 199),
        ("bytes=0-0", 0, 0),
        ("bytes=299900-", 299900, TOTAL - 1),
        ("bytes=-50", TOTAL - 50, TOTAL - 1),
        ("bytes=299999-299999", TOTAL - 1, TOTAL - 1),
        ("bytes=299990-999999", 299990, TOTAL - 1),
        ("bytes=65535-65536", 65535, 65536),
    ],
)
def test_fr_003_13_a_range_is_answered_206_with_content_range(cons, header: str, first: int, last: int) -> None:
    r = cons.client.get(URL, headers={"Range": header})
    assert r.status == 206, f"{header}: {r.status} {r.text[:120]}"
    assert r.header("content-range") == f"bytes {first}-{last}/{TOTAL}"
    assert r.body == cw.CLIP[first : last + 1]
    assert r.header("content-length") == str(last - first + 1)
    assert r.header("content-type") == "video/mp4" and r.header("x-content-type-options") == "nosniff"


@pytest.mark.req("FR-003-13")
@pytest.mark.parametrize(
    "header",
    [f"bytes={TOTAL}-", f"bytes={TOTAL}-{TOTAL + 10}", "bytes=500000-600000", "bytes=-0", "bytes=99999999999-"],
    ids=["at-end", "past-end", "far-past-end", "zero-suffix", "huge-start"],
)
def test_fr_003_13_an_unsatisfiable_range_is_416_with_the_total(cons, header: str) -> None:
    r = cons.client.get(URL, headers={"Range": header})
    assert r.status == 416, f"{header}: {r.status}"
    assert r.header("content-range") == f"bytes */{TOTAL}"
    assert (r.header("content-type") or "").startswith("application/problem+json")
    assert r.header("x-content-type-options") == "nosniff"


@pytest.mark.req("FR-003-13")
@pytest.mark.parametrize(
    "header",
    [
        "bytes=5-1",
        "items=0-5",
        "bytes=0-9,20-29",
        "bytes=abc",
        "bytes=",
        "bytes=0-99999999999999999999",
        "",
        "bytes=-",
        "bytes=0-9,",
        "BYTES=0-9",
        "bytes=0-9 ; x",
    ],
    ids=[
        "inverted",
        "other-unit",
        "multi",
        "garbage",
        "empty-spec",
        "huge-end",
        "empty-header",
        "dash",
        "trailing-comma",
        "uppercase-unit",
        "junk-suffix",
    ],
)
def test_fr_003_13_malformed_or_exotic_range_headers_never_cause_a_server_error(cons, header: str) -> None:
    r = cons.client.get(URL, headers={"Range": header})
    assert r.status in (200, 206, 400, 416), f"{header!r}: {r.status}"
    assert r.status < 500 and r.exception is None
    if r.status == 200:
        assert r.body == cw.CLIP
    if r.status == 206 and r.header("content-range"):
        assert r.header("content-range").endswith(f"/{TOTAL}")


@pytest.mark.req("FR-003-13")
def test_fr_003_13_not_listed_or_missing_artefacts_are_404_problems(cons) -> None:
    for target in (
        f"/runs/{cw.RUN_ID}/artefacts/not-listed",
        f"/runs/{cw.OTHER_RUN_ID}/artefacts/a2-clip",
        "/runs/20250101T000000Z-nothing/artefacts/a2-clip",
    ):
        r = cons.client.get(target)
        assert r.status == 404, f"{target}: {r.status}"
        assert (r.header("content-type") or "").startswith("application/problem+json")
    # listed in the manifest but the object is gone from the store
    obj = cons.w.store / "cas" / "sha256" / pw.sha(cw.CLIP)[:2] / pw.sha(cw.CLIP)
    obj.unlink()
    gone = cons.client.get(URL)
    assert gone.status == 404 and (gone.header("content-type") or "").startswith("application/problem+json")
    assert cons.client.get(f"/runs/{cw.RUN_ID}/artefacts/a2-notes").status == 200


@pytest.mark.req("FR-003-13")
def test_fr_003_13_an_artefact_of_a_run_with_an_invalid_manifest_is_not_served(cons) -> None:
    r = cons.client.get(f"/runs/{cw.BROKEN_RUN_ID}/artefacts/a2-clip")
    assert r.status in (404, 409)
    assert (r.header("content-type") or "").startswith("application/problem+json")
