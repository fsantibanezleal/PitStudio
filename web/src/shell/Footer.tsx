import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { useShellConfig } from "./config";
import styles from "./shell.module.css";

export function Footer() {
  const { product, version, gitSha, buildDate, author, repoUrl, footer, access } = useShellConfig();
  const { t } = useTranslation("shell");
  const { t: tApp } = useTranslation("app");
  const items = footer.useProvenance?.() ?? footer.provenance;

  return (
    <footer className={styles.footer}>
      <div className={styles.footerInner}>
        <p>
          <strong>{product}</strong> · {t("footer.version", { version })} ·{" "}
          <a href={`${repoUrl}/commit/${gitSha}`}>{t("footer.commit", { sha: gitSha })}</a> ·{" "}
          {t("footer.built", { date: buildDate })} · {t("footer.author", { author })}
        </p>
        <p>
          {t("footer.provenance")}:{" "}
          {items.map((item, i) => (
            <span key={item.labelKey}>
              {i > 0 && " · "}
              {item.href ? (
                <Link to={item.href}>{tApp(item.labelKey, item.values)}</Link>
              ) : (
                tApp(item.labelKey, item.values)
              )}
            </span>
          ))}
        </p>
        <p>
          <a href={repoUrl}>{t("footer.source")}</a> · {t("footer.licence")}: {tApp(footer.licenceKey)}
        </p>
        <p className={styles.muted}>{t("footer.disclaimer")}</p>
        {access.digest && <p className={styles.muted}>{t("footer.gate")}</p>}
      </div>
    </footer>
  );
}
