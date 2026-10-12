# ruff: noqa: E501, PT018
"""T-003-012: `POST /jobs` and `POST /jobs/{job_id}/cancel` (US-003-1).

Requirements: FR-003-09, FR-003-11.

Expected behaviour (plan.md D1/D2; stated for the implementer):
  * `POST /jobs` with a valid job request naming a committed recipe, existing stage keys and an existing profile calls
    `pitstudio.runner.queue.enqueue` exactly once (looked up as a module attribute), answers 202 with `Location: /jobs/<job_id>` and a
    `job_created` body whose `location` equals that header, and the job appears in `GET /queue` within 1 s; the console
    process itself launches nothing (no process is started, no stage ledger line);
  * `POST /jobs/{job_id}/cancel` calls `queue.cancel(job_id)` and answers 202 (body: the `job` record) for a queued or running
    job, 404 for an unknown well-formed id, 409 for a job in a terminal state.
Oracles: the contract schema (`job_created`, `job`), a spy around the runner's queue API, the runner's own state for the job,
a real foreground worker killed through the console (the job ends cancelled, exit 6).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import contextlib

import console_world as cw
import runner_world as rw
import schemas


@pytest.fixture
def cons(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    c = cw.make_console_world(monkeypatch, tmp_path)
    c.w.write_recipe(
        rw.recipe("variants", [rw.stage("st10_terrain", variant="north"), rw.stage("st10_terrain", variant="south")])
    )
    yield c
    rw.cleanup_world(c.w)


class QueueSpy:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pitstudio.runner import queue

        self.enqueued: list[dict[str, Any]] = []
        self.cancelled: list[str] = []
        real_enqueue, real_cancel = queue.enqueue, queue.cancel

        def enqueue(req: dict[str, Any], *a: Any, **k: Any) -> Any:
            self.enqueued.append(dict(req))
            return real_enqueue(req, *a, **k)

        def cancel(job_id: str, *a: Any, **k: Any) -> Any:
            self.cancelled.append(job_id)
            return real_cancel(job_id, *a, **k)

        monkeypatch.setattr(queue, "enqueue", enqueue)
        monkeypatch.setattr(queue, "cancel", cancel)


@pytest.mark.req("FR-003-09")
@pytest.mark.parametrize(
    "body",
    [
        {"recipe": "a2-haulage", "profile": "test-profile"},
        {"recipe": "a2-haulage", "profile": "test-profile", "force": True, "rerun_check": True},
        {"recipe": "a2-haulage", "profile": "test-profile", "stages": [{"id": "s10_preprocess"}]},
        {
            "recipe": "a2-haulage",
            "profile": "test-profile",
            "stages": [{"id": "s10_preprocess"}, {"id": "st10_terrain"}],
            "force": False,
        },
        {"recipe": "bench-one", "profile": "test-profile"},
        {"recipe": "variants", "profile": "test-profile", "stages": [{"id": "st10_terrain", "variant": "north"}]},
    ],
    ids=["minimal", "flags", "one-stage", "two-stages", "bench-recipe", "variant-stage"],
)
def test_fr_003_09_a_valid_job_request_is_accepted_enqueued_once_and_visible_within_1_s(
    cons, monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]
) -> None:
    spy = QueueSpy(monkeypatch)
    calls = rw.forbid_popen(monkeypatch)
    r = cons.post_job(body)
    assert r.status == 202, r.text
    created = r.json()
    assert schemas.errors("console", created, "#/$defs/job_created") == []
    assert r.header("location") == created["location"] == f"/jobs/{created['job_id']}"
    assert len(spy.enqueued) == 1
    for k, v in body.items():
        assert spy.enqueued[0][k] == v, f"the request must reach the runner unchanged ({k})"
    t0 = time.monotonic()
    while time.monotonic() - t0 < 1.0:
        jobs = cons.client.get("/queue").json()["jobs"]
        if any(j["job_id"] == created["job_id"] for j in jobs):
            break
        time.sleep(0.05)
    assert any(j["job_id"] == created["job_id"] and j["state"] == "queued" for j in jobs), (
        "the job must be in the queue within 1 s"
    )
    assert calls == [] and cons.w.ledger_rows() == [], "the console launches nothing itself"
    one = cons.client.get(created["location"])
    assert one.status == 200 and one.json()["recipe"] == body["recipe"]


@pytest.mark.req("FR-003-09")
def test_fr_003_09_two_requests_make_two_jobs(cons) -> None:
    a = cons.post_job().json()["job_id"]
    b = cons.post_job().json()["job_id"]
    assert a != b
    assert {j["job_id"] for j in cons.client.get("/queue").json()["jobs"]} == {a, b}


@pytest.mark.req("FR-003-09")
def test_fr_003_09_a_queued_job_is_run_by_the_runners_worker_not_by_the_console(cons) -> None:
    job_id = cons.post_job({"recipe": "a2-haulage", "profile": "test-profile"}).json()["job_id"]
    assert cons.w.ledger_rows() == []
    assert cons.w.cli("worker").code == 0
    j = cons.client.get(f"/jobs/{job_id}").json()
    assert (j["state"], j["exit_code"]) == ("succeeded", 0)
    assert schemas.errors("console", j, "#/$defs/job") == []


# ---- FR-003-11: cancel ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-003-11")
def test_fr_003_11_cancelling_a_queued_job_is_202_and_calls_the_runner(cons, monkeypatch: pytest.MonkeyPatch) -> None:
    job_id = cons.post_job().json()["job_id"]
    spy = QueueSpy(monkeypatch)
    r = cons.client.post(f"/jobs/{job_id}/cancel")
    assert r.status == 202, r.text
    assert spy.cancelled == [job_id]
    body = r.json()
    assert schemas.errors("console", body, "#/$defs/job") == [] and body["job_id"] == job_id
    assert cons.client.get(f"/jobs/{job_id}").json()["state"] == "cancelled"


@pytest.mark.req("FR-003-11")
def test_fr_003_11_unknown_well_formed_ids_are_404_and_terminal_jobs_are_409(
    cons, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = QueueSpy(monkeypatch)
    r = cons.client.post("/jobs/20250101T000000Z-deadbeef/cancel")
    assert r.status == 404 and (r.header("content-type") or "").startswith("application/problem+json")
    job_id = cons.post_job().json()["job_id"]
    assert cons.client.post(f"/jobs/{job_id}/cancel").status == 202
    again = cons.client.post(f"/jobs/{job_id}/cancel")
    assert again.status == 409, again.text
    assert (again.header("content-type") or "").startswith("application/problem+json")
    # a job that finished by itself is terminal too
    done = cons.post_job().json()["job_id"]
    assert cons.w.cli("worker").code == 0
    assert cons.client.post(f"/jobs/{done}/cancel").status == 409
    assert spy.cancelled and spy.cancelled[0] == job_id, "the first (successful) cancel went through the runner's API"


@pytest.mark.req("FR-003-11")
def test_fr_003_11_cancelling_a_running_job_through_the_console_ends_the_worker_with_exit_6(cons) -> None:
    from pitstudio.runner import queue

    cons.w.write_recipe(
        rw.recipe("long", [rw.stage("s10_preprocess", timeout_s=120, params={"mode": "sleep", "sleep_s": 60})])
    )
    p = subprocess.Popen(
        [sys.executable, "-m", "pitstudio.runner", "run", str(cons.w.recipes["long"]), "--profile", "test-profile"],
        env=cons.w.env(),
        cwd=str(cons.w.base),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert rw.wait_until(
            lambda: any(j["state"] == "running" for j in queue.jobs()) and bool(cons.w.ledger_rows()), 90, proc=p
        ), "the job never started running"
        (job,) = [j for j in queue.jobs() if j["recipe"] == "long"]
        r = cons.client.post(f"/jobs/{job['job_id']}/cancel")
        assert r.status == 202, r.text
        assert p.wait(timeout=40) == 6
        assert cons.client.get(f"/jobs/{job['job_id']}").json()["state"] == "cancelled"
    finally:
        if p.poll() is None:
            p.kill()
        import psutil

        for row in cons.w.ledger_rows():
            with contextlib.suppress(psutil.Error):
                psutil.Process(row["pid"]).kill()
