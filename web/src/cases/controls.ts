// Numeric controls of the engine panels (FR-018-40, FR-018-41): a text is accepted only if it is a plain decimal number inside
// the control's range; a size control clamps a larger number to its cap; everything else is rejected, and the control keeps its
// last valid value. Nothing here throws.

export interface ControlSpec {
  name: string;
  value: number;
  min: number;
  max: number;
  unit: string;
  /** The size cap of the engine table (section 7.1) when the control sets a size; equals `max`. */
  cap?: number;
}

export type ControlParse =
  | { kind: "ok"; value: number }
  | { kind: "clamped"; value: number; cap: number }
  | { kind: "rejected" };

/** ASCII decimal numbers only: no hexadecimal, no digit group separators, no non-ASCII digits, no NaN or Infinity words. */
const DECIMAL = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;
const MAX_TEXT = 64;

export function parseControl(text: unknown, spec: Pick<ControlSpec, "min" | "max" | "cap">): ControlParse {
  if (typeof text !== "string") return { kind: "rejected" };
  const trimmed = text.trim();
  if (trimmed.length === 0 || trimmed.length > MAX_TEXT || !DECIMAL.test(trimmed))
    return { kind: "rejected" };
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value < spec.min) return { kind: "rejected" };
  if (value <= spec.max) return { kind: "ok", value };
  if (spec.cap !== undefined && Number.isFinite(spec.cap))
    return { kind: "clamped", value: spec.cap, cap: spec.cap };
  return { kind: "rejected" };
}
