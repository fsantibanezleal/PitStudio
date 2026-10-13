// @vitest-environment node
//
// T-007-012 (2/3) · TypeScript variates, bit-equal to the Python fixtures: FR-007-05, FR-007-06, FR-007-07, P-007-04.
//
// Spec: specs/007-haulage-dispatch/spec.md FR-007-05 and FR-007-06 (variates only from integer operations, the IEEE basic operations and linear interpolation in quantile tables carried in the
// bundle: uniform (x >> 11) * 2^-53, normal, unit-mean lognormal, exponential, bounded integers; identical in Python and TypeScript), FR-007-07 (profiles `exponential` and `deterministic`),
// section 7 (tables: 2^12 bins, the top 12 bits of a word choose the bin and the next 52 bits the position inside it, linear interpolation; 4,097 float64 knots little-endian in base64 with the
// SHA-256 of the decoded bytes) and P-007-04 (for any seed and purpose the first 10^4 variates of every family are equal in Python and TypeScript, by bit pattern).
//
// Oracle: (1) the Python variate source's output committed in tests/fixtures/haulage/variate_vectors.json (the Python module is the reference of the twin; its generator is checked against the
// Random123 vectors and numpy in tests/pipeline/test_t_007_010_philox.py and test_t_007_011_variates.py); (2) the spec's own exponential table in the contract example; (3) the interpolation
// formula lerp(a, b, t) = a + t * (b - a) written out here with BigInt words; (4) the profile rules of FR-007-07.
//
// Expected fixture `tests/fixtures/haulage/variate_vectors.json` (written by `tools/make_variate_vectors.py`):
//   { "tables": { "normal": <entry>, "lognormal-0.18": <entry>, "exponential": <entry> },     entries as in the bundle schema (family, [sigma], bins, encoding, knots_f64le_b64, knots_sha256)
//     "vectors": [ { "seed": "<decimal>", "purpose": str, "family": "uniform" | "normal" | "lognormal-unit-mean" | "exponential" | "integers", "params": {...},
//                    "count": 10000, "f64le_b64": "<base64 of the little-endian float64 draws>" }, ... ] }
//   params: uniform {lo, hi}, normal {loc, scale}, lognormal-unit-mean {sigma}, exponential {scale}, integers {lo, hi} (draws stored as float64). Profile `engine`.
// Expected API (module `~/engines/random/variates`; errors in `~/engines/des/errors`):
//   tableKey(family: string, sigma?: number): string         family, or `${family}:${sigma}`
//   decodeTable(entry: TableEntry): Float64Array              checks bins 4096, encoding, 4,097 knots, SHA-256 of the decoded bytes, finite and non-decreasing; throws InvalidScenario
//   lerpTable(knots: Float64Array, word: bigint): number      knots[i] + t * (knots[i + 1] - knots[i]), i = word >> 52, t = (word & (2^52 - 1)) * 2^-52
//   class VariateSource { constructor(seed: bigint, options?: { profile?: "engine" | "exponential" | "deterministic"; tables?: Map<string, Float64Array> | null });
//     profile; uniform(purpose, lo, hi); normal(purpose, loc, scale); lognormalUnitMean(purpose, sigma); exponential(purpose, scale); integers(purpose, lo, hi) }
//   with the semantics of tests/pipeline/test_t_007_011_variates.py: `tables: null` or absent is not allowed to build tables (the twin has no table builder: a missing table throws InvalidScenario).
//   errors: `InvalidScenario` (attribute `violations: {path: string; value: unknown; rule: string}[]`).

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { InvalidScenario } from "~/engines/des/errors";
import { PhiloxStream, streamKey } from "~/engines/random/philox";
import { decodeTable, lerpTable, tableKey, VariateSource } from "~/engines/random/variates";

const REPO = resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../..");
const readJson = (p: string) => JSON.parse(readFileSync(resolve(REPO, p), "utf-8"));
const M52 = (1n << 52n) - 1n;

