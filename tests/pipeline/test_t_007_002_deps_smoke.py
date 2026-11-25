# ruff: noqa: E501, PT018
"""T-007-002: dependency validation of spec 007, before any feature code: `highspy` (pipeline), `simpy` and `scipy` (pipeline dev group)
and `networkx` (root dev group) resolve in the lock on Python 3.14 Windows wheels, carry the licences the plan records, and import.

Requirements: none (setup task; plan.md "Technical context", ADR-0011).

Spec: specs/007-haulage-dispatch/tasks.md T-007-002 (the lock must resolve on Python 3.14 Windows wheels; record licences MIT, MIT, BSD-3, BSD-3;
smoke-import each package) and plan.md (highspy -> `pipeline/`; simpy -> the `pipeline/` dev group, test oracle; scipy -> the `pipeline/` dev
group as a direct dependency; networkx -> the root dev group, Dijkstra oracle).

Oracle: the committed lock files (`pipeline/uv.lock`, `uv.lock`, parsed with `tomllib`), the installed distributions' own metadata (licence
text, `importlib.metadata`), and a one-line numerical use of each package whose answer is known by hand (a 2-variable LP, a one-timeout SimPy
clock, the mean of a three-point sample, a 3-node shortest path).
"""

from __future__ import annotations

import importlib
import importlib.metadata as md
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_LOCK = tomllib.loads((ROOT / "pipeline" / "uv.lock").read_text(encoding="utf-8"))
ROOT_LOCK = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))


def locked(lock: dict, name: str) -> dict:
    rows = [p for p in lock["package"] if p["name"] == name]
    assert len(rows) == 1, f"{name} must be locked exactly once"
    return rows[0]


def declared(lock: dict, project: str) -> dict:
    """The project's own lock row (its dependency declarations)."""
    return locked(lock, project)


@pytest.mark.parametrize(
    ("package", "licence"),
    [("highspy", "MIT"), ("simpy", "MIT"), ("scipy", "BSD"), ("networkx", "BSD")],
)
def test_the_package_is_locked_with_a_python_3_14_windows_wheel_and_the_recorded_licence(package, licence):
    row = locked(PIPELINE_LOCK, package)
    wheels = " ".join(w["url"] for w in row.get("wheels", []))
    if package in ("simpy", "networkx"):
        assert "py3-none-any" in wheels  # pure Python: one universal wheel
    else:
        assert "cp314" in wheels and "win_amd64" in wheels, f"{package} has no cp314 win_amd64 wheel in the lock"
    meta = md.metadata(package)
    text = " ".join(
        [meta.get("License-Expression", "") or "", meta.get("License", "") or "", *(meta.get_all("Classifier") or [])]
    )
    assert licence in text, f"{package}: licence {licence} not found in its metadata"


def test_the_pipeline_dev_group_holds_simpy_and_the_lock_resolves_it():
    pipe = declared(PIPELINE_LOCK, "pitstudio-pipeline")
    dev = {d["name"] for d in pipe.get("dev-dependencies", {}).get("dev", [])}
    assert "simpy" in dev
    assert {"highspy", "scipy", "networkx"} <= {d["name"] for d in pipe["dependencies"]}


def test_networkx_is_locked_in_the_root_environment_too():
    assert locked(ROOT_LOCK, "networkx")["version"]


@pytest.mark.parametrize("package", ["highspy", "simpy", "scipy", "networkx"])
def test_every_package_imports(package):
    assert importlib.import_module(package) is not None


def test_each_package_computes_a_known_answer():
    import highspy
    import networkx as nx
    import simpy
    from scipy import stats

    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    inf = highspy.kHighsInf
    h.addVar(0.0, inf)
    h.addVar(0.0, inf)
    h.changeColCost(
        0, -1.0
    )  # minimise -x - y, i.e. maximise x + y, with x + 2y <= 4 and 3x + y <= 6: optimum 2.8 at (1.6, 1.2)
    h.changeColCost(1, -1.0)
    h.addRow(-inf, 4.0, 2, [0, 1], [1.0, 2.0])
    h.addRow(-inf, 6.0, 2, [0, 1], [3.0, 1.0])
    h.run()
    assert h.getInfo().objective_function_value == pytest.approx(-2.8, abs=1e-9)

    env = simpy.Environment()

    def wait_five():
        yield env.timeout(5.0)

    env.process(wait_five())
    env.run()
    assert env.now == 5.0

    assert float(stats.tmean([1.0, 2.0, 6.0])) == 3.0

    g = nx.DiGraph()
    g.add_weighted_edges_from([(1, 2, 1.0), (2, 3, 2.0), (1, 3, 5.0)])
    assert nx.dijkstra_path_length(g, 1, 3) == 3.0


def test_the_interpreter_is_python_3_14():
    assert sys.version_info[:2] == (3, 14)
