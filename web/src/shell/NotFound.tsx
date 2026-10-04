import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import styles from "./shell.module.css";

export function NotFound() {
  const { t } = useTranslation("shell");
  return (
    <article className={styles.page}>
      <h1>{t("notFound.title")}</h1>
      <p className={styles.lead}>{t("notFound.body")}</p>
      <p>
        <Link to="/">{t("notFound.home")}</Link>
      </p>
    </article>
  );
}
