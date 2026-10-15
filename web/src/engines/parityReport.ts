// Parity-report completeness at the web gate (SC-018-01, FR-018-48, FR-018-63, FR-018-64, FR-018-67). The report is DC-018-05, the
// lane measurements DC-018-06; both are validated by the generated standalone validators, then by the rules the schemas cannot
// state: the deployed commit, the engines of the table, the verdict against the tolerance of its class, the classes an engine's
// system class allows (spec 018 section 7.2) and the owner of a hosted engine's tolerance (FR-018-48).
import { validate as validateLane } from "~/contracts/validators/lane-measurements.js";
import { validate as validateReport } from "~/contracts/validators/parity-report.js";

export interface Problem {
  rule: string;
  engine?: string;
  message: string;
}

type Json = Record<string, unknown>;

const isObject = (v: unknown): v is Json => v !== null && typeof v === "object" && !Array.isArray(v);

const ANALYTICAL = ["analytical-closed-form", "analytical-iterative"];
const ML = ["ml-wasm-fp32", "ml-webgpu-fp32", "ml-fp16"];
const WGSL = ["wgsl-kernel", "wgsl-observables"];

/** The classes each engine of spec 018 section 7.1 may be judged by (section 7.2). */
export const ALLOWED_CLASSES: Readonly<Record<string, readonly string[]>> = {
  des: ["hosted"],
  policies: ["hosted"],
  haulage: ["hosted"],
  lp: ["hosted"],
  routing: ["hosted"],
  "il1-twin": ["hosted"],
  "il2-twin": ["hosted"],
  "dust-lidar": ["hosted"],
  granular: WGSL,
  swe: WGSL,
  "dust-particles": WGSL,
  gns: ML,
  forecasters: ML,
  fno: ML,
  unet: ML,
  "meta-model": ML,
  traffic: ["rigid-body-hash", ...ANALYTICAL],
  detector: ["detector-wasm", "detector-webgpu"],
  geotech: [...ANALYTICAL, "monte-carlo-count", "monte-carlo-binomial", "exact-stream"],
  plume: ANALYTICAL,
  blasting: ANALYTICAL,
  comminution: ANALYTICAL,
  volume: ANALYTICAL,
  watershed: ["label-map-exact"],
  mincut: ["min-cut"],
};

/** The requirement of the owning spec that fixes the tolerance of a hosted engine (FR-018-48). */
export const HOSTED_OWNER: Readonly<Record<string, string>> = {
  des: "FR-007-10",
  policies: "FR-007-32",
  haulage: "FR-007-15",
  lp: "FR-007-20",
  routing: "FR-007-39",
  "il1-twin": "FR-014-42",
  "il2-twin": "FR-014-42",
  "dust-lidar": "P-013-15",
};

function schemaProblems(validate: typeof validateReport, doc: unknown, what: string): Problem[] {
  if (!isObject(doc)) return [{ rule: "schema", message: `the ${what} is not a JSON object` }];
  if (validate(doc)) return [];
  const seen = new Set<string>();
  const out: Problem[] = [];
  for (const e of validate.errors ?? []) {
    const message = `${what}${e.instancePath || "/"}: ${e.message ?? e.keyword}`;
    if (!seen.has(message)) {
      seen.add(message);
      out.push({ rule: "schema", message });
    }
    if (out.length >= 10) break;
  }
  return out.length > 0 ? out : [{ rule: "schema", message: `the ${what} does not match its schema` }];
}

const num = (v: unknown): number | undefined => (typeof v === "number" ? v : undefined);

/** Whether the measured error is within the tolerance of its class; null when the class has nothing to compare. */
function within(entry: Json): boolean {
  const tol = (isObject(entry.tolerance) ? entry.tolerance : {}) as Json;
  const me = (isObject(entry.max_error) ? entry.max_error : {}) as Json;
  const cls = String(tol.class);
  const mismatches = (num(me.mismatches) ?? 0) === 0;
  const le = (a: number | undefined, b: number | undefined) => a === undefined || b === undefined || a <= b;
  if (ANALYTICAL.includes(cls)) return le(num(me.rel), num(tol.rtol)) && mismatches;
  if (cls === "label-map-exact") return le(num(me.rel), num(tol.rtol)) && mismatches;
  if (["monte-carlo-count", "exact-stream", "rigid-body-hash", "hosted"].includes(cls)) return mismatches;
  if (cls === "monte-carlo-binomial") return le(num(me.z), num(tol.sigma));
  if (cls === "min-cut") return mismatches && le(num(me.objective_rel), num(tol.objective_rtol));
  if (cls === "wgsl-kernel") return le(num(me.abs), num(tol.max_abs));
  if (cls === "wgsl-observables") {
    const measured = (isObject(me.observables) ? me.observables : {}) as Json;
    const allowed = (isObject(tol.observables) ? tol.observables : {}) as Json;
    return Object.keys(measured).every((k) => le(num(measured[k]), num(allowed[k])));
  }
  if (ML.includes(cls)) {
    const agreement = num(me.top1_agreement);
    const minimum = num(tol.top1_agreement_min);
    return (
      le(num(me.abs), num(tol.max_abs)) &&
      (agreement === undefined || minimum === undefined || agreement >= minimum)
    );
  }
  if (cls === "detector-wasm" || cls === "detector-webgpu") {
    const agreement = num(me.top1_agreement);
    const minimum = num(tol.top1_agreement_min);
    return (
      le(num(me.abs_px), num(tol.max_abs_px)) &&
      (agreement === undefined || minimum === undefined || agreement >= minimum)
    );
  }
  return true;
}

