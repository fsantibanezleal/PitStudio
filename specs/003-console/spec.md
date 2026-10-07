# Spec 003 — Console
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

The runner's command line always works, but the studio's outputs are media: renders, videos, point clouds and live GPU
timelines. The console is the studio's own window: a FastAPI app in `api/` (package `pitstudio_api`, root extra `api`
with FastAPI 0.142.2 and uvicorn 0.54.0) bound to 127.0.0.1 only, with `/health`, recipes, the queue, runs, artefacts
and a server-sent-events stream of run events and telemetry, plus a separate web entry `web/console/` that reuses the
site's shell. `POST /jobs` accepts only a job request valid against `contracts/recipe.schema.json#/$defs/job_request`
that names a committed recipe, so hostile input gets a 4xx — never a 5xx, never a hang (Schemathesis). The console is
never part of the Pages artifact (CI check), and the public site never contacts it unless the visitor presses the opt-in
"connect to my local studio" control (FR-000-11). Every console action is a runner API call (spec 002-runner).

Who benefits: the maintainer (watch and queue runs with media next to them), visitors (no surprise local-network
prompts), reviewers (an API whose contract is tested by generated hostile requests).

Out of scope: authentication (single-user local tool; loopback is the boundary), remote access other than SSH port
forwarding, the Kit WebRTC "studio link" (a separate localhost tool), the opt-in "connect to my local studio" control
itself — its placement, port field, request and labels (spec 019-web-studio, FR-019-44, FR-019-45; this spec owns the
endpoint it calls, its CORS rules and the public-site loopback rule: FR-003-06, FR-003-20, FR-003-21, FR-003-25) — and
any GPU work (the console starts none).

## 2. User stories

### US-003-1 (P1) Watch and queue runs locally
As the maintainer, I want to see recipes, the queue, runs, manifests, artefacts and live telemetry in a browser on the
studio machine, and to queue or cancel a job, so that I can operate the studio with its media in view. Independent
test: with a fixture store, every read endpoint returns schema-valid data, a valid `POST /jobs` appears in the runner
queue within 1 s, and the SSE stream delivers a newly appended event within 2 s.

### US-003-2 (P1) Hostile traffic cannot break or misuse the console
As the maintainer, I want malformed, oversized, cross-site, rebinding and path-traversal requests rejected with the
right 4xx, so that no web page, script or typo can crash the console or start unintended work. Independent test:
Schemathesis over the OpenAPI document reports 0 failures, and the hand-written hostile suite gets the expected status
for every case.

### US-003-3 (P1) The public site stays quiet
As a visitor of the public site, I want it never to contact my machine unless I press "connect to my local studio",
and then to make exactly one health request, so that I see no local-network prompt by surprise. Independent test:
Playwright records 0 loopback or private-network requests across every public route, and exactly one after the click.

### US-003-4 (P1) The console never ships in Pages
As a release reviewer, I want CI to fail if any console code reaches the Pages artifact, so that the static site stays
static. Independent test: the check passes on the real build and fails on each seeded violation.

### US-003-5 (P3) A console UI that reuses the shell
As the maintainer, I want the console UI in the same theme and languages as the site, so that viewers and charts are
shared. Independent test: Playwright drives the UI against a fixture console in both themes and both languages with
0 serious accessibility findings.

Story index (for traceability):

| ID | Priority | Story |
|---|---|---|
| US-003-1 | P1 | Watch and queue runs locally |
| US-003-2 | P1 | Hostile traffic cannot break or misuse the console |
| US-003-3 | P1 | The public site stays quiet |
| US-003-4 | P1 | The console never ships in Pages |
| US-003-5 | P3 | A console UI that reuses the shell |

## 3. Functional requirements (EARS)

Tables "plan.md D1…D5" (endpoints, status codes, response schemas, SSE format, CORS) are normative parts of the
requirements that cite them.

