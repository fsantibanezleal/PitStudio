// @vitest-environment node
//
// T-007-064 (2/2) · the TypeScript route-energy port equals the Python golden vectors within rtol 1e-12, the hand values, the relations of P-007-19 and the hostile inputs as typed results: FR-007-34, FR-007-39, FR-007-45, P-007-19.
//
// Spec: specs/007-haulage-dispatch/spec.md FR-007-34 (wheel and source energy of every leg, regenerated energy on trolley and battery-electric descents, kWh/t, L/(t km) for diesel and kg CO2e/t with their basis), FR-007-39 (the TypeScript ports equal the Python
// implementations on the golden vectors: costs and energies within rtol 1e-12), FR-007-45 (a non-finite length, grade or mass, a length <= 0 m, a payload <= 0 t or an unknown drivetrain is rejected naming the field and value, never NaN or Infinity), P-007-19 (the
// relations), section 7 (the M06 worked example: 400 t gross, 2 km, 10 %, 3 % RR: 283.4 kWh at the wheels) and the minephys section 7.4 value (392.266 kWh for 3,000 m at 2 % RR and 10 %).
//
// Oracle: tests/fixtures/haulage/routing/energy_goldens.json (25 cases from the test author's plain-Python per-segment oracle with explicit constants: the hand cases, the three drivetrains, both legs, the exact and small-angle grade forms and 18 random routes of up to 199
// segments); the hand values above; relations checked on pseudo-random routes (mulberry32) with the tolerances of P-007-19.
//
// Expected API (module `~/engines/haulage/energy`), the same snake_case names as the Python engine; the browser has no knowledge-table access, so `constants` is required (the precomputed bundle supplies it):
//   type Segment = { length_m: number; grade_pct: number; rr_pct: number; trolley: boolean }
//   type Truck = { empty_mass_t: number; payload_t: number; drivetrain: "diesel" | "trolley" | "bev" }
//   type Constants = { g: number; eta_diesel: number; eta_electric: number; eta_drive: number; eta_regen: number; fuel_energy_density_j_per_m3: number; diesel_co2_kg_per_m3: number }
//   type Basis = { payload_t: number; road_km: number }
//   routeEnergy(input: { route: Segment[]; truck: Truck; leg: "loaded" | "empty"; constants: Constants; small_angle?: boolean /* default true */; grid_intensity_kg_per_j?: number | null }):
//     | { ok: true; value: { leg; mass_t; payload_t; road_km; wheel_kwh; diesel_kwh; electric_kwh; regen_kwh; source_kwh; kwh_per_t: { value: number; basis: Basis }; diesel_l_per_t_km: { value: number | null; basis: Basis }; co2e_kg_per_t: { value: number | null; basis: Basis }; co2e_note: string | null } }
//     | { ok: false; kind: "InvalidRouteInput"; field: string; value: unknown }
//   The formulas are those of `pitstudio.haulage.energy.route_energy` (see tests/unit/test_t_007_062_route_energy.py); `diesel_l_per_t_km.value` is null for bev, `co2e_kg_per_t.value` is null (with a note) when electricity needs a grid intensity that was not supplied.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { routeEnergy, type Segment } from "~/engines/haulage/energy";

const REPO = resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../..");
// biome-ignore lint/suspicious/noExplicitAny: golden JSON
type Json = Record<string, any>;
const GOLD = (
  JSON.parse(readFileSync(resolve(REPO, "tests/fixtures/haulage/routing/energy_goldens.json"), "utf-8")) as {
    cases: Json[];
  }
).cases;

