import { useTranslation } from "react-i18next";
import styles from "~/cases/cases.module.css";
import { formatValue } from "~/cases/KpiTable";
import type { EstimateRow, McnemarRow } from "../ComparisonRows";
import { mcnemarVerdict } from "../verdict";
import { verdictText } from "../verdictText";
import { estimates, finite, langOf } from "./shared";

// FR-020-27: balanced accuracy per question type for the three systems, the exact McNemar comparison of Cosmos against
// Qwen with the verdict of the decision rule (never the stored one), the Q8_0 versus BF16 agreement, and the attribution.
const SYSTEMS = ["Cosmos Reason 2", "Qwen3-VL-2B", "detector + geometric rule"] as const;
const Q8_ID = "q8_bf16_agreement";
const Q8_DEFAULT_MIN = 0.95;

const isMcnemar = (r: unknown): r is McnemarRow =>
  typeof r === "object" && r !== null && (r as McnemarRow).kind === "mcnemar";

export function CosmosTab({ rows }: { rows: unknown }) {
  const { t, i18n } = useTranslation("results");
  const lang = langOf(i18n.resolvedLanguage);
  const num = (n: number) => formatValue(n, lang);
  const notRun = t("pending.status");

  const list = Array.isArray(rows) ? rows : [];
  const accuracy = estimates(list).filter(
    (r) => r.metric?.id === "balanced_accuracy" && typeof r.group === "string",
  );
  const mcnemars = list.filter(isMcnemar).filter((r) => typeof r.group === "string");
  const types = [
    ...new Set([...accuracy.map((r) => r.group as string), ...mcnemars.map((r) => r.group as string)]),
  ];

  const q8 = estimates(list).find((r) => r.metric?.id === Q8_ID);
  const q8Value = q8 && finite(q8.value) ? q8.value : undefined;
  const q8Min = q8?.threshold && finite(q8.threshold.value) ? q8.threshold.value : Q8_DEFAULT_MIN;
  const q8Comparator = q8?.threshold?.comparator === "le" ? "le" : "ge";
  const q8Met =
    q8Value === undefined ? undefined : q8Comparator === "ge" ? q8Value >= q8Min : q8Value <= q8Min;

  const cell = (row: EstimateRow | undefined) => {
    if (!row) return <p className={styles.pending}>{notRun}</p>;
    const iv = row.interval;
    return (
      <>
        <p data-field="value">{finite(row.value) ? num(row.value) : t("rows.unavailable")}</p>
        {iv && finite(iv.lo) && finite(iv.hi) && (
          <p data-field="interval">
            {t("cosmosTab.interval", {
              level: Math.round((finite(iv.level) ? iv.level : 0.95) * 100),
              lo: num(iv.lo),
              hi: num(iv.hi),
            })}
          </p>
        )}
      </>
    );
  };

  return (
    <div>
      <p data-testid="cosmos-attribution">{t("cosmosTab.attribution")}</p>
      <p className={styles.unit}>{t("cosmosTab.noHeadline")}</p>
      {types.map((type) => {
        const mc = mcnemars.find((r) => r.group === type);
        return (
          <section key={type} data-testid="cosmos-type" data-qtype={type} aria-label={type}>
            <h3>{t("cosmosTab.type", { type })}</h3>
            <h4>{t("cosmosTab.balancedAccuracy")}</h4>
            <ul className={styles.rows}>
              {SYSTEMS.map((system) => (
                <li key={system} data-testid="cosmos-system" data-system={system} className={styles.card}>
                  <strong>{system}</strong>
                  {cell(accuracy.find((r) => r.group === type && r.system === system))}
                </li>
              ))}
            </ul>
            {mc && (
              <p data-testid="cosmos-mcnemar">
                {t("cosmosTab.mcnemar", {
                  p: finite(mc.p_value) ? num(mc.p_value) : t("rows.unavailable"),
                  b: finite(mc.b) ? mc.b : t("rows.unavailable"),
                  c: finite(mc.c) ? mc.c : t("rows.unavailable"),
                })}
                {" · "}
                {verdictText(
                  t,
                  mcnemarVerdict(mc.b, mc.c, mc.p_value),
                  String(mc.challenger),
                  String(mc.baseline),
                )}
              </p>
            )}
          </section>
        );
      })}
      <section aria-label={t("cosmosTab.q8")}>
        <h3>{t("cosmosTab.q8")}</h3>
        <div
          data-testid="q8-agreement"
          data-met={q8Met === undefined ? undefined : String(q8Met)}
          className={styles.card}
        >
          {q8Value === undefined ? (
            <p className={styles.pending}>{notRun}</p>
          ) : (
            <p>{t("cosmosTab.q8Value", { value: num(q8Value), threshold: num(q8Min) })}</p>
          )}
        </div>
      </section>
    </div>
  );
}