### 3.1 Process and binding

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-003-01 | Ubiquitous | `uv run --extra api python -m pitstudio_api` shall serve the app with uvicorn on the IPv4 loopback address 127.0.0.1 only — every listening socket of the process has local address 127.0.0.1 — and print `http://127.0.0.1:<port>/ui/`. | integration (socket inspection) |
| FR-003-02 | Unwanted | If any other bind address is requested (`--host`, `PITSTUDIO_CONSOLE_HOST`, a uvicorn option), then the console shall exit 2 naming the option and shall open no socket. | unit (hostile) |
| FR-003-03 | Ubiquitous | The console shall read its port from `PITSTUDIO_CONSOLE_PORT` (integer 1024–65535) and, when the variable is unset, bind an OS-assigned free port and print it; no port number is hard-coded. | unit |
| FR-003-04 | Unwanted | If `PITSTUDIO_CONSOLE_PORT` is not a decimal integer in 1024–65535 (e.g. `abc`, `80`, `65536`, `8765.0`, `-1`, empty), then the console shall exit 2 naming the variable; and if the port is in use, it shall exit 3. | unit (hostile) |
| FR-003-05 | Ubiquitous | The console shall never import an NVML binding, take a GPU lock, start a stage process or write to the store, except through the runner's queue API (`enqueue`, `cancel`; FR-002-39). | unit (import and call spies) |

