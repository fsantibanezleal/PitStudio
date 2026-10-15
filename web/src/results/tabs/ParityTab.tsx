import { useTranslation } from "react-i18next";
import styles from "~/cases/cases.module.css";

// FR-020-26: the parity report of the deployed commit (DC-018-05) grouped by system class.
interface EngineRun {
  engine: string;
  tolerance: Record<string, unknown> & { class: string };
  max_error?: Record<string, unknown>;
  browsers?: string[];
  verdict: string;
  reason?: string;
}
export interface ParityReport {
  engines: EngineRun[];
}

const numbers = (o: Record<string, unknown> | undefined) =>
  Object.entries(o ?? {})
    .filter(([, v]) => typeof v === "number")
    .map(([k, v]) => `${k} ${String(v)}`)
    .join(", ");

export function ParityTab({ report }: { report: ParityReport }) {
  const { t } = useTranslation("results");
  const engines = (Array.isArray(report?.engines) ? report.engines : []).filter(
    (e) => typeof e === "object" && e !== null && typeof e.tolerance?.class === "string",
  );
  const classes = [...new Set(engines.map((e) => e.tolerance.class))];
  if (classes.length === 0) return <p>{t("parityTab.empty")}</p>;
  return (
    <div>
      {classes.map((cls) => (
        <section key={cls} data-testid="parity-group" data-class={cls} aria-label={cls}>
          <h3>{cls}</h3>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">{t("parityTab.engine")}</th>
                  <th scope="col">{t("parityTab.class")}</th>
                  <th scope="col">{t("parityTab.tolerance")}</th>
                  <th scope="col">{t("parityTab.maxError")}</th>
                  <th scope="col">{t("parityTab.browsers")}</th>
                  <th scope="col">{t("parityTab.verdict")}</th>
                </tr>
              </thead>
              <tbody>
                {engines
                  .filter((e) => e.tolerance.class === cls)
                  .map((e) => {
                    const ran = e.verdict !== "not_run";
                    return (
                      <tr key={e.engine} data-engine={e.engine}>
                        <th scope="row">{e.engine}</th>
                        <td>{cls}</td>
                        <td>{numbers(e.tolerance)}</td>
                        <td>{ran ? numbers(e.max_error) : ""}</td>
                        <td>{ran ? (e.browsers ?? []).join(", ") : ""}</td>
                        <td>
                          {ran
                            ? e.verdict === "pass"
                              ? t("parityTab.pass")
                              : t("parityTab.fail")
                            : t("parityTab.notRun", { reason: String(e.reason ?? "") })}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}
