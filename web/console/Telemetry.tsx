import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert } from "./Alert";
import { api } from "./api";

interface Sample {
  t_s: number;
  power_w: number | null;
}
const KEEP = 240; // points kept on the chart
const W = 400;
const H = 120;

/** The live chart of a run: one `EventSource` on the run's event stream, opened with the run and closed with it. */
export function Telemetry({ run }: { run: string }) {
  const { t } = useTranslation();
  const [points, setPoints] = useState<Sample[]>([]);
  const [events, setEvents] = useState<string[]>([]);
  const [error, setError] = useState<string>();

  useEffect(() => {
    setPoints([]);
    setEvents([]);
    setError(undefined);
    const source = new EventSource(api.eventsUrl(run));
    source.addEventListener("telemetry", (e) => {
      try {
        const s = JSON.parse((e as MessageEvent<string>).data) as Sample;
        if (typeof s.t_s === "number") setPoints((p) => [...p, s].slice(-KEEP));
      } catch {
        // a malformed sample is skipped
      }
    });
    source.addEventListener("event", (e) => {
      try {
        const ev = JSON.parse((e as MessageEvent<string>).data) as { seq: number; type: string };
        setEvents((list) => [...list, `${ev.seq} ${ev.type}`].slice(-8));
      } catch {
        // a malformed event is skipped
      }
    });
    source.addEventListener("error", (e) => {
      if ((e as MessageEvent<string>).data) setError((e as MessageEvent<string>).data);
      else if (source.readyState === EventSource.CLOSED) setError("the event stream closed");
    });
    return () => source.close();
  }, [run]);

  const watts = points.map((p) => p.power_w ?? 0);
  const top = Math.max(1, ...watts);
  const line = watts
    .map((w, i) => `${(i / Math.max(1, watts.length - 1)) * W},${H - (w / top) * (H - 8) - 4}`)
    .join(" ");
  return (
    <section aria-label={t("runs.telemetry")}>
      <h3>{t("runs.telemetry")}</h3>
      <Alert text={error} />
      <svg
        data-testid="telemetry-chart"
        data-points={points.length}
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={H}
        role="img"
        aria-label={t("runs.chart")}
        className="chart"
      >
        <polyline points={line} fill="none" stroke="currentColor" strokeWidth="2" />
      </svg>
      <p className="muted">{t("runs.points", { count: points.length })}</p>
      <h3>{t("runs.events")}</h3>
      <ol>
        {events.map((e) => (
          <li key={e}>{e}</li>
        ))}
      </ol>
    </section>
  );
}
