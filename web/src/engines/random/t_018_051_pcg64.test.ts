// T-018-051 [red] · FR-018-49 (numpy-compatible PCG64 + SeedSequence port, integer operations only, lint rule on `Math.*`),
// P-018-04 (same 10^4 words and doubles as numpy), P-018-05 (stream independence), P-018-74 (advance), P-018-75 (uniform doubles).
// Browser half (Chromium, Firefox, WebKit): web/e2e/parity/t_018_051_pcg64_browsers.spec.ts.
//
// Expected API
//   module `~/engines/random/seedSequence` (web/src/engines/random/seedSequence.ts):
//     class SeedSequence { constructor(entropy: bigint | number | string, spawnKey?: readonly number[]);
//         readonly spawnKey: readonly number[];
//         spawn(n: number): SeedSequence[];                       children carry spawnKey + [i], i counting from the parent's
//                                                                 number of children already spawned (numpy: n_children_spawned)
//         generateState(nWords: number, dtype?: "uint32" | "uint64"): Array<number | bigint> }   uint32 -> number[], uint64 -> bigint[]
//       entropy: a non-negative integer as bigint, safe-integer number or decimal string; spawn-key words are integers in [0, 2^32).
//       Anything else throws (RangeError or TypeError).
//   module `~/engines/random/pcg64` (web/src/engines/random/pcg64.ts):
//     class PCG64 { constructor(seed: SeedSequence);               seeded as numpy's PCG64(SeedSequence) (also default_rng)
//         nextU64(): bigint;                                       next 64-bit word (numpy: random_raw)
//         random(): number;                                        (word >> 11) * 2^-53, exactly numpy's Generator.random()
//         advance(delta: bigint): void;                            numpy's PCG64.advance for delta in [0, 2^64); a value that
//                                                                  is not a bigint throws (numpy wraps larger deltas modulo 2^128 and
//                                                                  accepts negative ones; the port is not required to) }
//
// Oracles: numpy 2.5.3 called directly (web/src/engines/random/t_018_051_numpy_reference.json holds its output, with the recipe);
// the exact conversion (word >> 11) x 2^-53 written in FR-018-49 / P-018-75; the lint rule is checked against planted files.
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { PCG64 } from "~/engines/random/pcg64";
import { SeedSequence } from "~/engines/random/seedSequence";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = resolve(HERE, "../../..");

interface Stream {
  entropy: string;
  spawn_key: number[];
  first_words: string[];
  first_doubles: string[];
  words_sha256: string;
  doubles_sha256: string;
  word_at: Record<string, string>;
}
interface Reference {
  numpy: string;
  streams: Stream[];
  state_u32: number[];
  state_u64: string[];
  state0_u32: number[];
  children: Array<{ spawn_key: number[]; first_words: string[] }>;
  advance: Array<{ n: string; next: string }>;
  default_rng_777: string[];
}
const ref = JSON.parse(readFileSync(resolve(HERE, "t_018_051_numpy_reference.json"), "utf8")) as Reference;
const gen = (s: Stream) => new PCG64(new SeedSequence(BigInt(s.entropy), s.spawn_key));
const sha = (b: Uint8Array) => createHash("sha256").update(b).digest("hex");

