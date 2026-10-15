import { useTranslation } from "react-i18next";
import { Chart, type ChartSeries } from "~/charts/Chart";
import { ReasonPanel } from "~/features/reason/ReasonPanel";
import type { ComparisonRow, DiffInterval } from "~/results/ComparisonRows";
import { mcnemarVerdict, pairedVerdict, singleEventVerdict, type Verdict } from "~/results/verdict";
import { verdictText } from "~/results/verdictText";
import styles from "./cases.module.css";
import { formatValue } from "./KpiTable";
import { type CaseRegistry, type Kpi, type Lang, pick } from "./types";
import { unitSymbol } from "./units";

const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

/** The verdict of a row, always derived by the decision rule of FR-020-22 (a stored `verdict` field is never read). */
function rowVerdict(row: ComparisonRow, orientation: string): Verdict | "single" | null {
  if (row.kind === "single-event") return singleEventVerdict(row.n) ?? "unavailable";
  if (row.kind === "paired") return pairedVerdict(row.interval, orientation);
  if (row.kind === "mcnemar") return mcnemarVerdict(row.b, row.c, row.p_value);
  return null;
}

type Label = (key: string) => string;

/** The numbers the row carries, as the points of a small chart (nothing is invented: every y is a value of the row). */
function chartOf(row: ComparisonRow, label: Label): { x: number[]; series: ChartSeries[] } | null {
  const unit = unitSymbol(row.metric.unit) || "1";
  if (row.kind === "paired" && finite(row.interval.lo) && finite(row.interval.hi)) {
    return {
      x: [0, 1],
      series: [
        { id: "interval", name: label("charts.interval"), y: [row.interval.lo, row.interval.hi], unit },
      ],
    };
  }
  if (row.kind === "single-event" && finite(row.challenger_value) && finite(row.baseline_value)) {
    return {
      x: [0, 1],
      series: [
        { id: "values", name: label("charts.values"), y: [row.baseline_value, row.challenger_value], unit },
      ],
    };
  }
  if (row.kind === "mcnemar" && finite(row.b) && finite(row.c)) {
    return {
      x: [0, 1],
      series: [{ id: "discordant", name: label("charts.discordant"), y: [row.b, row.c], unit: "1" }],
    };
  }
  if (row.kind === "estimate" && finite(row.value)) {
    const lo = row.interval?.lo;
    const hi = row.interval?.hi;
    if (finite(lo) && finite(hi)) {
      return {
        x: [0, 1, 2],
        series: [{ id: "estimate", name: label("charts.estimate"), y: [lo, row.value, hi], unit }],
      };
    }
    return { x: [0], series: [{ id: "estimate", name: label("charts.estimate"), y: [row.value], unit }] };
  }
  return null;
}

function KpiChart({ kpi, row, lang }: { kpi: Kpi; row: ComparisonRow | undefined; lang: Lang }) {
  const { t } = useTranslation("cases");
  const { t: tr } = useTranslation("results");
  const unit = unitSymbol(kpi.unit);
  const name = pick(kpi.name, lang);
  const num = (n: number) => formatValue(n, lang);
  const chart = row ? chartOf(row, (key) => t(key)) : null;
  const interval = (iv: DiffInterval) =>
    tr("rows.interval", {
      level: Math.round((finite(iv.level) ? iv.level : 0.95) * 100),
      lo: num(iv.lo),
      hi: num(iv.hi),
      method: tr(`method.${iv.method}`, { defaultValue: iv.method }),
    });
  const verdict = row ? rowVerdict(row, kpi.orientation) : null;
  const challenger = row && row.kind !== "estimate" ? row.challenger : "";
  const baseline = row && row.kind !== "estimate" ? row.baseline : "";
  const words = verdict ? verdictText((key, options) => tr(key, options), verdict, challenger, baseline) : "";

  return (
    <section className={styles.panel} data-kpi-chart={kpi.id} aria-label={name}>
      <h3>
        {name}
        {unit && <span className={styles.unit}> ({unit})</span>}
      </h3>
      <Chart
        id={`kpi-${kpi.id}`}
        title={t("charts.chartTitle", { name })}
        x={chart?.x ?? []}
        xName={t("charts.position")}
        xUnit="1"
        series={chart?.series ?? [{ id: "none", name: t("charts.noData"), y: [], unit: unit || "1" }]}
        height={150}
      />
      {!row && <p className={styles.pending}>{t("notYetRun")}</p>}
      {row && row.kind !== "estimate" && (
        <p className={styles.unit}>
          {tr("rows.versus", { challenger: row.challenger, baseline: row.baseline })}
        </p>
      )}
      {row?.kind === "paired" && <p>{interval(row.interval)}</p>}
      {row?.kind === "single-event" && (
        <p>
          {tr("rows.values", {
            challenger: finite(row.challenger_value) ? num(row.challenger_value) : tr("rows.unavailable"),
            baseline: finite(row.baseline_value) ? num(row.baseline_value) : tr("rows.unavailable"),
          })}
        </p>
      )}
      {row?.kind === "mcnemar" && (
        <p>
          {tr("rows.discordant", {
            b: row.b,
            c: row.c,
            p: finite(row.p_value) ? num(row.p_value) : tr("rows.unavailable"),
          })}
        </p>
      )}
      {row?.kind === "estimate" && (
        <p>
          {tr("rows.value", { value: finite(row.value) ? num(row.value) : tr("rows.unavailable") })}
          {row.interval ? ` · ${interval(row.interval)}` : ""}
        </p>
      )}
      {words && <p className={styles.verdict}>{words}</p>}
    </section>
  );
}

/**
 * The Charts tab (FR-018-16): for each KPI of the case, in registry order, its name and unit, an interactive chart of the numbers
 * of its result row, the baseline, the 95 % interval of the paired difference with its method and the verdict of the decision rule
 * (FR-020-22, derived here, never stored); a KPI without a result row says "Not yet run".
 */
export function ChartsTab({
  caseId,
  registry,
  rows,
}: {
  caseId: string;
  registry: CaseRegistry;
  rows: readonly ComparisonRow[];
}) {
  const { i18n } = useTranslation("cases");
  const lang: Lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const entry = Object.hasOwn(registry.cases, caseId) ? registry.cases[caseId] : undefined;
  if (!entry) return null;
  return (
    <>
      {entry.kpis.map((kpi) => (
        <KpiChart key={kpi.id} kpi={kpi} row={rows.find((r) => r.metric?.id === kpi.id)} lang={lang} />
      ))}
      {(caseId === "B1" || caseId === "B2") && <ReasonPanel caseId={caseId} />}
    </>
  );
}
