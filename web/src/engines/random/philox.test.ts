// @vitest-environment node
//
// T-007-012 (1/3) · Philox4x64-10 and FNV-1a-64 in TypeScript (BigInt): FR-007-05, P-007-01, P-007-04 (the generator part).
//
// Spec: specs/007-haulage-dispatch/spec.md FR-007-05 (every random number from Philox4x64-10 as defined by Random123; key (seed, FNV-1a-64 of the UTF-8 purpose name); counter (block, 0, 0, 0),
// block 0 first for each stream; the four 64-bit words of each block consumed in order; identical in Python and TypeScript), P-007-01 (known answers: counter 0 and key 0 gives
// 16554d9eca36314c db20fe9d672d0fdc d7e772cee186176b 7e68b68aec7ba23b; all words 2^64 - 1 gives 87b092c3013fe90b 438c3c67be8d0224 9cc7d7c69cd777b6 a09caebf594f0ba0; FNV-1a-64 of "" is
// cbf29ce484222325, of "a" af63dc4c8601ec8c, of "foobar" 85944171f73967e8).
//
// Oracle: the published Random123 / FNV vectors above; 400 (key, counter) pairs with their blocks computed by `numpy.random.Philox` (counter offset by -1) and committed in
// tests/fixtures/haulage/philox_vectors.json (reference implementation, generated outside this repository's code); FNV-1a written out in the test.
//
// Expected API (module `~/engines/random/philox`):
//   philox4x64_10(counter: readonly [bigint, bigint, bigint, bigint], key: readonly [bigint, bigint]): [bigint, bigint, bigint, bigint]   words must be 0 <= w < 2^64, else RangeError
//   fnv1a64(data: string | Uint8Array): bigint                       a string is encoded as UTF-8
//   streamKey(seed: bigint, purpose: string): [bigint, bigint]       [seed, fnv1a64(purpose)]
//   u01FromU64(x: bigint): number                                    Number(x >> 11n) * 2 ** -53, in [0, 1)
//   class PhiloxStream { constructor(seed: bigint, purpose: string); get blockIndex(): bigint; nextU64(): bigint; jump(block: bigint): void }
//        counter (block, 0, 0, 0); blockIndex is the number of blocks started (0 for a fresh stream); words of a block are consumed in order.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { fnv1a64, PhiloxStream, philox4x64_10, streamKey, u01FromU64 } from "~/engines/random/philox";

const REPO = resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../..");
const M64 = (1n << 64n) - 1n;
const hex = (w: readonly bigint[]) => w.map((x) => x.toString(16).padStart(16, "0"));
const big = (s: string) => BigInt(`0x${s}`);

describe("Philox4x64-10", () => {
  it("P-007-01 · the Random123 known answer for counter 0 and key 0", () => {
    expect(hex(philox4x64_10([0n, 0n, 0n, 0n], [0n, 0n]))).toEqual([
      "16554d9eca36314c",
      "db20fe9d672d0fdc",
      "d7e772cee186176b",
      "7e68b68aec7ba23b",
    ]);
  });

  it("P-007-01 · the Random123 known answer for every word 2^64 - 1", () => {
    expect(hex(philox4x64_10([M64, M64, M64, M64], [M64, M64]))).toEqual([
      "87b092c3013fe90b",
      "438c3c67be8d0224",
      "9cc7d7c69cd777b6",
      "a09caebf594f0ba0",
    ]);
  });

  it("P-007-01 · 400 random (key, counter) pairs equal numpy.random.Philox", () => {
    const doc = JSON.parse(
      readFileSync(resolve(REPO, "tests/fixtures/haulage/philox_vectors.json"), "utf-8"),
    ) as {
      pairs: { key: string[]; counter: string[]; block: string[] }[];
    };
    expect(doc.pairs.length).toBeGreaterThanOrEqual(400);
    for (const p of doc.pairs) {
      const got = philox4x64_10(
        p.counter.map(big) as [bigint, bigint, bigint, bigint],
        p.key.map(big) as [bigint, bigint],
      );
      expect(hex(got)).toEqual(p.block);
    }
  });

  it("FR-007-05 · words outside 64 bits are rejected", () => {
    expect(() => philox4x64_10([-1n, 0n, 0n, 0n], [0n, 0n])).toThrow(RangeError);
    expect(() => philox4x64_10([0n, 0n, 0n, 1n << 64n], [0n, 0n])).toThrow(RangeError);
    expect(() => philox4x64_10([0n, 0n, 0n, 0n], [0n, -5n])).toThrow(RangeError);
    expect(() => philox4x64_10([0n, 0n, 0n, 0n], [1n << 64n, 0n])).toThrow(RangeError);
  });
});

