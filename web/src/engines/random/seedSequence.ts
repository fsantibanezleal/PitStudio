// FR-018-49, P-018-04: numpy's SeedSequence (numpy/random/bit_generator.pyx), integer operations only (no Math.* but
// Math.imul; enforced by lint/no-math.grit). Pool size 4, 32-bit words.
const INIT_A = 0x43b0d7e5;
const MULT_A = 0x931e8875;
const INIT_B = 0x8b51f9dd;
const MULT_B = 0x58f38ded;
const MIX_MULT_L = 0xca01f9dd;
const MIX_MULT_R = 0x4973f715;
const XSHIFT = 16;
const POOL_SIZE = 4;
const U32 = 0xffffffffn;

function coerceEntropy(entropy: unknown): bigint {
  if (typeof entropy === "bigint") {
    if (entropy < 0n) throw new RangeError("SeedSequence entropy must be non-negative");
    return entropy;
  }
  if (typeof entropy === "number") {
    if (!Number.isSafeInteger(entropy) || entropy < 0)
      throw new RangeError("SeedSequence entropy must be a non-negative safe integer");
    return BigInt(entropy);
  }
  if (typeof entropy === "string") {
    if (!/^[0-9]+$/.test(entropy)) throw new RangeError("SeedSequence entropy string must be decimal digits");
    return BigInt(entropy);
  }
  throw new TypeError("SeedSequence entropy must be a bigint, a safe integer or a decimal string");
}

function toWords(value: bigint): number[] {
  if (value === 0n) return [0];
  const out: number[] = [];
  let v = value;
  while (v > 0n) {
    out.push(Number(v & U32));
    v >>= 32n;
  }
  return out;
}

export class SeedSequence {
  readonly spawnKey: readonly number[];
  private readonly entropyValue: bigint;
  private readonly pool: number[];
  private childrenSpawned = 0;

  constructor(entropy: bigint | number | string, spawnKey: readonly number[] = []) {
    this.entropyValue = coerceEntropy(entropy);
    if (!Array.isArray(spawnKey)) throw new TypeError("spawnKey must be an array of 32-bit integers");
    for (const w of spawnKey) {
      if (typeof w !== "number" || !Number.isInteger(w) || w < 0 || w > 0xffffffff)
        throw new RangeError("spawnKey words must be integers in [0, 2^32)");
    }
    this.spawnKey = [...spawnKey];
    this.pool = SeedSequence.mix(this.entropyValue, this.spawnKey);
  }

  private static mix(entropy: bigint, spawnKey: readonly number[]): number[] {
    const run = toWords(entropy);
    if (spawnKey.length > 0) while (run.length < POOL_SIZE) run.push(0);
    const src = [...run, ...spawnKey];
    let hashConst = INIT_A;
    const hashmix = (value: number): number => {
      let v = (value ^ hashConst) >>> 0;
      hashConst = Math.imul(hashConst, MULT_A) >>> 0;
      v = Math.imul(v, hashConst) >>> 0;
      return (v ^ (v >>> XSHIFT)) >>> 0;
    };
    const mixWords = (x: number, y: number): number => {
      const r = (Math.imul(MIX_MULT_L, x) - Math.imul(MIX_MULT_R, y)) >>> 0;
      return (r ^ (r >>> XSHIFT)) >>> 0;
    };
    const pool: number[] = [];
    for (let i = 0; i < POOL_SIZE; i++) pool.push(hashmix(i < src.length ? (src[i] as number) : 0));
    for (let s = 0; s < POOL_SIZE; s++)
      for (let d = 0; d < POOL_SIZE; d++)
        if (s !== d) pool[d] = mixWords(pool[d] as number, hashmix(pool[s] as number));
    for (let s = POOL_SIZE; s < src.length; s++)
      for (let d = 0; d < POOL_SIZE; d++) pool[d] = mixWords(pool[d] as number, hashmix(src[s] as number));
    return pool;
  }

  /** Children carry spawnKey + [i], i counting from the parent's number of children already spawned. */
  spawn(n: number): SeedSequence[] {
    if (!Number.isInteger(n) || n < 0) throw new RangeError("spawn count must be a non-negative integer");
    const out: SeedSequence[] = [];
    for (let i = 0; i < n; i++) {
      out.push(new SeedSequence(this.entropyValue, [...this.spawnKey, this.childrenSpawned]));
      this.childrenSpawned += 1;
    }
    return out;
  }

  generateState(nWords: number, dtype?: "uint32"): number[];
  generateState(nWords: number, dtype: "uint64"): bigint[];
  generateState(nWords: number, dtype: "uint32" | "uint64" = "uint32"): Array<number | bigint> {
    if (!Number.isInteger(nWords) || nWords < 0)
      throw new RangeError("nWords must be a non-negative integer");
    const count = dtype === "uint64" ? nWords * 2 : nWords;
    let hashConst = INIT_B;
    const words: number[] = [];
    for (let i = 0; i < count; i++) {
      let v = ((this.pool[i % POOL_SIZE] as number) ^ hashConst) >>> 0;
      hashConst = Math.imul(hashConst, MULT_B) >>> 0;
      v = Math.imul(v, hashConst) >>> 0;
      words.push((v ^ (v >>> XSHIFT)) >>> 0);
    }
    if (dtype === "uint32") return words;
    const out: bigint[] = [];
    for (let i = 0; i < nWords; i++)
      out.push((BigInt(words[2 * i + 1] as number) << 32n) | BigInt(words[2 * i] as number));
    return out;
  }
}
