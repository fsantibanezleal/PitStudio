"""Neighbour search and fixed-capacity contact lists of the Warp DEM (FR-005-06, FR-005-07).

Every particle owns a list of `capacity` slots (neighbour index, tangential history, rolling history). A step reads
the previous list, finds the current contacts with a Warp `HashGrid` query, carries the history of contacts that
persist, starts a zero history for new ones and writes the new list. Each particle computes its own side of every
contact (the two sides are exact mirror images), so the force kernel needs no atomics and is deterministic.

The device control block `ctl` (int32) carries the halt protocol so that `step(n)` never returns to the host
between steps: ctl[0] halt flag, ctl[1] lowest particle whose contacts exceed the capacity, ctl[2] its true contact
count, ctl[3] completed steps, ctl[4] the step at which the overflow happened.
"""

from __future__ import annotations

import warp as wp

from pitstudio_studio.physics.dem.contact import contact_response

CTL_HALT, CTL_PARTICLE, CTL_COUNT, CTL_STEP, CTL_FAIL_STEP = 0, 1, 2, 3, 4
CTL_SIZE = 8
NO_PARTICLE = 2**31 - 1


@wp.kernel
def contact_kernel(
    grid: wp.uint64,
    pos: wp.array(dtype=wp.vec3d),
    local: wp.array(dtype=wp.vec3),
    vel: wp.array(dtype=wp.vec3),
    ang: wp.array(dtype=wp.vec3),
    radius: wp.array(dtype=float),
    mass: wp.array(dtype=float),
    inertia: wp.array(dtype=float),
    r_max: float,
    pad: float,
    e_star: float,
    g_star: float,
    beta: float,
    mu_s: float,
    mu_r: float,
    dt: float,
    capacity: int,
    nb_old: wp.array(dtype=int),
    tang_old: wp.array(dtype=wp.vec3),
    roll_old: wp.array(dtype=wp.vec3),
    nb_new: wp.array(dtype=int),
    tang_new: wp.array(dtype=wp.vec3),
    roll_new: wp.array(dtype=wp.vec3),
    counts: wp.array(dtype=int),
    ctl: wp.array(dtype=int),
    inside: wp.array(dtype=int),
    force: wp.array(dtype=wp.vec3),
    torque: wp.array(dtype=wp.vec3),
):
    i = wp.tid()
    if ctl[0] != 0:
        return
    base = i * capacity
    if inside[i] == 0:  # left through an outflow boundary: out of the dynamics, no contacts
        for s in range(capacity):
            nb_new[base + s] = -1
            tang_new[base + s] = wp.vec3(0.0, 0.0, 0.0)
            roll_new[base + s] = wp.vec3(0.0, 0.0, 0.0)
        counts[i] = 0
        force[i] = wp.vec3(0.0, 0.0, 0.0)
        torque[i] = wp.vec3(0.0, 0.0, 0.0)
        return
    f = wp.vec3(0.0, 0.0, 0.0)
    t = wp.vec3(0.0, 0.0, 0.0)
    count = int(0)  # noqa: UP018, RUF046
    q = wp.hash_grid_query(grid, local[i], radius[i] + r_max + pad)
    j = int(0)  # noqa: UP018, RUF046
    while wp.hash_grid_query_next(q, j):
        if j == i or inside[j] == 0:
            continue
        dx = pos[j] - pos[i]
        dist = wp.length(dx)
        delta = float(wp.float64(radius[i]) + wp.float64(radius[j]) - dist)
        if delta <= 0.0:
            continue
        slot = count
        count += 1
        if slot >= capacity:
            continue  # counted, not stored: the overflow check stops the run
        n = wp.vec3(float(dx[0]), float(dx[1]), float(dx[2])) / float(dist)
        h_tang = wp.vec3(0.0, 0.0, 0.0)
        h_roll = wp.vec3(0.0, 0.0, 0.0)
        for m in range(capacity):
            if nb_old[base + m] == j:
                h_tang = tang_old[base + m]
                h_roll = roll_old[base + m]
                break
        r_star = radius[i] * radius[j] / (radius[i] + radius[j])
        m_star = mass[i] * mass[j] / (mass[i] + mass[j])
        i_eff = inertia[i] * inertia[j] / (inertia[i] + inertia[j])
        v_contact = vel[i] - vel[j] + wp.cross(ang[i] * radius[i] + ang[j] * radius[j], n)
        fi, ti, tang, roll = contact_response(
            e_star, g_star, r_star, m_star, i_eff, beta, mu_s, mu_r, delta, n, v_contact, ang[i] - ang[j],
            radius[i], h_tang, h_roll, dt,
        )  # fmt: skip
        nb_new[base + slot] = j
        tang_new[base + slot] = tang
        roll_new[base + slot] = roll
        f += fi
        t += ti
    for s in range(wp.min(count, capacity), capacity):
        nb_new[base + s] = -1
        tang_new[base + s] = wp.vec3(0.0, 0.0, 0.0)
        roll_new[base + s] = wp.vec3(0.0, 0.0, 0.0)
    counts[i] = count
    force[i] = f
    torque[i] = t


@wp.kernel
def check_overflow_kernel(counts: wp.array(dtype=int), capacity: int, ctl: wp.array(dtype=int)):
    i = wp.tid()
    if ctl[0] == 0 and counts[i] > capacity:
        wp.atomic_min(ctl, 1, i)


@wp.kernel
def commit_step_kernel(counts: wp.array(dtype=int), n: int, ctl: wp.array(dtype=int)):
    """Single thread: halt on a contact-list overflow (never drop a contact silently), else count the step."""
    if ctl[0] != 0:
        return
    if ctl[1] < n:
        ctl[0] = 1
        ctl[2] = counts[ctl[1]]
        ctl[4] = ctl[3]
    else:
        ctl[3] = ctl[3] + 1