describe("SeedSequence against numpy (P-018-04)", () => {
  it("P-018-04 · generate_state(8, uint32) and (4, uint64) of SeedSequence(20261007) equal numpy's", () => {
    const ss = new SeedSequence(20261007n);
    expect(ss.generateState(8, "uint32")).toEqual(ref.state_u32);
    expect(ss.generateState(4, "uint64")).toEqual(ref.state_u64.map(BigInt));
  });

  it("P-018-04 · the default dtype is uint32 and entropy 0 works (numpy generate_state(4) of SeedSequence(0))", () => {
    expect(new SeedSequence(0n).generateState(4)).toEqual(ref.state0_u32);
  });

  it("P-018-04 · entropy given as a bigint, a number or a decimal string is the same seed", () => {
    const a = new SeedSequence(20261007n).generateState(4, "uint32");
    expect(new SeedSequence(20261007).generateState(4, "uint32")).toEqual(a);
    expect(new SeedSequence("20261007").generateState(4, "uint32")).toEqual(a);
  });

  it("P-018-04 · spawn(3) of SeedSequence(20261007, spawn_key=(5,)) gives numpy's children (keys and first words)", () => {
    const kids = new SeedSequence(20261007n, [5]).spawn(3);
    expect(kids.map((k: SeedSequence) => [...k.spawnKey])).toEqual(ref.children.map((c) => c.spawn_key));
    kids.forEach((k: SeedSequence, i: number) => {
      const g = new PCG64(k);
      expect([g.nextU64(), g.nextU64(), g.nextU64()].map(String)).toEqual(
        (ref.children[i] as { first_words: string[] }).first_words,
      );
    });
  });

  it("P-018-04 · a second spawn call continues the child counter (numpy n_children_spawned)", () => {
    const parent = new SeedSequence(20261007n, [5]);
    parent.spawn(3);
    const more = parent.spawn(2);
    expect(more.map((k: SeedSequence) => [...k.spawnKey])).toEqual([
      [5, 3],
      [5, 4],
    ]);
  });
});

describe("PCG64 against numpy (P-018-04)", () => {
  for (const s of ref.streams) {
    const label = `entropy ${s.entropy.length > 12 ? `${s.entropy.slice(0, 8)}…` : s.entropy}, spawn_key [${s.spawn_key.join(",")}]`;

    it(`P-018-04 · ${label}: the first words, the word at 0, 63, 64, 999, 9999 and the SHA-256 of 10^4 words equal numpy's`, () => {
      const g = gen(s);
      const words: bigint[] = [];
      for (let i = 0; i < 10_000; i++) words.push(g.nextU64());
      expect(words.slice(0, 6).map(String)).toEqual(s.first_words);
      for (const [i, w] of Object.entries(s.word_at)) expect(String(words[Number(i)])).toBe(w);
      const buf = Buffer.alloc(8 * words.length);
      for (const [i, w] of words.entries()) buf.writeBigUInt64LE(w, i * 8);
      expect(sha(buf)).toBe(s.words_sha256);
    });

    it(`P-018-04 · ${label}: random() reproduces numpy's first doubles exactly and the SHA-256 of 10^4 doubles`, () => {
      const g = gen(s);
      const doubles = new Float64Array(10_000);
      for (let i = 0; i < doubles.length; i++) doubles[i] = g.random();
      expect(Array.from(doubles.slice(0, 3))).toEqual(s.first_doubles.map(Number));
      expect(sha(new Uint8Array(doubles.buffer))).toBe(s.doubles_sha256);
    });
  }

  it("P-018-04 · the stream of default_rng(777) (numpy) is the stream of PCG64(SeedSequence(777))", () => {
    const g = new PCG64(new SeedSequence(777n));
    expect([g.nextU64(), g.nextU64()].map(String)).toEqual(ref.default_rng_777);
  });
});

describe("uniform doubles (P-018-75)", () => {
  it("P-018-75 · every random() is (word >> 11) x 2^-53 of the corresponding 64-bit word, inside [0, 1), for 3 seeds x 10^6 draws", () => {
    for (const entropy of [1n, 20261007n, 2n ** 70n + 3n]) {
      const words = new PCG64(new SeedSequence(entropy));
      const doubles = new PCG64(new SeedSequence(entropy));
      for (let i = 0; i < 1_000_000; i++) {
        const w = words.nextU64();
        const d = doubles.random();
        if (d !== Number(w >> 11n) * 2 ** -53 || !(d >= 0 && d < 1)) {
          expect.fail(`seed ${entropy}, draw ${i}: word ${w}, double ${d}`);
        }
      }
    }
  }, 180_000);
});

