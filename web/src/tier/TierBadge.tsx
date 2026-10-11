import { useTranslation } from "react-i18next";
import styles from "~/cases/cases.module.css";
import { useTier } from "./probe";

/** The active compute tier as a text badge with an accessible name (FR-018-06). */
export function TierBadge() {
  const { t } = useTranslation("cases");
  const tier = useTier();
  return (
    <output aria-label={t("tier.label")} data-testid="tier-badge" data-tier={tier ?? "pending"}>
      <span className={styles.tier}>{tier ? t(`tier.${tier}`) : t("tier.detecting")}</span>
    </output>
  );
}
