import { importedRuns } from "./importedRuns";
import { usePublishedCase } from "./publishedResults";
import { ReproduceBlock } from "./ReproduceBlock";
import { recipeOf } from "./recipes";

/** The Reproduce block of a case page with the published imported runs of the case (FR-018-77). */
export function ReproduceWithRuns({ caseId, runId }: { caseId: string; runId: string | null }) {
  const published = usePublishedCase(caseId);
  return (
    <ReproduceBlock
      caseId={caseId}
      recipe={recipeOf(caseId)}
      runId={runId}
      runs={importedRuns(published.results)}
    />
  );
}
