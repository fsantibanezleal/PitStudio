// Small hand-written validators shared by the dust-slider and cloud-shard loaders (DC-013-04, DC-013-05).
// They mirror the JSON Schemas in `contracts/` for the members these two headers use; the schemas stay the source of truth.

export type Json = Record<string, unknown>;

export const RUN_ID = /^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$/;
export const SENSOR_ID = /^[a-z][a-z0-9-]{0,31}$/;
export const SHA256 = /^[0-9a-f]{64}$/;
export const RELPATH =
  /^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(\/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$/;
export const SCHEMA_VERSION = /^1\.[0-9]+$/;
export const MAX_PAYLOAD_BYTES = 10_000_000;

export function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function check(condition: boolean, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

/** `value` is an object with exactly the keys `keys` (no more, no fewer). */
export function exactKeys(value: unknown, keys: readonly string[], what: string): Json {
  check(isObject(value), `${what} must be an object`);
  const got = Object.keys(value);
  check(
    got.length === keys.length && keys.every((k) => Object.hasOwn(value, k)),
    `${what} must have exactly the members ${keys.join(", ")}`,
  );
  return value;
}

export function isInt(value: unknown, min: number, max: number): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= min && value <= max;
}

export function isNum(value: unknown, min: number, max: number): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
}

export function str(value: unknown, pattern: RegExp, what: string): string {
  check(typeof value === "string" && value.length <= 255 && pattern.test(value), `${what} is malformed`);
  return value;
}

export function vec3(value: unknown, what: string, ok: (v: number) => boolean): [number, number, number] {
  check(
    Array.isArray(value) && value.length === 3 && value.every((v) => typeof v === "number" && ok(v)),
    `${what} is malformed`,
  );
  return value as [number, number, number];
}

export function payloadBlock(value: unknown): { path: string; bytes: number; sha256: string } {
  const p = exactKeys(value, ["path", "bytes", "sha256"], "payload");
  str(p.path, RELPATH, "payload.path");
  check(isInt(p.bytes, 0, MAX_PAYLOAD_BYTES), "payload.bytes is out of range");
  str(p.sha256, SHA256, "payload.sha256");
  return p as { path: string; bytes: number; sha256: string };
}

export async function sha256Hex(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data as BufferSource);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}
