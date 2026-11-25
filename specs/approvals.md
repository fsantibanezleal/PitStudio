# Approval ledger

`tools/check_tdd.py` reads the "Waivers" table below. A listed commit is accepted for exactly the listed rule (1 to 4
of the docstring of `tools/check_tdd.py`) and for no other; an unlisted commit gets no waiver. The ledger exists for
the few commits that are already pushed and cannot carry a `Test-Change-Approved:` trailer: pushed history is never
rewritten. A new commit that changes a locked test carries the trailer instead and needs no entry here.

## Waivers

| Commit | Rule | Decision | Note |
|---|---|---|---|
| de12c88 | 4 | owner 2026-10-12 (all listed test-change requests approved, most robust variant) | Two `pytest.skip` calls in an environment smoke test of T-011-002; removed in 0e20c20, so no skip marker remains at HEAD |
| 44230d1 | 4 | owner 2026-10-12 (all listed test-change requests approved, most robust variant) | The ledger commit itself: the fixture text of its unit test for rule 4 spelled the marker literally in a string; spelled in two parts since the next commit |
| d234a778 | 3 | owner 2026-11-23 (all open test-change requests and waivers, most robust variant) | Own relock of the T-004-097 test file before its push: the commit removes a stray last test of the agent's own unpushed red file; no other file is touched |
| 8270053c | 3 | owner 2026-11-23 (all open test-change requests and waivers, most robust variant) | Own relock of the three own, not yet pushed test files of T-004-097 and T-004-098 after ruff format and lint; no assertion changed |
| bb1d6515 | 3 | owner 2026-11-23 (all open test-change requests and waivers, most robust variant) | Own relock of tests/unit/test_t_009_016_geometry_gate.py by its author before the push (an agreement case compared a result dict that its sibling case extends); defect found before the push |
| 24fcafb8 | 1 | owner 2026-11-23 (all open test-change requests and waivers, most robust variant) | The [red] commits of T-018-098 (17303bf, 288632f) carry five task ids in one subject, which the TASK regex of check_tdd does not read, so no [red] is seen for T-018-098 |
| fcfc2dc1 | 1 | owner 2026-11-23 (all open test-change requests and waivers, most robust variant) | The [red] commit of T-004-099 (f6ceaf2) carries two task ids (T-004-099,T-009-100) in one subject, which the TASK regex does not read, so no [red] is seen for T-004-099 |

## Recorded trailers

Commits whose `Test-Change-Approved:` trailer was written by an agent before the owner approved the change. They are
not waivers (the trailer is what check_tdd accepts); they are listed so the owner can see them. Reported to the owner
on 2026-10-12.

| Commit | Task | Note |
|---|---|---|
| 7cdd9c5 | T-015-033 | agent-added trailer, reported to the owner |
| 5b71f7a | T-015-092 | agent-added trailer, reported to the owner |
| 09c9aba | T-015-030 | agent-added trailer, reported to the owner |
