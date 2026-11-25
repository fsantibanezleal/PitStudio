import { useTranslation } from "react-i18next";
import { Chart, type ChartBand, type ChartMarker, type ChartSeries } from "./Chart";
import type { ChartDoc } from "./chartSeries";

type Lang = "en" | "es";
type DocSeries = NonNullable<ChartDoc["series"]>[number];

const nan = (values: ReadonlyArray<number | null>): Float64Array =>
  Float64Array.from(values, (v) => v ?? Number.NaN);

/** Series that share the same x values are drawn in one chart; the others each get their own (the chart has one x). */
function groupsOf(series: DocSeries[]): DocSeries[][] {
  const groups: DocSeries[][] = [];
  for (const s of series) {
    const key = JSON.stringify(s.x);
    const hit = groups.find((g) => JSON.stringify(g[0]?.x) === key);
    if (hit) hit.push(s);
    else groups.push([s]);
  }
  return groups;
}

/** A scatter is drawn in x order (the chart reads x non-decreasing); the pairs stay together. */
function sorted(
  group: DocSeries[],
  scatter: boolean,
): { x: Float64Array; ys: Float64Array[]; los: Float64Array[]; his: Float64Array[] } {
  const first = group[0] as DocSeries;
  const x = first.x as number[];
  const order = x.map((_, i) => i);
  if (scatter) order.sort((a, b) => (x[a] as number) - (x[b] as number));
  const pick = (v: ReadonlyArray<number | null> | undefined) =>
    nan(v ? order.map((i) => v[i] as number | null) : []);
  return {
    x: Float64Array.from(order.map((i) => x[i] as number)),
    ys: group.map((s) => pick(s.y)),
    los: group.map((s) => pick(s.lo)),
    his: group.map((s) => pick(s.hi)),
  };
}

/** Line, scatter and ECDF charts of a chart series: the interactive Chart with bands, steps, points and markers. */
export function LinePlot({ doc, lang, title }: { doc: ChartDoc; lang: Lang; title: string }) {
  const { t } = useTranslation("charts");
  const xAxis = doc.x_axis;
  const yAxis = doc.y_axis;
  if (!xAxis || !yAxis || !doc.series) return null;
  const scatter = doc.chart_type === "scatter";
  const groups = groupsOf(doc.series);
  const markers: ChartMarker[] = (doc.markers ?? []).map((m) => ({
    id: m.id,
    label: m.label[lang],
    valueText: m.value_text,
    orientation: m.orientation,
    ...(m.x !== undefined ? { x: m.x } : {}),
    ...(m.y !== undefined ? { y: m.y } : {}),
  }));
  return (
    <>
      {groups.map((group, gi) => {
        const data = sorted(group, scatter);
        const series: ChartSeries[] = group.map((s, k) => ({
          id: s.id,
          name: s.label[lang],
          y: data.ys[k] as Float64Array,
          unit: s.unit ?? yAxis.unit,
          draw: s.draw ?? (scatter ? "points" : doc.chart_type === "ecdf" ? "step" : "line"),
        }));
        const bands: ChartBand[] = group.flatMap((s, k) =>
          s.lo && s.hi
            ? [
                {
                  id: `${s.id}-band`,
                  name: s.band_label ? s.band_label[lang] : t("bandDefault", { name: s.label[lang] }),
                  series: k,
                  lo: data.los[k] as Float64Array,
                  hi: data.his[k] as Float64Array,
                },
              ]
            : [],
        );
        return (
          <Chart
            key={group[0]?.id}
            id={`${doc.id}${gi > 0 ? `-${gi + 1}` : ""}`}
            title={groups.length > 1 ? `${title} (${gi + 1}/${groups.length})` : title}
            x={data.x}
            xName={xAxis.label[lang]}
            xUnit={xAxis.unit}
            series={series}
            xScale={xAxis.scale ?? "linear"}
            yScale={yAxis.scale ?? "linear"}
            bands={bands}
            markers={gi === 0 ? markers : []}
            height={260}
          />
        );
      })}
    </>
  );
}
