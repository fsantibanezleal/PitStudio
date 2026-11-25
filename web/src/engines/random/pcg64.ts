// FR-018-49, P-018-04/-74/-75: numpy's PCG64 (XSL-RR 128/64, setseq) seeded from a SeedSequence. BigInt integer
// operations only (lint/no-math.grit forbids Math.* but Math.imul here).
import type { SeedSequence } from "./seedSequence";

const MASK128 = (1n << 128n) - 1n;
const MASK64 = (1n << 64n) - 1n;
const MULT = (2549297995355413924n << 64n) | 4865540595714422341n;

export class PCG64 {
  private state: bigint;
  private readonly inc: bigint;

  constructor(seed: SeedSequence) {
    const s = seed.generateState(4, "uint64");
    const initstate = ((s[0] as bigint) << 64n) | (s[1] as bigint);
    const initseq = ((s[2] as bigint) << 64n) | (s[3] as bigint);
    this.inc = ((initseq << 1n) | 1n) & MASK128;
    this.state = 0n;
    this.step();
    this.state = (this.state + initstate) & MASK128;
    this.step();
  }

  private step(): void {
    this.state = (this.state * MULT + this.inc) & MASK128;
  }

  nextU64(): bigint {
    this.step();
    const st = this.state;
    const x = (st >> 64n) ^ (st & MASK64);
    const rot = st >> 122n;
    return ((x >> rot) | (x << ((64n - rot) & 63n))) & MASK64;
  }

  random(): number {
    return Number(this.nextU64() >> 11n) * 2 ** -53;
  }

  advance(delta: bigint): void {
    if (typeof delta !== "bigint") throw new TypeError("advance(delta) needs a bigint");
    if (delta < 0n || delta >= 1n << 64n) throw new RangeError("advance(delta) needs delta in [0, 2^64)");
    let accMult = 1n;
    let accPlus = 0n;
    let curMult = MULT;
    let curPlus = this.inc;
    let d = delta;
    while (d > 0n) {
      if (d & 1n) {
        accMult = (accMult * curMult) & MASK128;
        accPlus = (accPlus * curMult + curPlus) & MASK128;
      }
      curPlus = ((curMult + 1n) * curPlus) & MASK128;
      curMult = (curMult * curMult) & MASK128;
      d >>= 1n;
    }
    this.state = (accMult * this.state + accPlus) & MASK128;
  }
}
