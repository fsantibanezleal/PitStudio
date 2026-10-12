# ruff: noqa: E501, PT018
"""T-007-056: policy export against the I/O schema; ONNX Runtime CPU against PyTorch on >= 200 golden states with 100 % masked-argmax agreement and < 2 MB per policy; wrong shapes, non-finite features and pin mismatches stop the run.

Requirements: FR-007-31, FR-007-33, FR-007-44, SC-007-03, NFR-007-03.

Spec: specs/007-haulage-dispatch/spec.md FR-007-31 (an exported policy takes the input layout of `contracts/dispatch-policy-io.schema.json` and returns one logit per target slot: truck features [1, 40, 12], target features [1, 16, 9], truck mask [1, 40], target mask [1, 16]; the DES, in
Python and TypeScript, applies the mask and the argmax, ties going to the lowest target index), FR-007-33 (every target masked: the learned and LP dispatchers raise `NoServiceableLoader`), FR-007-44 (an input tensor with a shape, dtype or layout version other than DC-007-04, a
non-finite feature, or an ONNX file whose SHA-256 differs from its manifest stops the run with `InvalidPolicyInput` or `PolicyPinMismatch`, and no partial KPIs are returned), SC-007-03 (ONNX Runtime CPU fp32 against PyTorch fp32 on >= 200 golden states: rtol 1e-3, atol 1e-5, max abs 1e-4;
100 % masked-argmax agreement; failing variants are reported as rejected), NFR-007-03 (each exported dispatch policy is < 2 MB), DC-007-04 (`contracts/dispatch-policy-io.schema.json`: layout_version 1, opset 17 to 19, ir_version 10, `bytes` < 2,000,000, tie rule `lowest-target-index`).

Oracle: `onnxruntime` and PyTorch called directly by this test on states generated here (the parity function of the code under test is checked against these numbers, not the reverse); `hashlib` for the pin; the JSON schema validator; numpy `argmax` on `-inf`-masked logits
(first maximum = lowest index) for the tie rule; hand-written tie and all-masked cases.

Expected API (module `pitstudio_pipeline.dispatch.export`; errors `InvalidPolicyInput`, `PolicyPinMismatch`, `NoServiceableLoader` in `pitstudio_pipeline.haulage.errors`):
    export_policy(policy: torch.nn.Module, *, out_dir: Path, artefact_id: str, opset: int = 17) -> dict
        `policy` is a `dispatch.policies.MlpPolicy` (id ppo, architecture shared-mlp) or `AttentionPolicy` (id attention, architecture dense-attention); writes `<out_dir>/policy.onnx` (inputs `truck_features` float32 [1, 40, 12], `target_features` float32 [1, 16, 9],
        `truck_mask` bool [1, 40], `target_mask` bool [1, 16]; output `logits` float32 [1, 16]) and `<out_dir>/policy-io.json`; returns the document of `policy-io.json`, valid against the `dispatch-policy-io` schema, with the file's SHA-256, byte size, opset and ir_version 10.
        Any other object raises TypeError; an opset outside 17 to 19 raises ValueError; a file of 2,000,000 bytes or more raises ValueError (nothing is left in `out_dir`).
    parity_report(policy, export_dir: Path, states: Sequence[dict]) -> dict
        `states`: dicts with `truck`, `target`, `truck_mask`, `target_mask` arrays of the layout above (batch 1). Fewer than 200 states raises ValueError; a non-finite feature or a wrong shape or dtype raises InvalidPolicyInput. Returns
        {"n_states", "max_abs_diff", "max_rel_diff", "argmax_agreement" (fraction), "rtol": 1e-3, "atol": 1e-5, "max_abs_limit": 1e-4, "passed": bool, "status": "accepted" | "rejected"}, comparing ONNX Runtime CPU with PyTorch on the unmasked targets.
    masked_argmax(logits, mask) -> int      the lowest index among the maximal logits of the true entries of `mask`; raises NoServiceableLoader when `mask` has no true entry; non-finite logits on a true entry raise InvalidPolicyInput.
    PolicyDispatcher(onnx_path: Path, io_path: Path)
        verifies on construction: the layout version of `io_path` is 1 (InvalidPolicyInput otherwise) and the SHA-256 of the ONNX file equals the manifest's (PolicyPinMismatch otherwise); `.decide(truck, target, truck_mask, target_mask) -> int` validates dtype (float32 / float32 / bool / bool),
        shapes ([1, 40, 12], [1, 16, 9], [1, 40], [1, 16]) and finiteness of every feature, including padded slots (InvalidPolicyInput), runs ONNX Runtime CPU and returns `masked_argmax(logits, target_mask)`; a failed call leaves no state behind.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit as kit
from pitstudio_pipeline.dispatch.export import PolicyDispatcher, export_policy, masked_argmax, parity_report
from pitstudio_pipeline.dispatch.policies import AttentionPolicy, MlpPolicy
from pitstudio_pipeline.haulage.errors import InvalidPolicyInput, NoServiceableLoader, PolicyPinMismatch

IO = kit.schema_validator("dispatch-policy-io")
N_STATES = 200


def make_states(n: int, seed: int) -> list[dict]:
    """Random but well-formed policy inputs: 3 to 40 real trucks (one deciding), 2 to 16 loaders/dumps of which a random non-empty subset is serviceable and reachable."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        n_t, n_g = int(rng.integers(3, 41)), int(rng.integers(2, 17))
        truck = np.zeros((1, 40, 12), np.float32)
        for i in range(n_t):
            truck[0, i, int(rng.integers(0, 7))] = 1.0
            truck[0, i, 7] = rng.uniform(0.6, 1.2)
            truck[0, i, 8] = rng.uniform(0.0, 0.3)
            truck[0, i, 9] = rng.uniform(0.0, 0.4)
            truck[0, i, 11] = 1.0
        truck[0, int(rng.integers(0, n_t)), 10] = 1.0
        target = np.zeros((1, 16, 9), np.float32)
        for j in range(n_g):
            target[0, j, 0] = float(rng.random() < 0.2)
            target[0, j, 1] = rng.uniform(0, 0.4)
            target[0, j, 2] = rng.uniform(0, 0.4)
            target[0, j, 3:6] = rng.uniform(0, 0.4, 3)
            target[0, j, 6] = rng.uniform(0.0, 0.4)
            target[0, j, 7] = rng.integers(1, 5) / 4.0
            target[0, j, 8] = 1.0
        tmask = np.zeros((1, 40), bool)
        tmask[0, :n_t] = True
        gmask = np.zeros((1, 16), bool)
        gmask[0, :n_g] = rng.random(n_g) < 0.7
        if not gmask.any():
            gmask[0, int(rng.integers(0, n_g))] = True
        target[0, :, 8] = gmask[0].astype(np.float32)
        target[0, ~gmask[0], 6] = 0.0  # the ETA of a masked target is 0
        out.append({"truck": truck, "target": target, "truck_mask": tmask, "target_mask": gmask})
    return out


