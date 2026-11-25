// The slim run cards of the studio ledger and loop, part of the prerendered page data (`web/src/studio/generated/studio-runs.json`, written by
// `web/scripts/build-studio-index.mjs`). Kept apart from `data.ts` so that the case pages, which read only the registry and the index,
// do not carry the cards in their JavaScript (NFR-018-02).

import type { Loaded } from "./data";
import { runs } from "./generated/studio-runs.json";
import type { RunCard } from "./types";

/** The slim cards of the runs published with this build, part of the prerendered page data: the ledger and the loop read these. */
export const studioRuns: RunCard[] = (runs as unknown as RunCard[] | undefined) ?? [];
const READY: Loaded<RunCard[]> = { status: "ready", value: studioRuns };

export function useRunSummaries(): Loaded<RunCard[]> {
  return READY;
}
