// T-014-053 [red] · FR-014-44: hostile twin inputs and a corrupted ONNX hash.
//
// Spec: specs/014-robot-learning/spec.md FR-014-44: "If a visitor sets a twin input (payload, light-vehicle speed, soil cohesion or friction angle) to a
// non-finite or out-of-range value, then the panel shall clamp it to its randomisation range and show 'clamped to the training range'; and if the ONNX
// file fails its SHA-256, then the panel shall not load it and shall show the replay." FR-014-43: the panel falls back to the replay when ORT-web cannot
// initialise (FR-000-02). Ranges (FR-014-13, FR-014-19, twin bundle `input_ranges`): payload fraction [0, 1], light-vehicle speed [20, 40] km/h,
// cohesion [0, 20] kPa, friction angle [25, 40] deg.
//
// Oracle: the ranges of the requirement (hand-written); the SHA-256 of fixed byte strings (published vectors: "abc" -> ba7816bf...15ad, FIPS 180-2 appendix B.1,
// and the empty message -> e3b0c442...b855); an injected session factory that records whether it was called, so that "the panel shall not load it" is an observable.
//
// Expected API of the implementation (web/src/engines/robots/):
//   inputs.ts   export type TwinInput = "payload_fraction" | "light_vehicle_speed_km_h" | "cohesion_kpa" | "friction_angle_deg";
//               export const TWIN_INPUT_RANGES: Record<TwinInput, readonly [number, number]>;
//               export const CLAMP_MESSAGE = "clamped to the training range";
//               clampTwinInput(kind: TwinInput, raw: unknown): { value: number; clamped: boolean; message: string | null }
//                 raw a finite number in range: unchanged, clamped false, message null; a finite number outside: the nearest bound, clamped true, message CLAMP_MESSAGE;
//                 +Infinity the upper bound, -Infinity the lower bound; NaN, null, undefined, booleans, objects, arrays and non-numeric text: the midpoint of the range
//                 (a defined value, see the red report), clamped true, message CLAMP_MESSAGE; a string is trimmed and parsed with Number() (so "30" is 30, "" is not a number).
//   policy.ts   sha256Hex(bytes: Uint8Array): Promise<string>;
//               loadPolicy(bytes: Uint8Array, expectedSha256: string, createSession: (bytes: Uint8Array) => Promise<unknown>)
//                 : Promise<{ kind: "live"; session: unknown } | { kind: "replay"; reason: "sha256" | "ort-init" | "invalid-digest"; message: string }>
//                 a digest mismatch (or an expected digest that is not 64 lower-case hex characters) gives the replay WITHOUT calling createSession; a createSession that rejects gives the replay
//                 with reason "ort-init"; otherwise live with the created session.
//   bicycle.ts / arm.ts  bicycleStep and armStep throw an Error naming the offending input (`state`, `steerRateCmd`, `driveCmd`, `dt`; `q`, `vFill`, `heights`, `action`, `dt`) for non-finite values.
import { describe, expect, it, vi } from "vitest";
import { armParamsFromTwin, armStep } from "./arm";
import { bicycleParamsFromTwin, bicycleStep } from "./bicycle";
import { CLAMP_MESSAGE, clampTwinInput, TWIN_INPUT_RANGES, type TwinInput } from "./inputs";
import { loadPolicy, sha256Hex } from "./policy";

const enc = (s: string) => new TextEncoder().encode(s);
const ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
const EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

const KINDS: [TwinInput, number, number][] = [
  ["payload_fraction", 0, 1],
  ["light_vehicle_speed_km_h", 20, 40],
  ["cohesion_kpa", 0, 20],
  ["friction_angle_deg", 25, 40],
];

describe("FR-014-44 · the randomisation ranges", () => {
  it("FR-014-44 · TWIN_INPUT_RANGES and the message are the ones of the requirement", () => {
    for (const [kind, lo, hi] of KINDS) expect(TWIN_INPUT_RANGES[kind]).toEqual([lo, hi]);
    expect(CLAMP_MESSAGE).toBe("clamped to the training range");
  });
});

