"""T-009-106: the subframe count is the smallest of the probe grid that keeps a frame independent of its predecessor.

Requirements: FR-009-60 (supersedes the count of the earlier history probe, made under a light that was not
physically proportioned and with a first-frame black sky).

Evidence (report sdg-finish-2026-11-23, jobs 8q and the earlier probes): the six history rows rendered in two orders
under the physical light, the metered exposure, the fog on every row and the primed first row; the largest difference
of a row's mean luminance between the orders, in 8-bit levels, at 8, 16, 32 and 64 subframes.

Expected (`pitstudio_isaac.sdg.render_settings`, `scene_render`):
- `HISTORY_MEASURED_LEVELS == {8: 6.65, 16: 3.98, 32: 2.49, 64: 1.16}` and `HISTORY_LIMIT_LEVELS == 2.0`;
- `RT_SUBFRAMES` is the smallest count of the grid whose measured level is within the limit: 64;
- `describe()` records the count with its measured level.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_isaac.sdg import render_settings, scene_render  # noqa: E402


@pytest.mark.req("FR-009-60")
def test_the_measured_levels_are_those_of_the_probe_under_the_physical_light() -> None:
    assert render_settings.HISTORY_MEASURED_LEVELS == {8: 6.65, 16: 3.98, 32: 2.49, 64: 1.16}
    assert render_settings.HISTORY_LIMIT_LEVELS == 2.0


@pytest.mark.req("FR-009-60")
def test_the_count_is_the_smallest_of_the_grid_within_the_limit() -> None:
    within = [
        n
        for n, lv in sorted(render_settings.HISTORY_MEASURED_LEVELS.items())
        if lv <= render_settings.HISTORY_LIMIT_LEVELS
    ]
    assert within
    assert scene_render.RT_SUBFRAMES == within[0] == 64
    assert render_settings.RT_SUBFRAMES == scene_render.RT_SUBFRAMES


@pytest.mark.req("FR-009-60")
def test_the_description_records_the_count_and_its_level() -> None:
    h = render_settings.describe()["history"]
    assert h["rt_subframes"] == 64
    assert h["max_mean_diff_levels"] == 1.16
    assert h["limit_levels"] == 2.0
