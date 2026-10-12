import type { Verdict } from "./verdict";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * The words of a derived verdict in the active language (`results` namespace). An unusable verdict prints the line that says so
 * ("no verdict"), never a claim; `verdictLabel` in `./verdict` is the English reference of the same rule.
 */
export function verdictText(
  t: Translate,
  verdict: Verdict | "single",
  challenger: string,
  baseline: string,
): string {
  if (verdict === "challenger") return t("verdict.better", { winner: challenger, loser: baseline });
  if (verdict === "baseline") return t("verdict.better", { winner: baseline, loser: challenger });
  if (verdict === "none") return t("verdict.none");
  if (verdict === "single") return t("verdict.single");
  return t("verdict.unavailable");
}
