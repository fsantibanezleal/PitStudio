// T-018-065 [red, @gpu, not run here] · FR-018-56 for the WGSL shallow-water kernels (engine `swe`: swe_step, breach_run), P-018-62 (lake at rest), P-018-63 (mirror
// symmetry), P-018-64 (mass conservation and the Ritter dam-break front). Runs only in the Playwright project `webgpu`.
//
// Hooks: web/e2e/support/gpu-kernels.ts (host call with buffers on tier T1) and web/e2e/support/parity.ts. Oracles: Warp's shallow-water solver on the CPU device
// (per-kernel fixtures, class wgsl-kernel, non-dimensional max abs <= 1e-3) and the spec 005 golden observables; the analytical solutions of spec 018 section 4: a flat free
// surface with zero velocity stays at rest (||u|| <= 1e-6 m/s, ||d eta|| <= 1e-5 m over 1,000 steps), the equations are mirror symmetric, mass drift < 0.5 % in a closed domain,
// and the dry-bed dam-break front moves at 2 sqrt(g h0) (Ritter 1892) within +-5 %.
import { expect, test } from "@playwright/test";
import { loadParityFixtures } from "../../src/test-support/parity-fixtures";
import { gpuCall, openGpuRunner, rng } from "../support/gpu-kernels";
import { openParityRunner, runParity } from "../support/parity";

const G = 9.81;
const base = {
  cell_size_m: 1,
  cfl: 0.45,
  dry_depth_m: 1e-3,
  yield_stress_pa: 0,
  viscosity_pa_s: 0,
  density_kg_per_m3: 1000,
  boundary: "reflective",
};

async function step(
  page: import("@playwright/test").Page,
  rows: number,
  cols: number,
  s: { h: number[]; qx: number[]; qy: number[]; bed: number[] },
  over: Record<string, unknown> = {},
) {
  const shape = { rows, cols };
  const reply = await gpuCall(page, "swe", "swe_step", { ...base, ...over }, [
    { name: "depth_m", values: s.h, shape },
    { name: "discharge_x_m2_per_s", values: s.qx, shape },
    { name: "discharge_y_m2_per_s", values: s.qy, shape },
    { name: "bed_m", values: s.bed, shape },
  ]);
  expect(reply.response.kind, JSON.stringify(reply.response)).toBe("output");
  return {
    h: reply.buffers.depth_m as number[],
    qx: reply.buffers.discharge_x_m2_per_s as number[],
    qy: reply.buffers.discharge_y_m2_per_s as number[],
    dt: reply.response.result?.step_s as number,
  };
}

