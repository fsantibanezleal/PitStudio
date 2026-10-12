// Typed message protocol of the engine host (FR-018-38..40): requests are DC-018-02 `input` documents, answers are `output`
// documents or typed errors. Validation is by the generated standalone validators; a request is never mutated and nothing here
// throws or evals. NaN and infinities are checked before the schema (E_NONFINITE).
import { ENGINE_VALIDATORS } from "./generated/index.js";

export type ErrorCode =
  | "E_SCHEMA"
  | "E_RANGE"
  | "E_NONFINITE"
  | "E_SIZE"
  | "E_UNKNOWN_ENGINE"
  | "E_TIMEOUT"
  | "E_RUNTIME";

export const ENGINE_ERROR_CODES: readonly ErrorCode[] = [
  "E_SCHEMA",
  "E_RANGE",
  "E_NONFINITE",
  "E_SIZE",
  "E_UNKNOWN_ENGINE",
  "E_TIMEOUT",
  "E_RUNTIME",
];

export interface EngineError {
  kind: "error";
  code: ErrorCode;
  message: string;
  detail?: { pointer?: string; cap?: number | string; name?: string };
}

export interface EngineRequest {
  kind: "input";
  engine: string;
  engine_version: string;
  function: string;
  args: Record<string, unknown>;
  [key: string]: unknown;
}

export interface EngineResult {
  kind: "output";
  engine: string;
  [key: string]: unknown;
}

export type RequestOutcome = { ok: true; request: EngineRequest } | { ok: false; error: EngineError };
export type ResultOutcome = { ok: true; result: EngineResult } | { ok: false; error: EngineError };

const MAX_DEPTH = 64;
const MAX_POINTER = 200;

export function engineError(code: ErrorCode, message: string, detail?: EngineError["detail"]): EngineError {
  const error: EngineError = { kind: "error", code, message };
  if (detail) error.detail = detail;
  return error;
}

/** A printable, bounded rendering of a JSON pointer: control and bidi characters never reach a message. */
function safe(text: string): string {
  // biome-ignore lint/suspicious/noControlCharactersInRegex: stripping controls is the point
  const cleaned = text.replace(/[\u0000-\u001f\u007f-\u009f‎‏‪-‮⁦-⁩<>"'`]/g, "?");
  return cleaned.length > MAX_POINTER ? `${cleaned.slice(0, MAX_POINTER)}...` : cleaned;
}

/** Path of the first NaN or infinity in a JSON-like value, or null. Bounded in depth, never throws. */
function findNonFinite(value: unknown, path: string, depth: number): string | null {
  if (typeof value === "number") return Number.isFinite(value) ? null : path;
  if (depth > MAX_DEPTH || value === null || typeof value !== "object") return null;
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++) {
      const hit = findNonFinite(value[i], `${path}/${i}`, depth + 1);
      if (hit !== null) return hit;
    }
    return null;
  }
  if (ArrayBuffer.isView(value)) {
    const view = value as unknown as ArrayLike<number | bigint>;
    for (let i = 0; i < view.length; i++) {
      const v = view[i];
      if (typeof v === "number" && !Number.isFinite(v)) return `${path}/${i}`;
    }
    return null;
  }
  for (const key of Object.keys(value as object)) {
    const hit = findNonFinite((value as Record<string, unknown>)[key], `${path}/${key}`, depth + 1);
    if (hit !== null) return hit;
  }
  return null;
}

interface AjvErrorLike {
  keyword: string;
  instancePath: string;
  schemaPath: string;
  params: Record<string, unknown>;
}

const RANGE_KEYWORDS = new Set(["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"]);
const SIZE_KEYWORDS = new Set(["maxItems", "maxLength", "maxProperties"]);
/** Keywords that say the value has the wrong form, whatever its size or magnitude. */
const FORM_KEYWORDS = new Set([
  "type",
  "enum",
  "required",
  "additionalProperties",
  "pattern",
  "dependentRequired",
  "propertyNames",
  "unevaluatedProperties",
  "minItems",
  "minLength",
  "minProperties",
  "uniqueItems",
]);

