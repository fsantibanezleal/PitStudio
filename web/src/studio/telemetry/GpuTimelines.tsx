import { type KeyboardEvent, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Chart } from "~/charts/Chart";
import { clip, gib, num, percent, THROTTLE_REASONS } from "../format";
import styles from "../studio.module.css";
import type { RunCard, StageRecord, TelemetrySummary } from "../types";
import { ConditionsNote } from "./Conditions";

/** One sample of the published telemetry (DC-002-03). */
type Point = Record<string, number | null | undefined>;

export interface PublishedTelemetry {
  run_id: string;
  stages: Array<{
    key: { id: string; variant?: string };
    performance: string;
    bucket_s: number;
    points: Point[];
  }>;
}

/** NVML clocks-event reason bits (NVML API reference, "Clocks Event Reasons"); 0x1 is GPU idle and 0x2 application clocks: not throttle reasons here. */
const REASON_BITS: Record<(typeof THROTTLE_REASONS)[number], number> = {
  sw_power_cap: 0x4,
  sw_thermal: 0x20,
  hw_thermal: 0x40,
  hw_slowdown: 0x8,
  power_brake: 0x80,
};
const NVML_DEVICE_QUERIES = "https://docs.nvidia.com/deploy/nvml-api/group__nvmlDeviceQueries.html";
const NVML_CLOCKS_EVENT = "https://docs.nvidia.com/deploy/nvml-api/group__nvmlClocksEventReasons.html";
const GIB = 2 ** 30;

const CHARTS = ["busy", "memory", "power", "sm_clock", "throttle"] as const;
type ChartName = (typeof CHARTS)[number];

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const column = (points: Point[], field: string, scale = 1): number[] =>
  points.map((p) => (finite(p[field]) ? (p[field] as number) / scale : Number.NaN));

