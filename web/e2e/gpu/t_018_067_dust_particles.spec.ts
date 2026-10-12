// T-018-067 [red, @gpu, not run here] · FR-018-56 for the WGSL dust-particle kernels (engine `dust-particles`: dust_step, dust_run), P-018-65 (Stokes terminal velocity),
// P-018-66 (uniform wind shifts the centroid by U t and leaves the spread unchanged), P-018-67 (the particle count is conserved exactly in a closed box).
// Runs only in the Playwright project `webgpu`.
//
// Hooks: web/e2e/support/gpu-kernels.ts and web/e2e/support/parity.ts. Oracles: Warp's particle kernels on the CPU device (per-kernel fixtures, class wgsl-kernel,
// non-dimensional max abs <= 1e-3) and the spec 005 goldens; Stokes (1851): v_s = (rho_p - rho_a) g d^2 / (18 mu) for particle Reynolds numbers below 0.1 (d in 1-25 um,
// rho_p in 2,000-3,000 kg/m3, rho_a = 1.2 kg/m3, mu = 1.81e-5 Pa s; spec 018 section 7.3 shows Re <= 0.094), within +-1 %; a uniform wind U moves the cloud by U t (rtol 1e-3).
import { expect, test } from "@playwright/test";
import { loadParityFixtures } from "../../src/test-support/parity-fixtures";
import { gpuCall, openGpuRunner, rng } from "../support/gpu-kernels";
import { openParityRunner, runParity } from "../support/parity";

const G = 9.81;
const MU = 1.81e-5;
const RHO_A = 1.2;
const dust = (
  radius: number,
  rhoP: number,
  wind: [number, number, number],
  diffusivity: number,
  seed: number,
) => ({
  radius_m: radius,
  particle_density_kg_per_m3: rhoP,
  air_density_kg_per_m3: RHO_A,
  air_viscosity_pa_s: MU,
  diffusivity_m2_per_s: diffusivity,
  wind_m_per_s: wind,
  step_s: 0.1,
  seed,
});

async function advance(
  page: import("@playwright/test").Page,
  positions: number[],
  n: number,
  args: ReturnType<typeof dust>,
  steps: number,
): Promise<number[]> {
  let pos = positions;
  for (let k = 0; k < steps; k++) {
    const reply = await gpuCall(page, "dust-particles", "dust_step", { ...args, step_index: k }, [
      { name: "positions_m", values: pos, shape: { particles: n, components: 3 } },
    ]);
    expect(reply.response.kind, JSON.stringify(reply.response)).toBe("output");
    pos = reply.buffers.positions_m as number[];
  }
  return pos;
}
const cloud = (seed: number, n: number, z: number) => {
  const next = rng(seed);
  return Array.from({ length: n }, () => [100 + next() * 4, 100 + next() * 4, z + next() * 4]).flat();
};
const mean = (pos: number[], axis: number) =>
  pos.filter((_, i) => i % 3 === axis).reduce((a, b) => a + b, 0) / (pos.length / 3);
const sd = (pos: number[], axis: number) => {
  const m = mean(pos, axis);
  return Math.sqrt(
    pos.filter((_, i) => i % 3 === axis).reduce((a, b) => a + (b - m) ** 2, 0) / (pos.length / 3),
  );
};

