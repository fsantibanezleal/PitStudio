// T-013-031 · FR-013-14 · TypeScript MurmurHash3 known-answer vectors from the Python reference.
//
// Oracle: the published MurmurHash3_x86_32 test vectors (SMHasher verification, the `mmh3` and `murmur3` suites) and ten beam-hash keys whose hashes
// were computed with the reference implementation in `tests/_sensor_kit/sensor_kit.py` (itself validated against those vectors); the Python port
// is tested against the same numbers in tests/property/test_t_013_022_beam_hash.py, so both ports give identical u.
//
// Expected API (module `web/src/engines/sensors/beam-hash.ts`):
//   murmur3x86_32(data: Uint8Array, seed?: number): number          unsigned 32-bit MurmurHash3_x86_32 (seed default 0)
//   beamHash(frame: number, beam: number, seed: number): number     murmur3x86_32 (seed 0) of the 12-byte little-endian key (frame, beam, seed)
//   beamValue(frame: number, beam: number, seed: number): number    beamHash / 2**32, in [0, 1)
// A frame, beam or seed that is not an integer in 0 <= x < 2**32 throws (RangeError or TypeError).

import { describe, expect, it } from "vitest";
import { beamHash, beamValue, murmur3x86_32 } from "./beam-hash";

const enc = (s: string): Uint8Array => new TextEncoder().encode(s);

// [seed, bytes, expected unsigned hash]
const VECTORS: [number, Uint8Array, number][] = [
  [0, enc(""), 0x00000000],
  [1, enc(""), 0x514e28b7],
  [0xffffffff, enc(""), 0x81f16f39],
  [0, enc("test"), 0xba6bd213],
  [0, enc("foo"), 0xf6a5c420],
  [0, enc("Hello, world!"), 0xc0363e43],
  [0, enc("The quick brown fox jumps over the lazy dog"), 0x2e4ff723],
  [0, enc("abc"), 0xb3dd93fa],
  [0x9747b28c, enc("a"), 0x7fa09ea6],
  [0x9747b28c, enc("aa"), 0x5d211726],
  [0x9747b28c, enc("aaa"), 0x283e0130],
  [0x9747b28c, enc("aaaa"), 0x5a97808a],
  [0x9747b28c, enc("Hello, world!"), 0x24884cba],
  [0, new Uint8Array([0, 0, 0, 0]), 0x2362f9de],
  [0, new Uint8Array([0xff, 0xff, 0xff, 0xff]), 0x76293b50],
];

// [frame, beam, seed, hash, u] computed with the Python reference
const KEYS: [number, number, number, number, number][] = [
  [0, 0, 0, 0xd941144b, 0.8486492808442563],
  [1, 0, 0, 0xd4657dc3, 0.8296736336778849],
  [0, 1, 0, 0x6f08baed, 0.43372696195729077],
  [0, 0, 1, 0x5fbbc52a, 0.3739588954485953],
  [1, 2, 3, 0xe9d78ad6, 0.9134451649151742],
  [3, 17, 20261007, 0x641a6166, 0.39102753391489387],
  [7, 199999, 20261007, 0x2a3a2faa, 0.16495035076513886],
  [100000, 200000, 4294967295, 0x16f9ef31, 0.08975119539536536],
  [4294967295, 4294967295, 4294967295, 0xa9ed186d, 0.6637740388978273],
  [12345, 678, 90, 0xba88ca14, 0.7286497401073575],
];

describe("murmur3x86_32", () => {
  it.each(VECTORS.map((v, i) => [i, ...v] as const))(
    "FR-013-14 · matches the published vector %i",
    (_i, seed, data, expected) => {
      expect(murmur3x86_32(data, seed)).toBe(expected);
    },
  );

  it("FR-013-14 · returns an unsigned 32-bit integer for every tail length", () => {
    for (let n = 0; n < 40; n++) {
      const h = murmur3x86_32(new Uint8Array(n).fill(0xab), 0xdeadbeef);
      expect(Number.isInteger(h) && h >= 0 && h <= 0xffffffff).toBe(true);
    }
  });
});

describe("beamHash and beamValue", () => {
  it.each(KEYS.map((k, i) => [i, ...k] as const))(
    "FR-013-14 · known answer %i: the hash and u equal the Python reference",
    (_i, frame, beam, seed, hash, u) => {
      expect(beamHash(frame, beam, seed)).toBe(hash);
      expect(beamValue(frame, beam, seed)).toBe(u);
    },
  );

  it("FR-013-14 · u is hash / 2^32 and stays in [0, 1)", () => {
    for (const key of [
      [0, 0, 0],
      [4294967295, 4294967295, 4294967295],
      [0, 4294967295, 0],
      [123456, 789, 42],
    ] as const) {
      const u = beamValue(...key);
      expect(u).toBe(beamHash(...key) / 2 ** 32);
      expect(u >= 0 && u < 1).toBe(true);
    }
  });

  it("FR-013-14 · the key is the 12-byte little-endian (frame, beam, seed)", () => {
    const key = new Uint8Array([3, 0, 0, 0, 17, 0, 0, 0, 0x8f, 0x28, 0x35, 0x01]); // 3, 17, 20261007 = 0x0135288f
    expect(murmur3x86_32(key, 0)).toBe(beamHash(3, 17, 20261007));
  });

  it("FR-013-14 · keys outside the unsigned 32-bit integers are rejected", () => {
    for (const bad of [-1, 2 ** 32, 2 ** 53, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(() => beamHash(bad, 0, 0)).toThrow();
      expect(() => beamHash(0, bad, 0)).toThrow();
      expect(() => beamHash(0, 0, bad)).toThrow();
    }
    expect(() => beamHash("1" as unknown as number, 0, 0)).toThrow();
  });
});
