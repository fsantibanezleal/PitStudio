"""The ownership map of tests/envs.yaml and the collection rule of tests/conftest.py (not a locked test; root environment)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

import conftest as c  # noqa: E402


def test_every_glob_of_the_map_matches_at_least_one_file() -> None:
    files = [p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").rglob("test_*.py")]
    for glob, owner in c.load_owners():
        assert any(c.matches(f, glob) for f in files), f"{owner}: {glob} matches no file"


def test_a_file_is_owned_by_at_most_one_environment() -> None:
    owners = c.load_owners()
    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        rel = path.relative_to(ROOT).as_posix()
        hits = {owner for glob, owner in owners if c.matches(rel, glob)}
        assert len(hits) <= 1, f"{rel} is owned by {sorted(hits)}"


@pytest.mark.parametrize(
    ("path", "owner"),
    [
        ("tests/pipeline/test_t_011_010_gns_model.py", "pipeline"),
        ("tests/unit/test_t_012_015_unet_loss.py", "pipeline"),
        ("tests/property/test_t_011_050_dft_spectral.py", "pipeline"),
        ("tests/unit/test_t_005_010_dem_contact_law.py", "studio"),
        ("tests/unit/test_t_011_034_tape_arm.py", "studio"),
        ("tests/contract/test_t_011_036_calibration_result.py", "studio"),
        ("tests/unit/test_t_011_017_rollout_guards.py", "root"),
        ("tests/property/test_t_011_011_radius_graph.py", "root"),
    ],
)
def test_the_owner_of_known_files(path: str, owner: str) -> None:
    assert c.owner_of(path, c.load_owners()) == owner


def test_an_unknown_environment_name_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PITSTUDIO_TEST_ENV", "gpu")
    with pytest.raises(RuntimeError, match="PITSTUDIO_TEST_ENV"):
        c.running_env()


def test_the_default_environment_is_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PITSTUDIO_TEST_ENV", raising=False)
    assert c.running_env() == "root"
