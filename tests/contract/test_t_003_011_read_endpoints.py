# ruff: noqa: E501, PT018
"""T-003-011: the console's read endpoints (US-003-1).

Requirements: FR-003-06, FR-003-07, FR-003-08, FR-003-12.

Expected behaviour (plan.md D1-D3; stated for the implementer; the application is built as described in
tests/support/console_world.py):
  * `GET /health` 200 within 200 ms, body valid against contracts/console.schema.json#/$defs/health, no path, host or user;
  * `GET /recipes` lists every `.yaml` file under `studio/recipes/cases/` and `studio/recipes/_bench/` as a `recipe_summary`
    (repository-relative `path`, `sha256` of the file bytes, `stages`, `valid`, at most 20 `errors`; an invalid or unreadable
    file is listed invalid with `id`/`case` null when it yields none, never a 5xx); `GET /recipes/{recipe_id}` returns the
    validated recipe (404 unknown, a 4xx problem for an invalid one);
  * `GET /queue` (`job_list`) and `GET /jobs/{job_id}` (`job`) return the runner's job records (404 for an unknown
    well-formed id);
  * `GET /runs` lists run summaries (`run_list`; a run with an unreadable manifest is `valid: false` with null
    recipe/created/profile; `state` is the state of the job that produced it, or null); `GET /runs/{run_id}` returns the
    manifest after validating it against the manifest schema and answers 409 with a problem body when it is invalid.
Oracles: the contract schema (Python `jsonschema`), hashlib digests of the fixture files, the hand-built store of
tests/support/console_world.py (one valid run, one valid second run, one damaged manifest), the runner's own CLI to produce
a job and a run.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import console_world as cw
import runner_world as rw
import schemas


@pytest.fixture
def cons(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    c = cw.make_console_world(monkeypatch, tmp_path)
    yield c
    rw.cleanup_world(c.w)


def valid(body: Any, target: str) -> list[str]:
    return schemas.errors("console", body, target)


def is_problem(r: Any, status: int) -> None:
    assert r.status == status, r.text
    assert (r.header("content-type") or "").startswith("application/problem+json"), r.header("content-type")
    body = r.json()
    assert valid(body, "#/$defs/problem") == [] and body["status"] == status


# ---- /health ---------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-003-06")
def test_fr_003_06_health_is_200_within_200_ms_valid_and_free_of_machine_details(cons) -> None:
    cons.client.get("/health")  # warm-up
    slowest = 0.0
    for _ in range(20):
        t0 = time.perf_counter()
        r = cons.client.get("/health")
        slowest = max(slowest, time.perf_counter() - t0)
        assert r.status == 200
    assert slowest <= 0.2, f"/health took {slowest * 1000:.0f} ms"
    body = r.json()
    assert valid(body, "#/$defs/health") == []
    assert body["status"] == "ok" and set(body) == {"status", "console_version", "runner_version", "contracts"}
    text = r.text
    import getpass
    import socket

    for secret in (
        str(cons.w.repo),
        str(cons.w.store),
        str(Path.home()),
        socket.gethostname(),
        getpass.getuser(),
        "\\\\",
        "C:/",
        "/home/",
    ):
        assert len(secret) < 3 or secret.lower() not in text.lower(), f"/health leaks {secret!r}"
    assert (r.header("content-type") or "").startswith("application/json")


# ---- /recipes ---------------------------------------------------------------------------------------------------------------------------------------------
def by_path(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {x["path"]: x for x in body["recipes"]}


@pytest.mark.req("FR-003-07")
def test_fr_003_07_recipe_list_covers_cases_and_bench_with_digests_counts_and_validity(cons) -> None:
    r = cons.client.get("/recipes")
    assert r.status == 200, r.text
    body = r.json()
    assert valid(body, "#/$defs/recipe_list") == []
    rows = by_path(body)
    assert set(rows) == {
        "studio/recipes/cases/a2-haulage.yaml",
        "studio/recipes/cases/broken-one.yaml",
        "studio/recipes/cases/pub-case.yaml",
        "studio/recipes/_bench/bench-one.yaml",
        "studio/recipes/_bench/not-yaml.yaml",
    }
    good = rows["studio/recipes/cases/a2-haulage.yaml"]
    f = cons.w.repo / "studio" / "recipes" / "cases" / "a2-haulage.yaml"
    assert (good["id"], good["case"], good["stages"], good["valid"], good["errors"]) == (
        "a2-haulage",
        "A2",
        2,
        True,
        [],
    )
    assert good["sha256"] == hashlib.sha256(f.read_bytes()).hexdigest()
    bench = rows["studio/recipes/_bench/bench-one.yaml"]
    assert (bench["id"], bench["case"], bench["valid"]) == ("bench-one", "bench", True)
    bad = rows["studio/recipes/cases/broken-one.yaml"]
    assert bad["valid"] is False and 1 <= len(bad["errors"]) <= 20
    assert all(e["message"] and len(e["message"]) <= 300 for e in bad["errors"])
    unreadable = rows["studio/recipes/_bench/not-yaml.yaml"]
    assert (unreadable["valid"], unreadable["id"], unreadable["case"]) == (False, None, None) and unreadable["errors"]


@pytest.mark.req("FR-003-07")
def test_fr_003_07_hostile_recipe_files_are_listed_invalid_never_a_500(cons) -> None:
    folder = cons.w.repo / "studio" / "recipes" / "cases"
    (folder / "empty.yaml").write_bytes(b"")
    (folder / "binary.yaml").write_bytes(bytes(range(256)) * 8)
    (folder / "huge.yaml").write_bytes(
        b"id: huge\n" + b"# padding\n" * 40_000
    )  # larger than the 262,144-byte recipe cap
    (folder / "bom.yaml").write_bytes(
        b"\xef\xbb\xbf" + yaml.safe_dump(rw.recipe("bom-one", [rw.stage("s10_preprocess")])).encode()
    )
    (folder / "tags.yaml").write_text("id: !!python/object/apply:os.system ['echo x']\n", encoding="utf-8")
    many = rw.recipe("many-errors", [rw.stage("s10_preprocess") for _ in range(2)])
    many["stages"] = [{"id": "nope", "env": "none", "bad": i} for i in range(40)]
    (folder / "many-errors.yaml").write_text(yaml.safe_dump(many), encoding="utf-8")
    (folder / "README.md").write_text("not a recipe", encoding="utf-8")
    r = cons.client.get("/recipes")
    assert r.status == 200, r.text
    assert valid(r.json(), "#/$defs/recipe_list") == []
    rows = by_path(r.json())
    for name in ("empty", "binary", "huge", "bom", "tags", "many-errors"):
        row = rows[f"studio/recipes/cases/{name}.yaml"]
        assert row["valid"] is False, name
    assert len(rows["studio/recipes/cases/many-errors.yaml"]["errors"]) == 20, "at most 20 errors are listed"
    assert "studio/recipes/cases/README.md" not in rows
    assert all(not p.startswith("/") and ":" not in p and "\\" not in p for p in rows), "paths are repository-relative"


@pytest.mark.req("FR-003-07")
def test_fr_003_07_recipe_detail_returns_the_validated_recipe_or_a_4xx_problem(cons) -> None:
    r = cons.client.get("/recipes/a2-haulage")
    assert r.status == 200, r.text
    expect = yaml.safe_load(
        (cons.w.repo / "studio" / "recipes" / "cases" / "a2-haulage.yaml").read_text(encoding="utf-8")
    )
    assert r.json() == expect
    assert schemas.errors("recipe", r.json()) == []
    assert cons.client.get("/recipes/bench-one").json()["id"] == "bench-one"
    is_problem(cons.client.get("/recipes/no-such-recipe"), 404)
    bad = cons.client.get("/recipes/broken-one")
    assert 400 <= bad.status < 500 and bad.status != 405, bad.text
    assert (bad.header("content-type") or "").startswith("application/problem+json")


@pytest.mark.req("FR-003-07")
def test_fr_003_07_an_empty_or_missing_recipe_folder_lists_nothing_and_does_not_fail(cons) -> None:
    import shutil

    shutil.rmtree(cons.w.repo / "studio" / "recipes" / "_bench")
    r = cons.client.get("/recipes")
    assert r.status == 200 and all(x["path"].startswith("studio/recipes/cases/") for x in r.json()["recipes"])


# ---- /queue and /jobs/{id} -----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-003-08")
def test_fr_003_08_queue_and_job_return_the_runners_records(cons) -> None:
    from pitstudio.runner import queue

    r = cons.client.get("/queue")
    assert r.status == 200 and r.json() == {"jobs": []}
    j1 = queue.enqueue({"recipe": "a2-haulage", "profile": "test-profile"})
    j2 = queue.enqueue({"recipe": "bench-one", "profile": "test-profile", "force": True})
    body = cons.client.get("/queue").json()
    assert valid(body, "#/$defs/job_list") == []
    assert {j["job_id"] for j in body["jobs"]} == {j1, j2}
    one = cons.client.get(f"/jobs/{j1}")
    assert one.status == 200 and valid(one.json(), "#/$defs/job") == []
    assert one.json() == queue.job(j1)
    assert (one.json()["state"], one.json()["recipe"], one.json()["exit_code"]) == ("queued", "a2-haulage", None)
    is_problem(cons.client.get("/jobs/20250101T000000Z-deadbeef"), 404)


@pytest.mark.req("FR-003-08")
def test_fr_003_08_a_finished_job_shows_its_run_state_and_exit_code(cons) -> None:
    assert cons.w.run("a2-haulage").code == 0
    body = cons.client.get("/queue").json()
    assert valid(body, "#/$defs/job_list") == []
    (job,) = body["jobs"]
    assert (job["state"], job["exit_code"], job["run_id"]) == ("succeeded", 0, cons.w.last_run().name)
    runs = {x["run_id"]: x for x in cons.client.get("/runs").json()["runs"]}
    assert runs[job["run_id"]]["state"] == "succeeded"


# ---- /runs ---------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-003-12")
def test_fr_003_12_run_list_has_summaries_for_valid_and_damaged_runs(cons) -> None:
    r = cons.client.get("/runs")
    assert r.status == 200, r.text
    body = r.json()
    assert valid(body, "#/$defs/run_list") == []
    rows = {x["run_id"]: x for x in body["runs"]}
    assert set(rows) == {cw.RUN_ID, cw.OTHER_RUN_ID, cw.BROKEN_RUN_ID}
    good = rows[cw.RUN_ID]
    assert (good["recipe"], good["profile"], good["stages"], good["published"], good["valid"], good["state"]) == (
        "pub-case",
        "test-profile",
        3,
        False,
        True,
        None,
    )
    assert good["created"] == "2026-10-07T12:00:00Z"
    bad = rows[cw.BROKEN_RUN_ID]
    assert (bad["valid"], bad["recipe"], bad["created"], bad["profile"]) == (False, None, None, None)


@pytest.mark.req("FR-003-12")
def test_fr_003_12_run_detail_returns_the_validated_manifest(cons) -> None:
    r = cons.client.get(f"/runs/{cw.RUN_ID}")
    assert r.status == 200, r.text
    body = r.json()
    on_disk = json.loads((cons.w.store / "runs" / cw.RUN_ID / "manifest.json").read_text(encoding="utf-8"))
    assert body == on_disk
    assert schemas.errors("manifest", body, "#/$defs/run") == []
    assert [a["id"] for a in body["artefacts"]] == ["a2-clip", "a2-notes"]


@pytest.mark.req("FR-003-12")
@pytest.mark.parametrize(
    "damage",
    [
        b"{this is not json",
        b"",
        b"\xef\xbb\xbf{}",
        b"[1, 2, 3]",
        b'{"kind": "run"}',
        json.dumps({"kind": "run", "unexpected": True}).encode(),
        b'{"a": NaN}',
    ],
    ids=["not-json", "empty", "bom", "array", "missing-fields", "unknown-field", "nan"],
)
def test_fr_003_12_an_invalid_manifest_is_a_409_problem_not_a_500(cons, damage: bytes) -> None:
    (cons.w.store / "runs" / cw.OTHER_RUN_ID / "manifest.json").write_bytes(damage)
    is_problem(cons.client.get(f"/runs/{cw.OTHER_RUN_ID}"), 409)
    listed = {x["run_id"]: x for x in cons.client.get("/runs").json()["runs"]}
    assert listed[cw.OTHER_RUN_ID]["valid"] is False


@pytest.mark.req("FR-003-12")
def test_fr_003_12_the_damaged_run_of_the_fixture_is_a_409_and_an_unknown_run_a_404(cons) -> None:
    is_problem(cons.client.get(f"/runs/{cw.BROKEN_RUN_ID}"), 409)
    is_problem(cons.client.get("/runs/20250101T000000Z-nothing"), 404)
