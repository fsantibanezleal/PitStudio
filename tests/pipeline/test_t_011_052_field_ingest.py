"""T-011-052 - FR-011-34, FR-011-41 (and the data-level clause of FR-011-40): field data, patch split, hostile
    field files.

Oracles (independent of the code under test; plan 011 test strategy FR-011-34 / FR-011-41):
- the split by patch of FR-011-34 counted by hand: 64 patches -> 48 training + 6 validation + 10 test, disjoint,
    covering all,
  and 40 tailings + 20 dust scenarios per patch (2,560 and 1,280 in total);
- the scenario parameter ranges of the DC-011-02 FNO example (`surrogate-io.valid-fno.json` training envelope:
    yield stress
  10 ... 200 Pa, plastic viscosity 0.05 ... 1.0 Pa.s, release volume 10^4 ... 2 x 10^5 m^3, density 1,600 ... 2,000
      kg/m^3,
  breach cell 0 ... 63) and of the DC-011-03 draft schema for the dust scenarios;
- block-mean resampling by hand: a 1 m DEM whose value is i + j at row i, column j has the 8 x 8 block mean
  mean(i) + mean(j) = 3.5 + 3.5 = 7.0 in the first block and 7.0 + 8 (di + dj) in block (di, dj); a block of
      constant value
  keeps its value;
- field files built in this test from the DC-011-03 example (`field-dataset.valid.json`; its schema admits the Zarr
    store
  only): the payload is a Zarr v3 group with one float32 array `data` [C, ny, nx] in metadata channel order, its
      digest being
  `data.zarr_digest(store)` (the SHA-256 of the sorted chunk-digest listing, spec section 8; the test uses it only
      to build the
  file and checks that it changes with the bytes, is deterministic and does not depend on the store path); one
      invalid file
  per class of FR-011-41 (the corpus classes: grid other than 64 x 64, missing unit, missing cell size, non-finite
      value, depth
  below -1e-9 m, absolute or `..` store path) plus the checker classes of the corpus index (digest, payload shape,
      output
  times, breach cell, channel order, label).

Expected public API (module `pitstudio_pipeline.surrogates.fno.data`, package under `pipeline/src/`; errors in
`pitstudio_pipeline.surrogates.errors`):

    split_patches(patch_ids, *, seed) -> PatchSplit      attributes train, val, test (lists of ids); needs exactly
        64 distinct ids (the 48 / 6 / 10 split of FR-011-34); reproducible by seed; raises DatasetError otherwise.
    draw_tailings_scenarios(n, *, seed, patch_id=None) -> list[dict]   keys breach_row, breach_col, release_volume_m3,
        yield_stress_pa, plastic_viscosity_pa_s, density_kg_per_m3 (uniform in the training envelope above)
    draw_dust_scenarios(n, *, seed, patch_id=None) -> list[dict]       keys source_row_start, source_col_start,
        source_row_end,
        source_col_end, source_strength_kg_per_m2_s, wind_speed_m_per_s (0 ... 50), wind_direction_deg ([0, 360))
    scenarios_for_patches(patch_ids, *, seed) -> dict[str, {"tailings": list, "dust": list}]   40 and 20 per patch
    block_mean(dem, factor) -> np.ndarray      mean of factor x factor blocks; raises ValueError for a shape that
        the factor
        does not divide, a non-finite value, or factor < 1
    zarr_digest(store) -> str       SHA-256 (64 lower-case hex) of the sorted chunk-digest listing of a Zarr store
        directory
    load_field_file(meta_path, *, root, expected_channels=None) -> FieldRecord
        FieldRecord attributes: meta (dict), channels (list of names), data (float32 array [C, ny, nx]).
        Rejects with `FieldFileError` (attributes `.reason`, naming the offending key or class; never coerces)
            every invalid
        file above; `expected_channels` (a tuple of names) is compared with the channel order of the file.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.errors import DatasetError, FieldFileError  # noqa: E402
from pitstudio_pipeline.surrogates.fno import data  # noqa: E402

EX = ROOT / "specs" / "011-surrogates" / "contracts" / "examples"
META = json.loads((EX / "field-dataset.valid.json").read_text(encoding="utf-8"))
ENVELOPE = json.loads((EX / "surrogate-io.valid-fno.json").read_text(encoding="utf-8"))["training_envelope"]
CHANNELS = [c["name"] for c in META["channels"]]
TAILINGS_INPUTS = tuple(CHANNELS[:5])


# ------------------------------------------------------------------ FR-011-34 split and scenarios


@pytest.mark.req("FR-011-34")
def test_the_split_by_patch_is_48_6_10_disjoint_and_complete() -> None:
    ids = [f"p{i:02d}" for i in range(64)]
    s = data.split_patches(ids, seed=1)
    assert (len(s.train), len(s.val), len(s.test)) == (48, 6, 10)
    assert not (set(s.train) & set(s.val))
    assert not (set(s.train) & set(s.test))
    assert not (set(s.val) & set(s.test))
    assert set(s.train) | set(s.val) | set(s.test) == set(ids)


@pytest.mark.req("FR-011-34")
def test_the_split_is_reproducible_and_depends_on_the_seed() -> None:
    ids = [f"p{i:02d}" for i in range(64)]
    a, b, c = data.split_patches(ids, seed=3), data.split_patches(ids, seed=3), data.split_patches(ids, seed=4)
    assert (a.train, a.val, a.test) == (b.train, b.val, b.test)
    assert a.test != c.test


@pytest.mark.req("FR-011-34")
@pytest.mark.parametrize("count", [0, 10, 63, 65, 100])
def test_a_patch_list_that_is_not_64_patches_is_refused(count: int) -> None:
    with pytest.raises(DatasetError):
        data.split_patches([f"p{i}" for i in range(count)], seed=1)


@pytest.mark.req("FR-011-34")
def test_duplicate_patch_ids_are_refused() -> None:
    with pytest.raises(DatasetError):
        data.split_patches(["p0"] * 64, seed=1)


@pytest.mark.req("FR-011-34")
def test_forty_tailings_and_twenty_dust_scenarios_per_patch() -> None:
    ids = [f"p{i:02d}" for i in range(64)]
    plan = data.scenarios_for_patches(ids, seed=2)
    assert set(plan) == set(ids)
    assert all(len(v["tailings"]) == 40 and len(v["dust"]) == 20 for v in plan.values())
    assert sum(len(v["tailings"]) for v in plan.values()) == 2560
    assert sum(len(v["dust"]) for v in plan.values()) == 1280


@pytest.mark.req("FR-011-34")
def test_tailings_scenarios_lie_in_the_training_envelope_and_are_reproducible() -> None:
    a = data.draw_tailings_scenarios(400, seed=5)
    assert a == data.draw_tailings_scenarios(400, seed=5)
    assert a != data.draw_tailings_scenarios(400, seed=6)
    for s in a:
        assert ENVELOPE["yield_stress"]["min"] <= s["yield_stress_pa"] <= ENVELOPE["yield_stress"]["max"]
        assert (
            ENVELOPE["plastic_viscosity"]["min"] <= s["plastic_viscosity_pa_s"] <= ENVELOPE["plastic_viscosity"]["max"]
        )
        assert ENVELOPE["release_volume"]["min"] <= s["release_volume_m3"] <= ENVELOPE["release_volume"]["max"]
        assert ENVELOPE["density"]["min"] <= s["density_kg_per_m3"] <= ENVELOPE["density"]["max"]
        assert 0 <= s["breach_row"] <= 63
        assert 0 <= s["breach_col"] <= 63
        assert isinstance(s["breach_row"], int)
        assert isinstance(s["breach_col"], int)


@pytest.mark.req("FR-011-34")
def test_dust_scenarios_have_a_source_line_inside_the_grid_and_a_legal_wind() -> None:
    for s in data.draw_dust_scenarios(300, seed=7):
        for k in ("source_row_start", "source_col_start", "source_row_end", "source_col_end"):
            assert 0 <= s[k] <= 63
        assert 0.0 < s["source_strength_kg_per_m2_s"] <= 1.0
        assert 0.0 <= s["wind_speed_m_per_s"] <= 50.0
        assert 0.0 <= s["wind_direction_deg"] < 360.0


@pytest.mark.req("FR-011-34")
def test_block_mean_of_a_ramp_is_the_hand_value_per_block() -> None:
    i, j = np.meshgrid(np.arange(512), np.arange(512), indexing="ij")
    dem = (i + j).astype(float)
    out = data.block_mean(dem, 8)
    assert out.shape == (64, 64)
    assert out[0, 0] == pytest.approx(7.0, abs=1e-12)  # 3.5 + 3.5
    assert out[2, 5] == pytest.approx(7.0 + 8 * (2 + 5), abs=1e-12)
    assert data.block_mean(np.full((16, 16), 3.25), 8).tolist() == [[3.25, 3.25], [3.25, 3.25]]


@pytest.mark.req("FR-011-34")
@pytest.mark.parametrize(
    ("dem", "factor"),
    [(np.zeros((10, 10)), 8), (np.zeros((16, 16)), 0), (np.full((16, 16), np.nan), 8), (np.zeros((16, 12)), 8)],
    ids=["not-divisible", "factor-zero", "nan", "rectangular-not-divisible"],
)
def test_block_mean_rejects_hostile_input(dem: np.ndarray, factor: int) -> None:
    with pytest.raises(ValueError, match=r"."):
        data.block_mean(dem, factor)


# ------------------------------------------------------------------ FR-011-41 field files


def payload_arrays(meta: dict) -> dict[str, np.ndarray]:
    """Deterministic per-channel fields: the first channel's values are uniform(0, 5) from default_rng(0)."""
    ny, nx = meta["grid"]["ny"], meta["grid"]["nx"]
    rng = np.random.default_rng(0)
    out = {}
    for c in meta["channels"]:
        unit = c.get("unit")
        vals = rng.uniform(0.0, 5.0, ny * nx) if unit in (None, "m") else rng.uniform(1.0, 2.0, ny * nx)
        out[c["name"]] = vals.astype(np.float32).reshape(ny, nx)
    return out