describe.each(KINDS)("FR-014-44 · clamping %s to [%d, %d]", (kind, lo, hi) => {
  const mid = (lo + hi) / 2;

  it("FR-014-44 · an in-range value is left alone, bounds included", () => {
    for (const v of [lo, mid, hi, lo + 1e-9 * (hi - lo)]) {
      expect(clampTwinInput(kind, v)).toEqual({ value: v, clamped: false, message: null });
    }
  });

  it("FR-014-44 · an out-of-range finite value is clamped to the nearest bound with the message", () => {
    expect(clampTwinInput(kind, hi + 1)).toEqual({ value: hi, clamped: true, message: CLAMP_MESSAGE });
    expect(clampTwinInput(kind, lo - 1)).toEqual({ value: lo, clamped: true, message: CLAMP_MESSAGE });
    expect(clampTwinInput(kind, 1e308)).toEqual({ value: hi, clamped: true, message: CLAMP_MESSAGE });
    expect(clampTwinInput(kind, -1e308)).toEqual({ value: lo, clamped: true, message: CLAMP_MESSAGE });
  });

  it("FR-014-44 · infinities go to the matching bound", () => {
    expect(clampTwinInput(kind, Number.POSITIVE_INFINITY)).toEqual({
      value: hi,
      clamped: true,
      message: CLAMP_MESSAGE,
    });
    expect(clampTwinInput(kind, Number.NEGATIVE_INFINITY)).toEqual({
      value: lo,
      clamped: true,
      message: CLAMP_MESSAGE,
    });
  });

  it("FR-014-44 · NaN and non-numeric input fall to the midpoint with the message", () => {
    for (const raw of [
      Number.NaN,
      null,
      undefined,
      true,
      false,
      {},
      [],
      [5],
      "abc",
      "",
      "   ",
      "1e999x",
      "NaN",
      "中文",
      "\u0000",
    ]) {
      expect(clampTwinInput(kind, raw)).toEqual({ value: mid, clamped: true, message: CLAMP_MESSAGE });
    }
  });

  it("FR-014-44 · numeric text is parsed after trimming", () => {
    expect(clampTwinInput(kind, ` ${mid} `)).toEqual({ value: mid, clamped: false, message: null });
    expect(clampTwinInput(kind, `${hi + 5}`)).toEqual({ value: hi, clamped: true, message: CLAMP_MESSAGE });
    expect(clampTwinInput(kind, "-Infinity")).toEqual({ value: lo, clamped: true, message: CLAMP_MESSAGE });
  });

  it("FR-014-44 · the result is always inside the range and finite, whatever the input", () => {
    const hostile: unknown[] = [
      0,
      -0,
      1e-320,
      5e-324,
      1.7976931348623157e308,
      -1.7976931348623157e308,
      12345.678,
      -12345.678,
      "7",
      "7e1",
      "0x10",
    ];
    for (const raw of hostile) {
      const r = clampTwinInput(kind, raw);
      expect(Number.isFinite(r.value)).toBe(true);
      expect(r.value).toBeGreaterThanOrEqual(lo);
      expect(r.value).toBeLessThanOrEqual(hi);
      expect(r.clamped).toBe(r.message !== null);
    }
  });
});

