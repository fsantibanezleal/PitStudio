"""Errors of the calibration protocol (spec 011)."""

from __future__ import annotations


class InvalidCalibrationError(ValueError):
    """A calibration request is invalid (FR-011-30); raised with the reason before any simulation."""