def torch_logits(policy, st):
    with torch.no_grad():
        policy.eval()
        lg, _ = policy(
            torch.from_numpy(st["truck"]),
            torch.from_numpy(st["target"]),
            torch.from_numpy(st["truck_mask"]),
            torch.from_numpy(st["target_mask"]),
        )
    return lg.numpy()[0]


def ort_session(path):
    import onnxruntime as ort

    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def ort_logits(sess, st):
    return sess.run(
        ["logits"],
        {
            "truck_features": st["truck"],
            "target_features": st["target"],
            "truck_mask": st["truck_mask"],
            "target_mask": st["target_mask"],
        },
    )[0][0]


POLICIES = {"ppo": lambda: MlpPolicy(seed=3), "attention": lambda: AttentionPolicy(seed=4)}
ARCH = {"ppo": "shared-mlp", "attention": "dense-attention"}


@pytest.fixture(scope="module")
def states():
    return make_states(N_STATES, seed=2026)


@pytest.fixture(scope="module", params=["ppo", "attention"])
def exported(request, tmp_path_factory):
    pid = request.param
    policy = POLICIES[pid]()
    out = tmp_path_factory.mktemp(f"export-{pid}")
    doc = export_policy(policy, out_dir=out, artefact_id=f"a1-dispatch-{pid}-onnx")
    return pid, policy, out, doc


