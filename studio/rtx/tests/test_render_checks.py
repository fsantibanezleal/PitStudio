# SPDX-License-Identifier: Apache-2.0

"""The image checks of the render run: luminance, noise floor, distinct stills, light gain, PNG read-back."""

from __future__ import annotations

import numpy as np
import pytest
from pitstudio_rtx.render.checks import distinct_threshold, first_clash, gain_for, luminance, mean_abs_diff
from pitstudio_rtx.render.imageio import read_png, write_png


def grey(value: int, shape=(4, 6)) -> np.ndarray:
    return np.full((*shape, 3), value, dtype=np.uint8)


def test_luminance_is_the_mean_linear_rec709_luma_of_the_srgb_image():
    assert luminance(grey(0)) == pytest.approx(0.0)
    assert luminance(grey(255)) == pytest.approx(1.0)
    # hand calculation: ((128/255 + 0.055) / 1.055) ** 2.4 = 0.21586 for a neutral grey
    assert luminance(grey(128)) == pytest.approx(0.21586, abs=1e-4)
    red = np.zeros((2, 2, 3), dtype=np.uint8)
    red[..., 0] = 255
    assert luminance(red) == pytest.approx(0.2126)


def test_mean_abs_difference_is_in_grey_levels_and_symmetric():
    assert mean_abs_diff(grey(10), grey(14)) == 4.0 == mean_abs_diff(grey(14), grey(10))
    half = grey(0)
    half[:, :3] = 8
    assert mean_abs_diff(half, grey(0)) == 4.0
    with pytest.raises(ValueError, match="shape"):
        mean_abs_diff(grey(0), grey(0, (2, 2)))


def test_the_distinct_threshold_is_a_multiple_of_the_noise_floor_with_a_minimum():
    assert distinct_threshold(0.0, minimum=2.0, factor=10.0) == 2.0  # a deterministic renderer: the minimum
    assert distinct_threshold(0.5, minimum=2.0, factor=10.0) == 5.0
    assert distinct_threshold(3.0, minimum=2.0, factor=10.0) == 30.0


def test_first_clash_names_the_still_that_is_too_close_to_the_candidate():
    others = {"a": grey(10), "b": grey(100)}
    assert first_clash(grey(101), others, 5.0) == ("b", 1.0)
    assert first_clash(grey(60), others, 5.0) is None
    assert first_clash(grey(10), {}, 5.0) is None


def test_gain_for_scales_the_light_to_the_target_and_is_bounded():
    assert gain_for(0.5, 0.25, 1.0, limit=32.0) == pytest.approx(0.5)
    assert gain_for(0.05, 0.25, 2.0, limit=32.0) == pytest.approx(10.0)
    assert gain_for(0.0001, 0.25, 1.0, limit=32.0) == 32.0
    assert gain_for(0.9, 0.25, 1 / 32, limit=32.0) == pytest.approx(1 / 32)


def test_png_round_trip(tmp_path):
    image = np.random.default_rng(5).integers(0, 256, (7, 9, 3), dtype=np.uint8)
    write_png(tmp_path / "x.png", image)
    assert np.array_equal(read_png(tmp_path / "x.png"), image)
    (tmp_path / "bad.png").write_bytes(b"not a png")
    with pytest.raises(ValueError, match="PNG"):
        read_png(tmp_path / "bad.png")
