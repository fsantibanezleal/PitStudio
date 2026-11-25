// FR-018-79: which tools and methods a published run of the case produced one kind of visual with. A pure module: the case story and
// the unit test both read it. Nothing is used by default, and the render tools never count here (they have their own section).
import type { UsedParts } from "./builtWith";
import { kpiItems } from "./kpiValues";
import type { PublishedResult } from "./publishedResults";
import type { CaseEntry } from "./types";

/** The tool whose published run is the browser 3D scene (terrain tiles); the scene line is used only once a run names it. */
export const SCENE_VIEWER_TOOL = "threejs-r3f-3d-tiles";

/**
 * - kpi: the runs that feed a KPI value of the table;
 * - scene: the runs whose stages name the 3D viewer tool;
 * - chart: the working runs of the case;
 * - simulate: the working runs, only when the caller says the live engine ran (`ran` true).
 * `ran` false means the visual shows a not-run state: nothing is used.
 */
export function usedForVisual(
  kind: string,
  results: readonly PublishedResult[],
  entry: CaseEntry,
  ran?: boolean,
): UsedParts {
  const working = results.filter((r) => r.verdict !== "failed");
  let picked: readonly PublishedResult[] = [];
  if (ran !== false) {
    if (kind === "kpi") {
      const runs = new Set(
        kpiItems(entry, results)
          .filter((i) => i.value !== null && i.artefact !== null)
          .map((i) => i.artefact?.run_id),
      );
      picked = working.filter((r) => runs.has(r.runId));
    } else if (kind === "scene") picked = working.filter((r) => r.tools.includes(SCENE_VIEWER_TOOL));
    else if (kind === "chart") picked = working;
    else if (kind === "simulate") picked = ran === true ? working : [];
  }
  return {
    tools: new Set(picked.flatMap((r) => r.tools)),
    methods: new Set(picked.flatMap((r) => r.methods)),
  };
}
