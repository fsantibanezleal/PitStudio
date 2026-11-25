// T-013-032 · FR-013-39 · hostile slider assets, out-of-range levels and corrupted replay shards.
//
// Oracle: a hostile corpus derived from the committed golden asset, one defect per case, written here (the digest in the header is recomputed with
// WebCrypto whenever the payload is edited on purpose, so that only the intended defect is present): a wrong SHA-256, an edited payload, a wrong byte
// count, NaN, infinite and negative tau, a reference-target tau of 0, more than 150,000 returns, header violations of the DC-013-05 schema, and slider
// levels outside 0..40; replay shards (DC-013-04) with a wrong digest, a schema violation, a wrong payload size and more than 1,250,000 points.
//
// Expected API:
//   module `dust-slider.ts` (see dust-slider-parity.test.ts), in addition:
//     SliderAssetError (extends Error); UNAVAILABLE_MESSAGE === "dust model unavailable — clean frame shown";
//     cleanFrame(frame: SliderFrame): Attenuated        the clean frame: every return kept, intensity = the baked clean intensity, no dust return
//     prepareSlider(header: unknown, payload: Uint8Array): Promise<{ ok: true; frame: SliderFrame } | { ok: false; message: string }>
//                                                        never throws: a rejected asset gives { ok: false, message: UNAVAILABLE_MESSAGE }
//     attenuate(frame, level)  throws RangeError for a level that is not an integer in 0..40 (NaN, +-Infinity, 41, -1, 1.5) and TypeError for a non-number
//   module `cloud-shard.ts` (the replay viewer's loader):
//     loadCloudShard(header: unknown, payload: Uint8Array): Promise<CloudShard>     validates DC-013-04 (schema, SHA-256, payload bytes = 8 x points, points <= 1,250,000,
//                                                        finite quantisation) and throws ShardError; CloudShard: { header, points: number, positions: Float32Array (3 x points,
//                                                        dequantised offset + scale x code), intensity: Uint8Array, classCode: Uint8Array }
//     prepareReplay(header: unknown, payload: Uint8Array): Promise<{ ok: true; shard: CloudShard } | { ok: false; showPoster: true }>   never throws

import { describe, expect, it } from "vitest";
import golden1 from "./__fixtures__/dust-golden-1.json";
import { loadCloudShard, prepareReplay, ShardError } from "./cloud-shard";
import {
  attenuate,
  cleanFrame,
  loadSliderAsset,
  prepareSlider,
  SliderAssetError,
  UNAVAILABLE_MESSAGE,
} from "./dust-slider";

type Payload = { path: string; bytes: number; sha256: string };
type Header = Record<string, unknown> & { payload: Payload; returns: number }; // a baked slider header (DC-013-05)
type CloudHeader = Record<string, unknown> & { payload: Payload; points: number }; // a replay shard header (DC-013-04)

const decode = (b64: string): Uint8Array => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
const clone = <T>(v: T): T => structuredClone(v);
const hex = (buf: ArrayBuffer): string =>
  Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
const sha256 = async (data: Uint8Array): Promise<string> =>
  hex(await crypto.subtle.digest("SHA-256", data as BufferSource));

const good = () => ({
  header: clone(golden1.header) as unknown as Header,
  payload: decode(golden1.payload_b64),
});

/** The header with its payload block rewritten for an edited payload (so only the intended defect remains). */
async function sealed(header: Header, payload: Uint8Array): Promise<{ header: Header; payload: Uint8Array }> {
  const h = clone(header);
  h.payload = { path: h.payload.path, bytes: payload.length, sha256: await sha256(payload) };
  return { header: h, payload };
}

/** Overwrite the float32 tau_unit of one return (the plane starts at byte 8 n). */
function withTau(payload: Uint8Array, n: number, index: number, value: number): Uint8Array {
  const out = payload.slice();
  new DataView(out.buffer).setFloat32(8 * n + 4 * index, value, true);
  return out;
}

