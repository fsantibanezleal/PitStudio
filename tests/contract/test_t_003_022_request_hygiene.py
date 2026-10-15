# ruff: noqa: E501, PT018
"""T-003-022: Host check, cross-site POST refusal, CORS for /health only, hostile allowlists, problem bodies and security headers.

Requirements: FR-003-18, FR-003-19, FR-003-20, FR-003-21, FR-003-22.

Expected behaviour (plan.md D2, D5; stated for the implementer):
  * a `Host` header that is not exactly `127.0.0.1:<port>` or `localhost:<port>` (host part case-insensitive) is a 400 for any method
    and path (DNS rebinding); a missing Host header too;
  * a POST with an `Origin` other than `http://127.0.0.1:<port>` / `http://localhost:<port>` (including `null`), or
    `Sec-Fetch-Site: cross-site`, is a 403 and enqueues/cancels nothing;
  * CORS: only `GET /health` (and its OPTIONS preflight for GET) from an origin in the allowlist
    (`PITSTUDIO_CONSOLE_ALLOW_ORIGINS`, exact string equality, default `https://fsantibanezleal.github.io`) gets
    `Access-Control-Allow-Origin: <that origin>` + `Vary: Origin` (never `Access-Control-Allow-Credentials`; the preflight is 204 with
    `Access-Control-Allow-Methods: GET`, `Access-Control-Max-Age: 600` and `Access-Control-Allow-Private-Network: true` when asked);
    every other path, method or origin gets no CORS header and its preflight is 403;
  * `pitstudio_api.config.parse_allow_origins(value: str | None) -> list[str]` (None = the default) raises ValueError naming a bad
    entry (`*`, a path, query, fragment, user information, a non-https scheme other than loopback `http://127.0.0.1:<port>` /
    `http://localhost:<port>`); the process exits 2 at start naming the entry;
  * every error response is `application/problem+json` (RFC 9457) with `status` = the HTTP status and `detail` <= 300 characters,
    no stack trace and no absolute path; every response has `X-Content-Type-Options: nosniff`; every HTML response has
    `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'`; JSON responses are `Cache-Control: no-store`.
Oracles: the Fetch standard's CORS semantics and RFC 9457 field rules written out by hand; the table of hostile hosts, origins and
allowlists below; the contract schema `problem`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import console_world as cw
import runner_world as rw
import schemas

PORT = cw.PORT
PUBLIC = "https://fsantibanezleal.github.io"
OK_BODY = {"recipe": "a2-haulage", "profile": "test-profile"}


@pytest.fixture
def cons(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    c = cw.make_console_world(monkeypatch, tmp_path)
    ui = c.w.repo / "web" / "build" / "console"
    ui.mkdir(parents=True)
    (ui / "index.html").write_text(
        "<!doctype html><html><head><title>c</title></head><body><!-- pitstudio-console-build --></body></html>",
        encoding="utf-8",
    )
    (ui / "app.js").write_text("// pitstudio-console-build\nconsole.log(1)\n", encoding="utf-8")
    yield c
    rw.cleanup_world(c.w)


class Spy:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pitstudio.runner import queue

        self.enqueued = 0
        self.cancelled = 0
        real_e, real_c = queue.enqueue, queue.cancel

        def enqueue(*a: Any, **k: Any) -> Any:
            self.enqueued += 1
            return real_e(*a, **k)

        def cancel(*a: Any, **k: Any) -> Any:
            self.cancelled += 1
            return real_c(*a, **k)

        monkeypatch.setattr(queue, "enqueue", enqueue)
        monkeypatch.setattr(queue, "cancel", cancel)


def is_problem(r: Any, status: int | None = None) -> None:
    assert (r.header("content-type") or "").startswith("application/problem+json"), (r.status, r.header("content-type"))
    body = r.json()
    assert schemas.errors("console", body, "#/$defs/problem") == []
    assert body["status"] == r.status and (status is None or r.status == status)


# ---- FR-003-18: Host ---------------------------------------------------------------------------------------------------------------------------------
BAD_HOSTS = [
    "evil.com",
    f"evil.com:{PORT}",
    "127.0.0.1",
    "localhost",
    f"127.0.0.1:{PORT + 1}",
    "127.0.0.1:1",
    f"127.0.0.1:{PORT}.evil.com",
    f"localhost.evil.com:{PORT}",
    f"[::1]:{PORT}",
    f"0.0.0.0:{PORT}",
    f"127.0.0.2:{PORT}",
    "",
    f"127.0.0.1:{PORT}@evil.com",
    f"evil.com#@127.0.0.1:{PORT}",
    f"localhost.:{PORT}",
    f"user@127.0.0.1:{PORT}",
    f"127.0.0.1:0{PORT}",
    f"127.0.0.1:{PORT}:{PORT}",
    f"LOCALHOST:{PORT + 5}",
    f"1.1.1.1:{PORT}",
    f"127.1:{PORT}",
    f"2130706433:{PORT}",
    f"0x7f.0.0.1:{PORT}",
    f"127.0.0.1:{PORT}/x",
]
ANY_REQUESTS = [
    ("GET", "/health"),
    ("GET", "/runs"),
    ("GET", "/no/such/path"),
    ("POST", "/jobs"),
    ("OPTIONS", "/health"),
    ("DELETE", "/runs/x"),
    ("GET", "/ui/"),
    ("GET", "/openapi.json"),
]


@pytest.mark.req("FR-003-18")
@pytest.mark.parametrize("host", BAD_HOSTS, ids=[repr(h)[:40] for h in BAD_HOSTS])
def test_fr_003_18_a_wrong_host_header_is_400_for_every_method_and_path(
    cons, monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    spy = Spy(monkeypatch)
    for method, path in ANY_REQUESTS:
        r = cons.client.request(
            method,
            path,
            host=host if host else "",
            headers=[("host", host)] if host == "" else None,
            body=json.dumps(OK_BODY).encode() if method == "POST" else None,
        )
        assert r.status == 400, f"{method} {path} Host={host!r}: {r.status}"
        is_problem(r, 400)
    assert spy.enqueued == 0


@pytest.mark.req("FR-003-18")
def test_fr_003_18_a_missing_host_header_is_400(cons) -> None:
    r = cons.client.request("GET", "/health", host="")
    assert r.status == 400


@pytest.mark.req("FR-003-18")
@pytest.mark.parametrize("host", [f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"LOCALHOST:{PORT}", f"LocalHost:{PORT}"])
def test_fr_003_18_loopback_hosts_with_the_right_port_are_served_host_part_case_insensitively(cons, host: str) -> None:
    for path in ("/health", "/runs", "/recipes", "/queue"):
        assert cons.client.get(path, host=host).status == 200, f"Host {host}: {path}"


@pytest.mark.req("FR-003-18")
def test_fr_003_18_forwarded_headers_do_not_override_the_host_rule(cons) -> None:
    r = cons.client.get(
        "/health",
        host="evil.com",
        headers=[("x-forwarded-host", f"127.0.0.1:{PORT}"), ("forwarded", f"host=127.0.0.1:{PORT}")],
    )
    assert r.status == 400
    ok = cons.client.get("/health", headers=[("x-forwarded-host", "evil.com")])
    assert ok.status == 200


# ---- FR-003-19: Origin / Sec-Fetch-Site on POST -------------------------------------------------------------------------------------------------------
BAD_ORIGINS = [
    "null",
    "http://evil.com",
    "https://evil.com",
    PUBLIC,
    "http://127.0.0.1",
    f"https://127.0.0.1:{PORT}",
    f"http://127.0.0.1:{PORT + 1}",
    f"http://127.0.0.1:{PORT}.evil.com",
    f"http://localhost.evil.com:{PORT}",
    "file://",
    "*",
    f"http://127.0.0.1:{PORT}/",
    f"http://0.0.0.0:{PORT}",
    f"http://[::1]:{PORT}",
    "chrome-extension://abc",
]


@pytest.mark.req("FR-003-19")
@pytest.mark.parametrize("origin", BAD_ORIGINS, ids=[repr(o)[:40] for o in BAD_ORIGINS])
def test_fr_003_19_a_post_from_another_origin_is_403_and_changes_nothing(
    cons, monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    spy = Spy(monkeypatch)
    job_id = cons.post_job().json()["job_id"]
    spy.enqueued = 0
    r = cons.client.post("/jobs", json_body=OK_BODY, headers=[("origin", origin)])
    assert r.status == 403, f"Origin {origin!r}: {r.status}"
    is_problem(r, 403)
    c = cons.client.post(f"/jobs/{job_id}/cancel", headers=[("origin", origin)])
    assert c.status == 403
    assert spy.enqueued == 0 and spy.cancelled == 0
    assert cons.client.get(f"/jobs/{job_id}").json()["state"] == "queued"


@pytest.mark.req("FR-003-19")
@pytest.mark.parametrize("site", ["cross-site", "Cross-Site", "CROSS-SITE"])
def test_fr_003_19_sec_fetch_site_cross_site_is_403_even_with_an_allowed_origin_or_none(
    cons, monkeypatch: pytest.MonkeyPatch, site: str
) -> None:
    spy = Spy(monkeypatch)
    for extra in ([], [("origin", f"http://127.0.0.1:{PORT}")]):
        r = cons.client.post("/jobs", json_body=OK_BODY, headers=[("sec-fetch-site", site), *extra])
        assert r.status == 403, f"{site} {extra}: {r.status}"
    assert spy.enqueued == 0


@pytest.mark.req("FR-003-19")
@pytest.mark.parametrize(
    "headers",
    [
        [],
        [("origin", f"http://127.0.0.1:{PORT}")],
        [("origin", f"http://localhost:{PORT}")],
        [("sec-fetch-site", "same-origin")],
        [("sec-fetch-site", "none")],
        [("origin", f"http://127.0.0.1:{PORT}"), ("sec-fetch-site", "same-origin")],
    ],
    ids=["no-origin", "loopback-ip", "localhost", "same-origin", "none", "both"],
)
def test_fr_003_19_same_origin_and_non_browser_posts_are_accepted(cons, headers: list[tuple[str, str]]) -> None:
    r = cons.client.post("/jobs", json_body=OK_BODY, headers=headers)
    assert r.status == 202, f"{headers}: {r.status} {r.text[:150]}"


# ---- FR-003-20: CORS ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-003-20")
def test_fr_003_20_health_from_the_allowlisted_origin_gets_the_exact_origin_and_vary_and_no_credentials(cons) -> None:
    r = cons.client.get("/health", headers=[("origin", PUBLIC)])
    assert r.status == 200
    assert r.header("access-control-allow-origin") == PUBLIC
    assert "origin" in (r.header("vary") or "").lower().replace(" ", "").split(",")
    assert r.header("access-control-allow-credentials") is None
    assert r.header("access-control-allow-private-network") is None, (
        "only the preflight carries the private-network header"
    )


@pytest.mark.req("FR-003-20")
def test_fr_003_20_the_preflight_for_get_health_is_204_with_methods_max_age_and_private_network(cons) -> None:
    r = cons.client.request(
        "OPTIONS",
        "/health",
        headers=[
            ("origin", PUBLIC),
            ("access-control-request-method", "GET"),
            ("access-control-request-private-network", "true"),
        ],
    )
    assert r.status == 204, f"{r.status} {r.text[:120]}"
    assert r.header("access-control-allow-origin") == PUBLIC
    assert r.header("access-control-allow-methods") == "GET"
    assert r.header("access-control-max-age") == "600"
    assert r.header("access-control-allow-private-network") == "true"
    assert r.header("access-control-allow-credentials") is None
    assert "origin" in (r.header("vary") or "").lower()
    plain = cons.client.request(
        "OPTIONS", "/health", headers=[("origin", PUBLIC), ("access-control-request-method", "GET")]
    )
    assert plain.status == 204 and plain.header("access-control-allow-private-network") is None, "only when requested"


@pytest.mark.req("FR-003-20")
@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.com",
        "https://fsantibanezleal.github.io.example.com",
        "http://fsantibanezleal.github.io",
        "https://FSANTIBANEZLEAL.github.io",
        "null",
        "https://fsantibanezleal.github.io/",
        "https://fsantibanezleal.github.io:443",
        f"http://127.0.0.1:{PORT}",
        "*",
    ],
    ids=repr,
)
def test_fr_003_20_origins_outside_the_allowlist_get_no_cors_header_and_a_403_preflight(cons, origin: str) -> None:
    r = cons.client.get("/health", headers=[("origin", origin)])
    assert r.status == 200
    assert not [k for k, _ in r.headers if k.startswith("access-control-")], r.headers
    pre = cons.client.request(
        "OPTIONS", "/health", headers=[("origin", origin), ("access-control-request-method", "GET")]
    )
    assert pre.status == 403, f"{origin!r}: {pre.status}"
    assert not [k for k, _ in pre.headers if k.startswith("access-control-")]


@pytest.mark.req("FR-003-20")
@pytest.mark.parametrize(
    "path",
    [
        "/recipes",
        "/queue",
        "/runs",
        f"/runs/{cw.RUN_ID}",
        "/openapi.json",
        "/jobs/20250101T000000Z-deadbeef",
        "/ui/",
        "/no/such",
    ],
)
def test_fr_003_20_no_other_path_is_readable_from_the_public_origin(cons, path: str) -> None:
    r = cons.client.get(path, headers=[("origin", PUBLIC)])
    assert not [k for k, _ in r.headers if k.startswith("access-control-")], f"{path}: {r.headers}"
    pre = cons.client.request("OPTIONS", path, headers=[("origin", PUBLIC), ("access-control-request-method", "GET")])
    assert pre.status in (403, 404, 405) and not [k for k, _ in pre.headers if k.startswith("access-control-")]
    assert pre.status == 403 if path != "/no/such" else pre.status in (403, 404)


@pytest.mark.req("FR-003-20")
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_fr_003_20_no_other_method_is_allowed_for_the_public_origin(cons, method: str) -> None:
    pre = cons.client.request(
        "OPTIONS", "/health", headers=[("origin", PUBLIC), ("access-control-request-method", method)]
    )
    assert pre.status == 403 and not [k for k, _ in pre.headers if k.startswith("access-control-")]
    r = cons.client.request(method, "/health", headers=[("origin", PUBLIC)])
    assert not [k for k, _ in r.headers if k.startswith("access-control-")]
    post = cons.client.post("/jobs", json_body=OK_BODY, headers=[("origin", PUBLIC)])
    assert post.status == 403 and not [k for k, _ in post.headers if k.startswith("access-control-")]


@pytest.mark.req("FR-003-20")
def test_fr_003_20_the_allowlist_comes_from_the_environment_and_matches_exactly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(
        "PITSTUDIO_CONSOLE_ALLOW_ORIGINS", "https://a.example,https://b.example:8443,http://localhost:5173"
    )
    c = cw.make_console_world(monkeypatch, tmp_path)
    try:
        for origin in ("https://a.example", "https://b.example:8443", "http://localhost:5173"):
            assert c.client.get("/health", headers=[("origin", origin)]).header("access-control-allow-origin") == origin
        for origin in (PUBLIC, "https://a.example.evil.com", "https://b.example", "https://A.example"):
            assert c.client.get("/health", headers=[("origin", origin)]).header("access-control-allow-origin") is None
    finally:
        rw.cleanup_world(c.w)


# ---- FR-003-21: hostile allowlists -------------------------------------------------------------------------------------------------------------------------
BAD_ENTRIES = [
    ("*", "*"),
    ("https://a.example/path", "https://a.example/path"),
    ("https://a.example/", "https://a.example/"),
    ("https://a.example?x=1", "https://a.example?x=1"),
    ("https://a.example#frag", "https://a.example#frag"),
    ("https://user:pw@a.example", "https://user:pw@a.example"),
    ("https://user@a.example", "https://user@a.example"),
    ("http://a.example", "http://a.example"),
    ("ftp://a.example", "ftp://a.example"),
    ("a.example", "a.example"),
    ("https://", "https://"),
    ("http://localhost", "http://localhost"),
    ("http://127.0.0.1", "http://127.0.0.1"),
    ("http://localhost:0", "http://localhost:0"),
    ("http://localhost:99999", "http://localhost:99999"),
    ("https://a.example:99999", "https://a.example:99999"),
    ("javascript:alert(1)", "javascript:alert(1)"),
    ("https://*.example", "https://*.example"),
    ("https://a.example,*", "*"),
    ("https://a.example,,https://b.example", ""),
]
GOOD_ENTRIES = [
    "https://a.example",
    "https://a.example:8443",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "https://fsantibanezleal.github.io",
    "https://a.example,https://b.example",
    "https://a-b.example.org",
]


@pytest.mark.req("FR-003-21")
@pytest.mark.parametrize(("value", "named"), BAD_ENTRIES, ids=[repr(b[0]) for b in BAD_ENTRIES])
def test_fr_003_21_a_bad_allowlist_entry_is_rejected_naming_it(value: str, named: str) -> None:
    from pitstudio_api import config

    with pytest.raises(ValueError, match=r"(?s).+") as e:  # the message must name the entry (checked below)
        config.parse_allow_origins(value)
    assert named in str(e.value)


@pytest.mark.req("FR-003-21")
@pytest.mark.parametrize("value", GOOD_ENTRIES)
def test_fr_003_21_valid_allowlists_parse_in_order(value: str) -> None:
    from pitstudio_api import config

    assert config.parse_allow_origins(value) == value.split(",")
    assert config.parse_allow_origins(None) == [PUBLIC]


@pytest.mark.req("FR-003-21")
@pytest.mark.parametrize("value", ["*", "https://a.example/path", "http://a.example", "https://user:pw@a.example"])
def test_fr_003_21_the_process_exits_2_at_start_naming_the_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    w = rw.make_world(monkeypatch, tmp_path)
    try:
        env = {**w.env(), "PITSTUDIO_CONSOLE_ALLOW_ORIGINS": value}
        env.pop("PITSTUDIO_CONSOLE_PORT", None)
        p = subprocess.run(
            [sys.executable, "-m", "pitstudio_api"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(w.base),
            timeout=60,
        )
        assert p.returncode == 2, p.stdout + p.stderr
        assert value in p.stdout + p.stderr
        assert not re.search(r"http://127\.0\.0\.1:\d+/ui/", p.stdout), "no URL may be printed"
    finally:
        rw.cleanup_world(w)


# ---- FR-003-22: problem bodies and security headers -------------------------------------------------------------------------------------------------------
ERROR_REQUESTS: list[tuple[str, str, dict[str, Any]]] = [
    ("GET", "/no/such/path", {}),
    ("GET", "/runs/not-a-run", {}),
    ("GET", f"/runs/{cw.BROKEN_RUN_ID}", {}),
    ("GET", "/runs/20250101T000000Z-nothing", {}),
    ("GET", "/recipes/no-such", {}),
    ("GET", "/jobs/xyz", {}),
    ("DELETE", "/runs", {}),
    ("POST", "/jobs", {"body": b"{", "headers": [("content-type", "application/json")]}),
    ("POST", "/jobs", {"body": b"{}", "headers": [("content-type", "text/plain")]}),
    ("POST", "/jobs", {"json_body": {"recipe": "zzz", "profile": "test-profile"}}),
    ("POST", "/jobs", {"json_body": OK_BODY, "headers": [("origin", "http://evil.com")]}),
    ("GET", "/health", {"host": "evil.com"}),
    ("GET", f"/runs/{cw.RUN_ID}/artefacts/a2-clip", {"headers": [("range", "bytes=999999999-")]}),
    ("GET", f"/runs/{cw.RUN_ID}/events", {"headers": [("last-event-id", "abc")]}),
    ("POST", "/jobs/20250101T000000Z-deadbeef/cancel", {}),
]


@pytest.mark.req("FR-003-22")
@pytest.mark.parametrize(("method", "path", "kw"), ERROR_REQUESTS, ids=[f"{m} {p}"[:50] for m, p, _ in ERROR_REQUESTS])
def test_fr_003_22_every_error_is_a_rfc_9457_problem_without_trace_or_path_and_with_nosniff(
    cons, method: str, path: str, kw: dict[str, Any]
) -> None:
    r = cons.client.request(method, path, **kw)
    assert 400 <= r.status < 500, f"{method} {path}: {r.status}"
    is_problem(r)
    body = r.json()
    assert len(body["detail"]) <= 300 and "\n" not in body["detail"] and "\n" not in body["title"]
    text = r.text
    assert "Traceback" not in text and 'File "' not in text and "site-packages" not in text
    assert not re.search(r"[A-Za-z]:[\\/]", text) and not re.search(
        r"(^|[\s\"'=(,:])/(home|Users|root|tmp|var|mnt|opt|srv)/", text
    )
    assert str(cons.w.repo) not in text and str(cons.w.store) not in text
    assert r.header("x-content-type-options") == "nosniff"


@pytest.mark.req("FR-003-22")
@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/recipes",
        "/recipes/a2-haulage",
        "/queue",
        "/runs",
        f"/runs/{cw.RUN_ID}",
        "/openapi.json",
        f"/runs/{cw.RUN_ID}/artefacts/a2-clip",
    ],
)
def test_fr_003_22_every_success_carries_nosniff_and_json_is_never_cached(cons, path: str) -> None:
    r = cons.client.get(path)
    assert r.status == 200
    assert r.header("x-content-type-options") == "nosniff"
    if path.endswith("a2-clip"):
        return  # artefacts may be cached (plan.md D5)
    assert "no-store" in (r.header("cache-control") or "")


@pytest.mark.req("FR-003-22")
def test_fr_003_22_html_responses_carry_the_content_security_policy(cons) -> None:
    for path in ("/ui/", "/ui/index.html"):
        r = cons.client.get(path)
        assert r.status == 200, f"{path}: {r.status}"
        assert (r.header("content-type") or "").startswith("text/html")
        assert r.header("content-security-policy") == "default-src 'self'; frame-ancestors 'none'"
        assert r.header("x-content-type-options") == "nosniff"
    js = cons.client.get("/ui/app.js")
    assert js.status == 200 and js.header("x-content-type-options") == "nosniff"
    for bad in ("/ui/../../secret", "/ui/%2e%2e/%2e%2e/etc/passwd", "/ui/..%5c..%5cwindows"):
        r = cons.client.get(bad)
        assert r.status in (400, 404, 422) and r.status < 500
        assert b"pitstudio-console-build" not in r.body or r.status == 200
