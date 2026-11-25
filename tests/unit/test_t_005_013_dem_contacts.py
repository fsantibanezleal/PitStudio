"""T-005-013 - FR-005-06, FR-005-07: HashGrid neighbours, fixed-capacity contact list and `contact-overflow`.

Oracle: hand-built clusters (plan 005 test strategy): a central sphere of radius 10 mm touched by k spheres of
radius 2 mm placed on k Fibonacci-sphere directions at centre distance (10 + 2) mm minus a 12 um overlap, so the
central particle has exactly k contacts and every satellite exactly one (the satellites do not touch each other;
checked in the fixture). Seven far-apart filler particles come first so that the central index is 7, not 0.
History accumulation is checked against kinematics: a contact sliding tangentially at speed v_t for n steps of dt
(no slip, mu_s = 10) accumulates a tangential displacement v_t n dt; a relative rotation rate Omega about a
tangential axis accumulates a rolling rotation Omega n dt (equal radii).

Expected public API (module `pitstudio_studio.physics.dem.step`; see T-005-011 for the constructor):
    DemSimulation(..., contact_capacity=12, ...)
        .contact_capacity            declared capacity (default 12, FR-005-06)
        .hash_grid                   the `warp.HashGrid` used for the neighbour search
        .contact_counts()            numpy int (N,): current contacts per particle (sphere-sphere)
        .contact_list()              (neighbours, tangential, rolling): numpy arrays of shape (N, capacity),
                                     (N, capacity, 3) and (N, capacity, 3); neighbour index -1 marks an empty slot;
                                     tangential [m] and rolling [rad] are the stored contact histories
        .step_index                  completed steps
Errors (module `pitstudio_studio.physics.errors`):
    PhysicsError(Exception) with .error_class (str) and .details (dict); str(error) == f"{error_class}: {detail}".
    contact-overflow: details {"particle": i, "contacts": count, "step": s}, where s is the number of steps completed
    before the failing step (so after the error sim.step_index == s); the count is the true number of contacts,
    not the capacity.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
import warp as wp

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)

from pitstudio_studio.physics.dem.step import DemMaterial, DemSimulation  # noqa: E402
from pitstudio_studio.physics.errors import PhysicsError  # noqa: E402

DEVICE = "cpu"
RC = 10.0e-3  # central radius, m
RS = 2.0e-3  # satellite radius, m
OVERLAP = 12.0e-6  # m
DT = 1.0e-6  # s; Rayleigh limit for R_min = 2 mm: 0.2 * 7.88e-5 s = 1.58e-5 s
N_FILL = 7
CENTRAL = N_FILL


def material(mu_s: float = 0.5) -> DemMaterial:
    return DemMaterial(
        density=2650.0, youngs_modulus=50.0e6, poisson_ratio=0.25, restitution=0.5, friction_static=mu_s,
        friction_rolling=0.1,
    )  # fmt: skip


def fibonacci_directions(k: int) -> np.ndarray:
    i = np.arange(k) + 0.5
    phi = np.arccos(1.0 - 2.0 * i / k)
    theta = math.pi * (1.0 + math.sqrt(5.0)) * i
    return np.c_[np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)]


def cluster(k: int, *, gap: float = -OVERLAP, inward_speed: float = 0.0):
    """Fillers (indices 0-6), the central sphere (index 7) and k satellites (indices 8 .. 8 + k - 1).

    gap < 0 is an overlap; gap > 0 leaves the satellites apart, approaching at `inward_speed`.
    """
    fill = np.c_[np.arange(N_FILL) * 1.0 + 1.0, np.full(N_FILL, 1.0), np.zeros(N_FILL)]
    dirs = fibonacci_directions(k)
    sat = dirs * (RC + RS + gap)
    pos = np.vstack([fill, [[0.0, 0.0, 0.0]], sat])
    radii = np.r_[np.full(N_FILL, RS), RC, np.full(k, RS)]
    vel = np.zeros_like(pos)
    vel[N_FILL + 1 :] = -inward_speed * dirs
    # fixture self-check: satellites never touch each other
    d = np.linalg.norm(sat[:, None, :] - sat[None, :, :], axis=-1) + np.eye(k) * 1.0
    assert d.min() > 2.0 * RS
    return pos, radii, vel


def make(k: int, capacity: int | None = None, **kw) -> DemSimulation:
    pos, radii, vel = cluster(k, **kw)
    extra = {} if capacity is None else {"contact_capacity": capacity}
    return DemSimulation(
        pos, radii, material(), DT, velocities=vel, gravity=(0.0, 0.0, 0.0), device=DEVICE, **extra
    )  # fmt: skip


@pytest.mark.req("FR-005-06")
def test_default_contact_capacity_is_twelve() -> None:
    assert make(1).contact_capacity == 12


@pytest.mark.req("FR-005-06")
def test_neighbour_search_uses_warp_hashgrid() -> None:
    assert isinstance(make(12).hash_grid, wp.HashGrid)


@pytest.mark.req("FR-005-06")
def test_twelve_contacts_fit_in_the_default_list() -> None:
    sim = make(12)
    sim.step(1)
    counts = np.asarray(sim.contact_counts())
    expected = np.r_[np.zeros(N_FILL, int), 12, np.ones(12, int)]
    np.testing.assert_array_equal(counts, expected)
    neighbours, tangential, rolling = sim.contact_list()
    n = len(expected)
    assert np.asarray(neighbours).shape == (n, 12)
    assert np.asarray(tangential).shape == (n, 12, 3)
    assert np.asarray(rolling).shape == (n, 12, 3)
    assert set(np.asarray(neighbours)[CENTRAL].tolist()) == set(range(N_FILL + 1, N_FILL + 13))
    for s in range(N_FILL + 1, N_FILL + 13):
        row = np.asarray(neighbours)[s]
        assert sorted(row[row >= 0].tolist()) == [CENTRAL]
    assert (np.asarray(neighbours)[:N_FILL] == -1).all()


@pytest.mark.req("FR-005-06")
def test_declared_capacity_is_honoured() -> None:
    sim = make(13, capacity=13)
    sim.step(1)
    assert sim.contact_capacity == 13
    assert int(np.asarray(sim.contact_counts())[CENTRAL]) == 13
    neighbours, _, _ = sim.contact_list()
    assert np.asarray(neighbours).shape[1] == 13
    assert set(np.asarray(neighbours)[CENTRAL].tolist()) == set(range(N_FILL + 1, N_FILL + 14))


def pair_history(sim: DemSimulation, i: int, j: int) -> tuple[np.ndarray, np.ndarray]:
    """History of contact (i, j) from whichever particle's list stores it (both entries must agree in size)."""
    neighbours, tangential, rolling = (np.asarray(a) for a in sim.contact_list())
    found = []
    for a, b in ((i, j), (j, i)):
        slots = np.nonzero(neighbours[a] == b)[0]
        assert len(slots) <= 1, f"contact ({a}, {b}) stored twice in one list"
        if len(slots):
            found.append((tangential[a, slots[0]], rolling[a, slots[0]]))
    assert found, f"contact ({i}, {j}) is in no contact list"
    if len(found) == 2:
        assert np.linalg.norm(found[0][0]) == pytest.approx(np.linalg.norm(found[1][0]), rel=1e-5, abs=1e-15)
        assert np.linalg.norm(found[0][1]) == pytest.approx(np.linalg.norm(found[1][1]), rel=1e-5, abs=1e-15)
    return found[0]


