"""Error classes of the media stage `st56_encode` (spec 006, section 3).

Every error carries its class as the prefix of its message (`"<error_class>: <detail>"`): the stage helper reports
it in the detail of a failed stage result with `error_class: unknown`.
"""

from __future__ import annotations


class EncodeError(Exception):
    """Base class: `error_class` is a stable kebab-case name, `str(e)` starts with `"<error_class>: "`."""

    error_class = "encode-error"

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(f"{self.error_class}: {detail}")


class VmafUnreachable(EncodeError):
    """No constant-quality setting meets the VMAF targets; `best` is the trial with the highest VMAF mean."""

    error_class = "vmaf-unreachable"

    def __init__(self, detail: str = "", best: object | None = None) -> None:
        self.best = best
        super().__init__(detail)


class OverBudget(EncodeError):
    """A clip pair or a poster exceeds its byte budget; `best` holds the final measurements."""

    error_class = "over-budget"

    def __init__(self, detail: str = "", best: object | None = None) -> None:
        self.best = best
        super().__init__(detail)


class DecodeFailed(EncodeError):
    error_class = "decode-failed"


class FramesInvalid(EncodeError):
    error_class = "frames-invalid"


class NameInvalid(EncodeError):
    error_class = "name-invalid"


class NotPublishable(EncodeError):
    error_class = "not-publishable"


class ProfileInvalid(EncodeError):
    error_class = "profile-invalid"
