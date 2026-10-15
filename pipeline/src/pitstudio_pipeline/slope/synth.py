"""Event-set stage of case C1 (`s05_synthesize`): seeded Voight events at the observed or nominal SNR."""

from __future__ import annotations

from typing import Any

from pitstudio.slope import events


def synthesize(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Every event of the configuration, validated first (an invalid configuration generates nothing)."""
    docs: list[dict[str, Any]] = []
    events.generate_event_set(config, docs.append)
    return docs