const KWH = 3.6e6;
const G0 = 9.80665;
const C = {
  g: G0,
  eta_diesel: 0.35,
  eta_electric: 0.9,
  eta_drive: 0.92,
  eta_regen: 0.6,
  fuel_energy_density_j_per_m3: 36e9,
  diesel_co2_kg_per_m3: 10.21 / 3.785411784e-3,
};
const seg = (length_m = 1000, grade_pct = 0, rr_pct = 3, trolley = false): Segment => ({
  length_m,
  grade_pct,
  rr_pct,
  trolley,
});
const TRUCK = { empty_mass_t: 180, payload_t: 220, drivetrain: "diesel" as const };
type Dt = "diesel" | "trolley" | "bev";
const run = (
  route: Segment[],
  drivetrain: Dt = "diesel",
  leg: "loaded" | "empty" = "loaded",
  extra: Json = {},
) => routeEnergy({ route, truck: { ...TRUCK, drivetrain }, leg, constants: C, ...extra });
const ok = (r: ReturnType<typeof routeEnergy>) => {
  expect(r.ok).toBe(true);
  if (!r.ok) throw new Error("not ok");
  return r.value;
};
const near = (a: number, b: number, rtol = 1e-12, atol = 1e-12) =>
  Math.abs(a - b) <= atol + rtol * Math.abs(b);

describe("FR-007-39 · the Python goldens", () => {
  for (const c of GOLD) {
    it(`FR-007-39 · ${c.id}: every figure within rtol 1e-12`, () => {
      const v = ok(
        routeEnergy({
          route: c.route,
          truck: c.truck,
          leg: c.leg,
          constants: c.constants,
          small_angle: c.small_angle,
          grid_intensity_kg_per_j: c.grid_intensity_kg_per_j,
        }),
      );
      const e = c.expected as Json;
      for (const k of [
        "mass_t",
        "road_km",
        "wheel_kwh",
        "diesel_kwh",
        "electric_kwh",
        "regen_kwh",
        "source_kwh",
      ] as const) {
        expect(near(v[k] as number, e[k] as number), `${k}: ${v[k]} vs ${e[k]}`).toBe(true);
      }
      expect(near(v.kwh_per_t.value, e.kwh_per_t)).toBe(true);
      expect(v.kwh_per_t.basis).toEqual({ payload_t: c.truck.payload_t, road_km: e.road_km });
      if (e.diesel_l_per_t_km === null) expect(v.diesel_l_per_t_km.value).toBeNull();
      else expect(near(v.diesel_l_per_t_km.value as number, e.diesel_l_per_t_km)).toBe(true);
      if (e.co2e_kg_per_t === null) {
        expect(v.co2e_kg_per_t.value).toBeNull();
        expect(typeof v.co2e_note).toBe("string");
      } else {
        expect(near(v.co2e_kg_per_t.value as number, e.co2e_kg_per_t)).toBe(true);
        expect(v.co2e_note).toBeNull();
      }
    });
  }
});

