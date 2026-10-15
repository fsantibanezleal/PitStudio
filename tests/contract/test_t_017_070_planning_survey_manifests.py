"""T-017-070: manifests, synthetic labels, separate CC BY-SA entries, real-volume attribution (contract).

Requirements: FR-017-51.

Spec: specs/017-planning-survey/spec.md FR-017-51: every D2, E1 and E2 artefact carries a manifest (DC-000-01):
sweeps and
meta-model labelled "calibrated synthetic -- not validated against real data" (an em dash), `oreblocks` deposits
labelled
synthetic, MineLib-derived layers in separate CC BY-SA 3.0 entries, the real Bingham volume with its public-domain
attribution, and the splat with its producing tools. plan.md test strategy row FR-017-51: manifests against
`contracts/manifest.schema.json`; label strings; separate CC BY-SA entries.

Oracles:
- the promoted manifest schema (`contracts/manifest.schema.json`, `$defs/artefact`, validated with `jsonschema`):
  the shape of
  an entry (producer, licence class, SPDX id, attribution, lane, host, budget class; a `table` entry has lane
  `static` and no
  lane measurements; a git-hosted entry has fewer than 10,485,760 bytes and no release tag; a release-hosted entry
  has a bare file
  name and a tag; every licence class other than public-domain, open-no-attribution and own requires an attribution);
- the label strings and attribution texts written in this test from the spec and the spec's valid real-volume example
  ("U.S. Geological Survey, 3D Elevation Program (public domain)", SPDX `LicenseRef-USGov-PD`, class public-domain);
- the MineLib licence: CC BY-SA 3.0 (SPDX `CC-BY-SA-3.0`, class `share-alike`), stated on the MineLib home page
  (spec section 7);
- hand-built artefact inputs; because the manifest has no label property, the honesty label travels in the entry's
  `attribution` text (UNVERIFIED reading: the schema offers no other free-text field), and the "producing tools" of
  the splat
  (COLMAP 4.2.1, Brush v0.3.0, splat-transform 3.9.0) are named in its attribution, with `producer.tool` = `brush`.

Expected public API (module `pitstudio.planning.manifests`, root environment, pure Python):
    LABEL = "calibrated synthetic â€” not validated against real data"
    BINGHAM_ATTRIBUTION = "U.S. Geological Survey, 3D Elevation Program (public domain)"
    SPLAT_TOOLS = "COLMAP 4.2.1, Brush v0.3.0, @playcanvas/splat-transform 3.9.0"
    build_entries(artefacts: Sequence[Mapping], *, run_id: str, git_sha: str, minelib_attribution: str | None = None)
        -> list[dict]
        each input: {"role": "sweep" | "meta-model" | "oreblocks-deposit" | "minelib-derived" | "bingham-volume" |
        "splat",
        "id", "path", "bytes", "sha256", "media_type", "kind", "inputs", "cases", "budget_class", "asset_host",
        "release_tag" (release only), "lane", "lane_measurements" (not for `static`), "tool", "stage"}; output: one
        manifest
        artefact per input, in order, with `licence_class`, `spdx`, `attribution` set by the role:
          sweep, meta-model   -> own, CC-BY-4.0, attribution LABEL
          oreblocks-deposit   -> own, CC-BY-4.0, attribution containing "synthetic" and "oreblocks"
          minelib-derived     -> share-alike, CC-BY-SA-3.0, attribution `minelib_attribution` verbatim (ValueError
          when it is
                                 missing or empty)
          bingham-volume      -> public-domain, LicenseRef-USGov-PD, attribution BINGHAM_ATTRIBUTION
          splat               -> own, CC-BY-4.0, attribution containing SPLAT_TOOLS; producer.tool "brush"
        A minelib-derived entry never shares an entry with another role (each input stays its own entry) and its
        `inputs`
        may not reference a source of another licence class (the `licence_class` helper key of an input is dropped
        from the
        output, whose inputs follow the manifest input_ref): ValueError for an input whose role is
        "minelib-derived" and
        that lists an input with `"licence_class"` other than "share-alike". Raises ValueError for an unknown role
        and for
        a splat larger than 25,000,000 bytes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pitstudio.planning.manifests import (
    BINGHAM_ATTRIBUTION,
    LABEL,
    SPLAT_TOOLS,
    build_entries,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "contracts" / "manifest.schema.json").read_text("utf-8"))
EM_DASH = "â€”"
MINELIB_TEXT = "MineLib: a library of open pit mining problems (Espinoza et al. 2012), CC BY-SA 3.0, minelib.org"
RUN = {"run_id": "20261020T010000Z-e1-planning", "git_sha": "c" * 40}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _validator():
    from jsonschema import Draft202012Validator

    return Draft202012Validator({"$ref": "#/$defs/artefact", "$defs": MANIFEST["$defs"]})


def _base(role: str, name: str, kind: str, **over) -> dict:
    spec = {
        "role": role,
        "id": name,
        "path": f"assets/e/{name}.json",
        "bytes": 40_000,
        "sha256": _sha(name),
        "media_type": "application/json",
        "kind": kind,
        "inputs": [{"id": "source-a", "sha256": _sha("source-a"), "kind": "source"}],
        "cases": ["D2"],
        "budget_class": "own-code",
        "asset_host": "git",
        "lane": "static",
        "tool": "minephys-sweeps",
        "stage": {"id": "s05_synthesize"},
    }
    spec.update(over)
    return spec


def _measured(nbytes: int) -> dict:
    return {
        "web_drivable": True,
        "max_asset_bytes": nbytes,
        "interaction_ms": None,
        "run_ms_t2": None,
        "trace_bytes": None,
        "measured": {"tier": "T2", "date": "2026-10-20", "browser": "Chromium 141"},
    }


MARVIN_INPUT = {"id": "marvin-source", "sha256": _sha("marvin"), "kind": "source", "licence_class": "share-alike"}
ARTEFACTS = [
    _base("sweep", "d2-sweeps", "table"),
    _base(
        "meta-model",
        "d2-meta-mlp",
        "onnx",
        media_type="application/octet-stream",
        lane="replay",
        lane_measurements=_measured(40_000),
        path="assets/models/d2-meta-mlp.onnx",
    ),
    _base("oreblocks-deposit", "e1-porphyry-seed3", "table", cases=["E1"]),
    _base("minelib-derived", "e1-marvin-shells", "table", cases=["E1"], inputs=[MARVIN_INPUT]),
    _base("bingham-volume", "e2-bingham-volume", "table", cases=["E2"]),
]


def _entries(items=None, **kw):
    return build_entries(items if items is not None else ARTEFACTS, minelib_attribution=MINELIB_TEXT, **RUN, **kw)


# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-51")
def test_the_constants_are_the_spec_texts() -> None:
    assert f"calibrated synthetic {EM_DASH} not validated against real data" == LABEL
    assert BINGHAM_ATTRIBUTION == "U.S. Geological Survey, 3D Elevation Program (public domain)"
    assert "COLMAP 4.2.1" in SPLAT_TOOLS
    assert "Brush v0.3.0" in SPLAT_TOOLS
    assert "3.9.0" in SPLAT_TOOLS


@pytest.mark.req("FR-017-51")
def test_every_entry_validates_against_the_manifest_artefact_schema_and_keeps_its_order() -> None:
    entries = _entries()
    assert [e["id"] for e in entries] == [a["id"] for a in ARTEFACTS]
    for entry, source in zip(entries, ARTEFACTS, strict=True):
        assert list(_validator().iter_errors(entry)) == [], entry["id"]
        assert entry["producer"] == {"tool": source["tool"], "stage": source["stage"]}
        assert entry["run_id"] == RUN["run_id"]
        assert entry["git_sha"] == RUN["git_sha"]


@pytest.mark.req("FR-017-51")
def test_sweeps_and_the_meta_model_carry_the_calibrated_synthetic_label() -> None:
    by_id = {e["id"]: e for e in _entries()}
    for name in ("d2-sweeps", "d2-meta-mlp"):
        assert by_id[name]["attribution"] == LABEL
        assert by_id[name]["licence_class"] == "own"
        assert by_id[name]["spdx"] == "CC-BY-4.0"


@pytest.mark.req("FR-017-51")
def test_oreblocks_deposits_are_labelled_synthetic() -> None:
    entry = {e["id"]: e for e in _entries()}["e1-porphyry-seed3"]
    assert "synthetic" in entry["attribution"].lower()
    assert "oreblocks" in entry["attribution"].lower()
    assert entry["licence_class"] == "own"


@pytest.mark.req("FR-017-51")
def test_minelib_derived_layers_are_separate_cc_by_sa_entries_with_the_verbatim_attribution() -> None:
    entries = _entries()
    share_alike = [e for e in entries if e["licence_class"] == "share-alike"]
    assert [e["id"] for e in share_alike] == ["e1-marvin-shells"]  # only the derived layer, nothing else is share-alike
    assert share_alike[0]["spdx"] == "CC-BY-SA-3.0"
    assert share_alike[0]["attribution"] == MINELIB_TEXT
    assert {e["id"] for e in entries if e["licence_class"] != "share-alike"}.isdisjoint({"e1-marvin-shells"})


@pytest.mark.req("FR-017-51")
def test_a_minelib_layer_needs_its_attribution_and_cannot_hide_inside_another_licence_class() -> None:
    with pytest.raises(ValueError, match="attribution"):
        build_entries(ARTEFACTS, minelib_attribution=None, **RUN)
    with pytest.raises(ValueError, match="attribution"):
        build_entries(ARTEFACTS, minelib_attribution="   ", **RUN)
    mixed = list(ARTEFACTS)
    other_class = {"id": "oreblocks-src", "sha256": _sha("o"), "kind": "source", "licence_class": "own"}
    mixed[3] = _base("minelib-derived", "e1-merged", "table", cases=["E1"], inputs=[MARVIN_INPUT, other_class])
    with pytest.raises(ValueError, match="share-alike"):
        _entries(mixed)


@pytest.mark.req("FR-017-51")
def test_the_real_bingham_volume_carries_its_public_domain_attribution() -> None:
    entry = {e["id"]: e for e in _entries()}["e2-bingham-volume"]
    assert entry["licence_class"] == "public-domain"
    assert entry["spdx"] == "LicenseRef-USGov-PD"
    assert entry["attribution"] == BINGHAM_ATTRIBUTION


@pytest.mark.req("FR-017-51")
def test_the_splat_names_its_producing_tools_and_respects_the_25_mb_cap() -> None:
    splat = _base(
        "splat",
        "e2-splat",
        "splat",
        cases=["E2"],
        media_type="application/octet-stream",
        bytes=20_000_000,
        asset_host="release",
        release_tag="assets-v1.00.001",
        path="e2-splat.spz",
        budget_class="splats",
        tool="brush",
        stage={"id": "st58b_capture_splat"},
        lane="replay",
        lane_measurements=_measured(20_000_000),
    )
    (entry,) = build_entries([splat], minelib_attribution=MINELIB_TEXT, **RUN)
    assert list(_validator().iter_errors(entry)) == []
    assert entry["producer"] == {"tool": "brush", "stage": {"id": "st58b_capture_splat"}}
    for tool in ("COLMAP 4.2.1", "Brush v0.3.0", "splat-transform 3.9.0"):
        assert tool in entry["attribution"]
    too_big = dict(splat, bytes=25_000_001)
    with pytest.raises(ValueError, match="25"):
        build_entries([too_big], minelib_attribution=MINELIB_TEXT, **RUN)


@pytest.mark.req("FR-017-51")
def test_an_unknown_role_is_refused() -> None:
    with pytest.raises(ValueError, match="role"):
        build_entries([_base("mystery", "x", "table")], minelib_attribution=MINELIB_TEXT, **RUN)


@pytest.mark.req("FR-017-51")
def test_an_empty_artefact_list_gives_no_entries() -> None:
    assert build_entries([], minelib_attribution=MINELIB_TEXT, **RUN) == []
