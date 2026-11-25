"""The Mendeley fragment set (`mendeley-78ht3pjsr4`): augmentation structure, instance counts, ingestion (FR-008-29).

The set holds 80 photographs, three crops each (files k, k + 80, k + 160 for k = 1 ... 80: 240 originals) and, for every
original k, a horizontal flip (k + 240), a vertical flip (k + 480) and a 180-degree rotation (k + 720). The group key of
spec 008 depends on that dihedral structure, so it is checked here, exactly, on the foreground of the masks; the crop
structure is a recorded finding of the dataset card and is not checked (spec 008 section 7).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from pitstudio_pipeline.errors import AugmentationStructureBroken
from pitstudio_pipeline.ingest.files import validate_image, validate_mask
from pitstudio_pipeline.splits import N_FILES, N_FOLDS, N_ORIGINALS, build_mendeley_split

DIHEDRAL = (
    (N_ORIGINALS, np.fliplr, "horizontal flip"),
    (2 * N_ORIGINALS, np.flipud, "vertical flip"),
    (3 * N_ORIGINALS, lambda m: np.rot90(m, 2), "180-degree rotation"),
)


def _foreground(mask: Any) -> np.ndarray:
    return np.asarray(mask) > 0


def check_augmentation_structure(label_masks: Mapping[int, Any], cv2_masks: Mapping[int, Any]) -> None:
    """Raise `AugmentationStructureBroken` unless the dihedral copies and the two mask kinds agree exactly.

    Both mappings give, for every file number 1 ... 960, the `label.png` and the `cv2_mask` instance mask. The
    foreground (label > 0) of file k + 240, k + 480 and k + 720 must equal the horizontal flip, the vertical flip and
    the 180-degree rotation of the foreground of file k (k = 1 ... 240), and the two mask kinds must have the same
    foreground and shape for all 960 files. Label values may differ between copies: only the foreground counts.
    """
    missing = [k for k in range(1, N_FILES + 1) if k not in label_masks or k not in cv2_masks]
    if missing:
        raise AugmentationStructureBroken(f"{len(missing)} file(s) have no mask, first: {missing[0]}")
    for k in range(1, N_FILES + 1):
        label, cv2 = _foreground(label_masks[k]), _foreground(cv2_masks[k])
        if label.shape != cv2.shape or not np.array_equal(label, cv2):
            raise AugmentationStructureBroken(f"file {k}: the cv2_mask and label.png foregrounds differ")
    for k in range(1, N_ORIGINALS + 1):
        original = _foreground(label_masks[k])
        for offset, transform, name in DIHEDRAL:
            copy = _foreground(label_masks[k + offset])
            expected = transform(original)
            if copy.shape != expected.shape or not np.array_equal(copy, expected):
                raise AugmentationStructureBroken(f"file {k + offset} is not the {name} of file {k}")


def summarize_masks(label_masks: Mapping[int, Any]) -> dict[str, Any]:
    """Counts of the label masks: images, instances with pixels (distinct labels above 0, summed) and their mean."""
    images, instances = 0, 0
    for key in label_masks:
        mask = np.asarray(label_masks[key])
        instances += int(np.unique(mask[mask > 0]).size)
        images += 1
    return {
        "images": images,
        "instances_with_pixels": instances,
        "mean_instances_per_image": instances / images if images else 0.0,
    }


class _LazyMasks(Mapping[int, np.ndarray]):
    """File number -> mask array, read from disk on access (960 masks of 512 x 512 would not need to sit in memory)."""

    def __init__(self, paths: Mapping[int, Path]) -> None:
        self._paths = dict(paths)

    def __getitem__(self, key: int) -> np.ndarray:
        with Image.open(self._paths[key]) as image:
            return np.asarray(image).copy()

    def __iter__(self) -> Iterator[int]:
        return iter(sorted(self._paths))

    def __len__(self) -> int:
        return len(self._paths)


def _annotated_root(directory: Path) -> Path:
    for candidate in (directory, directory / "Annotated data", *directory.glob("*/Annotated data")):
        if (candidate / "pic").is_dir():
            return candidate
    raise FileNotFoundError(f"no `Annotated data/pic` folder under {directory}")


def _numbered(folder: Path, pattern: str, key: Callable[[Path], str]) -> dict[int, Path]:
    return {int(key(p)): p for p in sorted(folder.glob(pattern)) if key(p).isdigit()}


def ingest_mendeley(directory: Path | str) -> dict[str, Any]:
    """Check the extracted archive (local, real data): validators, augmentation structure, counts, groups and folds.

    `directory` holds `Annotated data/` (directly, or one level down as `Research Data/Annotated data/`) with the
    folders `pic` (NNN.jpg), `labelme_json/NNN_json/label.png` and `cv2_mask` (NNN.png). Any failed check raises.
    """
    root = _annotated_root(Path(directory))
    pics = _numbered(root / "pic", "*.jpg", lambda p: p.stem)
    labels = _numbered(root / "labelme_json", "*_json/label.png", lambda p: p.parent.name.removesuffix("_json"))
    cv2 = _numbered(root / "cv2_mask", "*.png", lambda p: p.stem)
    for path in pics.values():
        validate_image(path, file=f"pic/{path.name}")
    for path in labels.values():
        validate_mask(path, file=f"labelme_json/{path.parent.name}/label.png")
    label_masks, cv2_masks = _LazyMasks(labels), _LazyMasks(cv2)
    check_augmentation_structure(label_masks, cv2_masks)
    counts = summarize_masks(label_masks)
    split = build_mendeley_split(0)
    return {
        "images": len(pics),
        "masks": len(labels),
        "originals_verified": N_ORIGINALS,
        "instances_with_pixels": counts["instances_with_pixels"],
        "groups": len(split["groups"]),
        "folds": N_FOLDS,
        "fold_test_originals": [len(fold["test"]) for fold in split["folds"]],
    }