function limitOf(e: AjvErrorLike): number | string {
  const p = e.params;
  const v = p.limit ?? p.allowedValue ?? p.comparison;
  return typeof v === "number" || typeof v === "string" ? v : "the cap";
}

/** Maps schema violations to the typed error of FR-018-39 (E_SCHEMA, E_RANGE) and FR-018-40 (E_SIZE naming the cap). */
/** The value at a JSON pointer of the document, or undefined. */
function instanceAt(doc: unknown, pointer: string): unknown {
  let node: unknown = doc;
  for (const part of pointer.split("/").slice(1)) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string, unknown>)[part.replaceAll("~1", "/").replaceAll("~0", "~")];
  }
  return node;
}

/**
 * The U-Net tile is a fixed 512 x 512 window, expressed as a `const` in the schema; a larger image is a request over the
 * size of the engine (FR-018-40: `E_SIZE`), while the same `const` on the detector's 640 x 640 input is a wrong shape.
 * The schema cannot tell the two apart, so the engine and the dimension are named here.
 */
function isOversizedTile(engine: string, e: AjvErrorLike, value: unknown): boolean {
  return (
    engine === "unet" &&
    e.keyword === "const" &&
    /^\/args\/tile\/shape\/(rows|cols)$/.test(e.instancePath) &&
    typeof value === "number" &&
    typeof e.params.allowedValue === "number" &&
    value > e.params.allowedValue
  );
}

