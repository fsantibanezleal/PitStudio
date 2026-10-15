# ruff: noqa: E501
"""T-003-015: latency of the non-streaming endpoints and idempotence of reads (US-003-1).

Requirements: NFR-003-01, P-003-03.

Fixture: a store with 100 runs and 1,000 jobs (tests/support/console_world.py plus copies of its manifest and
`queue.enqueue` calls). Expected behaviour: the 95th-percentile latency of each non-streaming endpoint over 200 requests is at most
200 ms (in-process ASGI client, warm); repeating any non-streaming GET on an unchanged store returns the same status and a
byte-identical body (same order of list members).
Oracles: `time.perf_counter` percentiles (nearest-rank), byte equality of two responses.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import console_world as cw
import runner_world as rw


@pytest.fixture(scope="module")
def heavy(tmp_path_factory: pytest.TempPathFactory):
    mp = pytest.MonkeyPatch()
    cons = cw.make_console_world(mp, tmp_path_factory.mktemp("heavy"))
    base = json.loads((cons.w.store / "runs" / cw.RUN_ID / "manifest.json").read_text(encoding="utf-8"))
    for i in range(100):
        run_id = f"20261012T{i // 60:02d}{i % 60:02d}00Z-load{i}"
        d = cons.w.store / "runs" / run_id
        d.mkdir(parents=True)
        m = {**base, "run_id": run_id, "artefacts": []}
        (d / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        (d / "events.jsonl").write_text(
            json.dumps({"seq": 1, "t": "2026-10-12T00:00:00Z", "run_id": run_id, "type": "run-started"}) + "\n",
            encoding="utf-8",
        )
    from pitstudio.runner import queue

    ids = [
        queue.enqueue({"recipe": "a2-haulage" if i % 2 else "bench-one", "profile": "test-profile"})
        for i in range(1000)
    ]
    cons.job_ids = ids  # type: ignore[attr-defined]
    yield cons
    mp.undo()
    rw.cleanup_world(cons.w)


def p95(samples: list[float]) -> float:
    s = sorted(samples)
    return s[max(0, int(0.95 * len(s) + 0.9999) - 1)]  # nearest rank


def endpoints(cons: Any) -> list[str]:
    return [
        "/health",
        "/recipes",
        "/recipes/a2-haulage",
        "/queue",
        f"/jobs/{cons.job_ids[500]}",
        "/runs",
        f"/runs/{cw.RUN_ID}",
        f"/runs/{cw.RUN_ID}/artefacts/a2-notes",
        "/openapi.json",
    ]


@pytest.mark.req("NFR-003-01")
@pytest.mark.parametrize("index", range(9))
def test_nfr_003_01_p95_latency_of_every_non_streaming_endpoint_is_at_most_200_ms(heavy, index: int) -> None:
    target = endpoints(heavy)[index]
    heavy.client.get(target)  # warm-up
    times = []
    for _ in range(200):
        t0 = time.perf_counter()
        r = heavy.client.get(target)
        times.append(time.perf_counter() - t0)
        assert r.status == 200, f"{target}: {r.status}"
    assert p95(times) <= 0.2, f"{target}: p95 {p95(times) * 1000:.0f} ms (> 200 ms)"


@pytest.mark.req("NFR-003-01")
def test_nfr_003_01_the_fixture_really_holds_100_runs_and_1000_jobs(heavy) -> None:
    assert len(heavy.client.get("/runs").json()["runs"]) >= 100
    assert len(heavy.client.get("/queue").json()["jobs"]) == 1000


@pytest.mark.req("P-003-03")
def test_p_003_03_every_read_endpoint_is_idempotent_on_an_unchanged_store(heavy) -> None:
    for target in [
        *endpoints(heavy),
        f"/jobs/{heavy.job_ids[0]}",
        "/recipes/bench-one",
        f"/runs/{cw.OTHER_RUN_ID}",
        f"/runs/{cw.BROKEN_RUN_ID}",
        "/recipes/no-such",
        "/jobs/20250101T000000Z-deadbeef",
        f"/runs/{cw.RUN_ID}/artefacts/nope",
    ]:
        a, b = heavy.client.get(target), heavy.client.get(target)
        assert (a.status, a.body) == (b.status, b.body), f"{target} is not idempotent"
        assert a.header("content-type") == b.header("content-type")


@pytest.mark.req("P-003-03")
@settings(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))
@given(i=st.integers(0, 999), j=st.integers(0, 99), repeat=st.integers(2, 4))
def test_p_003_03_reads_of_random_ids_repeat_byte_for_byte(heavy, i: int, j: int, repeat: int) -> None:
    targets = [f"/jobs/{heavy.job_ids[i]}", f"/runs/20261012T{j // 60:02d}{j % 60:02d}00Z-load{j}", "/queue"]
    for t in targets:
        first = heavy.client.get(t)
        assert first.status == 200
        for _ in range(repeat - 1):
            again = heavy.client.get(t)
            assert (again.status, again.body) == (first.status, first.body)
