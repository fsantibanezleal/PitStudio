// FR-018-77: the published runs of a case that `studio import-run` recorded from a queue job, for the Reproduce block.
import type { PublishedResult } from "./publishedResults";

export interface ImportedRun {
  runId: string;
  /** The queue job the run notes name; null when they name none. */
  job: string | null;
  label: string;
  verdict: "ok" | "partial" | "failed";
  partialReasons: string[];
}

/** Imported runs, newest first. A run the runner made itself is not listed: its recipe reproduces it. */
export function importedRuns(results: readonly PublishedResult[]): ImportedRun[] {
  return results
    .filter((r) => r.imported)
    .map((r) => ({
      runId: r.runId,
      job: r.job,
      label: r.label,
      verdict: r.verdict,
      partialReasons: r.partialReasons,
    }))
    .sort((a, b) => b.runId.localeCompare(a.runId));
}