describe("advance (P-018-74)", () => {
  for (const { n, next } of ref.advance) {
    it(`P-018-74 · advance(${n}) then one draw equals numpy's PCG64.advance(${n}) then random_raw()`, () => {
      const g = new PCG64(new SeedSequence(20261007n));
      g.advance(BigInt(n));
      expect(String(g.nextU64())).toBe(next);
    });
  }

  it("P-018-74 · for n up to 5 x 10^4, advance(n) then one draw is the (n + 1)-th draw of a fresh generator", () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 50_000 }), (n) => {
        const fresh = new PCG64(new SeedSequence(99n, [1]));
        let word = 0n;
        for (let i = 0; i <= n; i++) word = fresh.nextU64();
        const jumped = new PCG64(new SeedSequence(99n, [1]));
        jumped.advance(BigInt(n));
        return jumped.nextU64() === word;
      }),
      { numRuns: 20 },
    );
  }, 120_000);

  it("P-018-74 · the bound n = 10^6", () => {
    const fresh = new PCG64(new SeedSequence(5n));
    let word = 0n;
    for (let i = 0; i <= 1_000_000; i++) word = fresh.nextU64();
    const jumped = new PCG64(new SeedSequence(5n));
    jumped.advance(1_000_000n);
    expect(jumped.nextU64()).toBe(word);
  }, 120_000);

  it("P-018-74 · advance(0) changes nothing and two advances add up", () => {
    const a = new PCG64(new SeedSequence(8n));
    const b = new PCG64(new SeedSequence(8n));
    a.advance(0n);
    a.advance(40n);
    a.advance(2n);
    b.advance(42n);
    expect(a.nextU64()).toBe(b.nextU64());
  });
});

describe("stream independence (P-018-05)", () => {
  it("P-018-05 · interleaving draws of two generators with different spawn keys in any order leaves each sequence unchanged", () => {
    const solo = (key: number[], n: number) => {
      const g = new PCG64(new SeedSequence(20261007n, key));
      return Array.from({ length: n }, () => g.nextU64());
    };
    const expectedA = solo([0], 1000);
    const expectedB = solo([1, 2], 1000);
    fc.assert(
      fc.property(fc.array(fc.boolean(), { minLength: 1, maxLength: 1000 }), (order) => {
        const a = new PCG64(new SeedSequence(20261007n, [0]));
        const b = new PCG64(new SeedSequence(20261007n, [1, 2]));
        const gotA: bigint[] = [];
        const gotB: bigint[] = [];
        for (const pickA of order) {
          if (pickA) gotA.push(a.nextU64());
          else gotB.push(b.nextU64());
        }
        return gotA.every((w, i) => w === expectedA[i]) && gotB.every((w, i) => w === expectedB[i]);
      }),
      { numRuns: 100 },
    );
  });

  it("P-018-05 · different spawn keys give different streams (empty key, [0], [1], [0, 0])", () => {
    const firsts = [[], [0], [1], [0, 0]].map((k) => new PCG64(new SeedSequence(20261007n, k)).nextU64());
    expect(new Set(firsts).size).toBe(4);
  });
});

