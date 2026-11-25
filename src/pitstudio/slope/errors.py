"""Errors shared by the C1 forecasting cores (spec 010)."""

from __future__ import annotations


class InvalidWindowError(ValueError):
    """A forecaster received a window it cannot use: wrong length, shape or dtype, a non-finite value after
    pre-processing, or no positive velocity at all (FR-010-29). No time to failure is ever returned for it."""