describe("hostile slider assets", () => {
  it("FR-013-39 · the unmodified golden asset loads", async () => {
    const { header, payload } = good();
    const frame = await loadSliderAsset(header, payload);
    expect(frame.count).toBe(header.returns);
    expect((await prepareSlider(header, payload)).ok).toBe(true);
  });

  it("FR-013-39 · a wrong SHA-256, an edited payload and a wrong byte count are rejected", async () => {
    const { header, payload } = good();
    const badHash = clone(header);
    badHash.payload.sha256 = `${badHash.payload.sha256.slice(0, 63)}${badHash.payload.sha256.endsWith("0") ? "1" : "0"}`;
    await expect(loadSliderAsset(badHash, payload)).rejects.toBeInstanceOf(SliderAssetError);
    const edited = payload.slice();
    edited[5] = (edited[5] as number) ^ 0xff; // one byte flipped: the digest no longer matches
    await expect(loadSliderAsset(header, edited)).rejects.toBeInstanceOf(SliderAssetError);
    const truncated = await sealed(header, payload.slice(0, payload.length - 20));
    await expect(loadSliderAsset(truncated.header, truncated.payload)).rejects.toBeInstanceOf(
      SliderAssetError,
    ); // 20 x returns bytes expected
    const lying = clone(header);
    lying.payload.bytes += 1;
    await expect(loadSliderAsset(lying, payload)).rejects.toBeInstanceOf(SliderAssetError);
  });

  it.each([
    ["NaN", Number.NaN],
    ["+Infinity", Number.POSITIVE_INFINITY],
    ["-Infinity", Number.NEGATIVE_INFINITY],
    ["a negative value", -0.5],
    ["a tiny negative value", -1e-30],
  ])("FR-013-39 · tau_unit holding %s is rejected", async (_name, value) => {
    const { header, payload } = good();
    const s = await sealed(header, withTau(payload, header.returns, 7, value));
    await expect(loadSliderAsset(s.header, s.payload)).rejects.toBeInstanceOf(SliderAssetError);
  });

  it("FR-013-39 · a zero tau_unit is a valid return outside the dust", async () => {
    const { header, payload } = good();
    const s = await sealed(header, withTau(payload, header.returns, 7, 0));
    await expect(loadSliderAsset(s.header, s.payload)).resolves.toBeDefined();
  });

  it.each([
    ["zero", 0],
    ["negative", -1],
    ["NaN", Number.NaN],
    ["infinite", Number.POSITIVE_INFINITY],
  ])("FR-013-39 · a reference-target tau of %s is rejected", async (_name, value) => {
    const { header, payload } = good();
    const h = clone(header);
    h.tau_ref = value;
    await expect(loadSliderAsset(h, payload)).rejects.toBeInstanceOf(SliderAssetError);
  });

  it("FR-013-39 · more than 150,000 returns are rejected (150,000 are accepted)", async () => {
    const { header } = good();
    for (const [n, accepted] of [
      [150_000, true],
      [150_001, false],
    ] as const) {
      const payload = new Uint8Array(20 * n); // zero planes: tau 0, hash 0
      const s = await sealed({ ...clone(header), returns: n }, payload);
      const result = loadSliderAsset(s.header, s.payload);
      if (accepted) await expect(result).resolves.toBeDefined();
      else await expect(result).rejects.toBeInstanceOf(SliderAssetError);
    }
  });

  it("FR-013-39 · a header whose returns do not match the payload size is rejected", async () => {
    const { header, payload } = good();
    const h = clone(header);
    h.returns = header.returns + 1;
    await expect(loadSliderAsset(h, payload)).rejects.toBeInstanceOf(SliderAssetError);
  });

  it.each([
    ["levels other than 41", (h: Header) => Object.assign(h, { levels: 40 })],
    ["a k array of 40 values", (h: Header) => Object.assign(h, { k: (h.k as number[]).slice(1) })],
    [
      "a negative k",
      (h: Header) => Object.assign(h, { k: (h.k as number[]).map((v, i) => (i === 3 ? -0.1 : v)) }),
    ],
    [
      "a NaN k",
      (h: Header) => Object.assign(h, { k: (h.k as number[]).map((v, i) => (i === 3 ? Number.NaN : v)) }),
    ],
    ["another label", (h: Header) => Object.assign(h, { label: "dust model" })],
    [
      "a changed rule constant",
      (h: Header) => Object.assign(h, { rule: { ...(h.rule as object), tau_on: 0.5 } }),
    ],
    [
      "a missing material code",
      (h: Header) => Object.assign(h, { material_codes: { retro: 0, diffuse: 1 } }),
    ],
    [
      "another position encoding",
      (h: Header) => Object.assign(h, { encoding: { ...(h.encoding as object), position: "uint8" } }),
    ],
    ["an unknown key", (h: Header) => Object.assign(h, { surprise: true })],
    ["a missing source", (h: Header) => delete h.source],
    [
      "a quantisation scale of zero",
      (h: Header) => Object.assign(h, { quantisation: { offset_m: [0, 0, 0], scale_m: [0, 1, 1] } }),
    ],
  ])("FR-013-39 · a header with %s fails the schema and is rejected", async (_name, mutate) => {
    const { header, payload } = good();
    const h = clone(header);
    mutate(h);
    await expect(loadSliderAsset(h, payload)).rejects.toBeInstanceOf(SliderAssetError);
  });

  it("FR-013-39 · non-object headers and empty payloads are rejected, never thrown synchronously", async () => {
    const { payload } = good();
    for (const h of [null, undefined, 3, "x", [], {}]) {
      await expect(loadSliderAsset(h, payload)).rejects.toBeInstanceOf(SliderAssetError);
    }
    await expect(loadSliderAsset(good().header, new Uint8Array(0))).rejects.toBeInstanceOf(SliderAssetError);
  });
});

describe("slider levels", () => {
  it("FR-013-39 · levels 0 and 40 work and every other value is rejected", async () => {
    const { header, payload } = good();
    const frame = await loadSliderAsset(header, payload);
    expect(() => attenuate(frame, 0)).not.toThrow();
    expect(() => attenuate(frame, 40)).not.toThrow();
    for (const bad of [-1, 41, 1.5, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, 1e9]) {
      expect(() => attenuate(frame, bad), String(bad)).toThrow(RangeError);
    }
    expect(() => attenuate(frame, "3" as unknown as number)).toThrow(TypeError);
  });
});