describe("FR-007-34 · hand values", () => {
  it("FR-007-34 · the M06 worked example: 400 t on 2 km at 10 % with 3 % RR is 283.4 kWh at the wheels (g = 9.80665 gives 283.3)", () => {
    const v = ok(run([seg(2000, 10, 3)]));
    expect(v.mass_t).toBe(400);
    expect(Math.abs(v.wheel_kwh - 283.4) / 283.4).toBeLessThan(1e-3);
    expect(near(v.wheel_kwh, (400000 * G0 * 0.13 * 2000) / KWH)).toBe(true);
    expect(v.wheel_kwh).toBeGreaterThanOrEqual((400000 * G0 * 200) / KWH); // the lift floor
  });
  it("FR-007-34 · minephys section 7.4: 3,000 m at 2 % RR and 10 % is 392.266 kWh at the wheels, 0.112076 m3 of fuel at eta 0.35", () => {
    const v = ok(run([seg(3000, 10, 2)]));
    expect(Math.abs(v.wheel_kwh - 392.266) / 392.266).toBeLessThan(1e-6);
    expect(Math.abs((v.diesel_kwh * KWH) / 36e9 - 0.112076) / 0.112076).toBeLessThan(1e-6);
    expect(v.diesel_l_per_t_km.basis).toEqual({ payload_t: 220, road_km: 3 });
    expect(Math.abs((v.co2e_kg_per_t.value as number) * 220 - 302.291) / 302.291).toBeLessThan(1e-5);
  });
  it("FR-007-34 · the empty leg carries the empty mass only; the basis stays the payload", () => {
    const v = ok(run([seg(1000, 5, 3)], "diesel", "empty"));
    expect(v.mass_t).toBe(180);
    expect(near(v.wheel_kwh, (180000 * G0 * 0.08 * 1000) / KWH)).toBe(true);
    expect(v.kwh_per_t.basis).toEqual({ payload_t: 220, road_km: 1 });
  });
  it("FR-007-34 · a battery truck regenerates on descents and a trolley truck draws nothing on them", () => {
    const route = [seg(2000, 8, 2), seg(3000, -10, 2)];
    const bev = ok(run(route, "bev"));
    const m = 400000;
    const regen = 0.6 * m * G0 * (0.1 - 0.02) * 3000;
    expect(near(bev.regen_kwh, regen / KWH)).toBe(true);
    expect(bev.diesel_kwh).toBe(0);
    const tr = ok(run([seg(1500, -9, 2, true)], "trolley"));
    expect(tr.diesel_kwh).toBe(0);
    expect(tr.electric_kwh).toBe(0);
    expect(tr.regen_kwh).toBe(0);
  });
});

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const randomRoute = (rnd: () => number, n: number): Segment[] =>
  Array.from({ length: n }, () => seg(5 + rnd() * 2995, -20 + rnd() * 40, 0.5 + rnd() * 9.5, rnd() < 0.4));
const DTS: Dt[] = ["diesel", "trolley", "bev"];

