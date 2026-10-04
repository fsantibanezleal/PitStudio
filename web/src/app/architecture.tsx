import type { ComponentType } from "react";
import { useTranslation } from "react-i18next";

/** Text content of one ⓘ tab. Diagrams join each tab as the matching docs pages are written. */
export function archTab(id: string): ComponentType {
  function ArchTab() {
    const { t } = useTranslation("app");
    return <p>{t(`arch.${id}.body`)}</p>;
  }
  ArchTab.displayName = `ArchTab(${id})`;
  return ArchTab;
}