type Entry = {
  family: string;
  sigma?: number;
  bins: number;
  encoding: string;
  knots_f64le_b64: string;
  knots_sha256: string;
};
const exampleTable = (): Entry =>
  readJson("specs/007-haulage-dispatch/contracts/examples/haul-scenario.valid-exponential.json")
    .quantile_tables[0];
const fixture = () =>
  readJson("tests/fixtures/haulage/variate_vectors.json") as {
    tables: Record<string, Entry>;
    vectors: {
      seed: string;
      purpose: string;
      family: string;
      params: Record<string, number>;
      count: number;
      f64le_b64: string;
    }[];
  };

function tablesFrom(f: ReturnType<typeof fixture>): Map<string, Float64Array> {
  const m = new Map<string, Float64Array>();
  for (const e of Object.values(f.tables)) m.set(tableKey(e.family, e.sigma), decodeTable(e));
  return m;
}

describe("quantile tables", () => {
  it("FR-007-06 · tableKey names a family and an optional sigma", () => {
    expect(tableKey("normal")).toBe("normal");
    expect(tableKey("lognormal-unit-mean", 0.18)).toBe("lognormal-unit-mean:0.18");
  });

  it("FR-007-06 · the spec's exponential table decodes to 4,097 non-decreasing knots whose SHA-256 matches", () => {
    const e = exampleTable();
    const k = decodeTable(e);
    expect(k.length).toBe(4097);
    expect(createHash("sha256").update(Buffer.from(e.knots_f64le_b64, "base64")).digest("hex")).toBe(
      e.knots_sha256,
    );
    for (let i = 1; i < k.length; i++) expect(k[i] as number).toBeGreaterThanOrEqual(k[i - 1] as number);
    expect(k[0] as number).toBeGreaterThanOrEqual(0);
  });

  it("FR-007-06 · lerpTable takes the bin from the top 12 bits and the position from the next 52", () => {
    const k = decodeTable(exampleTable());
    const words = [
      0n,
      1n,
      M52,
      1n << 52n,
      (0xabcn << 52n) | 0x123456789abcdn,
      (1n << 64n) - 1n,
      0x800n << 52n,
      4095n << 52n,
    ];
    for (const w of words) {
      const i = Number(w >> 52n);
      const t = Number(w & M52) * 2 ** -52;
      const a = k[i] as number;
      const b = k[i + 1] as number;
      expect(Object.is(lerpTable(k, w), a + t * (b - a))).toBe(true);
    }
  });

  it("FR-007-06 · damaged tables are rejected with InvalidScenario", () => {
    const good = exampleTable();
    const raw = Buffer.from(good.knots_f64le_b64, "base64");
    const withBytes = (b: Buffer, over: Partial<Entry> = {}): Entry => ({
      ...good,
      knots_f64le_b64: b.toString("base64"),
      knots_sha256: createHash("sha256").update(b).digest("hex"),
      ...over,
    });
    const nan = Buffer.from(raw);
    nan.writeDoubleLE(Number.NaN, 8 * 100);
    const swapped = Buffer.from(raw);
    raw.copy(swapped, 8 * 10, 8 * 11, 8 * 12);
    raw.copy(swapped, 8 * 11, 8 * 10, 8 * 11);
    const cases: Entry[] = [
      { ...good, knots_sha256: "0".repeat(64) },
      { ...good, bins: 2048 },
      { ...good, encoding: "float32-le-base64" },
      withBytes(raw.subarray(0, raw.length - 8)),
      { ...good, knots_f64le_b64: "!!!not base64!!!" },
      withBytes(nan),
      withBytes(swapped),
    ];
    for (const c of cases) expect(() => decodeTable(c)).toThrow(InvalidScenario);
  });
});

