import { useTranslation } from "react-i18next";
import styles from "~/cases/cases.module.css";

export interface PendingItem {
  id: string;
  title: string;
  /** What will be reported once the comparison has run. */
  reports: string;
  /** The pre-registered acceptance criterion. */
  criterion: string;
}

/** A comparison with no published result: "Not yet run", what it will report and its criterion, and no number (FR-020-31). */
export function NotYetRun({ items }: { items: PendingItem[] }) {
  const { t } = useTranslation("results");
  return (
    <ul className={styles.rows}>
      {items.map((item) => (
        <li key={item.id} data-pending={item.id} className={styles.card}>
          <h4>{item.title}</h4>
          <p className={styles.pending}>{t("pending.status")}</p>
          <p>
            <strong>{t("pending.reports")}:</strong> {item.reports}
          </p>
          <p>
            <strong>{t("pending.criterion")}:</strong> {item.criterion}
          </p>
        </li>
      ))}
    </ul>
  );
}
