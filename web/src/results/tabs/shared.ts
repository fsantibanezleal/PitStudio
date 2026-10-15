import type { Lang } from "~/cases/types";
import type { EstimateRow } from "../ComparisonRows";

export const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

/** The estimate rows of a published bundle, hostile entries (null, strings, other kinds) dropped. */
export function estimates(rows: unknown, group?: string): EstimateRow[] {
  if (!Array.isArray(rows)) return [];
  return rows.filter(
    (r): r is EstimateRow =>
      typeof r === "object" &&
      r !== null &&
      (r as EstimateRow).kind === "estimate" &&
      (group === undefined || (r as EstimateRow).group === group),
  );
}

export function langOf(language: string | undefined): Lang {
  return language === "es" ? "es" : "en";
}