describe("the panel contract: keep showing the clean frame", () => {
  it("FR-013-39 · a rejected asset gives the unavailable message and no frame", async () => {
    expect(UNAVAILABLE_MESSAGE).toBe("dust model unavailable — clean frame shown");
    const { header, payload } = good();
    const bad = clone(header);
    bad.payload.sha256 = "0".repeat(64);
    const result = await prepareSlider(bad, payload);
    expect(result).toEqual({ ok: false, message: UNAVAILABLE_MESSAGE });
    const bogus = await prepareSlider("not a header", payload);
    expect(bogus).toEqual({ ok: false, message: UNAVAILABLE_MESSAGE });
  });

  it("FR-013-39 · the clean frame keeps every return and its baked intensity and adds no dust", async () => {
    const { header, payload } = good();
    const frame = await loadSliderAsset(header, payload);
    const clean = cleanFrame(frame);
    expect(clean.kept.every((k) => k === 1)).toBe(true);
    expect(clean.dustCount).toBe(0);
    expect(Array.from(clean.display)).toEqual(Array.from(frame.intensityCode));
  });
});

// ------------------------------------------------------------------------------------------------ replay cloud shards (DC-013-04)
const cloudHeader = async (n: number, payload: Uint8Array): Promise<CloudHeader> => ({
  schema_version: "1.0",
  source: { run_id: "20261007T120000Z-b1-sensors", scenario: "S1", sensor: "rotary-64", frame: 0 },
  points: n,
  quantisation: { offset_m: [-10, -20, -1], scale_m: [20 / 65535, 40 / 65535, 5 / 65535] },
  encoding: {
    position: "uint16",
    intensity: "uint8",
    class: "uint8",
    byte_order: "little",
    layout: "planar",
  },
  intensity_map: { quantity: "lidar-intensity", low: 0, high: 1 },
  classes: { "0": "diffuse", "1": "retro", "2": "dust" },
  payload: { path: "sensors/s1/cloud-00000.bin", bytes: payload.length, sha256: await sha256(payload) },
});

function cloudPayload(n: number): Uint8Array {
  const out = new Uint8Array(8 * n);
  const v = new DataView(out.buffer);
  for (let i = 0; i < n; i++) {
    v.setUint16(2 * i, Math.floor((65535 * i) / Math.max(1, n - 1)), true); // x ramp over the box
    v.setUint16(2 * n + 2 * i, 0, true);
    v.setUint16(4 * n + 2 * i, 65535, true);
    out[6 * n + i] = i % 256;
    out[7 * n + i] = i % 3;
  }
  return out;
}

describe("hostile replay cloud shards", () => {
  it("FR-013-39 · a valid shard loads and dequantises by offset + scale x code", async () => {
    const payload = cloudPayload(5);
    const header = await cloudHeader(5, payload);
    const shard = await loadCloudShard(header, payload);
    expect(shard.points).toBe(5);
    expect(shard.positions[0]).toBeCloseTo(-10, 5);
    expect(shard.positions[12]).toBeCloseTo(10, 4); // the last x code is 65535: -10 + 20
    expect(shard.positions[1]).toBeCloseTo(-20, 5);
    expect(shard.positions[2]).toBeCloseTo(4, 4); // z code 65535: -1 + 5
    expect(Array.from(shard.classCode)).toEqual([0, 1, 2, 0, 1]);
  });

  it("FR-013-39 · a wrong digest, a schema violation or a wrong payload size is rejected and the viewer shows the poster", async () => {
    const payload = cloudPayload(5);
    const header = await cloudHeader(5, payload);
    const wrongDigest = clone(header);
    wrongDigest.payload.sha256 = "f".repeat(64);
    const badEncoding = clone(header);
    (badEncoding.encoding as Record<string, unknown>).position = "float32";
    const wrongSize = clone(header);
    wrongSize.points = 6;
    const nanScale = clone(header);
    (nanScale.quantisation as { scale_m: number[] }).scale_m[1] = Number.NaN;
    for (const h of [wrongDigest, badEncoding, wrongSize, nanScale, null, {}]) {
      await expect(loadCloudShard(h, payload)).rejects.toBeInstanceOf(ShardError);
      expect(await prepareReplay(h, payload)).toEqual({ ok: false, showPoster: true });
    }
    const edited = payload.slice();
    edited[0] = (edited[0] as number) ^ 1;
    await expect(loadCloudShard(header, edited)).rejects.toBeInstanceOf(ShardError);
  });

  it("FR-013-39 · more than 1,250,000 points are rejected (1,250,000 are accepted)", async () => {
    for (const [n, accepted] of [
      [1_250_000, true],
      [1_250_001, false],
    ] as const) {
      const payload = new Uint8Array(8 * n);
      const header = await cloudHeader(n, payload);
      const result = loadCloudShard(header, payload);
      if (accepted) await expect(result).resolves.toBeDefined();
      else await expect(result).rejects.toBeInstanceOf(ShardError);
    }
  });
});