/** "How measured" popover button of a chart (FR-019-29); Escape closes it and returns the focus to the button. */
function HowMeasured({ hz }: { hz: number | null }) {
  const { t } = useTranslation("studio");
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement | null>(null);
  const id = useId();
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Escape" || !open) return;
    event.stopPropagation();
    setOpen(false);
    button.current?.focus();
  };
  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: the wrapper only listens for Escape on behalf of the button and popover it holds
    <div className={styles.how} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={button}
        data-testid="how-measured"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        {t("gpu.how.button")}
      </button>
      {open && (
        <div
          id={id}
          role="dialog"
          aria-label={t("gpu.how.button")}
          data-testid="how-measured-popover"
          className={styles.notice}
        >
          <p>
            {hz === null ? t("gpu.how.noRate", { na: t("gpu.notAvailable") }) : t("gpu.how.rate", { hz })}
          </p>
          <p>{t("gpu.how.utilisation")}</p>
          <p>{t("gpu.how.power")}</p>
          <p>{t("gpu.how.energy")}</p>
          <p>
            <a href={NVML_DEVICE_QUERIES} target="_blank" rel="noopener noreferrer">
              {t("gpu.how.linkQueries")}
            </a>{" "}
            <a href={NVML_CLOCKS_EVENT} target="_blank" rel="noopener noreferrer">
              {t("gpu.how.linkClocks")}
            </a>
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * Timelines of the open-runtime stages of a published run (FR-019-27, FR-019-28, FR-019-29, FR-019-31): GPU busy % beside the
 * power-at-limit fraction, memory against the GPU's total memory, board power against the enforced limit, SM clock and the
 * clocks-event reasons as a stacked band. A stage that the run card marks local-only is never charted, whatever the file holds.
 * A reading that is null is a gap; a field null or absent in every point replaces its chart by "not available on this GPU".
 */
export function GpuTimelines({ run, telemetry }: { run: RunCard; telemetry: PublishedTelemetry }) {
  const { t } = useTranslation("studio");
  const na = t("gpu.notAvailable");

  return (
    <div data-testid="telemetry-charts" className={styles.gpuStages}>
      {telemetry.stages.map((tStage, i) => {
        const card: StageRecord | undefined = run.stages.find(
          (s) =>
            s.key.id === tStage.key.id &&
            (tStage.key.variant === undefined || s.key.variant === tStage.key.variant),
        );
        if (tStage.performance !== "public" || !card || card.performance !== "public") return null;
        const summary: TelemetrySummary | null = typeof card.telemetry === "object" ? card.telemetry : null;
        // a sample without a finite time cannot be placed; the rest are ordered by time so that the chart always gets a valid axis
        const points = tStage.points
          .filter((p) => finite(p.t_s))
          .sort((a, b) => (a.t_s as number) - (b.t_s as number));
        const id = tStage.key.id;
        const x = points.map((p) => (finite(p.t_s) ? (p.t_s as number) : Number.NaN));
        const total = run.gpu?.vram_total_bytes;
        const limit = run.gpu?.power_limit_enforced_w;
        const hz = finite(summary?.sample_hz) ? (summary?.sample_hz as number) : null;
        const powerAtLimit = percent(summary?.power_at_limit_frac);

        const specs: Record<
          ChartName,
          { y: number[][]; names: string[]; ids: string[]; unit: string; title: string }
        > = {
          busy: {
            y: [column(points, "util_pct")],
            names: [t("gpu.chart.busy")],
            ids: ["busy"],
            unit: "%",
            title: t("gpu.chart.busy"),
          },
          memory: {
            y: [column(points, "mem_used_bytes", GIB)],
            names: [t("gpu.chart.memory")],
            ids: ["memory"],
            unit: "GiB",
            title: t("gpu.chart.memory"),
          },
          power: {
            y: [column(points, "power_w")],
            names: [t("gpu.chart.power")],
            ids: ["power"],
            unit: "W",
            title: t("gpu.chart.power"),
          },
          sm_clock: {
            y: [column(points, "sm_clock_mhz")],
            names: [t("gpu.chart.smClock")],
            ids: ["sm_clock"],
            unit: "MHz",
            title: t("gpu.chart.smClock"),
          },
          throttle: {
            y: THROTTLE_REASONS.map((reason) =>
              points.map((p) =>
                finite(p.clocks_event_mask)
                  ? (p.clocks_event_mask as number) & REASON_BITS[reason]
                    ? 1
                    : 0
                  : Number.NaN,
              ),
            ),
            names: THROTTLE_REASONS.map((reason) => t(`throttle.${reason}`)),
            ids: [...THROTTLE_REASONS],
            unit: "0/1",
            title: t("gpu.chart.throttle"),
          },
        };

        return (
          <section
            // biome-ignore lint/suspicious/noArrayIndexKey: a stage is identified by its place in the telemetry file
            key={i}
            data-testid="gpu-stage"
            data-stage={id}
            className={styles.block}
          >
            <h3>{clip(id)}</h3>
            <ConditionsNote run={run} stage={id} />
            {CHARTS.map((name) => {
              const spec = specs[name];
              const missing = (spec.y[0] ?? []).filter((v) => !Number.isFinite(v)).length;
              const allMissing = spec.y.every((y) => y.length === 0 || y.every((v) => !Number.isFinite(v)));
              if (allMissing)
                return (
                  <p key={name} data-testid="chart-unavailable" data-chart={name}>
                    {spec.title}: {na}
                  </p>
                );
              const references =
                name === "memory" && finite(total)
                  ? [{ id: "vram_total", y: total / GIB, label: `${gib(total)} GB`, value: total }]
                  : name === "power" && finite(limit)
                    ? [{ id: "power_limit", y: limit, label: `${num(limit)} W`, value: limit }]
                    : [];
              return (
                <Chart
                  key={name}
                  id={`${id}-${name}`}
                  title={spec.title}
                  x={x}
                  xName={t("gpu.chart.time")}
                  xUnit="s"
                  series={spec.y.map((y, k) => ({
                    id: spec.ids[k] as string,
                    name: spec.names[k] as string,
                    y,
                    unit: spec.unit,
                  }))}
                  stacked={name === "throttle"}
                  missingText={na}
                  references={references.map(({ id: rid, y, label }) => ({ id: rid, y, label }))}
                  attrs={{
                    "data-chart": name,
                    "data-stage": id,
                    "data-missing": missing,
                    ...(name === "throttle" ? { "data-kind": "stacked-band" } : {}),
                  }}
                >
                  <div className={styles.chartNotes}>
                    {name === "busy" && (
                      <>
                        <span>{t("gpu.busyLabel")}</span>{" "}
                        <span data-testid="power-at-limit">
                          {t("gpu.powerAtLimit")}: {powerAtLimit === null ? na : `${powerAtLimit} %`}
                        </span>
                      </>
                    )}
                    {references.map((r) => (
                      <span key={r.id} data-testid="chart-reference" data-ref={r.id} data-value={r.value}>
                        {t(`gpu.ref.${r.id}`)}: {r.label}
                      </span>
                    ))}
                    {name === "power" && !finite(limit) && (
                      <span>
                        {t("gpu.ref.power_limit")}: {na}
                      </span>
                    )}
                    {name === "memory" && !finite(total) && (
                      <span>
                        {t("gpu.ref.vram_total")}: {na}
                      </span>
                    )}
                    {name === "throttle" && (
                      <ul className={styles.plain}>
                        {THROTTLE_REASONS.map((reason) => (
                          <li key={reason} data-series={reason}>
                            {t(`throttle.${reason}`)}
                          </li>
                        ))}
                      </ul>
                    )}
                    <HowMeasured hz={hz} />
                  </div>
                </Chart>
              );
            })}
          </section>
        );
      })}
      {telemetry.stages.length === 0 && <p>{na}</p>}
    </div>
  );
}
