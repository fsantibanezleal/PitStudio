// Hostile-input guard of the `fno` engine (FR-011-40): the web twin of pitstudio_pipeline.surrogates.fno.infer.FnoPredictor.validate.
//
// Never throws: a bad input gives { ok: false, message: "field not computed — <reason>" } (the em dash is part of the string fixed by
// the spec), the reason names the offending argument (shape, channels, x, patchId), and no field is computed.
const PREFIX = "field not computed — ";
export const GRID = 64;

export interface FnoInputs {
  x: Float32Array;
  shape: number[];
  channels: string[];
  patchId: string;
}

export interface FnoDescription {
  channels: string[];
  knownPatches: ReadonlySet<string>;
}

export type GuardResult = { ok: true } | { ok: false; message: string };

function stop(reason: string): GuardResult {
  return { ok: false, message: PREFIX + reason };
}

export function validateFnoInputs(inputs: FnoInputs, io: FnoDescription): GuardResult {
  if (inputs === null || typeof inputs !== "object") return stop("inputs are missing");
  const { x, shape, channels, patchId } = inputs;
  const expected = [1, io.channels.length, GRID, GRID];
  if (
    !Array.isArray(shape) ||
    shape.length !== expected.length ||
    !shape.every((d, i) => Number.isInteger(d) && d === expected[i])
  ) {
    return stop(`shape ${JSON.stringify(shape)} is not [${expected.join(", ")}]`);
  }
  const size = expected.reduce((a, b) => a * b, 1);
  if (!(x instanceof Float32Array) || x.length !== size) {
    return stop(`shape: the data must be a Float32Array of ${size} values (x)`);
  }
  if (
    !Array.isArray(channels) ||
    channels.length !== io.channels.length ||
    !channels.every((c, i) => c === io.channels[i])
  ) {
    return stop(
      `channels ${JSON.stringify(channels)} differ from the model's channel order [${io.channels.join(", ")}]`,
    );
  }
  for (let i = 0; i < x.length; i++) {
    if (!Number.isFinite(x[i] as number)) return stop(`x holds a non-finite value at index ${i}`);
  }
  if (typeof patchId !== "string" || !io.knownPatches.has(patchId)) {
    return stop(`patchId ${JSON.stringify(patchId)} is not a published patch`);
  }
  return { ok: true };
}
