// Dust-slider worker core (FR-013-38, FR-013-39, P-013-15): decode a baked S1 frame and apply the calibrated detection
// rule at any of the 41 slider levels. Pure functions of the frame and the level; no DOM, no global state.
// The Python reference is `pitstudio.sensors.dust` (rule) and `pitstudio.sensors.quantise.bake_slider` (bake).

import {
  check,
  exactKeys,
  isInt,
  isNum,
  payloadBlock,
  RUN_ID,
  SCHEMA_VERSION,
  SENSOR_ID,
  sha256Hex,
  str,
  vec3,
} from "./contract-check";

export const LEVELS = 41;
export const MAX_RETURNS = 150_000;
export const BYTES_PER_RETURN = 20;
export const UNAVAILABLE_MESSAGE = "dust model unavailable — clean frame shown";
const LABEL = "own Beer–Lambert dust model";

export class SliderAssetError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SliderAssetError";
  }
}

export interface SliderHeader {
  schema_version: string;
  source: { run_id: string; sensor: string; frame: number };
  returns: number;
  levels: number;
  k: number[];
  tau_ref: number;
  rule: { tau_on: number; tau_floor_retro: number; tau_floor_diffuse: number };
  dust_return_intensity: number;
  material_codes: { retro: number; diffuse: number; dust: number };
  label: string;
  quantisation: { offset_m: number[]; scale_m: number[] };
  encoding: Record<string, string>;
  payload: { path: string; bytes: number; sha256: string };
}

export interface SliderFrame {
  header: SliderHeader;
  count: number;
  tauUnit: Float32Array;
  rEdge: Float32Array;
  hash: Uint32Array;
  intensityCode: Uint8Array;
  classCode: Uint8Array;
  x: Uint16Array;
  y: Uint16Array;
  z: Uint16Array;
}

export interface Attenuated {
  kept: Uint8Array;
  emit: Uint8Array;
  dustCount: number;
  dustREdge: Float64Array;
  intensity: Float64Array;
  display: Uint8Array;
  dustDisplay: number;
}

const ENCODING = {
  position: "uint16",
  intensity: "uint8",
  class: "uint8",
  tau_unit: "float32",
  r_edge_m: "float32",
  hash: "uint32",
  byte_order: "little",
  layout: "planar",
} as const;

function validateHeader(header: unknown): SliderHeader {
  const h = exactKeys(
    header,
    [
      "schema_version",
      "source",
      "returns",
      "levels",
      "k",
      "tau_ref",
      "rule",
      "dust_return_intensity",
      "material_codes",
      "label",
      "quantisation",
      "encoding",
      "payload",
    ],
    "header",
  );
  str(h.schema_version, SCHEMA_VERSION, "schema_version");
  const source = exactKeys(h.source, ["run_id", "sensor", "frame"], "source");
  str(source.run_id, RUN_ID, "source.run_id");
  str(source.sensor, SENSOR_ID, "source.sensor");
  check(isInt(source.frame, 0, 4294967295), "source.frame is out of range");
  check(isInt(h.returns, 1, MAX_RETURNS), "returns must be an integer in 1..150000");
  check(h.levels === LEVELS, "levels must be 41");
  check(
    Array.isArray(h.k) && h.k.length === LEVELS && h.k.every((v) => isNum(v, 0, 1_000_000)),
    "k must hold 41 numbers in [0, 1e6]",
  );
  check(isNum(h.tau_ref, 0, 100) && h.tau_ref > 0, "tau_ref must be in (0, 100]");
  const rule = exactKeys(h.rule, ["tau_on", "tau_floor_retro", "tau_floor_diffuse"], "rule");
  check(
    rule.tau_on === 0.3216 && rule.tau_floor_retro === 3.912 && rule.tau_floor_diffuse === 2.8134,
    "rule constants differ from the contract",
  );
  check(isNum(h.dust_return_intensity, 0, 1), "dust_return_intensity must be in [0, 1]");
  const codes = exactKeys(h.material_codes, ["retro", "diffuse", "dust"], "material_codes");
  check(
    Object.values(codes).every((v) => isInt(v, 0, 255)),
    "material_codes must be uint8 integers",
  );
  check(h.label === LABEL, "label must name the own dust model");
  const q = exactKeys(h.quantisation, ["offset_m", "scale_m"], "quantisation");
  vec3(q.offset_m, "quantisation.offset_m", (v) => Number.isFinite(v) && Math.abs(v) <= 1e8);
  vec3(q.scale_m, "quantisation.scale_m", (v) => Number.isFinite(v) && v > 0 && v <= 1);
  const enc = exactKeys(h.encoding, Object.keys(ENCODING), "encoding");
  check(
    Object.entries(ENCODING).every(([key, want]) => enc[key] === want),
    "encoding differs from the contract",
  );
  payloadBlock(h.payload);
  return h as unknown as SliderHeader;
}

