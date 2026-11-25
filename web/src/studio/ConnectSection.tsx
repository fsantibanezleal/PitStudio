import { useTranslation } from "react-i18next";
import { ConnectControl } from "./ConnectControl";
import styles from "./studio.module.css";

/** The opt-in "connect to my local studio" control with its explanation, shown on every studio page (FR-019-44). */
export function ConnectSection({ id = "connect" }: { id?: string }) {
  const { t } = useTranslation("studio");
  return (
    <section aria-labelledby={id} className={styles.block}>
      <h2 id={id}>{t("connect.title")}</h2>
      <p>{t("connect.lead")}</p>
      <ConnectControl />
    </section>
  );
}