describe("P-007-19 · relations on random routes", () => {
  it("P-007-19 · additive over concatenated routes (every drivetrain, both legs)", () => {
    const rnd = mulberry32(19);
    for (let i = 0; i < 60; i++) {
      const a = randomRoute(rnd, 1 + Math.floor(rnd() * 100));
      const b = randomRoute(rnd, 1 + Math.floor(rnd() * 100));
      const dt = DTS[i % 3] as Dt;
      const leg = i % 2 ? "loaded" : "empty";
      const whole = ok(run([...a, ...b], dt, leg));
      const ra = ok(run(a, dt, leg));
      const rb = ok(run(b, dt, leg));
      for (const k of [
        "wheel_kwh",
        "diesel_kwh",
        "electric_kwh",
        "regen_kwh",
        "source_kwh",
        "road_km",
      ] as const) {
        const tol = 1e-12 * (Math.abs(ra[k]) + Math.abs(rb[k]) + 1e-9);
        expect(Math.abs(whole[k] - (ra[k] + rb[k]))).toBeLessThanOrEqual(tol);
      }
    }
  });
  it("P-007-19 · non-decreasing in grade and rolling resistance; in payload for diesel and trolley", () => {
    const rnd = mulberry32(20);
    for (let i = 0; i < 60; i++) {
      const route = randomRoute(rnd, 1 + Math.floor(rnd() * 80));
      const dt = DTS[i % 3] as Dt;
      const base = ok(run(route, dt)).source_kwh;
      const bump = rnd() * 5;
      const steeper = route.map((s, k) => (k === 0 ? { ...s, grade_pct: s.grade_pct + bump } : s));
      const rougher = route.map((s) => ({ ...s, rr_pct: s.rr_pct + bump }));
      const slack = 1e-12 * (Math.abs(base) + 1);
      expect(ok(run(steeper, dt)).source_kwh).toBeGreaterThanOrEqual(base - slack);
      expect(ok(run(rougher, dt)).source_kwh).toBeGreaterThanOrEqual(base - slack);
      if (dt !== "bev") {
        const heavier = routeEnergy({
          route,
          truck: { ...TRUCK, drivetrain: dt, payload_t: 220 + bump },
          leg: "loaded",
          constants: C,
        });
        expect(ok(heavier).source_kwh).toBeGreaterThanOrEqual(base - slack);
      }
    }
  });
  it("P-007-19 · the wheel energy of any route is at least the potential energy gained", () => {
    const rnd = mulberry32(21);
    for (let i = 0; i < 60; i++) {
      const route = randomRoute(rnd, 1 + Math.floor(rnd() * 100));
      const v = ok(run(route, DTS[i % 3] as Dt, i % 2 ? "loaded" : "empty"));
      const dz = route.reduce((s, x) => s + (x.length_m * x.grade_pct) / 100, 0);
      const floor = (v.mass_t * 1000 * G0 * dz) / KWH;
      expect(v.wheel_kwh).toBeGreaterThanOrEqual(
        floor - 1e-12 * (Math.abs(floor) + Math.abs(v.wheel_kwh) + 1e-9),
      );
    }
  });
  it("P-007-19 · a trolley route with no trolley length equals diesel; CO2 is linear in the factor", () => {
    const rnd = mulberry32(22);
    for (let i = 0; i < 30; i++) {
      const route = randomRoute(rnd, 1 + Math.floor(rnd() * 60)).map((s) => ({ ...s, trolley: false }));
      const d = ok(run(route, "diesel"));
      const t = ok(run(route, "trolley"));
      for (const k of ["wheel_kwh", "diesel_kwh", "electric_kwh", "source_kwh"] as const)
        expect(near(t[k], d[k])).toBe(true);
      const k2 = 0.5 + rnd() * 1.5;
      const scaled = routeEnergy({
        route,
        truck: TRUCK,
        leg: "loaded",
        constants: { ...C, diesel_co2_kg_per_m3: k2 * C.diesel_co2_kg_per_m3 },
      });
      expect(near(ok(scaled).co2e_kg_per_t.value as number, k2 * (d.co2e_kg_per_t.value as number))).toBe(
        true,
      );
    }
  });
  it("P-007-19 · the regenerated energy of a battery truck is the descent potential times the regeneration efficiency", () => {
    const rnd = mulberry32(23);
    for (let i = 0; i < 40; i++) {
      const route = randomRoute(rnd, 1 + Math.floor(rnd() * 100));
      const v = ok(run(route, "bev"));
      const m = v.mass_t * 1000;
      let bound = 0;
      for (const s of route) {
        const f = -s.grade_pct / 100 - s.rr_pct / 100;
        if (f > 0) bound += 0.6 * m * G0 * f * s.length_m;
      }
      expect(near(v.regen_kwh, bound / KWH)).toBe(true);
    }
  });
  it("P-007-19 · on a flat road the way there costs the same as the way back", () => {
    const rnd = mulberry32(24);
    for (let i = 0; i < 30; i++) {
      const route = randomRoute(rnd, 1 + Math.floor(rnd() * 40)).map((s) => ({ ...s, grade_pct: 0 }));
      const back = [...route].reverse();
      const a = ok(run(route, DTS[i % 3] as Dt));
      const b = ok(run(back, DTS[i % 3] as Dt));
      for (const k of ["wheel_kwh", "diesel_kwh", "electric_kwh", "source_kwh"] as const)
        expect(near(a[k], b[k])).toBe(true);
    }
  });
});

