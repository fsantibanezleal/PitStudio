# ruff: noqa: E501
"""Typed errors of spec 007. Every one derives from HaulError so callers can catch the family."""

from __future__ import annotations

from pitstudio.haulage.errors import HaulError  # one family with the root-core engines (routing, energy, network)

__all__ = [
    "DisconnectedNetwork",
    "EngineVersionMismatch",
    "EventBudgetExceeded",
    "HaulError",
    "InvalidHorizon",
    "InvalidScenario",
    "InvalidSeed",
    "InvalidTrace",
    "UnsupportedFeature",
]


class EngineVersionMismatch(HaulError):
    """The installed engine differs from the adapter's pin file (FR-007-02).

    `differences` lists (item, pinned, installed) for the version and for every differing module path; an absent file has
    `installed == "missing"`.
    """

    def __init__(self, differences: list[tuple[str, str, str]]) -> None:
        self.differences = list(differences)
        body = "; ".join(
            f"{item}: pinned {pinned}, installed {installed}" for item, pinned, installed in self.differences
        )
        super().__init__(f"engine does not match its pin ({body})")


class InvalidScenario(HaulError):
    """A scenario bundle (or variate request) is hostile (FR-007-03, FR-007-06); `violations` is (JSON pointer, value, rule)."""

    def __init__(self, violations: list[tuple[str, object, str]]) -> None:
        self.violations = list(violations)
        body = "; ".join(f"{path or '<root>'}: {rule} (got {value!r})" for path, value, rule in self.violations)
        super().__init__(f"invalid scenario: {body}")


class InvalidHorizon(HaulError):
    """A bundle whose only violations are at /horizon_s, or a horizon outside (0, 7 days] (FR-007-13)."""

    def __init__(self, violations: list[tuple[str, object, str]]) -> None:
        self.violations = list(violations)
        body = "; ".join(f"{path}: {rule} (got {value!r})" for path, value, rule in self.violations)
        super().__init__(f"invalid horizon: {body}")


class DisconnectedNetwork(HaulError):
    """Some loader or dump is unreachable on the frozen network (FR-007-04); `triples` is (origin, destination, truck class)."""

    def __init__(self, triples: list[tuple[int, int, str]]) -> None:
        self.triples = list(triples)
        body = ", ".join(f"{a}->{b} ({cls})" for a, b, cls in self.triples)
        super().__init__(f"disconnected network, unreachable: {body}")


class UnsupportedFeature(HaulError):
    """A bundle uses a reference-engine feature outside the twin's declared feature set (FR-007-12)."""

    def __init__(self, features: list[str]) -> None:
        self.features = list(features)
        super().__init__(f"unsupported feature(s): {', '.join(self.features)}")


class InvalidSeed(HaulError):
    """The seed is not an integer in [0, 2^63) (FR-007-13)."""


class EventBudgetExceeded(HaulError):
    """A run executed more events than its budget (FR-007-13)."""


class InvalidTrace(HaulError):
    """A trace fails its schema, order, finiteness or window rule (FR-007-42); `section` and `row` name the first offender."""

    def __init__(self, message: str, *, section: str = "trace", row: int | None = None) -> None:
        self.section = section
        self.row = row
        where = section if row is None else f"{section}[{row}]"
        super().__init__(f"invalid trace at {where}: {message}")
