// Types and small pure helpers shared by the case components. The shapes follow the contracts:
//   CaseRegistry   specs/018-web-cases/contracts/cases.schema.json (DC-018-01)
//   ArtefactRecord data-model 001 section 2.5 (web manifest), RunSummary section 2.1
//   SourceEntry    data-model 001 section 5.1 (only the fields the pages read)
//   ToolEntry      data-model 001 section 4.1 (only the fields the pages read)

export const CASE_IDS = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"] as const;
export type CaseId = (typeof CASE_IDS)[number];

export const CATEGORY_IDS = ["A", "B", "C", "D", "E"] as const;
export type CategoryId = (typeof CATEGORY_IDS)[number];

export const LAYER_IDS = [
  "terrain-2018",
  "terrain-2023",
  "roads",
  "pit-shells",
  "fleet",
  "fields",
  "sensors",
] as const;
export type LayerId = (typeof LAYER_IDS)[number];

export type Lang = "en" | "es";

export interface Text2 {
  en: string;
  es: string;
}

export interface Kpi {
  id: string;
  name: Text2;
  unit: string;
  orientation: string;
  headline: boolean;
  target_value?: number;
}

export interface SyntheticData {
  label: Text2;
  validation: "validated-against-real" | "descriptive-only" | "unvalidated";
  reference_source?: string;
}

export interface CaseEntry {
  category: string;
  title: Text2;
  question: Text2;
  kpis: Kpi[];
  sources: string[];
  synthetic_data: SyntheticData[];
  methods: string[];
  tools: Record<string, "named" | "supporting">;
  engines: string[];
  layers: string[];
  clock_fps?: number;
  recipe: string;
  validity: Text2;
}

export interface CaseRegistry {
  schema_version: string;
  categories: Record<string, { title: Text2 }>;
  cases: Record<string, CaseEntry>;
}

export interface ArtefactRecord {
  id: string;
  run_id: string;
  git_sha: string;
  path: string;
  bytes: number;
  sha256: string;
  kind: string;
  producer: { tool: string; stage: { id: string; variant?: string } };
  inputs: Array<{ id: string; sha256: string; kind: "source" | "artefact" | "knowledge" }>;
  cases?: string[];
  lane: "live" | "replay" | "static";
  licence_class: string;
  spdx: string;
  attribution?: string;
}

export interface RunSummary {
  run_id: string;
  gpu: { name: string } | null;
  created: string;
}

export interface SourceEntry {
  id: string;
  kind: "real" | "synthetic";
  title: string;
  spdx: string;
  landing_url: string;
}

export interface ToolEntry {
  id: string;
  name: string;
  category: "studio-tool" | "component";
  status: string;
}

const CANONICAL = new Set<string>(CASE_IDS);

export function isCaseId(value: unknown): value is CaseId {
  return typeof value === "string" && CANONICAL.has(value);
}

export function pick(text: Text2 | undefined, lang: Lang): string {
  return text?.[lang] ?? text?.en ?? "";
}

/** The registry entry of a canonical id, read as an own property only (never from the prototype chain). */
export function caseEntry(registry: CaseRegistry, id: string): CaseEntry | undefined {
  if (!isCaseId(id)) return undefined;
  return Object.hasOwn(registry.cases, id) ? registry.cases[id] : undefined;
}

/** The 12 canonical ids the registry holds, in canonical order whatever its key order. */
export function orderedCaseIds(registry: CaseRegistry): CaseId[] {
  return CASE_IDS.filter((id) => caseEntry(registry, id) !== undefined);
}

export function headlineKpis(entry: CaseEntry): Kpi[] {
  return entry.kpis.filter((k) => k.headline);
}

/** `M7` -> `/methods/m07/` (FR-020-17 page pattern). Anything that is not M1 to M99 gives null. */
export function methodHref(method: string): string | null {
  const m = /^M([1-9][0-9]?)$/.exec(method);
  return m?.[1] ? `/methods/m${m[1].padStart(2, "0")}/` : null;
}

export function methodNumber(method: string): number {
  return Number(method.slice(1));
}