test.describe("dust-particle WGSL kernels @gpu (FR-018-56)", () => {
  test("FR-018-56 · @gpu per-kernel outputs equal Warp's CPU reference within non-dimensional max abs 1e-3 on every kernel fixture", async ({
    page,
  }) => {
    const fixtures = loadParityFixtures("dust-particles").filter((f) => f.tolerance.class === "wgsl-kernel");
    expect(fixtures.length, "a wgsl-kernel fixture for dust-particles exists").toBeGreaterThan(0);
    await openParityRunner(page);
    for (const fx of fixtures) {
      const r = await runParity(page, "dust-particles", fx);
      expect(r.verdict, fx.file).toBe("pass");
      expect(r.maxError.abs, fx.file).toBeLessThanOrEqual(1e-3);
    }
  });

  for (const [d, rhoP] of [
    [2e-6, 2000],
    [5e-6, 2650],
    [10e-6, 3000],
    [20e-6, 2650],
    [25e-6, 3000],
  ] as Array<[number, number]>) {
    test(`P-018-65 · @gpu d = ${d * 1e6} um, rho_p = ${rhoP}: in still air the cloud settles at the Stokes velocity (rho_p - rho_a) g d^2 / (18 mu) within 1 %`, async ({
      page,
    }) => {
      await openGpuRunner(page);
      const n = 500;
      const start = cloud(1, n, 100);
      const end = await advance(page, start, n, dust(d / 2, rhoP, [0, 0, 0], 0, 1), 100);
      const vStokes = ((rhoP - RHO_A) * G * d * d) / (18 * MU);
      const measured = (mean(start, 2) - mean(end, 2)) / (100 * 0.1);
      expect(Math.abs(measured - vStokes)).toBeLessThanOrEqual(0.01 * vStokes);
      // the Stokes domain of the property: particle Reynolds number below 0.1
      expect((RHO_A * vStokes * d) / MU).toBeLessThan(0.1);
    });
  }

  for (const U of [0, 5, 20]) {
    test(`P-018-66 · @gpu U = ${U} m/s: a uniform wind shifts the centroid by U t (rtol 1e-3) and leaves the spread unchanged`, async ({
      page,
    }) => {
      await openGpuRunner(page);
      const n = 800;
      const start = cloud(2, n, 100);
      const calm = await advance(page, start, n, dust(5e-6, 2650, [0, 0, 0], 0.5, 7), 60);
      const windy = await advance(page, start, n, dust(5e-6, 2650, [U, 0, 0], 0.5, 7), 60);
      const t = 60 * 0.1;
      expect(Math.abs(mean(windy, 0) - mean(calm, 0) - U * t)).toBeLessThanOrEqual(1e-3 * Math.max(U * t, 1));
      for (const axis of [0, 1, 2])
        expect(Math.abs(sd(windy, axis) - sd(calm, axis))).toBeLessThanOrEqual(1e-3 * sd(calm, axis));
    });
  }

  test("P-018-67 · @gpu in a closed box with reflecting ground no particle leaves or is lost: airborne + deposited + exited = the particle count, exactly, with none exited", async ({
    page,
    request,
    baseURL,
  }) => {
    const manifest = (await (
      await request.get(new URL("assets/manifest.json", baseURL as string).toString())
    ).json()) as {
      artefacts: Array<{ id: string; sha256: string; bytes: number }>;
    };
    const scene = manifest.artefacts.find((a) => /^c3-.*(terrain|scene)/.test(a.id));
    expect(scene, "the web manifest lists a C3 scene asset for dust_run").toBeDefined();
    await openGpuRunner(page);
    for (const count of [1000, 5000, 20000]) {
      const reply = await gpuCall(page, "dust-particles", "dust_run", {
        scene: { artefact: scene?.id, sha256: scene?.sha256, bytes: scene?.bytes },
        particle_count: count,
        radius_m: 5e-6,
        particle_density_kg_per_m3: 2650,
        air_density_kg_per_m3: RHO_A,
        air_viscosity_pa_s: MU,
        diffusivity_m2_per_s: 1,
        wind_m_per_s: [4, 0, 0],
        source_position_m: [100, 200, 2],
        ground: "reflect",
        boundary: "closed-box",
        duration_s: 120,
        step_s: 0.5,
        seed: 3,
      });
      expect(reply.response.kind, JSON.stringify(reply.response)).toBe("output");
      const r = reply.response.result as {
        particle_count: number;
        airborne: number;
        deposited: number;
        exited: number;
      };
      expect(r.particle_count).toBe(count);
      expect(r.exited).toBe(0);
      expect(r.airborne + r.deposited + r.exited).toBe(count);
    }
  });
});
