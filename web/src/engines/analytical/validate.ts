// Argument checks shared by the analytical engines: a wrong type is E_SCHEMA, a number outside its domain is E_RANGE.
import { rangeError, schemaError } from "./errors";

export interface Bounds {
  lo?: number;
  hi?: number;
  loOpen?: boolean;
  hiOpen?: boolean;
}

export function asObject(value: unknown, name: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    throw schemaError(`${name} must be an object`);
  return value as Record<string, unknown>;
}

export function asArray(value: unknown, name: string, min = 0, max = Number.POSITIVE_INFINITY): unknown[] {
  if (!Array.isArray(value)) throw schemaError(`${name} must be an array`);
  if (value.length < min || value.length > max)
    throw rangeError(`${name} must hold ${min} to ${max} entries, got ${value.length}`);
  return value;
}

export function asNumber(value: unknown, name: string, b: Bounds = {}): number {
  if (typeof value !== "number") throw schemaError(`${name} must be a number`);
  if (!Number.isFinite(value)) throw rangeError(`${name} must be finite`);
  const { lo, hi, loOpen, hiOpen } = b;
  if (lo !== undefined && (loOpen ? value <= lo : value < lo))
    throw rangeError(`${name} is below its range (${value})`);
  if (hi !== undefined && (hiOpen ? value >= hi : value > hi))
    throw rangeError(`${name} is above its range (${value})`);
  return value;
}

export function asInteger(value: unknown, name: string, b: Bounds = {}): number {
  const n = asNumber(value, name, b);
  if (!Number.isInteger(n)) throw schemaError(`${name} must be an integer`);
  return n;
}

export function optional<T>(value: unknown, make: (v: unknown) => T, fallback: T): T {
  return value === undefined ? fallback : make(value);
}