describe("FNV-1a-64 and stream keys", () => {
  it("P-007-01 · the published FNV-1a-64 vectors", () => {
    expect(fnv1a64("")).toBe(0xcbf29ce484222325n);
    expect(fnv1a64("a")).toBe(0xaf63dc4c8601ec8cn);
    expect(fnv1a64("foobar")).toBe(0x85944171f73967e8n);
    expect(fnv1a64(new Uint8Array([0x66, 0x6f, 0x6f, 0x62, 0x61, 0x72]))).toBe(0x85944171f73967e8n);
  });

  it("FR-007-05 · the hash is over the UTF-8 bytes and equals the definition", () => {
    const ref = (b: Uint8Array) => {
      let h = 0xcbf29ce484222325n;
      for (const x of b) h = ((h ^ BigInt(x)) * 0x100000001b3n) & M64;
      return h;
    };
    for (const name of [
      "loadtime",
      "dumptime",
      "payload",
      "init",
      "fail.truck",
      "policy",
      "café",
      "ランダム",
      "a\u0000b",
    ]) {
      expect(fnv1a64(name)).toBe(ref(new TextEncoder().encode(name)));
    }
  });

  it("FR-007-05 · the stream key is the seed and the hash of the purpose", () => {
    for (const seed of [0n, 1n, 42n, (1n << 63n) - 1n]) {
      expect(streamKey(seed, "loadtime")).toEqual([seed, fnv1a64("loadtime")]);
    }
  });
});

describe("PhiloxStream", () => {
  it("FR-007-05 · a stream yields the words of blocks 0, 1, 2 in order with counter (block, 0, 0, 0)", () => {
    for (const seed of [0n, 7n, (1n << 62n) + 12345n]) {
      const key = streamKey(seed, "loadtime");
      const expected = [0n, 1n, 2n].flatMap((b) => philox4x64_10([b, 0n, 0n, 0n], key));
      const s = new PhiloxStream(seed, "loadtime");
      expect(s.blockIndex).toBe(0n);
      const got = Array.from({ length: 12 }, () => s.nextU64());
      expect(got).toEqual(expected);
      expect(s.blockIndex).toBe(3n);
    }
  });

  it("FR-007-05 · the block index counts started blocks", () => {
    const s = new PhiloxStream(1n, "payload");
    s.nextU64();
    expect(s.blockIndex).toBe(1n);
    for (let i = 0; i < 3; i++) s.nextU64();
    expect(s.blockIndex).toBe(1n);
    s.nextU64();
    expect(s.blockIndex).toBe(2n);
  });

  it("P-007-02 · jumping to block k equals k sequential blocks (counter addressability)", () => {
    for (const k of [0n, 1n, 2n, 17n, 40n]) {
      const a = new PhiloxStream(99n, "dumptime");
      for (let i = 0n; i < 4n * k; i++) a.nextU64();
      const b = new PhiloxStream(99n, "dumptime");
      b.jump(k);
      expect(Array.from({ length: 9 }, () => b.nextU64())).toEqual(
        Array.from({ length: 9 }, () => a.nextU64()),
      );
    }
  });

  it("FR-007-06 · the uniform is the top 53 bits times 2^-53 and never reaches 1", () => {
    expect(u01FromU64(M64)).toBe((2 ** 53 - 1) * 2 ** -53);
    expect(u01FromU64(M64)).toBeLessThan(1);
    expect(u01FromU64(0n)).toBe(0);
    expect(u01FromU64(2n ** 11n - 1n)).toBe(0);
    expect(u01FromU64(2n ** 11n)).toBe(2 ** -53);
    expect(u01FromU64(1n << 63n)).toBe(0.5);
  });
});
