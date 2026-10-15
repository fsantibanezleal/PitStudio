"""T-017-012: GBM and MLP training and the selection rule (pipeline).

Requirements: FR-017-03, FR-017-04.

Spec: specs/017-planning-survey/spec.md
- FR-017-03: two families are trained on the training sweeps with the mean squared error of standardised outputs:
  gradient-boosted trees (scikit-learn `HistGradientBoostingRegressor`, one per output) and an MLP (3 hidden layers of
  64 units, SiLU, standardised and log-transformed positive inputs, multi-output), with hyper-parameters chosen on the
  validation sweeps only;
- FR-017-04: the selection rule picks the family with the higher minimum over outputs of the validation R^2; when
  the two differ by < 0.005 it picks the one with the smaller ONNX file; trees are eligible only if their ONNX
  conversion is available in the lock, is <= 10^6 bytes and passes FR-017-07 on ONNX Runtime CPU and WASM; the
  held-out sweeps are touched once, after selection.
plan.md test strategy rows FR-017-03 / FR-017-04: selection decisions on fixture validation scores (including the tie
and the ineligible-tree cases).

Oracles:
- the selection decisions are hand-built truth tables (scores and file sizes written in the test; the 0.005 band is
  exercised with differences of 0.0039 and 0.0078, away from the float boundary);
- scikit-learn `HistGradientBoostingRegressor` called directly as the reference for the per-output trees and for the
  hyper-parameter choice (deterministic: no early stopping, no subsampling) and `numpy` for the standardised mean
  squared error and the log + z-score input transform (hand arithmetic on a four-row array);
- the architecture read back from the torch module (layer types and widths);
- a noise-free linear target: both families must fit it (validation R^2 >= 0.85 trees, >= 0.9 MLP).

Expected public API (`pipeline/` environment, module `pitstudio_pipeline.mine_to_mill.train` and `.select`):
train:
    standardised_mse(pred, target, mean, std) -> float       # mean over rows and outputs of ((pred-target)/std)^2
    fit_input_transform(X: np.ndarray, positive_columns: Sequence[int]) -> InputTransform
        .apply(X) = log on the positive columns, then (x - mean) / std per column with the statistics of the TRAINING
        matrix (population std, ddof=0); ValueError when a positive column holds a value <= 0 or a non-finite value.
    train_gbm(X_train, Y_train, X_val, Y_val, *, grid: Sequence[dict]) -> GbmModel
        one HistGradientBoostingRegressor per output (`.models`), fitted with each parameter dict of `grid`; the chosen
        dict (`.params`) minimises the standardised validation MSE; `.predict(X) -> (n, n_outputs)`.
    build_mlp(n_inputs: int, n_outputs: int) -> torch.nn.Module     # Linear(n_in,64) SiLU Linear(64,64) SiLU
                                                                    # Linear(64,64) SiLU Linear(64,n_out)
    train_mlp(X_train, Y_train, X_val, Y_val, *, positive_columns, epochs: int, seed: int) -> MlpModel
        `.predict(X) -> (n, n_outputs)` in the original output units (inputs transformed, outputs standardised inside).
select:
    r2_min(r2_per_output: Sequence[float]) -> float          # the minimum over outputs
    select_family(val_r2: Mapping[str, Sequence[float]], onnx_bytes: Mapping[str, int], *,
                  trees: Mapping) -> Selection
        keys "gbm" and "mlp"; `trees` = {"convertible": bool, "parity_cpu": bool, "parity_wasm": bool}; Selection:
        `.family` ("gbm" | "mlp") and `.reason` (non-empty str; contains "ineligible" when the trees were excluded).
    class ProtocolLog: .record_selection(selection) ; .touch_held_out()
        touch_held_out raises HeldOutProtocolError before any selection was recorded and on a second touch.
"""

from __future__ import annotations

import numpy as np
import pytest
from pitstudio_pipeline.mine_to_mill.select import HeldOutProtocolError, ProtocolLog, r2_min, select_family
from pitstudio_pipeline.mine_to_mill.train import (
    build_mlp,
    fit_input_transform,
    standardised_mse,
    train_gbm,
    train_mlp,
)

