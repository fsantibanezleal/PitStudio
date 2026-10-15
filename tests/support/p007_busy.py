# ruff: noqa: E501
"""Second test-support module of spec 007: a busy smoke-network bundle builder shared by the metamorphic, oracle and parity tests (locked with its first user, T-007-018).

Nothing here imports the code under test. Built on `p007_kit` (locked with T-007-003).
"""

from __future__ import annotations

import p007_kit as kit


def busy_bundle(
    dispatcher: str = "sptf",
    mode: str = "fast",
    n_trucks: int = 6,
    horizon: float = 3 * 3600.0,
    profile: str = "deterministic",
    warmup: float = 0.0,
) -> dict:
    """The spec's smoke network (2 loaders, 2 dumps, 1 junction) with `n_trucks` CAT_793F trucks alternating between the loaders, both loaders declaring dump 4."""
    b = kit.smoke_bundle()
    b["dispatcher"] = {"id": dispatcher}
    b["mode"] = mode
    b["horizon_s"] = horizon
    b["kpi_window"] = {"warmup_s": warmup}
    b["fleet"] = [
        {"id": i + 1, "truck_class": "CAT_793F", "start_loader": 1 if i % 2 == 0 else 2} for i in range(n_trucks)
    ]
    for ld in b["loaders"]:
        ld["destination_dump"] = 4
    if profile == "engine":
        kit.with_engine_profile(b)
    return b
