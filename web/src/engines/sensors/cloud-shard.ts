// Replay point-cloud shard loader (FR-013-35, FR-013-39): validate a DC-013-04 header and its quantised payload and
// dequantise positions as offset + scale x code. A rejected shard never throws into the viewer: it shows the poster.

import {
  check,
  exactKeys,
  isInt,
  isNum,
  isObject,
  payloadBlock,
  RUN_ID,
  SCHEMA_VERSION,
  SENSOR_ID,
  sha256Hex,
  str,
  vec3,
} from "./contract-check";

export const MAX_POINTS = 1_250_000;
export const BYTES_PER_POINT = 8;

export class ShardError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ShardError";
  }
}

export interface CloudHeader {
  points: number;
  quantisation: { offset_m: [number, number, number]; scale_m: [number, number, number] };
  payload: { path: string; bytes: number; sha256: string };
  [key: string]: unknown;
}

export interface CloudShard {
  header: CloudHeader;
  points: number;
  positions: Float32Array;
  intensity: Uint8Array;
  classCode: Uint8Array;
}

const QUANTITIES = ["lidar-intensity", "radar-rcs-dbsm", "radar-radial-velocity-m-per-s"];
const SCENARIOS = ["S1", "S4a", "rain"];
const CLASS_CODE = /^([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$/;
const CLASS_LABEL = /^[a-z0-9][a-z0-9-]{0,63}$/;

function validateHeader(header: unknown): CloudHeader {
  const h = exactKeys(
    header,
    ["schema_version", "source", "points", "quantisation", "encoding", "intensity_map", "classes", "payload"],
    "header",
  );
  str(h.schema_version, SCHEMA_VERSION, "schema_version");
  const source = exactKeys(h.source, ["run_id", "scenario", "sensor", "frame"], "source");
  str(source.run_id, RUN_ID, "source.run_id");
  check(
    typeof source.scenario === "string" && SCENARIOS.includes(source.scenario),
    "source.scenario is unknown",
  );
  str(source.sensor, SENSOR_ID, "source.sensor");
  check(isInt(source.frame, 0, 4294967295), "source.frame is out of range");
  check(isInt(h.points, 0, MAX_POINTS), "points must be an integer in 0..1250000");
  const q = exactKeys(h.quantisation, ["offset_m", "scale_m"], "quantisation");
  vec3(q.offset_m, "quantisation.offset_m", (v) => Number.isFinite(v) && Math.abs(v) <= 1e8);
  vec3(q.scale_m, "quantisation.scale_m", (v) => Number.isFinite(v) && v > 0 && v <= 1);
  const enc = exactKeys(h.encoding, ["position", "intensity", "class", "byte_order", "layout"], "encoding");
  check(
    enc.position === "uint16" &&
      enc.intensity === "uint8" &&
      enc.class === "uint8" &&
      enc.byte_order === "little" &&
      enc.layout === "planar",
    "encoding differs from the contract",
  );
  const map = exactKeys(h.intensity_map, ["quantity", "low", "high"], "intensity_map");
  check(
    typeof map.quantity === "string" && QUANTITIES.includes(map.quantity),
    "intensity_map.quantity is unknown",
  );
  check(isNum(map.low, -1000, 1000) && isNum(map.high, -1000, 1000), "intensity_map limits are out of range");
  check(isObject(h.classes) && Object.keys(h.classes).length >= 1, "classes must be a non-empty object");
  for (const [code, label] of Object.entries(h.classes as Record<string, unknown>)) {
    check(CLASS_CODE.test(code), `class code ${code} is not a uint8`);
    check(typeof label === "string" && CLASS_LABEL.test(label), `class label of ${code} is malformed`);
  }
  payloadBlock(h.payload);
  return h as unknown as CloudHeader;
}

/** Validate the header, the payload size and its SHA-256, then dequantise; throws `ShardError`. */
export async function loadCloudShard(header: unknown, payload: Uint8Array): Promise<CloudShard> {
  let h: CloudHeader;
  try {
    h = validateHeader(header);
  } catch (error) {
    throw new ShardError(`shard header rejected: ${(error as Error).message}`);
  }
  const n = h.points;
  if (
    !(payload instanceof Uint8Array) ||
    payload.length !== BYTES_PER_POINT * n ||
    h.payload.bytes !== payload.length
  ) {
    throw new ShardError(`shard payload must hold ${BYTES_PER_POINT * n} bytes`);
  }
  if ((await sha256Hex(payload)) !== h.payload.sha256) throw new ShardError("shard payload digest mismatch");
  const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  const { offset_m: o, scale_m: s } = h.quantisation;
  const positions = new Float32Array(3 * n);
  for (let i = 0; i < n; i++) {
    for (let axis = 0; axis < 3; axis++) {
      positions[3 * i + axis] =
        (o[axis] as number) + (s[axis] as number) * view.getUint16(2 * axis * n + 2 * i, true);
    }
  }
  return {
    header: h,
    points: n,
    positions,
    intensity: payload.slice(6 * n, 7 * n),
    classCode: payload.slice(7 * n, 8 * n),
  };
}

/** The shard, or `showPoster` when it is rejected; never throws. */
export async function prepareReplay(
  header: unknown,
  payload: Uint8Array,
): Promise<{ ok: true; shard: CloudShard } | { ok: false; showPoster: true }> {
  try {
    return { ok: true, shard: await loadCloudShard(header, payload) };
  } catch {
    return { ok: false, showPoster: true };
  }
}