describe("bit-equality with the Python fixtures", () => {
  it("P-007-04 · the first 10^4 variates of every family equal the Python variates, by bit pattern", () => {
    const f = fixture();
    expect(f.vectors.length).toBeGreaterThanOrEqual(9);
    expect(new Set(f.vectors.map((v) => v.family))).toEqual(
      new Set(["uniform", "normal", "lognormal-unit-mean", "exponential", "integers"]),
    );
    const tables = tablesFrom(f);
    for (const v of f.vectors) {
      expect(v.count).toBeGreaterThanOrEqual(10_000);
      const want = new BigUint64Array(new Uint8Array(Buffer.from(v.f64le_b64, "base64")).buffer);
      expect(want.length).toBe(v.count);
      const src = new VariateSource(BigInt(v.seed), { profile: "engine", tables });
      const got = new Float64Array(v.count);
      for (let i = 0; i < v.count; i++) {
        const p = v.params;
        got[i] =
          v.family === "uniform"
            ? src.uniform(v.purpose, p.lo as number, p.hi as number)
            : v.family === "normal"
              ? src.normal(v.purpose, p.loc as number, p.scale as number)
              : v.family === "lognormal-unit-mean"
                ? src.lognormalUnitMean(v.purpose, p.sigma as number)
                : v.family === "exponential"
                  ? src.exponential(v.purpose, p.scale as number)
                  : src.integers(v.purpose, p.lo as number, p.hi as number);
      }
      const bits = new BigUint64Array(got.buffer);
      let first = -1;
      for (let i = 0; i < v.count; i++) {
        if (bits[i] !== want[i]) {
          first = i;
          break;
        }
      }
      expect({ family: v.family, seed: v.seed, purpose: v.purpose, firstMismatch: first }).toEqual({
        family: v.family,
        seed: v.seed,
        purpose: v.purpose,
        firstMismatch: -1,
      });
    }
  });

  it("P-007-04 · the fixture covers the extreme seeds and the engine's stream purposes", () => {
    const f = fixture();
    const seeds = new Set(f.vectors.map((v) => v.seed));
    expect(seeds.has("0")).toBe(true);
    expect(seeds.has("9223372036854775807")).toBe(true);
    const purposes = new Set(f.vectors.map((v) => v.purpose));
    for (const p of ["init", "payload", "loadtime", "dumptime"]) expect(purposes.has(p)).toBe(true);
  });
});

