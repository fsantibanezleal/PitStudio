# ruff: noqa: E501
"""The honesty stamp of every A1 and A2 artefact (FR-007-41, FR-000-09): the label and the known DES cycle-time bias note.

The strings are the text pinned by `contracts/des-trace.schema.json`; no C2ST or TSTR claim is ever made for a haulage output.
"""

from __future__ import annotations

LABEL = "calibrated synthetic — not validated against real data"  # the dash is U+2014
BIAS_NOTE = (
    "Known DES bias: simulated truck cycle times tend to underestimate short hauls and overestimate long hauls; "
    "no real haul telemetry exists to correct it."
)


def stamp() -> dict[str, str]:
    """The `honesty` object of a trace, evaluation table or energy table header."""
    return {"label": LABEL, "bias_note": BIAS_NOTE}
