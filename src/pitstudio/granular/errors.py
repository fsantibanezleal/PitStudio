"""Error classes of the granular surrogate cores (spec 011)."""

from __future__ import annotations


class InvalidGraphError(ValueError):
    """The graph builder or the GNS step received an invalid input (FR-011-15); no graph or acceleration is returned."""


class RolloutError(ValueError):
    """A rollout, or one of its steps, is invalid; `error_class` is the stable class name of the failure."""

    def __init__(self, error_class: str, detail: str) -> None:
        super().__init__(f"{error_class}: {detail}")
        self.error_class = error_class
        self.detail = detail