describe("draw formulas and profiles", () => {
  const first = (seed: bigint, purpose: string) => new PhiloxStream(seed, purpose).nextU64();

  it("FR-007-06 · engine-profile draws follow the table and affine formulas", () => {
    const f = fixture();
    const tables = tablesFrom(f);
    const seed = 42n;
    const nk = tables.get(tableKey("normal")) as Float64Array;
    expect(new VariateSource(seed, { tables }).normal("payload", 227, 11)).toBe(
      227 + 11 * lerpTable(nk, first(seed, "payload")),
    );
    const lk = tables.get(tableKey("lognormal-unit-mean", 0.18)) as Float64Array;
    expect(new VariateSource(seed, { tables }).lognormalUnitMean("loadtime", 0.18)).toBe(
      lerpTable(lk, first(seed, "loadtime")),
    );
    const ek = tables.get(tableKey("exponential")) as Float64Array;
    expect(new VariateSource(seed, { tables }).exponential("dumptime", 55)).toBe(
      55 * lerpTable(ek, first(seed, "dumptime")),
    );
    expect(new VariateSource(seed, { tables }).integers("init", 3, 10)).toBe(
      3 + Number((first(seed, "init") * 7n) >> 64n),
    );
  });

  it("FR-007-07 · the exponential profile answers load and dump times with unit exponentials and payloads with their mean", () => {
    const tables = tablesFrom(fixture());
    const ek = tables.get(tableKey("exponential")) as Float64Array;
    for (const purpose of ["loadtime", "dumptime"]) {
      const src = new VariateSource(5n, { profile: "exponential", tables });
      expect(src.lognormalUnitMean(purpose, 0.18)).toBe(lerpTable(ek, first(5n, purpose)));
    }
    const src = new VariateSource(5n, { profile: "exponential", tables });
    for (let i = 0; i < 5; i++) expect(src.normal("payload", 227, 11)).toBe(227);
    const lk = tables.get(tableKey("lognormal-unit-mean", 0.18)) as Float64Array;
    expect(new VariateSource(5n, { profile: "exponential", tables }).lognormalUnitMean("lhd.dig", 0.18)).toBe(
      lerpTable(lk, first(5n, "lhd.dig")),
    );
  });

  it("FR-007-07 · the deterministic profile answers every request with the mean and needs no table", () => {
    const src = new VariateSource(123n, { profile: "deterministic", tables: new Map() });
    for (let i = 0; i < 3; i++) {
      expect(src.uniform("init", 0, 60)).toBe(30);
      expect(src.uniform("init", -4, 10)).toBe(3);
      expect(src.normal("payload", 227, 11)).toBe(227);
      expect(src.lognormalUnitMean("loadtime", 0.18)).toBe(1);
      expect(src.exponential("dumptime", 55)).toBe(55);
      expect(src.integers("init", 3, 10)).toBe(3);
    }
    expect(src.profile).toBe("deterministic");
  });

  it("FR-007-06 · a request for a table the bundle does not carry throws InvalidScenario", () => {
    const src = new VariateSource(1n, { tables: new Map() });
    expect(() => src.normal("payload", 1, 1)).toThrow(InvalidScenario);
    expect(() => src.lognormalUnitMean("loadtime", 0.18)).toThrow(InvalidScenario);
    expect(() => src.exponential("dumptime", 1)).toThrow(InvalidScenario);
    expect(src.uniform("init", 0, 60)).toBeGreaterThanOrEqual(0);
    expect(() => new VariateSource(1n)).not.toThrow();
    expect(() => new VariateSource(1n).normal("payload", 1, 1)).toThrow(InvalidScenario); // no table builder in the twin
  });

  it("FR-007-07 · an unknown profile is rejected", () => {
    for (const bad of ["Engine", "", "uniform"]) {
      expect(() => new VariateSource(1n, { profile: bad as never, tables: new Map() })).toThrow(
        InvalidScenario,
      );
    }
  });

  it("P-007-02 · streams are independent: the nth draw of one purpose does not depend on the others", () => {
    const tables = tablesFrom(fixture());
    const alone = new VariateSource(77n, { tables });
    const ref = Array.from({ length: 20 }, () => alone.uniform("loadtime", 0, 1));
    const mixed = new VariateSource(77n, { tables });
    const got: number[] = [];
    for (let i = 0; i < 20; i++) {
      mixed.uniform("payload", 0, 1);
      got.push(mixed.uniform("loadtime", 0, 1));
      mixed.normal("payload", 0, 1);
    }
    expect(got).toEqual(ref);
    expect(streamKey(77n, "loadtime")[0]).toBe(77n);
  });

  it("FR-007-06 · degenerate or non-finite parameters are rejected", () => {
    const tables = tablesFrom(fixture());
    const s = () => new VariateSource(3n, { tables });
    expect(() => s().uniform("init", 2, 1)).toThrow(RangeError);
    expect(() => s().uniform("init", Number.NaN, 1)).toThrow(RangeError);
    expect(() => s().normal("payload", 0, 0)).toThrow(RangeError);
    expect(() => s().normal("payload", 0, -1)).toThrow(RangeError);
    expect(() => s().exponential("dumptime", 0)).toThrow(RangeError);
    expect(() => s().exponential("dumptime", Number.POSITIVE_INFINITY)).toThrow(RangeError);
    expect(() => s().integers("init", 5, 5)).toThrow(RangeError);
  });
});
