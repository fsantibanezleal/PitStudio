// T-018-061 [red] · FR-018-54: for every traffic golden (<= 40 vehicles, >= 600 steps at 60 Hz) the browser Rapier run produces a SHA-256 snapshot hash after
// the last step equal to the golden produced in Node with the same Rapier version and initial state, in Chromium, Firefox and WebKit. Unit half (TTC,
// near-misses): web/src/engines/traffic/t_018_061_ttc.test.ts.
//
// Runner hooks: web/e2e/support/parity.ts (`window.__pitstudio.parity.run("traffic", fixture)`). A traffic fixture (DC-018-04, class rigid-body-hash, function
// "simulate") holds `input` = the DC-018-02 simulate args (initial states as binary64 written in the file, never computed with Math.sin/cos in the browser, spec 018
// section 7.2) and `output.snapshot_sha256` = the golden hash. A ParityResult has mismatches = the number of vectors whose hash differs.
// Oracles: the golden hashes inside the fixtures (reference: Rapier 0.21 in Node, `tools/make_parity_fixtures.py` / the Node golden runner) and the size limits of FR-018-54.
import { expect, test } from "@playwright/test";
import { loadParityFixtures } from "../../src/test-support/parity-fixtures";
import { openParityRunner, runParity } from "../support/parity";

const fixtures = loadParityFixtures("traffic").filter((f) => f.function === "simulate");

test.describe("Rapier snapshot hash (FR-018-54)", () => {
  test("FR-018-54 · the traffic goldens exist: class rigid-body-hash, at most 40 vehicles and at least 600 steps of 1/60 s in every vector, each with a SHA-256 snapshot hash", () => {
    expect(fixtures.length, "a rigid-body-hash fixture for traffic.simulate exists").toBeGreaterThan(0);
    for (const fx of fixtures) {
      expect(fx.tolerance.class, fx.file).toBe("rigid-body-hash");
      expect(fx.cases.length, `${fx.file}: goldens`).toBeGreaterThan(0);
      for (const [i, v] of fx.cases.entries()) {
        const input = v.input as { vehicles: unknown[]; steps: number; step_s: number };
        expect(input.vehicles.length, `${fx.file} #${i}: vehicles`).toBeLessThanOrEqual(40);
        expect(input.steps, `${fx.file} #${i}: steps`).toBeGreaterThanOrEqual(600);
        expect(input.step_s, `${fx.file} #${i}: step`).toBeCloseTo(1 / 60, 15);
        expect(v.output.snapshot_sha256, `${fx.file} #${i}: golden hash`).toMatch(/^[0-9a-f]{64}$/);
      }
    }
  });

  for (const fx of fixtures) {
    test(`FR-018-54 · ${fx.file}: the snapshot hash after the last step equals the Node golden on all ${fx.cases.length} vectors`, async ({
      page,
    }) => {
      await openParityRunner(page);
      const r = await runParity(page, "traffic", fx);
      expect(r.vectors).toBe(fx.cases.length);
      expect(r.mismatches).toBe(0);
      expect(r.verdict).toBe("pass");
    });
  }

  test("FR-018-54 · a one-bit change of an initial speed changes the hash (the run is deterministic, not constant)", async ({
    page,
  }) => {
    await openParityRunner(page);
    const hashes = await page.evaluate(async () => {
      const p = (
        window as unknown as { __pitstudio: { parity: { trafficHash?: (v: unknown) => Promise<string> } } }
      ).__pitstudio.parity;
      if (!p.trafficHash) throw new Error("the runner has no trafficHash");
      const base = {
        vehicles: [
          { vehicle_class: "haul-truck", position_m: [0, 0], heading_rad: 0, speed_m_per_s: 10 },
          { vehicle_class: "light-vehicle", position_m: [100, 0], heading_rad: Math.PI, speed_m_per_s: 5 },
        ],
        speed_limit_m_per_s: 11,
        collision_radius_m: 4,
        steps: 600,
        step_s: 1 / 60,
        ttc_threshold_s: 3,
      };
      const nudged = structuredClone(base);
      (nudged.vehicles[0] as { speed_m_per_s: number }).speed_m_per_s = 10.000000000000002;
      return [await p.trafficHash(base), await p.trafficHash(base), await p.trafficHash(nudged)];
    });
    expect(hashes[0]).toBe(hashes[1]);
    expect(hashes[0]).not.toBe(hashes[2]);
    expect(hashes[0]).toMatch(/^[0-9a-f]{64}$/);
  });
});
