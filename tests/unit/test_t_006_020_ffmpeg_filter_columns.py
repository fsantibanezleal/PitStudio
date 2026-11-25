# ruff: noqa: E501, PT018
"""T-006-020 (third file): `discover` reads the `-filters` list of FFmpeg 8.1 and of the older three-flag format.

Requirements: FR-006-09.

Oracle: the `-filters` listing printed by the pinned FFmpeg n8.1.3 build (lines copied verbatim: two flag characters,
`TS` or `..`, then the name, the input and output types and the description) and the three-flag listing (`T.C`, `...`)
of earlier builds; the specification's rule that `libvmaf` must be listed.

Expected API: `pitstudio_studio.media.ffmpeg.discover` as in T-006-020; the filter is found whatever the number (2 or 3) of
flag characters before the name, and the legend lines of the listing (`T.. = Timeline support`) name no filter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit as kit
from pitstudio_stagekit import NotRun
from pitstudio_studio.media.ffmpeg import discover

LEGEND = (
    "Filters:\n  T.. = Timeline support\n  .S. = Slice threading\n  A = Audio input/output\n  V = Video input/output\n"
    "  N = Dynamic number and/or type of input/output\n  | = Source or sink filter\n  ------\n"
)
TWO_FLAGS = (
    " TS aap               AA->A      Apply Affine Projection algorithm to first audio stream.\n"
    " .. abench            A->A       Benchmark part of a filtergraph.\n"
    " .. format            V->V       Convert the input video to one of the specified pixel formats.\n"
    " .. libvmaf           VV->V      Calculate the VMAF between two video streams.\n"
    " .. scale             V->V       Scale the input video size and/or convert the image format.\n"
)
THREE_FLAGS = (
    " T.C aap               AA->A      Apply Affine Projection algorithm to first audio stream.\n"
    " ... format            V->V       Convert the input video to one of the specified pixel formats.\n"
    " ... libvmaf           VV->V      Calculate the VMAF between two video streams.\n"
    " .S. scale             V->V       Scale the input video size and/or convert the image format.\n"
)


class Listing(kit.FakeFFmpeg):
    """The fake with a fixed `-filters` text."""

    def __init__(self, text: str, **kw: object) -> None:
        super().__init__(**kw)
        self._text = text

    def __call__(self, argv, **kw):
        if "-filters" in [str(a) for a in argv]:
            self.calls.append([str(a) for a in argv])
            return self._done([str(a) for a in argv], self._text)
        return super().__call__(argv, **kw)


def _discover(tmp_path: Path, text: str):
    exe, sha = kit.install_exe(tmp_path / "bin")
    return discover(
        env={"PITSTUDIO_FFMPEG": str(exe), "PATH": ""},
        runner=Listing(text),
        pinned_sha256=sha,
        driver_version="582.78",
    )


@pytest.mark.req("FR-006-09")
@pytest.mark.parametrize("body", [TWO_FLAGS, THREE_FLAGS], ids=["ffmpeg-8.1-two-flags", "earlier-three-flags"])
def test_libvmaf_is_found_in_either_listing_format(tmp_path: Path, body: str) -> None:
    build = _discover(tmp_path, LEGEND + body)
    assert build.version == "n8.1" and build.major == 8


@pytest.mark.req("FR-006-09")
@pytest.mark.parametrize("body", [TWO_FLAGS, THREE_FLAGS], ids=["ffmpeg-8.1-two-flags", "earlier-three-flags"])
def test_a_listing_without_libvmaf_is_refused_in_either_format(tmp_path: Path, body: str) -> None:
    without = "".join(line for line in body.splitlines(keepends=True) if "libvmaf" not in line)
    with pytest.raises(NotRun) as caught:
        _discover(tmp_path, LEGEND + without)
    assert str(caught.value) == "FFmpeg lacks the filter libvmaf"


@pytest.mark.req("FR-006-09")
def test_a_legend_line_or_a_description_is_not_a_filter(tmp_path: Path) -> None:
    only_legend = LEGEND + " .. scale             V->V       Mentions libvmaf in its description.\n"
    with pytest.raises(NotRun) as caught:
        _discover(tmp_path, only_legend)
    assert str(caught.value) == "FFmpeg lacks the filter libvmaf"