test.describe("shallow-water WGSL kernels @gpu (FR-018-56)", () => {
  test("FR-018-56 · @gpu per-kernel outputs equal Warp's CPU reference within non-dimensional max abs 1e-3 on every kernel fixture", async ({
    page,
  }) => {
    const fixtures = loadParityFixtures("swe").filter((f) => f.tolerance.class === "wgsl-kernel");
    expect(fixtures.length, "a wgsl-kernel fixture for swe exists").toBeGreaterThan(0);
    await openParityRunner(page);
    for (const fx of fixtures) {
      const r = await runParity(page, "swe", fx);
      expect(r.verdict, fx.file).toBe("pass");
      expect(r.maxError.abs, fx.file).toBeLessThanOrEqual(1e-3);
    }
  });

  test("FR-018-56 · @gpu the breach-run observables agree with the spec 005 goldens (run-out within 5 %, mass drift below 0.5 %)", async ({
    page,
  }) => {
    const fixtures = loadParityFixtures("swe").filter((f) => f.tolerance.class === "wgsl-observables");
    expect(fixtures.length, "a wgsl-observables fixture for swe exists").toBeGreaterThan(0);
    await openParityRunner(page);
    for (const fx of fixtures) {
      const r = await runParity(page, "swe", fx);
      expect(r.verdict, fx.file).toBe("pass");
      expect((r.maxError as Record<string, number>).runout_rel ?? 0).toBeLessThanOrEqual(0.05);
      expect((r.maxError as Record<string, number>).mass_drift_rel ?? 0).toBeLessThan(0.005);
    }
  });

  for (const seed of [1, 2, 3]) {
    test(`P-018-62 · @gpu seed ${seed}: a flat free surface with zero velocity over a random bed stays at rest for 1,000 steps (|u| <= 1e-6 m/s, |d eta| <= 1e-5 m)`, async ({
      page,
    }) => {
      await openGpuRunner(page);
      const next = rng(seed);
      const rows = 32;
      const cols = 32;
      const eta0 = 6;
      const bed = Array.from({ length: rows * cols }, () => next() * 4);
      let s = {
        h: bed.map((z) => eta0 - z),
        qx: new Array(rows * cols).fill(0),
        qy: new Array(rows * cols).fill(0),
        bed,
      };
      for (let i = 0; i < 1000; i++) {
        const out = await step(page, rows, cols, s);
        s = { ...s, h: out.h, qx: out.qx, qy: out.qy };
      }
      let maxU = 0;
      let maxEta = 0;
      for (let i = 0; i < rows * cols; i++) {
        const h = s.h[i] as number;
        maxU = Math.max(maxU, Math.hypot(s.qx[i] as number, s.qy[i] as number) / h);
        maxEta = Math.max(maxEta, Math.abs(h + (bed[i] as number) - eta0));
      }
      expect(maxU).toBeLessThanOrEqual(1e-6);
      expect(maxEta).toBeLessThanOrEqual(1e-5);
    });

    test(`P-018-63 · @gpu seed ${seed}: mirroring the initial state and the bed about x mirrors the solution (non-dimensional max abs 1e-3)`, async ({
      page,
    }) => {
      await openGpuRunner(page);
      const next = rng(10 + seed);
      const rows = 32;
      const cols = 32;
      const bed = Array.from({ length: rows * cols }, () => next() * 2);
      const h = bed.map((z) => 5 - z + next() * 0.5);
      const qx = Array.from({ length: rows * cols }, () => (next() - 0.5) * 0.2);
      const qy = Array.from({ length: rows * cols }, () => (next() - 0.5) * 0.2);
      const flip = (a: number[], sign = 1) =>
        a.map((_, i) => sign * (a[Math.floor(i / cols) * cols + (cols - 1 - (i % cols))] as number));
      let a = { h, qx, qy, bed };
      let b = { h: flip(h), qx: flip(qx, -1), qy: flip(qy), bed: flip(bed) };
      for (let i = 0; i < 50; i++) {
        const oa = await step(page, rows, cols, a);
        const ob = await step(page, rows, cols, b);
        a = { ...a, h: oa.h, qx: oa.qx, qy: oa.qy };
        b = { ...b, h: ob.h, qx: ob.qx, qy: ob.qy };
      }
      const hScale = Math.max(...a.h);
      const qScale = hScale * Math.sqrt(G * hScale);
      const fh = flip(a.h);
      const fqx = flip(a.qx, -1);
      const fqy = flip(a.qy);
      let worst = 0;
      for (let i = 0; i < rows * cols; i++) {
        worst = Math.max(
          worst,
          Math.abs((fh[i] as number) - (b.h[i] as number)) / hScale,
          Math.abs((fqx[i] as number) - (b.qx[i] as number)) / qScale,
          Math.abs((fqy[i] as number) - (b.qy[i] as number)) / qScale,
        );
      }
      expect(worst).toBeLessThanOrEqual(1e-3);
    });
  }

  for (const h0 of [1, 4, 16]) {
    test(`P-018-64 · @gpu h0 = ${h0} m: in a closed domain the mass drift is below 0.5 % and the dry-bed dam-break front is within 5 % of Ritter's 2 sqrt(g h0) t`, async ({
      page,
    }) => {
      await openGpuRunner(page);
      const rows = 4;
      const cols = 256;
      const dam = 96;
      const h = Array.from({ length: rows * cols }, (_, i) => (i % cols < dam ? h0 : 0));
      let s = {
        h,
        qx: new Array(rows * cols).fill(0),
        qy: new Array(rows * cols).fill(0),
        bed: new Array(rows * cols).fill(0),
      };
      const mass0 = h.reduce((a, b) => a + b, 0);
      const c0 = Math.sqrt(G * h0);
      const tEnd = Math.min(70 / (2 * c0), (dam - 10) / c0);
      let t = 0;
      while (t < tEnd) {
        const out = await step(page, rows, cols, s, { dry_depth_m: 1e-3 * h0 });
        s = { ...s, h: out.h, qx: out.qx, qy: out.qy };
        t += out.dt;
      }
      const mass = s.h.reduce((a, b) => a + b, 0);
      expect(Math.abs(mass - mass0) / mass0).toBeLessThan(0.005);
      let front = dam;
      for (let c = cols - 1; c >= dam; c--)
        if ((s.h[1 * cols + c] as number) > 0.01 * h0) {
          front = c;
          break;
        }
      const expected = 2 * c0 * t;
      expect(Math.abs(front - dam - expected)).toBeLessThanOrEqual(0.05 * expected);
    });
  }
});