function classify(
  engine: string,
  raw: unknown,
  all: readonly AjvErrorLike[],
  sizeCaps: readonly string[],
  fixedShapes: readonly string[],
): EngineError {
  const caps = new Set(sizeCaps);
  const fixed = new Set(fixedShapes);
  // Ajv reports a path relative to the `$defs` entry it inlined, so both sides drop that first segment.
  const schemaPathNoKeyword = (e: AjvErrorLike) =>
    e.schemaPath.slice(0, e.schemaPath.lastIndexOf("/")).replace(/^#\/\$defs\/[^/]+/, "#");
  /** A numeric `const` is a fixed parameter (a range); under `/shape/` or on a string it is a wrong form. */
  const isRangeConst = (e: AjvErrorLike) =>
    e.keyword === "const" && typeof e.params.allowedValue === "number" && !e.instancePath.includes("/shape/");
  // `unevaluatedProperties` and the conditional wrappers only repeat a failure found deeper in the document.
  const real = all.filter((e) => e.keyword !== "unevaluatedProperties");
  const errors = real.length > 0 ? real : all;
  const isSize = (e: AjvErrorLike) =>
    (SIZE_KEYWORDS.has(e.keyword) && !fixed.has(schemaPathNoKeyword(e))) ||
    ((e.keyword === "maximum" || e.keyword === "const") && caps.has(schemaPathNoKeyword(e))) ||
    isOversizedTile(engine, e, instanceAt(raw, e.instancePath));
  const sizeErr = errors.find(isSize);
  if (sizeErr) {
    const cap = limitOf(sizeErr);
    const pointer = safe(sizeErr.instancePath || "/");
    return engineError("E_SIZE", `size cap exceeded at ${pointer}: the cap is ${cap}`, { pointer, cap });
  }
  const rest = errors.filter((e) => e.keyword !== "if" && e.keyword !== "oneOf" && e.keyword !== "anyOf");
  const form = rest.find((e) => FORM_KEYWORDS.has(e.keyword) || (e.keyword === "const" && !isRangeConst(e)));
  if (form) {
    const pointer = safe(form.instancePath || "/");
    return engineError("E_SCHEMA", `schema violation (${form.keyword}) at ${pointer}`, { pointer });
  }
  const range = rest.find((e) => RANGE_KEYWORDS.has(e.keyword) || isRangeConst(e));
  if (range) {
    const pointer = safe(range.instancePath || "/");
    return engineError("E_RANGE", `value out of range (${range.keyword}) at ${pointer}`, { pointer });
  }
  const first = rest[0] ?? errors[0];
  const pointer = safe(first?.instancePath || "/");
  return engineError("E_SCHEMA", `schema violation (${first?.keyword ?? "schema"}) at ${pointer}`, {
    pointer,
  });
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function validateRequest(
  raw: unknown,
  opts: { loaded?: Record<string, string> } = {},
): RequestOutcome {
  try {
    if (!isPlainObject(raw))
      return { ok: false, error: engineError("E_SCHEMA", "a request must be an object") };
    const bad = findNonFinite(raw, "", 0);
    if (bad !== null) {
      return {
        ok: false,
        error: engineError("E_NONFINITE", `a number is not finite at ${safe(bad || "/")}`, {
          pointer: safe(bad || "/"),
        }),
      };
    }
    if (raw.kind !== "input") {
      return {
        ok: false,
        error: engineError("E_SCHEMA", "the document is not a request (kind must be input)"),
      };
    }
    const engine = raw.engine;
    const known = typeof engine === "string" && Object.hasOwn(ENGINE_VALIDATORS, engine);
    if (!known)
      return {
        ok: false,
        error: engineError("E_UNKNOWN_ENGINE", "the engine id is not one of the engine table"),
      };
    const id = engine as string;
    const loaded = opts.loaded;
    if (loaded && Object.hasOwn(loaded, id) && raw.engine_version !== loaded[id]) {
      return {
        ok: false,
        error: engineError(
          "E_SCHEMA",
          `engine_version does not match the loaded engine (${safe(String(loaded[id]))})`,
          {
            pointer: "/engine_version",
          },
        ),
      };
    }
    const module = ENGINE_VALIDATORS[id];
    if (!module) return { ok: false, error: engineError("E_UNKNOWN_ENGINE", "no validator for this engine") };
    if (module.validateInput(raw)) return { ok: true, request: raw as EngineRequest };
    return {
      ok: false,
      error: classify(
        id,
        raw,
        (module.validateInput.errors ?? []) as AjvErrorLike[],
        module.SIZE_CAPS,
        module.FIXED_SHAPES,
      ),
    };
  } catch {
    return { ok: false, error: engineError("E_SCHEMA", "the request could not be read") };
  }
}

export function validateResult(raw: unknown): ResultOutcome {
  try {
    if (!isPlainObject(raw))
      return { ok: false, error: engineError("E_SCHEMA", "a result must be an object") };
    const bad = findNonFinite(raw, "", 0);
    if (bad !== null) {
      return {
        ok: false,
        error: engineError("E_NONFINITE", `a number is not finite at ${safe(bad || "/")}`),
      };
    }
    if (raw.kind !== "output")
      return {
        ok: false,
        error: engineError("E_SCHEMA", "the document is not a result (kind must be output)"),
      };
    const engine = raw.engine;
    if (typeof engine !== "string" || !Object.hasOwn(ENGINE_VALIDATORS, engine)) {
      return {
        ok: false,
        error: engineError("E_UNKNOWN_ENGINE", "the engine id is not one of the engine table"),
      };
    }
    const module = ENGINE_VALIDATORS[engine];
    if (module?.validateOutput(raw)) return { ok: true, result: raw as EngineResult };
    return {
      ok: false,
      error: classify(
        engine,
        raw,
        (module?.validateOutput.errors ?? []) as AjvErrorLike[],
        module?.SIZE_CAPS ?? [],
        module?.FIXED_SHAPES ?? [],
      ),
    };
  } catch {
    return { ok: false, error: engineError("E_SCHEMA", "the result could not be read") };
  }
}