describe("FR-014-44 · the SHA-256 of the ONNX file", () => {
  it("FR-014-44 · sha256Hex reproduces the published vectors", async () => {
    expect(await sha256Hex(enc("abc"))).toBe(ABC);
    expect(await sha256Hex(new Uint8Array(0))).toBe(EMPTY);
  });

  it("FR-014-44 · a matching digest loads the policy live", async () => {
    const create = vi.fn(async (b: Uint8Array) => ({ session: b.length }));
    const r = await loadPolicy(enc("abc"), ABC, create);
    expect(r.kind).toBe("live");
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("FR-014-44 · a corrupted file is not loaded and the replay is shown", async () => {
    const create = vi.fn(async () => ({}));
    const corrupted = enc("abd"); // one byte changed
    const r = await loadPolicy(corrupted, ABC, create);
    expect(r.kind).toBe("replay");
    if (r.kind === "replay") {
      expect(r.reason).toBe("sha256");
      expect(r.message).toMatch(/SHA-256/);
    }
    expect(create).not.toHaveBeenCalled(); // the session factory never saw the bytes
  });

  it("FR-014-44 · an empty or truncated file fails the digest too", async () => {
    const create = vi.fn(async () => ({}));
    expect((await loadPolicy(new Uint8Array(0), ABC, create)).kind).toBe("replay");
    expect((await loadPolicy(enc("ab"), ABC, create)).kind).toBe("replay");
    expect(create).not.toHaveBeenCalled();
  });

  it("FR-014-44 · an expected digest that is not 64 lower-case hex characters is refused without loading", async () => {
    const create = vi.fn(async () => ({}));
    for (const bad of [
      "",
      "abc",
      ABC.toUpperCase(),
      `${ABC}0`,
      ABC.slice(1),
      "g".repeat(64),
      "中".repeat(64),
    ]) {
      const r = await loadPolicy(enc("abc"), bad, create);
      expect(r.kind).toBe("replay");
      if (r.kind === "replay") expect(["invalid-digest", "sha256"]).toContain(r.reason);
    }
    expect(create).not.toHaveBeenCalled();
  });

  it("FR-014-44 · when ORT-web cannot initialise the panel falls back to the replay", async () => {
    const create = vi.fn(async () => {
      throw new Error("WebAssembly.instantiate failed");
    });
    const r = await loadPolicy(enc("abc"), ABC, create);
    expect(r.kind).toBe("replay");
    if (r.kind === "replay") expect(r.reason).toBe("ort-init");
  });
});

describe("FR-014-44 · the twins reject non-finite inputs", () => {
  const BP = bicycleParamsFromTwin({
    machine: "m",
    mass_kg: 160000,
    rated_payload_kg: 220000,
    yaw_inertia_kg_m2: 1800000,
    cg_to_front_axle_m: 2.6,
    cg_to_rear_axle_m: 2.7,
    cornering_stiffness_front_n_per_rad: 900000,
    cornering_stiffness_rear_n_per_rad: 1800000,
    max_steer_deg: 38,
    max_steer_rate_deg_per_s: 20,
    envelope: [
      { speed_m_per_s: 0, rimpull_n: 900000, retarder_n: 0 },
      { speed_m_per_s: 3, rimpull_n: 800000, retarder_n: 1100000 },
    ],
    dt_s: 0.01,
    kinematic_below_m_per_s: 1,
    substeps: 5,
  });
  const STATE = [0, 0, 0, 8, 0, 0, 0];

  it("FR-014-44 · bicycleStep names the offending input", () => {
    for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
      expect(() => bicycleStep([0, 0, 0, bad, 0, 0, 0], 0, 0.1, BP)).toThrow(/state/);
      expect(() => bicycleStep(STATE, bad, 0.1, BP)).toThrow(/steerRateCmd/);
      expect(() => bicycleStep(STATE, 0, bad, BP)).toThrow(/driveCmd/);
      expect(() => bicycleStep(STATE, 0, 0.1, BP, undefined, bad)).toThrow(/dt/);
    }
    expect(() => bicycleStep(STATE, 0, 0.1, BP, undefined, 0)).toThrow(/dt/);
    expect(() => bicycleStep(STATE, 0, 0.1, BP, undefined, -0.01)).toThrow(/dt/);
    expect(() => bicycleStep([0, 0, 0], 0, 0.1, BP)).toThrow(/state/);
  });

  it("FR-014-44 · armStep names the offending input", () => {
    const AP = armParamsFromTwin({
      machine: "m",
      boom_pivot_m: [0.2, 2.0],
      links: { boom: { length_m: 6 }, stick: { length_m: 3 }, bucket: { length_m: 1.5 } },
      joints: {
        boom: { lower_deg: -40, upper_deg: 60, torque_max_n_m: 400000, velocity_max_deg_per_s: 30 },
        stick: { lower_deg: -150, upper_deg: -30, torque_max_n_m: 250000, velocity_max_deg_per_s: 40 },
        bucket: { lower_deg: -170, upper_deg: 40, torque_max_n_m: 120000, velocity_max_deg_per_s: 60 },
      },
      bucket_width_m: 1.2,
      heaped_volume_m3: 1.5,
      fill_cap: 1.15,
      gravity_m_per_s2: 9.81,
      dt_s: 0.01,
    });
    const soil = { rho: 1800, c: 0, cA: 0, phi: 0.61, delta: 0.35, q: 0 };
    const q = [0, -1.5, 0];
    const h = new Array(60).fill(-2);
    for (const bad of [Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(() => armStep([bad, -1.5, 0], 0, h, [0, 0, 1, 0], AP, soil)).toThrow(/\bq\b/);
      expect(() => armStep(q, bad, h, [0, 0, 1, 0], AP, soil)).toThrow(/vFill/);
      expect(() => armStep(q, 0, [bad, ...h], [0, 0, 1, 0], AP, soil)).toThrow(/heights/);
      expect(() => armStep(q, 0, h, [0, 0, bad, 0], AP, soil)).toThrow(/action/);
    }
    expect(() => armStep(q, 0, h, [0, 0, 1], AP, soil)).toThrow(/action/);
  });
});