@pytest.mark.req("FR-005-06")
def test_tangential_and_rolling_history_accumulate_across_steps() -> None:
    r = 5.0e-3
    v_t = 0.01  # m/s along y, normal along x
    omega = -2.0  # rad/s about z (a tangential axis), particle 1 only
    dt = 1.0e-7  # s; short window: the spin-up by the tangential force stays < 0.1 % of omega
    pos = np.array([[0.0, 0.0, 0.0], [2.0 * r - 1.0e-3 * r, 0.0, 0.0]])
    vel = np.array([[0.0, 0.0, 0.0], [0.0, v_t, 0.0]])
    ang = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, omega]])
    sim = DemSimulation(
        pos, np.full(2, r), material(mu_s=10.0), dt, velocities=vel, angular_velocities=ang,
        gravity=(0.0, 0.0, 0.0), device=DEVICE,
    )  # fmt: skip
    n = 50
    sim.step(n)
    t1, r1 = pair_history(sim, 0, 1)
    sim.step(n)
    t2, r2 = pair_history(sim, 0, 1)
    # the history is accumulated, not recomputed from the current step: it doubles from n to 2n steps
    # (within 3 %, whether the accumulation starts at step 0 or step 1)
    assert np.linalg.norm(t2) == pytest.approx(2.0 * np.linalg.norm(t1), rel=0.03)
    assert np.linalg.norm(r2) == pytest.approx(2.0 * np.linalg.norm(r1), rel=0.03)
    # rolling rotation: |Omega| * 2n * dt (rad)
    assert np.linalg.norm(r2) == pytest.approx(abs(omega) * 2 * n * dt, rel=0.02)
    # tangential displacement: the contact point of particle 1 (at -r x from its centre) moves at
    # v_t y + omega z x (-r x) = (v_t - omega r) y = 0.02 m/s along y; particle 0 is at rest
    v_contact = v_t - omega * r
    assert np.linalg.norm(t2) == pytest.approx(v_contact * 2 * n * dt, rel=0.02)
    assert abs(t2[1]) == pytest.approx(np.linalg.norm(t2), rel=1e-3)


@pytest.mark.req("FR-005-07")
def test_thirteenth_contact_overflows_the_default_list() -> None:
    sim = make(13)
    with pytest.raises(PhysicsError) as info:
        sim.step(1)
    err = info.value
    assert err.error_class == "contact-overflow"
    assert str(err).startswith("contact-overflow: ")
    assert err.details["particle"] == CENTRAL
    assert err.details["contacts"] == 13
    assert err.details["step"] == 0
    assert sim.step_index == 0
    msg = str(err)
    assert "7" in msg
    assert "13" in msg


@pytest.mark.req("FR-005-07")
def test_overflow_with_a_small_declared_capacity() -> None:
    sim = make(5, capacity=4)
    with pytest.raises(PhysicsError) as info:
        sim.step(3)
    assert info.value.error_class == "contact-overflow"
    assert info.value.details["particle"] == CENTRAL
    assert info.value.details["contacts"] == 5


@pytest.mark.req("FR-005-07")
def test_overflow_reports_the_step_at_which_it_happens() -> None:
    # gap 1 um closed at 0.01 m/s with dt = 1 us: first contact after about 1e-6 / (0.01 * 1e-6) = 100 steps
    sim = make(13, gap=1.0e-6, inward_speed=0.01)
    with pytest.raises(PhysicsError) as info:
        sim.step(1000)
    step = info.value.details["step"]
    assert info.value.error_class == "contact-overflow"
    assert 90 <= step <= 110
    assert sim.step_index == step
    assert info.value.details["contacts"] == 13


@pytest.mark.req("FR-005-06")
@pytest.mark.parametrize("bad", [0, -1, 65, 12.5, math.nan])
def test_invalid_contact_capacity_is_rejected(bad) -> None:
    """Hostile input: the scenario schema bounds the capacity to integers 1..64 (DC-005-01 dem block)."""
    with pytest.raises((PhysicsError, ValueError, TypeError)):
        make(1, capacity=bad)
