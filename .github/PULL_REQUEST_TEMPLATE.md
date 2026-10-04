## Summary
<!-- What and why, in two or three lines. Task id(s) T-NNN-xxx and requirement id(s). -->

## Type
<!-- feat | fix | docs | test | refactor | perf | chore | data -->

## Checklist
- [ ] Spec updated first (or not needed) — requirement IDs referenced
- [ ] Failing tests committed and locked before the implementation (`[red]` → `[green]`)
- [ ] `uv run pytest -m "not gpu"`, `python tools/trace.py --check`, `python tools/check_tdd.py`, `python tools/check_repo.py`
- [ ] Web: `pnpm check && pnpm build && pnpm test:e2e` (both themes, both languages)
- [ ] Docs and CHANGELOG `[Unreleased]` updated
- [ ] No third-party data, no files > 10 MB, licences of new assets recorded
