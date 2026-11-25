"""T-017-025: optional MineLib `marvin`: value check, share-alike handling, "Not run" paths (pipeline).

Requirements: FR-017-23, FR-017-24, SC-017-05.

Spec: specs/017-planning-survey/spec.md
- FR-017-23 (optional): where the MineLib `marvin` instance is fetched (`s00_download`, SHA-256 pinned at first
  download), its UPIT value from `marvin.blocks`, `marvin.prec` and `marvin.upit` equals the published best-known
  value
  1,415,655,436, and every derived artefact is a separate manifest entry licensed CC BY-SA 3.0 carrying the
  attribution
  text of the dataset card verbatim; the raw files are never committed or re-hosted;
- FR-017-24: if the MineLib host is unreachable, a file fails its pinned SHA-256, or a file fails to parse, E1
  shows the
  MineLib check as "Not run -- <reason>" (an em dash in the label) and continues on the `oreblocks` deposits;
- SC-017-05 (optional): UPIT value = 1,415,655,436 (oracle test).
Edge case of section 7: if the own pit value and all three oracles agree on a value different from 1,415,655,436, the
report states that the published value is contradicted by three independent solvers.
plan.md test strategy rows FR-017-23 (the published best-known UPIT value of the MineLib `marvin` page) and FR-017-24
(a host stub that refuses connections, files with a wrong SHA-256, unparseable files).

Oracles:
- the published value 1,415,655,436 (MineLib instance page `minelib.org/v1/marvin.xhtml`, read 2026-10-07 by the spec
  author; the real files are not fetched by the tests: UNVERIFIED here, hence the fixture below);
- a tiny MineLib-format instance written by `oreblocks.write_minelib` (the reference writer of the `.blocks / .prec /
  .upit` formats) from a 3 x 3 x 2 grid with integer block values chosen in the test; its UPIT value is computed by an
  independent solver in the test (networkx maximum flow, minimal residual-reachable closure) and is the expected value
  that the check must reproduce, so that the check logic is verified without the licensed data;
- SHA-256 digests by `hashlib`; fake fetchers (a function returning the fixture bytes, one raising `ConnectionError`,
  one returning altered bytes, one returning garbage with the right digest).

Expected public API (module `pitstudio_pipeline.planning.minelib`, `pipeline/` environment):
    MARVIN_PUBLISHED_UPIT = 1_415_655_436
    MARVIN_FILES = ("marvin.blocks", "marvin.prec", "marvin.upit")
    MARVIN_LICENCE = {"spdx": "CC-BY-SA-3.0", "licence_class": "share-alike"}
    RAW_SUFFIXES = (".blocks", ".prec", ".upit", ".cpit", ".pcpsp")
    class RawMinelibFile(Exception)         # a raw MineLib file must never become a committed / hosted artefact
    @dataclass MarvinReport: own_value: int, published_value: int, status: str
        status "match" (own value == published), "mismatch" (own != published and the oracles do not all agree with
        the own value), "published-contradicted" (own value and every oracle value agree and differ from the published
        one); message: str ("contradicted by three independent solvers" in the last case).
    check_marvin(files: Mapping[str, bytes], *, published_value: int = MARVIN_PUBLISHED_UPIT,
                 oracle_values: Mapping[str, int] | None = None) -> MarvinReport
        files: name -> bytes for the three files (names MARVIN_FILES or any ``<name>.blocks/.prec/.upit`` trio); the
        own value is the maximum-closure value (rounded to an integer) of the `.upit` block values under the `.prec`
        arcs (a block requires the blocks listed in its `.prec` row).
    @dataclass MarvinOutcome: status ("ok" | "not_run"), label (str | None), report (MarvinReport | None)
    run_marvin_check(fetch, pins: dict[str, str], *, published_value: int = MARVIN_PUBLISHED_UPIT) -> MarvinOutcome
        `fetch(name) -> bytes` downloads one file; `pins` maps file name -> SHA-256 (empty on the first run: the first
        successful download pins the digests into `pins`). A fetch that raises OSError / TimeoutError, a digest
        that does
        not match its pin, or bytes that do not parse give status "not_run" and label "Not run â€” <reason>" with
        the reason naming "unreachable", "sha256" or "parse"; nothing else is raised.
    marvin_manifest_entries(names: Sequence[str], *, attribution: str) -> list[dict]
        one separate entry per derived artefact name: {"name", "licence_class": "share-alike", "spdx": "CC-BY-SA-3.0",
        "attribution": attribution verbatim}; RawMinelibFile when a name ends with one of RAW_SUFFIXES.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.planning.minelib import (
    MARVIN_FILES,
    MARVIN_LICENCE,
    MARVIN_PUBLISHED_UPIT,
    RAW_SUFFIXES,
    RawMinelibFile,
    check_marvin,
    marvin_manifest_entries,
    run_marvin_check,
)

ATTRIBUTION = "MineLib: a library of open pit mining problems (Espinoza et al. 2012), CC BY-SA 3.0, minelib.org"
EM_DASH = "â€”"
VALUES = [7, -3, -2, 5, -9, 4, -1, 6, -2, 8, -5, 3, -4, 2, 9, -6, 1, -7]  # 18 blocks of the 3 x 3 x 2 grid


def _fixture(tmp_path: Path) -> dict[str, bytes]:
    """A tiny instance in MineLib format written by the reference writer, renamed to the marvin file names."""
    from oreblocks import BlockGrid, build_precedence, make_deposit, write_minelib

    grid = BlockGrid(nx=3, ny=3, nz=2)
    deposit = make_deposit(grid, "porphyry", 1)
    paths = write_minelib(
        tmp_path / "w", "marvin", deposit, np.array(VALUES, dtype=np.float64), build_precedence(grid, 45.0)
    )
    return {f"marvin.{ext}": paths[ext].read_bytes() for ext in ("blocks", "prec", "upit")}


def _expected_value(tmp_path: Path) -> int:
    """The UPIT value by an independent solver: networkx maximum flow on the s-t network of FR-017-14."""
    import networkx as nx
    from oreblocks import BlockGrid, build_precedence

    grid = BlockGrid(nx=3, ny=3, nz=2)
    prec = build_precedence(grid, 45.0)
    inf = sum(abs(v) for v in VALUES) + 1
    g = nx.DiGraph()
    for b, v in enumerate(VALUES):
        if v > 0:
            g.add_edge("s", b, capacity=v)
        elif v < 0:
            g.add_edge(b, "t", capacity=-v)
        for p in prec.plist[prec.pstart[b] : prec.pstart[b + 1]]:
            g.add_edge(b, int(p), capacity=inf)
    cut = nx.maximum_flow_value(g, "s", "t")
    return sum(v for v in VALUES if v > 0) - cut


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-23 and SC-017-05
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("SC-017-05")
@pytest.mark.req("FR-017-23")
def test_the_published_best_known_upit_value_and_the_licence_constants() -> None:
    assert MARVIN_PUBLISHED_UPIT == 1_415_655_436
    assert MARVIN_FILES == ("marvin.blocks", "marvin.prec", "marvin.upit")
    assert MARVIN_LICENCE == {"spdx": "CC-BY-SA-3.0", "licence_class": "share-alike"}


@pytest.mark.req("FR-017-23")
def test_the_fixture_instance_value_is_reproduced_from_the_three_minelib_files(tmp_path: Path) -> None:
    expected = _expected_value(tmp_path)
    assert expected > 0  # the fixture has a non-trivial pit
    report = check_marvin(_fixture(tmp_path), published_value=expected)
    assert report.own_value == expected
    assert report.status == "match"
    assert report.published_value == expected


@pytest.mark.req("FR-017-23")
def test_a_different_published_value_is_a_mismatch_or_a_contradiction(tmp_path: Path) -> None:
    expected = _expected_value(tmp_path)
    files = _fixture(tmp_path)
    plain = check_marvin(files, published_value=expected + 1)
    assert plain.status == "mismatch"
    oracles = {"networkx": expected, "scipy": expected, "ortools": expected}
    contradicted = check_marvin(files, published_value=expected + 1, oracle_values=oracles)
    assert contradicted.status == "published-contradicted"
    assert "contradicted by three independent solvers" in contradicted.message
    disagreeing = check_marvin(files, published_value=expected + 1, oracle_values={**oracles, "ortools": expected - 1})
    assert disagreeing.status == "mismatch"  # an oracle that disagrees with the own value blocks the claim
    assert check_marvin(files, published_value=expected, oracle_values=oracles).status == "match"


@pytest.mark.req("FR-017-23")
def test_every_derived_artefact_is_a_separate_cc_by_sa_entry_with_the_verbatim_attribution() -> None:
    names = ["marvin-shells.json", "marvin-upit-check.json", "marvin-pit.bits"]
    entries = marvin_manifest_entries(names, attribution=ATTRIBUTION)
    assert [e["name"] for e in entries] == names  # one entry each, nothing merged
    for entry in entries:
        assert entry["licence_class"] == "share-alike"
        assert entry["spdx"] == "CC-BY-SA-3.0"
        assert entry["attribution"] == ATTRIBUTION  # verbatim


@pytest.mark.req("FR-017-23")
@pytest.mark.parametrize("suffix", [".blocks", ".prec", ".upit", ".cpit", ".pcpsp"])
def test_a_raw_minelib_file_is_never_a_manifest_artefact(suffix: str) -> None:
    with pytest.raises(RawMinelibFile):
        marvin_manifest_entries([f"marvin{suffix}"], attribution=ATTRIBUTION)
    with pytest.raises(RawMinelibFile):
        marvin_manifest_entries(["ok.json", f"MARVIN{suffix.upper()}"], attribution=ATTRIBUTION)


@pytest.mark.req("FR-017-23")
def test_raw_suffixes_are_the_five_minelib_file_types() -> None:
    assert set(RAW_SUFFIXES) == {".blocks", ".prec", ".upit", ".cpit", ".pcpsp"}


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-24: Not run paths
# ----------------------------------------------------------------------------------------------------------------------


def _fetcher(files: dict[str, bytes]):
    return lambda name: files[name]


@pytest.mark.req("FR-017-24")
def test_the_first_successful_run_pins_the_digests_and_reports_the_check(tmp_path: Path) -> None:
    files = _fixture(tmp_path)
    pins: dict[str, str] = {}
    outcome = run_marvin_check(_fetcher(files), pins, published_value=_expected_value(tmp_path))
    assert outcome.status == "ok"
    assert outcome.label is None
    assert outcome.report.status == "match"
    assert pins == {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}


@pytest.mark.req("FR-017-24")
@pytest.mark.parametrize("error", [ConnectionRefusedError("refused"), TimeoutError("timed out"), OSError("no route")])
def test_an_unreachable_host_gives_not_run(error: Exception) -> None:
    def refuse(_name: str) -> bytes:
        raise error

    outcome = run_marvin_check(refuse, {})
    assert outcome.status == "not_run"
    assert outcome.report is None
    assert outcome.label.startswith(f"Not run {EM_DASH} ")
    assert "unreachable" in outcome.label


@pytest.mark.req("FR-017-24")
def test_a_file_that_fails_its_pinned_sha256_gives_not_run_naming_the_file(tmp_path: Path) -> None:
    files = _fixture(tmp_path)
    pins = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    tampered = {**files, "marvin.prec": files["marvin.prec"] + b"0 0\n"}
    outcome = run_marvin_check(_fetcher(tampered), pins)
    assert outcome.status == "not_run"
    assert "sha256" in outcome.label
    assert "marvin.prec" in outcome.label
    assert pins == {
        name: hashlib.sha256(data).hexdigest() for name, data in files.items()
    }  # the pins are not rewritten


@pytest.mark.req("FR-017-24")
@pytest.mark.parametrize("victim", ["marvin.blocks", "marvin.prec", "marvin.upit"])
def test_a_file_that_fails_to_parse_gives_not_run_even_with_the_right_digest(victim: str, tmp_path: Path) -> None:
    files = _fixture(tmp_path)
    garbage = {**files, victim: b"\x00\xff not a minelib file \x00"}
    pins = {name: hashlib.sha256(data).hexdigest() for name, data in garbage.items()}
    outcome = run_marvin_check(_fetcher(garbage), pins)
    assert outcome.status == "not_run"
    assert "parse" in outcome.label
    assert outcome.label.startswith(f"Not run {EM_DASH} ")


@pytest.mark.req("FR-017-24")
def test_a_missing_file_on_the_host_gives_not_run_not_an_exception(tmp_path: Path) -> None:
    files = _fixture(tmp_path)
    del files["marvin.upit"]

    def fetch(name: str) -> bytes:
        if name not in files:
            raise FileNotFoundError(name)
        return files[name]

    outcome = run_marvin_check(fetch, {})
    assert outcome.status == "not_run"
    assert "unreachable" in outcome.label or "missing" in outcome.label