OK_TREES = {"convertible": True, "parity_cpu": True, "parity_wasm": True}


def _pick(gbm, mlp, gbm_bytes=500_000, mlp_bytes=200_000, trees=None):
    return select_family({"gbm": gbm, "mlp": mlp}, {"gbm": gbm_bytes, "mlp": mlp_bytes}, trees=trees or OK_TREES)


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-04: the selection rule
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-04")
def test_the_minimum_over_outputs_is_the_score_of_a_family() -> None:
    assert r2_min([0.99, 0.97, 0.91]) == 0.91


@pytest.mark.req("FR-017-04")
def test_the_higher_minimum_validation_r2_wins_when_the_gap_is_at_least_the_band() -> None:
    assert _pick([0.9, 0.9, 0.9], [0.9078125, 0.9078125, 0.9078125]).family == "mlp"  # gap 0.0078 > 0.005
    assert _pick([0.9078125, 0.95, 0.99], [0.9, 0.99, 0.99]).family == "gbm"
    # the minimum over outputs decides, not the mean: gbm mean is higher, its minimum is lower
    assert _pick([0.99, 0.99, 0.90], [0.95, 0.95, 0.95]).family == "mlp"


@pytest.mark.req("FR-017-04")
def test_within_the_band_the_smaller_onnx_file_wins_even_when_its_r2_is_lower() -> None:
    gbm, mlp = [0.9039, 0.95, 0.95], [0.9, 0.95, 0.95]  # gap 0.0039 < 0.005
    assert _pick(gbm, mlp, gbm_bytes=800_000, mlp_bytes=200_000).family == "mlp"
    assert _pick(gbm, mlp, gbm_bytes=100_000, mlp_bytes=200_000).family == "gbm"
    sel = _pick(gbm, mlp, gbm_bytes=800_000, mlp_bytes=200_000)
    assert sel.reason


@pytest.mark.req("FR-017-04")
@pytest.mark.parametrize(
    ("trees", "bytes_"),
    [
        ({"convertible": False, "parity_cpu": True, "parity_wasm": True}, 500_000),
        ({"convertible": True, "parity_cpu": False, "parity_wasm": True}, 500_000),
        ({"convertible": True, "parity_cpu": True, "parity_wasm": False}, 500_000),
        (OK_TREES, 1_000_001),
    ],
)
def test_ineligible_trees_never_win_even_with_a_much_higher_r2(trees: dict, bytes_: int) -> None:
    sel = _pick([0.99] * 3, [0.90] * 3, gbm_bytes=bytes_, trees=trees)
    assert sel.family == "mlp"
    assert "ineligible" in sel.reason


@pytest.mark.req("FR-017-04")
def test_trees_of_exactly_one_million_bytes_are_eligible() -> None:
    assert _pick([0.99] * 3, [0.90] * 3, gbm_bytes=1_000_000).family == "gbm"


@pytest.mark.req("FR-017-04")
def test_the_held_out_sweeps_are_touched_once_and_only_after_selection() -> None:
    log = ProtocolLog()
    with pytest.raises(HeldOutProtocolError):
        log.touch_held_out()  # before selection
    log.record_selection(_pick([0.99] * 3, [0.9] * 3))
    assert log.touch_held_out() is None
    with pytest.raises(HeldOutProtocolError):
        log.touch_held_out()  # a second look


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-03: the families
# ----------------------------------------------------------------------------------------------------------------------


def _data(n: int, seed: int):
    rng = np.random.default_rng(seed)
    X = np.column_stack([rng.uniform(1, 10, n), rng.uniform(0.5, 2, n), rng.uniform(100, 300, n)])
    Y = np.column_stack([2 * X[:, 0] + X[:, 1], 100 / X[:, 2] + 0.3 * X[:, 0]])
    return X, Y


@pytest.mark.req("FR-017-03")
def test_standardised_mse_by_hand() -> None:
    pred = np.array([[1.0, 10.0], [2.0, 20.0]])
    target = np.array([[1.0, 12.0], [4.0, 20.0]])
    # errors 0, -2, -2, 0 divided by std (2, 4): 0, 0.25, 1, 0 -> mean over 4 = 0.3125
    assert standardised_mse(pred, target, mean=np.zeros(2), std=np.array([2.0, 4.0])) == pytest.approx(0.3125)


