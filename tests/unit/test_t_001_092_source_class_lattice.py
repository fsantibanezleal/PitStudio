"""T-001-092 · a sources entry may not be less restrictive than its per-file SPDX overrides: FR-001-58.

Oracle: the licence-class lattice of data-model 5.4 (public-domain 0 < open-no-attribution 1 < own 2 < attribution 3
< share-alike 4 < display-only 5 < reference-only 6) and the (SPDX, kind) -> class table of 5.2 for real sources
(LicenseRef-USGov-PD -> public-domain; CC0-1.0 and DL-DE-ZERO-2.0 -> open-no-attribution; CC-BY-4.0 and
LicenseRef-Copernicus-CLMS -> attribution; CC-BY-SA-3.0 / -4.0 -> share-alike), evaluated by hand: an entry is too
permissive exactly when rank(entry class) < rank(class of an override). Share-alike overrides under another entry
SPDX are left out of the pair table because the share-alike mixing rule (FR-001-52) fires there too.

Expected API: ``pitstudio.contracts.load_sources(path) -> dict`` (strict YAML load, schema validation, the per-file
class rule) raises ``ContractError`` with ``error_class == "source-class-too-permissive"`` (also in ``str(exc)``),
naming the entry id and the file; it returns nothing for a rejected file. ``tools/check_contracts.py`` reports the same
as a finding with ``error_class: "source-class-too-permissive"`` and a pointer below ``/sources/<i>``.
"""

from __future__ import annotations

import copy
import itertools
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contract"))
import contract_support as cs

CLASS = "source-class-too-permissive"
REAL_CLASS = {
    "LicenseRef-USGov-PD": "public-domain",
    "CC0-1.0": "open-no-attribution",
    "DL-DE-ZERO-2.0": "open-no-attribution",
    "CC-BY-4.0": "attribution",
    "LicenseRef-Copernicus-CLMS": "attribution",
    "CC-BY-SA-3.0": "share-alike",
    "CC-BY-SA-4.0": "share-alike",
}
NON_SA = [s for s, c in REAL_CLASS.items() if c != "share-alike"]
VALID = json.loads((cs.FIXTURES / "sources/valid/sources.valid.json").read_text(encoding="utf-8"))


def entry(sid: str, spdx: str, override: str | None) -> dict:
    cls = REAL_CLASS[spdx]
    e = copy.deepcopy(VALID["sources"][1])
    e.update(
        id=sid, spdx=spdx, licence_class=cls, card=f"data/cards/{sid}.md", landing_url=f"https://example.org/data/{sid}"
    )
    e["attribution"] = "Example attribution."
    second = copy.deepcopy(e["files"][0])
    second["url"] = f"https://example.org/data/{sid}/second.csv"
    if override is not None:
        e["files"][0]["spdx"] = override
    e["files"] = [e["files"][0], second]
    return e


def write_registry(tmp: Path, entries: list[dict], name: str = "sources.yaml") -> Path:
    p = tmp / name
    p.write_text(yaml.safe_dump({"sources": entries}, sort_keys=False), encoding="utf-8")
    return p


def load_sources(p: Path) -> Any:
    from pitstudio.contracts import load_sources as impl

    return impl(p)


def error_class_of(exc: BaseException) -> str:
    return getattr(exc, "error_class", None) or str(exc)


@pytest.mark.req("FR-001-58")
@pytest.mark.parametrize(("entry_spdx", "override"), list(itertools.product(NON_SA, NON_SA)), ids=lambda v: v)
def test_fr_001_58_entry_class_lower_than_an_override_class_is_rejected(
    tmp_path: Path, entry_spdx: str, override: str
) -> None:
    from pitstudio.contracts import ContractError

    rank = cs.LICENCE_RANK
    too_permissive = rank[REAL_CLASS[entry_spdx]] < rank[REAL_CLASS[override]]
    p = write_registry(tmp_path, [entry("example-source", entry_spdx, override)])
    result = None
    if too_permissive:
        with pytest.raises(ContractError) as info:
            result = load_sources(p)
        assert result is None  # no partial registry
        msg = str(info.value)
        assert CLASS in error_class_of(info.value), msg
        assert "example-source" in msg, msg
        assert p.name in msg, msg
    else:
        assert load_sources(p) == yaml.safe_load(p.read_text(encoding="utf-8"))


