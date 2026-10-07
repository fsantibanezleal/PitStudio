# Tasks 003 — Console
Format: `- [ ] T-NNN-xxx [US-NNN-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/003-console/tests.lock <files>`). Python tests use an
in-process ASGI client and a fixture store written by spec 002's fake runs; no GPU anywhere.

## Phase 1 — Setup

- [ ] T-003-001 [US-003-1] (DC-003-01, DC-003-02, DC-003-03, DC-003-04, FR-003-17) schema + generated types: `contracts/console.schema.json` (plan.md D3) through spec 001's generators; dependency check before feature code (`uv add --dev schemathesis httpx` resolves on 3.14 with the locked pytest and Hypothesis; `api/` added to the package search); `tools/gen_openapi.py [--check]` and the committed `api/openapi.json`, with a seeded drift detected — test: tests/contract/test_t_003_001_console_contracts.py

## Phase 2 — US-003-1 (P1) Watch and queue runs locally

- [ ] T-003-010 [US-003-1] (FR-003-01, FR-003-02, FR-003-03, FR-003-04, FR-003-05) start-up: loopback-only sockets, refused bind options, port from the variable or OS-assigned, hostile port values, port in use, no GPU import, no lock, no store write — test: tests/unit/test_t_003_010_startup.py
- [ ] T-003-011 [US-003-1] (FR-003-06, FR-003-07, FR-003-08, FR-003-12) read endpoints: health, recipes (valid and invalid files), queue and job, runs and manifest (409 on an invalid manifest), bodies valid against their schemas — test: tests/contract/test_t_003_011_read_endpoints.py
- [ ] T-003-012 [US-003-1] (FR-003-09, FR-003-11) `POST /jobs` (202, `Location`, job visible in the queue within 1 s, nothing launched in the console process) and cancel (202, 404, 409) — test: tests/contract/test_t_003_012_jobs.py
- [ ] T-003-013 [US-003-1] (FR-003-13) artefact streaming: content type, length, `nosniff`, `Range` 206 and 416, first byte within 2 s — test: tests/contract/test_t_003_013_artefacts.py
- [ ] T-003-014 [US-003-1] (FR-003-15, FR-003-16, P-003-04) event stream: replay, follow within 2 s, telemetry ≤ 1 Hz, keep-alive ≤ 15 s, `Last-Event-ID` (valid and hostile), 9th stream 429, corrupt line → `error` event, disconnect clean-up, completeness and order — test: tests/property/test_t_003_014_event_stream.py
- [ ] T-003-015 [US-003-1] (NFR-003-01, P-003-03) latency p95 ≤ 200 ms on the 100-run / 1,000-job fixture; idempotent reads — test: tests/unit/test_t_003_015_latency_idempotence.py

## Phase 3 — US-003-2 (P1) Hostile traffic

- [ ] T-003-020 [US-003-2] (FR-003-10, P-003-01) hostile `POST /jobs` bodies (NaN, duplicate keys, BOM, oversized with and without `Content-Length`, chunked, wrong content type, inline recipe fields, unknown recipe, stage or profile) and the acceptance-agreement property — test: tests/contract/test_t_003_020_jobs_hostile.py
- [ ] T-003-021 [US-003-2] (FR-003-14, P-003-02) path parameters: patterns, encodings, traversal, NUL, overlong, unknown ids, links outside the store — test: tests/property/test_t_003_021_path_params.py
- [ ] T-003-022 [US-003-2] (FR-003-18, FR-003-19, FR-003-20, FR-003-21, FR-003-22) `Host` check, cross-site `POST` refusal, CORS for `/health` only (exact-origin matching, no credentials, private-network preflight), hostile allowlists, problem bodies and security headers — test: tests/contract/test_t_003_022_request_hygiene.py
- [ ] T-003-023 [US-003-2] (FR-003-23) store or queue unavailable → 503 with `Retry-After`, process stays up — test: tests/unit/test_t_003_023_unavailable_store.py
- [ ] T-003-024 [US-003-2] (NFR-003-02, SC-003-01) Schemathesis over `api/openapi.json`, in-process, ≥ 200 examples per operation, the eight checks of NFR-003-02, 0 failures — test: tests/contract/test_t_003_024_schemathesis.py

## Phase 4 — US-003-3 / US-003-4 (P1) Public-site boundary

- [ ] T-003-030 [US-003-4] (FR-003-24) `tools/check_pages_artifact.py` with seeded violations (marker, `console/` file, `.py` file) and the clean real build; steps in `ci.yml` (web job) and `pages.yml` before upload — test: tests/unit/test_t_003_030_pages_artifact.py
- [ ] T-003-031 [US-003-3] (FR-003-25) every public route, deep link, unknown route, gate on and off, both themes and both languages: 0 loopback or private-network requests of any kind — test: web/e2e/console-optin.spec.ts
- ~~T-003-032~~ retired (integration 2026-10-07): the opt-in control moved to spec 019 (T-019-036)

## Phase 5 — US-003-5 (P3) Console UI

- [ ] T-003-040 [US-003-5] (FR-003-28, FR-003-29, NFR-003-03) `web/console/` entry built by `pnpm build:console` with base `/ui/` and the build marker, served by the console; recipes, queue, runs, manifest viewer, live telemetry chart, artefact preview, cancel and run form; both themes and languages; axe 0 serious or critical — test: web/e2e/console/console-ui.spec.ts
- [ ] T-003-041 [US-003-5] (FR-003-30) UI under failing API calls and injected markup in recipe and manifest strings: messages, no crash, no script execution — test: web/e2e/console/console-hostile.spec.ts

## Phase 6 — Polish and hostile review

- [ ] T-003-090 mutation run on `api/pitstudio_api/` middleware (host, origin, body limit, CORS); record the score (target ≥ `mutation.other_min` 0.60)
- [ ] T-003-091 independent review of the diff against this spec (every FR/P has a locked test naming it; the Pages artifact holds no console code); append tasks for gaps