describe("hostile construction (FR-018-49)", () => {
  const badEntropy: Array<[string, unknown]> = [
    ["a negative bigint", -1n],
    ["a negative number", -5],
    ["a fractional number", 1.5],
    ["NaN", Number.NaN],
    ["Infinity", Number.POSITIVE_INFINITY],
    ["a number beyond 2^53", 2 ** 60],
    ["a non-numeric string", "abc"],
    ["an empty string", ""],
    ["a string with a sign", "-12"],
    ["a hex string", "0x10"],
    ["a string with spaces", " 12 "],
    ["null", null],
    ["undefined", undefined],
    ["an object", {}],
    ["an array", [1]],
  ];
  for (const [name, value] of badEntropy) {
    it(`FR-018-49 · entropy ${name} throws`, () => {
      expect(() => new SeedSequence(value as bigint)).toThrow();
    });
  }

  const badKeys: Array<[string, unknown]> = [
    ["a negative word", [-1]],
    ["a word of 2^32", [4294967296]],
    ["a fractional word", [1.5]],
    ["NaN", [Number.NaN]],
    ["a string word", ["1"]],
    ["not an array", 7],
  ];
  for (const [name, value] of badKeys) {
    it(`FR-018-49 · a spawn key with ${name} throws`, () => {
      expect(() => new SeedSequence(1n, value as number[])).toThrow();
    });
  }

  it("FR-018-49 · spawn and advance reject invalid counts", () => {
    const ss = new SeedSequence(1n);
    for (const n of [-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) expect(() => ss.spawn(n)).toThrow();
    const g = new PCG64(ss);
    expect(() => g.advance(1.5 as unknown as bigint)).toThrow();
    expect(() => g.advance("3" as unknown as bigint)).toThrow();
  });

  it("FR-018-49 · the largest 32-bit spawn-key word and a 128-bit entropy are accepted", () => {
    expect(() => new SeedSequence(2n ** 128n - 1n, [4294967295])).not.toThrow();
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// FR-018-49 · lint rule: any `Math.*` other than Math.imul fails the build in the port's source files
// ---------------------------------------------------------------------------------------------------------------------
describe("Math lint rule (FR-018-49)", () => {
  const biome = resolve(WEB, "node_modules/@biomejs/biome/bin/biome");
  const lint = (files: string[]) =>
    spawnSync(process.execPath, [biome, "lint", ...files], { cwd: WEB, encoding: "utf8", timeout: 120_000 });

  const planted: Record<string, string> = {
    "zz_planted_floor.ts": "export const a = Math.floor(1.5);\n",
    "zz_planted_pow.ts": "export const a = Math.pow(2, 3);\n",
    "zz_planted_random.ts": "export const a = Math.random();\n",
    "zz_planted_max.ts": "export const a = Math.max(1, 2);\n",
    "zz_planted_computed.ts": "export const a = Math['floor'](1.5);\n",
    "zz_planted_alias.ts": "const m = Math;\nexport const a = m.floor(1);\n",
    "zz_planted_destructure.ts": "const { floor } = Math;\nexport const a = floor(1.5);\n",
    "zz_planted_globalthis.ts": "export const a = globalThis.Math.sqrt(4);\n",
  };

  it("FR-018-49 · a planted Math.floor, pow, random, max, computed access, alias, destructuring or globalThis.Math fails the lint", () => {
    const names = Object.keys(planted);
    try {
      for (const [name, body] of Object.entries(planted)) writeFileSync(resolve(HERE, name), body);
      for (const name of names) {
        const out = lint([`src/engines/random/${name}`]);
        expect(out.status, `biome must reject ${name}\n${out.stdout}${out.stderr}`).not.toBe(0);
      }
    } finally {
      for (const name of names) if (existsSync(resolve(HERE, name))) rmSync(resolve(HERE, name));
    }
  }, 240_000);

  it("FR-018-49 · Math.imul and the other integer operations pass the lint", () => {
    const name = "zz_planted_imul_ok.ts";
    try {
      writeFileSync(
        resolve(HERE, name),
        "export const a = Math.imul(3, 4) >>> 0;\nexport const b = (7n << 11n) >> 3n;\nexport const c = (5 ^ 3) & 0xff;\n",
      );
      const out = lint([`src/engines/random/${name}`]);
      expect(out.status, `${out.stdout}${out.stderr}`).toBe(0);
    } finally {
      if (existsSync(resolve(HERE, name))) rmSync(resolve(HERE, name));
    }
  }, 120_000);

  it("FR-018-49 · the port's own source files pass the lint (and call no other Math function)", () => {
    const files = ["src/engines/random/pcg64.ts", "src/engines/random/seedSequence.ts"];
    const out = lint(files);
    expect(out.status, `${out.stdout}${out.stderr}`).toBe(0);
    for (const f of files) {
      const text = readFileSync(resolve(WEB, f), "utf8");
      const uses = [...text.matchAll(/\bMath\s*(?:\.\s*(\w+)|\[)/g)].map((m) => m[1] ?? "[computed]");
      for (const u of uses) expect(u).toBe("imul");
    }
  }, 120_000);
});