def write_field(root: Path, *, meta=None, mutate_table=None, name="field", short=False) -> Path:
    """Writes `<name>.zarr` (group with array `data` [C, ny, nx] in metadata channel order) and `<name>.json`."""
    import zarr

    meta = copy.deepcopy(META if meta is None else meta)
    cols = payload_arrays(meta)
    if mutate_table:
        mutate_table(cols)
    stack = np.stack([cols[c["name"]] for c in meta["channels"]])
    if short:
        stack = stack[:, :, :-1]
    store = root / f"{name}.zarr"
    group = zarr.open_group(str(store), mode="w", zarr_format=3)
    arr = group.create_array("data", shape=stack.shape, dtype="float32", chunks=stack.shape)
    arr[:] = stack
    meta["store"] = {"format": "zarr", "path": store.name, "sha256": data.zarr_digest(store)}
    meta_path = root / f"{name}.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    return meta_path


def chunk_files(store: Path) -> list[Path]:
    return sorted(p for p in store.rglob("*") if p.is_file() and p.name != "zarr.json")


@pytest.mark.req("FR-011-41")
def test_a_valid_field_file_loads_with_the_channels_in_metadata_order(tmp_path: Path) -> None:
    rec = data.load_field_file(write_field(tmp_path), root=tmp_path)
    expected = payload_arrays(META)
    assert rec.channels == CHANNELS
    assert rec.data.shape == (14, 64, 64)
    assert rec.data.dtype == np.float32
    for i, name in enumerate(CHANNELS):
        assert np.array_equal(rec.data[i], expected[name])
    assert rec.meta["patch_id"] == "p07"