# ---------------------------------------------------------------------------------------------------------------------
# the exported files and the contract
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-31")
def test_the_export_writes_the_two_files_and_the_document_is_valid_against_the_policy_io_schema(exported):
    pid, _, out, doc = exported
    assert (out / "policy.onnx").is_file() and (out / "policy-io.json").is_file()
    assert not list(IO.iter_errors(doc)), [e.message for e in IO.iter_errors(doc)][:3]
    assert json.loads((out / "policy-io.json").read_text(encoding="utf-8")) == doc
    assert (
        doc["policy"]["id"] == pid
        and doc["policy"]["architecture"] == ARCH[pid]
        and doc["policy"]["artefact_id"] == f"a1-dispatch-{pid}-onnx"
    )
    assert (
        doc["layout_version"] == 1 and doc["time_unit"] == "h" and doc["decision"]["tie_rule"] == "lowest-target-index"
    )
    assert [doc["inputs"][k]["shape"] for k in ("truck_features", "target_features", "truck_mask", "target_mask")] == [
        [1, 40, 12],
        [1, 16, 9],
        [1, 40],
        [1, 16],
    ]
    assert doc["output"]["shape"] == [1, 16] and doc["output"]["name"] == "logits"


@pytest.mark.req("FR-007-44")
def test_the_manifest_pins_the_onnx_file_by_sha256_and_size(exported):
    _, _, out, doc = exported
    raw = (out / "policy.onnx").read_bytes()
    assert doc["policy"]["onnx"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert doc["policy"]["onnx"]["bytes"] == len(raw)
    assert doc["policy"]["onnx"]["ir_version"] == 10 and 17 <= doc["policy"]["onnx"]["opset"] <= 19


@pytest.mark.req("NFR-007-03")
def test_each_exported_policy_is_smaller_than_two_megabytes(exported):
    _, _, out, doc = exported
    assert 0 < (out / "policy.onnx").stat().st_size < 2_000_000 and doc["policy"]["onnx"]["bytes"] < 2_000_000


@pytest.mark.req("FR-007-31")
def test_the_onnx_graph_has_exactly_the_documented_inputs_and_output(exported):
    _, _, out, _ = exported
    import onnx

    m = onnx.load(str(out / "policy.onnx"))
    types = {1: "float32", 9: "bool"}
    ins = {
        i.name: (types[i.type.tensor_type.elem_type], [d.dim_value for d in i.type.tensor_type.shape.dim])
        for i in m.graph.input
    }
    assert ins == {
        "truck_features": ("float32", [1, 40, 12]),
        "target_features": ("float32", [1, 16, 9]),
        "truck_mask": ("bool", [1, 40]),
        "target_mask": ("bool", [1, 16]),
    }
    assert [o.name for o in m.graph.output] == ["logits"] and m.ir_version == 10


# ---------------------------------------------------------------------------------------------------------------------
# SC-007-03: parity on golden states against a direct onnxruntime / torch comparison
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("SC-007-03")
def test_onnx_runtime_cpu_agrees_with_pytorch_on_200_states_within_the_tolerances_and_in_every_masked_argmax(
    exported, states
):
    _, policy, out, _ = exported
    sess = ort_session(out / "policy.onnx")
    max_abs = 0.0
    for st in states:
        ref, got, m = torch_logits(policy, st), ort_logits(sess, st), st["target_mask"][0]
        assert got.shape == (16,) and got.dtype == np.float32
        np.testing.assert_allclose(got[m], ref[m], rtol=1e-3, atol=1e-5)
        max_abs = max(max_abs, float(np.max(np.abs(got[m] - ref[m]))))
        a_ref = int(np.argmax(np.where(m, ref, -np.inf)))
        a_got = int(np.argmax(np.where(m, got, -np.inf)))
        assert a_ref == a_got  # 100 % masked-argmax agreement
    assert max_abs <= 1e-4


@pytest.mark.req("SC-007-03")
def test_the_parity_report_reproduces_the_direct_comparison_and_accepts_the_policy(exported, states):
    _, policy, out, _ = exported
    rep = parity_report(policy, out, states)
    sess = ort_session(out / "policy.onnx")
    direct = max(
        float(np.max(np.abs((ort_logits(sess, s) - torch_logits(policy, s))[s["target_mask"][0]]))) for s in states
    )
    assert (
        rep["n_states"] == N_STATES
        and rep["argmax_agreement"] == 1.0
        and rep["passed"] is True
        and rep["status"] == "accepted"
    )
    assert rep["max_abs_diff"] == pytest.approx(direct, abs=1e-7) and rep["max_abs_diff"] <= 1e-4
    assert (rep["rtol"], rep["atol"], rep["max_abs_limit"]) == (1e-3, 1e-5, 1e-4)
    json.dumps(rep)


@pytest.mark.req("SC-007-03")
def test_a_different_policy_is_reported_as_rejected_not_accepted(exported, states):
    pid, _, out, _ = exported
    other = (
        MlpPolicy(seed=99) if pid == "ppo" else AttentionPolicy(seed=98)
    )  # same architecture, other weights: the file no longer matches this policy
    rep = parity_report(other, out, states)
    assert rep["passed"] is False and rep["status"] == "rejected" and rep["max_abs_diff"] > 1e-4


@pytest.mark.req("SC-007-03")
@pytest.mark.parametrize("n", [0, 1, 199])
def test_fewer_than_200_golden_states_are_refused(exported, states, n):
    _, policy, out, _ = exported
    with pytest.raises(ValueError, match="200"):
        parity_report(policy, out, states[:n])


@pytest.mark.req("FR-007-44")
@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "shape", "dtype", "mask-dtype", "mask-shape"])
def test_a_malformed_golden_state_stops_the_parity_run(exported, states, bad):
    _, policy, out, _ = exported
    s = copy.deepcopy(states)
    st = s[17]
    if bad in {"nan", "inf", "-inf"}:
        st["truck"][0, 39, 4] = {"nan": np.nan, "inf": np.inf, "-inf": -np.inf}[
            bad
        ]  # a padded slot: every feature must be finite
    elif bad == "shape":
        st["target"] = st["target"][:, :15, :]
    elif bad == "dtype":
        st["truck"] = st["truck"].astype(np.float64)
    elif bad == "mask-dtype":
        st["target_mask"] = st["target_mask"].astype(np.uint8)
    else:
        st["truck_mask"] = st["truck_mask"][:, :39]
    with pytest.raises(InvalidPolicyInput):
        parity_report(policy, out, s)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-31 / FR-007-33: the decision rule
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-31")
@pytest.mark.parametrize(
    ("logits", "mask", "want"),
    [
        ([1.0, 3.0, 3.0, 2.0], [True, True, True, True], 1),  # a tie goes to the lowest index
        ([5.0, 3.0, 3.0, 2.0], [False, True, True, True], 1),  # a masked maximum is ignored
        ([0.0, 0.0, 0.0, 0.0], [False, False, True, True], 2),  # all equal: the lowest serviceable index
        ([-9.0, -8.0, -7.0], [True, True, True], 2),  # negative logits
        ([1e30, -1e30, 0.0], [False, True, True], 2),
        ([2.0, 2.0 + 1e-6, 2.0], [True, True, True], 1),  # a 1e-6 margin still decides
    ],
)
def test_masked_argmax_ties_go_to_the_lowest_target_index(logits, mask, want):
    assert masked_argmax(np.array(logits, dtype=np.float32), np.array(mask)) == want


