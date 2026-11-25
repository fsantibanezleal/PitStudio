// Shared argument guards for the teaching functions (FR-020-50): a RangeError that names the argument, never a value.

/** Throws a RangeError naming `name` unless `v` is a finite number. */
export function finite(name: string, v: unknown): number {
  if (typeof v !== "number" || !Number.isFinite(v)) {
    throw new RangeError(`${name} must be a finite number`);
  }
  return v;
}

/** Throws a RangeError naming `name` unless `v` is a finite number > 0. */
export function positive(name: string, v: unknown): number {
  const n = finite(name, v);
  if (!(n > 0)) throw new RangeError(`${name} must be greater than 0`);
  return n;
}

/** Throws a RangeError naming `name` unless `v` is a finite number >= 0. */
export function nonNegative(name: string, v: unknown): number {
  const n = finite(name, v);
  if (n < 0) throw new RangeError(`${name} must be at least 0`);
  return n;
}
