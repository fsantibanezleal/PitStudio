"""The licence-class lattice (FR-001-18, FR-001-19, data-model 5.4).

Total order, lowest to highest: public-domain < open-no-attribution < own < attribution < share-alike < display-only
< reference-only. The class of a derivative is the maximum of ``own`` and the classes of its inputs.
"""

from __future__ import annotations

from collections.abc import Iterable

from pitstudio.contracts.io import ContractError

LICENCE_ORDER = (
    "public-domain",
    "open-no-attribution",
    "own",
    "attribution",
    "share-alike",
    "display-only",
    "reference-only",
)
RANK = {name: rank for rank, name in enumerate(LICENCE_ORDER)}
NO_ATTRIBUTION_CLASSES = frozenset({"public-domain", "open-no-attribution", "own"})


def rank_of(licence_class: str) -> int:
    """Position of a class in the lattice; an unknown class raises ``ContractError``."""
    try:
        return RANK[licence_class]
    except KeyError, TypeError:
        raise ContractError(f"unknown licence class {str(licence_class)[:64]!r}") from None


def licence_class_of(classes: Iterable[str]) -> str:
    """The class of an output made from inputs of ``classes``: ``max_rank({own} | classes)``."""
    best = RANK["own"]
    for name in classes:
        best = max(best, rank_of(name))
    return LICENCE_ORDER[best]


# data-model 5.2: the licence classes a source of a given SPDX id may have, by kind (real | synthetic)
SOURCE_CLASSES: dict[tuple[str, str], frozenset[str]] = {
    ("LicenseRef-USGov-PD", "real"): frozenset({"public-domain"}),
    ("CC0-1.0", "real"): frozenset({"open-no-attribution"}),
    ("DL-DE-ZERO-2.0", "real"): frozenset({"open-no-attribution"}),
    ("CC-BY-4.0", "real"): frozenset({"attribution"}),
    ("LicenseRef-Copernicus-CLMS", "real"): frozenset({"attribution"}),
    ("CC-BY-SA-3.0", "real"): frozenset({"share-alike"}),
    ("CC-BY-SA-4.0", "real"): frozenset({"share-alike"}),
    ("CC-BY-4.0", "synthetic"): frozenset({"own"}),
    ("Apache-2.0", "synthetic"): frozenset({"own"}),
    ("LicenseRef-NVIDIA-Open-Model", "synthetic"): frozenset({"display-only"}),
}
SHARE_ALIKE_SPDX = frozenset({"CC-BY-SA-3.0", "CC-BY-SA-4.0"})


def source_class_of(spdx: str, kind: str) -> str | None:
    """The (highest-ranked) class a source of this SPDX id and kind may carry, or None when the pair is not allowed."""
    allowed = SOURCE_CLASSES.get((spdx, kind))
    return max(allowed, key=RANK.__getitem__) if allowed else None


def derivative_problems(
    artefact_id: str, declared_class: str, declared_spdx: str, inputs: Iterable[tuple[str, str, str | None]]
) -> list[tuple[str, str]]:
    """Rule findings for one published artefact: (rule id, message) of FR-001-18 and FR-001-19.

    ``inputs`` holds (input id, licence class, SPDX id or None) of every input whose class is known.
    """
    known = list(inputs)
    problems: list[tuple[str, str]] = []
    computed = licence_class_of(cls for _, cls, _ in known)
    if computed != declared_class:
        problems.append(
            (
                "FR-001-18",
                f"artefact {artefact_id}: declared licence_class {declared_class} but its inputs give {computed}",
            )
        )
    for input_id, cls, _ in known:
        if cls == "reference-only":
            problems.append(
                ("FR-001-19", f"artefact {artefact_id}: input {input_id} is reference-only and cannot be published")
            )
    share_alike = {spdx for _, cls, spdx in known if cls == "share-alike" and spdx}
    if len(share_alike) > 1:
        problems.append(
            (
                "FR-001-19",
                f"artefact {artefact_id}: inputs carry different share-alike ids ({', '.join(sorted(share_alike))})",
            )
        )
    elif len(share_alike) == 1 and declared_spdx not in share_alike:
        (only,) = share_alike
        problems.append(
            ("FR-001-19", f"artefact {artefact_id}: spdx {declared_spdx} differs from the share-alike input's {only}")
        )
    return problems
