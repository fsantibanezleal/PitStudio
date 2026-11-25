import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Chart } from "./Chart";
import styles from "./chart.module.css";

/** A plain loop: the sandbox hydrates with a million samples, so the data must be cheap to build. */
const range = (n: number, f: (i: number) => number): Float64Array => {
  const out = new Float64Array(n);
  for (let i = 0; i < n; i++) out[i] = f(i);
  return out;
};

/**
 * The unlisted chart sandbox the browser tests drive (`<base>charts/`): a sine in SI, a speed ramp in source units, a million
 * samples, a series with a gap and twelve small charts. The data is closed-form, so the tests can recompute every reading.
 */
export function ChartSandbox() {
  const { t } = useTranslation("charts");
  const data = useMemo(() => {
    const sineX = range(2001, (i) => 0.005 * i);
    return {
      sineX,
      sineY: sineX.map((x) => 5 * Math.sin((2 * Math.PI * x) / 10) + 2),
      kmhX: range(101, (i) => i),
      kmhY: range(101, (i) => 3.6 * i),
      bigX: range(1_000_000, (i) => i),
      bigY: range(1_000_000, (i) => ((i * 2654435761) % 4294967296) / 4294967296),
      gapX: range(100, (i) => i),
      gapY: range(100, (i) => (i >= 40 && i < 60 ? Number.NaN : Math.cos(i / 9))),
      smallX: range(50, (i) => i),
      smallY: range(50, (i) => Math.sin(i / 6)),
    };
  }, []);
  const common = { xName: t("sandbox.x"), xUnit: "s" };

  return (
    <article>
      <h1>{t("sandbox.title")}</h1>
      <p>{t("sandbox.lead")}</p>
      <div className={styles.grid}>
        <Chart
          id="sine"
          title={t("sandbox.sine")}
          x={data.sineX}
          series={[{ id: "y", name: t("sandbox.y"), y: data.sineY, unit: "m" }]}
          {...common}
        />
        <Chart
          id="big"
          title={t("sandbox.big")}
          x={data.bigX}
          series={[{ id: "y", name: t("sandbox.y"), y: data.bigY, unit: "1" }]}
          xName={t("sandbox.x")}
          xUnit="1"
        />
        <Chart
          id="kmh"
          title={t("sandbox.kmh")}
          x={data.kmhX}
          series={[
            {
              id: "v",
              name: t("sandbox.speed"),
              y: data.kmhY,
              unit: "km/h",
              si: { unit: "m/s", factor: 1 / 3.6 },
            },
          ]}
          {...common}
        />
        <Chart
          id="gap"
          title={t("sandbox.gap")}
          x={data.gapX}
          series={[{ id: "y", name: t("sandbox.y"), y: data.gapY, unit: "m" }]}
          {...common}
        />
        {Array.from({ length: 12 }, (_, k) => {
          const n = String(k + 1).padStart(2, "0");
          return (
            <Chart
              key={n}
              id={`many-${n}`}
              title={t("sandbox.many", { n })}
              x={data.smallX}
              series={[{ id: "y", name: t("sandbox.y"), y: data.smallY, unit: "m" }]}
              height={110}
              {...common}
            />
          );
        })}
      </div>
    </article>
  );
}
