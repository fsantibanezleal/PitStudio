"""T-009-016 (sdg-gate): a frame is a function of its row only, at the smallest subframe count that allows it.

Requirements: FR-009-02, NFR-009-03.

Probes of 2026-11-23 on Isaac Sim 6.1 (queue jobs 88f and 88g, report sdg-gate-2026-11-23): the 6 history rows of the
gate sample rendered forward and in reverse order (every row has two different predecessors), maximum difference of the
mean luminance over the 6 rows, in 8-bit levels, per subframe count 8 / 16 / 32 / 64:

| variant                                              |  8   | 16   | 32   | 64   |
| defaults (`/rtx/post/aa/op` dlss, temporal on)       | 2.17 | 1.03 | 0.50 | 0.45 |
| `aa/op` none                                         | 1.56 | 0.96 | 0.66 | 0.47 |
| `aa/op` taa / fxaa / rtxaa                           | 1.44 / 1.33 / 1.42 at 8 | | | |
| no temporal: `aa/op` none, indirect diffuse denoiser | 1.25 | 0.85 | 0.53 | 0.34 |
| temporal off, spatial cache `temporalAlpha` 1 and    |      |      |      |      |
| `temporalReuse` 1                                    |      |      |      |      |

Seconds per frame at 8 subframes: defaults 1.32, `aa/op` none 0.93, no temporal 1.20. The limit is 2.0 levels (decision
5 of the sdg-geometry brief): the defaults need 16 subframes (1.20 s per frame); with `aa/op` none 8 subframes meet it
at 0.93 s per frame, the cheapest variant at the smallest count, so that is the choice. The setting is the one of the
installed schema `omni.usd.schema.render_settings.rtx-1.0.3` (generatedSchema.usda line 3118) and is set on every row,
so a row never inherits what an earlier row left in the carb tree.

Oracles: the setting names and values of the schema, the same keys for every row, the frame-row independence.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_isaac.sdg import render_settings, scene_render  # noqa: E402
from test_t_009_016_exposure_fog import _u_dr  # noqa: E402
from test_t_009_016_shard_driver import _row  # noqa: E402

AA_OP = "/rtx/post/aa/op"
DENOISER = "/rtx/indirectDiffuse/denoiser/temporal/enabled"
CACHE_ALPHA = "/rtx/raytracing/lightcache/spatialCache/temporalAlpha"
CACHE_REUSE = "/rtx/raytracing/lightcache/spatialCache/temporalReuse"


@pytest.mark.req("FR-009-02")
def test_the_temporal_super_resolution_of_the_renderer_is_switched_off() -> None:
    s = render_settings.history_settings()
    assert s == {AA_OP: 0}  # token `none` is the first of none, taa, fxaa, dlss, rtxaa (the default 3 is dlss)


@pytest.mark.req("FR-009-02")
def test_every_row_sets_every_history_setting_so_no_row_inherits_the_state_of_another() -> None:
    structured = render_settings.render_settings(_row())
    unstructured = render_settings.render_settings(_row("pit-u-00000", arm="unstructured") | {"dr": _u_dr(2.0)})
    for s in (structured, unstructured):
        for key, value in render_settings.history_settings().items():
            assert s[key] == value


@pytest.mark.req("FR-009-02")
def test_the_history_settings_are_a_function_of_nothing_but_the_module() -> None:
    before = render_settings.history_settings()
    row = _row()
    other = copy.deepcopy(row)
    other["dr"]["dust_extinction_per_km"] = 9.0
    render_settings.render_settings(other)
    assert render_settings.history_settings() == before
    assert render_settings.history_settings() is not render_settings.history_settings()  # a fresh dict: no shared state


@pytest.mark.req("NFR-009-03")
def test_the_subframe_count_is_the_smallest_that_meets_the_history_limit() -> None:
    assert scene_render.RT_SUBFRAMES == 8  # 1.56 levels at 8 subframes with `aa/op` none, the limit is 2.0
    assert render_settings.HISTORY_LIMIT_LEVELS == 2.0
    assert render_settings.HISTORY_MEASURED_LEVELS[8] < render_settings.HISTORY_LIMIT_LEVELS
    assert render_settings.HISTORY_MEASURED_LEVELS == {8: 1.56, 16: 0.96, 32: 0.66, 64: 0.47}
    assert min(render_settings.HISTORY_MEASURED_LEVELS) == scene_render.RT_SUBFRAMES


@pytest.mark.req("NFR-009-03")
def test_the_render_settings_model_records_the_history_choice() -> None:
    doc = render_settings.describe()
    assert doc["history"]["settings"] == render_settings.history_settings()
    assert doc["history"]["rt_subframes"] == scene_render.RT_SUBFRAMES
    assert doc["history"]["max_mean_diff_levels"] == 1.56
