"""Error classes of the surrogate stages (spec 011). Every one is a ValueError so callers can catch the family."""

from __future__ import annotations


class InvalidFieldInputError(ValueError):
    """The FNO received an input of the wrong shape, channel order, finiteness or patch (FR-011-40)."""


class DatasetError(ValueError):
    """A dataset cannot be built or split under the rules of FR-011-03 / FR-011-34 / FR-011-52."""


class RolloutFileError(ValueError):
    """A rollout file fails `granular-rollout.schema.json` or its payload checks (FR-011-14); `reason` names the cause."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class FieldFileError(ValueError):
    """A field file fails `field-dataset.schema.json` or its payload checks (FR-011-41); `reason` names the cause."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class EvaluationError(ValueError):
    """An evaluation input is inconsistent (counts, names, shapes); nothing is scored."""


class ExportError(ValueError):
    """An export cannot proceed or its graph fails a check (operator whitelist, parity, schema)."""
