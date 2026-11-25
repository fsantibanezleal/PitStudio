"""Licence-class rule of the merge step (FR-008-04): share-alike inputs never merge with inputs of another class."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pitstudio.contracts.licence import rank_of
from pitstudio_pipeline.errors import ShareAlikeMerge

SHARE_ALIKE = "share-alike"


def check_merge(inputs: Sequence[Mapping[str, Any]]) -> None:
    """Raise `ShareAlikeMerge` when `inputs` hold a share-alike input and an input of any other class.

    `inputs` are mappings `{"id": str, "licence_class": str}`; the class names are those of spec 001 data-model 5.4
    (`pitstudio.contracts.licence`, which also rejects an unknown class). Share-alike derivatives stay separate outputs.
    """
    share_alike, others = [], []
    for item in inputs:
        cls = item["licence_class"]
        rank_of(cls)  # an unknown class is an error, never silently "other"
        (share_alike if cls == SHARE_ALIKE else others).append(str(item["id"]))
    if share_alike and others:
        raise ShareAlikeMerge([*share_alike, *others])
