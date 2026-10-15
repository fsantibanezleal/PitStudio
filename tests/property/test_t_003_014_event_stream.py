# ruff: noqa: E501, PT018
"""T-003-014: the server-sent event stream of a run (US-003-1).

Requirements: FR-003-15, FR-003-16, P-003-04.

Expected behaviour (plan.md D4; stated for the implementer):
  * `GET /runs/{run_id}/events` answers `200 text/event-stream` with `Cache-Control: no-cache`; it replays the run's `events.jsonl`
    as frames `id: <seq>` / `event: event` / `data: <the event JSON>`, then follows the file (each appended line is delivered
    within 2 s); telemetry samples from `telemetry.jsonl` are frames of `event: telemetry` at most once per wall-clock second;
    a keep-alive (SSE comment line) is sent at least every 15 s; `Last-Event-ID: k` replays only events with `seq` > k;
  * `Last-Event-ID` that is not a decimal integer in 0..2**63-1 is a 422; with 8 streams already open the next is a 429 with
    `Retry-After`; an invalid line of `events.jsonl` produces ONE `error` frame (`data`: {"line": n, "message": "..."}, valid
    against events.schema.json#/$defs/stream_error) and the stream continues; when the client disconnects the stream's task
    ends within 2 s.
Oracles: hand-written event files, arrival times measured with a monotonic clock, the stream_error schema, Hypothesis over
(N events, resume point k) with the exact expected id sequence k+1..N.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import console_world as cw
import runner_world as rw
import schemas

COUNTER = {"n": 0}


@pytest.fixture
def cons(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    c = cw.make_console_world(monkeypatch, tmp_path)
    yield c
    rw.cleanup_world(c.w)


def event(run_id: str, seq: int) -> dict[str, Any]:
    return {"seq": seq, "t": "2026-10-11T10:00:00Z", "run_id": run_id, "type": "lock-acquired"}


def make_run(cons: cw.ConsoleWorld, n_events: int, *, lines: list[str] | None = None) -> tuple[str, Path]:
    COUNTER["n"] += 1
    run_id = f"20261011T1000{COUNTER['n'] % 60:02d}Z-s{COUNTER['n']}"
    d = cons.w.store / "runs" / run_id
    d.mkdir(parents=True)
    base = json.loads((cons.w.store / "runs" / cw.RUN_ID / "manifest.json").read_text(encoding="utf-8"))
    base["run_id"], base["artefacts"] = run_id, []
    (d / "manifest.json").write_text(json.dumps(base), encoding="utf-8")
    body = lines if lines is not None else [json.dumps(event(run_id, i)) for i in range(1, n_events + 1)]
    (d / "events.jsonl").write_text("".join(ln + "\n" for ln in body), encoding="utf-8")
    return run_id, d


def append(d: Path, text: str) -> None:
    with open(d / "events.jsonl", "a", encoding="utf-8") as fh:
        fh.write(text + "\n")
        fh.flush()


def frames(s, count: int, timeout: float = 10.0) -> list[Any]:
    return [e for e in s.events(count, timeout) if e.event == "event"]


# ---- FR-003-15 ------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-003-15")
def test_fr_003_15_headers_and_replay_of_the_existing_events(cons) -> None:
    run_id, _ = make_run(cons, 5)
    s = cons.client.stream(f"/runs/{run_id}/events")
    try:
        s.wait_headers(5)
        assert s.status == 200
        assert (s.header("content-type") or "").startswith("text/event-stream")
        assert "no-cache" in (s.header("cache-control") or "")
        got = s.events(5, 10)
        assert [e.id for e in got] == ["1", "2", "3", "4", "5"] and {e.event for e in got} == {"event"}
        for e, seq in zip(got, range(1, 6), strict=True):
            doc = json.loads(e.data)
            assert doc == event(run_id, seq) and schemas.errors("events", doc, "#/$defs/event") == []
    finally:
        assert s.close(3.0), "the stream task must end after the client disconnects"


@pytest.mark.req("FR-003-15")
def test_fr_003_15_an_appended_event_is_delivered_within_2_seconds(cons) -> None:
    run_id, d = make_run(cons, 3)
    s = cons.client.stream(f"/runs/{run_id}/events")
    try:
        assert [e.id for e in frames(s, 3)] == ["1", "2", "3"]
        for seq in (4, 5, 6):
            t0 = time.monotonic()
            append(d, json.dumps(event(run_id, seq)))
            got = frames(s, 1, 2.5)
            assert [e.id for e in got] == [str(seq)], f"event {seq} not delivered"
            assert got[0].t - t0 <= 2.0, f"event {seq} took {got[0].t - t0:.2f}s"
            time.sleep(0.3)
    finally:
        s.close(3.0)


@pytest.mark.req("FR-003-15")
def test_fr_003_15_a_partially_written_line_is_not_delivered_until_complete(cons) -> None:
    run_id, d = make_run(cons, 1)
    s = cons.client.stream(f"/runs/{run_id}/events")
    try:
        assert [e.id for e in frames(s, 1)] == ["1"]
        full = json.dumps(event(run_id, 2))
        with open(d / "events.jsonl", "a", encoding="utf-8") as fh:
            fh.write(full[:20])
            fh.flush()
            time.sleep(1.5)
            assert frames(s, 1, 0.3) == [], "half a line must wait for its newline"
            fh.write(full[20:] + "\n")
            fh.flush()
        assert [e.id for e in frames(s, 1, 3)] == ["2"]
    finally:
        s.close(3.0)


@pytest.mark.req("FR-003-15")
def test_fr_003_15_telemetry_is_sent_as_telemetry_events_at_most_once_per_second(cons) -> None:
    s = cons.client.stream(f"/runs/{cw.RUN_ID}/events")
    try:
        s.wait_headers(5)
        t0 = time.monotonic()
        got = s.events(1000, 4.0)
        elapsed = time.monotonic() - t0
        tele = [e for e in got if e.event == "telemetry"]
        assert tele, "the run's telemetry.jsonl must be delivered as telemetry events"
        assert len(tele) <= int(elapsed) + 2, (
            f"{len(tele)} telemetry events in {elapsed:.1f}s: not reduced to one per second"
        )
        for e in tele:
            sample = json.loads(e.data)
            assert schemas.errors("events", sample, "#/$defs/telemetry_sample") == [] and sample["run_id"] == cw.RUN_ID
        ev = [e for e in got if e.event == "event"]
        assert [e.id for e in ev] == ["1", "2"]
    finally:
        s.close(3.0)


@pytest.mark.req("FR-003-15")
def test_fr_003_15_a_keep_alive_arrives_at_least_every_15_seconds(cons) -> None:
    run_id, _ = make_run(cons, 1)
    s = cons.client.stream(f"/runs/{run_id}/events")
    try:
        assert [e.id for e in frames(s, 1)] == ["1"]
        t0 = time.monotonic()
        deadline = t0 + 17.5
        while not s.comments and time.monotonic() < deadline:
            assert s.events(1, 0.25) == [], "an idle stream sends no event frames"
        assert s.comments, "no keep-alive within 17.5 s of an idle stream"
        assert s.comments[0] - t0 <= 15.5
    finally:
        s.close(3.0)


@pytest.mark.req("FR-003-15")
@pytest.mark.parametrize(
    ("k", "expected"),
    [(0, [1, 2, 3, 4, 5]), (1, [2, 3, 4, 5]), (3, [4, 5]), (4, [5]), (5, []), (50, []), (2**63 - 1, [])],
)
def test_fr_003_15_last_event_id_replays_only_later_events(cons, k: int, expected: list[int]) -> None:
    run_id, d = make_run(cons, 5)
    s = cons.client.stream(f"/runs/{run_id}/events", headers={"Last-Event-ID": str(k)})
    try:
        s.wait_headers(5)
        assert s.status == 200
        got = frames(s, len(expected), 5 if expected else 1.0)
        assert [int(e.id) for e in got] == expected
        append(d, json.dumps(event(run_id, 6)))
        assert [e.id for e in frames(s, 1, 3)] == ["6"], "following continues after the resume point"
    finally:
        s.close(3.0)


# ---- FR-003-16 ---------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-003-16")
@pytest.mark.parametrize(
    "value",
    [
        "abc",
        "-1",
        "1.5",
        "",
        " 3",
        "3 ",
        "9223372036854775808",
        "0x10",
        "1e3",
        "+3",
        "٣",
        "99999999999999999999999",
        "NaN",
        "3,4",
    ],
    ids=repr,
)
def test_fr_003_16_a_malformed_last_event_id_is_a_422_problem(cons, value: str) -> None:
    run_id, _ = make_run(cons, 2)
    r = cons.client.get(f"/runs/{run_id}/events", headers={"Last-Event-ID": value}, timeout=10)
    assert r.status == 422, f"{value!r}: {r.status}"
    assert (r.header("content-type") or "").startswith("application/problem+json")


@pytest.mark.req("FR-003-16")
def test_fr_003_16_the_ninth_concurrent_stream_is_429_with_retry_after_and_a_slot_frees_up(cons) -> None:
    run_id, _ = make_run(cons, 1)
    open_streams = []
    try:
        for i in range(8):
            s = cons.client.stream(f"/runs/{run_id}/events")
            s.wait_headers(5)
            assert s.status == 200, f"stream {i + 1}"
            open_streams.append(s)
        ninth = cons.client.get(f"/runs/{run_id}/events", timeout=10)
        assert ninth.status == 429, ninth.status
        assert ninth.header("retry-after") and ninth.header("retry-after").isdigit()
        assert (ninth.header("content-type") or "").startswith("application/problem+json")
        assert open_streams.pop().close(3.0)
        time.sleep(0.5)
        again = cons.client.stream(f"/runs/{run_id}/events")
        again.wait_headers(5)
        assert again.status == 200, "a closed stream frees its slot"
        open_streams.append(again)
    finally:
        for s in open_streams:
            s.close(2.0)


@pytest.mark.req("FR-003-16")
@pytest.mark.parametrize(
    "bad",
    [
        "{not json",
        '{"seq": 2}',
        '{"seq": "two", "t": "2026-10-11T10:00:00Z", "run_id": "RUN", "type": "lock-acquired"}',
        '{"seq": 2, "t": "2026-10-11T10:00:00Z", "run_id": "RUN", "type": "teleport"}',
        '{"seq": NaN, "t": "2026-10-11T10:00:00Z", "run_id": "RUN", "type": "lock-acquired"}',
        "[1, 2, 3]",
        "null",
        '{"seq": 2, "extra": true}',
        "x" * 200_000,
    ],
    ids=[
        "syntax",
        "missing-fields",
        "wrong-type",
        "unknown-type",
        "nan",
        "array",
        "null",
        "unknown-field",
        "huge-line",
    ],
)
def test_fr_003_16_an_invalid_line_gives_one_error_frame_naming_the_line_and_the_stream_continues(
    cons, bad: str
) -> None:
    COUNTER["n"] += 1
    run_id = "20261011T100000Z-bad" + str(COUNTER["n"])
    lines = [json.dumps(event(run_id, 1)), bad.replace("RUN", run_id), json.dumps(event(run_id, 3))]
    d = cons.w.store / "runs" / run_id
    d.mkdir(parents=True)
    base = json.loads((cons.w.store / "runs" / cw.RUN_ID / "manifest.json").read_text(encoding="utf-8"))
    base["run_id"], base["artefacts"] = run_id, []
    (d / "manifest.json").write_text(json.dumps(base), encoding="utf-8")
    (d / "events.jsonl").write_text("".join(ln + "\n" for ln in lines), encoding="utf-8")
    s = cons.client.stream(f"/runs/{run_id}/events")
    try:
        got = s.events(3, 10)
        kinds = [(e.event, e.id) for e in got]
        assert kinds == [("event", "1"), ("error", None), ("event", "3")] or kinds == [
            ("event", "1"),
            ("error", "2"),
            ("event", "3"),
        ], kinds
        err = json.loads(got[1].data)
        assert schemas.errors("events", err, "#/$defs/stream_error") == [] and err["line"] == 2
        assert "\n" not in err["message"] and 0 < len(err["message"]) <= 300
        assert "Traceback" not in got[1].data
    finally:
        s.close(3.0)


@pytest.mark.req("FR-003-16")
def test_fr_003_16_non_utf8_bytes_in_the_log_are_an_error_frame_not_a_crash(cons) -> None:
    run_id, d = make_run(cons, 1)
    with open(d / "events.jsonl", "ab") as fh:
        fh.write(b"\xff\xfe\x00 not utf8\n")
        fh.write((json.dumps(event(run_id, 3)) + "\n").encode())
    s = cons.client.stream(f"/runs/{run_id}/events")
    try:
        got = s.events(3, 10)
        assert [e.event for e in got] == ["event", "error", "event"] and json.loads(got[1].data)["line"] == 2
    finally:
        s.close(3.0)


@pytest.mark.req("FR-003-16")
def test_fr_003_16_disconnect_ends_the_stream_task_within_2_seconds_even_while_idle(cons) -> None:
    run_id, _ = make_run(cons, 2)
    s = cons.client.stream(f"/runs/{run_id}/events")
    s.events(2, 5)
    t0 = time.monotonic()
    assert s.close(2.0), "the stream task did not end"
    assert time.monotonic() - t0 <= 2.0
    assert s.exception is None


@pytest.mark.req("FR-003-16")
def test_fr_003_16_unknown_and_malformed_runs_are_404_and_422(cons) -> None:
    assert cons.client.get("/runs/20250101T000000Z-nothing/events").status == 404
    assert cons.client.get("/runs/not-a-run/events").status == 422


# ---- P-003-04 ------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("P-003-04")
@settings(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
@given(n=st.integers(0, 500), frac=st.floats(0, 1))
def test_p_003_04_a_client_receives_exactly_events_k_plus_1_to_n_in_order_without_duplicates(
    cons, n: int, frac: float
) -> None:
    k = int(frac * n)
    run_id, d = make_run(cons, n)
    s = cons.client.stream(f"/runs/{run_id}/events", headers={"Last-Event-ID": str(k)})
    try:
        want = list(range(k + 1, n + 1))
        got = frames(s, len(want), 20 if want else 0.4)
        assert [int(e.id) for e in got] == want
        extra = frames(s, 1, 0.3)
        assert extra == [], "nothing beyond N is delivered"
        # events appended while connected continue the sequence exactly once
        append(d, json.dumps(event(run_id, n + 1)))
        assert [int(e.id) for e in frames(s, 1, 3)] == [n + 1]
    finally:
        assert s.close(3.0)


@pytest.mark.req("P-003-04")
def test_p_003_04_events_appended_concurrently_arrive_in_order_exactly_once(cons) -> None:
    run_id, d = make_run(cons, 0)
    s = cons.client.stream(f"/runs/{run_id}/events")
    stop = threading.Event()

    def writer() -> None:
        for seq in range(1, 61):
            append(d, json.dumps(event(run_id, seq)))
            time.sleep(0.01 if seq % 7 else 0.15)
        stop.set()

    t = threading.Thread(target=writer, daemon=True)
    t.start()
    try:
        got = frames(s, 60, 30)
        assert [int(e.id) for e in got] == list(range(1, 61))
    finally:
        stop.wait(10)
        s.close(3.0)