@pytest.mark.req("FR-001-58")
def test_fr_001_58_the_plan_example_public_domain_with_a_share_alike_file_then_the_same_entry_at_share_alike(
    tmp_path: Path,
) -> None:
    from pitstudio.contracts import ContractError

    bad = entry("example-source", "LicenseRef-USGov-PD", "CC-BY-SA-4.0")
    with pytest.raises(ContractError):
        load_sources(write_registry(tmp_path, [bad], "bad.yaml"))
    good = entry("example-source", "CC-BY-SA-4.0", "CC-BY-SA-4.0")
    good["files"][1]["spdx"] = "CC-BY-SA-4.0"  # every file carries the one share-alike id
    loaded = load_sources(write_registry(tmp_path, [good], "good.yaml"))
    assert loaded["sources"][0]["licence_class"] == "share-alike"


@pytest.mark.req("FR-001-58")
@pytest.mark.parametrize("spdx", sorted(REAL_CLASS))
def test_fr_001_58_entries_without_overrides_are_never_too_permissive(tmp_path: Path, spdx: str) -> None:
    p = write_registry(tmp_path, [entry("example-source", spdx, None)])
    assert load_sources(p)["sources"][0]["spdx"] == spdx


@pytest.mark.req("FR-001-58")
def test_fr_001_58_the_error_names_the_offending_entry_not_the_first_one(tmp_path: Path) -> None:
    from pitstudio.contracts import ContractError

    good = entry("first-source", "CC-BY-4.0", "CC0-1.0")  # entry stricter than its override: fine
    bad = entry("second-source", "CC0-1.0", "CC-BY-4.0")
    other = entry("third-source", "LicenseRef-USGov-PD", None)
    p = write_registry(tmp_path, [good, bad, other], "registry.yaml")
    with pytest.raises(ContractError) as info:
        load_sources(p)
    assert "second-source" in str(info.value)
    assert "first-source" not in str(info.value)
    assert "registry.yaml" in str(info.value)


@pytest.mark.req("FR-001-58")
def test_fr_001_58_a_per_file_override_outside_the_allowlist_is_a_contract_error_not_a_crash(tmp_path: Path) -> None:
    from pitstudio.contracts import ContractError

    for bad in ("GPL-3.0-only", "cc-by-4.0", "", None, 5):
        e = entry("example-source", "CC-BY-4.0", "CC0-1.0")
        e["files"][0]["spdx"] = bad
        with pytest.raises(ContractError):
            load_sources(write_registry(tmp_path, [e]))


@pytest.mark.req("FR-001-58")
def test_fr_001_58_a_malformed_registry_file_is_rejected_by_the_same_loader(tmp_path: Path) -> None:
    from pitstudio.contracts import ContractError

    p = tmp_path / "broken.yaml"
    p.write_text("sources: [\n", encoding="utf-8")
    with pytest.raises(ContractError):
        load_sources(p)
    p.write_text("sources: &a []\nother: *a\n", encoding="utf-8")
    with pytest.raises(ContractError):
        load_sources(p)


@pytest.mark.req("FR-001-58")
@pytest.mark.parametrize(
    ("entry_spdx", "override", "flagged"),
    [
        ("LicenseRef-USGov-PD", "CC0-1.0", True),
        ("CC0-1.0", "CC-BY-4.0", True),
        ("CC-BY-4.0", "CC0-1.0", False),
        ("CC-BY-4.0", "LicenseRef-Copernicus-CLMS", False),
        ("DL-DE-ZERO-2.0", "LicenseRef-Copernicus-CLMS", True),
    ],
)
def test_fr_001_58_the_checker_reports_it_with_the_error_class_and_the_entry_pointer(
    tmp_path: Path, entry_spdx: str, override: str, flagged: bool
) -> None:
    root = cs.clean_repo(tmp_path)
    cs.edit_yaml(root, "data/sources.yaml", lambda d: d["sources"].append(entry("example-extra", entry_spdx, override)))
    res = cs.run_checker(root)
    hits = [f for f in res.in_file("data/sources.yaml", "/sources/3") if f.get("error_class") == CLASS]
    assert bool(hits) is flagged, res.findings
    for f in hits:
        assert "example-extra" in f["message"]
        assert len(f["message"]) <= 300
