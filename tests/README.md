# tests/

unit/ property/ metamorphic/ contract/ parity/ pipeline/ gpu/ — each task's tests in their own file(s), locked after the [red] commit.

Root environment run: `uv run python -m pytest -q` runs the whole suite (about 9,000 tests) over 8 pytest-xdist workers (`PITSTUDIO_TEST_WORKERS` changes the count, `-n 0` or any test path keeps one process; tests/conftest.py). A file whose imports need the studio or pipeline environment is listed in tests/envs.yaml and runs there, never here.
