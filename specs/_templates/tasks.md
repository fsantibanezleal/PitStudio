# Tasks NNN — <Feature name>
Format: `- [ ] T-NNN-xxx [US-NNN-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/NNN-slug/tests.lock <files>`).

## Phase 1 — Setup
- [ ] T-NNN-001 (DC-NNN-01) contract schema + generated types — test: tests/contract/test_t_nnn_001_schema.py

## Phase 2 — US-NNN-1 (P1)
- [ ] T-NNN-010 [US-NNN-1] (FR-NNN-01, P-NNN-01) acceptance + property tests, then implementation — test: tests/unit/test_t_nnn_010_transform.py
- [ ] T-NNN-011 [US-NNN-1] (FR-NNN-05) reject non-finite input — test: tests/unit/test_t_nnn_011_guards.py

## Phase 3 — Polish and adversarial
- [ ] T-NNN-090 mutation run on the touched core modules; record the score
- [ ] T-NNN-091 independent review of the diff against this spec; append tasks for gaps
