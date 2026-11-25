// The engines of specs 007, 013 and 014 run only through this spec's host and tiers (FR-018-48), and the verdicts of their own suites are
// written into the parity report (DC-018-05) so that the parity gate of FR-018-63 applies to them: a failing hosted engine runs in T0.
import type { EngineBackend } from "./host";
import type { EngineRequest } from "./protocol";

export type HostedId =
  | "des"
  | "policies"
  | "haulage"
  | "lp"
  | "routing"
  | "dust-lidar"
  | "il1-twin"
  | "il2-twin";

export const HOSTED_ENGINES: Readonly<Record<HostedId, { spec: "007" | "013" | "014"; definedBy: string }>> =
  {
    des: { spec: "007", definedBy: "FR-007-10" },
    policies: { spec: "007", definedBy: "FR-007-32" },
    haulage: { spec: "007", definedBy: "FR-007-15" },
    lp: { spec: "007", definedBy: "FR-007-20" },
    routing: { spec: "007", definedBy: "FR-007-39" },
    "dust-lidar": { spec: "013", definedBy: "P-013-15" },
    "il1-twin": { spec: "014", definedBy: "FR-014-42" },
    "il2-twin": { spec: "014", definedBy: "FR-014-42" },
  };

const isHosted = (id: string): id is HostedId => Object.hasOwn(HOSTED_ENGINES, id);

export interface HostedModule {
  run(request: unknown, ctx: { signal: AbortSignal }): Promise<unknown>;
  terminate(): void;
}

/** The host backend of a hosted engine: the owning module's code is reached only through its `run`. */
export function hostedBackend(engineId: string, module: HostedModule): EngineBackend {
  if (!isHosted(engineId))
    throw new RangeError(`${JSON.stringify(engineId)} is not an engine of specs 007, 013 or 014`);
  return {
    runtime: `hosted-${HOSTED_ENGINES[engineId].spec}`,
    run: (request: EngineRequest, ctx: { signal: AbortSignal }) => module.run(request, ctx),
    terminate: () => module.terminate(),
  };
}

export interface HostedSuiteResult {
  engine: string;
  version: string;
  definedBy: string;
  browsers: string[];
  files: number;
  vectors: number;
  mismatches: number;
  verdict: "pass" | "fail" | "not_run";
  reason?: string;
}

interface ParityReportLike {
  engines: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

const BROWSERS = ["chromium", "firefox", "webkit"];

function count(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0)
    throw new RangeError(`${name} must be a non-negative integer`);
  return value;
}

function entryOf(r: HostedSuiteResult): Record<string, unknown> {
  if (!isHosted(r.engine)) throw new RangeError(`${r.engine}: not a hosted engine`);
  const owner = HOSTED_ENGINES[r.engine].definedBy;
  if (r.definedBy !== owner)
    throw new RangeError(`${r.engine}: the tolerance is defined by ${owner}, not ${r.definedBy}`);
  const files = count(r.files, "files");
  const vectors = count(r.vectors, "vectors");
  const mismatches = count(r.mismatches, "mismatches");
  if (files < 1 || vectors < 1) throw new RangeError(`${r.engine}: an empty fixture set passes nothing`);
  if (
    !Array.isArray(r.browsers) ||
    r.browsers.some((b) => !BROWSERS.includes(b)) ||
    new Set(r.browsers).size !== r.browsers.length
  )
    throw new RangeError(`${r.engine}: browsers must be distinct names of chromium, firefox and webkit`);
  if (r.verdict === "pass") {
    if (r.browsers.length === 0) throw new RangeError(`${r.engine}: a pass needs at least one browser`);
    if (mismatches > 0) throw new RangeError(`${r.engine}: a pass cannot have mismatches`);
  } else if (r.verdict === "fail") {
    if (mismatches === 0 && !r.reason)
      throw new RangeError(`${r.engine}: a fail without mismatches needs a reason`);
  } else if (r.verdict === "not_run") {
    if (!r.reason) throw new RangeError(`${r.engine}: a not_run needs a reason`);
  } else throw new RangeError(`${r.engine}: unknown verdict`);
  const entry: Record<string, unknown> = {
    engine: r.engine,
    engine_version: r.version,
    tolerance: { class: "hosted", defined_by: owner },
    fixtures: { files, vectors },
  };
  if (r.verdict !== "not_run") entry.max_error = { mismatches };
  entry.browsers = [...r.browsers];
  entry.verdict = r.verdict;
  if (r.reason) entry.reason = r.reason;
  return entry;
}

/** A new report with one `hosted` entry per suite result appended, in the order given; the input is untouched. */
export function mergeHostedVerdicts<T extends ParityReportLike>(report: T, results: HostedSuiteResult[]): T {
  const listed = new Set(
    report.engines
      .filter((e) => (e.tolerance as { class?: string } | undefined)?.class === "hosted")
      .map((e) => String(e.engine)),
  );
  const seen = new Set<string>();
  const entries = results.map((r) => {
    if (listed.has(r.engine) || seen.has(r.engine))
      throw new RangeError(`${r.engine}: already listed with class hosted`);
    seen.add(r.engine);
    return entryOf(r);
  });
  return { ...structuredClone(report), engines: [...structuredClone(report.engines), ...entries] };
}