describe("FR-007-45 · hostile inputs are typed results and never NaN or Infinity", () => {
  const bad = [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY];
  const reject = (input: Json, field: string) => {
    const r = routeEnergy({ route: [seg()], truck: TRUCK, leg: "loaded", constants: C, ...input } as never);
    expect(r).toMatchObject({ ok: false, kind: "InvalidRouteInput", field });
  };
  for (const v of [...bad, 0, -1, -1e-9]) {
    it(`FR-007-45 · a length of ${String(v)} names length_m`, () =>
      reject({ route: [seg(), seg(v)] }, "length_m"));
  }
  for (const v of bad) {
    it(`FR-007-45 · a grade or rolling resistance of ${String(v)} is rejected`, () => {
      reject({ route: [seg(1000, v)] }, "grade_pct");
      reject({ route: [seg(1000, 0, v)] }, "rr_pct");
    });
  }
  it("FR-007-45 · a negative rolling resistance is rejected", () =>
    reject({ route: [seg(1000, 0, -0.5)] }, "rr_pct"));
  for (const f of ["empty_mass_t", "payload_t"] as const) {
    for (const v of [...bad, 0, -1]) {
      it(`FR-007-45 · ${f} = ${String(v)} is rejected`, () => reject({ truck: { ...TRUCK, [f]: v } }, f));
    }
  }
  for (const d of ["", "Diesel", "electric", "hybrid", "bev ", "ディーゼル", null, 3]) {
    it(`FR-007-45 · the drivetrain ${JSON.stringify(d)} is unknown`, () =>
      reject({ truck: { ...TRUCK, drivetrain: d } }, "drivetrain"));
  }
  for (const leg of ["", "Loaded", "both", null, 1]) {
    it(`FR-007-45 · the leg ${JSON.stringify(leg)} is unknown`, () => reject({ leg }, "leg"));
  }
  const routes: [unknown, string][] = [
    [[], "route"],
    [null, "route"],
    ["segment", "route"],
    [[{ length_m: 1, grade_pct: 0, rr_pct: 1 }], "trolley"],
    [[{ grade_pct: 0, rr_pct: 1, trolley: false }], "length_m"],
    [[seg(1000, 0, 3, 1 as unknown as boolean)], "trolley"],
    [[seg("100" as unknown as number)], "length_m"],
    [[null], "route"],
  ];
  for (const [route, field] of routes) {
    it(`FR-007-45 · a malformed route ${JSON.stringify(route)} names ${field}`, () =>
      reject({ route }, field));
  }
  it("FR-007-45 · more than 100,000 segments are rejected", () => {
    reject({ route: new Array(100_001).fill(seg()) }, "route");
    expect(
      routeEnergy({ route: new Array(100_000).fill(seg()), truck: TRUCK, leg: "loaded", constants: C }).ok,
    ).toBe(true);
  });
  it("FR-007-45 · an overflow is an error, never Infinity", () => {
    const r = routeEnergy({
      route: [seg(1e308, 20), seg(1e308, 20)],
      truck: TRUCK,
      leg: "loaded",
      constants: C,
    });
    if (r.ok) {
      for (const x of [r.value.wheel_kwh, r.value.diesel_kwh, r.value.source_kwh])
        expect(Number.isFinite(x)).toBe(true);
    } else {
      expect(r.kind).toBe("InvalidRouteInput");
    }
  });
  const consts: [string, number][] = [
    ["g", 0],
    ["g", Number.NaN],
    ["eta_diesel", 0],
    ["eta_diesel", 1.5],
    ["eta_regen", -0.1],
    ["eta_regen", 1.1],
    ["fuel_energy_density_j_per_m3", 0],
    ["diesel_co2_kg_per_m3", -1],
    ["eta_drive", Number.POSITIVE_INFINITY],
  ];
  for (const [k, v] of consts) {
    it(`FR-007-45 · the constant ${k} = ${String(v)} is rejected naming it`, () =>
      reject({ constants: { ...C, [k]: v } }, k));
  }
  it("FR-007-45 · missing constants are rejected (the browser has no knowledge tables to fall back on)", () => {
    reject({ constants: undefined }, "constants");
    reject({ constants: { g: G0 } }, "eta_diesel");
  });
  it("FR-007-45 · a rejected input leaves the route untouched", () => {
    const route = [seg(), seg(-5)];
    const snap = JSON.stringify(route);
    routeEnergy({ route, truck: TRUCK, leg: "loaded", constants: C });
    expect(JSON.stringify(route)).toBe(snap);
  });
});
