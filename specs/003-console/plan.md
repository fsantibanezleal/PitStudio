# Plan 003 — Console
Spec: ./spec.md

## Summary

A FastAPI app (`api/pitstudio_api/`, root extra `api`) started by `python -m pitstudio_api`: binding and port rules at
start-up (FR-003-01…05), read endpoints over the store through the runner's read functions and a single write path
through the runner's queue API (FR-003-06…13), path and body hygiene (FR-003-10, -14, -18, -19, -22, -23), an SSE
stream that tails `events.jsonl` and `telemetry.jsonl` (FR-003-15, -16), CORS for `GET /health` only (FR-003-20, -21),
an OpenAPI document generated from `contracts/console.schema.json` and drift-checked (FR-003-17). On the web side: a
Pages-artifact check (FR-003-24), the public-site quiet-by-default E2E suite (FR-003-25) and the separate console UI
entry (FR-003-28…30). The opt-in control that calls `GET /health` is spec 019's (FR-019-44, FR-019-45).

## Technical context

Runtime: Python 3.14 (root `.venv`, extra `api`: FastAPI 0.142.2, uvicorn 0.54.0, Starlette 1.7.0; extra `runner` for
the queue API) · spec 001 `pitstudio.contracts` (loaders, validator, generated models) and spec 002
`pitstudio.runner.queue` · tests: pytest 9.1.1, Hypothesis 6.168.3, Schemathesis 4.29.4 and httpx (added to the `dev`
group in T-003-001 after a resolution check on 3.14), psutil 7.2.2 · web: Node 24, React Router 8, Vite 8, Vitest 5,
Playwright 1.63 with `@axe-core/playwright` (web lock) · target: the studio machine (loopback only); never Pages.

## Constitution check

| Principle | Pass? | Note / justification |
|---|---|---|
| 1. Real, not demo | yes | the console reads the real store and calls the real runner queue; E2E fixtures are a real store written by fake runs of spec 002 |
| 2. Spec before code | yes | endpoints, codes, schemas, SSE and CORS fixed in D1–D5 |
| 3. Acceptance-test-first | yes | tasks.md pairs; Schemathesis and E2E suites are `[red]` before the app exists |
| 4. Independent oracles | yes | the OpenAPI document and JSON Schemas drive Schemathesis (reference implementation); Python `jsonschema` validates bodies; RFC 9110 (status, `Range`), RFC 9457 (problem details) and the Fetch standard (CORS) give expected headers; psutil (reference) lists listening sockets; Playwright's request log is the oracle for "no request" |
| 5. Determinism & explicit tolerances | yes | statuses and bodies exact; timing limits are upper bounds (2 s, 200 ms, 15 s) measured with a monotonic clock |
| 6. Neutral contracts | yes | DC-003-01…04; response models generated from `contracts/console.schema.json`; OpenAPI committed and drift-checked |
| 7. Static delivery | yes | the console is never in the Pages artifact (FR-003-24); the public site works with the console absent |
| 8. Honesty | yes | `/health` carries no metric and is the only cross-origin-readable endpoint; the opt-in control's labels are spec 019's (FR-019-44) |
| 9. Licence hygiene | yes | local-only metrics are shown only on the machine that measured them; `/health` carries no metric |
| 10. Simplicity | yes | no authentication layer, no WebSockets (SSE is enough), no server-side session; every action is one runner call |

## Design

![C4 containers: the studio console on 127.0.0.1](../../docs/assets/diagrams/c4-containers.svg)

| Component | Path | Requirements |
|---|---|---|
| Entry point and binding checks | `api/pitstudio_api/__main__.py` | FR-003-01…04, -21 |
| App factory, middleware (host check, origin check, body limit, CORS, security headers, problem handler) | `api/pitstudio_api/app.py` | FR-003-10, -18…20, -22, -23 |
| Endpoints | `api/pitstudio_api/routes.py` | FR-003-06…14 |
| Event stream | `api/pitstudio_api/sse.py` | FR-003-15, -16 |
| Read-only store access (no GPU, no locks) | `api/pitstudio_api/store.py` | FR-003-05, -12, -13 |
| OpenAPI dump and drift check | `tools/gen_openapi.py [--check]` → `api/openapi.json` | FR-003-17 |
| Pages-artifact check | `tools/check_pages_artifact.py` (in `ci.yml` web job and `pages.yml` before upload) | FR-003-24 |
| Console UI entry | `web/console/` (`pnpm build:console`, `web/playwright.console.config.ts`) | FR-003-28…30 |
| Packaging | root `pyproject.toml`: `api/` added to the setuptools package search | FR-003-01 |

### D1. Endpoints

