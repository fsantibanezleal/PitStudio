# ruff: noqa: E501, PT011, PT018
"""T-008-041: `synthetic: true` on sets and records; synthetic data cards; synthetic sets pass the real-data validators.

Requirements: FR-008-33, FR-008-34.

Spec: specs/008-data-pipeline/spec.md FR-008-33 (every synthetic set and every one of its records carries `synthetic: true`;
every set has a data card with generator, version, git SHA, configuration SHA-256, seeds, priors with citation and page, assets
with licence and SHA-256, and a validation entry per FR-008-36), FR-008-34 (a synthetic set of a type that has a real
counterpart passes the same schema or validator as the real data: Voight series as the de Wit displacement series; muck-pile
masks as the Mendeley mask validator; procedural terrain as the DEM raster validator); contract
`contracts/data-card.schema.json` (DC-008-05).

Oracle: the data-card JSON Schema and the spec's own card examples (`contracts/examples/data-card.valid*.json`: the field
values used below are those of the example documents); for FR-008-34 the real validators of T-008-022 called directly on
the same inputs: the synthetic path must return the same verdict and the same violations (a validator shared by real and
synthetic data cannot disagree with itself).

Expected API of the implementation:
- `pitstudio_pipeline.cards.build_synthetic_card(set_type, **fields) -> dict`: `fields` are the card fields `id`, `title`, `spdx`,
  `licence_class`, `redistribution`, `files_sha256`, `generator` (`module`, `stage`, `version`, `git_sha`), `config_sha256`,
  `seeds`, `priors` (`name`, `citation`, `page`), `assets` (`name`, `spdx`, `licence_class`, `sha256`) and, for the
  `validated-against-real` class, `real_reference`; returns the front matter with `kind: synthetic`, `synthetic: True` and the
  `validation` entry chosen by FR-008-36 (see test_t_008_042), valid against the data-card schema. A missing field, an empty
  seed list, a prior without page, an asset without SHA-256 or `synthetic=False` raises `ValueError`.
- `pitstudio_pipeline.synthesize.validate_set(set_type, subject, **kw) -> None` with `set_type` in `muck-pile-masks`
  (`subject` = path of an indexed PNG; `kw` as `ingest.files.validate_mask`), `procedural-terrain` (a GeoTIFF path; `kw` as
  `ingest.files.validate_raster`) and `voight-creep-series` (a record with `t` and `x` lists; `kw`: `series`); it calls the
  real-data validator of that type and raises `IngestionRejected` exactly as the real validator does.
- `pitstudio_pipeline.ingest.validate_series(t, x, *, series) -> None`: the displacement-series validator shared with
  `s20_feature_extraction` (see test_t_008_050).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import _p008_kit as kit
import numpy as np
import pytest
from pitstudio_pipeline.cards import build_synthetic_card
from pitstudio_pipeline.errors import IngestionRejected
from pitstudio_pipeline.ingest import files as F
from pitstudio_pipeline.ingest import validate_series
from pitstudio_pipeline.synthesize import run, validate_set

EXAMPLE = json.loads(
    (kit.SPEC008 / "contracts" / "examples" / "data-card.valid-unvalidated.json").read_text(encoding="utf-8")
)
FIELDS = {
    k: copy.deepcopy(EXAMPLE[k])
    for k in (
        "id",
        "title",
        "spdx",
        "licence_class",
        "redistribution",
        "files_sha256",
        "generator",
        "config_sha256",
        "seeds",
        "priors",
        "assets",
    )
}


def card(set_type: str = "des-cycles", **over):
    return build_synthetic_card(set_type, **{**copy.deepcopy(FIELDS), **over})


# ------------------------------------------------------------------------------------------------ FR-008-33
@pytest.mark.req("FR-008-33")
def test_synthetic_card_is_valid_and_flagged_synthetic() -> None:
    c = card()
    assert kit.schema_errors("data-card.schema.json", c) == []
    assert c["synthetic"] is True and c["kind"] == "synthetic"
    for key in ("generator", "config_sha256", "seeds", "priors", "assets", "validation"):
        assert key in c
    assert set(c["generator"]) == {"module", "stage", "version", "git_sha"}
    assert c["id"] == EXAMPLE["id"] and c["seeds"] == EXAMPLE["seeds"]
    assert c["priors"][0]["citation"] and c["priors"][0]["page"]


@pytest.mark.req("FR-008-33")
@pytest.mark.parametrize(
    "missing",
    ["id", "title", "generator", "config_sha256", "seeds", "priors", "assets", "files_sha256", "spdx", "licence_class"],
)
def test_a_card_without_a_required_field_is_refused(missing: str) -> None:
    fields = copy.deepcopy(FIELDS)
    del fields[missing]
    with pytest.raises(ValueError):
        build_synthetic_card("des-cycles", **fields)


@pytest.mark.req("FR-008-33")
@pytest.mark.parametrize(
    "mutate",
    [
        lambda f: f.update(seeds=[]),
        lambda f: f["priors"].append({"name": "x", "citation": "Someone (2020)"}),  # no page
        lambda f: f["priors"].append({"name": "x", "citation": "", "page": "3"}),
        lambda f: f["assets"].append(
            {"name": "a", "spdx": "CC0-1.0", "licence_class": "open-no-attribution"}
        ),  # no sha256
        lambda f: f["assets"].append(
            {"name": "a", "spdx": "CC0-1.0", "licence_class": "open-no-attribution", "sha256": "xyz"}
        ),
        lambda f: f.update(config_sha256="abc"),
        lambda f: f["generator"].update(git_sha="HEAD"),
        lambda f: f.update(synthetic=False),
        lambda f: f.update(spdx="GPL-3.0-only"),
    ],
    ids=[
        "no-seeds",
        "prior-without-page",
        "prior-without-citation",
        "asset-without-sha",
        "asset-bad-sha",
        "bad-config-digest",
        "git-sha-not-hex",
        "synthetic-false",
        "unknown-spdx",
    ],
)
def test_hostile_card_fields_are_refused(mutate) -> None:
    fields = copy.deepcopy(FIELDS)
    mutate(fields)
    with pytest.raises(ValueError):
        build_synthetic_card("des-cycles", **fields)


@pytest.mark.req("FR-008-33")
def test_unicode_and_oversized_text_in_a_card_is_handled_not_crashed() -> None:
    fields = copy.deepcopy(FIELDS)
    fields["title"] = "Perfiles de código ☃ " + "x" * 10
    assert kit.schema_errors("data-card.schema.json", build_synthetic_card("des-cycles", **fields)) == []
    fields["title"] = "x" * 301  # schema maximum is 300
    with pytest.raises(ValueError):
        build_synthetic_card("des-cycles", **fields)


@pytest.mark.req("FR-008-33")
def test_every_record_of_a_generated_set_is_flagged(tmp_path: Path) -> None:
    res = run("voight-creep", seed=3, config=None, data_root=tmp_path / "d", now=kit.NOW)
    assert res.synthetic is True and res.records and all(r["synthetic"] is True for r in res.records)


# ------------------------------------------------------------------------------------------------ FR-008-34
def _violations(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except IngestionRejected as exc:
        return exc.violations
    return None


@pytest.mark.req("FR-008-34")
def test_muck_pile_masks_go_through_the_mendeley_mask_validator(tmp_path: Path) -> None:
    labels = np.zeros((512, 512), dtype=np.uint8)
    labels[40:80, 40:80] = 1
    good = kit.write_indexed_mask(tmp_path / "good.png", labels)
    gray = kit.write_indexed_mask(tmp_path / "gray.png", labels, mode="L")
    small = kit.write_indexed_mask(tmp_path / "small.png", labels[:100, :100])
    assert validate_set("muck-pile-masks", good, file="raw/t/good.png") is None
    for bad in (gray, small):
        direct = _violations(F.validate_mask, bad, file="raw/t/x.png")
        assert direct, "premise: the real validator rejects this mask"
        assert _violations(validate_set, "muck-pile-masks", bad, file="raw/t/x.png") == direct


@pytest.mark.req("FR-008-34")
def test_procedural_terrain_goes_through_the_dem_raster_validator(tmp_path: Path) -> None:
    aoi = (399_000.0, 4_499_000.0, 401_000.0, 4_501_000.0)
    kw = {"aoi": aoi, "dtype": "float32", "nodata": -9999.0, "file": "raw/t/x.tif"}
    arr = np.arange(16, dtype=np.float32).reshape(4, 4)
    good = kit.write_geotiff(tmp_path / "g.tif", arr, nodata=-9999.0)
    no_crs = kit.write_geotiff(tmp_path / "n.tif", arr, epsg=None, nodata=-9999.0)
    assert validate_set("procedural-terrain", good, **kw) is None
    direct = _violations(F.validate_raster, no_crs, **kw)
    assert direct
    assert _violations(validate_set, "procedural-terrain", no_crs, **kw) == direct


@pytest.mark.req("FR-008-34")
def test_voight_series_go_through_the_displacement_series_validator(tmp_path: Path) -> None:
    res = run("voight-creep", seed=1, config=None, data_root=tmp_path / "d", now=kit.NOW)
    rec = res.records[0]
    assert validate_set("voight-creep-series", rec, series="voight-1") is None
    assert validate_series(rec["t"], rec["x"], series="voight-1") is None
    bad = {"t": list(rec["t"]), "x": list(rec["x"])}
    bad["t"][3] = bad["t"][2]  # a repeated timestamp: not strictly increasing
    direct = _violations(validate_series, bad["t"], bad["x"], series="voight-1")
    assert direct and direct[0]["row"] == 3
    assert _violations(validate_set, "voight-creep-series", bad, series="voight-1") == direct
