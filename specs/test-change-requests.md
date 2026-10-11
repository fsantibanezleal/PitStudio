# Test change requests

When a locked test looks wrong, do not edit it. Add an entry here and stop that task. A locked test changes only with
a spec change and a commit carrying a `Test-Change-Approved: <reason>` trailer.

| Date | Task | Locked test | Why it looks wrong (evidence) | Decision |
|---|---|---|---|---|
| 2026-10-11 | T-012-012 (groups and folds) | `tests/unit/test_t_012_012_groups_folds.py`, `tests/property/test_t_012_012_folds_property.py` (lock: `specs/012-fragmentation/tests.lock`) | Spec 012 changed (FR-012-04, FR-012-05): the Mendeley originals are 80 photographs × 3 crops, so the group key is g(k) = s(((k − 1) mod 240) + 1) with the scene s(k) = ((k − 1) mod 80) + 1, and the nine links mapped to scenes give 72 groups, not 231. Components: {29, 39}, {32, 34, 36, 37, 38, 41, 49}, {59, 60}; the link 189–199 duplicates 29–39 and 192–196, 196–198, 196–201 become 32–36, 36–38, 36–41. The locked tests still hold 231 and the old components. Evidence: DINOv2 ViT-B/14 scan of files 1–240 (170 of 240 nearest neighbours at offset ±80; median cosine 0.920 at offset 80 vs 0.703 over all pairs), spec 012 §7 and the dataset card. | open: needs the owner's `Test-Change-Approved:` trailer; the tests and `tests.lock` are changed separately |