@pytest.mark.req("FR-017-03")
def test_the_input_transform_logs_positive_columns_then_standardises_with_training_statistics() -> None:
    X = np.array([[1.0, 5.0], [10.0, 7.0], [100.0, 9.0], [1000.0, 11.0]])
    t = fit_input_transform(X, positive_columns=[0])
    logs = np.log(X[:, 0])
    expected0 = (logs - logs.mean()) / logs.std()
    np.testing.assert_allclose(t.apply(X)[:, 0], expected0, rtol=1e-12)
    expected1 = (X[:, 1] - X[:, 1].mean()) / X[:, 1].std()  # not logged
    np.testing.assert_allclose(t.apply(X)[:, 1], expected1, rtol=1e-12)
    # a new row is transformed with the TRAINING statistics
    row = np.array([[10.0, 7.0]])
    np.testing.assert_allclose(t.apply(row)[0, 0], (np.log(10.0) - logs.mean()) / logs.std(), rtol=1e-12)


@pytest.mark.req("FR-017-03")
@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_the_input_transform_refuses_non_positive_or_non_finite_values_in_log_columns(bad: float) -> None:
    X = np.array([[1.0, 5.0], [bad, 7.0], [3.0, 9.0]])
    with pytest.raises(ValueError, match=r"."):
        fit_input_transform(X, positive_columns=[0])


@pytest.mark.req("FR-017-03")
def test_the_mlp_has_three_hidden_layers_of_64_units_with_silu() -> None:
    import torch

    net = build_mlp(15, 3)
    layers = list(net.children()) if not isinstance(net, torch.nn.Sequential) else list(net)
    linears = [m for m in layers if isinstance(m, torch.nn.Linear)]
    assert [(m.in_features, m.out_features) for m in linears] == [(15, 64), (64, 64), (64, 64), (64, 3)]
    assert sum(isinstance(m, torch.nn.SiLU) for m in layers) == 3
    assert net(torch.zeros(4, 15)).shape == (4, 3)  # multi-output


@pytest.mark.req("FR-017-03")
def test_one_gradient_boosted_model_per_output_with_hyper_parameters_chosen_on_validation_only() -> None:
    from sklearn.ensemble import HistGradientBoostingRegressor

    Xtr, Ytr = _data(600, 1)
    Xva, Yva = _data(200, 2)
    grid = [{"max_iter": 5, "learning_rate": 0.05}, {"max_iter": 200, "learning_rate": 0.1}, {"max_iter": 20}]
    model = train_gbm(Xtr, Ytr, Xva, Yva, grid=grid)
    assert len(model.models) == 2
    assert all(isinstance(m, HistGradientBoostingRegressor) for m in model.models)
    # reference: fit every grid entry directly, score on the standardised validation MSE
    std = Ytr.std(axis=0)
    scores = []
    for params in grid:
        preds = np.column_stack(
            [
                HistGradientBoostingRegressor(early_stopping=False, **params).fit(Xtr, Ytr[:, j]).predict(Xva)
                for j in range(2)
            ]
        )
        scores.append(float(np.mean(((preds - Yva) / std) ** 2)))
    assert model.params == grid[int(np.argmin(scores))]
    assert model.predict(Xva).shape == (200, 2)


@pytest.mark.req("FR-017-03")
def test_both_families_fit_a_noise_free_target() -> None:
    Xtr, Ytr = _data(1500, 3)
    Xva, Yva = _data(400, 4)
    gbm = train_gbm(Xtr, Ytr, Xva, Yva, grid=[{"max_iter": 200, "learning_rate": 0.1}])
    mlp = train_mlp(Xtr, Ytr, Xva, Yva, positive_columns=[0, 1, 2], epochs=300, seed=0)

    def r2(model, j):
        p = model.predict(Xva)[:, j]
        return 1 - np.sum((Yva[:, j] - p) ** 2) / np.sum((Yva[:, j] - Yva[:, j].mean()) ** 2)

    for j in range(2):
        assert r2(gbm, j) >= 0.85
        assert r2(mlp, j) >= 0.9