@pytest.mark.req("FR-007-33")
def test_every_target_masked_raises_no_serviceable_loader():
    with pytest.raises(NoServiceableLoader):
        masked_argmax(np.zeros(16, np.float32), np.zeros(16, bool))
    assert issubclass(NoServiceableLoader, RuntimeError)


@pytest.mark.req("FR-007-44")
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_a_non_finite_logit_on_a_serviceable_target_is_an_input_error(bad):
    lg = np.zeros(4, np.float32)
    lg[2] = bad
    with pytest.raises(InvalidPolicyInput):
        masked_argmax(lg, np.array([True, True, True, False]))
    lg2 = np.zeros(4, np.float32)
    lg2[3] = bad
    assert masked_argmax(lg2, np.array([True, True, True, False])) == 0  # on a masked slot it is irrelevant


@pytest.mark.req("FR-007-31")
def test_the_dispatcher_returns_the_masked_argmax_of_the_onnx_logits(exported, states):
    _, _, out, _ = exported
    d = PolicyDispatcher(out / "policy.onnx", out / "policy-io.json")
    sess = ort_session(out / "policy.onnx")
    for st in states[:50]:
        want = masked_argmax(ort_logits(sess, st), st["target_mask"][0])
        got = d.decide(st["truck"], st["target"], st["truck_mask"], st["target_mask"])
        assert got == want and st["target_mask"][0][got]


