"""Error classes of the data pipeline stages s00 to s20 (spec 008).

Every class names the thing that was refused (source id, member, record) so a report or a log line can show it; none of
them carries a secret value.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RegistryViolation:
    """One violation of the source registry: the entry id, the JSON pointer and the rule that failed."""

    entry_id: str | None
    pointer: str
    rule: str

    def __str__(self) -> str:
        who = f"entry {self.entry_id}: " if self.entry_id else ""
        return f"{who}{self.pointer or '/'}: {self.rule}"


class RegistryError(Exception):
    """The whole registry is rejected (FR-008-02): `violations` lists every one."""

    def __init__(self, violations: Sequence[RegistryViolation]) -> None:
        self.violations = list(violations)
        shown = "; ".join(str(v) for v in self.violations[:5])
        more = f" (and {len(self.violations) - 5} more)" if len(self.violations) > 5 else ""
        super().__init__(f"source registry rejected, {len(self.violations)} violation(s): {shown}{more}")


class ChecksumMismatch(Exception):
    """A file's SHA-256 or byte count differs from the registry (FR-008-06)."""

    def __init__(
        self,
        source: str,
        name: str,
        *,
        expected_sha256: str | None,
        actual_sha256: str,
        expected_bytes: int | None,
        actual_bytes: int,
    ) -> None:
        self.source, self.name = source, name
        self.expected_sha256, self.actual_sha256 = expected_sha256, actual_sha256
        self.expected_bytes, self.actual_bytes = expected_bytes, actual_bytes
        super().__init__(
            f"{source}/{name}: checksum mismatch (expected sha256 {expected_sha256}, got {actual_sha256}; "
            f"expected {expected_bytes} bytes, got {actual_bytes})"
        )


class PublisherChecksumMismatch(Exception):
    """The checksum the publisher states for a file differs from the computed one (FR-008-07)."""


class UnpinnedSource(Exception):
    """A file has no pinned SHA-256 and `--pin` was not given, or a publishable run would use it (FR-008-08)."""


class Oversize(Exception):
    """The server announced or delivered more bytes than the registry declares (FR-008-10)."""


class InsufficientDisk(Exception):
    """Free space at the target is below 1.2 x (bytes + uncompressed bytes) (FR-008-10)."""


class UnsafePath(Exception):
    """The local file name derived from the URL is unsafe (FR-008-11)."""


class InsecureRedirect(Exception):
    """A redirect led to a non-HTTPS URL (FR-008-11)."""


class DownloadFailed(Exception):
    """A transfer failed after the retries, or with a non-retryable HTTP status (FR-008-12)."""


class UnsafeDataRoot(Exception):
    """PITSTUDIO_DATA resolves inside the working tree outside the git-ignored data folders (FR-008-15)."""


class UnsafeArchive(Exception):
    """An archive member is hostile, or the size cap is exceeded (FR-008-19); `member` names it."""

    def __init__(self, message: str, member: str | None = None) -> None:
        self.member = member
        super().__init__(f"{message} (member: {member})" if member is not None else message)


class ShareAlikeMerge(Exception):
    """Share-alike inputs would be merged with inputs of another class (FR-008-04); `sources` names them."""

    def __init__(self, sources: Iterable[str]) -> None:
        self.sources = sorted(set(sources))
        super().__init__("share-alike inputs cannot be merged with other classes: " + ", ".join(self.sources))


class IngestionRejected(Exception):
    """An input failed validation (FR-008-21, FR-008-24, FR-008-48): `violations` are ingestion-report violations."""

    def __init__(self, violations: Sequence[dict[str, Any]]) -> None:
        self.violations = list(violations)
        first = self.violations[0] if self.violations else {}
        super().__init__(
            f"input rejected, {len(self.violations)} violation(s); first: {first.get('file')} "
            f"row {first.get('row')} field {first.get('field')}: {first.get('rule')}"
        )


class UnitError(ValueError):
    """A unit conversion got a non-finite value, an unknown unit pair or would overflow (FR-008-46)."""


class LinksInvalid(ValueError):
    """The Mendeley similarity links are malformed (FR-008-28); `code` is `links-invalid`."""

    code = "links-invalid"

    def __init__(self, detail: str) -> None:
        super().__init__(f"links-invalid: {detail}")


class AugmentationStructureBroken(Exception):
    """The Mendeley flips and rotation or the two mask kinds disagree (FR-008-29)."""


class SplitIntegrityError(Exception):
    """A split file is not trustworthy (FR-008-47); `record` is the first offending record id or None."""

    def __init__(self, message: str, record: str | None = None) -> None:
        self.record = record
        super().__init__(f"{message} (record: {record})" if record is not None else message)


class HonestyRuleViolation(Exception):
    """A C2ST or TSTR verdict was attached to an unvalidated or descriptive-only set (FR-008-37)."""


class ModelPinMismatch(Exception):
    """The embedding weights, revision or licence differ from the pin (FR-008-41)."""
