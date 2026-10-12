# ruff: noqa: E501
"""T-015-033: hostile frame states are rejected by the loader and the query builder lists them and builds nothing from them.

Requirements: FR-015-23.

Spec: specs/015-vlm/spec.md FR-015-23 ("If a frame state is invalid against contracts/frame-state.schema.json - missing
metersPerUnit or upAxis, a non-finite transform, an unknown class label, a duplicated prim id, an empty object list or a
SHA-256 mismatch with its frame - then the builder shall reject that frame, list it with the reason, and generate no query
from it"); plan.md test strategy ("hostile frame-state corpus", pytest + Hypothesis).

Oracle: the spec's own list of hostile classes, written out as mutations of a hand-built valid frame state
(`_p015_kit.frame_state`); the SHA-256 of the frame image is recomputed with `hashlib` in the kit. JSON Schema 2020-12
semantics (reference implementation `jsonschema`) decide what the schema alone rejects; the loader must additionally reject
what the schema cannot express (NaN and infinities, duplicated prim ids, a digest that differs from the image bytes).

Expected API of the implementation (package `pitstudio`, root environment, NumPy):
- `pitstudio.reason.frames.FrameStateInvalid(ValueError)`: class attribute `error_class == "frame-state-invalid"`; the message
  names the offending field (for example `metersPerUnit`, `camera`, `image`) or, for an object problem, the `prim_id`.
- `pitstudio.reason.frames.load_frame_state(source, *, root) -> dict`: `source` is a mapping or the path of a JSON file; `root`
  is the folder the relative `image.path` is resolved against. It validates the document against
  `contracts/frame-state.schema.json`, requires finite numbers everywhere, unique `prim_id` values and
  `sha256(root / image.path bytes) == image.sha256`, and returns the validated document unchanged. It raises
  `FrameStateInvalid` for any violation (never `KeyError`, `TypeError` or `JSONDecodeError`).
- `pitstudio.reason.queries.build_queries(frames, *, root, seed, per_type=1080, truth_fn=None) -> QueryBuild` with
  `.queries` (list of DC-015-02 query dicts) and `.rejected` (list of `Rejection(index, frame_id, reason)`; `index` is the
  position in `frames`, `frame_id` is None when unreadable, `reason` is the loader message). `truth_fn(frame, qtype)` returns
  the exact answer label or None (not asked); when None the module's own ground truth is used.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import _p015_kit as kit
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pitstudio.reason.frames import FrameStateInvalid, load_frame_state
from pitstudio.reason.queries import build_queries


@pytest.fixture
def root(tmp_path: Path) -> Path:
    kit.write_frame_files(tmp_path)
    return tmp_path


def _valid() -> dict:
    return kit.frame_state([kit.truck(100.0, 0.0), kit.person(110.0, 5.0), kit.light_vehicle(120.0, -3.0)])


def _mut(doc: dict, path: list, value: object) -> dict:
    d = copy.deepcopy(doc)
    cur = d
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = value
    return d


def _drop(doc: dict, path: list) -> dict:
    d = copy.deepcopy(doc)
    cur = d
    for k in path[:-1]:
        cur = cur[k]
    del cur[path[-1]]
    return d


def _hostile() -> list[tuple[str, dict, str]]:
    """(name, hostile document, text the error must name)."""
    v = _valid()
    dup = copy.deepcopy(v)
    dup["objects"][1]["prim_id"] = dup["objects"][0]["prim_id"]
    out = [
        ("missing-metersPerUnit", _drop(v, ["metersPerUnit"]), "metersPerUnit"),
        ("missing-upAxis", _drop(v, ["upAxis"]), "upAxis"),
        ("unknown-upAxis", _mut(v, ["upAxis"], "X"), "upAxis"),
        ("zero-metersPerUnit", _mut(v, ["metersPerUnit"], 0), "metersPerUnit"),
        ("negative-metersPerUnit", _mut(v, ["metersPerUnit"], -0.01), "metersPerUnit"),
        ("string-metersPerUnit", _mut(v, ["metersPerUnit"], "0.01"), "metersPerUnit"),
        ("nan-metersPerUnit", _mut(v, ["metersPerUnit"], math.nan), "metersPerUnit"),
        ("unknown-class", _mut(v, ["objects", 1, "class"], "excavator"), v["objects"][1]["prim_id"]),
        ("unicode-class", _mut(v, ["objects", 0, "class"], "camión"), v["objects"][0]["prim_id"]),
        ("duplicate-prim-id", dup, v["objects"][0]["prim_id"]),
        ("empty-objects", _mut(v, ["objects"], []), "objects"),
        ("no-objects-key", _drop(v, ["objects"]), "objects"),
        ("nan-translation", _mut(v, ["objects", 0, "pose", "translation_m", 0], math.nan), v["objects"][0]["prim_id"]),
        ("inf-translation", _mut(v, ["objects", 2, "pose", "translation_m", 1], math.inf), v["objects"][2]["prim_id"]),
        (
            "neg-inf-footprint",
            _mut(v, ["objects", 1, "footprint", "centre_m", 0], -math.inf),
            v["objects"][1]["prim_id"],
        ),
        ("nan-rotation", _mut(v, ["objects", 0, "pose", "rotation_xyzw", 3], math.nan), v["objects"][0]["prim_id"]),
        ("nan-camera", _mut(v, ["camera", "pose", "translation_m", 2], math.nan), "camera"),
        ("huge-coordinate", _mut(v, ["objects", 0, "pose", "translation_m", 0], 1e9), v["objects"][0]["prim_id"]),
        (
            "wrong-unit-key",
            _mut(v, ["objects", 0, "pose"], {"translation_cm": [1, 2, 3], "rotation_xyzw": [0, 0, 0, 1]}),
            v["objects"][0]["prim_id"],
        ),
        ("negative-visible-px", _mut(v, ["objects", 0, "visible_px"], -1), v["objects"][0]["prim_id"]),
        ("float-visible-px", _mut(v, ["objects", 0, "visible_px"], 12.5), v["objects"][0]["prim_id"]),
        ("bad-prim-path", _mut(v, ["objects", 0, "prim_id"], "World/HaulTruck"), "prim_id"),
        ("image-digest-wrong", _mut(v, ["image", "sha256"], "0" * 64), "image"),
        ("image-digest-upper", _mut(v, ["image", "sha256"], kit.IMAGE_SHA256.upper()), "image"),
        ("image-path-traversal", _mut(v, ["image", "path"], "../secret.png"), "image"),
        ("image-path-absolute", _mut(v, ["image", "path"], "/etc/passwd"), "image"),
        ("image-missing-file", _mut(v, ["image", "path"], "img/absent.png"), "image"),
        ("not-synthetic", _mut(v, ["synthetic"], False), "synthetic"),
        ("extra-field", _mut(v, ["gps"], [1, 2]), "gps"),
        ("unknown-condition", _mut(v, ["condition"], "fog"), "condition"),
        ("empty-document", {}, ""),
    ]
    return out


@pytest.mark.req("FR-015-23")
def test_a_valid_frame_state_is_returned_unchanged(root: Path) -> None:
    doc = _valid()
    assert load_frame_state(doc, root=root) == doc


@pytest.mark.req("FR-015-23")
def test_a_valid_frame_state_file_is_loaded_from_disk(root: Path) -> None:
    doc = _valid()
    p = root / "frame.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert load_frame_state(p, root=root) == doc


@pytest.mark.req("FR-015-23")
@pytest.mark.parametrize(("name", "doc", "names"), _hostile(), ids=[h[0] for h in _hostile()])
def test_each_hostile_frame_state_is_rejected_naming_the_problem(root: Path, name: str, doc: dict, names: str) -> None:
    with pytest.raises(FrameStateInvalid) as exc:
        load_frame_state(doc, root=root)
    assert exc.value.error_class == "frame-state-invalid", name
    assert names in str(exc.value), f"{name}: the message must name {names!r}: {exc.value}"


@pytest.mark.req("FR-015-23")
def test_the_image_bytes_on_disk_must_match_the_declared_digest(root: Path) -> None:
    (root / "img" / "frame.png").write_bytes(kit.IMAGE_BYTES + b"tampered")
    with pytest.raises(FrameStateInvalid, match=r"sha256|digest"):
        load_frame_state(_valid(), root=root)


@pytest.mark.req("FR-015-23")
@pytest.mark.parametrize("text", ["", "not json", "{", "[1, 2]", "null", '{"frame_id": "é"}'])
def test_malformed_frame_state_files_raise_the_frame_state_error(root: Path, text: str) -> None:
    p = root / "bad.json"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(FrameStateInvalid):
        load_frame_state(p, root=root)


@pytest.mark.req("FR-015-23")
@pytest.mark.parametrize("source", [None, 5, "text", [1, 2], b"{}"])
def test_non_mapping_non_path_sources_raise_the_frame_state_error(root: Path, source: object) -> None:
    with pytest.raises(FrameStateInvalid):
        load_frame_state(source, root=root)  # type: ignore[arg-type]


def _pool(n: int) -> list[dict]:
    conds = ["day", "night", "dust", "rain"]
    locs = ["haul_road", "bench", "loading_area"]
    return [
        kit.frame_state(
            [kit.truck(100.0, 0.0), kit.person(110.0, 5.0)],
            frame_id=f"f{i:04d}",
            condition=conds[i % 4],
            location=locs[i % 3],
        )
        for i in range(n)
    ]


def _truth(frame: dict, qtype: int) -> str:
    k = int(frame["frame_id"][1:]) // 4
    return ["0", "1", "2", "3+"][k % 4] if qtype == 3 else ("yes" if k % 2 == 0 else "no")


@pytest.mark.req("FR-015-23")
def test_the_builder_lists_every_rejected_frame_with_its_reason_and_builds_no_query_from_it(root: Path) -> None:
    frames = _pool(64)
    hostile = _hostile()[:20]
    mixed: list[dict] = []
    bad_positions: dict[int, str] = {}
    for i, f in enumerate(frames):
        mixed.append(f)
        if i < len(hostile):
            name, doc, _ = hostile[i]
            doc = copy.deepcopy(doc)
            if isinstance(doc.get("frame_id"), str):
                doc["frame_id"] = f"bad{i:02d}"
            bad_positions[len(mixed)] = name
            mixed.append(doc)
    res = build_queries(mixed, root=root, seed=1, per_type=4, truth_fn=_truth)
    assert {r.index for r in res.rejected} == set(bad_positions)
    for r in res.rejected:
        assert r.reason, f"empty reason for {bad_positions[r.index]}"
    bad_ids = {f"bad{i:02d}" for i in range(len(hostile))}
    assert all(q["frame_id"] not in bad_ids for q in res.queries)
    assert len(res.queries) == 6 * 4


@pytest.mark.req("FR-015-23")
def test_a_pool_made_only_of_hostile_frames_gives_no_query(root: Path) -> None:
    docs = [h[1] for h in _hostile()]
    res = build_queries(docs, root=root, seed=1, per_type=4, truth_fn=_truth)
    assert res.queries == []
    assert len(res.rejected) == len(docs)


_LEAF = st.one_of(
    st.just(math.nan),
    st.just(math.inf),
    st.just(-math.inf),
    st.just(None),
    st.just(True),
    st.integers(-(10**12), 10**12),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(max_size=20),
    st.just([]),
    st.just({}),
)


def _paths(doc: object, prefix: tuple = ()) -> list[tuple]:
    out = [prefix]
    if isinstance(doc, dict):
        for k, v in doc.items():
            out += _paths(v, (*prefix, k))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            out += _paths(v, (*prefix, i))
    return out


_ALL_PATHS = [p for p in _paths(_valid()) if p]


@pytest.mark.req("FR-015-23")
@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(idx=st.integers(0, len(_ALL_PATHS) - 1), leaf=_LEAF)
def test_property_any_single_field_mutation_is_either_valid_or_raises_only_the_frame_state_error(
    root: Path, idx: int, leaf: object
) -> None:
    doc = _mut(_valid(), list(_ALL_PATHS[idx]), leaf)
    try:
        out = load_frame_state(doc, root=root)
    except FrameStateInvalid:
        return
    assert out == doc
