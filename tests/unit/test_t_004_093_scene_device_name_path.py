# ruff: noqa: E501, PT018, PT017
"""T-004-093: Windows device-name path segments are rejected by the scene loader.

Requirements: FR-004-43.

Oracle: hand calculation (plan.md "FR-004-43"): `con.txt`, `dir/NUL` and `Com3.png` give `path-forbidden`; `console.txt`
is accepted. The reserved names are the spec's list: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, `lpt1` to `lpt9`,
case-insensitive, with or without an extension; `COM0`, `COM10`, `LPT0` are not in the list and are accepted.

Expected API (package `pitstudio_studio.scene.common`, studio environment): `common.check_scene_path(path)` returns None
for an accepted path and raises `common.SceneStageError("path-forbidden")`, message `"path-forbidden: <path> ..."`, when
any segment of `path` (split on `/` and `\\`) is a device name (the segment's name before its first `.`, compared
case-insensitively). `common.check_scene_paths(paths)` checks an iterable and names the first offender.
`common.load_scene_spec(doc, paths=())` validates a scene specification and applies the same check to every path in
`paths` (the file paths a scene specification refers to); it raises `params-invalid` for an invalid document before that.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import common  # noqa: E402

DEVICES = ["con", "prn", "aux", "nul", *[f"com{i}" for i in range(1, 10)], *[f"lpt{i}" for i in range(1, 10)]]


def _forbidden(path: str) -> None:
    with pytest.raises(common.SceneStageError) as exc:
        common.check_scene_path(path)
    assert exc.value.error_class == "path-forbidden" and str(exc.value).startswith("path-forbidden: ")
    assert path in str(exc.value)


@pytest.mark.req("FR-004-43")
@pytest.mark.parametrize(
    "path",
    [
        "con.txt",
        "dir/NUL",
        "Com3.png",
        "con",
        "CON",
        "a/b/aux.usda",
        "x\\y\\prn.json",
        "LPT9",
        "layers/Lpt1.tar.gz",
        "nul.",
        "aux.x.y",
        "dir/com9/file.png",
    ],
)
def test_a_device_name_segment_is_path_forbidden(path: str) -> None:
    _forbidden(path)


@pytest.mark.req("FR-004-43")
@pytest.mark.parametrize(
    "path",
    [
        "console.txt",
        "dir/conx",
        "xcon.png",
        "my.con/x.png",
        "nul0",
        "aux2.txt",
        "comma.txt",
        "COM0",
        "com10.txt",
        "lpt0",
        "lpt",
        "auxiliary/prn_1.png",
        "layers/design.usda",
        "a.b/c.d",
    ],
)
def test_names_that_merely_contain_a_device_name_are_accepted(path: str) -> None:
    assert common.check_scene_path(path) is None


@pytest.mark.req("FR-004-43")
@pytest.mark.parametrize("device", DEVICES)
def test_every_listed_device_name_is_rejected_in_any_case_and_with_any_extension(device: str) -> None:
    for variant in (
        device,
        device.upper(),
        device.title(),
        f"{device}.png",
        f"dir/{device.upper()}.TXT",
        f"{device}\\x",
    ):
        _forbidden(variant)


_ASCII = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
_SEGMENTS = st.one_of(
    st.text(alphabet=_ASCII, min_size=1, max_size=8),
    st.builds(
        lambda d, up, ext: (d.upper() if up else d) + ext,
        st.sampled_from(DEVICES),
        st.booleans(),
        st.sampled_from(["", ".png", ".tar.gz", "x", "0", ".", "-a", "_b"]),
    ),
).filter(lambda s: s.strip(".") != "")  # "." and ".." are traversal segments, not device-name cases


@pytest.mark.req("FR-004-43")
@given(_SEGMENTS)
def test_a_segment_is_rejected_exactly_when_its_stem_is_a_device_name(segment: str) -> None:
    stem = segment.split(".", 1)[0].lower()
    expected_forbidden = stem in DEVICES
    try:
        common.check_scene_path(f"dir/{segment}/file.png")
    except common.SceneStageError as exc:
        assert expected_forbidden and exc.error_class == "path-forbidden"
    else:
        assert not expected_forbidden


@pytest.mark.req("FR-004-43")
def test_check_scene_paths_names_the_first_offender() -> None:
    with pytest.raises(common.SceneStageError) as exc:
        common.check_scene_paths(["ok/a.png", "dir/aux.png", "con.txt"])
    assert "dir/aux.png" in str(exc.value) and "con.txt" not in str(exc.value)
    assert common.check_scene_paths(["ok/a.png", "b/c.usda"]) is None


@pytest.mark.req("FR-004-43")
def test_the_scene_loader_rejects_a_forbidden_path_but_a_bad_document_first() -> None:
    spec = kit.scene_spec()
    assert common.load_scene_spec(spec, paths=["layers/design.usda"]) is not None
    with pytest.raises(common.SceneStageError) as exc:
        common.load_scene_spec(spec, paths=["layers/design.usda", "textures/NUL.png"])
    assert exc.value.error_class == "path-forbidden" and "textures/NUL.png" in str(exc.value)
    bad = dict(spec)
    bad.pop("seed")
    with pytest.raises(common.SceneStageError) as exc2:
        common.load_scene_spec(bad, paths=["con.txt"])
    assert exc2.value.error_class == "params-invalid"