@pytest.mark.req("FR-011-41")
def test_the_zarr_digest_is_deterministic_path_independent_and_sensitive_to_every_chunk_byte(tmp_path: Path) -> None:
    import shutil

    write_field(tmp_path, name="a")
    store = tmp_path / "a.zarr"
    d1 = data.zarr_digest(store)
    assert len(d1) == 64
    assert set(d1) <= set("0123456789abcdef")
    assert data.zarr_digest(store) == d1
    shutil.copytree(store, tmp_path / "elsewhere.zarr")
    assert data.zarr_digest(tmp_path / "elsewhere.zarr") == d1
    chunk = chunk_files(store)[0]
    raw = bytearray(chunk.read_bytes())
    raw[len(raw) // 2] ^= 0x01
    chunk.write_bytes(bytes(raw))
    assert data.zarr_digest(store) != d1


@pytest.mark.req("FR-011-41")
def test_a_128_grid_is_accepted_only_for_a_resolution_transfer_run(tmp_path: Path) -> None:
    transfer = json.loads((EX / "field-dataset.valid-transfer.json").read_text(encoding="utf-8"))
    rec = data.load_field_file(write_field(tmp_path, meta=transfer), root=tmp_path)
    assert rec.data.shape == (14, 128, 128)
    plain = copy.deepcopy(transfer)
    plain["resolution_transfer"] = False
    with pytest.raises(FieldFileError, match=r"grid|resolution_transfer"):
        data.load_field_file(write_field(tmp_path, meta=plain, name="plain"), root=tmp_path)


def meta_edit(fn) -> dict:
    m = copy.deepcopy(META)
    fn(m)
    return m


HOSTILE_META = [
    ("grid-32", meta_edit(lambda m: m.__setitem__("grid", {"nx": 32, "ny": 32})), "grid"),
    ("grid-65x64", meta_edit(lambda m: m.__setitem__("grid", {"nx": 65, "ny": 64})), "grid"),
    ("missing-unit", meta_edit(lambda m: m["channels"][0].pop("unit")), "unit"),
    ("empty-unit", meta_edit(lambda m: m["channels"][3].__setitem__("unit", "")), "unit"),
    ("wrong-unit", meta_edit(lambda m: m["channels"][5].__setitem__("unit", "km")), "unit"),
    ("missing-cell-size", meta_edit(lambda m: m.pop("cell_size_m")), "cell_size_m"),
    ("zero-cell-size", meta_edit(lambda m: m.__setitem__("cell_size_m", 0)), "cell_size_m"),
    ("negative-cell-size", meta_edit(lambda m: m.__setitem__("cell_size_m", -8)), "cell_size_m"),
    ("absolute-path", meta_edit(lambda m: m["store"].__setitem__("path", "/etc/passwd")), "path"),
    ("windows-absolute-path", meta_edit(lambda m: m["store"].__setitem__("path", "C:/data/field.zarr")), "path"),
    ("path-traversal", meta_edit(lambda m: m["store"].__setitem__("path", "../outside.zarr")), "path"),
    ("nested-traversal", meta_edit(lambda m: m["store"].__setitem__("path", "a/../../b.zarr")), "path"),
    ("unknown-model", meta_edit(lambda m: m.__setitem__("model", "snow")), "model"),
    ("wrong-label", meta_edit(lambda m: m.__setitem__("label", "validated against real data")), "label"),
    (
        "output-times",
        meta_edit(
            lambda m: m.__setitem__("output_times_s", [450.0, 900.0, 1350.0, 1800.0, 2250.0, 2700.0, 3150.0, 3500.0])
        ),
        "output_times_s",
    ),
    (
        "three-output-times",
        meta_edit(lambda m: m.__setitem__("output_times_s", [1200.0, 2400.0, 3600.0])),
        "output_times_s",
    ),
    ("breach-outside", meta_edit(lambda m: m["scenario"].__setitem__("breach_row", 64)), "breach"),
    ("negative-breach", meta_edit(lambda m: m["scenario"].__setitem__("breach_col", -1)), "breach"),
    ("unicode-patch-id", meta_edit(lambda m: m.__setitem__("patch_id", "pátch-ñ")), "patch_id"),
    ("malformed-dem-digest", meta_edit(lambda m: m["source_dem"].__setitem__("sha256", "zz")), "sha256"),
]


@pytest.mark.req("FR-011-41")
@pytest.mark.parametrize(("label", "meta", "needle"), HOSTILE_META, ids=[h[0] for h in HOSTILE_META])
def test_each_invalid_metadata_class_is_rejected_with_its_reason(
    tmp_path: Path, label: str, meta: dict, needle: str
) -> None:
    path = write_field(tmp_path, meta=meta)
    # write_field overwrites `store`; re-apply the hostile store edits after the digest was computed
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "store" in meta and meta["store"] != META["store"]:
        raw["store"]["path"] = meta["store"]["path"]
        path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(FieldFileError, match=needle) as info:
        data.load_field_file(path, root=tmp_path)
    assert info.value.reason


def set_value(channel: str, index: tuple[int, int], value: float):
    def mutate(cols: dict) -> None:
        cols[channel][index] = value

    return mutate


HOSTILE_PAYLOAD = [
    ("nan", set_value("bed_elevation", (0, 5), np.nan), False, "non-finite"),
    ("inf", set_value("yield_stress", (0, 9), np.inf), False, "non-finite"),
    ("minus-inf", set_value("density", (3, 3), -np.inf), False, "non-finite"),
    ("depth-below", set_value("depth_t3", (1, 36), -2e-9), False, "depth"),
    ("depth-max-negative", set_value("depth_max", (0, 7), -0.5), False, "depth"),
    ("short-payload", None, True, "shape"),
]


@pytest.mark.req("FR-011-41")
@pytest.mark.parametrize(("label", "mutate", "short", "needle"), HOSTILE_PAYLOAD, ids=[h[0] for h in HOSTILE_PAYLOAD])
def test_each_invalid_payload_class_is_rejected_with_its_reason(
    tmp_path: Path, label: str, mutate, short: bool, needle: str
) -> None:
    with pytest.raises(FieldFileError, match=needle):
        data.load_field_file(write_field(tmp_path, mutate_table=mutate, short=short), root=tmp_path)


@pytest.mark.req("FR-011-41")
def test_a_depth_of_exactly_minus_1e_9_is_not_below_the_limit(tmp_path: Path) -> None:
    at_limit = set_value("depth_t3", (1, 36), -1e-9)
    rec = data.load_field_file(write_field(tmp_path, mutate_table=at_limit), root=tmp_path)
    assert rec.data.shape == (14, 64, 64)


@pytest.mark.req("FR-011-41")
def test_a_negative_value_in_a_non_depth_channel_is_not_a_depth_violation(tmp_path: Path) -> None:
    rec = data.load_field_file(
        write_field(tmp_path, mutate_table=set_value("bed_elevation", (0, 0), -50.0)), root=tmp_path
    )
    assert rec.data[0].min() == pytest.approx(-50.0)


@pytest.mark.req("FR-011-41")
def test_a_changed_payload_fails_the_store_digest_before_it_is_read(tmp_path: Path) -> None:
    path = write_field(tmp_path)
    chunk = chunk_files(tmp_path / "field.zarr")[0]
    raw = bytearray(chunk.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    chunk.write_bytes(bytes(raw))
    with pytest.raises(FieldFileError, match="sha256"):
        data.load_field_file(path, root=tmp_path)


@pytest.mark.req("FR-011-41")
@pytest.mark.parametrize("payload", [b"", b"not a chunk", b"\x00" * 64], ids=["empty", "text", "zeros"])
def test_a_corrupt_chunk_with_a_matching_digest_is_a_field_file_error_not_a_crash(
    tmp_path: Path, payload: bytes
) -> None:
    path = write_field(tmp_path)
    store = tmp_path / "field.zarr"
    chunk_files(store)[0].write_bytes(payload)
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["store"]["sha256"] = data.zarr_digest(store)  # the digest matches: the chunk itself is unreadable
    path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(FieldFileError):
        data.load_field_file(path, root=tmp_path)


@pytest.mark.req("FR-011-41")
@pytest.mark.parametrize(
    "text",
    ["", "{", '{"model": "tailings"', "[]", "null", "\x00\x01"],
    ids=["empty", "open", "truncated", "list", "null", "binary"],
)
def test_a_malformed_metadata_file_is_a_field_file_error(tmp_path: Path, text: str) -> None:
    path = tmp_path / "meta.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(FieldFileError):
        data.load_field_file(path, root=tmp_path)


@pytest.mark.req("FR-011-41")
def test_a_missing_metadata_or_payload_file_is_a_field_file_error(tmp_path: Path) -> None:
    with pytest.raises(FieldFileError):
        data.load_field_file(tmp_path / "absent.json", root=tmp_path)
    import shutil

    path = write_field(tmp_path)
    shutil.rmtree(tmp_path / "field.zarr")
    with pytest.raises(FieldFileError):
        data.load_field_file(path, root=tmp_path)


@pytest.mark.req("FR-011-40")
def test_the_channel_order_of_the_file_must_match_the_models_io_description(tmp_path: Path) -> None:
    path = write_field(tmp_path)
    data.load_field_file(path, root=tmp_path, expected_channels=tuple(CHANNELS))
    swapped = list(CHANNELS)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    with pytest.raises(FieldFileError, match="channels"):
        data.load_field_file(path, root=tmp_path, expected_channels=tuple(swapped))
    with pytest.raises(FieldFileError, match="channels"):
        data.load_field_file(path, root=tmp_path, expected_channels=TAILINGS_INPUTS)
