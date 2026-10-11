// Shared, locked test support (first used by T-018-012; later engine tasks import it). Not a test file.
//
// Reads the spec's own corpus of engine request and result examples (DC-018-02): `index-engines.json` lists every example
// under specs/018-web-cases/contracts/examples/ with its schema target, whether it is valid, and for hostile ones the class
// of defect. These were hand-built by the spec author, so they are an oracle independent of the code under test.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const EXAMPLES = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../specs/018-web-cases/contracts/examples",
);

/** The 25 engine ids of spec 018 section 7.1 (also the file stems of contracts/engines/). */
export const ENGINE_IDS = [
  "des",
  "policies",
  "haulage",
  "lp",
  "routing",
  "il1-twin",
  "il2-twin",
  "granular",
  "gns",
  "traffic",
  "dust-lidar",
  "detector",
  "geotech",
  "forecasters",
  "swe",
  "fno",
  "plume",
  "dust-particles",
  "blasting",
  "watershed",
  "unet",
  "comminution",
  "meta-model",
  "mincut",
  "volume",
] as const;
export type EngineId = (typeof ENGINE_IDS)[number];

export type ErrorCode =
  | "E_SCHEMA"
  | "E_RANGE"
  | "E_NONFINITE"
  | "E_SIZE"
  | "E_UNKNOWN_ENGINE"
  | "E_TIMEOUT"
  | "E_RUNTIME";

export interface EngineExample {
  file: string;
  engine: EngineId;
  /** "input" for a request example, "output" for a result example (from the schema target). */
  direction: "input" | "output";
  valid: boolean;
  note?: string;
  klass?: string;
  pointer?: string;
  keyword?: string;
  rule?: string;
  doc: Record<string, unknown>;
}

interface IndexEntry {
  file: string;
  schema: string;
  target: string;
  valid: boolean;
  note?: string;
  class?: string;
  pointer?: string;
  keyword?: string;
  rule?: string;
}

export function loadEngineExamples(): EngineExample[] {
  const index = JSON.parse(readFileSync(resolve(EXAMPLES, "index-engines.json"), "utf8")) as {
    examples: IndexEntry[];
  };
  return index.examples.map((e) => {
    const doc = JSON.parse(readFileSync(resolve(EXAMPLES, e.file), "utf8")) as Record<string, unknown>;
    const engine = e.schema.replace(/^engines\//, "").replace(/\.schema\.json$/, "") as EngineId;
    const direction: "input" | "output" =
      e.target.endsWith("output") || doc.kind === "output" ? "output" : "input";
    return {
      file: e.file,
      engine,
      direction,
      valid: e.valid,
      note: e.note,
      klass: e.class,
      pointer: e.pointer,
      keyword: e.keyword,
      rule: e.rule,
      doc,
    };
  });
}

/**
 * The typed error the host must answer a hostile REQUEST example with (FR-018-39, FR-018-40), derived from the author's
 * defect class. Hand-written mapping of the spec text:
 *   oversized ...                    -> E_SIZE   (a size cap of section 7.1 / the schema maxima)
 *   out of range, wrong unit ...     -> E_RANGE  (value outside the declared validity range)
 *   empty ...                        -> E_SCHEMA or E_RANGE (FR-018-39 does not say which; see the report, ambiguity)
 *   everything else (unknown enum or field, wrong shape or dtype, bad pattern, missing required, conditional rule)
 *                                    -> E_SCHEMA
 */
export function expectedCodes(ex: EngineExample): ErrorCode[] {
  const c = ex.klass ?? "";
  if (/^oversized/.test(c)) return ["E_SIZE"];
  if (/^(out of range|wrong unit)/.test(c)) return ["E_RANGE"];
  if (/^empty/.test(c)) return ["E_SCHEMA", "E_RANGE"];
  return ["E_SCHEMA"];
}

/** Every finite number leaf of a JSON value, as a path of keys and indices. */
export function numericPaths(
  value: unknown,
  prefix: Array<string | number> = [],
): Array<Array<string | number>> {
  if (typeof value === "number" && Number.isFinite(value)) return [prefix];
  if (Array.isArray(value)) return value.flatMap((v, i) => numericPaths(v, [...prefix, i]));
  if (value !== null && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).flatMap(([k, v]) =>
      numericPaths(v, [...prefix, k]),
    );
  }
  return [];
}

/** A deep copy of `doc` with the number at `path` replaced. */
export function withValueAt<T>(doc: T, path: Array<string | number>, replacement: unknown): T {
  const copy = structuredClone(doc) as unknown;
  let node = copy as Record<string | number, unknown>;
  for (const key of path.slice(0, -1)) node = node[key] as Record<string | number, unknown>;
  node[path[path.length - 1] as string | number] = replacement;
  return copy as T;
}