### 3.2 Endpoints

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-003-06 | Event | When `GET /health` is received, the console shall answer 200 within 200 ms with a body valid against `contracts/console.schema.json#/$defs/health` (`status: ok`, console and runner versions, contract versions) containing no path, host or user name. | contract |
| FR-003-07 | Event | When `GET /recipes` or `GET /recipes/{recipe_id}` is received, the console shall list every `.yaml` under `studio/recipes/cases/` and `studio/recipes/_bench/` with its id, case, repository-relative path, SHA-256, stage count and validity (invalid files listed with ≤ 20 errors, never a 5xx), or return the validated recipe. | contract |
| FR-003-08 | Event | When `GET /queue` or `GET /jobs/{job_id}` is received, the console shall return the runner's job records (plan.md D3) for all jobs or the named one. | contract |
| FR-003-09 | Event | When `POST /jobs` carries a valid job request naming a committed recipe, existing stage keys and an existing profile, the console shall call the runner's `enqueue`, answer 202 with `Location: /jobs/<job_id>` and a `job_created` body, and the job shall appear in `GET /queue` within 1 s; the console process shall launch nothing itself. | integration |
| FR-003-10 | Unwanted | If a `POST /jobs` body is malformed JSON (including `NaN`, duplicate keys, a byte-order mark), exceeds 65,536 bytes (with or without `Content-Length`, including chunked bodies), has a content type other than `application/json`, fails `$defs/job_request` (unknown field — including an inline recipe, `entry`, `env` or `params` — wrong type, pattern, more than 64 stages), or names an unknown recipe, stage or profile, then the console shall answer 400, 413, 415 or 422 as in plan.md D2 within 2 s, enqueue nothing and never answer 5xx. | contract (hostile, Schemathesis) |
| FR-003-11 | Event | When `POST /jobs/{job_id}/cancel` is received, the console shall call the runner's `cancel` and answer 202 for a queued or running job, 404 for an unknown well-formed id and 409 for a job in a terminal state. | contract |
| FR-003-12 | Event | When `GET /runs` or `GET /runs/{run_id}` is received, the console shall return run summaries, or the run's local manifest after validating it against `contracts/manifest.schema.json`, and shall answer 409 with a problem body when that manifest is invalid. | contract |
| FR-003-13 | Event | When `GET /runs/{run_id}/artefacts/{artefact_id}` names an artefact or stage output listed in that run's manifest, the console shall stream the stored object with `Content-Type` from its `media_type` (else `application/octet-stream`), `Content-Length`, `X-Content-Type-Options: nosniff`, the first byte within 2 s, and answer `Range: bytes=a-b` with 206 and `Content-Range`, or 416 for an unsatisfiable range. | contract |
| FR-003-14 | Unwanted | If a path parameter does not match its pattern (spec 001 data-model §1.3: `slug`, `run_id`, `artefact_id`, job id), contains an encoded `/`, `\`, `..`, NUL or exceeds its length, then the console shall answer 422; if it is well formed but unknown, 404; and if the object it resolves to lies outside `$PITSTUDIO_STORE/cas/` (for example through a link), 404 — never serving a file outside the store and never answering 5xx. | contract (hostile) |
| FR-003-15 | Event | When `GET /runs/{run_id}/events` is received, the console shall answer `text/event-stream` with `Cache-Control: no-cache`, replay the run's `events.jsonl` as SSE events with `id:` equal to `seq`, then follow the file and deliver each appended event within 2 s, send telemetry samples as `telemetry` events at ≤ 1 Hz, send a keep-alive at least every 15 s, and on `Last-Event-ID: k` send only events with `seq` > k (plan.md D4). | integration |
| FR-003-16 | Unwanted | If `Last-Event-ID` is not a decimal integer in 0…2⁶³−1, then the console shall answer 422; if 8 event streams are already open, it shall answer 429 with `Retry-After`; if a line of `events.jsonl` is invalid, it shall send one `error` event naming the line number and continue; and when the client disconnects, the stream task shall end within 2 s. | integration (hostile) |
| FR-003-17 | Ubiquitous | `GET /openapi.json` shall describe every endpoint with response models generated from `contracts/console.schema.json` (spec 001 generators), and the committed `api/openapi.json` shall equal the generated document (CI drift check). | contract + CI |

### 3.3 Request hygiene

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-003-18 | Unwanted | If the `Host` header is not exactly `127.0.0.1:<port>` or `localhost:<port>` (host part case-insensitive), then the console shall answer 400 to any method and path (DNS-rebinding defence). | contract (hostile) |
| FR-003-19 | Unwanted | If a `POST` request carries an `Origin` header other than `http://127.0.0.1:<port>` or `http://localhost:<port>` (including `null`), or `Sec-Fetch-Site: cross-site`, then the console shall answer 403 and enqueue or cancel nothing (cross-site request defence). | contract (hostile) |
| FR-003-20 | Optional | Where a request to `GET /health`, or its `OPTIONS` preflight for method `GET`, comes from an origin in the allowlist (`PITSTUDIO_CONSOLE_ALLOW_ORIGINS`, default `https://fsantibanezleal.github.io`), the console shall add `Access-Control-Allow-Origin: <that exact origin>` and `Vary: Origin`, never `Access-Control-Allow-Credentials`, and `Access-Control-Allow-Private-Network: true` on the preflight; every other path, method or origin shall get no CORS header, and its preflight 403 (plan.md D5). | contract (hostile) |
| FR-003-21 | Unwanted | If an allowlist entry is `*`, carries a path, query, user information or a non-`https` scheme (except `http://127.0.0.1:<port>` and `http://localhost:<port>`), then the console shall exit 2 at start naming the entry. | unit (hostile) |
| FR-003-22 | Ubiquitous | Every error response shall be `application/problem+json` (RFC 9457) with `status` equal to the HTTP status and `detail` ≤ 300 characters, without a stack trace or an absolute path; every response shall carry `X-Content-Type-Options: nosniff`, and every HTML response `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'`. | contract |
| FR-003-23 | Unwanted | If the store or the queue is unavailable (missing folder, locked or corrupt `queue.db`), then the console shall answer 503 with a problem body and `Retry-After: 5`, and shall stay up; hostile input shall never produce a 5xx. | integration (hostile) |

### 3.4 Public-site boundary

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-003-24 | Unwanted | If any file of the Pages artifact (`web/build/client/`) contains the console build marker `pitstudio-console-build`, lies under a `console/` folder, or is a Python file, then `tools/check_pages_artifact.py` (run in `ci.yml` and `pages.yml` before upload) shall exit 1 naming the file. | CI + unit (hostile) |
| FR-003-25 | Unwanted | If the public site is loaded on any route (every prerendered route, a deep link, an unknown route, with the gate on and off, both themes, both languages), then it shall issue 0 requests of any kind (fetch, XHR, EventSource, WebSocket, image, script, prefetch) to a loopback or private address (127.0.0.0/8, `localhost`, ::1, 0.0.0.0, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, fc00::/7, fe80::/10) (refines FR-000-11). | E2E (hostile) |
| ~~FR-003-26~~ | — | Retired: the opt-in control's request and labels. | superseded by FR-019-44 (integration 2026-10-07) |
| ~~FR-003-27~~ | — | Retired: the opt-in control's port-field validation. | superseded by FR-019-45 (integration 2026-10-07) |

