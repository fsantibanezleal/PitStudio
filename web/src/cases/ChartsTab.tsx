import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { Chart, type ChartSeries } from "~/charts/Chart";
import { type IntervalEntry, IntervalPlot } from "~/charts/IntervalPlot";
import { ReasonPanel } from "~/features/reason/ReasonPanel";
import type { ComparisonRow, DiffInterval } from "~/results/ComparisonRows";
import { mcnemarVerdict, pairedVerdict, singleEventVerdict, type Verdict } from "~/results/verdict";
import { verdictText } from "~/results/verdictText";
import { Attribution } from "./BuiltWithView";
import styles from "./cases.module.css";
import { formatValue } from "./KpiTable";
import { type CaseRegistry, type Kpi, type Lang, pick } from "./types";
import { unitSymbol } from "./units";

const CaseRunCharts = lazy(() => import("~/charts/RunCharts"));

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

/** The intervals a KPI's rows carry, to be drawn as intervals: a paired difference (with the zero reference) or an estimate with its interval. */
function intervalsOf(
  rows: readonly ComparisonRow[],
  label: (row: ComparisonRow) => string,
): { entries: IntervalEntry[]; zero: boolean; level: number } | null {
  const first = rows[0];
  if (!first) return null;
  const entries: IntervalEntry[] = [];
  let level = 0.95;
  for (const [k, r] of rows.entries()) {
    if (r.kind !== first.kind) continue;
    if (
      r.kind === "paired" &&
      finite(r.interval.lo) &&
      finite(r.interval.hi) &&
      r.interval.lo <= r.interval.hi
    ) {
      entries.push({ id: `row-${k}`, label: label(r), lo: r.interval.lo, hi: r.interval.hi });
      level = finite(r.interval.level) ? r.interval.level : level;
    } else if (
      r.kind === "estimate" &&
      finite(r.value) &&
      r.interval &&
      finite(r.interval.lo) &&
      finite(r.interval.hi) &&
      r.interval.lo <= r.interval.hi
    ) {
      entries.push({ id: `row-${k}`, label: label(r), lo: r.interval.lo, hi: r.interval.hi, point: r.value });
      level = finite(r.interval.level) ? r.interval.level : level;
    }
  }
  return entries.length > 0 ? { entries, zero: first.kind === "paired", level } : null;
}

function KpiChart({ kpi, rows, lang }: { kpi: Kpi; rows: readonly ComparisonRow[]; lang: Lang }) {
  const { t } = useTranslation("cases");
  const { t: tr } = useTranslation("results");
  const unit = unitSymbol(kpi.unit);
  const kpiName = pick(kpi.name, lang);
  const row = rows[0];
  // the chart is titled with what the published row measures: a row whose own metric name differs from the KPI is not the KPI
  const rowName = row ? pick(row.metric.name, lang) : kpiName;
  const same = rowName.trim().toLowerCase() === kpiName.trim().toLowerCase();
  const name = same ? kpiName : rowName;
  const num = (n: number) => formatValue(n, lang);
  const chart = row ? chartOf(row, (key) => t(key)) : null;
  const drawn = row
    ? intervalsOf(rows, (r) =>
        r.kind === "estimate"
          ? r.system
          : tr("rows.versus", { challenger: r.challenger, baseline: r.baseline }),
      )
    : null;
  const interval = (iv: DiffInterval) =>
    tr("rows.interval", {
      level: Math.round((finite(iv.level) ? iv.level : 0.95) * 100),
      lo: num(iv.lo),
      hi: num(iv.hi),
      method: tr(`method.${iv.method}`, { defaultValue: iv.method }),
    });
  const wordsOf = (r: ComparisonRow) => {
    const verdict = rowVerdict(r, kpi.orientation);
    const challenger = r.kind !== "estimate" ? r.challenger : "";
    const baseline = r.kind !== "estimate" ? r.baseline : "";
    return verdict ? verdictText((key, options) => tr(key, options), verdict, challenger, baseline) : "";
  };

  return (
    <section className={styles.panel} data-kpi-chart={kpi.id} data-visual="chart" aria-label={name}>
      <h3>
        {name}
        {unit && <span className={styles.unit}> ({unit})</span>}
      </h3>
      {drawn ? (
        <IntervalPlot
          id={`kpi-${kpi.id}`}
          title={t("charts.chartTitle", { name })}
          unit={unit || "1"}
          intervals={drawn.entries}
          zero={drawn.zero}
          level={drawn.level}
          lang={lang}
        />
      ) : (
        <Chart
          id={`kpi-${kpi.id}`}
          title={t("charts.chartTitle", { name })}
          x={chart?.x ?? []}
          xName={t("charts.position")}
          xUnit="1"
          series={chart?.series ?? [{ id: "none", name: t("charts.noData"), y: [], unit: unit || "1" }]}
          height={150}
        />
      )}
      {!row && <p className={styles.pending}>{t("notYetRun")}</p>}
      {row && !same && <p className={styles.unit}>{t("charts.notTheKpi", { kpi: kpiName, row: rowName })}</p>}
      {rows.map((r, k) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: result rows have no id of their own, their order is their identity
        <div key={k} data-kpi-row={k}>
          {r.kind !== "estimate" && (
            <p className={styles.unit}>
              {tr("rows.versus", { challenger: r.challenger, baseline: r.baseline })}
            </p>
          )}
          {r.kind === "paired" && <p>{interval(r.interval)}</p>}
          {r.kind === "single-event" && (
            <p>
              {tr("rows.values", {
                challenger: finite(r.challenger_value) ? num(r.challenger_value) : tr("rows.unavailable"),
                baseline: finite(r.baseline_value) ? num(r.baseline_value) : tr("rows.unavailable"),
              })}
            </p>
          )}
          {r.kind === "mcnemar" && (
            <p>
              {tr("rows.discordant", {
                b: r.b,
                c: r.c,
                p: finite(r.p_value) ? num(r.p_value) : tr("rows.unavailable"),
              })}
            </p>
          )}
          {r.kind === "estimate" && (
            <p>
              {tr("rows.value", { value: finite(r.value) ? num(r.value) : tr("rows.unavailable") })}
              {r.interval ? ` · ${interval(r.interval)}` : ""}
            </p>
          )}
          {wordsOf(r) && <p className={styles.verdict}>{wordsOf(r)}</p>}
        </div>
      ))}
      <Attribution kind="chart" ran={row !== undefined} />
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
        <KpiChart key={kpi.id} kpi={kpi} rows={rows.filter((r) => r.metric?.id === kpi.id)} lang={lang} />
      ))}
      <Suspense fallback={null}>
        <CaseRunCharts caseId={caseId} />
      </Suspense>
      {(caseId === "B1" || caseId === "B2") && <ReasonPanel caseId={caseId} />}
    </>
  );
}
