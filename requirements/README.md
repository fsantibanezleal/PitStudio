# requirements/

**Status: planned.** Generated pip fallback files for users without uv (`runtime.txt`, `pipeline-cpu.txt`,
`pipeline-cu126.txt`, `pipeline-cu130.txt`), exported from the uv locks. They are added in the build phase together
with a CI job that installs each file and fails on drift from the locks. Until then use `uv sync`.
