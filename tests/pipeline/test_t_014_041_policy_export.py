# ruff: noqa: E501
"""T-014-041: policy handoff contract, export hooks (opset 17, IR 10, normaliser in the graph, < 1 MB, parity on >= 200 goldens), hostile handoffs.

Requirements: FR-014-27, FR-014-28, NFR-014-03, SC-014-10.

Spec: specs/014-robot-learning/spec.md FR-014-27: "When training ends, `st60_il_train` shall write a policy handoff valid against
`contracts/il-policy-handoff.schema.json` ..., and `s60_export` (spec 016) shall export it as ONNX opset 17 with IR version 10, with the normaliser
inside the graph and a file size < 1 MB, with parity against PyTorch of rtol 1e-3, atol 1e-5 and max abs 1e-4 on >= 200 golden observations drawn from
the evaluation rollouts." FR-014-28: "If a policy handoff fails its schema or SHA-256, declares an observation size other than 63 (IL-1) or 46
(IL-2/IL-3), or holds a non-finite normaliser value or a variance <= 0, then `s60_export` shall reject it and export nothing." NFR-014-03: exported policy
< 1 MB. SC-014-10: export parity fp32 rtol 1e-3 / atol 1e-5.

Oracle: (1) the reference implementations `onnx` (read-back of `ir_version`, the opset import, `onnx.checker`, graph initialisers and node types) and
`onnxruntime` CPU for the exported file; (2) a PyTorch module built in this test from the same checkpoint tensors (an `nn.Sequential` of Linear and the
named activation) with the normaliser applied by hand as (x - mean) / (sqrt(var) + 1e-2) (the `EmpiricalNormalization` of rsl_rl, default eps 1e-2;
UNVERIFIED against the rsl_rl 5.4.1 source, see the red report); (3) `hashlib` for digests; (4) the spec's hostile handoff corpus (`index.json`) and hand-built
mutations. "Export nothing" is checked on the output folder.

Expected API of the implementation (module `pitstudio_pipeline.export.il`, pipeline environment; module name proposed here, spec 016 owns `s60_export`):
    ExportRejected(ValueError): attribute `pointer` (JSON pointer or field name of the first offending member); str(error) contains it
    export_il_policy(handoff, *, root, out_dir) -> ExportResult
        handoff: a dict or the path of a JSON file valid against contracts/il-policy-handoff.schema.json; root: the folder the relative paths of the handoff
        (checkpoint.path, goldens.path) are resolved against. The checkpoint is a torch file {"model_state_dict": {"actor.0.weight": ..., "actor.0.bias": ...,
        "actor.2.weight": ..., "actor.4.weight": ..., "actor.4.bias": ...}, "iter": n} (the rsl_rl layout: Linear layers at the even indices of the actor
        Sequential, the activation of the handoff in between); the goldens file is an .npz with the array `observations` of shape (count, observation_size).
        The mean action is exported: y = actor((x - mean) / (sqrt(var) + 1e-2)) with the normaliser constants inside the graph, input "obs" of shape
        (batch, observation_size), output "action" of shape (batch, action_size), opset 17, IR version 10, fp32.
        Writes <out_dir>/<policy lower case without hyphen>.onnx (il1.onnx, il2.onnx, il3.onnx) and returns ExportResult (frozen dataclass): onnx_path, sha256 (hex
        digest of the file), bytes, parity (dict with count, max_abs, rtol, atol and ok), input_name ("obs"), output_name ("action"). Raises ExportRejected
        (and writes nothing) for: a handoff failing its schema (pointer of the schema error), an observation size other than 63 for IL-1 or 46 for IL-2 and IL-3
        (pointer "/observation_size"), a normaliser value that is not finite (pointer "/normaliser/mean" or "/normaliser/var"), a variance <= 0
        ("/normaliser/var"), a normaliser whose length differs from the observation size, a golden file whose SHA-256 differs from goldens.sha256 or that holds
        fewer rows than goldens.count or than 200 ("/goldens"), a checkpoint whose tensors do not fit the declared sizes and hidden units
        ("/checkpoint"), and a parity failure (pointer "/parity").
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import os
from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.export.il import ExportRejected, export_il_policy

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "014-robot-learning" / "contracts" / "examples"
EPS = 1e-2


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_run(tmp_path: Path, *, policy="IL-1", activation="elu", n_golden=256, seed=0):
    """A fake training run on disk: checkpoint, goldens and a valid handoff. Returns (handoff dict, root, torch reference callable)."""
    import torch

    base = json.loads(
        (EX / ("il-policy-handoff.valid.json" if policy == "IL-1" else "il-policy-handoff.valid-il2.json")).read_text(
            "utf-8"
        )
    )
    n_obs, n_act = (63, 2) if policy == "IL-1" else (46, 4)
    g = torch.Generator().manual_seed(seed)
    layers = {}
    sizes = [n_obs, 256, 256, n_act]
    for i, (a, b) in enumerate(itertools.pairwise(sizes)):
        layers[f"actor.{2 * i}.weight"] = torch.randn(b, a, generator=g) * (1.0 / math.sqrt(a))
        layers[f"actor.{2 * i}.bias"] = torch.randn(b, generator=g) * 0.1
    layers["critic.0.weight"] = torch.randn(1, n_obs, generator=g)  # present in a real checkpoint, must be ignored
    root = tmp_path / "run"
    (root / "checkpoints").mkdir(parents=True)
    (root / "goldens").mkdir()
    ckpt = root / "checkpoints" / "model_1500.pt"
    torch.save({"model_state_dict": layers, "iter": 1500}, ckpt)
    rng = np.random.default_rng(seed + 1)
    mean = rng.normal(0.0, 1.0, n_obs)
    var = rng.uniform(0.5, 4.0, n_obs)
    obs = (mean + rng.normal(0.0, 1.0, (n_golden, n_obs)) * np.sqrt(var)).astype(np.float32)
    npz = root / "goldens" / "observations.npz"
    np.savez(npz, observations=obs)
    handoff = copy.deepcopy(base)
    handoff["checkpoint"] = {
        "id": "ckpt-1500",
        "path": "checkpoints/model_1500.pt",
        "sha256": sha(ckpt),
        "iteration": 1500,
    }
    handoff["normaliser"] = {"mean": mean.tolist(), "var": var.tolist()}
    handoff["actor"] = {"hidden_units": [256, 256], "activation": activation}
    handoff["goldens"] = {"path": "goldens/observations.npz", "sha256": sha(npz), "count": n_golden}

    act = {"elu": torch.nn.ELU, "relu": torch.nn.ReLU, "tanh": torch.nn.Tanh}[activation]
    net = torch.nn.Sequential(
        torch.nn.Linear(n_obs, 256), act(), torch.nn.Linear(256, 256), act(), torch.nn.Linear(256, n_act)
    )
    net.load_state_dict({k.removeprefix("actor."): v for k, v in layers.items() if k.startswith("actor.")})

    def reference(x: np.ndarray) -> np.ndarray:
        z = (x.astype(np.float64) - mean) / (np.sqrt(var) + EPS)
        with torch.no_grad():
            return net(torch.tensor(z, dtype=torch.float32)).numpy()

    return handoff, root, reference, obs, (mean, var)


def session(path):
    import onnxruntime as ort

    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def out_files(out: Path) -> list[Path]:
    return sorted(out.rglob("*")) if out.exists() else []


# ------------------------------------------------------------------------------------------------ export contract
@pytest.mark.req("FR-014-27")
@pytest.mark.parametrize(("policy", "n_obs", "n_act"), [("IL-1", 63, 2), ("IL-2", 46, 4)])
def test_the_export_is_onnx_opset_17_ir_10_and_passes_the_checker(tmp_path: Path, policy, n_obs, n_act) -> None:
    import onnx

    handoff, root, _ref, _obs, _ = make_run(tmp_path, policy=policy)
    res = export_il_policy(handoff, root=root, out_dir=tmp_path / "out")
    assert res.onnx_path.is_file()
    assert res.onnx_path.name == ("il1.onnx" if policy == "IL-1" else "il2.onnx")
    model = onnx.load(str(res.onnx_path))
    onnx.checker.check_model(model, full_check=True)
    assert model.ir_version == 10
    opsets = {o.domain: o.version for o in model.opset_import}
    assert opsets.get("", opsets.get("ai.onnx")) == 17
    inp, out = model.graph.input[0], model.graph.output[0]
    assert (inp.name, out.name) == ("obs", "action") == (res.input_name, res.output_name)
    dims_in = [d.dim_value or d.dim_param for d in inp.type.tensor_type.shape.dim]
    dims_out = [d.dim_value or d.dim_param for d in out.type.tensor_type.shape.dim]
    assert dims_in[1] == n_obs
    assert dims_out[1] == n_act
    assert isinstance(dims_in[0], str)  # a symbolic batch dimension
    assert inp.type.tensor_type.elem_type == onnx.TensorProto.FLOAT


@pytest.mark.req("FR-014-27")
def test_the_normaliser_is_inside_the_graph(tmp_path: Path) -> None:
    import onnx
    from onnx import numpy_helper

    handoff, root, _ref, _obs, (mean, _var) = make_run(tmp_path)
    res = export_il_policy(handoff, root=root, out_dir=tmp_path / "out")
    model = onnx.load(str(res.onnx_path))
    consts = [numpy_helper.to_array(t) for t in model.graph.initializer]
    consts += [
        numpy_helper.to_array(n.attribute[0].t)
        for n in model.graph.node
        if n.op_type == "Constant" and n.attribute[0].t.dims
    ]
    assert any(c.size == 63 and np.allclose(c.ravel(), mean, rtol=1e-6, atol=1e-6) for c in consts), (
        "the mean is not a graph constant"
    )
    ops = {n.op_type for n in model.graph.node}
    assert "Sub" in ops
    assert ops & {"Div", "Mul"}
    # fed with RAW observations the model must equal the normalised reference (checked in the parity test); a raw-input network would not
    obs = np.zeros((1, 63), dtype=np.float32)
    raw = session(res.onnx_path).run(None, {"obs": obs})[0]
    shifted = session(res.onnx_path).run(None, {"obs": obs + mean.astype(np.float32)})[0]
    assert not np.allclose(
        raw, shifted, rtol=1e-3, atol=1e-5
    )  # the output depends on the mean offset: the normaliser acts


@pytest.mark.req("FR-014-27")
@pytest.mark.req("NFR-014-03")
@pytest.mark.parametrize("policy", ["IL-1", "IL-2"])
def test_the_file_is_below_one_megabyte_and_the_report_matches_it(tmp_path: Path, policy) -> None:
    handoff, root, _ref, _obs, _ = make_run(tmp_path, policy=policy)
    res = export_il_policy(handoff, root=root, out_dir=tmp_path / "out")
    size = os.path.getsize(res.onnx_path)
    assert size < 1_000_000
    assert res.bytes == size
    assert res.sha256 == sha(res.onnx_path)


@pytest.mark.req("FR-014-27")
@pytest.mark.req("SC-014-10")
@pytest.mark.parametrize("activation", ["elu", "relu", "tanh"])
@pytest.mark.parametrize("policy", ["IL-1", "IL-2"])
def test_parity_with_pytorch_on_the_golden_observations(tmp_path: Path, policy, activation) -> None:
    handoff, root, ref, obs, _ = make_run(tmp_path, policy=policy, activation=activation, n_golden=256)
    res = export_il_policy(handoff, root=root, out_dir=tmp_path / "out")
    got = session(res.onnx_path).run(None, {"obs": obs})[0]
    want = ref(obs)
    assert got.shape == want.shape
    np.testing.assert_allclose(got, want, rtol=1e-3, atol=1e-5)
    assert float(np.max(np.abs(got - want))) <= 1e-4
    assert res.parity["count"] >= 200
    assert res.parity["count"] == 256
    assert res.parity["ok"] is True
    assert res.parity["max_abs"] <= 1e-4
    assert (res.parity["rtol"], res.parity["atol"]) == (1e-3, 1e-5)


@pytest.mark.req("FR-014-27")
def test_the_model_accepts_any_batch_size(tmp_path: Path) -> None:
    handoff, root, ref, obs, _ = make_run(tmp_path)
    res = export_il_policy(handoff, root=root, out_dir=tmp_path / "out")
    sess = session(res.onnx_path)
    for n in (1, 7, 200):
        y = sess.run(None, {"obs": obs[:n]})[0]
        assert y.shape == (n, 2)
        np.testing.assert_allclose(y, ref(obs[:n]), rtol=1e-3, atol=1e-5)


@pytest.mark.req("FR-014-27")
def test_the_handoff_may_be_given_as_a_json_file(tmp_path: Path) -> None:
    handoff, root, _ref, _obs, _ = make_run(tmp_path)
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(handoff), encoding="utf-8")
    res = export_il_policy(path, root=root, out_dir=tmp_path / "out")
    assert res.onnx_path.is_file()


@pytest.mark.req("FR-014-27")
def test_the_critic_tensors_of_the_checkpoint_are_ignored_and_not_exported(tmp_path: Path) -> None:
    import onnx

    handoff, root, _ref, _obs, _ = make_run(tmp_path)
    res = export_il_policy(handoff, root=root, out_dir=tmp_path / "out")
    model = onnx.load(str(res.onnx_path))
    assert not any("critic" in t.name for t in model.graph.initializer)


# ------------------------------------------------------------------------------------------ hostile handoffs
def rejected(handoff, root, out, *, pointer: str) -> None:
    with pytest.raises(ExportRejected, match=pointer) as info:
        export_il_policy(handoff, root=root, out_dir=out)
    assert isinstance(info.value, ValueError)
    assert out_files(out) == []  # nothing was exported


def corpus() -> list:
    index = json.loads((EX / "index.json").read_text("utf-8"))["examples"]
    out = []
    for e in index:
        if e["schema"] == "il-policy-handoff.schema.json" and not e["valid"]:
            doc = json.loads((EX / e["file"]).read_text("utf-8"))
            out.append(pytest.param(e["pointer"], doc, id=e["file"]))
    return out


@pytest.mark.req("FR-014-28")
@pytest.mark.parametrize(("pointer", "doc"), corpus())
def test_every_hostile_handoff_of_the_spec_is_rejected_and_nothing_is_exported(tmp_path: Path, pointer, doc) -> None:
    named = (
        "|".join(sorted({k for k in doc if k not in {"schema_version", "policy", "task", "run_id", "checkpoint"}}))
        if isinstance(doc, dict)
        else ""
    )
    rejected(doc, tmp_path / "run", tmp_path / "out", pointer=pointer or named or r".+")


MUTATIONS = [
    (["observation_size"], 46, "/observation_size|/normaliser", "IL-1"),  # IL-1 declares the IL-2 size
    (["observation_size"], 64, "/observation_size|/normaliser", "IL-1"),
    (["observation_size"], 63, "/observation_size|/normaliser", "IL-2"),  # IL-2 declares the IL-1 size
    (["action_size"], 4, "/action_size", "IL-1"),
    (["normaliser", "var", 5], 0.0, "/normaliser/var", "IL-1"),
    (["normaliser", "var", 5], -1.0, "/normaliser/var", "IL-1"),
    (["normaliser", "var", 62], -1e-12, "/normaliser/var", "IL-1"),
    (["normaliser", "var", 0], math.nan, "/normaliser/var", "IL-1"),
    (["normaliser", "var", 0], math.inf, "/normaliser/var", "IL-1"),
    (["normaliser", "mean", 3], math.nan, "/normaliser/mean", "IL-1"),
    (["normaliser", "mean", 3], math.inf, "/normaliser/mean", "IL-1"),
    (["normaliser", "mean", 3], -math.inf, "/normaliser/mean", "IL-1"),
    (["normaliser", "mean", 3], "0.1", "/normaliser/mean", "IL-1"),
    (["zz_unknown"], 1, "zz_unknown", "IL-1"),
    (["goldens", "count"], 199, "/goldens", "IL-1"),  # fewer than 200 declared
    (["goldens", "sha256"], "0" * 64, "/goldens", "IL-1"),  # digest differs from the file
    (["goldens", "path"], "../outside.npz", "/goldens", "IL-1"),
    (["checkpoint", "path"], "/etc/model.pt", "/checkpoint", "IL-1"),
    (["checkpoint", "path"], "../model.pt", "/checkpoint", "IL-1"),
    (["actor", "hidden_units"], [128, 128], "/actor", "IL-1"),  # the checkpoint holds 256 x 256 tensors
    (["actor", "activation"], "swish", "/actor", "IL-1"),
]


@pytest.mark.req("FR-014-28")
@pytest.mark.parametrize(
    ("path", "value", "pointer", "policy"),
    MUTATIONS,
    ids=[f"{p[0]}:{'/'.join(map(str, p))}={v}" for p, v, _, p0 in MUTATIONS for p in [(p0, *p)]],
)
def test_hand_built_invalid_handoffs_are_rejected_naming_the_member(
    tmp_path: Path, path, value, pointer, policy
) -> None:
    handoff, root, _ref, _obs, _ = make_run(tmp_path, policy=policy)
    node = handoff
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    rejected(handoff, root, tmp_path / "out", pointer=pointer)


@pytest.mark.req("FR-014-28")
def test_a_normaliser_of_the_wrong_length_is_rejected(tmp_path: Path) -> None:
    handoff, root, _ref, _obs, _ = make_run(tmp_path)
    handoff["normaliser"]["mean"] = handoff["normaliser"]["mean"][:-1]
    rejected(handoff, root, tmp_path / "out", pointer="/normaliser")


@pytest.mark.req("FR-014-28")
def test_a_golden_file_with_too_few_rows_is_rejected(tmp_path: Path) -> None:
    handoff, root, _ref, obs, _ = make_run(tmp_path, n_golden=256)
    npz = root / "goldens" / "observations.npz"
    np.savez(npz, observations=obs[:150])  # the handoff still declares 256 and an old digest
    handoff["goldens"]["sha256"] = sha(npz)
    rejected(handoff, root, tmp_path / "out", pointer="/goldens")


@pytest.mark.req("FR-014-28")
def test_a_golden_file_with_non_finite_values_is_rejected(tmp_path: Path) -> None:
    handoff, root, _ref, obs, _ = make_run(tmp_path, n_golden=256)
    bad = obs.copy()
    bad[7, 3] = np.nan
    npz = root / "goldens" / "observations.npz"
    np.savez(npz, observations=bad)
    handoff["goldens"]["sha256"] = sha(npz)
    rejected(handoff, root, tmp_path / "out", pointer="/goldens")


@pytest.mark.req("FR-014-28")
def test_a_checkpoint_without_the_actor_tensors_is_rejected(tmp_path: Path) -> None:
    import torch

    handoff, root, _ref, _obs, _ = make_run(tmp_path)
    ckpt = root / "checkpoints" / "model_1500.pt"
    torch.save({"model_state_dict": {"critic.0.weight": torch.zeros(1, 63)}, "iter": 1500}, ckpt)
    handoff["checkpoint"]["sha256"] = sha(ckpt)
    rejected(handoff, root, tmp_path / "out", pointer="/checkpoint")


@pytest.mark.req("FR-014-28")
def test_a_checkpoint_that_is_not_a_torch_file_is_rejected(tmp_path: Path) -> None:
    handoff, root, _ref, _obs, _ = make_run(tmp_path)
    ckpt = root / "checkpoints" / "model_1500.pt"
    ckpt.write_bytes(b"this is not a checkpoint \x00\xff")
    handoff["checkpoint"]["sha256"] = sha(ckpt)
    rejected(handoff, root, tmp_path / "out", pointer="/checkpoint")


@pytest.mark.req("FR-014-28")
def test_a_checkpoint_digest_that_does_not_match_the_file_is_rejected(tmp_path: Path) -> None:
    handoff, _root, _ref, _obs, _ = make_run(tmp_path)
    handoff["checkpoint"]["sha256"] = "f" * 64
    with pytest.raises(ExportRejected):  # the stale-input class of T-014-093 subclasses ExportRejected
        export_il_policy(handoff, root=tmp_path / "run", out_dir=tmp_path / "out")
    assert out_files(tmp_path / "out") == []


@pytest.mark.req("FR-014-28")
@pytest.mark.parametrize("bad", [None, [], "handoff", 3, {}])
def test_a_handoff_that_is_not_an_object_or_is_empty_is_rejected(tmp_path: Path, bad) -> None:
    with pytest.raises(ExportRejected):
        export_il_policy(bad, root=tmp_path, out_dir=tmp_path / "out")
    assert out_files(tmp_path / "out") == []


@pytest.mark.req("FR-014-28")
def test_a_handoff_file_that_is_not_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "handoff.json"
    path.write_bytes(b"{not json \xff")
    with pytest.raises(ExportRejected):
        export_il_policy(path, root=tmp_path, out_dir=tmp_path / "out")
    assert out_files(tmp_path / "out") == []


@pytest.mark.req("FR-014-28")
def test_unicode_in_the_run_id_is_rejected_by_the_schema_pattern(tmp_path: Path) -> None:
    handoff, root, _ref, _obs, _ = make_run(tmp_path)
    handoff["run_id"] = "rün-中文"
    rejected(handoff, root, tmp_path / "out", pointer="/run_id")
