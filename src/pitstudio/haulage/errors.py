# ruff: noqa: E501
"""Typed errors of the root-core haulage engines (spec 007). Every one derives from HaulError so callers can catch the family."""

from __future__ import annotations

from typing import Any


class HaulError(Exception):
    """Base class of every typed error of spec 007 (the pipeline adapter's errors derive from it too)."""


class InvalidDEM(HaulError):
    """A DEM fails FR-007-36: `cell` is the first offending cell (row, col) in row-major order or None, `count` the number of
    offending cells (1 for a scalar field), `field` one of "z", "cell_m", "nodata" or "shape"."""

    def __init__(self, field: str, message: str, *, cell: tuple[int, int] | None = None, count: int = 1) -> None:
        self.field, self.cell, self.count = field, cell, count
        where = f" first at ({cell[0]}, {cell[1]})" if cell is not None else ""
        super().__init__(f"invalid DEM, {field}: {message};{where} {count} offending cell(s)")


class InvalidRouteRequest(HaulError):
    """A routing request fails FR-007-36 or FR-007-45: `field` names the offending argument and `value` is its value."""

    def __init__(self, field: str, value: Any, message: str) -> None:
        self.field, self.value = field, value
        text = repr(value)
        super().__init__(f"invalid route request, {field}={text[:80]}: {message}")


class InvalidRouteInput(HaulError):
    """A route-energy or network-builder input fails FR-007-45: `field` names it and `value` is its value."""

    def __init__(self, field: str, value: Any, message: str) -> None:
        self.field, self.value = field, value
        text = repr(value)
        super().__init__(f"invalid route input, {field}={text[:80]}: {message}")


class MissingKnowledgeRow(HaulError):
    """A physical constant has no row in the `minephys` knowledge tables, so no default exists (FR-007-40): the caller must
    supply it explicitly. `names` lists the constants."""

    def __init__(self, names: list[str]) -> None:
        self.names = list(names)
        super().__init__(
            "no minephys knowledge-table row for: "
            + ", ".join(self.names)
            + "; supply these constants explicitly (they are listed as inputs, never defaulted)"
        )


class DisconnectedNetwork(HaulError):
    """The network builder found loader-dump pairs with no feasible route; `pairs` is (loader id, dump id)."""

    def __init__(self, pairs: list[tuple[int, int]]) -> None:
        self.pairs = list(pairs)
        super().__init__("no feasible route for (loader, dump): " + ", ".join(f"({a}, {b})" for a, b in self.pairs))
