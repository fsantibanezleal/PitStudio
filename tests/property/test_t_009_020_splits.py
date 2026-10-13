# ruff: noqa: E501
"""T-009-020 - FR-009-16, FR-009-17, P-009-13, NFR-009-05: seed-grouped splits, leak checks, arm volume.

Oracles (independent of the code under test):
- FR-009-16 / P-009-13, hand calculation: for n scenario seeds the targets are 0.8 n, 0.1 n, 0.1 n and each count must be
  within +-1 seed of its target (spec 009 FR-009-16); the three splits are disjoint and cover every seed; the
  unstructured arm reuses exactly the structured pit training seeds (so its seeds are a subset of the training seeds);
  10,000 seeds (the default recipe, one image per scenario) give a test set of 1,000 >= 900 images (hand calculation);
- layouts shared by several seeds must stay in one split (FR-009-17 forbids a layout id in two splits): with 40 layouts of 10
  seeds each (400 seeds) the counts can only be within one layout (10 seeds) of the targets (reported ambiguity: FR-009-16's
  "+-1 seed" and FR-009-17 cannot both hold when layouts hold several seeds);
- FR-009-17, hand calculation with 64-bit hash integers: a test hash equal to a training hash XOR a mask of 4 set bits is a
  leak (Hamming 4 <= 4), a mask of 5 set bits is not; reference implementation `ImageHash` (`imagehash.phash`, default
  hash_size 8 = 64 bits) called directly in the file-based tests: a JPEG re-encoded copy of a smooth image is within Hamming 4
  of the original (the reference itself is asserted first) and a different image is not;
- NFR-009-05, hand calculation: 9,500 valid of 10,000 requested passes (0.95 x 10,000 = 9,500), 9,499 fails; the same ratio at 1,000
  requested gives 950 / 949.

Expected public API (module `pitstudio_pipeline.perception.splits`, package under `pipeline/src/`):

    SplitError(Exception)             .code: str ("split-leak", "scenario-invalid", "volume-invalid"); .pairs: tuple[tuple[str, str, str], ...]
                                      for split-leak: (record_id_a, record_id_b, reason) with reason "scenario_seed",
                                      "layout_id" or "phash"; str(error) contains the code and every record id of every pair
    SplitAssignment                   frozen dataclass: train, validation, test: tuple[int, ...] (scenario seeds, ascending)
    assign_splits(scenarios: Sequence[tuple[int, str]], *, rng_seed: int) -> SplitAssignment
        `scenarios` = (scenario_seed, layout_id) pairs of ONE family; seeds are distinct integers in 0..2**63-1, layout ids
        non-empty strings. All seeds of one layout id go to the same split. Deterministic for a given input and rng_seed (the
        input order does not matter). Proportions 80 / 10 / 10 %: when every layout holds one seed each count is within
        +-1 of its target; in general within the size of the largest layout.
        SplitError("scenario-invalid") for empty input, a duplicated seed, a negative / non-int / bool seed, a seed above
        2**63-1, an empty or non-string layout id, or a non-int rng_seed.
    ArmSplits                         frozen dataclass: pit: SplitAssignment, crusher: SplitAssignment,
                                      unstructured_train: tuple[int, ...]
    build_arm_splits(pit: Sequence[tuple[int, str]], crusher: Sequence[tuple[int, str]], *, rng_seed: int) -> ArmSplits
        assign_splits per family; `unstructured_train` == the structured pit training seeds (the unstructured arm is in
        training only and reuses them).
    hamming64(a: int, b: int) -> int  population count of (a XOR b) over 64 bits; ValueError (message contains "hash") unless
                                      both are ints (bool excluded) in 0..2**64-1.
    phash64(path: pathlib.Path) -> int
        int(str(imagehash.phash(PIL.Image.open(path))), 16): the 64-bit perceptual hash.
    check_leaks(records: Sequence[Mapping], *, root: pathlib.Path | None = None, hashes: Mapping[str, int] | None = None) -> None
        records carry "record_id", "scenario_seed", "layout_id", "split" ("train" | "validation" | "test") and, for the hash
        check, image["path"] below `root`. Raises SplitError("split-leak") listing every pair when (a) a scenario seed occurs in two
        splits, (b) a layout id occurs in two splits, or (c) a test image and a training or validation image have hashes at
        Hamming distance <= 4 (hashes from `hashes[record_id]`, else phash64 of root / image.path; no hash check when neither
        is given). A malformed record (missing key, non-int seed, split other than the three names, not a mapping) raises
        SplitError("scenario-invalid"). Pairs inside one split never leak (train-train, train-validation of different seeds are fine for (c)).
    arm_volume_ok(requested: int, valid: int) -> bool
        True iff valid >= 0.95 * requested (exact integer arithmetic: 100 * valid >= 95 * requested). SplitError("volume-invalid")
        for requested < 1, valid < 0 or valid > requested, or non-int arguments (bool included).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.perception import splits  # noqa: E402

EXAMPLES = 200
RNG = 20261007


def _unique(seeds) -> list[tuple[int, str]]:
    return [(s, f"layout-{s}") for s in seeds]


def _counts_ok(a: splits.SplitAssignment, n: int, tol: float) -> bool:
    return (
        abs(len(a.train) - 0.8 * n) <= tol
        and abs(len(a.validation) - 0.1 * n) <= tol
        and abs(len(a.test) - 0.1 * n) <= tol
    )


# ---------------------------------------------------------------- FR-009-16 / P-009-13


@pytest.mark.req("FR-009-16")
def test_the_default_recipe_size_gives_a_test_set_of_at_least_900_images() -> None:
    a = splits.assign_splits(_unique(range(10_000)), rng_seed=RNG)
    assert len(a.train) + len(a.validation) + len(a.test) == 10_000
    assert len(a.test) >= 900
    assert _counts_ok(a, 10_000, 1.0)


@pytest.mark.req("FR-009-16")
@pytest.mark.req("P-009-13")
@given(
    seeds=st.sets(st.integers(0, 2**63 - 1), min_size=10, max_size=5000),
    rng_seed=st.integers(0, 2**32 - 1),
)
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_splits_are_disjoint_cover_every_seed_and_follow_80_10_10(seeds: set[int], rng_seed: int) -> None:
    a = splits.assign_splits(_unique(seeds), rng_seed=rng_seed)
    train, val, test = set(a.train), set(a.validation), set(a.test)
    assert len(train) == len(a.train)
    assert len(val) == len(a.validation)
    assert len(test) == len(a.test)
    assert train.isdisjoint(val)
    assert train.isdisjoint(test)
    assert val.isdisjoint(test)
    assert train | val | test == seeds
    assert _counts_ok(a, len(seeds), 1.0)
    assert list(a.train) == sorted(a.train)


@pytest.mark.req("P-009-13")
@given(
    pit=st.sets(st.integers(0, 2**40), min_size=10, max_size=400),
    crusher=st.sets(st.integers(0, 2**40), min_size=10, max_size=400),
    rng_seed=st.integers(0, 2**32 - 1),
)
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_the_unstructured_arm_seeds_are_a_subset_of_the_structured_pit_training_seeds(
    pit: set[int], crusher: set[int], rng_seed: int
) -> None:
    arms = splits.build_arm_splits(_unique(pit), _unique(crusher), rng_seed=rng_seed)
    assert set(arms.unstructured_train) == set(arms.pit.train)
    assert set(arms.unstructured_train) <= set(arms.pit.train)
    assert set(arms.unstructured_train).isdisjoint(arms.pit.test)
    assert set(arms.unstructured_train).isdisjoint(arms.pit.validation)
    assert set(arms.pit.train) | set(arms.pit.validation) | set(arms.pit.test) == pit
    assert set(arms.crusher.train) | set(arms.crusher.validation) | set(arms.crusher.test) == crusher


@pytest.mark.req("FR-009-16")
def test_the_split_is_deterministic_independent_of_input_order_and_changes_with_the_seed() -> None:
    sc = _unique(range(100, 300))
    a = splits.assign_splits(sc, rng_seed=1)
    assert a == splits.assign_splits(sc, rng_seed=1)
    assert a == splits.assign_splits(list(reversed(sc)), rng_seed=1)
    assert a != splits.assign_splits(sc, rng_seed=2)


@pytest.mark.req("FR-009-16")
def test_every_layout_stays_in_one_split() -> None:
    sc = [(1000 + 10 * layout + k, f"layout-{layout:02d}") for layout in range(40) for k in range(10)]  # 400 seeds
    a = splits.assign_splits(sc, rng_seed=RNG)
    where = {"train": set(a.train), "validation": set(a.validation), "test": set(a.test)}
    layout_of = dict(sc)
    for layout in {lay for _, lay in sc}:
        seeds = {s for s, lay in sc if lay == layout}
        holders = [name for name, members in where.items() if seeds & members]
        assert len(holders) == 1, (layout, holders)
        assert seeds <= where[holders[0]]
    assert len(layout_of) == 400
    assert set(a.train) | set(a.validation) | set(a.test) == set(layout_of)
    assert _counts_ok(a, 400, 10.0)  # within one layout of the targets (320 / 40 / 40)


@pytest.mark.req("FR-009-16")
@pytest.mark.parametrize(
    ("scenarios", "rng_seed"),
    [
        ([], 0),
        ([(1, "a"), (1, "b")], 0),  # duplicated seed
        ([(-1, "a")], 0),
        ([(1.5, "a")], 0),
        ([(True, "a")], 0),
        ([("7", "a")], 0),
        ([(2**63, "a")], 0),
        ([(1, "")], 0),
        ([(1, None)], 0),
        ([(1, 7)], 0),
        ([(1, "a")], "0"),
        ([(1, "a")], True),
    ],
)
def test_hostile_scenarios_are_rejected(scenarios: list, rng_seed: object) -> None:
    with pytest.raises(splits.SplitError) as exc:
        splits.assign_splits(scenarios, rng_seed=rng_seed)  # type: ignore[arg-type]
    assert exc.value.code == "scenario-invalid"
    assert "scenario-invalid" in str(exc.value)


# ---------------------------------------------------------------- FR-009-17: leaks


def _rec(rid: str, seed: int, layout: str, split: str, image: str | None = None) -> dict:
    r = {
        "record_id": rid,
        "scenario_seed": seed,
        "layout_id": layout,
        "split": split,
        "family": "pit",
        "arm": "structured",
    }
    if image is not None:
        r["image"] = {"path": image}
    return r


def _leaks(records: list[dict], **kw) -> splits.SplitError:
    with pytest.raises(splits.SplitError) as exc:
        splits.check_leaks(records, **kw)
    assert exc.value.code == "split-leak"
    assert "split-leak" in str(exc.value)
    return exc.value


def _pairs(err: splits.SplitError) -> set[tuple[frozenset[str], str]]:
    return {(frozenset((a, b)), why) for a, b, why in err.pairs}


@pytest.mark.req("FR-009-17")
def test_clean_records_pass() -> None:
    recs = [
        _rec("a", 1, "L1", "train"),
        _rec("b", 1, "L1", "train"),  # same seed twice inside one split is fine
        _rec("c", 2, "L2", "validation"),
        _rec("d", 3, "L3", "test"),
    ]
    assert splits.check_leaks(recs) is None
    assert splits.check_leaks([]) is None


@pytest.mark.req("FR-009-17")
def test_a_scenario_seed_in_two_splits_is_a_leak_listing_the_pair() -> None:
    recs = [_rec("a", 7, "L1", "train"), _rec("b", 7, "L2", "test"), _rec("c", 8, "L3", "validation")]
    err = _leaks(recs)
    assert _pairs(err) == {(frozenset({"a", "b"}), "scenario_seed")}
    assert "a" in str(err)
    assert "b" in str(err)


@pytest.mark.req("FR-009-17")
def test_a_layout_id_in_two_splits_is_a_leak_listing_the_pair() -> None:
    recs = [_rec("a", 7, "L1", "train"), _rec("b", 8, "L1", "validation"), _rec("c", 9, "L2", "test")]
    assert _pairs(_leaks(recs)) == {(frozenset({"a", "b"}), "layout_id")}


@pytest.mark.req("FR-009-17")
def test_every_leaking_pair_is_listed_not_just_the_first() -> None:
    recs = [
        _rec("a", 1, "L1", "train"),
        _rec("b", 1, "L9", "test"),
        _rec("c", 2, "L2", "train"),
        _rec("d", 3, "L2", "validation"),
    ]
    assert _pairs(_leaks(recs)) == {
        (frozenset({"a", "b"}), "scenario_seed"),
        (frozenset({"c", "d"}), "layout_id"),
    }


MASK4 = 0b1111  # four set bits
MASK5 = 0b11111  # five set bits
H = 0x0123456789ABCDEF


@pytest.mark.req("FR-009-17")
def test_a_test_hash_at_hamming_distance_four_from_a_training_hash_is_a_leak_and_five_is_not() -> None:
    recs = [_rec("tr", 1, "L1", "train"), _rec("va", 2, "L2", "validation"), _rec("te", 3, "L3", "test")]
    err = _leaks(recs, hashes={"tr": H ^ MASK4, "va": H ^ (MASK5 << 20), "te": H})
    assert _pairs(err) == {(frozenset({"tr", "te"}), "phash")}  # distance 4 leaks; validation is at distance 5
    assert splits.check_leaks(recs, hashes={"tr": H ^ MASK5, "va": H ^ (MASK5 << 20), "te": H}) is None


@pytest.mark.req("FR-009-17")
def test_a_test_hash_equal_to_a_validation_hash_is_a_leak() -> None:
    recs = [_rec("va", 2, "L2", "validation"), _rec("te", 3, "L3", "test")]
    assert _pairs(_leaks(recs, hashes={"va": H, "te": H})) == {(frozenset({"va", "te"}), "phash")}


@pytest.mark.req("FR-009-17")
def test_similar_images_inside_training_or_between_training_and_validation_are_not_leaks() -> None:
    recs = [
        _rec("t1", 1, "L1", "train"),
        _rec("t2", 2, "L2", "train"),
        _rec("va", 3, "L3", "validation"),
        _rec("te", 4, "L4", "test"),
    ]
    assert splits.check_leaks(recs, hashes={"t1": H, "t2": H, "va": H, "te": H ^ (MASK5 << 40)}) is None


@pytest.mark.req("FR-009-17")
def test_hamming_distance_of_64_bit_hashes() -> None:
    assert splits.hamming64(0, 0) == 0
    assert splits.hamming64(H, H ^ MASK4) == 4
    assert splits.hamming64(0, 2**64 - 1) == 64
    assert splits.hamming64(0b1010, 0b0101) == 4
    for bad in (-1, 2**64, 1.5, True, None):
        with pytest.raises(ValueError, match="hash"):
            splits.hamming64(bad, 0)  # type: ignore[arg-type]


def _smooth_image(shift: int = 0) -> np.ndarray:
    """A smooth 128 x 128 greyscale-like image (gradients and two blobs) so that JPEG re-encoding barely moves its pHash."""
    y, x = np.mgrid[0:128, 0:128].astype(np.float64)
    img = 80 + 0.6 * x + 0.3 * y
    img += 90 * np.exp(-(((x - 40 - shift) ** 2) + ((y - 50) ** 2)) / 300.0)
    img += 70 * np.exp(-(((x - 95) ** 2) + ((y - 90 + shift) ** 2)) / 200.0)
    img = np.clip(img, 0, 255).astype(np.uint8)
    return np.stack([img, img, img], axis=-1)


@pytest.mark.req("FR-009-17")
def test_phash64_equals_the_imagehash_reference(tmp_path: Path) -> None:
    import imagehash
    from PIL import Image

    p = tmp_path / "a.png"
    Image.fromarray(_smooth_image()).save(p)
    assert splits.phash64(p) == int(str(imagehash.phash(Image.open(p))), 16)


@pytest.mark.req("FR-009-17")
def test_a_re_encoded_copy_of_a_training_image_in_the_test_set_is_found_through_the_files(tmp_path: Path) -> None:
    import imagehash
    from PIL import Image

    train_png, copy_jpg, other_png = tmp_path / "train.png", tmp_path / "copy.jpg", tmp_path / "other.png"
    Image.fromarray(_smooth_image()).save(train_png)
    Image.fromarray(_smooth_image()).save(copy_jpg, quality=90)
    Image.fromarray(255 - _smooth_image(shift=25)[:, ::-1]).save(other_png)

    def ref(p: Path):
        return imagehash.phash(Image.open(p))

    assert ref(train_png) - ref(copy_jpg) <= 4  # the oracle itself: a re-encoded copy is within Hamming 4
    assert ref(train_png) - ref(other_png) > 4  # and a different image is not
    recs = [
        _rec("tr", 1, "L1", "train", "train.png"),
        _rec("te-copy", 2, "L2", "test", "copy.jpg"),
        _rec("te-other", 3, "L3", "test", "other.png"),
    ]
    assert _pairs(_leaks(recs, root=tmp_path)) == {(frozenset({"tr", "te-copy"}), "phash")}


@pytest.mark.req("FR-009-17")
@pytest.mark.parametrize(
    "records",
    [
        [{"record_id": "a"}],
        [{"record_id": "a", "scenario_seed": 1, "layout_id": "L", "split": "holdout"}],
        [{"record_id": "a", "scenario_seed": "1", "layout_id": "L", "split": "train"}],
        ["not a record"],
        [None],
    ],
)
def test_malformed_records_are_rejected(records: list) -> None:
    with pytest.raises(splits.SplitError) as exc:
        splits.check_leaks(records)
    assert exc.value.code == "scenario-invalid"


# ---------------------------------------------------------------- NFR-009-05


@pytest.mark.req("NFR-009-05")
@pytest.mark.parametrize(
    ("requested", "valid", "ok"),
    [
        (10_000, 10_000, True),
        (10_000, 9_500, True),
        (10_000, 9_499, False),
        (1_000, 950, True),
        (1_000, 949, False),
        (20, 19, True),
        (20, 18, False),
        (1, 1, True),
        (1, 0, False),
    ],
)
def test_an_arm_needs_at_least_95_percent_valid_images(requested: int, valid: int, ok: bool) -> None:
    assert splits.arm_volume_ok(requested, valid) is ok


@pytest.mark.req("NFR-009-05")
@pytest.mark.parametrize(
    ("requested", "valid"),
    [(0, 0), (-5, 0), (100, -1), (100, 101), (100.0, 95), (100, 95.0), (True, 1), (100, True), (None, 1), ("100", 95)],
)
def test_hostile_volume_arguments_are_rejected(requested: object, valid: object) -> None:
    with pytest.raises(splits.SplitError) as exc:
        splits.arm_volume_ok(requested, valid)  # type: ignore[arg-type]
    assert exc.value.code == "volume-invalid"