@pytest.mark.req("FR-007-33")
def test_the_dispatcher_raises_no_serviceable_loader_when_every_target_is_masked(exported, states):
    _, _, out, _ = exported
    d = PolicyDispatcher(out / "policy.onnx", out / "policy-io.json")
    st = states[0]
    with pytest.raises(NoServiceableLoader):
        d.decide(st["truck"], st["target"], st["truck_mask"], np.zeros((1, 16), bool))


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-44: hostile inputs and pins
# ---------------------------------------------------------------------------------------------------------------------
def hostile_variants(st):
    t, g, tm, gm = (st[k] for k in ("truck", "target", "truck_mask", "target_mask"))
    nan_t = t.copy()
    nan_t[0, 5, 3] = np.nan
    inf_g = g.copy()
    inf_g[0, 15, 2] = np.inf  # padded target slot
    ninf_t = t.copy()
    ninf_t[0, 39, 11] = -np.inf  # padded truck slot
    return {
        "truck-shape-39": (t[:, :39], g, tm[:, :39], gm),
        "truck-batch-2": (np.concatenate([t, t]), g, np.concatenate([tm, tm]), gm),
        "truck-rank-2": (t[0], g, tm, gm),
        "truck-feature-11": (t[:, :, :11], g, tm, gm),
        "target-shape-17": (t, np.concatenate([g, g[:, :1]], axis=1), tm, np.concatenate([gm, gm[:, :1]], axis=1)),
        "truck-float64": (t.astype(np.float64), g, tm, gm),
        "target-float16": (t, g.astype(np.float16), tm, gm),
        "truck-int32": (t.astype(np.int32), g, tm, gm),
        "mask-uint8": (t, g, tm.astype(np.uint8), gm),
        "mask-float": (t, g, tm, gm.astype(np.float32)),
        "nan-truck": (nan_t, g, tm, gm),
        "inf-padded-target": (t, inf_g, tm, gm),
        "neg-inf-padded-truck": (ninf_t, g, tm, gm),
        "lists": (t.tolist(), g, tm, gm),
        "none": (None, g, tm, gm),
        "empty": (np.zeros((1, 0, 12), np.float32), g, np.zeros((1, 0), bool), gm),
    }


@pytest.mark.req("FR-007-44")
def test_every_hostile_input_raises_invalid_policy_input_and_a_valid_call_still_works_afterwards(exported, states):
    _, _, out, _ = exported
    d = PolicyDispatcher(out / "policy.onnx", out / "policy-io.json")
    st = states[3]
    expected = d.decide(st["truck"], st["target"], st["truck_mask"], st["target_mask"])
    for name, args in hostile_variants(st).items():
        with pytest.raises(InvalidPolicyInput):
            d.decide(*args)
        assert d.decide(st["truck"], st["target"], st["truck_mask"], st["target_mask"]) == expected, (
            name
        )  # no partial state, no partial result


