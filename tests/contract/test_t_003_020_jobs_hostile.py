# ruff: noqa: E501, PT018, RUF001
"""T-003-020: hostile `POST /jobs` bodies and the acceptance-agreement property (US-003-2).

Requirements: FR-003-10, P-003-01.

Expected behaviour (plan.md D2; stated for the implementer): a `POST /jobs` whose body is malformed JSON (including `NaN`,
duplicate keys, a byte-order mark, invalid UTF-8, an empty body) is a 400; a body over 65,536 bytes (declared by Content-Length or
sent chunked without it) is a 413; a content type other than `application/json` (parameters such as `; charset=utf-8` and any
letter case are fine) is a 415; a body that fails `contracts/recipe.schema.json#/$defs/job_request` (unknown field, in particular an
inline recipe, `entry`, `env` or `params`; wrong type; pattern; more than 64 or duplicate stages; empty stages) or names an unknown
or invalid recipe, a stage key absent from the recipe, or an unknown profile is a 422; every rejection is an
`application/problem+json` within 2 s, enqueues nothing and is never a 5xx. The only accepted bodies (202) are those that validate
and name a committed valid recipe, its stage keys and an existing profile (P-003-01).
Oracles: Python `jsonschema` against the job_request definition as the reference acceptor, the fixture recipes written by hand
(a2-haulage: s10_preprocess, st10_terrain; bench-one: s64_bench; profile test-profile), byte-exact hostile bodies.
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
import schemas

LIMIT = 65536
OK = {"recipe": "a2-haulage", "profile": "test-profile"}
RECIPE_STAGES = {"a2-haulage": {"s10_preprocess", "st10_terrain"}, "bench-one": {"s64_bench"}}


@pytest.fixture
def cons(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    c = cw.make_console_world(monkeypatch, tmp_path)
    yield c
    rw.cleanup_world(c.w)


class Counter:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pitstudio.runner import queue

        self.n = 0
        real = queue.enqueue

        def enqueue(*a: Any, **k: Any) -> Any:
            self.n += 1
            return real(*a, **k)

        monkeypatch.setattr(queue, "enqueue", enqueue)


def post(cons: cw.ConsoleWorld, *, body: bytes | None = None, content_type: str | None = "application/json", **kw: Any):
    headers = [("content-type", content_type)] if content_type is not None else []
    t0 = time.monotonic()
    r = cons.client.post("/jobs", headers=headers, body=body, **kw)
    assert time.monotonic() - t0 < 2.0, "a rejection must take less than 2 s"
    return r


def rejected(r: Any, *statuses: int) -> None:
    assert r.status in statuses, f"{r.status} not in {statuses}: {r.text[:200]}"
    assert r.status < 500 and r.exception is None
    assert (r.header("content-type") or "").startswith("application/problem+json")
    body = r.json()
    assert schemas.errors("console", body, "#/$defs/problem") == [] and body["status"] == r.status


def padded(extra_bytes: int) -> bytes:
    """A valid request padded with JSON white space to `len(valid) + extra_bytes`."""
    core = json.dumps(OK).encode()
    return core + b" " * extra_bytes


# ---- 400: malformed JSON ------------------------------------------------------------------------------------------------------------------------------
MALFORMED = [
    ("truncated", b'{"recipe": "a2-haulage", "profile": '),
    ("nan", b'{"recipe": "a2-haulage", "profile": "test-profile", "force": NaN}'),
    ("infinity", b'{"recipe": "a2-haulage", "profile": "test-profile", "force": Infinity}'),
    ("duplicate-keys", b'{"recipe": "a2-haulage", "recipe": "bench-one", "profile": "test-profile"}'),
    ("bom", b"\xef\xbb\xbf" + json.dumps(OK).encode()),
    ("invalid-utf8", b'{"recipe": "a2-\xff\xfe", "profile": "test-profile"}'),
    ("empty-body", b""),
    ("only-whitespace", b"   \n  "),
    ("single-quotes", b"{'recipe': 'a2-haulage', 'profile': 'test-profile'}"),
    ("trailing-comma", b'{"recipe": "a2-haulage", "profile": "test-profile",}'),
    ("comment", b'{"recipe": "a2-haulage", /* c */ "profile": "test-profile"}'),
    ("two-documents", json.dumps(OK).encode() + json.dumps(OK).encode()),
    ("nul-byte", b'{"recipe": "a2-haulage\x00", "profile": "test-profile"}'),
    ("deeply-nested", b"[" * 5000 + b"]" * 5000),
    ("lone-surrogate-escape", b'{"recipe": "\\ud800", "profile": "test-profile"}'),
]


@pytest.mark.req("FR-003-10")
@pytest.mark.parametrize(("label", "body"), MALFORMED, ids=[m[0] for m in MALFORMED])
def test_fr_003_10_malformed_json_is_400_and_enqueues_nothing(
    cons, monkeypatch: pytest.MonkeyPatch, label: str, body: bytes
) -> None:
    spy = Counter(monkeypatch)
    r = post(cons, body=body)
    rejected(r, 400, 422)
    if label not in ("lone-surrogate-escape", "deeply-nested"):
        assert r.status == 400, f"{label}: malformed JSON must be 400, got {r.status}"
    assert spy.n == 0 and cons.client.get("/queue").json()["jobs"] == []


@pytest.mark.req("FR-003-10")
@pytest.mark.parametrize(
    "body",
    [b"[]", b'"text"', b"123", b"null", b"true", b'[{"recipe": "a2-haulage", "profile": "test-profile"}]'],
    ids=["array", "string", "number", "null", "bool", "array-of-request"],
)
def test_fr_003_10_valid_json_that_is_not_an_object_is_422(cons, body: bytes) -> None:
    rejected(post(cons, body=body), 422)


# ---- 413: size -------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-003-10")
def test_fr_003_10_the_size_limit_is_exact_with_and_without_a_content_length(cons) -> None:
    exact = padded(LIMIT - len(json.dumps(OK)))
    assert len(exact) == LIMIT
    ok = post(cons, body=exact)
    assert ok.status == 202, f"a body of exactly {LIMIT} bytes is within the limit: {ok.status} {ok.text[:200]}"
    over = padded(LIMIT + 1 - len(json.dumps(OK)))
    assert len(over) == LIMIT + 1
    rejected(post(cons, body=over), 413)
    rejected(post(cons, chunks=[over[:30000], over[30000:60000], over[60000:]], content_type="application/json"), 413)
    ok_chunked = post(cons, chunks=[exact[:100], exact[100:40000], exact[40000:]])
    assert ok_chunked.status == 202, f"a chunked body within the limit is accepted: {ok_chunked.status}"


@pytest.mark.req("FR-003-10")
def test_fr_003_10_a_declared_huge_length_or_an_endless_chunked_body_is_cut_off(cons) -> None:
    r = cons.client.post(
        "/jobs",
        headers=[("content-type", "application/json"), ("content-length", "999999999999")],
        body=b'{"recipe": "x"}',
        content_length=False,
    )
    rejected(r, 413, 400, 422)
    chunks = [b"x" * 100_000 for _ in range(30)]  # 3 MB without a Content-Length
    t0 = time.monotonic()
    rejected(cons.client.post("/jobs", headers=[("content-type", "application/json")], chunks=chunks), 413)
    assert time.monotonic() - t0 < 2.0
    # a lying Content-Length: shorter than the body actually sent
    liar = cons.client.post(
        "/jobs",
        headers=[("content-type", "application/json"), ("content-length", "10")],
        body=padded(LIMIT * 2),
        content_length=False,
    )
    assert liar.status in (400, 413, 422) and liar.status < 500


# ---- 415 -------------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-003-10")
@pytest.mark.parametrize(
    "ctype",
    [
        "text/plain",
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
        "application/jsonx",
        "application/vnd.api+json",
        "text/json",
        "application/xml",
        "json",
        "",
        None,
    ],
    ids=["text", "form", "multipart", "jsonx", "vnd", "text-json", "xml", "bare-json", "empty", "absent"],
)
def test_fr_003_10_a_content_type_other_than_application_json_is_415(
    cons, monkeypatch: pytest.MonkeyPatch, ctype: str | None
) -> None:
    spy = Counter(monkeypatch)
    rejected(post(cons, body=json.dumps(OK).encode(), content_type=ctype), 415)
    assert spy.n == 0


@pytest.mark.req("FR-003-10")
@pytest.mark.parametrize(
    "ctype",
    [
        "application/json",
        "application/json; charset=utf-8",
        "application/json;charset=UTF-8",
        "Application/JSON",
        "APPLICATION/JSON; charset=utf-8",
    ],
)
def test_fr_003_10_application_json_with_parameters_or_any_case_is_accepted(cons, ctype: str) -> None:
    r = post(cons, body=json.dumps(OK).encode(), content_type=ctype)
    assert r.status == 202, f"{ctype}: {r.status} {r.text[:200]}"


# ---- 422 ------------------------------------------------------------------------------------------------------------------------------------------------------
SCHEMA_VIOLATIONS: list[tuple[str, dict[str, Any]]] = [
    ("inline-recipe-object", {**OK, "recipe": {"id": "x", "case": "A1", "seed": 1, "stages": []}}),
    ("inline-recipe-field", {**OK, "stages": [{"id": "s10_preprocess"}], "inline_recipe": {"id": "x"}}),
    ("entry-injection", {**OK, "entry": "os; rm -rf /"}),
    ("env-field", {**OK, "env": "studio"}),
    ("params-field", {**OK, "params": {"particles": 1}}),
    ("stage-with-params", {**OK, "stages": [{"id": "s10_preprocess", "params": {"x": 1}}]}),
    ("stage-with-entry", {**OK, "stages": [{"id": "s10_preprocess", "entry": "evil.module"}]}),
    ("recipe-wrong-type", {**OK, "recipe": 5}),
    ("recipe-null", {**OK, "recipe": None}),
    ("recipe-missing", {"profile": "test-profile"}),
    ("profile-missing", {"recipe": "a2-haulage"}),
    ("profile-wrong-type", {**OK, "profile": ["test-profile"]}),
    ("force-string", {**OK, "force": "yes"}),
    ("force-number", {**OK, "force": 1}),
    ("rerun-check-null", {**OK, "rerun_check": None}),
    ("stages-string", {**OK, "stages": "s10_preprocess"}),
    ("stages-empty", {**OK, "stages": []}),
    ("stage-id-unknown-enum", {**OK, "stages": [{"id": "st99_magic"}]}),
    ("stage-id-injection", {**OK, "stages": [{"id": "../../etc/passwd"}]}),
    ("stage-variant-pattern", {**OK, "stages": [{"id": "s10_preprocess", "variant": "UPPER"}]}),
    ("stage-not-an-object", {**OK, "stages": ["s10_preprocess"]}),
    ("duplicate-stages", {**OK, "stages": [{"id": "s10_preprocess"}, {"id": "s10_preprocess"}]}),
    ("65-stages", {**OK, "stages": [{"id": "s10_preprocess", "variant": f"v{i}"} for i in range(65)]}),
    ("recipe-uppercase", {**OK, "recipe": "A2-Haulage"}),
    ("recipe-traversal", {**OK, "recipe": "../a2-haulage"}),
    ("recipe-slash", {**OK, "recipe": "cases/a2-haulage"}),
    ("recipe-dot-yaml", {**OK, "recipe": "a2-haulage.yaml"}),
    ("recipe-65-chars", {**OK, "recipe": "a" * 65}),
    ("recipe-fullwidth-unicode", {**OK, "recipe": "ａ２-haulage"}),
    ("recipe-trailing-newline", {**OK, "recipe": "a2-haulage\n"}),
    ("recipe-nul", {**OK, "recipe": "a2-haulage\u0000"}),
    ("profile-traversal", {**OK, "profile": "../test-profile"}),
    ("profile-empty", {**OK, "profile": ""}),
    ("empty-object", {}),
    ("recipe-unknown", {**OK, "recipe": "no-such-recipe"}),
    ("recipe-invalid-file", {**OK, "recipe": "broken-one"}),
    ("profile-unknown", {**OK, "profile": "no-such-profile"}),
    ("stage-absent-from-recipe", {**OK, "stages": [{"id": "st50_physics"}]}),
    ("stage-variant-absent", {**OK, "stages": [{"id": "s10_preprocess", "variant": "nope"}]}),
    ("stage-of-another-recipe", {**OK, "stages": [{"id": "s64_bench"}]}),
    ("one-good-one-bad-stage", {**OK, "stages": [{"id": "s10_preprocess"}, {"id": "st50_physics"}]}),
    (
        "bench-stage-on-case-recipe",
        {"recipe": "bench-one", "profile": "test-profile", "stages": [{"id": "s10_preprocess"}]},
    ),
]


@pytest.mark.req("FR-003-10")
@pytest.mark.parametrize(("label", "doc"), SCHEMA_VIOLATIONS, ids=[s[0] for s in SCHEMA_VIOLATIONS])
def test_fr_003_10_schema_violations_and_unknown_names_are_422_and_enqueue_nothing(
    cons, monkeypatch: pytest.MonkeyPatch, label: str, doc: dict[str, Any]
) -> None:
    spy = Counter(monkeypatch)
    rejected(post(cons, body=json.dumps(doc).encode()), 422)
    assert spy.n == 0
    assert cons.client.get("/queue").json()["jobs"] == []


@pytest.mark.req("FR-003-10")
def test_fr_003_10_a_422_names_the_offending_fields_without_echoing_dangerous_content(cons) -> None:
    r = post(cons, body=json.dumps({**OK, "entry": "<script>alert(1)</script>"}).encode())
    rejected(r, 422)
    assert "<script>" not in r.text and "\n" not in r.json()["detail"] and len(r.json()["detail"]) <= 300
    assert all(len(e["message"]) <= 300 and "\n" not in e["message"] for e in r.json().get("errors", []))


# ---- P-003-01 -----------------------------------------------------------------------------------------------------------------------------------------------
recipes = st.sampled_from(
    ["a2-haulage", "bench-one", "broken-one", "zzz-none", "A", "x" * 65, 5, None, "a2-haulage\n", ""]
)
profiles = st.sampled_from(["test-profile", "no-such-profile", "T", 3, None, "", "../test-profile"])
stage_lists = st.one_of(
    st.none(),
    st.just([]),
    st.just([{"id": "s10_preprocess"}]),
    st.just([{"id": "st10_terrain"}]),
    st.just([{"id": "s10_preprocess"}, {"id": "st10_terrain"}]),
    st.just([{"id": "s64_bench"}]),
    st.just([{"id": "st50_physics"}]),
    st.just([{"id": "s10_preprocess", "variant": "v"}]),
    st.just([{"id": "s10_preprocess"}, {"id": "s10_preprocess"}]),
    st.just([{"id": "s10_preprocess", "params": {}}]),
    st.just("s10_preprocess"),
    st.just([{"id": "s10_preprocess", "variant": f"v{i}"} for i in range(65)]),
)
flags = st.sampled_from([None, True, False, "yes", 1, 0])
extras = st.sampled_from([None, "entry", "env", "params", "recipe_inline", "note"])


def oracle_accepts(body: dict[str, Any]) -> bool:
    """Reference acceptor: job_request schema (Python jsonschema) AND a committed valid recipe, its stage keys, an existing profile."""
    if schemas.errors("recipe", body, "#/$defs/job_request"):
        return False
    stages = RECIPE_STAGES.get(body["recipe"])
    if stages is None or body["profile"] != "test-profile":
        return False
    return all(s["id"] in stages and "variant" not in s for s in body.get("stages", []))


@pytest.mark.req("P-003-01")
@settings(max_examples=150, deadline=None, suppress_health_check=list(HealthCheck))
@given(recipe=recipes, profile=profiles, stages=stage_lists, force=flags, rerun=flags, extra=extras)
def test_p_003_01_post_jobs_answers_202_iff_the_body_validates_and_names_committed_things(
    cons, recipe: Any, profile: Any, stages: Any, force: Any, rerun: Any, extra: str | None
) -> None:
    body: dict[str, Any] = {"recipe": recipe, "profile": profile}
    body.update({k: v for k, v in (("stages", stages), ("force", force), ("rerun_check", rerun)) if v is not None})
    if extra:
        body[extra] = {"x": 1} if extra != "note" else "hi"
    r = cons.client.post("/jobs", json_body=body)
    accepts = oracle_accepts({k: v for k, v in body.items() if v is not None or k in ("recipe", "profile")})
    if accepts:
        assert r.status == 202, f"{body}: expected 202, got {r.status} {r.text[:150]}"
    else:
        assert r.status in (400, 413, 415, 422), f"{body}: expected a 4xx rejection, got {r.status}"
    assert r.status < 500 and r.exception is None
