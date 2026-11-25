"""Error classes of the physics stage (spec 005, section 3).

The stage helper reports every class below as the prefix of the stage-result message (`<class>: <detail>`).
"""

from __future__ import annotations

from typing import Any


class PhysicsError(Exception):
    """A physics failure with a machine-readable class and structured details.

    `str(error)` is `f"{error_class}: {detail}"`, the message format of spec 005 (FR-005-07, FR-005-08).
    """

    def __init__(self, error_class: str, detail: str, **details: Any) -> None:
        super().__init__(f"{error_class}: {detail}")
        self.error_class = error_class
        self.detail = detail
        self.details: dict[str, Any] = details