### 3.5 Console UI

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-003-28 | Ubiquitous | The console UI shall be a separate web entry `web/console/`, built by `pnpm build:console` into `web/build/console/` with base `/ui/`, embedding the marker `pitstudio-console-build`, served by the console at `/ui/` with same-origin requests only, and reusing the shell's theme and i18n (English default, Spanish). | E2E (console) |
| FR-003-29 | Event | When the maintainer opens the console UI, it shall show recipes, the queue, runs with their manifests, a live telemetry chart fed by the event stream, artefact previews from the artefact endpoint, a cancel action and a run form that posts a job request — each action being one API call. | E2E (console) |
| FR-003-30 | Unwanted | If an API call fails (4xx, 5xx, network error, invalid body) or a manifest or recipe string contains markup (e.g. `<img src=x onerror=…>`), then the UI shall show an error message without crashing and render the string as text, executing no injected script. | E2E (console, hostile) |

## 4. Correctness properties

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-003-01 | Job-request agreement: `POST /jobs` answers 202 if and only if the body validates against `$defs/job_request` with Python `jsonschema` and names a committed recipe, its stage keys and an existing profile; every other body gets 400, 413, 415 or 422. | Schemathesis + Hypothesis bodies around the schema | exact |
| P-003-02 | Path-parameter closure: for every string used as a path parameter, the answer is 200 or 206 only for ids listed in the fixture store, never streams bytes of a file outside `$PITSTUDIO_STORE/cas/`, and is never 5xx. | Hypothesis strings (unicode, encodings, traversal fragments) | exact |
| P-003-03 | Idempotent reads: repeating any non-streaming `GET` on an unchanged store returns the same status and byte-identical body. | every read endpoint × fixture ids | exact |
| P-003-04 | Event-stream completeness: for N appended events and any `Last-Event-ID` k (0 ≤ k ≤ N), the client receives exactly the events k+1 … N, in `seq` order, without duplicates. | N ∈ 0…500, random k, append timing | exact |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-003-01 | p95 latency of non-streaming endpoints on a fixture store with 100 runs and 1,000 jobs | ≤ 200 ms | pytest timer over 200 requests per endpoint |
| NFR-003-02 | Schemathesis run over `api/openapi.json` with checks `not_a_server_error`, `status_code_conformance`, `content_type_conformance`, `response_schema_conformance`, `negative_data_rejection`, `positive_data_acceptance`, `unsupported_method`, `max_response_time` (2,000 ms) | 0 failures with ≥ 200 examples per operation (`property_tests.ci_examples_per_test`) | Schemathesis (pytest, in-process ASGI) |
| NFR-003-03 | Console UI accessibility in both themes | axe: 0 serious or critical | Playwright + axe |
| SC-003-01 | On every push after the build phase | Pages-artifact check passes; Schemathesis 0 failures; public-site loopback E2E 0 requests | CI history |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-003-01 | console response bodies: `health`, `recipe_summary`, `recipe_list`, `job`, `job_list`, `job_created`, `run_summary`, `run_list`, `problem` | `contracts/console.schema.json` | console → console UI, public opt-in control (`health` only), Schemathesis |
| DC-003-02 | the OpenAPI document `api/openapi.json` (generated, committed, drift-checked) | OpenAPI 3.1 generated by FastAPI from DC-003-01 | console → Schemathesis, console UI |
| DC-003-03 | job requests (`POST /jobs` body) | `contracts/recipe.schema.json#/$defs/job_request` (spec 001, DC-001-02) | console UI → console → runner |
| DC-003-04 | SSE payloads | `contracts/events.schema.json` (spec 002, DC-002-03) | runner → console → console UI |

## 7. Edge cases and assumptions

- **Loopback is the security boundary.** There is no authentication. On a multi-user Linux host, other local users can
  reach 127.0.0.1; the console is documented as single-user, and the CLI remains the tool for shared hosts.