export function checkParityReport(
  report: unknown,
  opts: { commit: string; engines?: readonly string[] },
): Problem[] {
  const problems = schemaProblems(validateReport, report, "parity report");
  if (problems.length > 0 || !isObject(report)) return problems;
  if (report.git_sha !== opts.commit)
    problems.push({
      rule: "commit-mismatch",
      message: `the report is for commit ${String(report.git_sha)}, the deployed commit is ${opts.commit}`,
    });
  const entries = report.engines as Json[];
  const listed = new Set(entries.map((e) => String(e.engine)));
  for (const engine of opts.engines ?? [])
    if (!listed.has(engine))
      problems.push({ rule: "engine-missing", engine, message: `${engine}: no entry in the parity report` });
  const seen = new Set<string>();
  for (const entry of entries) {
    const engine = String(entry.engine);
    const tol = (isObject(entry.tolerance) ? entry.tolerance : {}) as Json;
    const cls = String(tol.class);
    const key = `${engine}/${cls}`;
    if (seen.has(key))
      problems.push({ rule: "duplicate-entry", engine, message: `${engine}: class ${cls} is listed twice` });
    seen.add(key);
    const allowed = ALLOWED_CLASSES[engine];
    if (allowed !== undefined && !allowed.includes(cls)) {
      problems.push({
        rule: "class-not-allowed",
        engine,
        message: `${engine}: class ${cls} is not allowed for its system class`,
      });
      continue;
    }
    if (cls === "hosted" && tol.defined_by !== HOSTED_OWNER[engine])
      problems.push({
        rule: "hosted-owner-mismatch",
        engine,
        message: `${engine}: the tolerance is defined by ${HOSTED_OWNER[engine]}, not ${String(tol.defined_by)}`,
      });
    if (entry.verdict === "pass" && !within(entry))
      problems.push({
        rule: "verdict-inconsistent",
        engine,
        message: `${engine}: verdict pass, but the error is above the tolerance of ${cls}`,
      });
    if (entry.verdict === "fail" && within(entry))
      problems.push({
        rule: "verdict-inconsistent",
        engine,
        message: `${engine}: verdict fail, but every error is within the tolerance of ${cls}`,
      });
  }
  return problems;
}

export function checkLaneMeasurements(
  doc: unknown,
  opts: { engines?: readonly string[]; artefacts?: readonly string[] } = {},
): Problem[] {
  const problems = schemaProblems(validateLane as typeof validateReport, doc, "lane measurements");
  if (problems.length > 0 || !isObject(doc)) return problems;
  const entries = doc.entries as Json[];
  const engines = new Set(entries.filter((e) => typeof e.engine === "string").map((e) => String(e.engine)));
  for (const engine of opts.engines ?? [])
    if (!engines.has(engine))
      problems.push({ rule: "engine-missing", engine, message: `${engine}: no lane measurement` });
  const seen = new Set<string>();
  for (const e of entries) {
    const subject = typeof e.engine === "string" ? `engine:${e.engine}` : `artefact:${String(e.artefact)}`;
    const id = subject.slice(subject.indexOf(":") + 1);
    if (seen.has(subject))
      problems.push({
        rule: "duplicate-entry",
        ...(typeof e.engine === "string" ? { engine: id } : {}),
        message: `${id}: measured more than once`,
      });
    seen.add(subject);
    if (
      typeof e.artefact === "string" &&
      opts.artefacts !== undefined &&
      !opts.artefacts.includes(e.artefact)
    )
      problems.push({ rule: "unknown-artefact", message: `${e.artefact}: not in the web manifest` });
  }
  return problems;
}

export type ParityRow = {
  engine: string;
  status: "pass" | "t0";
  reason: "pass" | "failing" | "not-run" | "not-listed" | "invalid";
};

/** One row per engine: pass only when every entry of the engine passes, else T0 with the reason (SC-018-01). */
export function parityStatus(report: unknown, engines: readonly string[]): ParityRow[] {
  if (schemaProblems(validateReport, report, "parity report").length > 0)
    return engines.map((engine) => ({ engine, status: "t0", reason: "invalid" }));
  const entries = (report as { engines: Json[] }).engines;
  return engines.map((engine): ParityRow => {
    const mine = entries.filter((e) => e.engine === engine);
    if (mine.length === 0) return { engine, status: "t0", reason: "not-listed" };
    if (mine.some((e) => e.verdict === "fail")) return { engine, status: "t0", reason: "failing" };
    if (mine.some((e) => e.verdict === "not_run")) return { engine, status: "t0", reason: "not-run" };
    return { engine, status: "pass", reason: "pass" };
  });
}
