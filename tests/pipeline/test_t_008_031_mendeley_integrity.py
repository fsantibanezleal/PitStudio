# ruff: noqa: E501, PT018
"""T-008-031: augmentation-structure check of the Mendeley set (exact flips and rotation of the foreground, `cv2_mask` =
`label.png`), `AugmentationStructureBroken`, and the dataset card's counts.

Requirements: FR-008-29, SC-008-01.

Spec: specs/008-data-pipeline/spec.md FR-008-29 (for every k in 1..240 the foreground masks (label > 0) of files k + 240,
k + 480 and k + 720 equal the horizontal flip, the vertical flip and the 180-degree rotation of file k's foreground, exactly;
the `cv2_mask` and `label.png` foregrounds are equal for all 960 files; otherwise `AugmentationStructureBroken`) and SC-008-01
(960 images; 960 masks; 240 originals verified; 63,144 instances with pixels, mean 65.8 per image; 72 groups; 5 folds x 48
originals).

Oracle: exact numpy identities (`np.fliplr`, `np.flipud`, `np.rot90(m, 2)`) applied by the test to generated asymmetric
masks (non-square, so a flip cannot be mistaken for a rotation); hand counts of instances (original k has (k mod 7) + 1
instances with pixels, labels with gaps; the total 4 x 957 = 3,828 is computed from that formula); the card's published counts
for the real archive (local, `slow`).

Expected API of the implementation (module `pitstudio_pipeline.ingest.mendeley`):
- `check_augmentation_structure(label_masks, cv2_masks) -> None`: two mappings file number (1..960) -> 2-D integer array (the
  label.png and cv2_mask masks); raises `pitstudio_pipeline.errors.AugmentationStructureBroken` when a mask is missing for any
  file 1..960, shapes differ, a foreground of file k + 240 / 480 / 720 is not exactly the flip / flip / rotation of file k's,
  or the two mask kinds disagree in foreground for any file.
- `summarize_masks(label_masks) -> dict`: `images` (count), `instances_with_pixels` (number of distinct labels > 0 summed over
  the masks) and `mean_instances_per_image`.
- `ingest_mendeley(directory) -> dict` (local, real archive, extracted by `s00_download`): the keys `images`, `masks`,
  `originals_verified`, `instances_with_pixels`, `groups`, `folds`, `fold_test_originals`.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.errors import AugmentationStructureBroken
from pitstudio_pipeline.ingest.mendeley import check_augmentation_structure, ingest_mendeley, summarize_masks

H, W = 16, 24


def _original(k: int) -> np.ndarray:
    """Original k: (k mod 7) + 1 instances, instance i with the label 2i + 1 (gaps), as an off-centre block at rows 2i..2i+1."""
    a = np.zeros((H, W), dtype=np.uint8)
    rng = np.random.default_rng(k)
    for i in range((k % 7) + 1):
        c0 = int(rng.integers(0, W - 5))
        a[2 * i : 2 * i + 2, c0 : c0 + 1 + (i % 4)] = 2 * i + 1
    return a


def make_dataset() -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
    base = {k: _original(k) for k in range(1, 241)}
    label: dict[int, np.ndarray] = dict(base)
    for k, m in base.items():
        relabel = np.where(m > 0, m + 1, 0).astype(np.uint8)  # other (still distinct) label values, same foreground
        label[k + 240] = np.fliplr(relabel)
        label[k + 480] = np.flipud(relabel)
        label[k + 720] = np.rot90(relabel, 2)
    cv2 = {k: np.where(m > 0, 255, 0).astype(np.uint8) for k, m in label.items()}
    return label, cv2


@pytest.fixture(scope="module")
def dataset() -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
    return make_dataset()


def _copy(d: dict[int, np.ndarray]) -> dict[int, np.ndarray]:
    return {k: v.copy() for k, v in d.items()}


@pytest.mark.req("FR-008-29")
def test_the_generated_dataset_is_consistent_with_numpy_identities(dataset) -> None:
    label, _ = dataset
    for k in (1, 77, 240):
        fg = label[k] > 0
        assert np.array_equal(label[k + 240] > 0, np.fliplr(fg))
        assert np.array_equal(label[k + 480] > 0, np.flipud(fg))
        assert np.array_equal(label[k + 720] > 0, np.rot90(fg, 2))


@pytest.mark.req("FR-008-29")
def test_intact_structure_is_accepted(dataset) -> None:
    label, cv2 = dataset
    assert check_augmentation_structure(label, cv2) is None


@pytest.mark.req("FR-008-29")
@pytest.mark.parametrize("offset", [240, 480, 720])
@pytest.mark.parametrize("k", [1, 100, 240])
def test_one_flipped_foreground_pixel_in_a_copy_breaks_the_structure(offset: int, k: int, dataset) -> None:
    label, cv2 = dataset
    bad_label, bad_cv2 = _copy(label), _copy(cv2)
    target = bad_label[k + offset]
    r, c = np.argwhere(target == 0)[0]
    target[r, c] = 3  # one background pixel becomes foreground
    bad_cv2[k + offset] = np.where(target > 0, 255, 0).astype(np.uint8)  # keep the two mask kinds consistent
    with pytest.raises(AugmentationStructureBroken):
        check_augmentation_structure(bad_label, bad_cv2)


@pytest.mark.req("FR-008-29")
@pytest.mark.parametrize(
    ("offset", "wrong"), [(240, np.flipud), (480, np.fliplr), (720, np.fliplr), (240, lambda m: m)]
)
def test_a_copy_made_with_the_wrong_transform_is_rejected(offset: int, wrong, dataset) -> None:
    label, cv2 = dataset
    bad_label, bad_cv2 = _copy(label), _copy(cv2)
    k = 33
    bad_label[k + offset] = wrong(label[k]).copy()
    bad_cv2[k + offset] = np.where(bad_label[k + offset] > 0, 255, 0).astype(np.uint8)
    assert not np.array_equal(bad_label[k + offset] > 0, label[k + offset] > 0), "premise: the wrong transform differs"
    with pytest.raises(AugmentationStructureBroken):
        check_augmentation_structure(bad_label, bad_cv2)


@pytest.mark.req("FR-008-29")
@pytest.mark.parametrize("k", [1, 240, 241, 777, 960])
def test_cv2_mask_and_label_png_must_agree_for_all_960_files(k: int, dataset) -> None:
    label, cv2 = dataset
    bad_cv2 = _copy(cv2)
    r, c = np.argwhere(bad_cv2[k] == 0)[0]
    bad_cv2[k][r, c] = 255
    with pytest.raises(AugmentationStructureBroken):
        check_augmentation_structure(label, bad_cv2)


@pytest.mark.req("FR-008-29")
def test_label_values_may_differ_between_copies_only_the_foreground_counts(dataset) -> None:
    label, cv2 = dataset
    assert not np.array_equal(label[1], label[241]), "premise: the copies carry other label values"
    assert check_augmentation_structure(label, cv2) is None


@pytest.mark.req("FR-008-29")
@pytest.mark.parametrize("missing", [1, 500, 960])
def test_a_missing_file_is_a_broken_dataset(missing: int, dataset) -> None:
    label, cv2 = dataset
    short_label = {k: v for k, v in label.items() if k != missing}
    with pytest.raises(AugmentationStructureBroken):
        check_augmentation_structure(short_label, cv2)
    with pytest.raises(AugmentationStructureBroken):
        check_augmentation_structure(label, {k: v for k, v in cv2.items() if k != missing})


@pytest.mark.req("FR-008-29")
def test_shape_mismatch_between_label_and_cv2_mask_is_broken(dataset) -> None:
    label, cv2 = dataset
    bad = _copy(cv2)
    bad[5] = bad[5][:, :-1]
    with pytest.raises(AugmentationStructureBroken):
        check_augmentation_structure(label, bad)


@pytest.mark.req("SC-008-01")
def test_instance_counts_follow_the_hand_formula(dataset) -> None:
    label, _ = dataset
    out = summarize_masks(label)
    expected_total = 4 * sum((k % 7) + 1 for k in range(1, 241))  # hand formula: 4 x 957
    assert expected_total == 3828
    assert out["images"] == 960 and out["instances_with_pixels"] == expected_total
    assert out["mean_instances_per_image"] == pytest.approx(expected_total / 960, rel=1e-12)


@pytest.mark.req("SC-008-01")
def test_unnamed_instances_without_pixels_are_not_counted() -> None:
    m = np.zeros((H, W), dtype=np.uint8)
    m[0:2, 0:2] = 4  # instance 4 has pixels; instances 1..3 and 5 are "named" but absent (fully overlapped polygons)
    out = summarize_masks({1: m})
    assert out["instances_with_pixels"] == 1 and out["images"] == 1


@pytest.mark.slow
@pytest.mark.req("SC-008-01")
def test_real_archive_matches_the_dataset_card_counts() -> None:
    root = os.environ.get("PITSTUDIO_MENDELEY_DIR")
    if not root or not Path(root).is_dir():
        pytest.fail("set PITSTUDIO_MENDELEY_DIR to the extracted Mendeley archive (this test runs only with -m slow)")
    out = ingest_mendeley(Path(root))
    assert out["images"] == 960 and out["masks"] == 960 and out["originals_verified"] == 240
    assert out["instances_with_pixels"] == 63_144 and round(out["instances_with_pixels"] / 960, 1) == 65.8
    assert out["groups"] == 72 and out["folds"] == 5 and out["fold_test_originals"] == [48] * 5
