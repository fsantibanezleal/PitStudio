// T-018-059 [red, @gpu, not run here] · FR-018-56 for the WGSL granular kernels (engine `granular`: dem_step, dem_pile, mpm_collapse), P-018-59 (Newton's third
// law), P-018-60 (translation invariance), P-018-61 (particle conservation and MPM mass drift). Runs only in the Playwright project `webgpu`.
//
// Hooks: web/e2e/support/gpu-kernels.ts (host call with buffers on tier T1) and web/e2e/support/parity.ts (fixtures through `run`).
// Oracles: Warp DEM/MPM kernels on the CPU device as the per-kernel reference (fixtures, DC-018-04, class wgsl-kernel, non-dimensional max abs <= 1e-3) and the
// spec 005 golden observables (DC-005-06; class wgsl-observables: repose +-1.5 deg, run-out +-5 %, discharge +-5 %, mass drift < 0.5 %); Newton's third law
// (sum of contact forces = 0), translation invariance, conservation of the particle count, written in spec 018 section 4.
import { expect, test } from "@playwright/test";
import { loadParityFixtures } from "../../src/test-support/parity-fixtures";
import { gpuCall, openGpuRunner, rng } from "../support/gpu-kernels";
import { openParityRunner, runParity } from "../support/parity";

const R = 0.05; // particle radius, m
const RHO = 2600; // kg/m3
const MASS = (4 / 3) * Math.PI * R ** 3 * RHO;
const G = 9.81;

function config(seed: number, n: number, shift: [number, number, number] = [0, 0, 0]) {
  const next = rng(seed);
  const pos: number[] = [];
  const vel: number[] = [];
  // a loose cluster so that many pairs touch (centre spacing below 2 R) and no wall is in range
  for (let i = 0; i < n; i++) {
    pos.push(next() * 0.5 + 100 + shift[0], next() * 0.5 + 100 + shift[1], next() * 0.5 + 100 + shift[2]);
    vel.push(next() - 0.5, next() - 0.5, next() - 0.5);
  }
  return { pos, vel };
}
const demArgs = {
  radius_m: R,
  density_kg_per_m3: RHO,
  youngs_modulus_pa: 5e7,
  poisson_ratio: 0.3,
  restitution: 0.5,
  friction_static: 0.5,
  friction_rolling: 0.05,
  step_s: 1e-4,
  contact_capacity: 16,
};
async function demForces(
  page: import("@playwright/test").Page,
  c: { pos: number[]; vel: number[] },
  n: number,
): Promise<number[]> {
  const shape = { particles: n, components: 3 };
  const reply = await gpuCall(page, "granular", "dem_step", demArgs, [
    { name: "positions_m", values: c.pos, shape },
    { name: "velocities_m_per_s", values: c.vel, shape },
  ]);
  expect(reply.response.kind, JSON.stringify(reply.response)).toBe("output");
  return reply.buffers.forces_n as number[];
}

test.describe("granular WGSL kernels @gpu (FR-018-56)", () => {
  test("FR-018-56 · @gpu per-kernel outputs equal Warp's CPU reference within non-dimensional max abs 1e-3 on every kernel fixture", async ({
    page,
  }) => {
    const fixtures = loadParityFixtures("granular").filter((f) => f.tolerance.class === "wgsl-kernel");
    expect(fixtures.length, "a wgsl-kernel fixture for granular exists").toBeGreaterThan(0);
    await openParityRunner(page);
    for (const fx of fixtures) {
      const r = await runParity(page, "granular", fx);
      expect(r.verdict, fx.file).toBe("pass");
      expect(r.maxError.abs, fx.file).toBeLessThanOrEqual(1e-3);
    }
  });

  test("FR-018-56 · @gpu full-run observables agree with the spec 005 goldens: repose within 1.5 deg, run-out and discharge within 5 %, mass drift below 0.5 %", async ({
    page,
  }) => {
    const fixtures = loadParityFixtures("granular").filter((f) => f.tolerance.class === "wgsl-observables");
    expect(fixtures.length, "a wgsl-observables fixture for granular exists").toBeGreaterThan(0);
    await openParityRunner(page);
    for (const fx of fixtures) {
      const r = await runParity(page, "granular", fx);
      expect(r.verdict, fx.file).toBe("pass");
      const obs = r.maxError as Record<string, number>;
      if (obs.repose_deg !== undefined) expect(obs.repose_deg).toBeLessThanOrEqual(1.5);
      if (obs.runout_rel !== undefined) expect(obs.runout_rel).toBeLessThanOrEqual(0.05);
      if (obs.discharge_rel !== undefined) expect(obs.discharge_rel).toBeLessThanOrEqual(0.05);
      if (obs.mass_drift_rel !== undefined) expect(obs.mass_drift_rel).toBeLessThan(0.005);
    }
  });

  for (const seed of [1, 2, 3, 4, 5]) {
    test(`P-018-59 · @gpu seed ${seed}: the contact forces sum to zero over all particles without walls (|sum f| <= 1e-5 sum |f|)`, async ({
      page,
    }) => {
      await openGpuRunner(page);
      const n = 150 + 10 * seed;
      const f = await demForces(page, config(seed, n), n);
      expect(f).toHaveLength(3 * n);
      let sx = 0;
      let sy = 0;
      let sz = 0;
      let total = 0;
      for (let i = 0; i < n; i++) {
        sx += f[3 * i] as number;
        sy += f[3 * i + 1] as number;
        sz += f[3 * i + 2] as number;
        total += Math.hypot(f[3 * i] as number, f[3 * i + 1] as number, f[3 * i + 2] as number);
      }
      expect(total, "the cluster has contacts").toBeGreaterThan(0);
      expect(Math.hypot(sx, sy, sz)).toBeLessThanOrEqual(1e-5 * total);
    });

    test(`P-018-60 · @gpu seed ${seed}: translating every particle leaves the contact forces unchanged (non-dimensional max abs 1e-3)`, async ({
      page,
    }) => {
      await openGpuRunner(page);
      const n = 150;
      const a = await demForces(page, config(seed, n), n);
      const b = await demForces(page, config(seed, n, [37.25, -12.5, 8]), n);
      let worst = 0;
      for (let i = 0; i < a.length; i++)
        worst = Math.max(worst, Math.abs((a[i] as number) - (b[i] as number)) / (MASS * G));
      expect(worst).toBeLessThanOrEqual(1e-3);
    });
  }

  test("P-018-61 · @gpu the particle count is conserved exactly in a closed domain (dem_pile) and the mass drift stays below 0.5 % (dem_pile and mpm_collapse)", async ({
    page,
  }) => {
    await openGpuRunner(page);
    const pile = await gpuCall(page, "granular", "dem_pile", {
      ...demArgs,
      particle_count: 2000,
      method: "lifted-cylinder",
      steps: 20000,
      seed: 11,
    });
    expect(pile.response.kind, JSON.stringify(pile.response)).toBe("output");
    expect(pile.response.result?.particle_count).toBe(2000);
    expect(pile.response.result?.mass_drift_fraction as number).toBeLessThan(0.005);
    const mpm = await gpuCall(page, "granular", "mpm_collapse", {
      particle_count: 4000,
      aspect_ratio: 2,
      column_width_m: 0.1,
      friction_angle_rad: 0.5,
      density_kg_per_m3: RHO,
      youngs_modulus_pa: 1e6,
      poisson_ratio: 0.3,
      step_s: 1e-4,
      steps: 5000,
    });
    expect(mpm.response.kind, JSON.stringify(mpm.response)).toBe("output");
    expect(mpm.response.result?.mass_drift_fraction as number).toBeLessThan(0.005);
  });
});
