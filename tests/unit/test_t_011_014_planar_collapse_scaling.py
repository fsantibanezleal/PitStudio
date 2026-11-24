"""Planar reference data: the column collapse is verified by the published 2-D run-out scaling (T-011-014, FR-011-03).

Not locked. A granular column of aspect ratio a = H0 / L0 collapses dynamically, so its deposit slope falls below the
static repose angle as a grows; the repose range of pile and dump is the wrong check for it. The family is checked
against the published scaling laws of 2-D column collapse (Lube et al. 2005, Phys. Rev. E 72, 041301, as quoted by
Staron and Hinch 2005, arXiv:physics/0501022; Lajeunesse, Monnier and Homsy 2005, Phys. Fluids 17, 103302; Sarlin et
al. 2021, arXiv:2112.11458): the normalised run-out (L_inf - L0) / L0 and the normalised final height H_inf / L0, per
regime of a. The synthetic deposits below are built from those laws.

The final height in the free-fall regime (a >= 0.8) is the exception (gns-final, owner standing directive): the
published laws give the exponent 1/3 (Lajeunesse, Sarlin) or 0.4 (Lube; Balmforth and Kerswell 0.5), their coefficient
depends on the material (friction and rolling resistance change the deposit height; Balmforth and Kerswell 2005, J.
Fluid Mech. 538, 399-428), so the regime is accepted when the fitted exponent of H_inf / L0 against a is within 0.05
of 0.4, and the fitted coefficient is reported, not gated."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.physics.planar import space, verify  # noqa: E402

D = space.D
L0 = 0.5


def _geom(gid: str, a: float, run_out: float, height: float, width: float = L0) -> dict:
    """One geometry (the mean of its seeds): normalised run-out and final height times L0."""
    return {
        "geometry_id": gid,
        "aspect_ratio": a,
        "column_width_m": width,
        "run_out_m": run_out * width,
        "height_m": height * width,
    }


def _on_laws(a: float, t: float = 0.0) -> dict:
    """A deposit at a fraction t of the published half-spread above the midpoint of the laws (t = 0: on it).

    Free-fall heights (a >= 0.8) follow H / L0 = 0.93 a^0.4, the exponent the free-fall regime is gated on; t moves the
    run-out only there.
    """
    ro_lo, ro_hi = verify.law_envelope("runout", a)
    h_lo, h_hi = verify.law_envelope("height", a)
    ro_mid, h_mid = 0.5 * (ro_lo + ro_hi), 0.5 * (h_lo + h_hi)
    height = 0.93 * a**0.4 if verify.regime("height", a) == "free-fall" else h_mid + t * 0.5 * (h_hi - h_lo)
    return _geom(f"a{a}", a, ro_mid + t * 0.5 * (ro_hi - ro_lo), height)


def _free_fall(exponent: float, coefficient: float = 0.93, aspects=(0.9, 1.3, 1.8, 2.4, 3.0, 3.6, 4.0)) -> list[dict]:
    """Free-fall deposits with H / L0 = coefficient a^exponent and the run-out on the laws."""
    out = []
    for a in aspects:
        g = _on_laws(a)
        g["height_m"] = coefficient * a**exponent * L0
        out.append(g)
    return out


@pytest.mark.req("FR-011-03")
def test_011_a_the_cited_laws_give_their_coefficients_and_exponents() -> None:
    # run-out, a < 2.3: Lube 1.2 a, Sarlin 1.85 a (both linear; Lajeunesse: proportional to a for a < 3)
    lo, hi = verify.law_envelope("runout", 1.0)
    assert (lo, hi) == pytest.approx((1.2, 1.85))
    # run-out, a > 3: Lube 1.9 a^(2/3), Sarlin 2.67 a^(2/3)
    lo, hi = verify.law_envelope("runout", 4.0)
    assert lo == pytest.approx(1.9 * 4.0 ** (2 / 3))
    assert hi == pytest.approx(2.67 * 4.0 ** (2 / 3))
    # final height, a below 0.7: H = a in every law, no spread
    lo, hi = verify.law_envelope("height", 0.5)
    assert (lo, hi) == pytest.approx((0.5, 0.5))
    # final height, a above 0.8: Sarlin 0.93 a^(1/3); Lajeunesse a^(1/3) continuous with H = a at 0.7
    lo, hi = verify.law_envelope("height", 2.0)
    assert hi == pytest.approx(0.93 * 2.0 ** (1 / 3))
    assert lo == pytest.approx(0.7 ** (2 / 3) * 2.0 ** (1 / 3))


@pytest.mark.req("FR-011-03")
def test_011_a_the_regimes_split_at_the_boundaries_of_the_cited_laws() -> None:
    assert [verify.regime("runout", a) for a in (0.5, 2.29, 2.3, 3.0, 3.01, 4.0)] == [
        "linear",
        "linear",
        "transition",
        "transition",
        "power",
        "power",
    ]
    assert [verify.regime("height", a) for a in (0.5, 0.7, 0.71, 0.79, 0.8, 4.0)] == [
        "slump",
        "slump",
        "transition",
        "transition",
        "free-fall",
        "free-fall",
    ]
    # where the laws disagree on the branch (Lube switches at 2.3, the others at 3) the envelope takes both branches
    lo, hi = verify.law_envelope("runout", 2.6)
    assert lo == pytest.approx(min(1.2 * 2.6, 1.9 * 2.6 ** (2 / 3)))
    assert hi == pytest.approx(max(1.85 * 2.6, 2.67 * 2.6 ** (2 / 3)))


@pytest.mark.req("FR-011-03")
def test_011_a_the_scatter_is_the_published_spread_with_a_one_grain_floor() -> None:
    # run-out, linear regime: half-spread (1.85 - 1.2) / (1.85 + 1.2) = 21.3 percent of the midpoint
    assert verify.scatter("runout", 1.0, L0) == pytest.approx(0.65 / 3.05)
    # a slump has no spread between the laws; the floor is one grain diameter over the height of the column
    assert verify.scatter("height", 0.5, L0) == pytest.approx(D / (0.5 * L0))


@pytest.mark.req("FR-011-03")
def test_011_a_deposits_on_the_laws_and_inside_the_scatter_pass_in_every_regime() -> None:
    geoms = [
        _on_laws(a, t)
        for a, t in ((0.55, 0.0), (0.9, 0.5), (1.5, -0.8), (2.0, 0.8), (2.6, 0.0), (3.5, 0.9), (3.95, -0.5))
    ]
    rep = verify.collapse_scaling(geoms)
    assert rep["problems"] == []
    assert {g["geometry_id"] for g in rep["geometries"]} == {g["geometry_id"] for g in geoms}
    assert set(rep["runout"]) == {"linear", "transition", "power"}
    assert set(rep["height"]) == {
        "slump",
        "free-fall",
    }  # no geometry between 0.7 and 0.8: the regime is absent, not failed
    for part in ("runout", "height"):
        for name, res in rep[part].items():
            assert res["ok"]
            assert res["n"] >= 1
            if (part, name) != ("height", "free-fall"):  # the free-fall height is gated on its exponent
                assert abs(res["mean_deviation"]) <= res["mean_scatter"]


@pytest.mark.req("FR-011-03")
def test_011_a_a_regime_whose_mean_deviates_beyond_the_scatter_fails_and_names_the_numbers() -> None:
    # every geometry of the power regime sits 1.5 half-spreads above the laws: each is within twice the scatter,
    # the regime mean is not within the scatter
    geoms = [_on_laws(a, 1.5) for a in (3.4, 3.7, 3.95)]
    rep = verify.collapse_scaling(geoms)
    (problem,) = [p for p in rep["problems"] if "power" in p]
    assert "run-out" in problem
    assert "mean deviation" in problem
    assert not rep["runout"]["power"]["ok"]
    assert rep["runout"]["power"]["mean_deviation"] > rep["runout"]["power"]["mean_scatter"]


@pytest.mark.req("FR-011-03")
def test_011_a_one_geometry_beyond_twice_the_scatter_fails_even_when_the_regime_mean_passes() -> None:
    good = [_on_laws(a, 0.0) for a in (1.0, 1.2, 1.4, 1.6, 1.8, 2.0)]
    ro_lo, ro_hi = verify.law_envelope("runout", 1.1)
    mid = 0.5 * (ro_lo + ro_hi)
    s = verify.scatter("runout", 1.1, L0)
    off = _on_laws(1.1)
    off["run_out_m"] = mid * (1.0 + 2.1 * s) * L0  # 2.1 scatters above: over the per-geometry limit, mean still inside
    rep = verify.collapse_scaling([*good, off])
    lin = rep["runout"]["linear"]
    assert abs(lin["mean_deviation"]) <= lin["mean_scatter"]  # the mean passes, the regime does not
    assert not lin["ok"]
    (problem,) = [p for p in rep["problems"] if off["geometry_id"] in p]
    assert "twice" in problem
    assert any(g["geometry_id"] == off["geometry_id"] and not g["runout_ok"] for g in rep["geometries"])


@pytest.mark.req("FR-011-03")
def test_011_a_a_slump_or_transition_height_is_still_checked_against_the_published_laws() -> None:
    geoms = [_on_laws(a, 0.0) for a in (0.55, 0.75, 1.5, 2.5, 3.5)]
    for g in geoms[:2]:
        g["height_m"] *= 1.4  # a deposit 40 percent taller than the laws where the laws are one curve
    rep = verify.collapse_scaling(geoms)
    assert rep["runout"]["linear"]["ok"]
    assert not rep["height"]["slump"]["ok"]
    assert any("final height" in p and "slump" in p for p in rep["problems"])
    assert any("final height" in p and "a0.75" in p for p in rep["problems"])


@pytest.mark.req("FR-011-03")
def test_011_a_the_free_fall_height_is_accepted_on_the_fitted_exponent_within_005_of_04() -> None:
    for exponent in (0.35, 0.40, 0.423, 0.45):
        rep = verify.collapse_scaling(_free_fall(exponent))
        ff = rep["height"]["free-fall"]
        assert ff["ok"], exponent
        assert ff["exponent"] == pytest.approx(exponent, abs=1e-9)
        assert ff["coefficient"] == pytest.approx(0.93)
        assert ff["exponent_published"] == 0.4
        assert ff["exponent_tolerance"] == 0.05
        assert not any("final height" in p for p in rep["problems"])
    # the two laws that give 1/3 are outside the band, and so are a flat or a linear height
    for exponent in (1 / 3, 0.34, 0.46, 0.5, 0.0, 1.0):
        rep = verify.collapse_scaling(_free_fall(exponent))
        assert not rep["height"]["free-fall"]["ok"], exponent
        (problem,) = [p for p in rep["problems"] if "final height" in p]
        assert "free-fall" in problem
        assert "exponent" in problem
        assert "0.4" in problem
        assert f"{rep['height']['free-fall']['exponent']:.3f}" in problem


@pytest.mark.req("FR-011-03")
def test_011_a_the_free_fall_coefficient_is_reported_and_not_gated() -> None:
    for coefficient in (0.7, 0.93, 1.3, 1.6):  # friction and rolling resistance move the deposit height
        rep = verify.collapse_scaling(_free_fall(0.4, coefficient))
        ff = rep["height"]["free-fall"]
        assert ff["ok"]
        assert ff["coefficient"] == pytest.approx(coefficient)
        assert not any("final height" in p for p in rep["problems"])


@pytest.mark.req("FR-011-03")
def test_011_a_the_free_fall_exponent_needs_three_geometries_over_a_real_span_of_a() -> None:
    rep = verify.collapse_scaling(_free_fall(0.4, aspects=(1.5, 2.0)))
    assert not rep["height"]["free-fall"]["ok"]
    assert any("final height" in p and "fit" in p for p in rep["problems"])
    rep = verify.collapse_scaling(_free_fall(0.4, aspects=(2.0, 2.0, 2.0)))
    assert not rep["height"]["free-fall"]["ok"]


@pytest.mark.req("FR-011-03")
def test_011_a_a_geometry_outside_the_declared_aspect_range_is_reported_and_not_dropped() -> None:
    geoms = [_on_laws(2.0), _on_laws(5.0)]
    rep = verify.collapse_scaling(geoms)
    assert {g["geometry_id"] for g in rep["geometries"]} == {"a2.0", "a5.0"}
    assert rep["runout"]["power"]["n"] == 1  # a = 5 is evaluated on the power law, not skipped
    assert any("a5.0" in p and "aspect ratio" in p and "outside" in p for p in rep["problems"])


@pytest.mark.req("FR-011-03")
def test_011_a_the_repose_range_gates_pile_and_dump_and_not_the_collapse() -> None:
    summary = {
        "column-collapse": {"n": 30, "repose_mean_deg": 21.3},  # the collapse is judged by its run-out, not its slope
        "pile-formation": {"n": 30, "repose_mean_deg": 32.2},
        "dump-over-crest": {"n": 30, "repose_mean_deg": 30.9},
    }
    assert verify.range_problems(summary) == []
    bad = {**summary, "dump-over-crest": {"n": 30, "repose_mean_deg": 23.8}}
    (problem,) = verify.range_problems(bad)
    for token in ("dump-over-crest", "23.8", "25", "35"):
        assert token in problem
    empty = {**summary, "pile-formation": {"n": 0, "repose_mean_deg": None}}
    assert any("pile-formation" in p for p in verify.range_problems(empty))


@pytest.mark.req("FR-011-03")
def test_011_a_rows_and_records_become_geometries_with_the_seed_mean_and_boundary_free_height() -> None:
    rows = [
        {
            "family": "column-collapse",
            "geometry_id": "g1",
            "run_out_m": 0.60,
            "pile_height_d": 40.0,
            "repose_deg": 20.0,
        },
        {
            "family": "column-collapse",
            "geometry_id": "g1",
            "run_out_m": 0.70,
            "pile_height_d": 42.0,
            "repose_deg": 22.0,
        },
        {"family": "pile-formation", "geometry_id": "g2", "run_out_m": 1.0, "pile_height_d": 50.0, "repose_deg": 30.0},
    ]
    records = {"g1": {"aspect_ratio": 1.5, "column_width_m": 0.4}, "g2": {"pour_height_m": 1.0}}
    (g,) = verify.collapse_geometries(rows, records)
    assert g["geometry_id"] == "g1"
    assert g["aspect_ratio"] == 1.5
    assert g["column_width_m"] == 0.4
    assert g["run_out_m"] == pytest.approx(0.65)
    assert g["height_m"] == pytest.approx(41.0 * D)
    assert g["repose_deg"] == pytest.approx(21.0)
