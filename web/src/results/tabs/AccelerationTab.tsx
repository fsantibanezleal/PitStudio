import { useTranslation } from "react-i18next";
import styles from "~/cases/cases.module.css";
import { formatValue } from "~/cases/KpiTable";
import { finite, langOf } from "./shared";

// FR-020-28, FR-020-30, FR-000-08: acceleration rows per model and backend with the conditions of the run. A TensorRT
// row whose licence digest is not the reviewed one shows no number: "measured locally, not published (licence)".
export const REVIEWED_TENSORRT_LICENCE_SHA256 =
  "c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4";

interface Row {
  model: string;
  backend: string;
  precision: string;
  status: string;
  reason?: string;
  latency_ms?: { p50?: number; p95?: number };
  throughput_items_per_s?: number;
  energy_j_per_inference?: number;
  accuracy_delta_pp?: number;
  parity?: string;
  tensorrt_licence_sha256?: string;
}
interface Conditions {
  gpu?: string;
  driver?: string;
  power_limit_enforced_w?: number;
  throttle_frac?: Record<string, number>;
}
export interface AccelerationBundle {
  id?: string;
  rows: Row[];
  conditions?: Conditions;
}

const THROTTLES = ["sw_power_cap", "sw_thermal", "hw_thermal", "hw_slowdown", "power_brake"] as const;
const isTensorrt = (backend: string) => /tensorrt/i.test(backend);

export function AccelerationTab({ bundles }: { bundles: AccelerationBundle[] }) {
  const { t, i18n } = useTranslation("results");
  const lang = langOf(i18n.resolvedLanguage);
  const num = (n: number | undefined, unit: (v: string) => string) =>
    finite(n) ? unit(formatValue(n, lang)) : t("rows.unavailable");

  const list = (Array.isArray(bundles) ? bundles : []).filter((b) => typeof b === "object" && b !== null);
  if (list.length === 0) return <p className={styles.pending}>{t("pending.status")}</p>;

  return (
    <div>
      {list.map((bundle, bi) => {
        const rows = (Array.isArray(bundle.rows) ? bundle.rows : []).filter(
          (r) => typeof r === "object" && r !== null,
        );
        const c = bundle.conditions ?? {};
        return (
          <section key={bundle.id ?? bi} aria-label={bundle.id ?? String(bi)}>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col">{t("accelTab.model")}</th>
                    <th scope="col">{t("accelTab.backend")}</th>
                    <th scope="col">{t("accelTab.precision")}</th>
                    <th scope="col">{t("accelTab.p50")}</th>
                    <th scope="col">{t("accelTab.p95")}</th>
                    <th scope="col">{t("accelTab.throughput")}</th>
                    <th scope="col">{t("accelTab.energy")}</th>
                    <th scope="col">{t("accelTab.delta")}</th>
                    <th scope="col">{t("accelTab.parity")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, ri) => {
                    const withheld =
                      isTensorrt(String(r.backend)) &&
                      r.tensorrt_licence_sha256 !== REVIEWED_TENSORRT_LICENCE_SHA256;
                    const shown = r.status === "accepted" && !withheld;
                    return (
                      <tr
                        // biome-ignore lint/suspicious/noArrayIndexKey: rows have no stable id beyond their position
                        key={ri}
                        data-accel-row
                        data-model={r.model}
                        data-backend={r.backend}
                        data-precision={r.precision}
                        data-status={r.status}
                      >
                        <th scope="row">{r.model}</th>
                        <td>{r.backend}</td>
                        <td>{r.precision}</td>
                        {r.status === "not-run" ? (
                          <td colSpan={6}>{t("pending.status")}</td>
                        ) : r.status === "rejected" ? (
                          <td colSpan={6}>
                            <strong>{t("accelTab.rejected")}</strong>{" "}
                            <span data-field="reason">
                              {t("accelTab.reason", { reason: String(r.reason ?? "") })}
                            </span>
                          </td>
                        ) : withheld ? (
                          <td colSpan={6} data-field="licence-withheld">
                            {t("accelTab.withheld")}
                          </td>
                        ) : (
                          shown && (
                            <>
                              <td data-field="latency-p50">
                                {num(r.latency_ms?.p50, (v) => t("accelTab.ms", { value: v }))}
                              </td>
                              <td data-field="latency-p95">
                                {num(r.latency_ms?.p95, (v) => t("accelTab.ms", { value: v }))}
                              </td>
                              <td data-field="throughput">
                                {num(r.throughput_items_per_s, (v) => t("accelTab.itemsPerS", { value: v }))}
                              </td>
                              <td data-field="energy">
                                {num(r.energy_j_per_inference, (v) => t("accelTab.joules", { value: v }))}
                              </td>
                              <td data-field="accuracy-delta">
                                {num(r.accuracy_delta_pp, (v) => t("accelTab.pp", { value: v }))}
                              </td>
                              <td data-field="parity">{String(r.parity ?? "")}</td>
                            </>
                          )
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div data-testid="conditions" className={styles.card}>
              <h4>{t("accelTab.conditions")}</h4>
              <p>{t("accelTab.gpu", { gpu: String(c.gpu ?? "") })}</p>
              <p>{t("accelTab.driver", { driver: String(c.driver ?? "") })}</p>
              <p>
                {finite(c.power_limit_enforced_w)
                  ? t("accelTab.power", { watts: formatValue(c.power_limit_enforced_w, lang) })
                  : ""}
              </p>
              <p>{t("accelTab.throttle")}</p>
              <ul>
                {THROTTLES.map((k) => (
                  <li key={k}>
                    {t(`accelTab.${k}`)}:{" "}
                    {finite(c.throttle_frac?.[k])
                      ? `${formatValue(100 * (c.throttle_frac?.[k] as number), lang)} %`
                      : t("rows.unavailable")}
                  </li>
                ))}
              </ul>
              <p>{t("accelTab.licence", { sha: REVIEWED_TENSORRT_LICENCE_SHA256 })}</p>
              <p>{t("accelTab.notComparative")}</p>
            </div>
          </section>
        );
      })}
    </div>
  );
}
