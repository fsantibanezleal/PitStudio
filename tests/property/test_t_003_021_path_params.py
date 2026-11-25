# ruff: noqa: E501, PT018, RUF001
"""T-003-021: path parameters: patterns, encodings, traversal, NUL, overlong, unknown ids, links outside the store (US-003-2).

Requirements: FR-003-14, P-003-02.

Expected behaviour (stated for the implementer): a path parameter that does not match its pattern (spec 001 data-model 1.3: `slug`,
`run_id`, `artefact_id`, job id), contains an ENCODED `/` (%2F), `\\` (%5C), `..`, NUL (%00), or exceeds its length answers 422;
well-formed but unknown answers 404; an object that resolves outside `$PITSTUDIO_STORE/cas/` (for example through a link) answers 404
and is never served; never a 5xx. The check works on the raw request path (`scope["raw_path"]`), since a server decodes `%2F` before routing.
Oracles: hand-written hostile targets with the status the requirement dictates, a canary file outside the store whose content must
never appear in any response, Hypothesis over traversal/encoding fragments (P-003-02: 200/206 only for ids of the fixture store).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import console_world as cw
import publish_world as pw
import runner_world as rw

RUN = cw.RUN_ID
GOOD_JOB = "20250101T000000Z-deadbeef"
LISTED = {"a2-clip", "a2-notes"}


@pytest.fixture
def cons(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    c = cw.make_console_world(monkeypatch, tmp_path)
    yield c
    rw.cleanup_world(c.w)


def problem(r) -> None:
    assert (r.header("content-type") or "").startswith("application/problem+json"), (r.status, r.header("content-type"))
    assert r.json()["status"] == r.status


HOSTILE_422 = [
    # run ids
    f"/runs/{RUN}%2F..%2F..%2Fetc",
    "/runs/..%2f..%2fsecret",
    "/runs/%2e%2e",
    "/runs/%2E%2E%2F",
    "/runs/%2e",
    "/runs/.",
    f"/runs/{RUN}%5Cx",
    f"/runs/{RUN}%5c..%5c",
    f"/runs/{RUN}%00",
    f"/runs/%00{RUN}",
    "/runs/" + "a" * 200,
    "/runs/" + "9" * 65,
    "/runs/20261007T120000Z-PUB-CASE",
    "/runs/20261007t120000z-pub-case",
    "/runs/%E2%80%AEevil",
    "/runs/%252e%252e",
    "/runs/%252fetc",
    f"/runs/{RUN}%20",
    f"/runs/{RUN}%0a",
    f"/runs/{RUN}%09",
    f"/runs/{RUN}.",
    f"/runs/{RUN}%2e",
    "/runs/%EF%BC%92%EF%BC%90",
    "/runs/pub-case",
    "/runs/20261007T120000Z-",
    "/runs/20261007T120000Z-%2e%2e",
    "/runs/20261007T1200Z-pub",
    # recipes
    "/recipes/%2e%2e%2fa2-haulage",
    "/recipes/A2",
    "/recipes/a2-haulage.yaml",
    "/recipes/a2-haulage%2F",
    "/recipes/cases%2Fa2-haulage",
    "/recipes/a2-haulage%00",
    "/recipes/" + "a" * 65,
    "/recipes/%5c..%5c..%5cwindows",
    # jobs
    "/jobs/xyz",
    "/jobs/20250101T000000Z-DEADBEEF",
    "/jobs/20250101T000000Z-deadbee",
    "/jobs/20250101T000000Z-deadbeef0",
    "/jobs/20250101T000000Z-deadbeeg",
    "/jobs/..%2f..%2fx",
    "/jobs/%2e%2e",
    "/jobs/20250101T000000Z-deadbeef%00",
    "/jobs/20250101T000000Z-deadbeef%5c",
    # artefacts
    f"/runs/{RUN}/artefacts/..%2fmanifest.json",
    f"/runs/{RUN}/artefacts/%2e%2e",
    f"/runs/{RUN}/artefacts/a2-clip%00",
    f"/runs/{RUN}/artefacts/a2-clip%5c",
    f"/runs/{RUN}/artefacts/a2-clip%2fx",
    f"/runs/{RUN}/artefacts/" + "a" * 97,
    f"/runs/{RUN}/artefacts/A2-CLIP",
    f"/runs/{RUN}/artefacts/-a2-clip",
    f"/runs/{RUN}/artefacts/a2.clip",
    f"/runs/{RUN}/artefacts/%2e",
    "/runs/..%2f/artefacts/a2-clip",
    # events
    f"/runs/{RUN}%2F/events",
    "/runs/%2e%2e/events",
    "/runs/" + "a" * 70 + "/events",
]


@pytest.mark.req("FR-003-14")
@pytest.mark.parametrize("target", HOSTILE_422, ids=[t[:60] for t in HOSTILE_422])
def test_fr_003_14_malformed_encoded_traversal_nul_and_overlong_parameters_are_422(cons, target: str) -> None:
    r = cons.client.get(target)
    assert r.status == 422, f"{target}: {r.status} {r.text[:120]}"
    problem(r)
    assert r.exception is None


@pytest.mark.req("FR-003-14")
@pytest.mark.parametrize(
    "path",
    [
        "/jobs/..%2f../cancel",
        "/jobs/xyz/cancel",
        f"/jobs/{GOOD_JOB}%00/cancel",
        "/jobs/20250101T000000Z-DEADBEEF/cancel",
        "/jobs/%2e%2e/cancel",
    ],
)
def test_fr_003_14_cancel_validates_its_path_too_and_changes_nothing(cons, path: str) -> None:
    before = cons.client.get("/queue").body
    r = cons.client.post(path, headers=[("origin", f"http://127.0.0.1:{cw.PORT}")])
    assert r.status == 422, f"{path}: {r.status}"
    assert cons.client.get("/queue").body == before


@pytest.mark.req("FR-003-14")
@pytest.mark.parametrize(
    "target",
    [
        f"/runs/{cw.RUN_ID[:-3]}zzz",
        "/runs/20250101T000000Z-nothing",
        "/recipes/no-such-recipe",
        f"/jobs/{GOOD_JOB}",
        f"/runs/{RUN}/artefacts/not-listed",
        "/runs/20250101T000000Z-nothing/artefacts/a2-clip",
        "/runs/20250101T000000Z-nothing/events",
    ],
    ids=[
        "unknown-run-near-miss",
        "unknown-run",
        "unknown-recipe",
        "unknown-job",
        "unknown-artefact",
        "artefact-of-unknown-run",
        "events-of-unknown-run",
    ],
)
def test_fr_003_14_well_formed_unknown_ids_are_404(cons, target: str) -> None:
    r = cons.client.get(target)
    assert r.status == 404, f"{target}: {r.status}"
    problem(r)


@pytest.mark.req("FR-003-14")
def test_fr_003_14_an_object_reached_through_a_link_outside_the_cas_is_404_and_never_served(
    cons, tmp_path: Path
) -> None:
    secret = b"SECRET CONTENT OUTSIDE THE STORE " + uuid.uuid4().hex.encode()
    outside = tmp_path / "outside-store"
    outside.mkdir()
    digest = pw.sha(cw.CLIP)
    (outside / digest).write_bytes(secret)
    fan_out = cons.w.store / "cas" / "sha256" / digest[:2]
    import shutil

    shutil.rmtree(fan_out)
    cw.junction_or_symlink(fan_out, outside)  # cas/sha256/<aa> now leads outside the store
    r = cons.client.get(f"/runs/{RUN}/artefacts/a2-clip")
    assert r.status == 404, f"{r.status}"
    assert secret not in r.body
    problem(r)
    rr = cons.client.get(f"/runs/{RUN}/artefacts/a2-clip", headers={"Range": "bytes=0-9"})
    assert rr.status in (404, 416) and secret[:10] not in rr.body


@pytest.mark.req("FR-003-14")
@pytest.mark.parametrize("method", ["DELETE", "PUT", "PATCH", "OPTIONS", "TRACE"])
def test_fr_003_14_undefined_methods_are_405_not_5xx(cons, method: str) -> None:
    for path in ("/runs", f"/runs/{RUN}", "/queue", "/health", "/jobs"):
        r = cons.client.request(method, path, headers=[("origin", f"http://127.0.0.1:{cw.PORT}")])
        assert r.status in (400, 403, 404, 405), f"{method} {path}: {r.status}"
        assert r.exception is None and r.status < 500


# ---- P-003-02 ------------------------------------------------------------------------------------------------------------------------------------------
FRAGMENTS = [
    "..",
    "%2e%2e",
    "%2E",
    "%2f",
    "%2F",
    "%5c",
    "%5C",
    "%00",
    ".",
    "/",
    "\\",
    "a2-clip",
    "a2-notes",
    RUN,
    "%252e",
    "%252f",
    "‮",
    "é",
    "．．",
    "x",
    "-",
    "_",
    "0",
    "T",
    "Z",
    "%20",
    "?",
    "#",
    ";",
    ":",
    "*",
    "~",
    "\n",
    "\t",
    "a" * 120,
    "..%2f..%2f",
    "..\\..\\",
    "%c0%af",
    "%e0%80%af",
    "%ef%bc%8f",
]


@st.composite
def segments(draw: st.DrawFn) -> str:
    parts = draw(st.lists(st.sampled_from(FRAGMENTS) | st.text(max_size=12), min_size=1, max_size=6))
    mode = draw(st.sampled_from(["raw-fragments", "quoted"]))
    s = "".join(parts)
    if mode == "quoted":
        return quote(s, safe="")
    # fragments that already hold percent escapes stay as they are; everything else is quoted so the target is a legal request line
    return (
        "".join(p if p.startswith("%") or p in ("..", ".", "/", "\\") else quote(p, safe="") for p in parts)
        .replace("\\", "%5C")
        .replace("\n", "%0A")
        .replace("\t", "%09")
    )


@pytest.mark.req("P-003-02")
@settings(max_examples=200, deadline=None, suppress_health_check=list(HealthCheck))
@given(run=segments(), art=segments(), use_good_run=st.booleans())
def test_p_003_02_only_listed_ids_are_ever_served_nothing_outside_cas_and_never_a_5xx(
    cons, run: str, art: str, use_good_run: bool
) -> None:
    canary = cons.w.base / "canary.txt"
    canary.write_text("CANARY-" + uuid.uuid4().hex, encoding="utf-8")
    from urllib.parse import unquote

    run_part = RUN if use_good_run else run
    for target in (f"/runs/{run_part}/artefacts/{art}", f"/runs/{run}"):
        r = cons.client.get(target)
        assert r.status < 500 and r.exception is None, f"{target}: {r.status}"
        assert canary.read_text(encoding="utf-8").encode() not in r.body
        assert b"root:" not in r.body and b"[boot loader]" not in r.body
        if r.status in (200, 206):
            if "/artefacts/" in target:
                assert unquote(art) in LISTED and unquote(run_part) == RUN, f"{target} was served"
            else:
                assert unquote(run) in (cw.RUN_ID, cw.OTHER_RUN_ID), f"{target} was served"
        else:
            assert r.status in (400, 404, 409, 416, 422), f"{target}: {r.status}"


@pytest.mark.req("P-003-02")
def test_p_003_02_the_fixture_ids_themselves_are_served(cons) -> None:
    assert cons.client.get(f"/runs/{RUN}/artefacts/a2-clip").status == 200
    assert cons.client.get(f"/runs/{RUN}/artefacts/a2-notes", headers={"Range": "bytes=0-4"}).status == 206
    assert cons.client.get(f"/runs/{RUN}").status == 200
