"""T-012-012 - P-012-08, FR-012-04, FR-012-05: fold partition invariants for any seed; union-find groups.

Oracles (independent of the code under test):
- invariants of P-012-08 checked directly on the returned lists (partition of {1, ..., 240}, one role per group);
- reference implementation: scikit-learn `GroupKFold(n_splits=5, shuffle=True, random_state=seed)` called here;
- reference connected components: a breadth-first search over the link graph written in this file (canonical group
  id = smallest original of the component, as pinned in tests/unit/test_t_012_012_groups_folds.py).

Expected public API: `pitstudio_pipeline.fragmentation.splits` as documented in
tests/unit/test_t_012_012_groups_folds.py (`group_key`, `build_groups`, `build_folds`).
Example count: `property_tests.ci_examples_per_test` of specs/000-foundation/thresholds.yaml.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.fragmentation import splits  # noqa: E402

EXAMPLES = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "property_tests"
]["ci_examples_per_test"]
LINKS = [(29, 39), (34, 41), (36, 37), (41, 49), (59, 60), (189, 199), (192, 196), (196, 198), (196, 201)]
ORIGINALS = set(range(1, 241))


def _bfs_groups(links: list[tuple[int, int]]) -> dict[int, int]:
    adj: dict[int, set[int]] = {o: set() for o in ORIGINALS}
    for a, b in links:
        adj[a].add(b)
        adj[b].add(a)
    label: dict[int, int] = {}
    for start in sorted(ORIGINALS):
        if start in label:
            continue
        comp, queue = [start], deque([start])
        seen = {start}
        while queue:
            u = queue.popleft()
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    comp.append(v)
                    queue.append(v)
        for o in comp:
            label[o] = min(comp)
    return label


def _reference_test_lists(groups: dict[int, int], seed: int) -> list[list[int]]:
    from sklearn.model_selection import GroupKFold

    g = np.array([groups[o] for o in range(1, 241)])
    gkf = GroupKFold(n_splits=5, shuffle=True, random_state=seed)
    return [sorted(int(i) + 1 for i in te) for _, te in gkf.split(np.zeros((240, 1)), groups=g)]


@pytest.mark.req("P-012-08")
@pytest.mark.req("FR-012-05")
@settings(max_examples=EXAMPLES, deadline=None)
@given(seed=st.integers(0, 10**6), validation_seed=st.integers(0, 10**6))
def test_for_any_seed_test_lists_partition_the_originals_and_roles_are_group_disjoint(
    seed: int, validation_seed: int
) -> None:
    folds = splits.build_folds(LINKS, seed=seed, validation_seed=validation_seed)
    groups = _bfs_groups(LINKS)
    assert len(folds) == 5
    tests = [set(f["test_originals"]) for f in folds]
    assert set().union(*tests) == ORIGINALS
    assert sum(len(t) for t in tests) == 240, "the five test lists are pairwise disjoint"
    assert [f["test_originals"] for f in folds] == _reference_test_lists(groups, seed)
    for f in folds:
        roles = [set(f[k]) for k in ("test_originals", "validation_originals", "training_originals")]
        assert roles[0] | roles[1] | roles[2] == ORIGINALS
        role_groups = [{groups[o] for o in r} for r in roles]
        assert not (role_groups[0] & role_groups[1])
        assert not (role_groups[0] & role_groups[2])
        assert not (role_groups[1] & role_groups[2])
        assert all(o <= 240 for o in f["test_originals"])


@pytest.mark.req("P-012-08")
@pytest.mark.req("FR-012-04")
@settings(max_examples=EXAMPLES, deadline=None)
@given(k=st.integers(1, 960))
def test_the_four_dihedral_copies_of_an_original_share_its_group(k: int) -> None:
    groups = splits.build_groups(LINKS)
    original = (k - 1) % 240 + 1
    assert splits.group_key(k) == original
    assert {groups[original + 240 * m] for m in range(4)} == {groups[k]}


@st.composite
def _link_sets(draw) -> list[tuple[int, int]]:
    pairs = draw(st.lists(st.tuples(st.integers(1, 240), st.integers(1, 240)), max_size=40))
    return [(a, b) for a, b in pairs if a != b]


@pytest.mark.req("FR-012-04")
@settings(max_examples=EXAMPLES, deadline=None)
@given(links=_link_sets())
def test_union_find_groups_equal_the_connected_components(links: list[tuple[int, int]]) -> None:
    ref = _bfs_groups(links)
    groups = splits.build_groups(links)
    for k in range(1, 961):
        assert groups[k] == ref[(k - 1) % 240 + 1]
    assert len(set(groups.values())) == len(set(ref.values()))
