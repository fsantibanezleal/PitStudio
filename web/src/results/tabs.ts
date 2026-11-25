import { parseTabParam } from "~/shell/tabParam";

/** The seven tabs of `/results`, in the order of FR-020-20 (the first five are the `tab` enum of DC-020-02). */
export const RESULTS_TAB_IDS = [
  "learned-vs-classical",
  "sim-to-real",
  "parity",
  "dr-ablation",
  "isaac-lab",
  "cosmos",
  "acceleration",
] as const;

export type ResultsTabId = (typeof RESULTS_TAB_IDS)[number];

/** The tab named by the first `tab` parameter of a query string, else the first tab. */
export function parseResultsTab(search: string): ResultsTabId {
  return parseTabParam(search, RESULTS_TAB_IDS) as ResultsTabId;
}
