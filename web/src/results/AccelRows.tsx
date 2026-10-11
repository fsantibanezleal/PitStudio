import { useTranslation } from "react-i18next";
import styles from "~/cases/cases.module.css";
import type { AccelRow } from "./bundles";

/** Acceleration rows as a table: an accepted variant is shown with its parity; a rejected one with its reason. */
export function AccelRows({ rows }: { rows: AccelRow[] }) {
  const { t } = useTranslation("results");
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">{t("accel.model")}</th>
            <th scope="col">{t("accel.backend")}</th>
            <th scope="col">{t("accel.precision")}</th>
            <th scope="col">{t("accel.status")}</th>
            <th scope="col">{t("accel.parity")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.model}-${row.backend}-${row.precision}`} data-accel-row>
              <th scope="row">{row.model}</th>
              <td>{row.backend}</td>
              <td>{row.precision}</td>
              <td>
                {row.status}
                {row.reason && <span className={styles.unit}> · {row.reason}</span>}
              </td>
              <td>{row.parity}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
