import type { RecipeSummary } from "./ReproduceBlock";
import { CASE_IDS, type CaseId } from "./types";

// The case recipes that exist in the repository at build time (`studio/recipes/cases/<id>.yaml`). A case without a
// file is "recipe planned" (FR-018-20). The glob resolves at build time, so the set is the one the checkout holds.
const files = import.meta.glob("../../../studio/recipes/cases/*.yaml", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** The GPU need of each stage of a recipe: the `gpu:` value under `resources:` (data-model 001 section 3.2). */
export function summarizeRecipe(raw: string): RecipeSummary {
  const stages: RecipeSummary["stages"] = [];
  for (const match of raw.matchAll(/^\s*gpu:\s*["']?(exclusive|nvenc|none)["']?\s*(?:#.*)?$/gm)) {
    stages.push({ resources: { gpu: match[1] as "exclusive" | "nvenc" | "none" } });
  }
  return { stages };
}

const summaries = new Map<CaseId, RecipeSummary>();
for (const [path, raw] of Object.entries(files)) {
  const stem =
    path
      .split("/")
      .pop()
      ?.replace(/\.yaml$/, "") ?? "";
  const id = CASE_IDS.find((c) => c.toLowerCase() === stem);
  if (id) summaries.set(id, summarizeRecipe(raw));
}

export function recipeOf(caseId: string): RecipeSummary | null {
  return summaries.get(caseId as CaseId) ?? null;
}