| Method and path | Parameters (pattern) | Success | Body |
|---|---|---|---|
| `GET /health` | — | 200 | `health` |
| `GET /recipes` | — | 200 | `recipe_list` |
| `GET /recipes/{recipe_id}` | `slug` | 200 | the validated recipe (spec 001) |
| `GET /queue` | — | 200 | `job_list` |
| `POST /jobs` | body `job_request` (spec 001), ≤ 65,536 B, `application/json` | 202 + `Location` | `job_created` |
| `GET /jobs/{job_id}` | `^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$` | 200 | `job` |
| `POST /jobs/{job_id}/cancel` | as above | 202 | `job` |
| `GET /runs` | — | 200 | `run_list` |
| `GET /runs/{run_id}` | `run_id` | 200 | run manifest (spec 001, `kind: run`) |
| `GET /runs/{run_id}/artefacts/{artefact_id}` | `run_id`, `artefact_id`; optional `Range` | 200 / 206 | bytes |
| `GET /runs/{run_id}/events` | `run_id`; optional `Last-Event-ID` | 200 | `text/event-stream` (D4) |
| `GET /openapi.json` | — | 200 | OpenAPI 3.1 |
| `GET /ui/…` | static files of `web/build/console/` | 200 | HTML, JS, CSS |

### D2. Status codes

| Code | When |
|---|---|
| 200 / 202 / 206 | success (read / accepted / partial content) |
| 400 | malformed JSON body; `Host` header not allowed |
| 403 | cross-site `POST` (`Origin`, `Sec-Fetch-Site`); CORS preflight outside the allowlist rule |
| 404 | well-formed but unknown id; object outside the store |
| 405 | method not defined for the path |
| 409 | cancel of a terminal job; invalid local manifest |
| 413 | body over 65,536 bytes |
| 415 | `POST` content type other than `application/json` |
| 416 | unsatisfiable `Range` |
| 422 | schema violation; unknown recipe, stage or profile; path parameter or `Last-Event-ID` breaking its pattern |
| 429 | 9th concurrent event stream (`Retry-After: 5`) |
| 503 | store or queue unavailable (`Retry-After: 5`) — never caused by request content |

### D3. Response schemas (`contracts/console.schema.json`)

| `$defs` | Fields |
|---|---|
| `health` | `status` (const `ok`), `console_version` (`semver`), `runner_version` (`semver`), `contracts` (map schema stem → `schema_version` or `$id`, ≤ 16 entries) |
| `recipe_summary` | `id`, `case`, `path` (`relpath`), `sha256`, `stages` (0–64), `valid` (boolean), `errors` (≤ 20 of `{pointer, keyword, message ≤ 300}`) |
| `recipe_list` | `recipes` (≤ 256 of `recipe_summary`) |
| `job` | `job_id`, `recipe`, `state` (spec 002 job states), `run_id` or `null`, `created` (`utc_timestamp`), `stage` (`{id, variant?}` or `null`), `shards` (`{done, total}` or `null`), `exit_code` or `null`, `reason` (≤ 300) or `null` |
| `job_list` | `jobs` (≤ 1,000 of `job`) |
| `job_created` | `job_id`, `location` (`^/jobs/[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$`) |
| `run_summary` | `run_id`, `recipe`, `created`, `profile`, `state`, `stages` (1–64), `published` (boolean), `valid` (boolean) |
| `run_list` | `runs` (≤ 1,000 of `run_summary`) |
| `problem` | `type` (string ≤ 200), `title` (≤ 100), `status` (400–599), `detail` (≤ 300), `errors` (≤ 50 of `{pointer, keyword, message}`) |

### D4. Event-stream format

```text
id: <seq>
event: event | telemetry | error
data: <one JSON object: an events.schema.json event, a telemetry_sample, or {"line": n, "message": "…"}>

```

Replay first (all lines with `seq` > `Last-Event-ID`), then follow the files with a poll interval ≤ 1 s; telemetry is
reduced to the latest sample per wall-clock second; FastAPI's keep-alive ping at most every 15 s.

### D5. Cross-origin and security headers

| Request | Response headers |
|---|---|
| `GET /health` with `Origin` in the allowlist | `Access-Control-Allow-Origin: <origin>`, `Vary: Origin` |
| `OPTIONS /health` with allowlisted `Origin`, `Access-Control-Request-Method: GET` | 204, `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods: GET`, `Access-Control-Max-Age: 600`, `Access-Control-Allow-Private-Network: true` (when requested) |
| any other preflight | 403, no CORS header |
| any other cross-origin request | no CORS header (the browser blocks reading) |
| every response | `X-Content-Type-Options: nosniff`; `Cache-Control: no-store` except artefacts and `/ui/` assets |
| HTML responses | `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'` |

Allowlist: `PITSTUDIO_CONSOLE_ALLOW_ORIGINS`, comma-separated exact origins; default `https://fsantibanezleal.github.io`;
matching is exact string equality (so `https://fsantibanezleal.github.io.example.com` never matches).

### `thresholds.yaml` keys used by this spec

