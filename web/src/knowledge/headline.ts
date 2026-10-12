// FR-020-42 and SC-020-03: a headline KPI whose manifest lists an UNVERIFIED knowledge row among its inputs is not shown as
// a headline and carries the UNVERIFIED badge wherever it appears.

export const UNVERIFIED_BADGE = "UNVERIFIED — pinned at specification";

export interface KnowledgeInput {
  id: string;
  kind: string;
}
export interface VerificationRow {
  id: string;
  verification: string;
}

/** The ids of the knowledge inputs that name an UNVERIFIED row, in input order, without repeats. */
export function unverifiedInputs(inputs: KnowledgeInput[] | undefined, rows: VerificationRow[]): string[] {
  const bad = new Set(rows.filter((r) => r.verification === "UNVERIFIED").map((r) => r.id));
  const out: string[] = [];
  for (const input of inputs ?? []) {
    if (input.kind === "knowledge" && bad.has(input.id) && !out.includes(input.id)) out.push(input.id);
  }
  return out;
}

export function partitionHeadlines<K extends { id: string; inputs?: KnowledgeInput[] }>(
  kpis: K[],
  rows: VerificationRow[],
): { headline: K[]; demoted: Array<K & { unverified: string[] }> } {
  const headline: K[] = [];
  const demoted: Array<K & { unverified: string[] }> = [];
  for (const kpi of kpis) {
    const unverified = unverifiedInputs(kpi.inputs, rows);
    if (unverified.length > 0) demoted.push({ ...kpi, unverified });
    else headline.push(kpi);
  }
  return { headline, demoted };
}

/** The badge of a KPI wherever it appears: true exactly when it has an unverified input. */
export function badgeFor(
  kpi: { inputs?: KnowledgeInput[] },
  rows: VerificationRow[],
): { badge: boolean; ids: string[] } {
  const ids = unverifiedInputs(kpi.inputs, rows);
  return { badge: ids.length > 0, ids };
}
