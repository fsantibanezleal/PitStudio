"""Probe (studio env): Warp kernels and a Newton simulation step on the GPU, plus OpenUSD import."""

from __future__ import annotations

from typing import Any

from _common import run_probe, timer


def body(r: dict[str, Any]) -> None:
    import numpy as np
    import warp as wp
    from pxr import Usd

    wp.config.quiet = True
    wp.init()
    r["versions"].update(warp=wp.config.version, usd=".".join(map(str, Usd.GetVersion())))
    if not wp.is_cuda_available():
        raise RuntimeError("Warp sees no CUDA device")
    dev = wp.get_cuda_device()
    r["metrics"]["device"] = dev.name
    r["metrics"]["arch"] = f"sm_{dev.arch}"

    @wp.kernel
    def saxpy(a: float, x: wp.array(dtype=float), y: wp.array(dtype=float)):  # type: ignore[valid-type]
        i = wp.tid()
        y[i] = a * x[i] + y[i]

    n = 1 << 24
    x = wp.array(np.ones(n, dtype=np.float32), device=dev)
    y = wp.array(np.full(n, 2.0, dtype=np.float32), device=dev)
    wp.launch(saxpy, dim=n, inputs=[3.0, x, y], device=dev)  # warm-up + JIT
    wp.synchronize_device(dev)
    with timer(r["metrics"], "saxpy_16M_x20_s"):
        for _ in range(20):
            wp.launch(saxpy, dim=n, inputs=[3.0, x, y], device=dev)
        wp.synchronize_device(dev)
    out = y.numpy()
    expected = 2.0 + 3.0 * 21
    if not np.allclose(out[:: n // 8], expected):
        raise AssertionError(f"saxpy result {out[0]} != {expected}")

    import newton

    r["versions"]["newton"] = newton.__version__
    builder = newton.ModelBuilder()  # Newton is Z-up by default; gravity acts along -Z
    up = int(getattr(builder.up_axis, "value", builder.up_axis))  # Axis enum -> 0/1/2
    for k in range(64):
        p = [0.1 * (k % 8), 0.0, 0.0]
        p[up] = 1.0 + 0.1 * (k // 8)
        builder.add_particle(pos=wp.vec3(*p), vel=wp.vec3(0.0), mass=1.0, radius=0.04)
    builder.add_ground_plane()
    model = builder.finalize(device=dev)
    solver = newton.solvers.SolverXPBD(model)
    s0, s1 = model.state(), model.state()
    control = model.control()
    contacts = model.collide(s0)
    dt = 1.0 / 240.0
    with timer(r["metrics"], "newton_xpbd_240_steps_s"):
        for _ in range(240):
            s0.clear_forces()
            contacts = model.collide(s0)
            solver.step(s0, s1, control, contacts, dt)
            s0, s1 = s1, s0
        wp.synchronize_device(dev)
    z = s0.particle_q.numpy()
    # after 1 s of free fall from ~1 m, every particle must have dropped and stayed above the ground
    h = z[:, up]
    if not (np.all(h < 1.0) and np.all(h > -0.05)):
        raise AssertionError(f"unexpected particle heights: min {h.min():.3f}, max {h.max():.3f}")
    r["metrics"]["newton_particles"] = int(z.shape[0])


if __name__ == "__main__":
    run_probe("warp_newton", "public", body)
