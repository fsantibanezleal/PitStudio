// Beam hash of the dust keep law (FR-013-14): MurmurHash3_x86_32 of the 12-byte little-endian key
// (frame, beam, run seed). The Python port is `pitstudio.sensors.beamhash`; both give the same `u` bit for bit.

const C1 = 0xcc9e2d51;
const C2 = 0x1b873593;
const LIMIT = 2 ** 32;

function rotl(x: number, r: number): number {
  return ((x << r) | (x >>> (32 - r))) >>> 0;
}

function mixKey(k: number): number {
  k = Math.imul(k, C1) >>> 0;
  k = rotl(k, 15);
  return Math.imul(k, C2) >>> 0;
}

/** Unsigned 32-bit MurmurHash3_x86_32 of `data` (public-domain reference algorithm). */
export function murmur3x86_32(data: Uint8Array, seed = 0): number {
  let h = seed >>> 0;
  const blocks = data.length >>> 2;
  for (let i = 0; i < blocks; i++) {
    const o = 4 * i;
    const k = (data[o] | (data[o + 1] << 8) | (data[o + 2] << 16) | (data[o + 3] << 24)) >>> 0;
    h = (h ^ mixKey(k)) >>> 0;
    h = rotl(h, 13);
    h = (Math.imul(h, 5) + 0xe6546b64) >>> 0;
  }
  const tail = data.length & 3;
  if (tail > 0) {
    const o = 4 * blocks;
    let k = 0;
    if (tail >= 3) k ^= data[o + 2] << 16;
    if (tail >= 2) k ^= data[o + 1] << 8;
    k ^= data[o];
    h = (h ^ mixKey(k >>> 0)) >>> 0;
  }
  h = (h ^ data.length) >>> 0;
  h ^= h >>> 16;
  h = Math.imul(h, 0x85ebca6b) >>> 0;
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35) >>> 0;
  h ^= h >>> 16;
  return h >>> 0;
}

function u32(value: unknown, name: string): number {
  if (typeof value !== "number") throw new TypeError(`${name} must be an unsigned 32-bit integer`);
  if (!Number.isInteger(value) || value < 0 || value >= LIMIT) {
    throw new RangeError(`${name} must be an integer with 0 <= ${name} < 2^32, got ${value}`);
  }
  return value;
}

/** The uint32 hash of the key (frame, beam, seed). */
export function beamHash(frame: number, beam: number, seed: number): number {
  const key = new Uint8Array(12);
  const view = new DataView(key.buffer);
  view.setUint32(0, u32(frame, "frame"), true);
  view.setUint32(4, u32(beam, "beam"), true);
  view.setUint32(8, u32(seed, "seed"), true);
  return murmur3x86_32(key, 0);
}

/** `beamHash / 2^32`, in [0, 1). */
export function beamValue(frame: number, beam: number, seed: number): number {
  return beamHash(frame, beam, seed) / LIMIT;
}