/** Validate a baked header and payload (DC-013-05) and decode the planes; rejects with `SliderAssetError`. */
export async function loadSliderAsset(header: unknown, payload: Uint8Array): Promise<SliderFrame> {
  let h: SliderHeader;
  try {
    h = validateHeader(header);
  } catch (error) {
    throw new SliderAssetError(`slider header rejected: ${(error as Error).message}`);
  }
  const n = h.returns;
  if (
    !(payload instanceof Uint8Array) ||
    payload.length !== BYTES_PER_RETURN * n ||
    h.payload.bytes !== payload.length
  ) {
    throw new SliderAssetError(`slider payload must hold ${BYTES_PER_RETURN * n} bytes`);
  }
  if ((await sha256Hex(payload)) !== h.payload.sha256)
    throw new SliderAssetError("slider payload digest mismatch");
  const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  const u16 = (offset: number): Uint16Array =>
    Uint16Array.from({ length: n }, (_, i) => view.getUint16(offset + 2 * i, true));
  const tauUnit = new Float32Array(n);
  const rEdge = new Float32Array(n);
  const hash = new Uint32Array(n);
  for (let i = 0; i < n; i++) {
    tauUnit[i] = view.getFloat32(8 * n + 4 * i, true);
    rEdge[i] = view.getFloat32(12 * n + 4 * i, true);
    hash[i] = view.getUint32(16 * n + 4 * i, true);
    if (!Number.isFinite(tauUnit[i]) || (tauUnit[i] as number) < 0) {
      throw new SliderAssetError(`tau_unit of return ${i} must be finite and non-negative`);
    }
    if (!Number.isFinite(rEdge[i])) throw new SliderAssetError(`r_edge of return ${i} must be finite`);
  }
  return {
    header: h,
    count: n,
    tauUnit,
    rEdge,
    hash,
    intensityCode: payload.slice(6 * n, 7 * n),
    classCode: payload.slice(7 * n, 8 * n),
    x: u16(0),
    y: u16(2 * n),
    z: u16(4 * n),
  };
}

/** The slider asset, or a panel-ready message when it is rejected; never throws. */
export async function prepareSlider(
  header: unknown,
  payload: Uint8Array,
): Promise<{ ok: true; frame: SliderFrame } | { ok: false; message: string }> {
  try {
    return { ok: true, frame: await loadSliderAsset(header, payload) };
  } catch {
    return { ok: false, message: UNAVAILABLE_MESSAGE };
  }
}

/** The clean frame: every return kept with its baked intensity and no dust return. */
export function cleanFrame(frame: SliderFrame): Attenuated {
  const n = frame.count;
  return {
    kept: new Uint8Array(n).fill(1),
    emit: new Uint8Array(n),
    dustCount: 0,
    dustREdge: new Float64Array(0),
    intensity: Float64Array.from(frame.intensityCode),
    display: frame.intensityCode.slice(),
    dustDisplay: Math.floor(255 * frame.header.dust_return_intensity + 0.5),
  };
}

/** Apply slider level 0..40: tau = k[level] x tau_unit, the keep rule of FR-013-12 and the dust returns of FR-013-13. */
export function attenuate(
  frame: SliderFrame,
  level: number,
  options: { maxReturns?: number } = {},
): Attenuated {
  if (typeof level !== "number") throw new TypeError("level must be a number");
  if (!Number.isInteger(level) || level < 0 || level >= LEVELS) {
    throw new RangeError(`level must be an integer in 0..${LEVELS - 1}, got ${level}`);
  }
  const maxReturns = options.maxReturns ?? 1;
  const { rule, material_codes: codes, k } = frame.header;
  const kLevel = k[level] as number;
  const n = frame.count;
  const kept = new Uint8Array(n);
  const emit = new Uint8Array(n);
  const intensity = new Float64Array(n);
  const display = new Uint8Array(n);
  const edges: number[] = [];
  for (let i = 0; i < n; i++) {
    const tau = kLevel * (frame.tauUnit[i] as number);
    const u = (frame.hash[i] as number) / 2 ** 32;
    const floor = frame.classCode[i] === codes.retro ? rule.tau_floor_retro : rule.tau_floor_diffuse;
    const keep = tau <= rule.tau_on || (tau <= floor && u * (floor - rule.tau_on) < floor - tau);
    kept[i] = keep ? 1 : 0;
    if (tau > rule.tau_on && (!keep || maxReturns >= 2)) {
      emit[i] = 1;
      edges.push(frame.rEdge[i] as number);
    }
    intensity[i] = (frame.intensityCode[i] as number) * Math.exp(-2 * tau);
    display[i] = Math.min(255, Math.max(0, Math.floor((intensity[i] as number) + 0.5)));
  }
  return {
    kept,
    emit,
    dustCount: edges.length,
    dustREdge: Float64Array.from(edges),
    intensity,
    display,
    dustDisplay: Math.floor(255 * frame.header.dust_return_intensity + 0.5),
  };
}