```yaml
console:
  body_bytes_max: 65536        # FR-003-10
  response_ms_max: 2000        # FR-003-10, NFR-003-02 max_response_time
  health_ms_max: 200           # FR-003-06
  p95_ms_max: 200              # NFR-003-01
  sse_delivery_s_max: 2        # FR-003-15
  sse_keepalive_s_max: 15      # FR-003-15
  sse_streams_max: 8           # FR-003-16
  optin_timeout_s: 3           # FR-019-44 (the opt-in control, spec 019)
```

## Test strategy

| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-003-01 | integration | psutil `Process(pid).net_connections()` (reference) lists only 127.0.0.1 listeners; a connection to the host's non-loopback address is refused | pytest |
| FR-003-02, FR-003-04, FR-003-21 | unit (hostile) | table of hostile options and variables → expected exit code and no listening socket | pytest |
| FR-003-03 | unit | unset port → printed port equals the bound one (socket inspection) | pytest |
| FR-003-05 | unit | import blockers for NVML and `filelock` GPU-lock use; spy on the runner queue API; store hash unchanged after the read-only suite | pytest |
| FR-003-06…09, FR-003-11…13 | contract | Python `jsonschema` against `contracts/console.schema.json` and `manifest.schema.json`; expected statuses from D1/D2; fixture store written by spec 002's fake runs; `Range` semantics per RFC 9110 §14 | pytest + httpx ASGI transport |
| FR-003-10, P-003-01 | contract (hostile) + property | Schemathesis (`negative_data_rejection`, `positive_data_acceptance`) plus hand-built hostile bodies (NaN, duplicate keys, BOM, 65,537 B with and without `Content-Length`, chunked, `text/plain`, inline recipe fields); Python `jsonschema` as the reference acceptor | Schemathesis, Hypothesis |
| FR-003-14, P-003-02 | contract (hostile) + property | Hypothesis strings with `%2F`, `%5C`, `%2e%2e`, `%00`, overlong and unicode forms; a fixture link pointing outside the store; expected 422/404 | Hypothesis |
| FR-003-15, FR-003-16, P-003-04 | integration (hostile) | a writer appending events with recorded timestamps; client-side arrival times (≤ 2 s); expected id sequences by hand; 9 concurrent clients; disconnect detected via the server's task count | pytest + httpx streaming |
| FR-003-17 | contract + CI | regenerated OpenAPI byte-compared with `api/openapi.json` | pytest |
| FR-003-18, FR-003-19, FR-003-20, FR-003-22 | contract (hostile) | expected headers and statuses from D2/D5, RFC 9457 field rules, Fetch-standard CORS semantics; hand-built `Host`, `Origin`, `Sec-Fetch-Site` and preflight requests | pytest |
| FR-003-23 | integration (hostile) | fixture with a missing store, a locked and a corrupt `queue.db` → 503 and the process still answering `/health` | pytest |
| FR-003-24 | CI + unit (hostile) | fixture build folders seeded with the marker, a `console/` file and a `.py` file → exit 1 naming each; the real build → exit 0 | pytest |
| FR-003-25 | E2E (hostile) | Playwright request log (`page.on("request")`, `websocket`), each URL's host classified against the address ranges of FR-003-25 | Playwright (`web/e2e/console-optin.spec.ts`) |
| FR-003-28…30 | E2E (console) | Playwright against the console with the fixture store; injected-markup fixtures; error stubs | Playwright (`web/e2e/console/*.spec.ts`) |
| P-003-03 | property | repeated reads byte-compared | Hypothesis |
| NFR-003-01 | unit | `time.perf_counter` p95 over 200 requests per endpoint | pytest |
| NFR-003-02, SC-003-01 | contract | Schemathesis in-process over `api/openapi.json` with the listed checks | Schemathesis |
| NFR-003-03 | E2E (console) | axe-core (reference implementation) | Playwright + `@axe-core/playwright` |

## Risks and complexity tracking

| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Own body-size middleware | Starlette reads chunked bodies without a size limit; a hostile client could stream gigabytes into memory | relying on `Content-Length` misses chunked bodies |
| `Host` and `Origin` checks although bound to loopback | DNS rebinding lets a public page reach 127.0.0.1 under its own origin; simple `POST`s are sent cross-site without a preflight | loopback binding alone does not stop either |
| CORS for `/health` only | the opt-in control needs to read one response; nothing else should be readable from a public origin | a global CORS middleware would expose manifests and artefacts to any allowlisted page |
| Committed `api/openapi.json` | Schemathesis and the console UI need a stable contract; drift shows up in review | generating it only at test time hides contract changes |

Other risks: Schemathesis or its dependencies may not resolve on Python 3.14 with the locked pytest and Hypothesis — the
resolution check in T-003-001 comes before feature code, and if it fails the hostile suite falls back to Hypothesis
strategies over the same OpenAPI document (recorded as a spec change, not silently); browsers change their
local-network rules — the E2E suite pins Chromium through the web lock and checks only our behaviour (no request before
the click), which holds under any rule.
