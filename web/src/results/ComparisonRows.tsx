import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import styles from "~/cases/cases.module.css";
import { formatValue } from "~/cases/KpiTable";
import { type Lang, pick, type Text2 } from "~/cases/types";
import { unitSymbol } from "~/cases/units";
import { mcnemarVerdict, pairedVerdict, type Verdict } from "./verdict";

export interface Metric {
  id: string;
  name: Text2;
  unit: string;
  orientation: string;
}
export interface DiffInterval {
  lo: number;
  hi: number;
  level: number;
  method: string;
  resamples?: number;
}
interface RowBase {
  group?: string;
  metric: Metric;
  n: number;
}
export interface PairedRow extends RowBase {
  kind: "paired";
  challenger: string;
  baseline: string;
  pairing_unit: Text2;
  interval: DiffInterval;
}
export interface McnemarRow extends RowBase {
  kind: "mcnemar";
  challenger: string;
  baseline: string;
  pairing_unit: Text2;
  b: number;
  c: number;
  p_value: number;
}
export interface SingleEventRow extends RowBase {
  kind: "single-event";
  challenger: string;
  baseline: string;
  challenger_value: number;
  baseline_value: number;
}
export interface EstimateRow extends RowBase {
  kind: "estimate";
  system: string;
  value: number;
  interval?: DiffInterval;
  threshold?: { comparator: "ge" | "le"; value: number };
}
export type ComparisonRow = PairedRow | McnemarRow | SingleEventRow | EstimateRow;

const ORIENTATIONS = new Set(["higher-is-better", "lower-is-better"]);
const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

/** A line of a row. The trailing space keeps the text of neighbouring lines apart for readers that join them. */
function Line({ className, children }: { className?: string; children: ReactNode }) {
  return <p className={className}>{children} </p>;
}

/**
 * One row per comparison, in the given order and with no composite score: the metric with unit and orientation, the
 * systems, the design (pairing unit, n), the 95 % interval with its method, and a verdict derived by the decision
 * rule of FR-020-22 (never the stored `verdict` field).
 */
export function ComparisonRows({ rows }: { rows: ComparisonRow[] }) {
  const { t, i18n } = useTranslation("results");
  const lang: Lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const num = (n: number) => formatValue(n, lang);

  const verdictText = (verdict: Verdict, challenger: string, baseline: string) => {
    if (verdict === "challenger") return t("verdict.better", { winner: challenger, loser: baseline });
    if (verdict === "baseline") return t("verdict.better", { winner: baseline, loser: challenger });
    if (verdict === "none") return t("verdict.none");
    return t("verdict.unavailable");
  };

  const intervalText = (interval: DiffInterval | undefined) => {
    if (!interval || !finite(interval.lo) || !finite(interval.hi)) return t("rows.noInterval");
    return t("rows.interval", {
      level: Math.round((finite(interval.level) ? interval.level : 0.95) * 100),
      lo: num(interval.lo),
      hi: num(interval.hi),
      method: t(`method.${interval.method}`, { defaultValue: interval.method }),
    });
  };

  return (
    <ul className={styles.rows}>
      {rows.map((row, index) => {
        const unit = unitSymbol(row.metric.unit);
        const key = `${row.kind}-${row.metric.id}-${index}`;
        return (
          <li key={key} data-comparison-row={row.kind} data-group={row.group} className={styles.card}>
            <h4>
              {pick(row.metric.name, lang)}
              {unit && <span className={styles.unit}> ({unit})</span>}{" "}
            </h4>
            <Line className={styles.unit}>
              {ORIENTATIONS.has(row.metric.orientation) ? t(`orientation.${row.metric.orientation}`) : ""}
            </Line>
            {row.kind === "estimate" ? (
              <>
                <Line>{t("rows.system", { system: row.system })}</Line>
                <Line>
                  {t("rows.value", { value: finite(row.value) ? num(row.value) : t("rows.unavailable") })} ·{" "}
                  {t("rows.n", { n: row.n })}
                </Line>
                {row.interval && <Line>{intervalText(row.interval)}</Line>}
                {row.threshold && finite(row.threshold.value) && (
                  <Line>
                    {t("rows.threshold", {
                      comparator: row.threshold.comparator === "ge" ? "≥" : "≤",
                      value: num(row.threshold.value),
                    })}
                  </Line>
                )}
              </>
            ) : (
              <>
                <Line>{t("rows.versus", { challenger: row.challenger, baseline: row.baseline })}</Line>
                {row.kind === "single-event" ? (
                  <>
                    <Line>
                      {t("rows.values", {
                        challenger: finite(row.challenger_value)
                          ? num(row.challenger_value)
                          : t("rows.unavailable"),
                        baseline: finite(row.baseline_value)
                          ? num(row.baseline_value)
                          : t("rows.unavailable"),
                      })}
                    </Line>
                    <Line className={styles.verdict}>{t("verdict.single")}</Line>
                  </>
                ) : (
                  <>
                    <Line>{t("rows.pairing", { unit: pick(row.pairing_unit, lang), n: row.n })}</Line>
                    {row.kind === "paired" ? (
                      <>
                        <Line>{intervalText(row.interval)}</Line>
                        <Line className={styles.verdict}>
                          {verdictText(
                            pairedVerdict(row.interval, row.metric.orientation),
                            row.challenger,
                            row.baseline,
                          )}
                        </Line>
                      </>
                    ) : (
                      <>
                        <Line>
                          {t("rows.discordant", {
                            b: row.b,
                            c: row.c,
                            p: finite(row.p_value) ? num(row.p_value) : t("rows.unavailable"),
                          })}
                        </Line>
                        <Line className={styles.verdict}>
                          {verdictText(
                            mcnemarVerdict(row.b, row.c, row.p_value),
                            row.challenger,
                            row.baseline,
                          )}
                        </Line>
                      </>
                    )}
                  </>
                )}
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}
