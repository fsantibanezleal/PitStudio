@AGENTS.md
@specs/constitution.md

## Claude Code specifics
- Locked tests, goldens and `specs/000-foundation/thresholds.yaml` are protected by a PreToolUse hook
  (`tools/guard_locked_tests.py`, see `.claude/settings.json`). A denial means: stop, record the problem in
  `specs/test-change-requests.md`, do not work around it.
- Use sub-agents for reading-heavy research and for independent review; never approve your own work.
- When compacting, preserve: the current task id, its requirement IDs, failing test names, and the next command to run.