- **Browsers and the opt-in request.** Chrome's Local Network Access gates public-to-loopback requests behind a user
  permission rather than server headers; an HTTPS page may then reach `http://127.0.0.1` (Chrome for Developers, "Local
  Network Access"). The preflight header of FR-003-20 keeps browsers that still apply the older Private Network Access
  preflight working; it grants nothing beyond `GET /health`.
- **Simple-request CSRF.** CORS does not stop a cross-site page from *sending* a simple `POST`; FR-003-19 (Origin) and
  FR-003-10 (JSON content type only, which forces a preflight from browsers) stop it from having an effect.
- **SSE support.** FastAPI provides `EventSourceResponse` with keep-alive pings every 15 s and `Cache-Control:
  no-cache` since 0.135.0 (FastAPI documentation, "Server-Sent Events"); the locked 0.142.2 is newer.
- **Schemathesis.** Version 4.29.4 (MIT) declares Python 3.10–3.14 and runs in-process against an ASGI app
  (`schemathesis.openapi.from_asgi`); its built-in checks include those of NFR-003-02 (Schemathesis documentation,
  "Checks"). It and `httpx` (for FastAPI's test client) are added to the `dev` group after a resolution check (T-003-001).
- **Local-only metrics.** The console shows local-only performance data on the machine that measured it; that is not
  publication. The opt-in public-site request can read only `/health`, which carries no metric.
- **No UNVERIFIED constants.** All limits here (65,536 B, 2 s, 15 s, 8 streams, 3 s) are design values stated by this
  spec and proposed for `thresholds.yaml` (plan.md).

## 8. Clarifications log

- Resolved — **location and launch.** An earlier design note placed the console in the core package with an extra named
  `console`; plan §9/§12, docs DEC-0003 and `api/README.md` place it in `api/` with the root `api` extra. The plan wins:
  package `pitstudio_api` in `api/`, launched with `uv run --extra api python -m pitstudio_api` (docs `reference/cli.md`
  said the launch command would be fixed here).
- Resolved — **port.** Docs say "port from the environment, never hard-coded". `PITSTUDIO_CONSOLE_PORT`; when unset, an
  OS-assigned port, printed at start (FR-003-03). The opt-in control therefore asks for the port (now spec 019,
  FR-019-44, FR-019-45).
- Resolved — **what "validated against the recipe schema" means.** `POST /jobs` takes a job request
  (`recipe.schema.json#/$defs/job_request`, spec 001) naming a committed recipe, never an inline recipe: accepting
  recipe documents from a browser would let any page choose the module a stage launches.
- Resolved — **cross-origin scope.** Only `GET /health` is readable from allowlisted public origins; everything else is
  same-origin (FR-003-20). Docs only require that the public site probe after a click.
- Resolved — **status for invalid local manifests.** 409 with a problem body, so that no server-side data problem shows up
  as a 5xx in the hostile suite (FR-003-12); 503 is reserved for an unavailable store or queue (FR-003-23).
- Resolved — **console UI path.** `web/console/` (docs DEC-0003), served at `/ui/` by the console.
- Integration 2026-10-07: the opt-in "connect to my local studio" control has one owner per side: its UI (placement,
  port field, the one `GET /health` per press, labels) is spec 019-web-studio (FR-019-44, FR-019-45, task T-019-036);
  this spec keeps the endpoint (FR-003-06), CORS (FR-003-20, FR-003-21) and the public-site loopback rule
  (FR-003-25). FR-003-26 and FR-003-27 are struck; task T-003-032 is retired.
- Integration 2026-10-07: every `thresholds.yaml` key this spec proposes is marked "proposed key, pending maintainer
  approval" and compiled with the other specs' proposals for the maintainer; lane-gate keys are consolidated as
  `lane_gate.*` and budget keys as `budgets.*`.

## 9. Changes (only for features that modify earlier behaviour)
### ADDED Requirements
- FR-003-01 … FR-003-30 (FR-003-26 and FR-003-27 retired), P-003-01 … P-003-04, NFR-003-01 … NFR-003-03, SC-003-01, DC-003-01 … DC-003-04.
### MODIFIED Requirements
- (none)
### REMOVED Requirements
- (none)
