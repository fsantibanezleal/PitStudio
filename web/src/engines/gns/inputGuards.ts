// Hostile-input guard of the `gns` engine (FR-011-15): the web twin of pitstudio_pipeline.surrogates.gns.model.validate_gns_inputs.
//
// Never throws: a bad input gives { ok: false, message: "rollout stopped — <reason>" } (the em dash is part of the string fixed by the
// spec), the reason names the offending argument, and no acceleration is computed.
import { K_MAX } from "./radiusGraph";

export const HISTORY = 5;
const PREFIX = "rollout stopped — ";

export interface GnsInputs {
  n: number;
  positions: Float32Array;
  velocities: Float32Array;
  particleType: Int32Array;
  bounds: Float32Array;
  neighbourIndex: Int32Array;
  neighbourMask: Uint8Array;
}

export type GuardResult = { ok: true } | { ok: false; message: string };

function stop(reason: string): GuardResult {
  return { ok: false, message: PREFIX + reason };
}

function allFinite(values: ArrayLike<number>): boolean {
  for (let i = 0; i < values.length; i++) if (!Number.isFinite(values[i] as number)) return false;
  return true;
}

export function validateGnsInputs(inputs: GnsInputs, nParticleTypes: number): GuardResult {
  if (inputs === null || typeof inputs !== "object") return stop("inputs are missing");
  const { n, positions, velocities, particleType, bounds, neighbourIndex, neighbourMask } = inputs;
  if (!Number.isInteger(n) || n < 1)
    return stop(`n must be a positive integer (positions hold ${n} particles)`);
  if (!(positions instanceof Float32Array) || positions.length !== 2 * n) {
    return stop(`positions must be a Float32Array of length ${2 * n} (n x 2)`);
  }
  if (!(velocities instanceof Float32Array) || velocities.length !== 2 * HISTORY * n) {
    return stop(`velocities must be a Float32Array of length ${2 * HISTORY * n} (n x ${HISTORY} x 2)`);
  }
  if (!(particleType instanceof Int32Array) || particleType.length !== n) {
    return stop(`particleType must be an Int32Array of length ${n}`);
  }
  if (!(bounds instanceof Float32Array) || bounds.length !== 4)
    return stop("bounds must be a Float32Array of length 4");
  if (!(neighbourIndex instanceof Int32Array) || neighbourIndex.length !== K_MAX * n) {
    return stop(`neighbourIndex must be an Int32Array of length ${K_MAX * n} (n x ${K_MAX})`);
  }
  if (!(neighbourMask instanceof Uint8Array) || neighbourMask.length !== neighbourIndex.length) {
    return stop(
      `neighbourMask must be a Uint8Array with the length of neighbourIndex (${neighbourIndex.length})`,
    );
  }
  if (!allFinite(positions)) return stop("positions contain a non-finite value");
  if (!allFinite(velocities)) return stop("velocities contain a non-finite value");
  if (!allFinite(bounds)) return stop("bounds contain a non-finite value");
  for (let i = 0; i < n; i++) {
    const t = particleType[i] as number;
    if (t < 0 || t >= nParticleTypes) return stop(`particleType holds an unknown particle type (${t})`);
  }
  for (let i = 0; i < neighbourIndex.length; i++) {
    const j = neighbourIndex[i] as number;
    if (j < 0 || j >= n) return stop(`neighbourIndex holds an index outside [0, ${n}) (${j})`);
  }
  return { ok: true };
}
