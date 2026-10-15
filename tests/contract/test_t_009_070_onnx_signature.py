# ruff: noqa: E501
"""T-009-070 - FR-009-35, FR-009-36: detector and segmenter ONNX signatures.

Oracles (independent of the code under test; plan 009 test strategy rows FR-009-35 / FR-009-36):
- hand-built ONNX graphs written with `onnx.helper` in this file, each valid for the reference checker `onnx.checker.check_model` (asserted by the tests), so the inspector is
  exercised on real ModelProto objects: a conforming D-FINE-style graph (default-domain opset 19, a `GridSample` node, inputs `images` float32 [N, 3, 640, 640] and `orig_target_sizes`
  int64 [N, 2], outputs `labels` int64 [N, 300], `boxes` float32 [N, 300, 4], `scores` float32 [N, 300], a `TopK` with k = 300 as the in-graph top-300 selection, no
  `NonMaxSuppression`) passes; opset 20 (where `GridSample` has since-version 20), a wrong input or output name, dtype or shape, an extra input or output, a `NonMaxSuppression` node
  and a missing `TopK` each fail with a violation that names the problem;
- ONNX operator facts (onnx.ai/onnx/operators): `GridSample` has since-versions 16 and 20; in a model whose default-domain opset is 19 the node resolves to version 16, in a model at opset 20 to
  version 20 (the spec requires 16);
- the RF-DETR-Seg-N signature of spec 009 section 7 (resolution 312, 100 queries): one float32 input [N, 3, 312, 312], three outputs (boxes [N, 100, 4], labels int64 [N, 100], masks
  float32 [N, 100, h, w]), default-domain opset 19; a 320 x 320 input, opset 18 or a missing output fail; its initial lane is precompute at every precision (FR-009-36);
- slow test on the real export (needs the upstream D-FINE-N checkpoint of the asset staging in `PITSTUDIO_DFINE_N_CHECKPOINT`): the exported file passes the inspector and runs in
  onnxruntime on a 640 x 640 zero image with the output shapes [1, 300] / [1, 300, 4] / [1, 300].

Expected public API (module `pitstudio_pipeline.perception.export_hooks`, package under `pipeline/src/`; `onnx` is a dependency of the pipeline lane):

    SignatureError(ValueError)       .violations: tuple[str, ...] (one sentence per violation; str(error) contains all of them)
    inspect_dfine(model: onnx.ModelProto) -> None
        Raises SignatureError listing EVERY violation of FR-009-35: the default-domain ("" or "ai.onnx") opset import is missing or not 19 (the sentence contains "opset", and "GridSample" when the model
        has a GridSample node, which then resolves to a version other than 16); the graph inputs are not exactly `images` (float32, rank 4, dims 1..3 == 3, 640, 640) and `orig_target_sizes`
        (int64, rank 2, last dim 2) (sentence contains the input name); the outputs are not exactly `labels` (int64, [N, 300]), `boxes` (float32, [N, 300, 4]) and `scores` (float32, [N, 300])
        (sentence contains the output name); a `NonMaxSuppression` node exists (sentence contains "NonMaxSuppression"); no `TopK` node exists (sentence contains "TopK"). A non-ModelProto raises
        SignatureError whose violation contains "ModelProto". Dimension N may be symbolic or any positive int.
    inspect_rfdetr_seg(model: onnx.ModelProto, *, output_names: Sequence[str]) -> None
        FR-009-36 with the upstream output names given in the order (boxes, labels, masks): default-domain opset 19 ("opset"); exactly one float32 rank-4 input whose last two dims are 312 and 312
        ("312"); exactly the three outputs named `output_names` with boxes float32 [N, 100, 4], labels int64 [N, 100], masks float32 rank 4 with dim 1 == 100 (sentence contains the output name).
    initial_lane(model: str, precision: str) -> str
        "precompute" for model "rf-detr-seg-n" at every precision (fp32, fp16, int8); (the D-FINE lanes are covered by T-009-071). ValueError (message names the argument) for an unknown model or precision.
    export_dfine_onnx(checkpoint: pathlib.Path, output: pathlib.Path) -> pathlib.Path
        Exports the D-FINE checkpoint at opset 19 with the in-graph post-processor (upstream tools/deployment/export_onnx.py logic, re-exported at 19) and returns `output`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.perception import export_hooks as hooks  # noqa: E402


def _dfine(
    *,
    opset: int | None = 19,
    images_dtype: str = "FLOAT",
    images_shape: tuple = ("N", 3, 640, 640),
    sizes_dtype: str = "INT64",
    sizes_shape: tuple = ("N", 2),
    out_names: tuple[str, str, str] = ("labels", "boxes", "scores"),
    labels_dtype: str = "INT64",
    boxes_dtype: str = "FLOAT",
    scores_dtype: str = "FLOAT",
    boxes_shape: tuple = ("N", 300, 4),
    topk: bool = True,
    nms: bool = False,
    grid_sample: bool = True,
    extra_input: bool = False,
    extra_output: bool = False,
):
    """A small, checker-valid graph with the D-FINE signature: images -> pooled -> MatMul -> logits [N, 1200]; TopK(k = 300) gives scores and labels; a Reshape gives boxes."""
    import numpy as np
    import onnx
    from onnx import TensorProto as TP
    from onnx import helper as h
    from onnx import numpy_helper as nh

    def dt(name: str) -> int:
        return getattr(TP, name)

    def vi(name, dtype, shape):
        return h.make_tensor_value_info(name, dt(dtype), list(shape))

    inits = [
        nh.from_array(np.full((3, 1200), 0.01, dtype=np.float32), "w"),
        nh.from_array(np.array([0, 300, 4], dtype=np.int64), "box_shape"),
        nh.from_array(np.array([300], dtype=np.int64), "k"),
        nh.from_array(np.array([0], dtype=np.int64), "zero"),
        nh.from_array(np.array([1], dtype=np.int64), "one"),
        nh.from_array(np.zeros((1, 1, 4, 4), dtype=np.float32), "gs_x"),
        nh.from_array(np.zeros((1, 2, 2, 2), dtype=np.float32), "gs_grid"),
        nh.from_array(np.zeros((1, 4, 4), dtype=np.float32), "nms_boxes"),
        nh.from_array(np.zeros((1, 1, 4), dtype=np.float32), "nms_scores"),
    ]
    nodes = [
        h.make_node("GlobalAveragePool", ["images"], ["pooled"]),
        h.make_node("Flatten", ["pooled"], ["flat"], axis=1),
        h.make_node("MatMul", ["flat", "w"], ["logits"]),
        h.make_node("Reshape", ["logits", "box_shape"], ["boxes_raw"]),
    ]
    if topk:
        nodes.append(h.make_node("TopK", ["logits", "k"], ["scores_raw", "labels_raw"], axis=1))
    else:
        nodes += [
            h.make_node("Slice", ["logits", "zero", "k", "one"], ["scores_raw"]),
            h.make_node("Cast", ["scores_raw"], ["labels_raw"], to=TP.INT64),
        ]
    if grid_sample:
        nodes += [
            h.make_node("GridSample", ["gs_x", "gs_grid"], ["gs_y"]),
            h.make_node("ReduceSum", ["gs_y"], ["gs_sum"], keepdims=0),
            h.make_node("Add", ["scores_raw", "gs_sum"], ["scores_mixed"]),
        ]
    else:
        nodes.append(h.make_node("Identity", ["scores_raw"], ["scores_mixed"]))
    if nms:
        nodes.append(h.make_node("NonMaxSuppression", ["nms_boxes", "nms_scores"], ["nms_idx"]))
    n_labels, n_boxes, n_scores = out_names
    nodes += [
        h.make_node("Cast", ["labels_raw"], [n_labels], to=dt(labels_dtype)),
        h.make_node("Cast", ["boxes_raw"], [n_boxes], to=dt(boxes_dtype)),
        h.make_node("Cast", ["scores_mixed"], [n_scores], to=dt(scores_dtype)),
    ]
    inputs = [vi("images", images_dtype, images_shape), vi("orig_target_sizes", sizes_dtype, sizes_shape)]
    if extra_input:
        inputs.append(vi("mask", "FLOAT", ("N", 1)))
    outputs = [
        vi(n_labels, labels_dtype, ("N", 300)),
        vi(n_boxes, boxes_dtype, boxes_shape),
        vi(n_scores, scores_dtype, ("N", 300)),
    ]
    if extra_output:
        nodes.append(h.make_node("Identity", ["labels_raw"], ["extra"]))
        outputs.append(vi("extra", "INT64", ("N", 300)))
    graph = h.make_graph(nodes, "dfine_like", inputs, outputs, initializer=inits)
    imports = [h.make_opsetid("", opset)] if opset is not None else [h.make_opsetid("com.example", 1)]
    model = h.make_model(graph, opset_imports=imports, producer_name="pitstudio-test")
    model.ir_version = 9
    return model, onnx


def _check(model, onnx) -> None:
    onnx.checker.check_model(model)


def _violations(model) -> tuple[str, ...]:
    with pytest.raises(hooks.SignatureError) as exc:
        hooks.inspect_dfine(model)
    assert isinstance(exc.value, ValueError)
    assert all(v in str(exc.value) for v in exc.value.violations)
    return exc.value.violations


def _mentions(violations: tuple[str, ...], word: str) -> bool:
    return any(word in v for v in violations)


# ---------------------------------------------------------------- FR-009-35


@pytest.mark.req("FR-009-35")
def test_a_conforming_graph_is_valid_for_the_checker_and_passes_the_inspector() -> None:
    model, onnx = _dfine()
    _check(model, onnx)
    assert hooks.inspect_dfine(model) is None


@pytest.mark.req("FR-009-35")
def test_a_fixed_batch_of_one_is_accepted() -> None:
    model, onnx = _dfine(images_shape=(1, 3, 640, 640), sizes_shape=(1, 2))
    _check(model, onnx)
    assert hooks.inspect_dfine(model) is None


@pytest.mark.req("FR-009-35")
def test_opset_19_with_grid_sample_at_version_16_passes_and_opset_20_fails() -> None:
    ok, onnx = _dfine(opset=19, grid_sample=True)
    assert any(n.op_type == "GridSample" for n in ok.graph.node)
    assert hooks.inspect_dfine(ok) is None
    bad, onnx = _dfine(opset=20, grid_sample=True)
    _check(bad, onnx)  # a valid opset-20 model: GridSample-20
    v = _violations(bad)
    assert _mentions(v, "opset")
    assert _mentions(v, "GridSample")


@pytest.mark.req("FR-009-35")
@pytest.mark.parametrize("opset", [16, 17, 18, 21])
def test_any_default_domain_opset_other_than_19_fails(opset: int) -> None:
    model, _ = _dfine(opset=opset, grid_sample=False)
    assert _mentions(_violations(model), "opset")


@pytest.mark.req("FR-009-35")
def test_a_model_without_a_default_domain_opset_fails() -> None:
    model, _ = _dfine(opset=None, grid_sample=False)
    assert _mentions(_violations(model), "opset")


@pytest.mark.req("FR-009-35")
@pytest.mark.parametrize(
    ("kwargs", "word"),
    [
        ({"images_dtype": "FLOAT16"}, "images"),
        ({"images_shape": ("N", 3, 320, 320)}, "images"),
        ({"images_shape": ("N", 1, 640, 640)}, "images"),
        ({"images_shape": ("N", 640, 640)}, "images"),
        ({"sizes_dtype": "INT32"}, "orig_target_sizes"),
        ({"sizes_dtype": "FLOAT"}, "orig_target_sizes"),
        ({"sizes_shape": ("N", 3)}, "orig_target_sizes"),
        ({"extra_input": True}, "input"),
    ],
)
def test_a_wrong_input_declaration_fails_naming_the_input(kwargs: dict, word: str) -> None:
    model, _ = _dfine(**kwargs)
    assert _mentions(_violations(model), word)


@pytest.mark.req("FR-009-35")
@pytest.mark.parametrize(
    ("kwargs", "word"),
    [
        ({"out_names": ("classes", "boxes", "scores")}, "labels"),
        ({"out_names": ("labels", "bboxes", "scores")}, "boxes"),
        ({"out_names": ("labels", "boxes", "confidence")}, "scores"),
        ({"labels_dtype": "INT32"}, "labels"),
        ({"boxes_dtype": "FLOAT16"}, "boxes"),
        ({"scores_dtype": "FLOAT16"}, "scores"),
        ({"boxes_shape": ("N", 100, 4)}, "boxes"),
        ({"boxes_shape": ("N", 300, 5)}, "boxes"),
        ({"extra_output": True}, "output"),
    ],
)
def test_a_wrong_output_declaration_fails_naming_the_output(kwargs: dict, word: str) -> None:
    model, _ = _dfine(**kwargs)
    assert _mentions(_violations(model), word)


@pytest.mark.req("FR-009-35")
def test_a_non_maximum_suppression_node_fails() -> None:
    model, onnx = _dfine(nms=True)
    _check(model, onnx)
    assert _mentions(_violations(model), "NonMaxSuppression")


@pytest.mark.req("FR-009-35")
def test_a_graph_without_the_in_graph_top_k_selection_fails() -> None:
    model, _ = _dfine(topk=False)
    assert _mentions(_violations(model), "TopK")


@pytest.mark.req("FR-009-35")
def test_every_violation_is_listed_not_just_the_first() -> None:
    model, _ = _dfine(
        opset=18, images_dtype="FLOAT16", out_names=("labels", "boxes", "conf"), nms=True, topk=False, grid_sample=False
    )
    v = _violations(model)
    for word in ("opset", "images", "scores", "NonMaxSuppression", "TopK"):
        assert _mentions(v, word), (word, v)


@pytest.mark.req("FR-009-35")
@pytest.mark.parametrize("bad", [None, b"\x08\x07", "model.onnx", 7, [], {}])
def test_a_non_model_is_a_signature_error(bad: object) -> None:
    with pytest.raises(hooks.SignatureError) as exc:
        hooks.inspect_dfine(bad)  # type: ignore[arg-type]
    assert any("ModelProto" in v for v in exc.value.violations)


# ---------------------------------------------------------------- FR-009-36


NAMES = ("dets", "labels", "masks")


def _rfdetr(
    *,
    opset: int = 19,
    size: int = 312,
    dtype: str = "FLOAT",
    n_outputs: int = 3,
    labels_dtype: str = "INT64",
    names: tuple = NAMES,
    extra_input: bool = False,
    queries: int = 100,
):
    """A small, checker-valid graph with the RF-DETR-Seg-N signature: input [N, 3, size, size] -> boxes [N, queries, 4]; labels int64 [1, queries]; masks [1, queries, 2, 2]."""
    import numpy as np
    import onnx
    from onnx import TensorProto as TP
    from onnx import helper as h
    from onnx import numpy_helper as nh

    vi = h.make_tensor_value_info
    inits = [
        nh.from_array(np.full((3, queries * 4), 0.01, dtype=np.float32), "w"),
        nh.from_array(np.array([0, queries, 4], dtype=np.int64), "bshape"),
        nh.from_array(np.zeros((1, queries, 2, 2), dtype=np.float32), "m"),
        nh.from_array(np.zeros((1, queries), dtype=np.int64), "lab"),
    ]
    nodes = [
        h.make_node("GlobalAveragePool", ["input"], ["p"]),
        h.make_node("Flatten", ["p"], ["f"], axis=1),
        h.make_node("MatMul", ["f", "w"], ["l"]),
        h.make_node("Reshape", ["l", "bshape"], [names[0]]),
        h.make_node("Cast", ["lab"], [names[1]], to=getattr(TP, labels_dtype)),
        h.make_node("Identity", ["m"], [names[2]]),
    ]
    outs = [
        vi(names[0], TP.FLOAT, ["N", queries, 4]),
        vi(names[1], getattr(TP, labels_dtype), [1, queries]),
        vi(names[2], TP.FLOAT, [1, queries, 2, 2]),
    ]
    inputs = [vi("input", getattr(TP, dtype), ["N", 3, size, size])]
    if extra_input:
        inputs.append(vi("extra", TP.FLOAT, ["N", 1]))
    keep = n_outputs
    model = h.make_model(
        h.make_graph(
            nodes[: 4 + (keep - 1)] if keep < 3 else nodes, "rfdetr_like", inputs, outs[:keep], initializer=inits
        ),
        opset_imports=[h.make_opsetid("", opset)],
    )
    model.ir_version = 9
    return model, onnx


@pytest.mark.req("FR-009-36")
def test_a_conforming_segmenter_graph_passes() -> None:
    model, onnx = _rfdetr()
    _check(model, onnx)
    assert hooks.inspect_rfdetr_seg(model, output_names=NAMES) is None


def _seg_violations(model, names=NAMES) -> tuple[str, ...]:
    with pytest.raises(hooks.SignatureError) as exc:
        hooks.inspect_rfdetr_seg(model, output_names=names)
    return exc.value.violations


@pytest.mark.req("FR-009-36")
@pytest.mark.parametrize(
    ("kwargs", "word"),
    [
        ({"opset": 18}, "opset"),
        ({"opset": 20}, "opset"),
        ({"size": 320}, "312"),
        ({"size": 640}, "312"),
        ({"dtype": "FLOAT16"}, "input"),
        ({"extra_input": True}, "input"),
        ({"n_outputs": 2}, "masks"),
        ({"labels_dtype": "INT32"}, "labels"),
        ({"queries": 300}, "dets"),
    ],
)
def test_a_segmenter_graph_that_breaks_the_signature_fails(kwargs: dict, word: str) -> None:
    model, _ = _rfdetr(**kwargs)
    assert any(word in v for v in _seg_violations(model))


@pytest.mark.req("FR-009-36")
def test_the_segmenter_inspector_follows_the_given_upstream_output_names() -> None:
    model, _ = _rfdetr(names=("boxes", "labels", "masks"))
    assert hooks.inspect_rfdetr_seg(model, output_names=("boxes", "labels", "masks")) is None
    assert any("dets" in v for v in _seg_violations(model, NAMES))


@pytest.mark.req("FR-009-36")
@pytest.mark.parametrize("precision", ["fp32", "fp16", "int8"])
def test_rf_detr_seg_n_is_precompute_at_every_precision(precision: str) -> None:
    assert hooks.initial_lane("rf-detr-seg-n", precision) == "precompute"


@pytest.mark.req("FR-009-36")
@pytest.mark.parametrize(
    ("model", "precision", "arg"),
    [
        ("yolo", "fp32", "model"),
        ("", "fp32", "model"),
        ("rf-detr-seg-n", "fp64", "precision"),
        ("rf-detr-seg-n", "", "precision"),
        (None, "fp32", "model"),
    ],
)
def test_the_lane_rule_rejects_unknown_models_and_precisions(model: object, precision: str, arg: str) -> None:
    with pytest.raises(ValueError, match=arg):
        hooks.initial_lane(model, precision)  # type: ignore[arg-type]


# ---------------------------------------------------------------- slow: the real export


@pytest.mark.slow
@pytest.mark.req("FR-009-35")
def test_the_real_d_fine_n_export_passes_the_inspector_and_runs_in_onnxruntime(tmp_path: Path) -> None:
    import numpy as np
    import onnx
    import onnxruntime as ort

    ckpt = Path(os.environ["PITSTUDIO_DFINE_N_CHECKPOINT"])
    out = hooks.export_dfine_onnx(ckpt, tmp_path / "dfine_n.onnx")
    model = onnx.load(str(out))
    onnx.checker.check_model(model)
    assert hooks.inspect_dfine(model) is None
    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    labels, boxes, scores = sess.run(
        ["labels", "boxes", "scores"],
        {"images": np.zeros((1, 3, 640, 640), np.float32), "orig_target_sizes": np.array([[640, 640]], np.int64)},
    )
    assert labels.shape == (1, 300)
    assert labels.dtype == np.int64
    assert boxes.shape == (1, 300, 4)
    assert scores.shape == (1, 300)
    assert np.isfinite(boxes).all()
    assert np.isfinite(scores).all()
