"""T-012-012 - FR-012-04, FR-012-05, FR-012-06, FR-012-44, NFR-012-04: group keys, links, grouped 5-fold, leak checks.

Oracles (independent of the code under test):
- hand calculation of the source groups from spec 012 section 7: the nine links 29-39, 34-41, 36-37, 41-49, 59-60,
  189-199, 192-196, 196-198, 196-201 give the components {29, 39}, {34, 41, 49}, {36, 37}, {59, 60}, {189, 199},
  {192, 196, 198, 201}; 240 - 9 = 231 groups; file k belongs to original ((k - 1) mod 240) + 1;
- reference implementation: scikit-learn `GroupKFold(n_splits=5, shuffle=True, random_state=20261004)` called
  directly in this file over the 240 originals (FR-012-05 names it; plan 012 test strategy row FR-012-05);
- hand-built fold lists with one planted leak each (FR-012-06) and hand-written hostile links files (FR-012-44).

Expected public API (module `pitstudio_pipeline.fragmentation.splits`, package under `pipeline/src/`):

    SplitError(Exception)
        .code   str, "links-invalid" or "split-leak"; str(err) contains the code
        .files  tuple[int, ...], the offending file numbers (sorted); may be empty for "links-invalid"
    group_key(k: int) -> int
        ((k - 1) mod 240) + 1 for a file number k in 1..960.
    build_groups(links: Iterable[tuple[int, int]]) -> dict[int, int]
        Pure union-find over the originals 1..240 with the given links, then file k -> group of group_key(k).
        Keys: every file 1..960. Group id (canonical representative) = the SMALLEST original number of the
        component. No group-count check here (the links file carries groups_expected = 231 for that).
    read_links(path: Path) -> tuple[tuple[int, int], ...]
        Reads the YAML links file (DC-012-02, kind "links"); raises SplitError(code="links-invalid") if the file is
        not valid YAML / not UTF-8, does not validate against DC-012-02, names a file outside 1..240, or links a
        file to itself.
    build_folds(links, *, seed: int = 20261004, validation_seed: int = 20261004) -> list[dict]
        Five dicts {"fold": f, "test_originals": [...], "validation_originals": [...], "training_originals": [...]}
        (sorted ascending lists of original numbers 1..240). Fold f's test list = the originals of the f-th test
        split yielded by GroupKFold(n_splits=5, shuffle=True, random_state=seed).split(X, groups=g) with X one row
        per original 1..240 in ascending order and g[i] = build_groups(links)[i + 1]. Validation = the originals
        of a seeded 10 % of the remaining groups (validation_seed); training = all other originals.
    check_folds(folds: Sequence[Mapping], groups: Mapping[int, int]) -> None
        Raises SplitError(code="split-leak", files=...) if a group occurs in the test list and in the training or
        validation list of the same fold, a test list holds a file k > 240, or the union of the five test lists
        differs from {1, ..., 240}.
    write_fold_file(links_path: Path, out_path: Path, *, validation_seed: int = 20261004) -> dict
        read_links -> build_folds -> check_folds, then writes the DC-012-02 fold document (kind "folds") as JSON
        and returns it; byte-identical output for identical inputs (NFR-012-04); writes nothing on any error.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.fragmentation import splits  # noqa: E402

ARCHIVE_SHA256 = "7f4336a4fe1f83e3c828eed4c73e036d7694f94076b6f040e6211315693f402d"  # FR-012-01
SEED = 20261004  # FR-012-05
LINKS = [(29, 39), (34, 41), (36, 37), (41, 49), (59, 60), (189, 199), (192, 196), (196, 198), (196, 201)]  # spec 7
COMPONENTS = [{29, 39}, {34, 41, 49}, {36, 37}, {59, 60}, {189, 199}, {192, 196, 198, 201}]  # spec 7, hand union-find
ORIGINALS = set(range(1, 241))
COMMITTED_LINKS = ROOT / "data" / "splits" / "mendeley-78ht3pjsr4-links.yaml"


def _schema() -> dict:
    """DC-012-02; the promoted copy under contracts/ (T-012-002) wins over the spec draft."""
    for p in (
        ROOT / "contracts" / "fragment-split.schema.json",
        ROOT / "specs" / "012-fragmentation" / "contracts" / "fragment-split.schema.json",
    ):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise AssertionError("DC-012-02 schema not found")


def _links_doc(links=LINKS, **overrides) -> dict:
    doc = {
        "kind": "links",
        "source_id": "mendeley-78ht3pjsr4",
        "archive_sha256": ARCHIVE_SHA256,
        "links": [list(p) for p in links],
        "groups_expected": 231,
    }
    doc.update(overrides)
    return doc


def _write_links(tmp_path: Path, doc: dict | None = None, name: str = "links.yaml") -> Path:
    p = tmp_path / name
    p.write_text(yaml.safe_dump(_links_doc() if doc is None else doc, sort_keys=True), encoding="utf-8")
    return p


def _hand_group(k: int) -> int:
    """Hand oracle: original of file k, then the smallest member of its component (or itself)."""
    o = (k - 1) % 240 + 1
    for comp in COMPONENTS:
        if o in comp:
            return min(comp)
    return o


def _reference_test_lists(seed: int) -> list[list[int]]:
    from sklearn.model_selection import GroupKFold

    groups = np.array([_hand_group(k) for k in range(1, 241)])
    gkf = GroupKFold(n_splits=5, shuffle=True, random_state=seed)
    return [sorted(int(i) + 1 for i in te) for _, te in gkf.split(np.zeros((240, 1)), groups=groups)]


def _hand_valid_folds() -> list[dict]:
    """A hand-built leak-free fold set: group g (canonical id) goes to test fold (rank of g) mod 5; validation is the
    first remaining group in ascending order, training the rest."""
    gids = sorted({_hand_group(k) for k in range(1, 241)})
    members = {g: sorted(o for o in ORIGINALS if _hand_group(o) == g) for g in gids}
    folds = []
    for f in range(5):
        test_g = [g for r, g in enumerate(gids) if r % 5 == f]
        rest = [g for g in gids if g not in test_g]
        val_g, train_g = rest[:1], rest[1:]
        folds.append(
            {
                "fold": f,
                "test_originals": sorted(o for g in test_g for o in members[g]),
                "validation_originals": sorted(o for g in val_g for o in members[g]),
                "training_originals": sorted(o for g in train_g for o in members[g]),
            }
        )
    return folds


def _fold_of(folds: list[dict], original: int) -> dict:
    return next(f for f in folds if original in f["test_originals"])


# ---------------------------------------------------------------- FR-012-04 group keys and links


@pytest.mark.req("FR-012-04")
@pytest.mark.parametrize(("k", "g"), [(1, 1), (240, 240), (241, 1), (480, 240), (481, 1), (725, 5), (960, 240)])
def test_group_key_maps_dihedral_copies_to_their_original(k: int, g: int) -> None:
    assert splits.group_key(k) == g


@pytest.mark.req("FR-012-04")
def test_nine_links_give_the_hand_computed_231_groups() -> None:
    groups = splits.build_groups(LINKS)
    assert set(groups) == set(range(1, 961))
    assert len(set(groups.values())) == 231
    for k in range(1, 961):
        assert groups[k] == _hand_group(k), k
    for comp in COMPONENTS:
        members = [o + 240 * m for o in comp for m in range(4)]
        assert {groups[k] for k in members} == {min(comp)}
    singletons = sorted(ORIGINALS - set().union(*COMPONENTS))
    assert len(singletons) == 240 - sum(len(c) for c in COMPONENTS) == 225
    assert len({groups[o] for o in singletons}) == 225


@pytest.mark.req("FR-012-04")
def test_link_order_and_orientation_do_not_change_the_groups() -> None:
    reversed_links = [(b, a) for a, b in reversed(LINKS)]
    assert splits.build_groups(reversed_links) == splits.build_groups(LINKS)


@pytest.mark.req("FR-012-04")
def test_committed_links_file_holds_the_nine_links() -> None:
    assert COMMITTED_LINKS.is_file(), "data/splits/mendeley-78ht3pjsr4-links.yaml is committed by T-012-000"
    links = splits.read_links(COMMITTED_LINKS)
    assert {tuple(sorted(p)) for p in links} == set(LINKS)
    assert len(links) == 9
    assert len(set(splits.build_groups(links).values())) == 231


@pytest.mark.req("FR-012-04")
def test_read_links_returns_the_links_of_a_valid_file(tmp_path: Path) -> None:
    links = splits.read_links(_write_links(tmp_path))
    assert [tuple(p) for p in links] == LINKS


# ---------------------------------------------------------------- FR-012-05 grouped 5-fold


@pytest.mark.req("FR-012-05")
def test_test_lists_are_the_scikit_learn_group_kfold_splits() -> None:
    folds = splits.build_folds(LINKS)
    assert [f["fold"] for f in folds] == [0, 1, 2, 3, 4]
    assert [f["test_originals"] for f in folds] == _reference_test_lists(SEED)


@pytest.mark.req("FR-012-05")
def test_validation_is_a_tenth_of_the_remaining_groups_and_training_the_rest() -> None:
    folds = splits.build_folds(LINKS)
    for f in folds:
        test, val, train = (set(f[key]) for key in ("test_originals", "validation_originals", "training_originals"))
        for key in ("test_originals", "validation_originals", "training_originals"):
            assert f[key] == sorted(f[key]), "lists are sorted ascending"
            assert all(isinstance(o, int) and 1 <= o <= 240 for o in f[key])
        assert test | val | train == ORIGINALS
        assert not (test & val)
        assert not (test & train)
        assert not (val & train)
        g_test = {_hand_group(o) for o in test}
        g_val = {_hand_group(o) for o in val}
        g_train = {_hand_group(o) for o in train}
        assert not (g_test & g_val)
        assert not (g_test & g_train)
        assert not (g_val & g_train)
        remaining = 231 - len(g_test)
        # "a seeded 10 % of the remaining groups": the rounding rule is not fixed by the spec, so floor or ceil.
        assert len(g_val) in {math.floor(0.1 * remaining), math.ceil(0.1 * remaining)}
        assert len(g_val) >= 1


@pytest.mark.req("FR-012-05")
def test_expansion_lists_the_four_dihedral_files_of_each_original() -> None:
    assert splits.expand_dihedral([1, 2, 240]) == [1, 2, 240, 241, 242, 480, 481, 482, 720, 721, 722, 960]
    assert splits.expand_dihedral([]) == []


@pytest.mark.req("FR-012-05")
def test_validation_seed_changes_validation_but_never_the_test_lists() -> None:
    a = splits.build_folds(LINKS, validation_seed=1)
    b = splits.build_folds(LINKS, validation_seed=2)
    assert [f["test_originals"] for f in a] == [f["test_originals"] for f in b] == _reference_test_lists(SEED)
    assert splits.build_folds(LINKS, validation_seed=1) == a


@pytest.mark.req("FR-012-05")
def test_fold_file_is_a_valid_dc_012_02_document(tmp_path: Path) -> None:
    import jsonschema
    import sklearn

    links_path = _write_links(tmp_path)
    out = tmp_path / "folds.json"
    doc = splits.write_fold_file(links_path, out)
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == doc
    jsonschema.Draft202012Validator(_schema()).validate(on_disk)
    assert on_disk["kind"] == "folds"
    assert on_disk["archive_sha256"] == ARCHIVE_SHA256
    assert on_disk["links_sha256"] == hashlib.sha256(links_path.read_bytes()).hexdigest()
    assert on_disk["seed"] == SEED
    assert on_disk["validation_seed"] == SEED
    assert on_disk["n_folds"] == 5
    assert on_disk["group_count"] == 231
    assert on_disk["expansion"] == "dihedral-4"
    assert on_disk["sklearn_version"] == sklearn.__version__
    assert on_disk["folds"] == splits.build_folds(LINKS)


# ---------------------------------------------------------------- NFR-012-04 determinism


@pytest.mark.req("NFR-012-04")
def test_fold_file_is_byte_identical_across_two_runs(tmp_path: Path) -> None:
    links_a = _write_links(tmp_path, name="a.yaml")
    links_b = _write_links(tmp_path, name="b.yaml")
    assert links_a.read_bytes() == links_b.read_bytes()
    out_a, out_b = tmp_path / "a.json", tmp_path / "b.json"
    splits.write_fold_file(links_a, out_a)
    splits.write_fold_file(links_b, out_b)
    assert out_a.read_bytes() == out_b.read_bytes()


# ---------------------------------------------------------------- FR-012-06 leak checks (hostile)


@pytest.mark.req("FR-012-06")
def test_hand_built_leak_free_folds_pass_the_check() -> None:
    splits.check_folds(_hand_valid_folds(), splits.build_groups(LINKS))


@pytest.mark.req("FR-012-06")
@pytest.mark.parametrize("role", ["training_originals", "validation_originals"])
def test_group_split_across_test_and_another_role_is_a_leak(role: str) -> None:
    # Planted leak that keeps the union of the test lists intact: 39 (same group as 29 through link 29-39) moves from
    # fold f's test list to fold g's test list and into fold f's `role` list. Fold f then has 29 in test and 39 in
    # `role`; fold g has 39 in test and 29 in training or validation.
    folds = _hand_valid_folds()
    f = _fold_of(folds, 29)
    assert 39 in f["test_originals"]
    g = folds[(f["fold"] + 1) % 5]
    f["test_originals"].remove(39)
    f[role] = sorted([*f[role], 39])
    for other in ("training_originals", "validation_originals"):
        if 39 in g[other]:
            g[other].remove(39)
    g["test_originals"] = sorted([*g["test_originals"], 39])
    assert set().union(*(set(x["test_originals"]) for x in folds)) == ORIGINALS
    with pytest.raises(splits.SplitError) as exc:
        splits.check_folds(folds, splits.build_groups(LINKS))
    assert exc.value.code == "split-leak"
    assert "split-leak" in str(exc.value)
    assert 39 in exc.value.files


@pytest.mark.req("FR-012-06")
def test_test_list_with_a_file_above_240_is_a_leak() -> None:
    folds = _hand_valid_folds()
    folds[0]["test_originals"] = sorted([*folds[0]["test_originals"], 241])  # 241 = horizontal flip of file 1
    with pytest.raises(splits.SplitError) as exc:
        splits.check_folds(folds, splits.build_groups(LINKS))
    assert exc.value.code == "split-leak"
    assert 241 in exc.value.files


@pytest.mark.req("FR-012-06")
def test_union_of_test_lists_missing_an_original_is_a_leak() -> None:
    folds = _hand_valid_folds()
    f = _fold_of(folds, 240)  # 240 is a singleton group (no link names it)
    f["test_originals"].remove(240)
    with pytest.raises(splits.SplitError) as exc:
        splits.check_folds(folds, splits.build_groups(LINKS))
    assert exc.value.code == "split-leak"
    assert 240 in exc.value.files


# ---------------------------------------------------------------- FR-012-44 hostile links files


def _hostile_links_files(tmp_path: Path) -> dict[str, Path]:
    cases: dict[str, Path] = {}

    def doc(name: str, d: dict) -> None:
        cases[name] = _write_links(tmp_path, d, name=f"{name}.yaml")

    def raw(name: str, data: bytes) -> None:
        p = tmp_path / f"{name}.yaml"
        p.write_bytes(data)
        cases[name] = p

    doc("link-outside-1-240", _links_doc([*LINKS, (12, 241)]))
    doc("link-zero", _links_doc([*LINKS, (0, 12)]))
    doc("self-link", _links_doc([*LINKS, (5, 5)]))
    doc("triple", _links_doc([*LINKS, (1, 2, 3)]))
    doc("string-ids", {**_links_doc(), "links": [*([list(p) for p in LINKS]), ["12", "13"]]})
    doc("bool-ids", {**_links_doc(), "links": [*([list(p) for p in LINKS]), [True, 13]]})
    doc("wrong-kind", _links_doc(kind="folds"))
    doc("wrong-archive", _links_doc(archive_sha256="0" * 64))
    doc("wrong-groups-expected", _links_doc(groups_expected=230))
    doc("unknown-field", _links_doc(extra="x"))
    doc("missing-links", {k: v for k, v in _links_doc().items() if k != "links"})
    doc("huge-link-list", _links_doc([(a, a + 1) for a in range(1, 240)] * 40))
    doc("unicode-garbage", {**_links_doc(), "links": "✗é中"})
    raw("malformed-yaml", b"kind: links\nlinks: [[29, 39], [34, 41]\n")
    raw("empty-file", b"")
    raw("not-a-mapping", b"- [29, 39]\n- [34, 41]\n")
    raw("not-utf8", b"kind: links\nnote: \xc3\x28\xff\n")
    return cases


@pytest.mark.req("FR-012-44")
@pytest.mark.parametrize(
    "case",
    [
        "link-outside-1-240",
        "link-zero",
        "self-link",
        "triple",
        "string-ids",
        "bool-ids",
        "wrong-kind",
        "wrong-archive",
        "wrong-groups-expected",
        "unknown-field",
        "missing-links",
        "huge-link-list",
        "unicode-garbage",
        "malformed-yaml",
        "empty-file",
        "not-a-mapping",
        "not-utf8",
    ],
)
def test_hostile_links_file_stops_with_links_invalid_and_writes_no_fold_file(tmp_path: Path, case: str) -> None:
    path = _hostile_links_files(tmp_path)[case]
    with pytest.raises(splits.SplitError) as exc:
        splits.read_links(path)
    assert exc.value.code == "links-invalid"
    assert "links-invalid" in str(exc.value)
    out = tmp_path / "folds.json"
    with pytest.raises(splits.SplitError) as exc2:
        splits.write_fold_file(path, out)
    assert exc2.value.code == "links-invalid"
    assert not out.exists()


@pytest.mark.req("FR-012-44")
def test_missing_links_file_writes_no_fold_file(tmp_path: Path) -> None:
    out = tmp_path / "folds.json"
    with pytest.raises((splits.SplitError, FileNotFoundError)):
        splits.write_fold_file(tmp_path / "absent.yaml", out)
    assert not out.exists()
