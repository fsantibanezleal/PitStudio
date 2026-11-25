# ruff: noqa: E501, PT018
"""T-007-052: the M4 MLP and M5 attention policies: exact zero probability on masked targets, permutation, padding and size invariance.

Requirements: FR-007-24, P-007-15, P-007-16, NFR-007-03 (parameter budget).

Spec: specs/007-haulage-dispatch/spec.md FR-007-24 (the policies mask every target that is not serviceable or not reachable and give masked targets a probability of exactly 0), P-007-15 (M5 attention: (i) permuting non-deciding
truck tokens leaves the action distribution unchanged; (ii) permuting target tokens permutes the logits the same way; (iii) appending masked padding tokens leaves the outputs unchanged; (iv) the same weights accept 1 to 40 trucks;
float32, max abs 1e-6), P-007-16 (M4 MLP: permuting target slots permutes the logits; permuting non-deciding trucks leaves them unchanged (pooled fleet features); masked targets have probability 0 exactly), plan.md ("M4: a
parameter-shared pair-scoring MLP with mean-pooled fleet features; M5: dense masked attention (MatMul and Softmax only) and a pointer head") and NFR-007-03 (each exported policy < 2 MB; float32 parameters).

Oracle: the invariance and equivariance relations themselves (the unpermuted forward pass is the reference of the permuted one); exact comparison of the probabilities with 0.0; the softmax sum rule; parameter counts times 4 bytes
against the 2 MB budget. No expected value is produced by training.

Expected API (module `pitstudio_pipeline.dispatch.policies`):
    MlpPolicy(*, hidden: int = 64, seed: int = 0)       M4
    AttentionPolicy(*, d_model: int = 32, heads: int = 2, layers: int = 2, seed: int = 0)       M5
    both are torch.nn.Module; `forward(truck, target, truck_mask, target_mask) -> (logits, value)`:
        truck float32 [B, Tn, 12] and target float32 [B, Tm, 9] with any Tn in 1..40 and Tm in 1..16 (the token layouts of test_t_007_050), truck_mask bool [B, Tn], target_mask bool [B, Tm];
        logits float32 [B, Tm] with masked slots set to -1e9 (finite), value float32 [B]. The deciding truck is the token whose feature 10 is 1. A row without a valid truck is not allowed (ValueError).
    probs(truck, target, truck_mask, target_mask) -> float32 [B, Tm]   softmax of the logits over the unmasked targets; masked entries are exactly 0.0; a row whose targets are all masked is all zeros (no NaN).
    parameter_count(policy) -> int
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit  # noqa: F401
from pitstudio_pipeline.dispatch.policies import AttentionPolicy, MlpPolicy, parameter_count

SETTINGS = settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)
TOL = 1e-6
MAKERS = {"mlp": lambda seed=0: MlpPolicy(seed=seed), "attention": lambda seed=0: AttentionPolicy(seed=seed)}


def probs_of(policy, *state):
    from pitstudio_pipeline.dispatch.policies import probs

    return probs(policy, *state) if False else policy.probs(*state)


def state(seed: int, *, b=2, n_trucks=7, n_targets=5, pad_trucks=0, pad_targets=0):
    """A random observation: `n` valid trucks (one deciding) and `m` valid targets (at least one), then masked padding tokens with garbage content."""
    g = torch.Generator().manual_seed(seed)
    tn, tm = n_trucks + pad_trucks, n_targets + pad_targets
    truck = torch.randn(b, tn, 12, generator=g)
    target = torch.randn(b, tm, 9, generator=g)
    truck_mask = torch.zeros(b, tn, dtype=torch.bool)
    target_mask = torch.zeros(b, tm, dtype=torch.bool)
    truck_mask[:, :n_trucks] = True
    target_mask[:, :n_targets] = True
    for i in range(b):  # some valid targets are masked (not serviceable / not reachable), at least one stays valid
        drop = torch.randperm(n_targets, generator=g)[: torch.randint(0, n_targets, (1,), generator=g).item()]
        target_mask[i, drop] = False
        target_mask[i, torch.randint(0, n_targets, (1,), generator=g).item()] = True
    truck[..., 10] = 0.0
    for i in range(b):
        truck[i, torch.randint(0, n_trucks, (1,), generator=g).item(), 10] = 1.0
    truck[..., 11] = truck_mask.float()
    return truck, target, truck_mask, target_mask


def permute_trucks_keeping_the_decider(truck, mask, g):
    out = truck.clone()
    for i in range(truck.shape[0]):
        valid = mask[i].nonzero().flatten()
        others = [int(j) for j in valid if truck[i, j, 10] == 0.0]
        perm = torch.randperm(len(others), generator=g).tolist()
        for dst, src in zip(others, [others[p] for p in perm], strict=True):
            out[i, dst] = truck[i, src]
    return out


# ---------------------------------------------------------------------------------------------------------------------
# exact zero probability (FR-007-24)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-24")
@pytest.mark.parametrize("kind", ["mlp", "attention"])
@SETTINGS
@given(st.integers(0, 10**6), st.integers(1, 40), st.integers(1, 16))
def test_masked_targets_have_probability_exactly_zero_and_the_rest_sums_to_one(kind, seed, n_trucks, n_targets):
    p = MAKERS[kind]()
    truck, target, tmask, gmask = state(seed, n_trucks=n_trucks, n_targets=n_targets)
    logits, value = p(truck, target, tmask, gmask)
    pr = p.probs(truck, target, tmask, gmask)
    assert (
        logits.shape == (2, n_targets)
        and value.shape == (2,)
        and logits.dtype == torch.float32
        and pr.dtype == torch.float32
    )
    assert torch.equal(pr[~gmask], torch.zeros_like(pr[~gmask]))  # exactly 0.0, not merely small
    assert torch.isfinite(logits).all() and torch.isfinite(value).all() and (logits[~gmask] <= -1e8).all()
    assert torch.allclose(pr.sum(dim=1), torch.ones(2), atol=1e-6) and (pr[gmask] > 0).all()


@pytest.mark.req("FR-007-24")
@pytest.mark.parametrize("kind", ["mlp", "attention"])
def test_a_row_with_every_target_masked_gives_zeros_without_nan(kind):
    p = MAKERS[kind]()
    truck, target, tmask, gmask = state(3, b=3)
    gmask[1] = False  # the middle copy has no serviceable target
    pr = p.probs(truck, target, tmask, gmask)
    assert torch.equal(pr[1], torch.zeros(5)) and not torch.isnan(pr).any()
    assert torch.allclose(pr[0].sum(), torch.tensor(1.0), atol=1e-6) and torch.allclose(
        pr[2].sum(), torch.tensor(1.0), atol=1e-6
    )


@pytest.mark.req("FR-007-24")
@pytest.mark.parametrize("kind", ["mlp", "attention"])
def test_masked_target_content_cannot_change_any_output(kind):
    p = MAKERS[kind]()
    truck, target, tmask, gmask = state(5)
    base, v0 = p(truck, target, tmask, gmask)
    poisoned = target.clone()
    poisoned[~gmask] = torch.randn_like(poisoned[~gmask]) * 100.0  # arbitrary content in masked slots
    out, v1 = p(truck, poisoned, tmask, gmask)
    assert torch.allclose(out[gmask], base[gmask], atol=TOL) and torch.allclose(v0, v1, atol=TOL)


@pytest.mark.req("FR-007-24")
@pytest.mark.parametrize("kind", ["mlp", "attention"])
def test_a_row_without_a_valid_truck_is_rejected(kind):
    p = MAKERS[kind]()
    truck, target, tmask, gmask = state(7)
    tmask[0] = False
    with pytest.raises(ValueError):  # noqa: PT011
        p(truck, target, tmask, gmask)


# ---------------------------------------------------------------------------------------------------------------------
# P-007-16 (M4) and P-007-15 (M5)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("P-007-16")
@pytest.mark.req("P-007-15")
@pytest.mark.parametrize("kind", ["mlp", "attention"])
@SETTINGS
@given(st.integers(0, 10**6), st.integers(2, 12), st.integers(2, 9))
def test_permuting_target_slots_permutes_the_logits_the_same_way(kind, seed, n_trucks, n_targets):
    p = MAKERS[kind]()
    truck, target, tmask, gmask = state(seed, n_trucks=n_trucks, n_targets=n_targets)
    perm = torch.randperm(n_targets, generator=torch.Generator().manual_seed(seed))
    base, _ = p(truck, target, tmask, gmask)
    out, _ = p(truck, target[:, perm], tmask, gmask[:, perm])
    assert torch.allclose(out, base[:, perm], atol=TOL)
    assert torch.allclose(
        p.probs(truck, target[:, perm], tmask, gmask[:, perm]), p.probs(truck, target, tmask, gmask)[:, perm], atol=TOL
    )


@pytest.mark.req("P-007-16")
@pytest.mark.req("P-007-15")
@pytest.mark.parametrize("kind", ["mlp", "attention"])
@SETTINGS
@given(st.integers(0, 10**6), st.integers(3, 20), st.integers(2, 8))
def test_permuting_the_non_deciding_trucks_leaves_the_action_distribution_unchanged(kind, seed, n_trucks, n_targets):
    p = MAKERS[kind]()
    truck, target, tmask, gmask = state(seed, n_trucks=n_trucks, n_targets=n_targets)
    shuffled = permute_trucks_keeping_the_decider(truck, tmask, torch.Generator().manual_seed(seed))
    a, va = p(truck, target, tmask, gmask)
    b, vb = p(shuffled, target, tmask, gmask)
    assert torch.allclose(a, b, atol=TOL) and torch.allclose(va, vb, atol=TOL)
    assert torch.allclose(p.probs(truck, target, tmask, gmask), p.probs(shuffled, target, tmask, gmask), atol=TOL)


@pytest.mark.req("P-007-15")
@pytest.mark.parametrize("kind", ["mlp", "attention"])
@SETTINGS
@given(st.integers(0, 10**6), st.integers(1, 20), st.integers(1, 8), st.integers(1, 20), st.integers(0, 8))
def test_appending_masked_padding_tokens_leaves_the_outputs_unchanged(
    kind, seed, n_trucks, n_targets, pad_trucks, pad_targets
):
    p = MAKERS[kind]()
    small = state(seed, n_trucks=n_trucks, n_targets=n_targets)
    g = torch.Generator().manual_seed(seed + 1)
    truck = torch.cat(
        [small[0], torch.randn(2, pad_trucks, 12, generator=g) * 5.0], dim=1
    )  # garbage in the padding tokens
    target = torch.cat([small[1], torch.randn(2, pad_targets, 9, generator=g) * 5.0], dim=1)
    tmask = torch.cat([small[2], torch.zeros(2, pad_trucks, dtype=torch.bool)], dim=1)
    gmask = torch.cat([small[3], torch.zeros(2, pad_targets, dtype=torch.bool)], dim=1)
    a, va = p(*small)
    b, vb = p(truck, target, tmask, gmask)
    assert torch.allclose(b[:, :n_targets], a, atol=TOL) and torch.allclose(va, vb, atol=TOL)
    assert torch.equal(p.probs(truck, target, tmask, gmask)[:, n_targets:], torch.zeros(2, pad_targets))


@pytest.mark.req("P-007-15")
@pytest.mark.parametrize("kind", ["mlp", "attention"])
@pytest.mark.parametrize("n", [1, 2, 7, 16, 33, 40])
def test_the_same_weights_accept_one_to_forty_trucks(kind, n):
    p = MAKERS[kind]()
    truck, target, tmask, gmask = state(n, n_trucks=n, n_targets=4)
    out, value = p(truck, target, tmask, gmask)
    assert out.shape == (2, 4) and torch.isfinite(out).all() and torch.isfinite(value).all()


@pytest.mark.req("P-007-15")
def test_the_attention_policy_has_no_hidden_dependence_on_the_batch():
    p = MAKERS["attention"]()
    truck, target, tmask, gmask = state(11, b=4)
    full, vfull = p(truck, target, tmask, gmask)
    for i in range(4):
        one, vone = p(truck[i : i + 1], target[i : i + 1], tmask[i : i + 1], gmask[i : i + 1])
        assert torch.allclose(one[0], full[i], atol=TOL) and torch.allclose(vone[0], vfull[i], atol=TOL)


# ---------------------------------------------------------------------------------------------------------------------
# construction, determinism, budget
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-24")
@pytest.mark.parametrize("kind", ["mlp", "attention"])
def test_the_same_seed_gives_the_same_weights_and_another_seed_differs(kind):
    a, b, c = MAKERS[kind](1), MAKERS[kind](1), MAKERS[kind](2)
    st_ = state(9)
    assert torch.equal(a(*st_)[0], b(*st_)[0]) and not torch.equal(a(*st_)[0], c(*st_)[0])


@pytest.mark.req("FR-007-24")
@pytest.mark.parametrize("kind", ["mlp", "attention"])
def test_each_policy_fits_the_two_megabyte_budget_in_float32(kind):
    p = MAKERS[kind]()
    assert 0 < parameter_count(p) * 4 < 2_000_000
    assert all(x.dtype == torch.float32 for x in p.parameters())


@pytest.mark.req("FR-007-24")
@pytest.mark.parametrize("kind", ["mlp", "attention"])
def test_the_logits_depend_on_the_state_and_the_value_head_is_trainable(kind):
    p = MAKERS[kind]()
    truck, target, tmask, gmask = state(21)
    logits, value = p(truck, target, tmask, gmask)
    (logits[gmask].sum() + value.sum()).backward()
    assert all(x.grad is not None for x in p.parameters() if x.requires_grad)
    other = target.clone()
    other[:, :, 6] += 1.0  # a different ETA of the deciding truck changes the scores
    assert not torch.allclose(p(truck, other, tmask, gmask)[0][gmask], logits[gmask].detach(), atol=1e-6)
