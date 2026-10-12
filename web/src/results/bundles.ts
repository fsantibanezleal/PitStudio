import type { Text2 } from "~/cases/types";
import type { ComparisonRow } from "./ComparisonRows";
import { RESULTS_TAB_IDS, type ResultsTabId } from "./tabs";

// The results bundles committed under `web/public/results/<comparison-id>.json` (DC-020-02), read at build time.
// With none committed, every comparison is "Not yet run". A file that is not a well-formed bundle is ignored.
const files = import.meta.glob("../../public/results/*.json", { eager: true, import: "default" }) as Record<
  string,
  unknown
>;

export interface AccelRow {
  model: string;
  backend: string;
  precision: string;
  status: string;
  reason?: string;
  parity: string;
}

export interface PublishedBundle {
  id: string;
  tab: ResultsTabId;
  title: Text2;
  comparison: ComparisonRow[];
  acceleration: AccelRow[];
  criteria: CriterionRecord[];
  /** The run conditions of an acceleration bundle (DC-020-02 `conditions`), as published. */
  conditions?: unknown;
}

export interface CriterionRecord {
  requirement: string;
  status: "pass" | "fail" | "not-run";
}

const CRITERION_STATUSES = new Set(["pass", "fail", "not-run"]);

function readCriteria(raw: unknown): CriterionRecord[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(
      (c): c is CriterionRecord =>
        typeof c === "object" &&
        c !== null &&
        typeof (c as CriterionRecord).requirement === "string" &&
        CRITERION_STATUSES.has((c as CriterionRecord).status),
    )
    .map((c) => ({ requirement: c.requirement, status: c.status }));
}

const COMPARISON_KINDS = new Set(["paired", "mcnemar", "single-event", "estimate"]);

export function readBundle(raw: unknown): PublishedBundle | null {
  if (typeof raw !== "object" || raw === null) return null;
  const b = raw as Record<string, unknown>;
  const tab = b.tab;
  if (
    typeof b.id !== "string" ||
    typeof tab !== "string" ||
    !(RESULTS_TAB_IDS as readonly string[]).includes(tab)
  )
    return null;
  if (!Array.isArray(b.rows)) return null;
  const criteria = readCriteria(b.criteria);
  const title = (b.title ?? { en: b.id, es: b.id }) as Text2;
  if (b.kind === "acceleration" && tab === "acceleration") {
    return {
      id: b.id,
      tab,
      title,
      comparison: [],
      acceleration: b.rows as AccelRow[],
      criteria,
      conditions: b.conditions,
    };
  }
  if (b.kind !== "comparison" || tab === "acceleration" || tab === "parity") return null;
  const rows = (b.rows as ComparisonRow[]).filter(
    (row) => typeof row === "object" && row !== null && COMPARISON_KINDS.has(row.kind),
  );
  return { id: b.id, tab: tab as ResultsTabId, title, comparison: rows, acceleration: [], criteria };
}

export const publishedBundles: PublishedBundle[] = Object.values(files)
  .map(readBundle)
  .filter((b): b is PublishedBundle => b !== null);
