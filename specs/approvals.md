# Approvals of pushed commits

Pushed history is never rewritten, so a commit that is already on the remote cannot gain a `Test-Change-Approved:`
trailer afterwards. When the owner accepts such a commit, it is listed here, and `tools/check_tdd.py` excuses exactly
that commit for exactly that rule:

| Rule | What it checks |
|---|---|
| 1 | every `[green]` commit has an earlier `[red]` commit of the same task |
| 2 | a `[green]` commit does not modify files locked at its parent |
| 3 | `tests.lock` is append-only (no removed entry, no changed hash) |
| 4 | no commit adds a skip, xfail or only marker |

Rule 5 (a locked file differs from its hash at HEAD) and the checks of a commit that is not listed are never excused.
Each row below is read by the tool: the first cell is the commit SHA (7 to 40 hex digits), the second the rule number.
A listed SHA fails for any other rule, an unlisted SHA fails for every rule.

| SHA | Rule | Status | Owner decision | Note |
|---|---|---|---|---|
| `de12c88bcd2d7c9aef32198e5a141945c3d335a9` | 4 | approved | owner decision of 2026-10-12 (all listed test-change requests accepted) | T-011-002: two `pytest.skip` in an environment smoke test; removed again in `0e20c20364b998f0ba4de96591cdbb6e856c5d1e` |
| `7cdd9c54efcefd7160dac05ac4803504535c436d` | 3 | agent-added trailer, reported to the owner | owner decision of 2026-10-12 | T-015-033 red correction; the trailer was written by the agent, not the owner; the commit already passes rule 3 through it |
| `5b71f7a2e7d8b3088ba451a07b1e66e42bb3382c` | 3 | agent-added trailer, reported to the owner | owner decision of 2026-10-12 | T-015-092 red correction, same as above |
| `09c9aba4c7a7210ee23b7328060215fe1b089833` | 3 | agent-added trailer, reported to the owner | owner decision of 2026-10-12 | T-015-030 red correction, same as above |
