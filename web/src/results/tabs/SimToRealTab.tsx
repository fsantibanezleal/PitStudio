import { useTranslation } from "react-i18next";
import styles from "~/cases/cases.module.css";
import { formatValue } from "~/cases/KpiTable";
import { type CaseRegistry, pick } from "~/cases/types";
import type { EstimateRow } from "../ComparisonRows";
import { estimates, finite, langOf } from "./shared";

// FR-020-25 and FR-000-09: the Sim-to-real tab. Thresholds are the pre-registered ones of spec 012 (TSTR/TRTR >= 0.90,
// C2ST AUC <= 0.60 or image gap <= 0.10), compared here, never taken from a stored verdict.
const TSTR_MIN = 0.9;
const C2ST_AUC_MAX = 0.6;
const C2ST_GAP_MAX = 0.1;
const EPS = 1e-9;

const C2ST = [
  { type: "tabular", group: "c2st-tabular" },
  { type: "1-d", group: "c2st-1d" },
  { type: "images", group: "c2st-images" },
] as const;

export function SimToRealTab({ rows, registry }: { rows: unknown; registry: CaseRegistry }) {
  const { t, i18n } = useTranslation("results");
  const lang = langOf(i18n.resolvedLanguage);
  const num = (n: number) => formatValue(n, lang);
  const val = (r: EstimateRow | undefined) => (r && finite(r.value) ? num(r.value) : undefined);
  const first = (group: string, system?: string) =>
    estimates(rows, group).find((r) => system === undefined || r.system === system);
  const notRun = t("pending.status");

  const tstr = first("tstr-trtr-iou");
  const tstrValue = tstr && finite(tstr.value) ? tstr.value : undefined;

  const labels = new Map<string, string>();
  for (const entry of Object.values(registry?.cases ?? {}))
    for (const s of entry.synthetic_data ?? [])
      if (s.validation !== "validated-against-real" && !labels.has(s.label.en))
        labels.set(s.label.en, pick(s.label, lang));

  return (
    <div>
      <section aria-label={t("simToReal.tstr.title")}>
        <h3>{t("simToReal.tstr.title")}</h3>
        <div
          data-testid="tstr-ratio"
          data-met={tstrValue === undefined ? undefined : String(tstrValue + EPS >= TSTR_MIN)}
          className={styles.card}
        >
          <p>{t("simToReal.tstr.label")}</p>
          {tstr ? (
            <p>
              {t("rows.value", { value: val(tstr) ?? t("rows.unavailable") })} ·{" "}
              {t("simToReal.tstr.criterion", { value: num(TSTR_MIN) })}
            </p>
          ) : (
            <p className={styles.pending}>{notRun}</p>
          )}
        </div>
      </section>

      <section aria-label={t("simToReal.c2st.title")}>
        <h3>{t("simToReal.c2st.title")}</h3>
        <ul className={styles.rows}>
          {C2ST.map(({ type, group }) => {
            const synth = first(group, "synthetic vs real");
            const real = first(group, "real vs real");
            const auc = synth && finite(synth.value) ? synth.value : undefined;
            const base = real && finite(real.value) ? real.value : undefined;
            const gap = auc !== undefined && base !== undefined ? auc - base : undefined;
            let met: boolean | undefined;
            if (type === "images") met = gap === undefined ? undefined : gap <= C2ST_GAP_MAX + EPS;
            else met = auc === undefined ? undefined : auc <= C2ST_AUC_MAX + EPS;
            return (
              <li
                key={type}
                data-testid="c2st-row"
                data-datatype={type}
                data-met={met === undefined ? undefined : String(met)}
                className={styles.card}
              >
                <h4>{t(`simToReal.c2st.${type}`)}</h4>
                <p data-field="auc">
                  {auc === undefined ? notRun : t("simToReal.c2st.auc", { value: num(auc) })}
                </p>
                <p data-field="baseline">
                  {base === undefined ? notRun : t("simToReal.c2st.baseline", { value: num(base) })}
                </p>
                {type === "images" && (
                  <p data-field="gap">
                    {gap === undefined
                      ? notRun
                      : t("simToReal.c2st.gap", { value: (Math.round(gap * 100) / 100).toFixed(2) })}
                  </p>
                )}
                <p className={styles.unit}>
                  {t(type === "images" ? "simToReal.c2st.criterionGap" : "simToReal.c2st.criterionAuc")}
                </p>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-label={t("simToReal.sim2sim.title")}>
        <h3>{t("simToReal.sim2sim.title")}</h3>
        <ul className={styles.rows}>
          {(["fee-mpm-fill", "il-ts-twin"] as const).map((group) => {
            const row = first(group);
            const iv = row?.interval;
            return (
              <li key={group} data-testid="sim2sim" data-group={group} className={styles.card}>
                <h4>{t(`simToReal.sim2sim.${group}`)}</h4>
                {row ? (
                  <>
                    <p>{t("rows.value", { value: val(row) ?? t("rows.unavailable") })}</p>
                    {iv && finite(iv.lo) && finite(iv.hi) && (
                      <p>
                        {t("rows.interval", {
                          level: Math.round((finite(iv.level) ? iv.level : 0.95) * 100),
                          lo: num(iv.lo),
                          hi: num(iv.hi),
                          method: t(`method.${iv.method}`, { defaultValue: String(iv.method) }),
                        })}
                      </p>
                    )}
                  </>
                ) : (
                  <p className={styles.pending}>{notRun}</p>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-label={t("simToReal.probes.title")}>
        <h3>{t("simToReal.probes.title")}</h3>
        <ul className={styles.rows}>
          {(["equipment", "people"] as const).map((type) => {
            const probe = first(`real-probe-${type}`);
            return (
              <li key={type} data-testid="not-measured" data-datatype={type} className={styles.card}>
                <h4>{t(`simToReal.probes.${type}`)}</h4>
                <p>
                  {probe
                    ? t("rows.value", { value: val(probe) ?? t("rows.unavailable") })
                    : t("simToReal.probes.notMeasured")}
                </p>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-label={t("simToReal.synthetic.title")}>
        <h3>{t("simToReal.synthetic.title")}</h3>
        <ul className={styles.rows}>
          {[...labels].map(([en, shown]) => (
            <li key={en} data-testid="synthetic-label" data-datatype={en} className={styles.card}>
              <strong>{shown}</strong>: {t("simToReal.synthetic.label")}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