@pytest.mark.req("FR-007-44")
def test_a_tampered_onnx_file_is_a_pin_mismatch(exported, tmp_path):
    _, _, out, _ = exported
    raw = bytearray((out / "policy.onnx").read_bytes())
    raw[len(raw) // 2] ^= 0x01
    (tmp_path / "policy.onnx").write_bytes(bytes(raw))
    (tmp_path / "policy-io.json").write_bytes((out / "policy-io.json").read_bytes())
    with pytest.raises(PolicyPinMismatch):
        PolicyDispatcher(tmp_path / "policy.onnx", tmp_path / "policy-io.json")


@pytest.mark.req("FR-007-44")
@pytest.mark.parametrize("digest", ["0" * 64, "f" * 64, "", "xyz", None])
def test_a_manifest_with_another_digest_is_a_pin_mismatch_or_an_input_error(exported, tmp_path, digest):
    _, _, out, doc = exported
    d = copy.deepcopy(doc)
    d["policy"]["onnx"]["sha256"] = digest
    (tmp_path / "policy.onnx").write_bytes((out / "policy.onnx").read_bytes())
    (tmp_path / "policy-io.json").write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises((PolicyPinMismatch, InvalidPolicyInput)):
        PolicyDispatcher(tmp_path / "policy.onnx", tmp_path / "policy-io.json")


@pytest.mark.req("FR-007-44")
@pytest.mark.parametrize("version", [0, 2, 99, "1", None, True])
def test_an_unknown_layout_version_is_refused(exported, tmp_path, version):
    _, _, out, doc = exported
    d = copy.deepcopy(doc)
    d["layout_version"] = version
    (tmp_path / "policy.onnx").write_bytes((out / "policy.onnx").read_bytes())
    (tmp_path / "policy-io.json").write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(InvalidPolicyInput):
        PolicyDispatcher(tmp_path / "policy.onnx", tmp_path / "policy-io.json")


@pytest.mark.req("FR-007-44")
def test_missing_or_malformed_files_are_errors_not_crashes(exported, tmp_path):
    _, _, out, _ = exported
    with pytest.raises(FileNotFoundError):
        PolicyDispatcher(tmp_path / "nope.onnx", out / "policy-io.json")
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises((InvalidPolicyInput, ValueError)):
        PolicyDispatcher(out / "policy.onnx", tmp_path / "bad.json")
    (tmp_path / "empty.json").write_text("", encoding="utf-8")
    with pytest.raises((InvalidPolicyInput, ValueError)):
        PolicyDispatcher(out / "policy.onnx", tmp_path / "empty.json")


# ---------------------------------------------------------------------------------------------------------------------
# the export itself, hostile
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-31")
@pytest.mark.parametrize("obj", [None, "policy", 3, torch.nn.Linear(2, 2), object()])
def test_exporting_anything_but_a_dispatch_policy_is_a_type_error(tmp_path, obj):
    with pytest.raises(TypeError):
        export_policy(obj, out_dir=tmp_path, artefact_id="a1-dispatch-ppo-onnx")
    assert not list(tmp_path.iterdir())


@pytest.mark.req("FR-007-31")
@pytest.mark.parametrize("opset", [16, 20, 0, -1, 17.5, None])
def test_an_opset_outside_17_to_19_is_rejected_and_leaves_nothing_behind(tmp_path, opset):
    with pytest.raises((ValueError, TypeError)):
        export_policy(MlpPolicy(seed=1), out_dir=tmp_path, artefact_id="a1-dispatch-ppo-onnx", opset=opset)
    assert not list(tmp_path.iterdir())


@pytest.mark.req("FR-007-31")
@pytest.mark.parametrize("artefact_id", ["", "A1", "a b", "../x", "x" * 97, "é"])
def test_an_artefact_id_outside_the_schema_pattern_is_rejected(tmp_path, artefact_id):
    with pytest.raises(ValueError):  # noqa: PT011
        export_policy(MlpPolicy(seed=1), out_dir=tmp_path, artefact_id=artefact_id)


@pytest.mark.req("NFR-007-03")
def test_a_policy_whose_file_would_reach_two_megabytes_is_refused_and_leaves_nothing_behind(tmp_path):
    big = MlpPolicy(hidden=1024, seed=1)  # about 4 MB of fp32 weights in the score network
    with pytest.raises(ValueError, match="2"):
        export_policy(big, out_dir=tmp_path, artefact_id="a1-dispatch-ppo-onnx")
    assert not list(tmp_path.iterdir())


@pytest.mark.req("SC-007-03")
def test_exports_of_two_different_weight_sets_have_different_pins(tmp_path):
    a = export_policy(MlpPolicy(seed=1), out_dir=tmp_path / "a", artefact_id="a1-dispatch-ppo-onnx")
    b = export_policy(MlpPolicy(seed=2), out_dir=tmp_path / "b", artefact_id="a1-dispatch-ppo-onnx")
    assert a["policy"]["onnx"]["sha256"] != b["policy"]["onnx"]["sha256"]
