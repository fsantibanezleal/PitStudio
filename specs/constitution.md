# PitStudio — Constitution
Version: 1.0.0 · Ratified: 2026-10-04 · Last amended: 2026-10-04

Invariants every change must respect. Conflicts: this file wins over plans and specs; amending it is a PR that bumps
its version (MAJOR = a principle removed or redefined) and lists the affected specs.

## Core principles (non-negotiable)
1. **Real, not demo.** Real data through the real pipeline, real engines and trained models; synthetic data only when
   honest (physics/domain-grounded, labelled, real format, validated against real data).
2. **Spec before code.** No behaviour without an approved requirement ID (`FR/NFR/SC/P/DC-NNN-xx`, EARS).
3. **Acceptance-test-first.** Every requirement-bearing task starts with committed, failing, locked tests that
   reference its IDs (`[red]`); the implementation (`[green]`) never modifies locked tests.
4. **Independent oracles.** Expected values come from analytical solutions, reference implementations, published
   values or hand calculation — never from running the code under test.
5. **Determinism & explicit tolerances.** Seeds, deterministic algorithms where available, pinned data checksums;
   numerical tolerances (rtol/atol per dtype) are stated and justified in the spec.
6. **Neutral contracts.** Cross-boundary data is JSON Schema 2020-12 under `contracts/`; Python and TypeScript types are
   generated, never hand-written.
7. **Static delivery.** The web app runs on static hosting with no backend; every live computation has a baked
   reference and a fallback tier; browser outputs have parity tests against the Python reference.
8. **Honesty.** Every external number is sourced (DOI/URL); synthetic and precomputed content is labelled as such; the
   access gate states exactly what it protects.
9. **Licence hygiene.** Third-party data is fetched, never redistributed; every dataset and model has a licence record.
10. **Simplicity.** Use frameworks directly; no abstraction without two concrete users; structural and behavioural
    changes in separate commits.

## Quality gates
Thresholds live in `specs/000-foundation/thresholds.yaml` and only ratchet upwards. CI is authoritative
(`tools/trace.py --check`, `tools/check_tdd.py --replay`, `tools/check_repo.py`, tests, web build + E2E).
