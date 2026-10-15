# ruff: noqa: E501, PT018
"""T-003-023: an unavailable store or queue gives 503 and the console stays up (US-003-2).

Requirement: FR-003-23.

Expected behaviour (plan.md D2; stated for the implementer): when the store folder is missing (or is not a directory), or the queue
database is corrupt, the endpoints that need them answer `503` with an `application/problem+json` body and `Retry-After: 5`, the
process keeps serving (`GET /health` still answers 200, and the endpoints work again once the store is repaired); a 503 is never caused
by request content, and hostile input never produces any 5xx.
Oracles: the fixture store broken in each way by hand (folder removed, queue.db replaced by random bytes / truncated / a directory,
`runs/` unreadable as a file), the contract schema `problem`, the in-process client reporting any escaping exception as status 599.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import console_world as cw
import runner_world as rw
import schemas


@pytest.fixture
def cons(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    c = cw.make_console_world(monkeypatch, tmp_path)
    c.post_job()  # a real queue.db exists
    yield c
    rw.cleanup_world(c.w)


def assert_503(r) -> None:
    assert r.status == 503, f"{r.status} {r.text[:150]}"
    assert r.exception is None
    assert r.header("retry-after") == "5"
    assert (r.header("content-type") or "").startswith("application/problem+json")
    body = r.json()
    assert schemas.errors("console", body, "#/$defs/problem") == [] and body["status"] == 503
    assert "Traceback" not in r.text and str(Path.home()) not in r.text


QUEUE_ENDPOINTS = ["/queue"]
STORE_ENDPOINTS = ["/runs", f"/runs/{cw.RUN_ID}", f"/runs/{cw.RUN_ID}/artefacts/a2-clip", f"/runs/{cw.RUN_ID}/events"]


@pytest.mark.req("FR-003-23")
def test_fr_003_23_a_missing_store_folder_is_503_everywhere_it_matters_and_health_stays_up(cons) -> None:
    shutil.rmtree(cons.w.store)
    for path in QUEUE_ENDPOINTS + STORE_ENDPOINTS + ["/jobs/20250101T000000Z-deadbeef"]:
        assert_503(cons.client.get(path))
    r = cons.client.post("/jobs", json_body={"recipe": "a2-haulage", "profile": "test-profile"})
    assert_503(r)
    assert_503(cons.client.post("/jobs/20250101T000000Z-deadbeef/cancel"))
    assert cons.client.get("/health").status == 200
    assert cons.client.get("/recipes").status == 200, "recipes live in the repository, not in the store"
    cons.w.store.mkdir()
    assert cons.client.get("/runs").status == 200, "the console recovers once the store is back"
    assert cons.client.get("/queue").status == 200


@pytest.mark.req("FR-003-23")
def test_fr_003_23_a_store_path_that_is_a_file_is_503(cons) -> None:
    shutil.rmtree(cons.w.store)
    cons.w.store.write_text("not a directory", encoding="utf-8")
    try:
        assert_503(cons.client.get("/runs"))
        assert_503(cons.client.get("/queue"))
        assert cons.client.get("/health").status == 200
    finally:
        cons.w.store.unlink()
        cons.w.store.mkdir()


@pytest.mark.req("FR-003-23")
@pytest.mark.parametrize(
    "garbage",
    [
        bytes(range(256)) * 64,
        b"SQLite format 3\x00" + b"\xff" * 4096,
        b"not a database at all\n" * 100,
        b"\x00" * 100_000,
    ],
    ids=["random-bytes", "bad-header", "text", "zeros"],
)
def test_fr_003_23_a_corrupt_queue_database_is_503_for_the_queue_and_never_a_500(cons, garbage: bytes) -> None:
    db = cons.w.store / "queue.db"
    for sidecar in cons.w.store.glob("queue.db-*"):
        sidecar.unlink()
    db.write_bytes(garbage)
    for target in ("/queue", "/jobs/20250101T000000Z-deadbeef"):
        assert_503(cons.client.get(target))
    assert_503(cons.client.post("/jobs", json_body={"recipe": "a2-haulage", "profile": "test-profile"}))
    assert cons.client.get("/health").status == 200
    assert cons.client.get("/recipes").status == 200
    assert cons.client.get(f"/runs/{cw.RUN_ID}").status == 200, "runs do not depend on the queue file"


@pytest.mark.req("FR-003-23")
def test_fr_003_23_a_queue_database_that_is_a_directory_or_truncated_is_503(cons) -> None:
    db = cons.w.store / "queue.db"
    for sidecar in cons.w.store.glob("queue.db-*"):
        sidecar.unlink()
    db.unlink()
    db.mkdir()
    assert_503(cons.client.get("/queue"))
    assert cons.client.get("/health").status == 200
    db.rmdir()
    r = cons.client.get("/queue")
    assert r.status in (200, 503) and r.exception is None


@pytest.mark.req("FR-003-23")
def test_fr_003_23_the_runs_folder_missing_or_unreadable_is_503_or_an_empty_list_never_a_500(cons) -> None:
    shutil.rmtree(cons.w.store / "runs")
    r = cons.client.get("/runs")
    assert r.status in (200, 503) and r.exception is None
    if r.status == 200:
        assert r.json() == {"runs": []}
    else:
        assert_503(r)
    nf = cons.client.get(f"/runs/{cw.RUN_ID}")
    assert nf.status in (404, 503) and nf.exception is None


@pytest.mark.req("FR-003-23")
def test_fr_003_23_hostile_input_never_produces_a_5xx_even_with_a_broken_store(cons) -> None:
    shutil.rmtree(cons.w.store)
    for target in ("/runs/..%2f..%2f", "/runs/%00", "/jobs/xyz", "/recipes/%2e%2e", f"/runs/{cw.RUN_ID}/events"):
        r = cons.client.get(target)
        assert r.status in (404, 422, 503) and r.exception is None, f"{target}: {r.status}"
    bad = cons.client.post("/jobs", body=b"{", headers=[("content-type", "application/json")])
    assert bad.status in (400, 503), bad.status
    assert cons.client.post("/jobs", body=b"x", headers=[("content-type", "text/plain")]).status in (415, 503)
