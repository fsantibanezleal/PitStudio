import { useTranslation } from "react-i18next";
import styles from "./shell.module.css";

/** A planned section that has no content yet. It says so plainly and shows no invented results. */
export function PageStub({ page }: { page: string }) {
  const { t } = useTranslation("app");
  const { t: tShell } = useTranslation("shell");

  return (
    <article className={styles.page}>
      <h1>{t(`pages.${page}.title`)}</h1>
      <p className={styles.lead}>{t(`pages.${page}.lead`)}</p>
      <p className={styles.stub}>
        <span className={styles.badge}>{tShell("stub.badge")}</span> {tShell("stub.body")}
      </p>
    </article>
  );
}
