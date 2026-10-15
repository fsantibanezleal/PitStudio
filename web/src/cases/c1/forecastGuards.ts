// Context guards of the C1 slope forecaster in the browser (FR-010-29; the Python half is pipeline slope/infer.py).
// DC-010-05 describes the forecaster input: `context` float32 shape [1, 2, 128], channel 0 the scaled inverse velocity,
// channel 1 the mask (1 where a block has data). A context that breaks that description gives no forecast, with a reason
// that names the offending property; nothing is thrown, whatever the input.

export interface ForecastContext {
  data: ArrayLike<number>;
  shape: number[];
  dtype: string;
}

export type ForecastGuardResult = { ok: true } | { ok: false; message: string };

const CONTEXT_LENGTH = 128;
const CHANNELS = 2;
const PREFIX = "no forecast — ";

const refuse = (reason: string): ForecastGuardResult => ({ ok: false, message: `${PREFIX}${reason}` });

export function validateForecastContext(ctx: ForecastContext): ForecastGuardResult {
  const shape = ctx?.shape;
  if (!Array.isArray(shape)) return refuse("shape is missing");
  if (shape.length !== 3 || shape[0] !== 1 || shape[1] !== CHANNELS) {
    return refuse(`shape [${shape.join(", ")}] is not [1, ${CHANNELS}, ${CONTEXT_LENGTH}]`);
  }
  if (shape[2] !== CONTEXT_LENGTH) {
    return refuse(`context length ${String(shape[2])} is not ${CONTEXT_LENGTH}`);
  }
  const data = ctx.data;
  if (data === null || typeof data !== "object" || typeof data.length !== "number") {
    return refuse("context length is unknown: no data array");
  }
  if (data.length !== CHANNELS * CONTEXT_LENGTH) {
    return refuse(
      `context length ${data.length} does not match the shape (${CHANNELS * CONTEXT_LENGTH} values)`,
    );
  }
  if (ctx.dtype !== "float32") return refuse(`dtype ${JSON.stringify(ctx.dtype)} is not float32`);
  for (let i = 0; i < data.length; i++) {
    if (!Number.isFinite(data[i])) return refuse(`non-finite value at index ${i}`);
  }
  let positive = false;
  for (let i = CONTEXT_LENGTH; i < data.length; i++) {
    if ((data[i] as number) > 0) {
      positive = true;
      break;
    }
  }
  if (!positive) return refuse("no positive velocity in the context (every block is masked)");
  return { ok: true };
}
